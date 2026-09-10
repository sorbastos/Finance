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
        ''')

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
                self.db.execute('INSERT INTO transactions(account,batch,date,description,amount,fitid,category,invoice_month) VALUES (?,?,?,?,?,?,?,?)',
                    (account,batch,row['date'],row['description'],row['amount'],row['fitid'],row['category'],row.get('invoice_month','')))
                ident=self.db.execute('SELECT last_insert_rowid()').fetchone()[0]
                self.db.execute('UPDATE transactions SET ownership=?,holder=?,card_number=? WHERE id=?',
                    (row.get('ownership',''),row.get('holder',''),row.get('card_number',''),ident))
                count += 1
            for month, due, state, total in metadata:
                self.db.execute('INSERT INTO invoice_snapshots VALUES (?,?,?,?,?,?)', (batch,account,month,due,state,total))
            self.enrich_holders(account, rows)
            if not count and not metadata:
                raise ValueError('Nenhum lançamento novo para salvar.')
        return count

    def enrich_holders(self, account, rows):
        groups=defaultdict(list)
        for r in self.db.execute("""SELECT t.id,COALESCE(o.date,t.date) AS date,
          COALESCE(o.description,t.description) AS description,COALESCE(o.amount,t.amount) AS amount,
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
           COALESCE(o.description,t.description) AS description, COALESCE(o.amount,t.amount) AS amount,
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
        rows=super().transactions(month,account,search)
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
        # Use latest observed installment for each purchase; preserve equal-purchase multiplicity.
        series=defaultdict(lambda:defaultdict(list))
        for r in self.transactions(account=account):
            match=re.search(r'Parcela\s+(\d+)\s+de\s+(\d+)',r['description'],re.I)
            if not match or not r['invoice_month'] or r['kind']!='Cartão de crédito' or r['amount']>=0 or r['category']==TRANSFER: continue
            current,total=map(int,match.groups())
            if not 1<=current<=total<=600: continue
            base=re.sub(r'Parcela\s+\d+\s+de\s+\d+','',r['description'],flags=re.I)
            key=(r['account'],r['date'],normalize(base),total)
            series[key][r['invoice_month']].append((dict(r),current,total))
        result=[]
        for periods in series.values():
            latest=max(periods)
            for r,current,total in periods[latest]:
                for number in range(current+1,total+1):
                    result.append(dict(month=month_shift(latest,number-current),account=r['account'],name=r['name'],
                        description=re.sub(r'Parcela\s+\d+\s+de\s+\d+',f'Parcela {number} de {total}',r['description'],flags=re.I),
                        amount=-r['amount'],status='Previsto',source_month=latest))
        return sorted(result,key=lambda r:(r['month'],r['name'],r['description']))

    def payment_candidates(self):
        rows=self.transactions()
        used={r[0] for r in self.db.execute('SELECT debit FROM reconciliations UNION SELECT credit FROM reconciliations')}
        debits=[r for r in rows if r['id'] not in used and r['kind']=='Conta corrente' and r['amount']<0 and (r['category']==TRANSFER or 'fatura' in normalize(r['description']))]
        credits=[r for r in rows if r['id'] not in used and r['kind']=='Cartão de crédito' and r['amount']>0 and (r['category']==TRANSFER or 'pagamento' in normalize(r['description']))]
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
        if category not in CATEGORIES or category==TRANSFER or amount<0: raise ValueError('Categoria ou limite inválido.')
        with self.db: self.db.execute('INSERT OR REPLACE INTO budgets VALUES (?,?,?)',(month,category,amount))

    def delete_budget(self, month, category):
        with self.db: self.db.execute('DELETE FROM budgets WHERE month=? AND category=?',(month,category))

    def budget_report(self, month):
        validate_month(month)
        expenses=defaultdict(int)
        for r in self.transactions(month):
            if r['amount']<0 and r['category']!=TRANSFER: expenses[r['category']]-=r['amount']
        return [dict(category=r['category'],limit=r['amount'],spent=expenses[r['category']],remaining=r['amount']-expenses[r['category']])
                for r in self.db.execute('SELECT * FROM budgets WHERE month=? ORDER BY category',(month,))]

    def comparison(self, month, account=None, ownership=''):
        validate_month(month)
        data=[defaultdict(int),defaultdict(int)]
        for index,m in enumerate((month_shift(month,-1),month)):
            for r in self.transactions(m,account,ownership=ownership):
                if r['amount']<0 and r['category']!=TRANSFER: data[index][r['category']]-=r['amount']
        return [dict(category=c,previous=data[0][c],current=data[1][c],difference=data[1][c]-data[0][c]) for c in sorted(set(data[0])|set(data[1]))]

    def edit_transaction(self, ident, account, day, description, amount, category, invoice_month='', ownership='', holder='', card_number=''):
        day=date(day)
        if invoice_month: validate_month(invoice_month)
        if ownership not in ('','Titular','Adicional'): raise ValueError('Titularidade inválida.')
        if not description.strip() or category not in CATEGORIES: raise ValueError('Descrição ou categoria inválida.')
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
                self.db.execute('INSERT OR IGNORE INTO transaction_originals VALUES (?,?,?,?,?)',(ident,r['date'],r['description'],r['amount'],r['invoice_month']))
                self.db.execute('UPDATE transactions SET account=?,date=?,description=?,amount=?,category=?,invoice_month=? WHERE id=?',
                    (account,day,description.strip(),amount,category,invoice_month,ident))
            else:
                self.db.execute("INSERT INTO transactions(account,date,description,amount,category,invoice_month,fitid) VALUES (?,?,?,?,?,?,'')",
                    (account,day,description.strip(),amount,category,invoice_month))

            target = ident or self.db.execute('SELECT last_insert_rowid()').fetchone()[0]
            self.db.execute('UPDATE transactions SET ownership=?,holder=?,card_number=? WHERE id=?',(ownership,holder,card_number,target))

    def categorize(self, ids, category, term=''):
        if any(self.db.execute('SELECT 1 FROM reconciliations WHERE debit=? OR credit=?',(ident,ident)).fetchone() for ident in ids) and category!=TRANSFER:
            raise ValueError('Desfaça a conciliação antes de trocar a categoria de um pagamento conciliado.')
        super().categorize(ids,category,term)

    def save_rule(self, old_term, term, category, apply=False):
        term=normalize(term)
        if not term or category not in CATEGORIES: raise ValueError('Informe o texto e a categoria da regra.')
        with self.db:
            if old_term and old_term!=term: self.db.execute('DELETE FROM rules WHERE term=?',(old_term,))
            self.db.execute('INSERT OR REPLACE INTO rules VALUES (?,?)',(term,category))
            if apply:
                for r in self.transactions():
                    if r['category']=='Sem categoria':
                        self.db.execute('UPDATE transactions SET category=? WHERE id=?',(self.category(r['description']),r['id']))

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
            for table in ('invoice_overrides','invoice_snapshots','transactions','batches'):
                self.db.execute(f'DELETE FROM {table} WHERE account=?',(account,))
            self.db.execute('DELETE FROM accounts WHERE id=?',(account,))
