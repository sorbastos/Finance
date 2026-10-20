"""Propaga metadados pessoais de compras parceladas sem alterar dados bancários."""
import json
import re
from core import normalize


class InstallmentLinks:
    """Mantém alterações por compra e mês; usa a conexão e transação do domínio."""

    def __init__(self, store) -> None:
        """Cria histórico persistente, inclusive para parcelas ainda não importadas."""
        self.store = store
        self.db = store.db
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS installment_edits(
                series TEXT NOT NULL, month TEXT NOT NULL,
                account INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                description TEXT, category TEXT REFERENCES categories(name) ON UPDATE CASCADE,
                tags TEXT, PRIMARY KEY(series, month));
        ''')

    def rows(self) -> list[dict]:
        """Lê identidade original mesmo após correções de data, valor ou apelido."""
        return [dict(r) for r in self.db.execute('''
            SELECT t.*, a.kind, COALESCE(t.bank_description,o.description,t.description) AS original,
                   COALESCE(o.date,t.date) AS purchase_date,
                   COALESCE(o.amount,t.amount) AS purchase_amount
            FROM transactions t JOIN accounts a ON a.id=t.account
            LEFT JOIN transaction_originals o ON o.id=t.id''')]

    def key(self, row: dict) -> str | None:
        """Reconhece apenas compras exatas; nunca aproxima nomes de estabelecimentos."""
        match = re.search(r'Parcela\s+(\d+)\s+de\s+(\d+)', row['original'], re.I)
        if not match or row['kind'] != 'Cartão de crédito' or not row['invoice_month'] or row['purchase_amount'] >= 0:
            return None
        current, total = map(int, match.groups())
        if not 1 <= current <= total <= 600:
            return None
        base = re.sub(r'Parcela\s+\d+\s+de\s+\d+', '', row['original'], flags=re.I)
        metadata = {normalize(row['ownership']), normalize(row['card_number'])} - {''}
        base = ' '.join(part.strip() for part in base.split('·') if normalize(part.strip()) not in metadata).strip()
        return json.dumps([row['account'], row['purchase_date'], normalize(base), total,
                           row['purchase_amount'], row['ownership'], normalize(row['holder']),
                           re.sub(r'\D', '', row['card_number'])[-4:]], ensure_ascii=False)

    def record(self, ident: int, changes: dict) -> None:
        """Registra somente campos alterados e os aplica à parcela atual e seguintes."""
        if not changes:
            return
        rows = self.rows()
        source = next((r for r in rows if r['id'] == ident), None)
        series = self.key(source) if source else None
        if series is None:
            return
        members = [r for r in rows if self.key(r) == series]
        # Duas compras idênticas numa mesma fatura não permitem vínculo automático seguro.
        months = [r['invoice_month'] for r in members]
        if len(months) != len(set(months)):
            return
        self.db.execute('INSERT OR IGNORE INTO installment_edits(series,month,account) VALUES (?,?,?)',
                        (series, source['invoice_month'], source['account']))
        for name, value in changes.items():
            if name not in ('description', 'category', 'tags'):
                raise ValueError('Campo não permitido no vínculo de parcelas.')
            if name == 'tags':
                value = json.dumps(value, ensure_ascii=False)
            self.db.execute(f'UPDATE installment_edits SET {name}=? WHERE series=? AND month=?',
                            (value, series, source['invoice_month']))
        self.apply()

    def apply(self) -> None:
        """Herda o último valor de cada campo sem sobrescrever ajustes de meses posteriores."""
        rows = self.rows()
        counts = {}
        for row in rows:
            key = (self.key(row), row['invoice_month'])
            counts[key] = counts.get(key, 0) + 1
        ambiguous = {key[0] for key, count in counts.items() if count > 1}
        for row in rows:
            series = self.key(row)
            if series is None or series in ambiguous:
                continue
            edits = self.db.execute('SELECT * FROM installment_edits WHERE series=? AND month<=? ORDER BY month',
                                    (series, row['invoice_month'])).fetchall()
            values = {}
            for edit in edits:
                values.update({name: edit[name] for name in ('description', 'category', 'tags') if edit[name] is not None})
            if values:
                self.db.execute('INSERT OR IGNORE INTO transaction_originals VALUES (?,?,?,?,?)',
                                (row['id'], row['purchase_date'], row['original'],
                                 row['purchase_amount'], row['invoice_month']))
            for name in ('description', 'category'):
                if name not in values:
                    continue
                # Rateios e pagamentos conciliados têm regras próprias e não são reclassificados.
                if name == 'category' and (self.store.splits(row['id']) or self.db.execute(
                        'SELECT 1 FROM reconciliations WHERE debit=? OR credit=?', (row['id'], row['id'])).fetchone()):
                    continue
                self.db.execute(f'UPDATE transactions SET {name}=? WHERE id=?', (values[name], row['id']))
            if 'tags' in values:
                labels = json.loads(values['tags'])
                self.db.execute('DELETE FROM transaction_tags WHERE transaction_id=?', (row['id'],))
                self.db.executemany('INSERT OR IGNORE INTO tags VALUES (?)', [(tag,) for tag in labels])
                self.db.executemany('INSERT INTO transaction_tags VALUES (?,?)', [(row['id'], tag) for tag in labels])
