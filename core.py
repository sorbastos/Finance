"""Importação e armazenamento locais, sem dependências externas."""
import csv
import hashlib
import html
import io
import re
import sqlite3
import unicodedata
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path


def normalize(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value.lower()) if not unicodedata.combining(c)).strip()


def money(value):
    value = str(value).strip().replace('R$', '').replace('\u00a0', '').replace(' ', '')
    if value.startswith('(') and value.endswith(')'):
        value = '-' + value[1:-1]
    if ',' in value:
        value = value.replace('.', '').replace(',', '.')
    try:
        result = Decimal(value)
        if not result.is_finite() or result != result.quantize(Decimal('.01')):
            raise ValueError('Valor deve ter até duas casas decimais')
        return int(result * 100)
    except InvalidOperation as exc:
        raise ValueError(f'Valor inválido: {value}') from exc


def date(value):
    value = value.strip()
    for pattern, candidate in [('%Y%m%d', value[:8]), ('%Y-%m-%d', value[:10]), ('%d/%m/%Y', value), ('%d/%m/%y', value)]:
        try:
            return datetime.strptime(candidate, pattern).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f'Data inválida: {value}')


def decode(raw):
    if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
        return raw.decode('utf-16')
    try:
        return raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        return raw.decode('cp1252')


def csv_table(raw):
    text = decode(raw)
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=';,\t')
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    fields = reader.fieldnames or []
    if len(fields) < 2 or len(set(fields)) != len(fields):
        raise ValueError('CSV precisa de cabeçalho com colunas distintas (data, descrição e valor).')
    return fields, list(reader)


def parse_csv(rows, mapping, invert=False):
    result = []
    for index, row in enumerate(rows, 2):
        try:
            description = row[mapping['description']].strip()
            if not description:
                raise ValueError('Descrição vazia')
            result.append(dict(date=date(row[mapping['date']]), description=description,
                               amount=money(row[mapping['amount']]) * (-1 if invert else 1),
                               fitid=(row.get(mapping.get('fitid', ''), '') or '').strip()))
        except (ValueError, KeyError, AttributeError, TypeError) as exc:
            raise ValueError(f'Linha {index}: {exc}. Nenhuma linha foi salva.') from exc
    if not result:
        raise ValueError('Arquivo sem lançamentos.')
    return result


def parse_ofx(raw):
    text = decode(raw)
    currencies = re.findall(r'<CURDEF>\s*([^<\r\n]+)', text, re.I)
    if any(c.strip().upper() != 'BRL' for c in currencies):
        raise ValueError('Esta versão aceita apenas extratos em reais (BRL).')
    accounts = re.findall(r'<ACCTID>\s*([^<\r\n]+)', text, re.I)
    if len(set(accounts)) > 1:
        raise ValueError('Exporte uma conta por arquivo OFX.')
    result = []
    for index, block in enumerate(re.findall(r'<STMTTRN>(.*?)</STMTTRN>', text, re.I | re.S), 1):
        def tag(name):
            match = re.search(r'<' + name + r'>\s*([^<\r\n]*)', block, re.I)
            return html.unescape(match.group(1).strip()) if match else ''
        try:
            description = ' · '.join(dict.fromkeys(x for x in (tag('NAME'), tag('MEMO')) if x)) or tag('TRNTYPE')
            result.append(dict(date=date(tag('DTPOSTED')), description=description,
                               amount=money(tag('TRNAMT')), fitid=tag('FITID')))
            if normalize(description).startswith('fatura paga'):
                result[-1]['category'] = CATEGORIES[-1]
        except ValueError as exc:
            raise ValueError(f'Lançamento OFX {index}: {exc}') from exc
    if not result:
        raise ValueError('Nenhum lançamento STMTTRN encontrado no OFX.')
    return result


