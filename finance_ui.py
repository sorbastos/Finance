"""Telas de planejamento e manutenção do aplicativo desktop."""
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from core import CATEGORIES, money
from finance import month_shift, validate_month


def currency(value):
    return 'R$ ' + f'{value/100:,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.')


class FinanceUI:
    def __init__(self, app, parent):
        self.app, self.store = app, app.store
        self.tabs = ttk.Notebook(parent)
        self.tabs.pack(fill='both', expand=True)
        self.tables={}
        self.notes={}
        definitions=[
            ('invoices','Faturas',['Cartão','Mês','Situação','Vencimento','Total informado','Lançamentos','Titular líquido','Adicional líquido','Sem identificação','Pago vinculado','Restante','Origem'], [('Editar / cadastrar',self.invoice_form),('Usar dados do extrato',self.reset_invoice)]),
            ('forecasts','Parcelas futuras',['Mês previsto','Cartão','Parcela','Valor previsto','Base importada'],[]),
            ('payments','Conciliação',['Data débito','Conta','Data crédito','Cartão','Valor','Situação','Fatura vinculada'],[('Conciliar sugestão',self.reconcile),('Desfazer vínculo',self.unreconcile)]),
            ('budgets','Orçamento',['Categoria','Limite','Gasto','Disponível','Uso'],[('Definir limite',self.budget_form),('Remover limite',self.remove_budget)]),
            ('comparison','Comparação',['Categoria','Mês anterior','Mês selecionado','Variação R$','Variação %'],[]),
            ('rules','Regras',['Texto na descrição','Categoria'],[('Nova regra',lambda:self.rule_form(False)),('Editar regra',lambda:self.rule_form(True)),('Excluir regra',self.delete_rule)])]
        for key,title,columns,buttons in definitions:
            frame=ttk.Frame(self.tabs,padding=10)
            self.tabs.add(frame,text=title)
            toolbar=ttk.Frame(frame)
            toolbar.pack(fill='x',pady=(0,8))
            for label,action in buttons:
                ttk.Button(toolbar,text=label,command=lambda fn=action:self.run(fn)).pack(side='left',padx=(0,8))
            note=ttk.Label(frame,text='',wraplength=820)
            note.pack(anchor='w',pady=(0,10))
            self.notes[key]=note
            table=app.table(frame,columns)
            table.master.pack(fill='both',expand=True)
            self.tables[key]=table
        self.invoice_rows={};self.payment_rows={};self.rule_rows={}

    def run(self, action):
        import sqlite3
        try: action()
        except (ValueError,sqlite3.Error) as exc:
            messagebox.showerror('Confira os dados',str(exc),parent=self.app)

    def month(self):
        return self.app.month_options.get(self.app.month.get(),'')

    def required_month(self):
        month=self.month()
        if not month: raise ValueError('Escolha um mês no filtro superior.')
        return month

    def form(self, title, fields, save):
        win=tk.Toplevel(self.app)
        win.title(title);win.transient(self.app);win.grab_set()
        widgets={}
        for index,(key,label,value,options) in enumerate(fields):
            ttk.Label(win,text=label,padding=8).grid(row=index,column=0,sticky='w')
            if options is not None:
                widget=ttk.Combobox(win,values=options,state='readonly',width=46)
                widget.set(value)
            else:
                widget=ttk.Entry(win,width=49);widget.insert(0,value)
            widget.grid(row=index,column=1,padx=10,pady=5,sticky='ew')
            widgets[key]=widget
        def submit():
            import sqlite3
            try:
                save({key:w.get().strip() for key,w in widgets.items()})
                win.destroy();self.app.refresh()
            except (ValueError,sqlite3.Error) as exc: messagebox.showerror('Confira os dados',str(exc),parent=win)
        ttk.Button(win,text='Salvar',command=submit).grid(row=len(fields),columnspan=2,pady=12)
        ttk.Button(win,text='Cancelar',command=win.destroy).grid(row=len(fields)+1,columnspan=2,pady=(0,12))
        return win

    def fill(self,key,rows):
        table=self.tables[key];table.delete(*table.get_children())
        for ident,values in rows: table.insert('','end',iid=str(ident),values=values)

    def refresh(self):
        month=self.month();account=self.app.accounts.get(self.app.account.get())
        self.invoice_rows={str(i):r for i,r in enumerate(self.store.invoices(account)) if not month or r['month']==month}
        self.fill('invoices',[(i,(r['name'],r['month'],r['state'],r['due'] or 'A informar',currency(r['total']) if r['total'] is not None else 'Não informado',currency(r['calculated']),currency(r['titular']),currency(r['adicional']),currency(r['unknown']),currency(r['paid']),currency(r['remaining']),r['source'])) for i,r in self.invoice_rows.items()])
        self.notes['invoices'].config(text='Faturas do mês e conta selecionados, somando titular e adicional para um único pagamento. Restante = total informado (ou lançamentos) menos pagamentos vinculados. Fatura aberta tem valor parcial; pagamento exibido em um XLSX pode pertencer à fatura anterior.')
        forecasts=self.store.forecasts(account)
        start=month or datetime.now().strftime('%Y-%m')
        end=month_shift(start,12)
        forecasts=[r for r in forecasts if start<=r['month']<end]
        self.fill('forecasts',[(i,(r['month'],r['name'],r['description'],currency(r['amount']),r['source_month'])) for i,r in enumerate(forecasts)])
        self.notes['forecasts'].config(text=f'Previsões para 12 meses a partir de {start}: {currency(sum(r["amount"] for r in forecasts))}. Base: última parcela importada de cada compra; valores estimados constantes. Não entram nos gastos reais. A busca por descrição não se aplica às telas de planejamento.')
        self.payment_rows={}
        display=[]
        for i,(d,c) in enumerate(self.store.payment_candidates()):
            ident=f'p{i}'; self.payment_rows[ident]=('candidate',d,c)
            display.append((ident,(d['date'],d['name'],c['date'],c['name'],currency(c['amount']),'Sugestão — revisar','A escolher')))
        for r in self.store.reconciled():
            ident=f'r{r["id"]}';self.payment_rows[ident]=('done',dict(r))
            display.append((ident,(r['date'],r['description'],'',r['name'],currency(r['amount']),'Conciliado',r['invoice_month'] or 'Sem vínculo de fatura')))
        self.fill('payments',display)
        self.notes['payments'].config(text='Todas as contas e períodos. Sugestões: pagamentos identificados com mesmo valor, sinais opostos e até 3 dias de diferença. Revise o cartão e escolha a fatura paga; um pagamento só pode ser vinculado uma vez.')
        budgets=self.store.budget_report(month) if month else []
        self.fill('budgets',[(r['category'],(r['category'],currency(r['limit']),currency(r['spent']),currency(r['remaining']),f'{r["spent"]/r["limit"]*100:.1f}%' if r['limit'] else ('Acima do limite' if r['spent'] else '0%'))) for r in budgets])
        self.notes['budgets'].config(text=f'Orçamento de {month}: todas as contas, sem filtro de busca. Valores negativos em Disponível indicam limite excedido.' if month else 'Escolha um mês no filtro superior para definir limites e acompanhar os gastos.')
        comparison=self.store.comparison(month,account,'' if self.app.ownership.get()=='Todos os titulares' else self.app.ownership.get()) if month else []
        self.fill('comparison',[(r['category'],(r['category'],currency(r['previous']),currency(r['current']),currency(r['difference']),f'{r["difference"]/r["previous"]*100:+.1f}%' if r['previous'] else 'Sem base anterior')) for r in comparison])
        self.notes['comparison'].config(text=f'{month_shift(month,-1)} → {month}. Conta e titularidade selecionadas; sem filtro de busca. Apenas despesas. Ausência de extrato não comprova gasto zero.' if month else 'Escolha um mês para comparar com o mês calendário anterior.')
        rules=self.store.db.execute('SELECT * FROM rules ORDER BY length(term) DESC,term').fetchall()
        self.rule_rows={str(i):dict(r) for i,r in enumerate(rules)}
        self.fill('rules',[(i,(r['term'],r['category'])) for i,r in self.rule_rows.items()])
        self.notes['rules'].config(text='Regras globais para próximas importações. O texto mais específico tem prioridade. Aplicar ao histórico altera somente lançamentos sem categoria.')

    def selected(self,key):
        selected=self.tables[key].selection()
        if len(selected)!=1: raise ValueError('Selecione uma única linha.')
        return selected[0]

    def invoice_form(self):
        selection=self.tables['invoices'].selection()
        r=self.invoice_rows[selection[0]] if len(selection)==1 else {}
        cards={a['name']:a['id'] for a in self.store.accounts() if a['kind']=='Cartão de crédito'}
        if not cards: raise ValueError('Cadastre um cartão primeiro.')
        def save(v):
            self.store.set_invoice(cards[v['account']],v['month'],v['due'],v['state'],money(v['total']) if v['total'] else None)
        return self.form('Fatura — dados informados substituem o extrato',[
            ('account','Cartão',r.get('name',next(iter(cards))),list(cards)),
            ('month','Mês da fatura (AAAA-MM)',r.get('month',self.month() or datetime.now().strftime('%Y-%m')),None),
            ('due','Vencimento (DD/MM/AAAA)',r.get('due',''),None),
            ('state','Situação',r.get('state','Aberta'),['Aberta','Fechada','A conferir']),
            ('total','Total informado (vazio = lançamentos)',str(r['total']/100) if r.get('total') is not None else '',None)],save)

    def reset_invoice(self):
        r=self.invoice_rows[self.selected('invoices')]
        with self.store.db: self.store.db.execute('DELETE FROM invoice_overrides WHERE account=? AND month=?',(r['account'],r['month']))
        self.app.refresh()

    def reconcile(self):
        record=self.payment_rows[self.selected('payments')]
        if record[0]!='candidate': raise ValueError('Selecione uma sugestão ainda não conciliada.')
        _,d,c=record
        options=['Sem vínculo de fatura']+[r['month'] for r in self.store.invoices(c['account'])]
        self.form('Vincular pagamento após conferir os extratos',[
            ('month',f'{currency(c["amount"])} — fatura paga',options[0],options)],
            lambda v:self.store.reconcile(d['id'],c['id'],'' if v['month']==options[0] else v['month']))

    def unreconcile(self):
        record=self.payment_rows[self.selected('payments')]
        if record[0]!='done': raise ValueError('Selecione um pagamento conciliado.')
        self.store.unreconcile(record[1]['id']);self.app.refresh()

    def budget_form(self):
        month=self.required_month()
        selection=self.tables['budgets'].selection()
        category=selection[0] if len(selection)==1 else 'Alimentação'
        row=next((r for r in self.store.budget_report(month) if r['category']==category),None)
        self.form(f'Orçamento de {month} — todas as contas',[
            ('category','Categoria',category,CATEGORIES[:-1]),('amount','Limite em reais',str(row['limit']/100) if row else '',None)],
            lambda v:self.store.set_budget(month,v['category'],money(v['amount'])))

    def remove_budget(self):
        self.store.delete_budget(self.required_month(),self.selected('budgets'));self.app.refresh()

    def rule_form(self, editing):
        r=self.rule_rows[self.selected('rules')] if editing else {}
        self.form('Regra de categorização',[
            ('term','Texto contido na descrição',r.get('term',''),None),
            ('category','Categoria',r.get('category','Alimentação'),CATEGORIES),
            ('apply','Aplicar também aos sem categoria?','Não',['Não','Sim'])],
            lambda v:self.store.save_rule(r.get('term',''),v['term'],v['category'],v['apply']=='Sim'))

    def delete_rule(self):
        self.store.delete_rule(self.rule_rows[self.selected('rules')]['term']);self.app.refresh()

    def transaction_form(self, editing=False):
        r={}
        if editing:
            selected=self.app.tree.selection()
            if len(selected)!=1: raise ValueError('Selecione um lançamento na aba Transações.')
            r=dict(self.store.db.execute('SELECT * FROM transactions WHERE id=?',(selected[0],)).fetchone())
        accounts={a['name']:a['id'] for a in self.store.accounts()}
        if not accounts: raise ValueError('Cadastre uma conta primeiro.')
        current=next((name for name,ident in accounts.items() if ident==r.get('account')),next(iter(accounts)))
        def save(v):
            self.store.edit_transaction(r.get('id'),accounts[v['account']],v['date'],v['description'],money(v['amount']),v['category'],v['month'],v['ownership'] if v['ownership']!='Não informado' else '',v['holder'],v['card'])
        return self.form('Editar lançamento' if editing else 'Novo lançamento manual',[
            ('account','Conta (importados: manter origem)',current,list(accounts)),
            ('date','Data (DD/MM/AAAA)',r.get('date',datetime.now().strftime('%d/%m/%Y')),None),
            ('description','Descrição',r.get('description',''),None),
            ('amount','Valor: negativo = despesa',str(r['amount']/100) if r else '',None),
            ('category','Categoria',r.get('category','Sem categoria'),CATEGORIES),
            ('month','Mês de fatura do cartão (opcional)',r.get('invoice_month',''),None),
            ('ownership','Titularidade',r.get('ownership') or 'Não informado',['Não informado','Titular','Adicional']),
            ('holder','Nome do portador',r.get('holder',''),None),
            ('card','Final do cartão (opcional)',r.get('card_number',''),None)],save)
