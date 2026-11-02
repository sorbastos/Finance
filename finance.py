"""Planejamento e manutenção financeira. Previsões nunca são lançamentos reais."""
import hashlib
import re
from collections import defaultdict
from datetime import datetime
from core import Store, CATEGORIES, normalize, date

TRANSFER = CATEGORIES[-1]


def month_shift(month, delta):
    validate_month(month)
    year, number = map(int, month.split('-'))
    absolute = year * 12 + number - 1 + delta
    return f'{absolute // 12:04d}-{absolute % 12 + 1:02d}'


def validate_month(month):
    if not re.fullmatch(r'\d{4}-\d{2}', month or ''):
        raise ValueError('Informe o mês no formato AAAA-MM.')
    datetime.strptime(month, '%Y-%m')
    return month


class FinanceStore(Store):
    def __init__(self, path):
        super().__init__(path)
        columns={r[1] for r in self.db.execute('PRAGMA table_info(transactions)')}
        for name in ('ownership','holder','card_number'):
            if name not in columns:
                self.db.execute(f"ALTER TABLE transactions ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")
        self.db.execute("UPDATE transactions SET ownership='Adicional' WHERE ownership='' AND description LIKE '% · Adicional'")
        self.db.execute("UPDATE transactions SET ownership='Titular' WHERE ownership='' AND description LIKE '% · Titular'")
        self.db.commit()
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS invoice_snapshots(
          batch INTEGER REFERENCES batches(id) ON DELETE CASCADE,
          account INTEGER REFERENCES accounts(id), month TEXT, due TEXT, state TEXT, total INTEGER,
          PRIMARY KEY(batch,month));
        CREATE TABLE IF NOT EXISTS invoice_overrides(
          account INTEGER REFERENCES accounts(id), month TEXT, due TEXT, state TEXT, total INTEGER,
          PRIMARY KEY(account,month));
        CREATE TABLE IF NOT EXISTS budgets(month TEXT, category TEXT, amount INTEGER CHECK(amount>=0), PRIMARY KEY(month,category));
        CREATE TABLE IF NOT EXISTS reconciliations(
          id INTEGER PRIMARY KEY, debit INTEGER UNIQUE REFERENCES transactions(id) ON DELETE CASCADE,
          credit INTEGER UNIQUE REFERENCES transactions(id) ON DELETE CASCADE, invoice_month TEXT,
          old_debit_category TEXT, old_credit_category TEXT);
        CREATE TABLE IF NOT EXISTS transaction_originals(
          id INTEGER PRIMARY KEY REFERENCES transactions(id) ON DELETE CASCADE,
          date TEXT, description TEXT, amount INTEGER, invoice_month TEXT);
        CREATE TABLE IF NOT EXISTS monthly_closings(
          account INTEGER REFERENCES accounts(id) ON DELETE CASCADE, month TEXT,
          opening INTEGER NOT NULL, reported_closing INTEGER NOT NULL,
          PRIMARY KEY(account,month));
        CREATE TABLE IF NOT EXISTS transaction_splits(
          transaction_id INTEGER REFERENCES transactions(id) ON DELETE CASCADE,
          category TEXT NOT NULL, amount INTEGER NOT NULL,
          PRIMARY KEY(transaction_id,category));
        CREATE TABLE IF NOT EXISTS tags(name TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS transaction_tags(
          transaction_id INTEGER REFERENCES transactions(id) ON DELETE CASCADE,
          tag TEXT REFERENCES tags(name) ON UPDATE CASCADE ON DELETE CASCADE,
          PRIMARY KEY(transaction_id,tag));
        CREATE TABLE IF NOT EXISTS installment_plans(
          transaction_id INTEGER PRIMARY KEY REFERENCES transactions(id) ON DELETE CASCADE,
          current_number INTEGER NOT NULL, total_number INTEGER NOT NULL,
          anticipated INTEGER NOT NULL DEFAULT 0, cancelled INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS forecast_exclusions(
          transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
          month TEXT NOT NULL,
          PRIMARY KEY(transaction_id,month));
        ''')

        # A descrição importada tem armazenamento próprio e não acompanha o
        # apelido editável. Recupera originais salvos antes desta atualização.
        if 'bank_description' not in columns:
            self.db.execute('ALTER TABLE transactions ADD COLUMN bank_description TEXT')
        with self.db:
            self.db.execute('''UPDATE transactions SET bank_description=COALESCE(
                (SELECT description FROM transaction_originals o WHERE o.id=transactions.id),description)
                WHERE batch IS NOT NULL AND bank_description IS NULL''')
        self.db.executescript('''
        CREATE TRIGGER IF NOT EXISTS protect_bank_description
        BEFORE UPDATE OF bank_description ON transactions
        WHEN OLD.bank_description IS NOT NULL AND NEW.bank_description IS NOT OLD.bank_description
        BEGIN
          SELECT RAISE(ABORT,'A descrição original do banco não pode ser alterada.');
        END;
        ''')

        if not self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='categories'").fetchone():
            with self.db:
                self.db.execute('CREATE TABLE categories(name TEXT PRIMARY KEY)')
                names = set(CATEGORIES)
                for table in ('transactions', 'rules', 'budgets'):
                    names.update(r[0] for r in self.db.execute(f'SELECT DISTINCT category FROM {table}') if r[0])
                self.db.executemany('INSERT INTO categories VALUES (?)', [(name,) for name in names])
        from installments import InstallmentLinks
        self.installment_links = InstallmentLinks(self)
        from budgeting import BudgetPlanner
        self.planner = BudgetPlanner(self)

    def categories(self):
        return [r[0] for r in self.db.execute('SELECT name FROM categories ORDER BY name COLLATE NOCASE')]

    def save_category(self, name, old_name=None):
        """Cria ou renomeia categorias, preservando vínculos, regras e rateios."""
        name = ' '.join(name.split())
        if not name or len(name) > 60:
            raise ValueError('Informe um nome de categoria com até 60 caracteres.')
        names = self.categories()
        if old_name is not None and old_name not in names:
            raise ValueError('Selecione uma categoria existente.')
        if old_name in ('Sem categoria', TRANSFER):
            raise ValueError('Esta categoria é usada pelo sistema e não pode ser renomeada.')
        if any(normalize(existing) == normalize(name) and existing != old_name for existing in names):
            raise ValueError('Já existe uma categoria com esse nome.')
        with self.db:
            if old_name is None:
                self.db.execute('INSERT INTO categories VALUES (?)', (name,))
            else:
                self.db.execute('UPDATE categories SET name=? WHERE name=?', (name, old_name))
                for table in ('transactions', 'rules', 'budgets', 'transaction_splits'):
                    self.db.execute(f'UPDATE {table} SET category=? WHERE category=?', (name, old_name))
                for column in ('old_debit_category', 'old_credit_category'):
                    self.db.execute(f'UPDATE reconciliations SET {column}=? WHERE {column}=?', (name, old_name))
        return name

    def delete_category(self, name: str, replacement: str) -> None:
        """Exclui categoria após transferir referências; rateios convergentes são somados.

        O grupo do destino prevalece. Valores financeiros, descrições e identidades
        dos lançamentos são preservados, inclusive nas futuras parcelas vinculadas.
        """
        if name in ('Sem categoria', TRANSFER):
            raise ValueError('Esta categoria é usada pelo sistema e não pode ser excluída.')
        if name not in self.categories() or replacement not in self.categories() or replacement in (name, TRANSFER):
            raise ValueError('Selecione uma categoria existente e um destino diferente.')
        with self.db:
            for table in ('transactions', 'rules', 'installment_edits'):
                self.db.execute(f'UPDATE {table} SET category=? WHERE category=?', (replacement, name))
            for column in ('old_debit_category', 'old_credit_category'):
                self.db.execute(f'UPDATE reconciliations SET {column}=? WHERE {column}=?', (replacement, name))
            for row in self.db.execute('SELECT * FROM transaction_splits WHERE category=?', (name,)).fetchall():
                self.db.execute('''INSERT INTO transaction_splits VALUES (?,?,?)
                    ON CONFLICT(transaction_id,category) DO UPDATE SET amount=amount+excluded.amount''',
                    (row['transaction_id'], replacement, row['amount']))
            self.db.execute('DELETE FROM transaction_splits WHERE category=?', (name,))
            for row in self.db.execute('SELECT * FROM budgets WHERE category=?', (name,)).fetchall():
                self.db.execute('''INSERT INTO budgets VALUES (?,?,?)
                    ON CONFLICT(month,category) DO UPDATE SET amount=amount+excluded.amount''',
                    (row['month'], replacement, row['amount']))
            self.db.execute('DELETE FROM budgets WHERE category=?', (name,))
            self.db.execute('DELETE FROM categories WHERE name=?', (name,))

    def tags(self):
        return [r[0] for r in self.db.execute('SELECT name FROM tags ORDER BY name COLLATE NOCASE')]

    def transaction_tags(self, ident):
        return [r[0] for r in self.db.execute('SELECT tag FROM transaction_tags WHERE transaction_id=? ORDER BY tag COLLATE NOCASE',(ident,))]

    def set_transaction_tags(self, ident, tags):
        if not self.db.execute('SELECT 1 FROM transactions WHERE id=?',(ident,)).fetchone():
            raise ValueError('Lançamento não encontrado.')
        clean=[]
        for value in tags:
            name=' '.join(value.split())
            if name and name not in clean: clean.append(name)
        if any(len(name)>40 for name in clean): raise ValueError('Cada etiqueta pode ter até 40 caracteres.')
        with self.db:
            previous = self.transaction_tags(ident)
            self.db.execute('DELETE FROM transaction_tags WHERE transaction_id=?',(ident,))
            self.db.executemany('INSERT OR IGNORE INTO tags VALUES (?)',[(name,) for name in clean])
            self.db.executemany('INSERT INTO transaction_tags VALUES (?,?)',[(ident,name) for name in clean])
            if set(previous) != set(clean):
                self.installment_links.record(ident, {'tags': clean})

    def splits(self, ident):
        return [dict(r) for r in self.db.execute('SELECT category,amount FROM transaction_splits WHERE transaction_id=? ORDER BY category',(ident,))]

    def set_splits(self, ident, splits):
        row=self.db.execute('SELECT amount FROM transactions WHERE id=?',(ident,)).fetchone()
        if not row: raise ValueError('Lançamento não encontrado.')
        if self.db.execute('SELECT 1 FROM reconciliations WHERE debit=? OR credit=?',(ident,ident)).fetchone():
            raise ValueError('Pagamentos conciliados não podem ser divididos.')
        merged=defaultdict(int)
        for category,amount in splits:
            if category not in self.categories() or category==TRANSFER: raise ValueError('Categoria da divisão inválida.')
            if not amount or (amount>0)!=(row['amount']>0): raise ValueError('As partes devem ter o mesmo sinal do lançamento.')
            merged[category]+=amount
        if len(merged)<2: raise ValueError('Use pelo menos duas categorias na divisão.')
        if sum(merged.values())!=row['amount']: raise ValueError('A soma das partes deve ser igual ao valor do lançamento.')
        with self.db:
            self.db.execute('DELETE FROM transaction_splits WHERE transaction_id=?',(ident,))
            self.db.executemany('INSERT INTO transaction_splits VALUES (?,?,?)',[(ident,c,a) for c,a in merged.items()])

    def clear_splits(self, ident):
        with self.db: self.db.execute('DELETE FROM transaction_splits WHERE transaction_id=?',(ident,))

    def allocations(self, row):
        parts=self.splits(row['id'])
        return parts or [dict(category=row['category'],amount=row['amount'])]

    def set_closing(self, account, month, opening, reported_closing):
        validate_month(month)
        kind=self.db.execute('SELECT kind FROM accounts WHERE id=?',(account,)).fetchone()
        if not kind or kind[0]!='Conta corrente': raise ValueError('O fechamento mensal se aplica a uma conta corrente.')
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO monthly_closings VALUES (?,?,?,?)',(account,month,opening,reported_closing))

    def closings(self, month=''):
        params=[];where=''
        if month: validate_month(month);where='WHERE c.month=?';params=[month]
        result=[]
        for r in self.db.execute(f'''SELECT c.*,a.name FROM monthly_closings c JOIN accounts a ON a.id=c.account
                                    {where} ORDER BY c.month DESC,a.name''',params):
            movement=self.db.execute("SELECT COALESCE(sum(amount),0) FROM transactions WHERE account=? AND substr(date,1,7)=?",(r['account'],r['month'])).fetchone()[0]
            calculated=r['opening']+movement
            result.append(dict(r, movement=movement, calculated=calculated,
                               difference=r['reported_closing']-calculated,
                               state='Conferido' if r['reported_closing']==calculated else 'Com diferença'))
        return result

    def save(self, account, filename, raw, rows, include_possible=False):
        digest = hashlib.sha256(raw).hexdigest()
        metadata = {(r['invoice_month'], r.get('invoice_due', ''), r.get('invoice_state', 'Aberta'), r.get('invoice_total'))
                    for r in rows if r.get('invoice_metadata')}
        with self.db:
            existing = self.db.execute('SELECT id FROM batches WHERE account=? AND digest=?', (account,digest)).fetchone()
            if existing:
                if metadata and not self.db.execute('SELECT 1 FROM invoice_snapshots WHERE batch=?',(existing['id'],)).fetchone():
                    for month,due,state,total in metadata:
                        self.db.execute('INSERT INTO invoice_snapshots VALUES (?,?,?,?,?,?)',(existing['id'],account,month,due,state,total))
                    self.enrich_holders(account, rows)
                    return 0
                raise ValueError('Este arquivo já foi importado nesta conta.')
            batch = self.db.execute('INSERT INTO batches(account,filename,digest) VALUES (?,?,?)', (account,filename,digest)).lastrowid
            count = 0
            for row in rows:
                if row['status'] != 'Novo' and not (include_possible and row['status'] == 'Possível duplicata'):
                    continue
                self.db.execute('INSERT INTO transactions(account,batch,date,description,amount,fitid,category,invoice_month,bank_description) VALUES (?,?,?,?,?,?,?,?,?)',
                    (account,batch,row['date'],row['description'],row['amount'],row['fitid'],row['category'],row.get('invoice_month',''),row['description']))
                ident=self.db.execute('SELECT last_insert_rowid()').fetchone()[0]
                self.db.execute('UPDATE transactions SET ownership=?,holder=?,card_number=? WHERE id=?',
                    (row.get('ownership',''),row.get('holder',''),row.get('card_number',''),ident))
                count += 1
            for month, due, state, total in metadata:
                self.db.execute('INSERT INTO invoice_snapshots VALUES (?,?,?,?,?,?)', (batch,account,month,due,state,total))
            self.enrich_holders(account, rows)
            self.installment_links.apply()
            if not count and not metadata:
                raise ValueError('Nenhum lançamento novo para salvar.')
        return count

    def enrich_holders(self, account, rows):
        groups=defaultdict(list)
        for r in self.db.execute("""SELECT t.id,COALESCE(o.date,t.date) AS date,
          COALESCE(t.bank_description,o.description,t.description) AS description,COALESCE(o.amount,t.amount) AS amount,
          COALESCE(o.invoice_month,t.invoice_month) AS invoice_month FROM transactions t
          LEFT JOIN transaction_originals o ON t.id=o.id WHERE t.account=? ORDER BY t.id""",(account,)):
            groups[(r['date'],normalize(r['description']),r['amount'],r['invoice_month'])].append(r['id'])
        for row in rows:
            if not row.get('invoice_metadata'): continue
            key=(row['date'],normalize(row['description']),row['amount'],row.get('invoice_month',''))
            if groups[key]:
                ident=groups[key].pop(0)
                for field in ('ownership','holder','card_number'):
                    value=row.get(field,'')
                    if value: self.db.execute(f"UPDATE transactions SET {field}=? WHERE id=? AND {field}=''",(value,ident))

    def preview(self, account, rows):
        # Compare imported rows with original values, even after user corrections.
        originals = self.db.execute('''SELECT t.id,COALESCE(o.date,t.date) AS date,
           COALESCE(t.bank_description,o.description,t.description) AS description, COALESCE(o.amount,t.amount) AS amount,
           COALESCE(o.invoice_month,t.invoice_month) AS invoice_month,t.fitid
           FROM transactions t LEFT JOIN transaction_originals o ON t.id=o.id WHERE t.account=?''',(account,)).fetchall()
        from collections import Counter
        counts = Counter((r['date'],normalize(r['description']),r['amount'],r['invoice_month']) for r in originals)
        ids = {r['fitid']:r for r in originals if r['fitid']}
        seen = Counter()
        result=[]
        for source in rows:
            r=dict(source)
            key=(r['date'],normalize(r['description']),r['amount'],r.get('invoice_month',''))
            seen[key]+=1
            status='Novo'
            if r['fitid'] and r['fitid'] in ids:
                old=ids[r['fitid']]
                status='Duplicado (ID)' if (old['date'],old['amount'])==(r['date'],r['amount']) else 'Conflito de ID'
            elif seen[key]<=counts[key]:
                status='Possível duplicata'
            if r['fitid']: ids[r['fitid']]=r
            r.update(status=status,category=r.get('category') if r.get('category','Sem categoria')!='Sem categoria' else self.category(r['description']))
            result.append(r)
        return result

    def transactions(self, month='', account=None, search='', ownership=''):
        """Pesquisa descrição personalizada e original, respeitando os filtros."""
        rows = self.db.execute('''SELECT t.*,a.name,a.kind FROM transactions t JOIN accounts a ON a.id=t.account
            WHERE COALESCE(NULLIF(invoice_month,''),substr(date,1,7)) LIKE ?
            AND (? IS NULL OR account=?)
            AND (description LIKE ? OR COALESCE(bank_description,'') LIKE ?)
            ORDER BY date DESC,t.id DESC''',
            (month+'%',account,account,'%'+search+'%','%'+search+'%')).fetchall()
        if ownership:
            return [r for r in rows if r['ownership']==ownership]
        return rows

    def invoices(self, account=None):
        grouped=defaultdict(list)
        for r in self.transactions(account=account):
            if r['kind']=='Cartão de crédito' and r['invoice_month']:
                grouped[(r['account'],r['invoice_month'])].append(r)
        snapshots={}
        for r in self.db.execute('SELECT * FROM invoice_snapshots ORDER BY batch'):
            if account is None or r['account']==account:
                snapshots[(r['account'],r['month'])]=dict(r)
        overrides={(r['account'],r['month']):dict(r) for r in self.db.execute('SELECT * FROM invoice_overrides') if account is None or r['account']==account}
        names={a['id']:a['name'] for a in self.accounts()}
        result=[]
        for key in sorted(set(grouped)|set(snapshots)|set(overrides),key=lambda k:(k[1],k[0]),reverse=True):
            acc,month=key
            meta=overrides.get(key,snapshots.get(key,{}))
            rows=grouped[key]
            calculated=-sum(r['amount'] for r in rows if r['category']!=TRANSFER)
            total=meta.get('total')
            paid=self.db.execute('''SELECT COALESCE(sum(c.amount),0) FROM reconciliations r
                JOIN transactions c ON c.id=r.credit WHERE c.account=? AND r.invoice_month=?''',(acc,month)).fetchone()[0]
            due=meta.get('due','')
            result.append(dict(account=acc,name=names[acc],month=month,due=due,state=meta.get('state','A conferir'),
                total=total,calculated=calculated,
                titular=-sum(r['amount'] for r in rows if r['category']!=TRANSFER and r['ownership']=='Titular'),
                adicional=-sum(r['amount'] for r in rows if r['category']!=TRANSFER and r['ownership']=='Adicional'),
                unknown=-sum(r['amount'] for r in rows if r['category']!=TRANSFER and r['ownership'] not in ('Titular','Adicional')),
                paid=paid,remaining=max(0,(total if total is not None else calculated)-paid),
                source='Informado' if key in overrides else ('Extrato' if key in snapshots else 'Lançamentos')))
        return result

    def set_invoice(self, account, month, due, state, total):
        validate_month(month)
        if due: due=date(due)
        if state not in ('Aberta','Fechada','A conferir'): raise ValueError('Situação inválida.')
        if total is not None and total<0: raise ValueError('Total não pode ser negativo.')
        a=self.db.execute('SELECT kind FROM accounts WHERE id=?',(account,)).fetchone()
        if not a or a['kind']!='Cartão de crédito': raise ValueError('Selecione um cartão.')
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO invoice_overrides VALUES (?,?,?,?,?)',(account,month,due,state,total))

    def forecasts(self, account=None):
        """Projeta a última parcela observada de cada compra, sem gravar previsões.

        Titular, portador e final do cartão pertencem à identidade da compra.
        Repetições entre lotes não multiplicam a previsão, mas duas compras
        iguais presentes no mesmo lote continuam sendo duas compras.
        """
        series=defaultdict(lambda:defaultdict(list))
        for r in self.transactions(account=account):
            original = r['bank_description'] or r['description']
            match=re.search(r'Parcela\s+(\d+)\s+de\s+(\d+)',original,re.I)
            if not match or not r['invoice_month'] or r['kind']!='Cartão de crédito' or r['amount']>=0 or r['category']==TRANSFER: continue
            current,total=map(int,match.groups())
            override=self.db.execute('SELECT * FROM installment_plans WHERE transaction_id=?',(r['id'],)).fetchone()
            if override:
                current,total=override['current_number'],override['total_number']
            if not 1<=current<=total<=600: continue
            base=re.sub(r'Parcela\s+\d+\s+de\s+\d+','',original,flags=re.I)
            # Metadados anexados pelo XLSX não devem mudar a descrição-base.
            metadata = {normalize(r['ownership']), normalize(r['card_number'])} - {''}
            base = ' · '.join(part.strip() for part in base.split('·')
                              if part.strip() and normalize(part.strip()) not in metadata)
            card = re.sub(r'\D', '', r['card_number'])[-4:]
            key=(r['account'],r['date'],normalize(base),total,
                 r['ownership'], normalize(r['holder']), card)
            series[key][r['invoice_month']].append((dict(r),current,total))
        result=[]
        for periods in series.values():
            latest=max(periods)
            # Se a mesma competência mostra mais de uma etapa da compra,
            # a mais avançada substitui as anteriores na projeção.
            last_number = max(current for _, current, _ in periods[latest])
            candidates = [item for item in periods[latest] if item[1] == last_number]
            for r,current,total in self._unique_installment_sources(candidates):
                plan=self.db.execute('SELECT * FROM installment_plans WHERE transaction_id=?',(r['id'],)).fetchone()
                if plan and plan['cancelled']:
                    result.append(dict(month=month_shift(latest,1),account=r['account'],name=r['name'],transaction_id=r['id'],
                        description='Parcelas futuras canceladas · '+r['description'],amount=0,status='Cancelado',source_month=latest,
                        ownership=r.get('ownership','') or 'Não informado',holder=r.get('holder','')))
                    continue
                anticipated=plan['anticipated'] if plan else 0
                if anticipated:
                    result.append(dict(month=month_shift(latest,1),account=r['account'],name=r['name'],transaction_id=r['id'],
                        description=f'Antecipação de {anticipated} parcelas · {r["description"]}',amount=(-r['amount'])*anticipated,
                        status='Antecipado',source_month=latest,ownership=r.get('ownership','') or 'Não informado',holder=r.get('holder','')))
                for number in range(current+1+anticipated,total+1):
                    result.append(dict(month=month_shift(latest,number-current),account=r['account'],name=r['name'],
                        transaction_id=r['id'],
                        description=self._forecast_description(r,number,total),
                        amount=-r['amount'],status='Previsto',source_month=latest,
                        ownership=r.get('ownership','') or 'Não informado',holder=r.get('holder','')))
        # Exclusões são aplicadas depois da escolha da origem, para não fazer
        # uma observação antiga reaparecer ao esconder a previsão selecionada.
        excluded = {(r['transaction_id'], r['month']) for r in self.db.execute('SELECT * FROM forecast_exclusions')}
        result = [r for r in result if (r['transaction_id'], r['month']) not in excluded
                  and (r['transaction_id'], '*') not in excluded]
        return sorted(result,key=lambda r:(r['month'],r['name'],r['description']))

    def _forecast_description(self, row: dict, number: int, total: int) -> str:
        """Exibe o nome personalizado sem perder a numeração técnica da parcela."""
        if row.get('bank_description') and row['description'] != row['bank_description']:
            return f'{row["description"]} · Parcela {number} de {total}'
        return re.sub(r'Parcela\s+\d+\s+de\s+\d+',f'Parcela {number} de {total}',row['description'],flags=re.I)

    def exclude_forecast(self, ident: int, month: str, all_months: bool = False) -> None:
        """Oculta previsões da origem indicada sem apagar a compra confirmada.

        '*' cobre todas as competências geradas por esse lançamento de origem.
        Uma exclusão mensal afeta somente a parcela da competência escolhida.
        A confirmação deve ocorrer na apresentação antes desta gravação.
        """
        validate_month(month)
        if not any(r['transaction_id'] == ident and r['month'] == month for r in self.forecasts()):
            raise ValueError('A previsão não está mais disponível. Atualize a lista.')
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO forecast_exclusions VALUES (?,?)',
                            (ident, '*' if all_months else month))

    def _unique_installment_sources(self, records: list[tuple]) -> list[tuple]:
        """Usa a maior multiplicidade observada, nunca a soma de reimportações.

        IDs bancários distintos são evidência de compras distintas. Sem IDs,
        a multiplicidade dentro de um lote é preservada; entre lotes idênticos
        considera-se uma repetição da observação. Lançamentos manuais continuam
        com a multiplicidade informada pelo usuário.
        """
        signatures = defaultdict(lambda: defaultdict(list))
        for item in records:
            row, current, total = item
            signature = (current, total, row['amount'], row['fitid'] or '')
            signatures[signature][row['batch']].append(item)
        result = []
        for batches in signatures.values():
            chosen = max(batches.values(), key=lambda items: (len(items), max(r['id'] for r, _, _ in items)))
            result.extend(chosen)
        return result

    def installment_plan(self, ident):
        row=self.db.execute('SELECT * FROM transactions WHERE id=?',(ident,)).fetchone()
        if not row: raise ValueError('Lançamento não encontrado.')
        match=re.search(r'Parcela\s+(\d+)\s+de\s+(\d+)',row['bank_description'] or row['description'],re.I)
        plan=self.db.execute('SELECT * FROM installment_plans WHERE transaction_id=?',(ident,)).fetchone()
        if plan: return dict(plan)
        if not match: raise ValueError('O lançamento selecionado não possui indicação de parcela.')
        current,total=map(int,match.groups())
        return dict(transaction_id=ident,current_number=current,total_number=total,anticipated=0,cancelled=0)

    def set_installment_plan(self, ident, current, total, anticipated=0, cancelled=False):
        row=self.db.execute('''SELECT t.*,a.kind FROM transactions t JOIN accounts a ON a.id=t.account WHERE t.id=?''',(ident,)).fetchone()
        if not row or row['kind']!='Cartão de crédito': raise ValueError('Selecione uma compra parcelada do cartão.')
        if not 1<=current<=total<=600: raise ValueError('A parcela atual e o total informado são inválidos.')
        if not 0<=anticipated<=total-current: raise ValueError('A quantidade antecipada excede as parcelas restantes.')
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO installment_plans VALUES (?,?,?,?,?)',(ident,current,total,anticipated,1 if cancelled else 0))

    def payment_candidates(self):
        rows=self.transactions()
        used={r[0] for r in self.db.execute('SELECT debit FROM reconciliations UNION SELECT credit FROM reconciliations')}
        debits=[r for r in rows if r['id'] not in used and r['kind']=='Conta corrente' and r['amount']<0 and (r['category']==TRANSFER or 'fatura' in normalize(r['bank_description'] or r['description']))]
        credits=[r for r in rows if r['id'] not in used and r['kind']=='Cartão de crédito' and r['amount']>0 and (r['category']==TRANSFER or 'pagamento' in normalize(r['bank_description'] or r['description']))]
        return [(dict(d),dict(c)) for d in debits for c in credits if d['amount']==-c['amount'] and abs((datetime.fromisoformat(d['date'])-datetime.fromisoformat(c['date'])).days)<=3]

    def reconcile(self, debit, credit, invoice_month=''):
        if invoice_month: validate_month(invoice_month)
        pair=next(((d,c) for d,c in self.payment_candidates() if d['id']==debit and c['id']==credit),None)
        if not pair: raise ValueError('Par inválido ou já conciliado. Atualize a lista.')
        d,c=pair
        if invoice_month and not any(r['account']==c['account'] and r['month']==invoice_month for r in self.invoices()):
            raise ValueError('Fatura de destino não encontrada.')
        with self.db:
            self.db.execute('INSERT INTO reconciliations(debit,credit,invoice_month,old_debit_category,old_credit_category) VALUES (?,?,?,?,?)',
                (debit,credit,invoice_month,d['category'],c['category']))
            self.db.execute('UPDATE transactions SET category=? WHERE id IN (?,?)',(TRANSFER,debit,credit))

    def unreconcile(self, ident):
        r=self.db.execute('SELECT * FROM reconciliations WHERE id=?',(ident,)).fetchone()
        if not r: return
        with self.db:
            self.db.execute('UPDATE transactions SET category=? WHERE id=?',(r['old_debit_category'],r['debit']))
            self.db.execute('UPDATE transactions SET category=? WHERE id=?',(r['old_credit_category'],r['credit']))
            self.db.execute('DELETE FROM reconciliations WHERE id=?',(ident,))

    def reconciled(self):
        return self.db.execute('''SELECT r.*,d.date,d.description,c.amount,a.name FROM reconciliations r
          JOIN transactions d ON d.id=r.debit JOIN transactions c ON c.id=r.credit JOIN accounts a ON a.id=c.account ORDER BY d.date DESC''').fetchall()

    def set_budget(self, month, category, amount):
        validate_month(month)
        if category not in self.categories() or category==TRANSFER or amount<0: raise ValueError('Categoria ou limite inválido.')
        with self.db: self.db.execute('INSERT OR REPLACE INTO budgets VALUES (?,?,?)',(month,category,amount))

    def delete_budget(self, month, category):
        with self.db: self.db.execute('DELETE FROM budgets WHERE month=? AND category=?',(month,category))

    def budget_report(self, month):
        """Limites por categoria com a mesma base líquida do orçamento doméstico."""
        validate_month(month)
        expenses = {r['category']: r['spent'] for r in self.planner.report(month)['assignments']}
        return [dict(category=r['category'],limit=r['amount'],spent=expenses.get(r['category'],0),remaining=r['amount']-expenses.get(r['category'],0))
                for r in self.db.execute('SELECT * FROM budgets WHERE month=? ORDER BY category',(month,))]

    def comparison(self, month, account=None, ownership=''):
        validate_month(month)
        data=[defaultdict(int),defaultdict(int)]
        for index,m in enumerate((month_shift(month,-1),month)):
            for r in self.transactions(m,account,ownership=ownership):
                for part in self.allocations(r):
                    if part['amount']<0 and part['category']!=TRANSFER: data[index][part['category']]-=part['amount']
        return [dict(category=c,previous=data[0][c],current=data[1][c],difference=data[1][c]-data[0][c]) for c in sorted(set(data[0])|set(data[1]))]

    def edit_transaction(self, ident, account, day, description, amount, category, invoice_month='', ownership='', holder='', card_number=''):
        """Edita os dados pessoais do lançamento, preservando a descrição bancária."""
        day=date(day)
        if invoice_month: validate_month(invoice_month)
        if ownership not in ('','Titular','Adicional'): raise ValueError('Titularidade inválida.')
        if not description.strip() or category not in self.categories(): raise ValueError('Descrição ou categoria inválida.')
        if not self.db.execute('SELECT 1 FROM accounts WHERE id=?',(account,)).fetchone(): raise ValueError('Conta inválida.')
        if invoice_month and self.db.execute('SELECT kind FROM accounts WHERE id=?',(account,)).fetchone()[0]!='Cartão de crédito':
            raise ValueError('Mês de fatura só se aplica a cartões.')
        with self.db:
            if ident:
                r=self.db.execute('SELECT * FROM transactions WHERE id=?',(ident,)).fetchone()
                if not r: raise ValueError('Lançamento não encontrado.')
                if self.db.execute('SELECT 1 FROM reconciliations WHERE debit=? OR credit=?',(ident,ident)).fetchone():
                    raise ValueError('Desfaça a conciliação antes de editar este lançamento.')
                if r['batch'] is not None and account!=r['account']: raise ValueError('A conta de um lançamento importado não pode ser alterada.')
                if self.splits(ident) and amount!=r['amount']:
                    raise ValueError('Remova a divisão antes de alterar o valor do lançamento.')
                self.db.execute('INSERT OR IGNORE INTO transaction_originals VALUES (?,?,?,?,?)',(ident,r['date'],r['bank_description'] or r['description'],r['amount'],r['invoice_month']))
                self.db.execute('UPDATE transactions SET account=?,date=?,description=?,amount=?,category=?,invoice_month=? WHERE id=?',
                    (account,day,description.strip(),amount,category,invoice_month,ident))
            else:
                self.db.execute("INSERT INTO transactions(account,date,description,amount,category,invoice_month,fitid) VALUES (?,?,?,?,?,?,'')",
                    (account,day,description.strip(),amount,category,invoice_month))

            target = ident or self.db.execute('SELECT last_insert_rowid()').fetchone()[0]
            self.db.execute('UPDATE transactions SET ownership=?,holder=?,card_number=? WHERE id=?',(ownership,holder,card_number,target))
            if ident:
                changes = {name: value for name, value in
                           (('description', description.strip()), ('category', category)) if r[name] != value}
                self.installment_links.record(target, changes)
        return target

    def categorize(self, ids, category, term=''):
        if category not in self.categories(): raise ValueError('Selecione uma categoria existente.')
        if any(self.db.execute('SELECT 1 FROM reconciliations WHERE debit=? OR credit=?',(ident,ident)).fetchone() for ident in ids) and category!=TRANSFER:
            raise ValueError('Desfaça a conciliação antes de trocar a categoria de um pagamento conciliado.')
        with self.db:
            super().categorize(ids,category,term)
            for ident in ids:
                self.installment_links.record(ident, {'category': category})

    def save_rule(self, old_term, term, category, apply=False):
        term=normalize(term)
        if not term or category not in self.categories(): raise ValueError('Informe o texto e a categoria da regra.')
        with self.db:
            if old_term and old_term!=term: self.db.execute('DELETE FROM rules WHERE term=?',(old_term,))
            self.db.execute('INSERT OR REPLACE INTO rules VALUES (?,?)',(term,category))
            if apply:
                for r in self.transactions():
                    if r['category']=='Sem categoria':
                        self.db.execute('UPDATE transactions SET category=? WHERE id=?',(self.category(r['bank_description'] or r['description']),r['id']))

    def delete_rule(self, term):
        with self.db: self.db.execute('DELETE FROM rules WHERE term=?',(term,))

    def undo(self):
        batch=self.db.execute('SELECT id FROM batches ORDER BY id DESC LIMIT 1').fetchone()
        if batch:
            for r in self.db.execute('''SELECT r.id FROM reconciliations r JOIN transactions d ON d.id=r.debit
                JOIN transactions c ON c.id=r.credit WHERE d.batch=? OR c.batch=?''',(batch['id'],batch['id'])).fetchall():
                self.unreconcile(r['id'])
        super().undo()

    def account_impact(self, account):
        row=self.db.execute('SELECT * FROM accounts WHERE id=?',(account,)).fetchone()
        if not row: raise ValueError('Selecione uma conta ou cartão.')
        return dict(name=row['name'], transactions=self.db.execute('SELECT count(*) FROM transactions WHERE account=?',(account,)).fetchone()[0], batches=self.db.execute('SELECT count(*) FROM batches WHERE account=?',(account,)).fetchone()[0], invoices=len(self.invoices(account)))

    def delete_account(self, account):
        self.account_impact(account)
        with self.db:
            pairs=self.db.execute('''SELECT r.* FROM reconciliations r JOIN transactions d ON d.id=r.debit JOIN transactions c ON c.id=r.credit WHERE d.account=? OR c.account=?''',(account,account)).fetchall()
            for r in pairs:
                self.db.execute('UPDATE transactions SET category=? WHERE id=?',(r['old_debit_category'],r['debit']))
                self.db.execute('UPDATE transactions SET category=? WHERE id=?',(r['old_credit_category'],r['credit']))
                self.db.execute('DELETE FROM reconciliations WHERE id=?',(r['id'],))
            self.db.execute('DELETE FROM monthly_closings WHERE account=?',(account,))
            for table in ('invoice_overrides','invoice_snapshots','transactions','batches'):
                self.db.execute(f'DELETE FROM {table} WHERE account=?',(account,))
            self.db.execute('DELETE FROM accounts WHERE id=?',(account,))