CATEGORIES = ['Sem categoria', 'Alimentação', 'Mercado', 'Transporte', 'Moradia', 'Saúde', 'Educação', 'Lazer', 'Compras', 'Serviços', 'Receita', 'Transferência / pagamento de fatura']


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS accounts(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, kind TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS batches(id INTEGER PRIMARY KEY, account INTEGER REFERENCES accounts, filename TEXT, digest TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(account,digest));
        CREATE TABLE IF NOT EXISTS transactions(id INTEGER PRIMARY KEY, account INTEGER REFERENCES accounts, batch INTEGER REFERENCES batches, date TEXT, description TEXT, amount INTEGER, fitid TEXT, category TEXT);
        CREATE UNIQUE INDEX IF NOT EXISTS transaction_fitid ON transactions(account,fitid) WHERE fitid != '';
        CREATE TABLE IF NOT EXISTS rules(term TEXT PRIMARY KEY, category TEXT);
        ''')

        columns = {r[1] for r in self.db.execute('PRAGMA table_info(transactions)')}
        if 'invoice_month' not in columns:
            self.db.execute("ALTER TABLE transactions ADD COLUMN invoice_month TEXT NOT NULL DEFAULT ''")
            self.db.commit()

    def accounts(self):
        return self.db.execute('SELECT * FROM accounts ORDER BY name').fetchall()

    def add_account(self, name, kind):
        if not name.strip():
            raise ValueError('Informe um nome.')
        with self.db:
            self.db.execute('INSERT INTO accounts(name,kind) VALUES (?,?)', (name.strip(), kind))

    def category(self, description):
        for rule in self.db.execute('SELECT * FROM rules ORDER BY length(term) DESC'):
            if rule['term'] in normalize(description):
                return rule['category']
        return 'Sem categoria'

    def preview(self, account, rows):
        existing = self.db.execute('SELECT * FROM transactions WHERE account=?', (account,)).fetchall()
        ids = {r['fitid']: r for r in existing if r['fitid']}
        counts = Counter((r['date'], normalize(r['description']), r['amount'], r['invoice_month']) for r in existing)
        seen = Counter()
        result = []
        for row in rows:
            row = dict(row)
            key = row['date'], normalize(row['description']), row['amount'], row.get('invoice_month', '')
            seen[key] += 1
            status = 'Novo'
            if row['fitid'] and row['fitid'] in ids:
                old = ids[row['fitid']]
                status = 'Duplicado (ID)' if (old['date'], old['amount']) == (row['date'], row['amount']) else 'Conflito de ID'
            elif seen[key] <= counts[key]:
                status = 'Possível duplicata'
            if row['fitid']:
                ids[row['fitid']] = row
            row.update(status=status, category=row.get('category') if row.get('category', 'Sem categoria') != 'Sem categoria' else self.category(row['description']))
            result.append(row)
        return result

    def save(self, account, filename, raw, rows, include_possible=False):
        digest = hashlib.sha256(raw).hexdigest()
        with self.db:
            if self.db.execute('SELECT 1 FROM batches WHERE account=? AND digest=?', (account, digest)).fetchone():
                raise ValueError('Este arquivo já foi importado nesta conta.')
            batch = self.db.execute('INSERT INTO batches(account,filename,digest) VALUES (?,?,?)', (account, filename, digest)).lastrowid
            count = 0
            for row in rows:
                if row['status'] != 'Novo' and not (include_possible and row['status'] == 'Possível duplicata'):
                    continue
                self.db.execute('INSERT INTO transactions(account,batch,date,description,amount,fitid,category,invoice_month) VALUES (?,?,?,?,?,?,?,?)',
                                (account, batch, row['date'], row['description'], row['amount'], row['fitid'], row['category'], row.get('invoice_month', '')))
                count += 1
            if count == 0:
                raise ValueError('Nenhum lançamento novo para salvar.')
        return count

    def transactions(self, month='', account=None, search=''):
        return self.db.execute('''SELECT t.*, a.name, a.kind FROM transactions t JOIN accounts a ON a.id=t.account
        WHERE COALESCE(NULLIF(invoice_month,''),substr(date,1,7)) LIKE ? AND (? IS NULL OR account=?) AND description LIKE ? ORDER BY date DESC, t.id DESC''',
                               (month + '%', account, account, '%' + search + '%')).fetchall()

    def categorize(self, ids, category, term=''):
        with self.db:
            self.db.executemany('UPDATE transactions SET category=? WHERE id=?', [(category, i) for i in ids])
            if term.strip():
                self.db.execute('INSERT OR REPLACE INTO rules VALUES (?,?)', (normalize(term), category))

    def undo(self):
        batch = self.db.execute('SELECT id FROM batches ORDER BY id DESC LIMIT 1').fetchone()
        if batch:
            with self.db:
                self.db.execute('DELETE FROM transactions WHERE batch=?', (batch['id'],))
                self.db.execute('DELETE FROM batches WHERE id=?', (batch['id'],))

    def backup(self, path):
        with sqlite3.connect(path) as destination:
            self.db.backup(destination)
