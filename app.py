#!/usr/bin/env python3
"""Janela local para gestão de despesas."""
import os
import csv
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
        self.minsize(900, 600)
        data = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'minhas-despesas'
        self.store = Store(data / 'despesas.sqlite3')
        if not self.store.accounts():
            self.store.add_account('Itaú • conta corrente', 'Conta corrente')
            self.store.add_account('Itaú • cartão', 'Cartão de crédito')
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', font=('DejaVu Sans', 10))
        style.configure('Treeview', rowheight=30)
        style.configure('Title.TLabel', font=('DejaVu Sans', 23, 'bold'))
        style.configure('Import.TButton', font=('DejaVu Sans', 13, 'bold'), padding=(20, 12))
        self.configure(background='#f3f5f9')
        style.configure('TFrame', background='#f3f5f9')
        style.configure('TLabel', background='#f3f5f9', foreground='#17243b')
        style.configure('TButton', padding=(10, 7))
        style.configure('TNotebook.Tab', padding=(22, 10))
        style.configure('Treeview', background='white', fieldbackground='white', borderwidth=0)
        style.configure('Treeview.Heading', background='#e6edf5', padding=8)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        header = ttk.Frame(self, padding=20)
        header.grid(sticky='ew')
        ttk.Label(header, text='Minhas despesas', style='Title.TLabel').pack(anchor='w')
        ttk.Label(header, text='Contas e cartões • Importação semanal de extratos • Valores em reais').pack(anchor='w', pady=6)
        self.import_button = ttk.Button(header, text='Selecionar arquivos para importar', style='Import.TButton', command=self.import_file)
        self.import_button.pack(anchor='w', pady=(10, 4))
        self.import_status = ttk.Label(header, text='Selecione OFX, CSV ou XLSX. Os lançamentos confirmados ficam salvos neste computador.')
        self.import_status.pack(anchor='w')
        bar = ttk.Frame(self, padding=(20, 0))
        bar.grid(sticky='ew')
        for label, command in [('＋ Conta ou cartão', self.new_account), ('Categorizar seleção', self.categorize), ('Desfazer última importação', self.undo), ('Backup', self.backup)]:
            ttk.Button(bar, text=label, command=command).pack(side='left', padx=(0, 8))
        filter_container = ttk.Frame(self, padding=(20, 10))
        filter_container.grid(sticky='ew')
        filters = ttk.Frame(filter_container)
        filters.pack(fill='x')
        ttk.Label(filters, text='Conta:').pack(side='left')
        self.account = ttk.Combobox(filters, state='readonly', width=24)
        self.account.pack(side='left', padx=6)
        self.account.bind('<<ComboboxSelected>>', lambda e: self.refresh())
        ttk.Label(filters, text='Mês:').pack(side='left', padx=6)
        self.previous_month = ttk.Button(filters, text='‹', width=3, command=lambda: self.move_month(1))
        self.previous_month.pack(side='left')
        self.month = ttk.Combobox(filters, state='readonly', width=21)
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
        self.pages = ttk.Notebook(self)
        self.pages.grid(row=3, column=0, sticky='nsew', padx=20)
        overview = ttk.Frame(self.pages, padding=14)
        transactions = ttk.Frame(self.pages, padding=12)
        self.pages.add(overview, text='Visão geral')
        self.pages.add(transactions, text='Transações')
        overview.columnconfigure(0, weight=1)
        overview.rowconfigure(2, weight=1)
        cards = ttk.Frame(overview)
        cards.grid(sticky='ew', pady=(0, 14))
        self.metrics = {}
        for index, (key, title, color) in enumerate([
                ('income', 'ENTRADAS / CRÉDITOS', '#137b65'), ('expenses', 'DESPESAS', '#c4445e'),
                ('net', 'RESULTADO DO PERÍODO', '#315fc4'), ('pending', 'PARA CATEGORIZAR', '#a76b17')]):
            cards.columnconfigure(index, weight=1, uniform='cards')
            card = tk.Frame(cards, bg='white', padx=16, pady=16, highlightbackground='#e1e6ee', highlightthickness=1)
            card.grid(row=0, column=index, sticky='nsew', padx=(0, 10) if index < 3 else 0)
            tk.Label(card, text=title, font=('DejaVu Sans', 9, 'bold'), fg='#66758b', bg='white').pack(anchor='w')
            value = tk.Label(card, text='—', font=('DejaVu Sans', 20, 'bold'), fg=color, bg='white')
            value.pack(anchor='w', pady=(8, 0))
            self.metrics[key] = value
        self.dashboard_caption = ttk.Label(overview, text='', font=('DejaVu Sans', 11))
        self.dashboard_caption.grid(sticky='w', pady=(0, 12))
        plots = ttk.Frame(overview)
        plots.grid(sticky='nsew')
        plots.columnconfigure(0, weight=1, uniform='plots')
        plots.columnconfigure(1, weight=1, uniform='plots')
        plots.rowconfigure(0, weight=1)
        self.category_plot = tk.Canvas(plots, bg='white', highlightthickness=0, height=270)
        self.account_plot = tk.Canvas(plots, bg='white', highlightthickness=0, height=270)
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
        self.summary = ttk.Label(self, padding=(20, 8), font=('DejaVu Sans', 10))
        self.summary.grid(sticky='ew')
        ttk.Label(self, text='Resultado dos lançamentos, não saldo bancário. Transferências e pagamentos de fatura são excluídos dos totais.', padding=(20, 0)).grid(sticky='w')
        ttk.Label(self, text='Período: mês da fatura para XLSX; data do lançamento para OFX/CSV.', padding=(20, 2)).grid(sticky='w')
        ttk.Label(self, text=f'Banco local: {self.store.path}', padding=(20, 6)).grid(sticky='w')
        planning = ttk.Frame(self.pages, padding=4)
        self.pages.add(planning, text='Planejamento e faturas')
        self.finance = FinanceUI(self, planning)
        self.load_accounts()
        self.refresh()
        self.protocol('WM_DELETE_WINDOW', self.close)

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
        months = self.store.months(self.accounts.get(self.account.get()))
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

    def refresh(self):
        self.load_months()
        rows = self.store.transactions(self.month_options[self.month.get()], self.accounts.get(self.account.get()), self.search.get(), '' if self.ownership.get()=='Todos os titulares' else self.ownership.get())
        self.tree.delete(*self.tree.get_children())
        for r in rows:
            self.tree.insert('', 'end', iid=str(r['id']), values=(r['date'], r['invoice_month'], r['name'], r['ownership'] or 'Não informado', r['holder'], r['description'], brl(r['amount']), r['category']), tags=('negative',) if r['amount'] < 0 else ())
        relevant = [r for r in rows if r['category'] != CATEGORIES[-1]]
        income = sum(r['amount'] for r in relevant if r['amount'] > 0)
        expenses = -sum(r['amount'] for r in relevant if r['amount'] < 0)
        pending = sum(r['category'] == 'Sem categoria' for r in rows)
        for key, value in [('income', brl(income)), ('expenses', brl(expenses)),
                           ('net', brl(income-expenses)), ('pending', str(pending))]:
            self.metrics[key].config(text=value)
        categories, accounts = defaultdict(int), defaultdict(int)
        for row in relevant:
            if row['amount'] < 0:
                categories[row['category']] -= row['amount']
                accounts[row['name']] -= row['amount']
        self.chart_data = (categories, accounts)
        context = f'{self.month.get()} • {self.account.get()} • {self.ownership.get()} • {len(rows)} lançamentos'
        if self.search.get():
            context += f' • Busca: {self.search.get()}'
        self.dashboard_caption.config(text=context)
        self.summary.config(text=f'{len(rows)} lançamentos • {pending} para categorizar')
        self.draw_dashboard()
        self.finance.refresh()

    def draw_dashboard(self):
        for canvas, data, title, color in [
                (self.category_plot, self.chart_data[0], 'Despesas por categoria', '#5b68d6'),
                (self.account_plot, self.chart_data[1], 'Despesas por conta e cartão', '#189b91')]:
            canvas.delete('all')
            width, height = canvas.winfo_width(), canvas.winfo_height()
            if width < 10:
                continue
            canvas.create_text(20, 24, anchor='w', text=title, fill='#17243b', font=('DejaVu Sans', 12, 'bold'))
            if not data:
                canvas.create_text(width/2, height/2, text='Nenhuma despesa neste período.\nImporte um extrato ou escolha outro mês.', justify='center', fill='#66758b', font=('DejaVu Sans', 10), width=width-40)
                continue
            limit = max(1, min(6, (height-55)//48))
            items = sorted(data.items(), key=lambda item: item[1], reverse=True)
            if len(items) > limit:
                items = items[:limit-1] + [('Demais itens', sum(v for _, v in items[limit-1:]))]
            maximum = max(value for _, value in items)
            for index, (label, value) in enumerate(items):
                y = 56 + index*48
                short = label if len(label) <= max(15, (width-175)//7) else label[:max(15, (width-175)//7)-1]+'…'
                canvas.create_text(20, y, anchor='w', text=short, fill='#43516a', font=('DejaVu Sans', 10))
                canvas.create_text(width-20, y, anchor='e', text=brl(value), fill='#17243b', font=('DejaVu Sans', 10, 'bold'))
                canvas.create_rectangle(20, y+12, width-20, y+23, fill='#edf1f7', outline='')
                canvas.create_rectangle(20, y+12, 20+(width-40)*value/maximum, y+23, fill=color, outline='')

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
