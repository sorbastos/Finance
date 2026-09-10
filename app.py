#!/usr/bin/env python3
"""Janela local para gestão de despesas."""
import os
import csv
from theme import apply_theme
from rounded import RoundedPanel
from charts import draw as draw_chart
from collections import defaultdict
from pathlib import Path
import sqlite3
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from xlsx_itau import parse_xlsx
from finance import FinanceStore as Store
from finance_ui import FinanceUI
from core import CATEGORIES, csv_table, parse_csv, parse_ofx, normalize


def brl(cents):
    return 'R$ ' + f'{cents / 100:,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.')


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Minhas despesas • Local')
        self.geometry('1280x850')
        self.minsize(1080, 720)
        data = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'minhas-despesas'
        first_start = not (data / 'despesas.sqlite3').exists()
        self.store = Store(data / 'despesas.sqlite3')
        self.store.db.execute('CREATE TABLE IF NOT EXISTS preferences(key TEXT PRIMARY KEY,value TEXT)')
        self.store.db.commit()
        preference=self.store.db.execute("SELECT value FROM preferences WHERE key='dark_mode'").fetchone()
        self.dark_mode=tk.BooleanVar(value=bool(preference and preference[0]=='1'))
        if first_start:
            self.store.add_account('Itaú • conta corrente', 'Conta corrente')
            self.store.add_account('Itaú • cartão', 'Cartão de crédito')
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', font=('DejaVu Sans', 10))
        style.configure('Treeview', rowheight=30)
        style.configure('Title.TLabel', font=('DejaVu Sans', 23, 'bold'))
        style.configure('Import.TButton', font=('DejaVu Sans', 13, 'bold'), padding=(20, 12))
        self.configure(background='#f2f6fc')
        style.configure('TFrame', background='#f2f6fc')
        style.configure('TLabel', background='#f2f6fc', foreground='#25364c')
        style.configure('TButton', padding=(10, 7))
        style.configure('TNotebook.Tab', padding=(22, 10))
        style.configure('Treeview', background='white', fieldbackground='white', borderwidth=0)
        style.configure('Treeview.Heading', background='#eaf0f8', padding=8)
        style.configure('TButton', background='#eaf0f8', foreground='#258bd2', borderwidth=0, padding=(12,8))
        style.map('TButton', background=[('active','#dceafa')])
        style.configure('Import.TButton', background='#258bd2', foreground='white', font=('DejaVu Sans',10,'bold'),padding=(18,10))
        style.map('Import.TButton',background=[('active','#1477bb')],foreground=[('active','white')])
        style.configure('TNotebook',borderwidth=0,background='#f2f6fc')
        style.configure('TNotebook.Tab',background='#f2f6fc',borderwidth=0,padding=(18,10))
        style.map('TNotebook.Tab',background=[('selected','white')],foreground=[('selected','#258bd2')])
        style.configure('Main.TNotebook',borderwidth=0,tabmargins=0)
        style.layout('Main.TNotebook.Tab', [])
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self.content = ttk.Frame(self)
        self.content.grid(row=0,column=1,sticky='nsew')
        self.content.columnconfigure(0,weight=1)
        self.content.rowconfigure(3,weight=1)
        self.sidebar_view = tk.Canvas(self, bg='white', width=220, highlightthickness=0, borderwidth=0)
        self.sidebar_view.grid(row=0,column=0,sticky='nsew')
        self.sidebar = tk.Frame(self.sidebar_view,bg='white')
        sidebar_window = self.sidebar_view.create_window(0,0,window=self.sidebar,anchor='nw')
        def resize_sidebar(event=None):
            # Preserve enough room for labels at any display scale.
            natural = max(220, self.sidebar.winfo_reqwidth())
            width = max(natural, min(280, int(self.winfo_width() * .15)))
            if int(self.sidebar_view.cget('width')) != width:
                self.sidebar_view.configure(width=width)
            self.sidebar_view.itemconfigure(sidebar_window,width=self.sidebar_view.winfo_width())
            self.sidebar_view.configure(scrollregion=self.sidebar_view.bbox('all'))
        self.sidebar_view.bind('<Configure>', resize_sidebar)
        self.sidebar.bind('<Configure>', resize_sidebar)
        self.bind('<Configure>', lambda e: resize_sidebar() if e.widget is self else None, add='+')
        def scroll_sidebar(event):
            if self.sidebar.winfo_height() > self.sidebar_view.winfo_height():
                direction = -1 if event.num == 4 or getattr(event,'delta',0) > 0 else 1
                self.sidebar_view.yview_scroll(direction, 'units')
            return 'break'
        def reveal_sidebar_item(event):
            height = max(1,self.sidebar.winfo_height())
            top = event.widget.winfo_y()
            first,last = self.sidebar_view.yview()
            if top < first*height:
                self.sidebar_view.yview_moveto(top/height)
            elif top+event.widget.winfo_height() > last*height:
                self.sidebar_view.yview_moveto((top+event.widget.winfo_height()-self.sidebar_view.winfo_height())/height)
        tk.Label(self.sidebar,text='Finance',bg='white',fg='#258bd2',font=('DejaVu Sans',19,'bold'),pady=20).pack(anchor='w',padx=18)
        tk.Checkbutton(self.sidebar,text='Modo escuro',variable=self.dark_mode,command=self.toggle_theme,bg='white',fg='#52647b',relief='flat',highlightthickness=0).pack(anchor='w',padx=15,pady=(0,10))
        self.nav_buttons = {}
        for name in ['Visão geral','Contas','Cartões','Transações','Faturas','Parcelas futuras','Conciliação','Orçamentos','Comparação','Regras']:
            button = tk.Button(self.sidebar,text=name,anchor='w',bg='white',fg='#52647b',activebackground='#eaf3ff',
                activeforeground='#258bd2',relief='flat',borderwidth=0,highlightthickness=0,padx=18,pady=8,
                font=('DejaVu Sans',10),command=lambda label=name:self.navigate(label))
            button.pack(fill='x',padx=8,pady=1)
            self.nav_buttons[name]=button
        tk.Frame(self.sidebar,bg='white',height=16).pack(fill='x')
        for title,command in [('Nova conta / cartão',self.new_account),('Excluir conta / cartão',self.delete_account),
                              ('Desfazer importação',self.undo),('Backup manual',self.backup)]:
            tk.Button(self.sidebar,text=title,anchor='w',command=command,bg='white',fg='#7c8797',activebackground='#eef4fc',
                relief='flat',borderwidth=0,highlightthickness=0,padx=16,pady=6,font=('DejaVu Sans',9)).pack(fill='x',padx=8)

        for widget in (self.sidebar_view,self.sidebar,*self.sidebar.winfo_children()):
            for sequence in ('<Button-4>','<Button-5>','<MouseWheel>'):
                widget.bind(sequence,scroll_sidebar)
            widget.bind('<FocusIn>',reveal_sidebar_item)

        header = ttk.Frame(self.content, padding=20)
        header.grid(sticky='ew')
        heading = ttk.Frame(header)
        heading.pack(fill='x')
        self.page_title = ttk.Label(heading, text='Visão geral', style='Title.TLabel')
        self.page_title.pack(side='left')
        self.import_button = ttk.Button(heading, text='Importar extratos', style='Import.TButton', command=self.import_file)
        self.import_button.pack(side='right')
        self.import_status = ttk.Label(header, text='Visão mensal · Dados locais · OFX, CSV e XLSX')
        self.import_status.pack(anchor='w',pady=(8,0))
        ttk.Frame(self.content).grid(row=1,column=0)
        filter_container = ttk.Frame(self.content, padding=(20, 10))
        filter_container.grid(sticky='ew')
        filters = ttk.Frame(filter_container)
        filters.pack(fill='x')
        self.dashboard_mode = ttk.Combobox(filters, values=['Conta corrente', 'Cartão de crédito'], state='readonly', width=16)
        self.dashboard_mode.set('Conta corrente')
        self.dashboard_mode.pack(side='left', padx=(0,8))
        self.dashboard_mode.bind('<<ComboboxSelected>>', self.change_dashboard)
        ttk.Label(filters, text='Conta:').pack(side='left')
        self.account = ttk.Combobox(filters, state='readonly', width=20)
        self.account.pack(side='left', padx=6)
        self.account.bind('<<ComboboxSelected>>', lambda e: self.refresh())
        ttk.Label(filters, text='Mês:').pack(side='left', padx=6)
        self.previous_month = ttk.Button(filters, text='‹', width=3, command=lambda: self.move_month(1))
        self.previous_month.pack(side='left')
        self.month = ttk.Combobox(filters, state='readonly', width=18)
        self.month.pack(side='left', padx=4)
        self.next_month = ttk.Button(filters, text='›', width=3, command=lambda: self.move_month(-1))
        self.next_month.pack(side='left')
        self.month.bind('<<ComboboxSelected>>', lambda e: self.refresh())
        filters = ttk.Frame(filter_container)
        filters.pack(fill='x', pady=(8,0))
        ttk.Label(filters,text='Gastos de:').pack(side='left')
        self.ownership = ttk.Combobox(filters, values=['Todos os titulares', 'Titular', 'Adicional'], state='readonly', width=18)
        self.ownership.set('Todos os titulares')
        self.ownership.pack(side='left', padx=6)
        self.ownership.bind('<<ComboboxSelected>>', lambda e: self.refresh())
        self.search = ttk.Entry(filters, width=14)
        self.search.pack(side='left', padx=6)
        ttk.Button(filters, text='Buscar descrição', command=self.refresh).pack(side='left')
        self.search.bind('<Return>', lambda e: self.refresh())
        self.pages = ttk.Notebook(self.content, style='Main.TNotebook')
        self.pages.grid(row=3, column=0, sticky='nsew', padx=20)
        overview_page = ttk.Frame(self.pages)
        dashboard_scroll = ttk.Scrollbar(overview_page, orient='vertical')
        dashboard_scroll.pack(side='right',fill='y')
        viewport = tk.Canvas(overview_page,bg='#f2f6fc',highlightthickness=0,yscrollcommand=dashboard_scroll.set)
        viewport.pack(side='left',fill='both',expand=True)
        dashboard_scroll.configure(command=viewport.yview)
        overview = ttk.Frame(viewport, padding=14)
        dashboard_window = viewport.create_window((0,0),window=overview,anchor='nw')
        viewport.bind('<Configure>',lambda e:viewport.itemconfigure(dashboard_window,width=e.width))
        overview.bind('<Configure>',lambda e:viewport.configure(scrollregion=viewport.bbox('all')))
        viewport.bind('<Button-4>',lambda e:viewport.yview_scroll(-1,'units'))
        viewport.bind('<Button-5>',lambda e:viewport.yview_scroll(1,'units'))
        transactions = ttk.Frame(self.pages, padding=12)
        self.pages.add(overview_page, text='Visão geral')
        self.pages.add(transactions, text='Transações')
        overview.columnconfigure(0, weight=1)
        overview.rowconfigure(2, weight=1, minsize=270)
        cards = ttk.Frame(overview)
        cards.grid(sticky='ew', pady=(0, 14))
        self.metrics = {}
        self.metric_titles = {}
        for index, (key, title, color) in enumerate([
                ('income', 'ENTRADAS / CRÉDITOS', '#137b65'), ('expenses', 'DESPESAS', '#c4445e'),
                ('net', 'RESULTADO DO PERÍODO', '#315fc4'), ('pending', 'PARA CATEGORIZAR', '#a76b17')]):
            cards.columnconfigure(index, weight=1, uniform='cards')
            card = RoundedPanel(cards)
            card.grid(row=0, column=index, sticky='nsew', padx=(0, 10) if index < 3 else 0)
            label = tk.Label(card.body, text=title, font=('DejaVu Sans', 8), fg='#78879a', bg='white')
            label.pack(anchor='w')
            label.configure(wraplength=190)
            self.metric_titles[key] = label
            value = tk.Label(card.body, text='—', font=('DejaVu Sans', 19, 'bold'), fg=color, bg='white')
            value.pack(anchor='w', pady=(8, 0))
            self.metrics[key] = value
        self.dashboard_caption = ttk.Label(overview, text='', font=('DejaVu Sans', 11))
        self.dashboard_caption.grid(sticky='w', pady=(0, 12))
        chart_controls = ttk.Frame(overview)
        chart_controls.grid(row=3,column=0,sticky='w',pady=(12,0))
        ttk.Label(chart_controls,text='Visualização').pack(side='left',padx=(0,10))
        self.chart_mode = tk.StringVar(value='Barras')
        for mode in ('Barras','Rosca','Evolução'):
            ttk.Radiobutton(chart_controls,text=mode,variable=self.chart_mode,value=mode,command=self.draw_dashboard).pack(side='left',padx=8)
        self.timeline_data = ({},{})
        plots = ttk.Frame(overview)
        plots.grid(row=2,column=0,sticky='nsew')
        plots.columnconfigure(0, weight=1, uniform='plots')
        plots.columnconfigure(1, weight=1, uniform='plots')
        plots.rowconfigure(0, weight=1)
        self.category_plot = tk.Canvas(plots, bg='#f2f6fc', highlightthickness=0, height=270)
        self.account_plot = tk.Canvas(plots, bg='#f2f6fc', highlightthickness=0, height=270)
        self.category_plot.grid(row=0, column=0, sticky='nsew', padx=(0, 12))
        self.account_plot.grid(row=0, column=1, sticky='nsew')
        self.chart_data = ({}, {})
        for canvas in (self.category_plot, self.account_plot):
            canvas.bind('<Configure>', lambda e: self.draw_dashboard())
        ttk.Button(overview, text='Ver e categorizar transações →', command=lambda: self.pages.select(1)).grid(sticky='e', pady=(12, 0))
        actions = ttk.Frame(transactions)
        actions.pack(fill='x', pady=(0,8))
        ttk.Button(actions,text='Novo lançamento',command=lambda:self.finance.run(lambda:self.finance.transaction_form(False))).pack(side='left',padx=4)
        ttk.Button(actions,text='Editar lançamento',command=lambda:self.finance.run(lambda:self.finance.transaction_form(True))).pack(side='left',padx=4)
        self.tree = self.table(transactions, ['Data', 'Fatura', 'Conta', 'Titularidade', 'Nome', 'Descrição', 'Valor', 'Categoria'])
        self.tree.master.pack(fill='both', expand=True)
        ttk.Button(actions,text='Categorizar seleção',command=self.categorize).pack(side='left',padx=4)
        account_panel = ttk.Frame(overview,padding=(0,12))
        account_panel.grid(row=5,column=0,sticky='ew')
        ttk.Label(account_panel,text='Resumo por conta',font=('DejaVu Sans',12,'bold')).pack(anchor='w',pady=(0,10))
        self.account_summary = self.table(account_panel,['Conta / cartão','Entradas / créditos','Saídas / compras','Movimento líquido'])
        self.account_summary.configure(height=4)
        self.account_summary.master.pack(fill='x')
        self.summary = ttk.Label(self.content, padding=(20, 8), font=('DejaVu Sans', 10))
        self.summary.grid(sticky='ew')
        self.dashboard_note = ttk.Label(self.content, text='', padding=(20,0), wraplength=950)
        self.dashboard_note.grid(sticky='w')
        ttk.Label(self.content, text='Período: mês da fatura para XLSX; data do lançamento para OFX/CSV.', padding=(20, 2)).grid(sticky='w')
        ttk.Label(self.content, text=f'Banco local: {self.store.path}', padding=(20, 6)).grid(sticky='w')
        planning = ttk.Frame(self.pages, padding=4)
        self.pages.add(planning, text='Planejamento e faturas')
        self.finance = FinanceUI(self, planning)
        self.finance.tabs.configure(style='Main.TNotebook')
        self.pages.bind('<<NotebookTabChanged>>',lambda e:self.update_navigation())
        self.finance.tabs.bind('<<NotebookTabChanged>>',lambda e:self.update_navigation())
        self.load_accounts()
        self.refresh()
        self.protocol('WM_DELETE_WINDOW', self.close)
        apply_theme(self)
        self.refresh()
        self.bind_all('<Map>',self.theme_new_window,add='+')

    def navigate(self, name):
        if name in ('Contas','Cartões'):
            self.dashboard_mode.set('Conta corrente' if name=='Contas' else 'Cartão de crédito')
            self.change_dashboard()
            self.pages.select(0)
        elif name=='Visão geral': self.pages.select(0)
        elif name=='Transações': self.pages.select(1)
        else:
            section={'Faturas':0,'Parcelas futuras':1,'Conciliação':2,'Orçamentos':3,'Comparação':4,'Regras':5}[name]
            self.pages.select(2)
            self.finance.tabs.select(section)
        self.update_navigation()

    def update_navigation(self):
        if not hasattr(self,'finance'): return
        page=self.pages.index(self.pages.select())
        if page==0: name='Cartões' if self.dashboard_mode.get()=='Cartão de crédito' else 'Contas'
        elif page==1: name='Transações'
        else: name=['Faturas','Parcelas futuras','Conciliação','Orçamentos','Comparação','Regras'][self.finance.tabs.index(self.finance.tabs.select())]
        for label,button in self.nav_buttons.items():
            active=label==name
            button.configure(bg=('#243f5d' if active else '#1e293b') if self.dark_mode.get() else ('#eaf3ff' if active else 'white'),fg=('#7cc4ff' if active else '#cbd5e1') if self.dark_mode.get() else ('#258bd2' if active else '#52647b'))
        self.page_title.configure(text=('Visão geral · '+name.lower()) if page==0 else name)

    def toggle_theme(self):
        with self.store.db:
            self.store.db.execute("INSERT OR REPLACE INTO preferences VALUES ('dark_mode',?)",('1' if self.dark_mode.get() else '0',))
        apply_theme(self)
        self.refresh()

    def theme_new_window(self,event):
        if isinstance(event.widget,tk.Toplevel):
            self.after_idle(lambda:apply_theme(self) if self.winfo_exists() else None)

    def close(self):
        self.store.db.close()
        self.destroy()

    def table(self, parent, columns):
        frame = ttk.Frame(parent)
        tree = ttk.Treeview(frame, columns=columns, show='headings', selectmode='extended')
        for column in columns:
            tree.heading(column, text=column)
            tree.column(column, width=260 if column in ('Descrição', 'Categoria') else 125, minwidth=85)
        scroll = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        horizontal = ttk.Scrollbar(frame, orient='horizontal', command=tree.xview)
        tree.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        tree.grid(row=0, column=0, sticky='nsew')
        scroll.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        tree.tag_configure('negative', foreground='#aa293d')
        return tree

    def load_accounts(self):
        self.accounts = {f"{r['name']} ({r['kind']})": r['id'] for r in self.store.accounts()}
        self.account['values'] = ['Todas'] + list(self.accounts)
        if self.account.get() not in self.account['values']:
            self.account.set('Todas')

    def load_months(self):
        names = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
                 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
        selected = self.accounts.get(self.account.get())
        months = sorted({r['invoice_month'] or r['date'][:7] for r in self.store.transactions(account=selected) if r['kind']==self.dashboard_mode.get()}, reverse=True)
        if self.dashboard_mode.get()=='Cartão de crédito':
            months = sorted(set(months)|{r['month'] for r in self.store.invoices(selected)}, reverse=True)
        self.month_options = {'Todos os meses': ''}
        self.month_options.update({f'{names[int(m[5:7])-1]} de {m[:4]}': m for m in months})
        labels = list(self.month_options)
        selected = self.month.get()
        self.month['values'] = labels
        if selected not in self.month_options:
            self.month.set(labels[1] if months else labels[0])
        index = labels.index(self.month.get())
        self.previous_month.state(['!disabled'] if (index == 0 and months) or 0 < index < len(labels)-1 else ['disabled'])
        self.next_month.state(['!disabled'] if index > 1 else ['disabled'])

    def move_month(self, step):
        labels = list(self.month_options)
        index = labels.index(self.month.get())
        target = 1 if index == 0 else index + step
        if 1 <= target < len(labels):
            self.month.set(labels[target])
            self.refresh()

    def change_dashboard(self, event=None):
        self.account.set('Todas')
        self.month.set('')
        self.ownership.set('Todos os titulares')
        self.refresh()

    def refresh(self):
        account_id = self.accounts.get(self.account.get())
        if account_id is not None:
            self.dashboard_mode.set(next(a['kind'] for a in self.store.accounts() if a['id']==account_id))
        is_card = self.dashboard_mode.get()=='Cartão de crédito'
        if not is_card: self.ownership.set('Todos os titulares')
        self.ownership.configure(state='readonly' if is_card else 'disabled')
        self.pages.tab(0, text='Dashboard do cartão' if is_card else 'Dashboard da conta')
        self.load_months()
        rows = self.store.transactions(self.month_options[self.month.get()], self.accounts.get(self.account.get()), self.search.get(), '' if self.ownership.get()=='Todos os titulares' else self.ownership.get())
        rows = [r for r in rows if r['kind']==self.dashboard_mode.get()]
        self.tree.delete(*self.tree.get_children())
        for r in rows:
            self.tree.insert('', 'end', iid=str(r['id']), values=(r['date'], r['invoice_month'], r['name'], r['ownership'] or 'Não informado', r['holder'], r['description'], brl(r['amount']), r['category']), tags=('negative',) if r['amount'] < 0 else ())
        relevant = [r for r in rows if r['category'] != CATEGORIES[-1]] if is_card else rows
        income = sum(r['amount'] for r in relevant if r['amount'] > 0)
        expenses = -sum(r['amount'] for r in relevant if r['amount'] < 0)
        pending = sum(r['category'] == 'Sem categoria' for r in rows)
        if is_card:
            invoices = [r for r in self.store.invoices(account_id) if not self.month_options[self.month.get()] or r['month']==self.month_options[self.month.get()]]
            bill_total = sum(r['total'] if r['total'] is not None else r['calculated'] for r in invoices)
            titles = ['COMPRAS DO FILTRO', 'ESTORNOS / CRÉDITOS', 'FATURAS CONSOLIDADAS', 'RESTANTE DAS FATURAS']
            values = [brl(expenses), brl(income), brl(bill_total), brl(sum(r['remaining'] for r in invoices))]
            due = ', '.join(sorted({r['due'] for r in invoices if r['due']})) or 'a informar'
            note = f'Faturas somam titular e adicional, sem filtro de busca; abertas têm valor parcial. Restante depende dos pagamentos vinculados. Vencimento(s): {due}.'
        else:
            titles = ['ENTRADAS NA CONTA', 'SAÍDAS DA CONTA', 'MOVIMENTAÇÃO LÍQUIDA', 'PARA CATEGORIZAR']
            values = [brl(income), brl(expenses), brl(income-expenses), str(pending)]
            note = 'Fluxo da conta: inclui transferências e pagamentos de fatura. Movimentação líquida é entradas menos saídas; não inclui saldo inicial e não representa saldo bancário.'
        for key,title,value in zip(['income','expenses','net','pending'],titles,values):
            self.metric_titles[key].config(text=title)
            color = ('#e75b51' if key=='income' else '#16a46b') if is_card and key in ('income','expenses') else {'income':'#16a46b','expenses':'#e75b51','net':'#258bd2','pending':'#8261ca'}[key]
            if self.dark_mode.get(): color={'#e75b51':'#fb8b99','#16a46b':'#4adea0','#258bd2':'#7cc4ff','#8261ca':'#bba1f5'}.get(color,color)
            self.metrics[key].config(text=value,fg=color)
        self.dashboard_note.config(text=note)
        self.chart_titles = ('Compras por categoria','Compras por titularidade') if is_card else ('Saídas por categoria','Saídas por dia')
        categories, accounts = defaultdict(int), defaultdict(int)
        for row in relevant:
            if row['amount'] < 0:
                categories[row['category']] -= row['amount']
                accounts[(row['ownership'] or 'Não informado') if is_card else row['date']] -= row['amount']
        self.account_summary.delete(*self.account_summary.get_children())
        grouped = {}
        for row in relevant:
            amounts=grouped.setdefault(row['name'],[0,0])
            if row['amount']>0: amounts[0]+=row['amount']
            else: amounts[1]-=row['amount']
        for name,(credits,debits) in sorted(grouped.items()):
            self.account_summary.insert('','end',values=(name,brl(credits),brl(debits),brl(credits-debits)))
        self.chart_data = (categories, accounts)
        outgoing,incoming=defaultdict(int),defaultdict(int)
        for row in relevant:
            if row['amount']<0: outgoing[row['date']]-=row['amount']
            elif row['amount']>0: incoming[row['date']]+=row['amount']
        self.timeline_data=(outgoing,incoming)
        context = f'{self.month.get()} • {self.account.get()} • {self.ownership.get()} • {len(rows)} lançamentos'
        if self.search.get():
            context += f' • Busca: {self.search.get()}'
        self.dashboard_caption.config(text=context)
        self.summary.config(text=f'{len(rows)} lançamentos • {pending} para categorizar')
        self.draw_dashboard()
        self.finance.refresh()
        self.update_navigation()

    def draw_dashboard(self):
        mode=self.chart_mode.get()
        if mode=='Evolução':
            data=self.timeline_data
            titles=('Compras por data original','Créditos por data original') if self.dashboard_mode.get()=='Cartão de crédito' else ('Saídas por data','Entradas por data')
        else:
            data=self.chart_data
            titles=getattr(self,'chart_titles',('Saídas por categoria','Saídas por dia'))
        for canvas,values,title in zip((self.category_plot,self.account_plot),data,titles):
            draw_chart(canvas,values,title,mode)

    def delete_account(self):
        account = self.accounts.get(self.account.get())
        if account is None:
            messagebox.showinfo('Selecione uma conta', 'Escolha no filtro a conta ou cartão que deseja excluir.')
            return
        impact = self.store.account_impact(account)
        warning = (f"Excluir {impact['name']}?\n\n"
                   f"Serão removidos {impact['transactions']} lançamentos, {impact['batches']} importações e {impact['invoices']} faturas desta conta/cartão.\n"
                   'Os vínculos de pagamento serão desfeitos. Outras contas, regras e orçamentos permanecerão.\n\n'
                   'A exclusão não pode ser desfeita pelo aplicativo. Os arquivos de extrato originais não serão apagados.')
        if not messagebox.askyesno('Excluir conta / cartão',warning,icon='warning',default='no'): return
        try:
            self.store.delete_account(account)
            self.load_accounts()
            self.month.set('')
            self.refresh()
            self.import_status.config(text='Conta/cartão excluído do aplicativo.')
        except (ValueError,sqlite3.Error) as exc:
            messagebox.showerror('Não foi possível excluir',str(exc))

    def new_account(self):
        win = tk.Toplevel(self)
        win.title('Nova conta ou cartão')
        win.transient(self)
        ttk.Label(win, text='Nome (ex.: Banco • conta corrente)', padding=12).pack()
        name = ttk.Entry(win, width=40)
        name.pack(padx=12)
        kind = ttk.Combobox(win, values=['Conta corrente', 'Cartão de crédito'], state='readonly', width=37)
        kind.current(0)
        kind.pack(pady=12)
        def save():
            try:
                self.store.add_account(name.get(), kind.get())
                self.load_accounts()
                self.account.set(f'{name.get().strip()} ({kind.get()})')
                self.refresh()
                win.destroy()
            except (ValueError, sqlite3.Error) as exc:
                messagebox.showerror('Não foi possível criar', str(exc), parent=win)
        ttk.Button(win, text='Criar', command=save).pack(pady=12)

    def import_file(self):
        paths = filedialog.askopenfilenames(parent=self, title='Selecionar extratos e faturas',
            filetypes=[('Extratos e faturas', '*.ofx *.OFX *.csv *.CSV *.xlsx *.XLSX'), ('Todos', '*')])
        if not paths:
            return
        win = tk.Toplevel(self)
        win.title('Escolher destino dos arquivos')
        win.geometry('850x450')
        win.transient(self)
        win.grab_set()
        ttk.Label(win, text='Escolha a conta de cada arquivo. A prévia será apresentada antes de salvar.', padding=15).pack(anchor='w')
        area = ttk.Frame(win)
        area.pack(fill='both', expand=True, padx=15)
        canvas = tk.Canvas(area, highlightthickness=0)
        scroll = ttk.Scrollbar(area, command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        body = ttk.Frame(canvas)
        item = canvas.create_window((0, 0), window=body, anchor='nw')
        body.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(item, width=e.width))
        choices = []
        accounts = self.store.accounts()
        for index, path in enumerate(paths):
            ttk.Label(body, text=Path(path).name, wraplength=360).grid(row=index, column=0, sticky='w', pady=10, padx=6)
            box = ttk.Combobox(body, values=list(self.accounts), state='readonly', width=40)
            box.grid(row=index, column=1, padx=6)
            kind = 'Cartão de crédito' if Path(path).suffix.lower() == '.xlsx' else ('Conta corrente' if Path(path).suffix.lower() == '.ofx' else None)
            candidates = [a for a in accounts if a['kind'] == kind] if kind else []
            if len(candidates) == 1:
                box.set(next(label for label, ident in self.accounts.items() if ident == candidates[0]['id']))
            elif self.account.get() in self.accounts:
                box.set(self.account.get())
            choices.append((path, box))
        selected = []
        def proceed():
            if any(box.get() not in self.accounts for _, box in choices):
                messagebox.showerror('Escolha as contas', 'Selecione uma conta para cada arquivo.', parent=win)
                return
            selected.extend((path, self.accounts[box.get()]) for path, box in choices)
            win.destroy()
        ttk.Button(win, text='Revisar arquivos selecionados', command=proceed).pack(pady=15)
        self.wait_window(win)
        if not selected:
            return
        self.import_button.state(['disabled'])
        total = 0
        saved_files = 0
        try:
            for index, (path, account) in enumerate(selected, 1):
                self.import_status.config(text=f'Arquivo {index} de {len(selected)}: {Path(path).name}')
                count = self.process_file(account, path)
                total += count
                saved_files += count > 0
            self.account.set('Todas')
            self.ownership.set('Todos os titulares')
            self.month.set('')
            self.search.delete(0, 'end')
            self.refresh()
            self.import_status.config(text=f'{total} lançamentos novos salvos • metadados das faturas revisadas também são atualizados.')
        finally:
            self.import_button.state(['!disabled'])

    def process_file(self, account, path):
        try:
            raw = Path(path).read_bytes()
            if Path(path).suffix.lower() == '.ofx':
                return self.preview(account, path, raw, parse_ofx(raw))
            elif Path(path).suffix.lower() == '.xlsx':
                selected = next(r for r in self.store.accounts() if r['id'] == account)
                if selected['kind'] != 'Cartão de crédito':
                    raise ValueError('Selecione a conta do cartão para importar a fatura XLSX.')
                return self.preview(account, path, raw, parse_xlsx(raw))
            elif Path(path).suffix.lower() == '.csv':
                fields, rows = csv_table(raw)
                return self.csv_mapping(account, path, raw, fields, rows)
            else:
                raise ValueError('Selecione OFX, CSV ou XLSX.')
        except (ValueError, OSError, UnicodeError, csv.Error) as exc:
            messagebox.showerror('Erro na importação', f'{Path(path).name}: {exc}')
            return 0

    def csv_mapping(self, account, path, raw, fields, rows):
        win = tk.Toplevel(self)
        result = [0]
        win.title('Colunas do CSV')
        win.grab_set()
        win.transient(self)
        ttk.Label(win, text='Associe as colunas do extrato. Nenhum dado será salvo nesta etapa.', padding=15).grid(columnspan=2)
        choices = {}
        aliases = {'date': ['data', 'date', 'data lancamento'], 'description': ['descricao', 'description', 'title', 'historico'], 'amount': ['valor', 'amount'], 'fitid': ['id', 'fitid', 'identificador']}
        for i, (key, label) in enumerate([('date', 'Data'), ('description', 'Descrição'), ('amount', 'Valor com sinal'), ('fitid', 'ID (opcional)')], 1):
            ttk.Label(win, text=label, padding=8).grid(row=i, column=0)
            box = ttk.Combobox(win, values=[''] + fields, state='readonly', width=35)
            box.grid(row=i, column=1, padx=12)
            box.set(next((f for f in fields if normalize(f) in aliases[key]), ''))
            choices[key] = box
        invert = tk.BooleanVar()
        ttk.Checkbutton(win, text='Inverter sinais: compras positivas no arquivo viram despesas negativas', variable=invert).grid(row=5, columnspan=2, padx=12, pady=12)
        ttk.Label(win, text='Aceita datas DD/MM/AAAA e AAAA-MM-DD; valores 1.234,56 ou 1234.56.').grid(row=6, columnspan=2, padx=12)
        def proceed():
            try:
                mapping = {key: box.get() for key, box in choices.items()}
                required = [mapping[key] for key in ('date', 'description', 'amount')]
                if not all(required) or len(set(required)) < 3:
                    raise ValueError('Escolha três colunas distintas para data, descrição e valor.')
                parsed = parse_csv(rows, mapping, invert.get())
                result[0] = self.preview(account, path, raw, parsed)
                win.destroy()
            except ValueError as exc:
                messagebox.showerror('Confira as colunas', str(exc), parent=win)
        ttk.Button(win, text='Ver prévia', command=proceed).grid(row=7, columnspan=2, pady=15)
        self.wait_window(win)
        return result[0]

    def preview(self, account, path, raw, parsed):
        result = [0]
        rows = self.store.preview(account, parsed)
        win = tk.Toplevel(self)
        name = next(r['name'] for r in self.store.accounts() if r['id'] == account)
        win.title(f'Revisar importação • {name}')
        win.geometry('1050x600')
        win.transient(self)
        win.grab_set()
        ttk.Label(win, text=f'{Path(path).name} • {len(rows)} lançamentos • Negativos = despesas; positivos = créditos.', padding=15).pack(anchor='w')
        tree = self.table(win, ['Data', 'Fatura', 'Descrição', 'Valor', 'Categoria', 'Situação'])
        tree.master.pack(fill='both', expand=True, padx=15)
        for row in rows:
            tree.insert('', 'end', values=(row['date'], row.get('invoice_month', ''), row['description'], brl(row['amount']), row['category'], row['status']))
        include = tk.BooleanVar()
        ttk.Checkbutton(win, text='Incluir possíveis duplicatas (mesma data, descrição e valor, sem ID coincidente)', variable=include).pack(anchor='w', padx=15, pady=10)
        ttk.Label(win, text='IDs repetidos e conflitos de ID não serão importados. Conflitos precisam ser conferidos no extrato.').pack(anchor='w', padx=15)
        def save():
            try:
                count = self.store.save(account, Path(path).name, raw, rows, include.get())
                result[0] = count
                win.destroy()
                self.refresh()
            except (ValueError, sqlite3.Error) as exc:
                messagebox.showerror('Importação não salva', str(exc), parent=win)
        ttk.Button(win, text='Salvar lançamentos no banco SQL', command=save).pack(pady=15)
        ttk.Button(win, text='Pular este arquivo', command=win.destroy).pack(pady=(0, 10))
        self.wait_window(win)
        return result[0]

    def categorize(self):
        ids = self.tree.selection()
        if not ids:
            self.pages.select(1)
            messagebox.showinfo('Selecione lançamentos', 'Selecione uma ou mais linhas na aba Transações para categorizar.')
            return
        win = tk.Toplevel(self)
        win.title('Categoria e regra automática')
        ttk.Label(win, text=f'{len(ids)} lançamentos selecionados', padding=12).pack()
        category = ttk.Combobox(win, values=CATEGORIES, state='readonly', width=42)
        category.set('Sem categoria')
        category.pack(padx=12)
        ttk.Label(win, text='Regra opcional: texto contido na descrição de futuras importações', padding=12).pack()
        term = ttk.Entry(win, width=44)
        term.pack()
        def save():
            try:
                self.store.categorize(ids, category.get(), term.get())
            except (ValueError, sqlite3.Error) as exc:
                messagebox.showerror('Confira os lançamentos', str(exc), parent=win)
                return
            win.destroy()
            self.refresh()
        ttk.Button(win, text='Salvar categoria', command=save).pack(pady=12)

    def undo(self):
        if messagebox.askyesno('Desfazer importação', 'Remover os lançamentos da última importação, de qualquer conta? Você poderá importar o arquivo novamente.'):
            self.store.undo()
            self.refresh()

    def backup(self):
        path = filedialog.asksaveasfilename(defaultextension='.sqlite3', initialfile='backup-despesas.sqlite3')
        if path:
            try:
                if Path(path).resolve() == self.store.path.resolve():
                    raise ValueError('Escolha outro arquivo para o backup.')
                self.store.backup(path)
                messagebox.showinfo('Backup', 'Cópia salva com sucesso.')
            except (OSError, ValueError, sqlite3.Error) as exc:
                messagebox.showerror('Erro no backup', str(exc))


if __name__ == '__main__':
    App().mainloop()
