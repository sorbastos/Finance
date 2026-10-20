"""Consultas de apresentação e casos de uso, sem importar Qt ou Tkinter.

O serviço recebe filtros explícitos e devolve estruturas serializáveis. Essa
fronteira permite testar as telas sem abrir uma janela e trocar a apresentação
sem duplicar regras financeiras. SQLite é acessado na thread proprietária.
"""
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from finance import FinanceStore, TRANSFER, month_shift, validate_month
from .catalog import ACTIONS, PAGES
from .formatting import currency, editable_money, trend, month_title, installment_title


@dataclass
class Filters:
    """Recorte corrente; conta None e titularidade vazia representam todos."""
    kind: str = 'Conta corrente'
    account: int | None = None
    month: str = ''
    ownership: str = ''
    search: str = ''


def field(key: str, label: str, value: Any = '', choices: list | None = None,
          multiline: bool = False, read_only: bool = False) -> dict:
    """Descreve valor e permissão de edição; o QML escolhe o controle adequado."""
    return dict(key=key, label=label, value=str(value), choices=choices or [], multiline=multiline, read_only=read_only)


def table(headers: list[str], records: list[tuple]) -> dict:
    """Converte linhas em células e identidades estáveis, nunca índices visuais."""
    return dict(headers=headers, rows=[dict(id=str(key), cells=[str(v) for v in values])
                                      for key, values in records])


class FinanceService:
    """Coordena os casos de uso do desktop sobre o domínio FinanceStore."""

    def __init__(self, database: Path):
        """Abre explicitamente o banco escolhido; sem cópias ou backups implícitos."""
        first_start = not database.exists()
        self.store = FinanceStore(database)
        with self.store.db:
            self.store.db.execute('CREATE TABLE IF NOT EXISTS preferences(key TEXT PRIMARY KEY,value TEXT)')
        if first_start:
            self.store.add_account('Itaú • conta corrente', 'Conta corrente')
            self.store.add_account('Itaú • cartão', 'Cartão de crédito')

    def close(self) -> None:
        """Encerra a conexão pertencente à sessão desktop."""
        self.store.db.close()

    def preference(self, key: str, default: str = '') -> str:
        """Lê preferências compatíveis com a interface anterior."""
        row = self.store.db.execute('SELECT value FROM preferences WHERE key=?', (key,)).fetchone()
        return row[0] if row else default

    def set_preference(self, key: str, value: str) -> None:
        """Persiste apenas a preferência solicitada."""
        with self.store.db:
            self.store.db.execute('INSERT OR REPLACE INTO preferences VALUES (?,?)', (key, value))

    def months(self, filters: Filters) -> list[str]:
        """Inclui meses de extratos, fechamentos e projeções sem criar lançamentos."""
        periods = {r['invoice_month'] or r['date'][:7] for r in self.store.transactions(account=filters.account)
                   if r['kind'] == filters.kind}
        if filters.kind == 'Cartão de crédito':
            periods.update(r['month'] for r in self.store.invoices(filters.account))
            periods.update(r['month'] for r in self.store.forecasts(filters.account))
        else:
            periods.update(r['month'] for r in self.store.closings()
                           if filters.account is None or r['account'] == filters.account)
        periods.add(date.today().strftime('%Y-%m'))
        return sorted(periods, reverse=True)

    def transactions(self, filters: Filters, month: str | None = None) -> list[dict]:
        """Aplica o mesmo recorte à lista e aos indicadores comparáveis."""
        return [dict(r) for r in self.store.transactions(
            filters.month if month is None else month, filters.account, filters.search,
            filters.ownership if filters.kind == 'Cartão de crédito' and filters.ownership != 'Não informado' else '')
            if r['kind'] == filters.kind and (filters.ownership != 'Não informado' or not r['ownership'])]

    def snapshot(self, page: str, filters: Filters) -> dict:
        """Monta uma fotografia consistente da tela; seleção e rolagem ficam no QML."""
        meta = next((p for p in PAGES if p['id'] == page), PAGES[0])
        state = dict(meta, **table([], []), note='', metrics=[], charts=[], badges={},
                     actions=[dict(id=key, label=label) for key, label in ACTIONS.get(page, [])])
        state['accounts'] = [dict(id=0, name='Todas')] + [dict(id=a['id'], name=a['name'])
            for a in self.store.accounts() if a['kind'] == filters.kind]
        state['months'] = ['Todos os meses'] + self.months(filters)
        if page in ('accounts', 'cards', 'transactions', 'budget_transactions'):
            rows = self.transactions(filters)
            if page == 'budget_transactions':
                rows = [r for r in rows if r['category'] != TRANSFER and
                        (r['kind'] == 'Cartão de crédito' or r['amount'] < 0)]
            state.update(table(['Data', 'Fatura', 'Conta', 'Titularidade', 'Portador', 'Estabelecimento', 'Descrição', 'Valor', 'Categoria', 'Etiquetas'], [
                (r['id'], [r['date'], r['invoice_month'], r['name'], r['ownership'] or 'Não informado',
                           r['holder'], r['description'], r['bank_description'] if r['bank_description'] is not None else 'Lançamento manual', currency(r['amount']),
                           'Dividida: ' + ', '.join(p['category'] for p in self.store.splits(r['id']))
                           if self.store.splits(r['id']) else ('Não classificado' if r['category'] == 'Sem categoria' else r['category']),
                           ', '.join(self.store.transaction_tags(r['id']))]) for r in rows]))
            if page in ('accounts', 'cards'):
                # Painéis mantêm o resumo; transações e orçamento compartilham a classificação.
                index = state['headers'].index('Categoria')
                state['headers'].pop(index)
                for entry in state['rows']:
                    entry['cells'].pop(index)
            if page != 'budget_transactions':
                state.update(self.dashboard(filters, rows))
            if page in ('accounts', 'cards'):
                summaries = []
                for account in self.store.accounts():
                    chosen = [r for r in rows if r['account'] == account['id'] and
                              (filters.kind != 'Cartão de crédito' or r['category'] != TRANSFER)]
                    if account['kind'] != filters.kind or (filters.account and account['id'] != filters.account):
                        continue
                    income = sum(r['amount'] for r in chosen if r['amount'] > 0)
                    expenses = -sum(r['amount'] for r in chosen if r['amount'] < 0)
                    summaries.append((account['id'], [account['name'], currency(income), currency(expenses), currency(income-expenses)]))
                state.update(table(['Conta / cartão', 'Entradas / créditos', 'Saídas / compras', 'Movimento líquido'], summaries))
        elif page == 'invoices':
            rows = self.invoice_projection(filters.account)
            rows = [r for r in rows if not filters.month or r['month'] == filters.month]
            state.update(table(['Cartão', 'Mês', 'Situação', 'Total estimado', 'Titular estimado', 'Adicional estimado',
                'Sem identificação', 'Parcelas previstas', 'Lançamentos', 'Total informado', 'Pago vinculado',
                'Restante confirmado', 'Vencimento'], [
                (f'{r["account"]}|{r["month"]}', [r['name'], month_title(r['month']), r['state']] +
                 [currency(r[k]) for k in ('estimate', 'titular', 'adicional', 'unknown', 'projected', 'calculated', 'total', 'paid', 'remaining')]
                 + [r['due'] or 'A informar']) for r in rows]))
            state['note'] = ('Uma fatura por cartão e mês, reunindo titular e adicional. Subtotais por portador e total estimado '
                'somam lançamentos e parcelas previstas; não somam o total informado novamente. O restante confirmado '
                'considera somente a fatura importada/cadastrada e seus pagamentos. Previsões não são gravadas como compras.')
        elif page == 'forecasts':
            monthly = [r for r in self.store.forecasts(filters.account) if filters.month and r['month'] == filters.month]
            rows = [r for r in monthly if not filters.ownership or r['ownership'] == filters.ownership]
            rows.sort(key=lambda r: (r['ownership'], r['holder'], r['description']))
            periods = set(self.months(filters))
            if filters.month:
                periods.add(filters.month)
            state['forecastMonths'] = [dict(value=m, label=month_title(m)) for m in sorted(periods, reverse=True)]
            state['ownerOptions'] = [dict(value=o, label=o or 'Todos juntos', count=len(monthly) if not o else
                sum(r['ownership'] == o for r in monthly)) for o in ('', 'Titular', 'Adicional', 'Não informado')]
            state.update(table(['Titularidade', 'Portador', 'Parcela', 'Descrição', 'Valor', 'Cartão', 'Situação'], [
                (f'{r["transaction_id"]}|{r["month"]}', [r['ownership'], r['holder'] or 'Não informado',
                     installment_title(r['description'], r['status']), r['description'], currency(r['amount']),
                     r['name'], r['status']]) for i, r in enumerate(rows)]))
            state['metrics'] = [dict(label=owner, value=currency(sum(r['amount'] for r in monthly if r['ownership'] == owner)), detail='Total do portador no mês', tone='purple')
                                for owner in ('Titular', 'Adicional', 'Não informado')]
            state['metrics'].append(dict(label='Total do mês (juntos)',
                value=currency(sum(r['amount'] for r in monthly)), detail='Titular + adicional + não informado', tone='blue'))
            state['forecastCaption'] = (f'{month_title(filters.month)} · {filters.ownership or "Todos juntos"} · '
                f'{len(rows)} {"previsão" if len(rows) == 1 else "previsões"} · {currency(sum(r["amount"] for r in rows))}') if filters.month else 'Escolha um mês'
            state['emptyMessage'] = 'Nenhuma parcela prevista para este mês e titularidade.'
            state['note'] = ('Os cartões acima mantêm os totais de todos os portadores no mês; a lista e o valor exibido '
                'no cabeçalho respeitam a titularidade selecionada. Consulte Faturas para ver os valores reunidos por cartão. '
                'Previsões não são compras confirmadas.')
        elif page == 'closings':
            rows = [r for r in self.store.closings(filters.month) if filters.account is None or r['account'] == filters.account]
            state.update(table(['Conta', 'Mês', 'Saldo inicial', 'Movimentação', 'Saldo calculado', 'Saldo informado', 'Diferença', 'Situação'], [
                (f'{r["account"]}|{r["month"]}', [r['name'], r['month']] +
                 [currency(r[k]) for k in ('opening', 'movement', 'calculated', 'reported_closing', 'difference')] + [r['state']]) for r in rows]))
            state['note'] = 'Diferença = saldo do banco − (saldo inicial + movimentações). Novas importações recalculam a conferência.'
        elif page == 'payments':
            pending = [(f'p|{d["id"]}|{c["id"]}', [d['date'], d['name'], c['date'], c['name'], currency(c['amount']), 'Sugestão', 'A escolher'])
                       for d, c in self.store.payment_candidates()]
            linked = [(f'r|{r["id"]}', [r['date'], r['description'], '', r['name'], currency(r['amount']), 'Conciliado', r['invoice_month']])
                      for r in self.store.reconciled()]
            state.update(table(['Data débito', 'Conta / descrição', 'Data crédito', 'Cartão', 'Valor', 'Situação', 'Fatura vinculada'], pending + linked))
            state['note'] = 'Todas as contas e períodos. Sugestões com valores iguais, sinais opostos e até três dias de diferença.'
        elif page == 'budgets':
            if filters.month:
                state['budgetData'] = self.household_budget(filters.month)
            periods = {r['invoice_month'] or r['date'][:7] for r in self.store.transactions()}
            periods.update(r[0] for r in self.store.db.execute('SELECT month FROM budget_goals UNION SELECT month FROM budget_income_settings'))
            periods.add(date.today().strftime('%Y-%m'))
            if filters.month:
                periods.add(filters.month)
            state['months'] = sorted(periods, reverse=True)
            state['budgetMonths'] = [dict(value=m, label=month_title(m)) for m in state['months']]
            state['note'] = ('Orçamento consolidado de todas as contas e cartões, incluindo titular e adicional. '
                'Receitas das contas são informativas; metas e porcentagens usam somente a renda editável. '
                'Gastos usam o mês do lançamento na conta e o mês da fatura no cartão. '
                'Transferências e pagamentos de fatura não entram nos totais. Créditos do cartão reduzem os gastos. '
                'Lançamentos não classificados ficam fora dos gastos, gráficos e porcentagens do orçamento.')
        elif page == 'comparison':
            # Reutiliza o recorte do desktop para não misturar tipos de conta.
            totals = [defaultdict(int), defaultdict(int)]
            if filters.month:
                comparison_filters = Filters(filters.kind, filters.account, filters.month, filters.ownership)
                for index, period in enumerate((month_shift(filters.month, -1), filters.month)):
                    for row in self.transactions(comparison_filters, period):
                        for part in self.store.allocations(row):
                            if part['amount'] < 0 and part['category'] != TRANSFER:
                                totals[index][part['category']] -= part['amount']
            rows = [dict(category=c, previous=totals[0][c], current=totals[1][c], difference=totals[1][c]-totals[0][c])
                    for c in sorted(set(totals[0]) | set(totals[1]))]
            state.update(table(['Categoria', 'Mês anterior', 'Mês selecionado', 'Variação'], [
                (r['category'], [r['category']] + [currency(r[k]) for k in ('previous', 'current', 'difference')]) for r in rows]))
            state['note'] = 'A comparação respeita conta e titularidade; ausência de extrato não comprova gasto zero.'
        elif page == 'rules':
            state.update(table(['Texto na descrição', 'Categoria'], [(r['term'], [r['term'], r['category']])
                for r in self.store.db.execute('SELECT * FROM rules ORDER BY term')]))
        elif page == 'categories':
            state.update(table(['Categoria', 'Tipo'], [(c, [c, 'Sistema' if c in ('Sem categoria', TRANSFER) else 'Editável'])
                                                      for c in self.store.categories()]))
        elif page == 'settings':
            state.update(table(['Conta / cartão', 'Tipo'], [(a['id'], [a['name'], a['kind']]) for a in self.store.accounts()]))
            state['note'] = 'Dados locais. Backup manual e restauração por arquivo; sem sincronização automática.'
        state['badges'] = dict(budgets=sum(r['category'] == 'Sem categoria' and not self.store.splits(r['id']) for r in self.store.transactions()),
            invoices=sum(r['state'] == 'Aberta' for r in self.store.invoices()),
            closings=sum(r['difference'] != 0 for r in self.store.closings()))
        # Todas as telas temporais usam o mesmo contrato de menu, sem perder meses vazios.
        periods = {m for m in state['months'] if m != 'Todos os meses'}
        if filters.month:
            periods.add(filters.month)
        state['periodOptions'] = ([dict(value='', label='Todos os meses')]
            if page not in ('forecasts', 'budgets') else []) + [
                dict(value=m, label=month_title(m)) for m in sorted(periods, reverse=True)]
        if page in ('cards', 'transactions', 'comparison', 'budget_transactions') and filters.kind == 'Cartão de crédito':
            unfiltered = self.transactions(replace(filters, ownership=''))
            if page == 'budget_transactions':
                unfiltered = [r for r in unfiltered if r['category'] != TRANSFER]
            state['ownerOptions'] = [dict(value=owner, label=owner or 'Todos juntos',
                count=len(unfiltered) if not owner else sum((r['ownership'] or 'Não informado') == owner for r in unfiltered))
                for owner in ('', 'Titular', 'Adicional', 'Não informado')]
        return state

    def household_budget(self, month: str) -> dict:
        """Formata o relatório de metas sem delegar cálculos monetários ao QML."""
        from decimal import Decimal
        report = self.store.planner.report(month)
        def percentage(value: int, base: int) -> str:
            """Uma base ausente não permite inventar um percentual utilizado."""
            return f'{Decimal(value)*100/base:.1f}%'.replace('.', ',') if base else '—'
        for group in report['groups']:
            group.update(spentLabel=currency(group['spent']), plannedLabel=currency(group['planned']),
                remainingLabel=currency(group['remaining']), utilization=percentage(group['spent'], group['planned']),
                incomeShare=percentage(group['spent'], report['planning_income']))
        names = {'unassigned': 'Não classificado', **{g['id']: g['name'] for g in report['groups']}}
        report['categoryGroups'] = [dict(id=g['id'], name=g['name']) for g in report['groups']] + [dict(id='unassigned', name='Não classificado')]
        report['goals'] = [g for g in report['groups'] if g['id'] != 'unassigned']
        report['spendingChart'] = [dict(label=g['name'], value=g['spent'], formatted=currency(g['spent']))
                                   for g in report['groups'] if g['spent'] > 0]
        report['spendingColors'] = [g['color'] for g in report['groups'] if g['spent'] > 0]
        for assignment in report['assignments']:
            assignment.update(groupName=names[assignment['group']], spentLabel=currency(assignment['spent']))
            if assignment['category'] == 'Sem categoria':
                assignment['category'] = 'Não classificado'
        report.update(monthLabel=month_title(month), incomeLabel=currency(report['income']),
            planningIncomeLabel=currency(report['planning_income']),
            spentLabel=currency(report['spent']), remainingLabel=currency(report['remaining']),
            cashLabel=currency(report['cash']), cardLabel=currency(report['card']),
            utilization=percentage(report['spent'], report['planning_income']),
            goalSourceLabel=month_title(report['source']) if report['source'] else 'Distribuição inicial sugerida')
        report['summary'] = table(['Grupo', 'Gasto líquido', 'Planejado', 'Disponível', 'Uso da meta', '% da renda'],
            [(g['id'], [g['name'], g['spentLabel'], g['plannedLabel'], g['remainingLabel'], g['utilization'], g['incomeShare']])
             for g in report['groups']])
        return report

    def save_budget_goals(self, month: str, values: dict) -> None:
        """Valida e persiste a distribuição percentual para o mês selecionado."""
        self.store.planner.set_goals(month, values)

    def invoice_projection(self, account: int | None = None) -> list[dict]:
        """Consolida faturas reais e projeções sem persistir dados estimados.

        O total informado já pode incluir compras não disponíveis no extrato;
        por isso nunca é somado às previsões. A estimativa usa só lançamentos
        disponíveis e parcelas projetadas, mantendo o valor informado à parte.
        """
        invoices = {(r['account'], r['month']): dict(r, projected=0, estimate=r['calculated'])
                    for r in self.store.invoices(account)}
        owner_keys = {'Titular': 'titular', 'Adicional': 'adicional', 'Não informado': 'unknown'}
        for forecast in self.store.forecasts(account):
            if forecast['amount'] <= 0:
                continue
            key = (forecast['account'], forecast['month'])
            row = invoices.setdefault(key, dict(account=key[0], month=key[1], name=forecast['name'],
                due='', state='Prevista', total=None, calculated=0, titular=0, adicional=0,
                unknown=0, paid=0, remaining=None, projected=0, estimate=0))
            row['projected'] += forecast['amount']
            row['estimate'] += forecast['amount']
            row[owner_keys.get(forecast['ownership'], 'unknown')] += forecast['amount']
        return sorted(invoices.values(), key=lambda r: (r['month'], r['name']), reverse=True)

    def dashboard(self, filters: Filters, rows: list[dict]) -> dict:
        """Gera indicadores e séries; cartão exclui pagamentos das compras reais."""
        is_card = filters.kind == 'Cartão de crédito'
        relevant = [r for r in rows if not is_card or r['category'] != TRANSFER]
        previous = self.transactions(filters, month_shift(filters.month, -1)) if filters.month else []
        previous = [r for r in previous if not is_card or r['category'] != TRANSFER]
        income = sum(r['amount'] for r in relevant if r['amount'] > 0)
        expenses = -sum(r['amount'] for r in relevant if r['amount'] < 0)
        old_income = sum(r['amount'] for r in previous if r['amount'] > 0)
        old_expenses = -sum(r['amount'] for r in previous if r['amount'] < 0)
        if is_card:
            invoices = [r for r in self.store.invoices(filters.account) if not filters.month or r['month'] == filters.month]
            values = [('Compras do filtro', expenses, trend(expenses, old_expenses, bool(previous)), 'red'),
                      ('Estornos / créditos', income, trend(income, old_income, bool(previous)), 'green'),
                      ('Faturas consolidadas', sum(r['total'] if r['total'] is not None else r['calculated'] for r in invoices), 'Titular + adicional, sem busca', 'blue'),
                      ('Restante das faturas', sum(r['remaining'] for r in invoices), 'Depende dos pagamentos vinculados', 'purple')]
        else:
            values = [('Entradas', income, trend(income, old_income, bool(previous)), 'green'),
                      ('Saídas', expenses, trend(expenses, old_expenses, bool(previous)), 'red'),
                      ('Movimentação líquida', income - expenses, 'Não inclui saldo inicial', 'blue')]
        metrics = [dict(label=label, value=currency(amount), detail=detail, tone=tone) for label, amount, detail, tone in values]
        categories, groups, outgoing, incoming = (defaultdict(int) for _ in range(4))
        for row in relevant:
            if row['amount'] < 0:
                # Rateios pertencem às categorias de suas partes, sem contar a compra duas vezes.
                for part in self.store.allocations(row):
                    categories[part['category']] -= part['amount']
                groups[(row['ownership'] or 'Não informado') if is_card else row['date']] -= row['amount']
                outgoing[row['date']] -= row['amount']
            elif row['amount'] > 0:
                incoming[row['date']] += row['amount']
        def series(data: dict, chronological: bool = False, percentages: bool = False) -> list[dict]:
            """Envia centavos e rótulos prontos; Canvas desenha sem recalcular totais."""
            items = sorted(data.items()) if chronological else sorted(data.items(), key=lambda x: x[1], reverse=True)
            if not chronological and len(items) > 6:
                items = items[:5] + [('Demais itens', sum(value for _, value in items[5:]))]
            from decimal import Decimal
            total = sum(data.values())
            result = []
            for label, value in items:
                percentage = f'{Decimal(value)*100/total:.1f}%'.replace('.', ',') if total else '0,0%'
                result.append(dict(label=label, value=value,
                    formatted=f'{currency(value)} · {percentage}' if percentages else currency(value)))
            return result
        # Uma escala diária contínua evita ligar datas distantes como dias seguidos.
        if outgoing or incoming:
            days = set(outgoing) | set(incoming)
            day, last = date.fromisoformat(min(days)), date.fromisoformat(max(days))
            while day <= last:
                outgoing.setdefault(day.isoformat(), 0)
                incoming.setdefault(day.isoformat(), 0)
                day += timedelta(days=1)
        return dict(metrics=metrics, charts=[series(categories, percentages=True), series(groups)], timeline=[series(outgoing, True), series(incoming, True)],
                    chartTitles=['Despesas por categoria', 'Compras por titularidade' if is_card else 'Saídas por dia'],
                    note='Os filtros afetam lançamentos e gráficos. Totais das faturas consolidam titular e adicional.' if is_card else
                    'Entradas e saídas incluem transferências e pagamentos. Use Fechamento mensal para conferir o saldo do banco.')

    def account_choices(self, kind: str = '') -> list[str]:
        """IDs explícitos evitam ambiguidades entre contas de nomes semelhantes."""
        return [f'{a["id"]} · {a["name"]}' for a in self.store.accounts() if not kind or a['kind'] == kind]

    def transaction(self, ident: str) -> dict:
        """Resolve uma identidade de lançamento e falha claramente se foi removido."""
        row = self.store.db.execute('SELECT * FROM transactions WHERE id=?', (int(ident),)).fetchone()
        if not row:
            raise ValueError('Lançamento não encontrado. Atualize a tela.')
        return dict(row)

    def form(self, action: str, selected: list[str], filters: Filters) -> dict:
        """Prepara um formulário revisável, sem gravar nada ao abri-lo."""
        # Criar nunca pode reutilizar a identidade de uma linha selecionada.
        if action.startswith('new_'):
            selected = []
        needs_one = {'edit_transaction', 'split', 'clear_split', 'tags', 'edit_category', 'delete_category', 'edit_rule',
                     'delete_rule', 'delete_budget', 'delete_account', 'reconcile', 'unreconcile', 'installment', 'reset_invoice', 'delete_forecast'}
        if action in needs_one and len(selected) != 1:
            raise ValueError('Selecione uma única linha para esta ação.')
        if action == 'categorize' and not selected:
            raise ValueError('Selecione um ou mais lançamentos.')
        ident = selected[0] if selected else ''
        month = filters.month or date.today().strftime('%Y-%m')
        categories = [c for c in self.store.categories() if c != TRANSFER]
        result = dict(action=action, title='Confira os dados', note='', fields=[], selected=selected, splits=[])
        def account_field(kind: str = '', current: int | None = None) -> dict:
            """Seleciona uma conta válida sem inventar destino para gravar dados."""
            choices = self.account_choices(kind)
            if not choices:
                raise ValueError('Cadastre uma conta ou cartão primeiro.')
            value = next((s for s in choices if int(s.split(' · ')[0]) == current), choices[0])
            return field('account', 'Conta / cartão', value, choices)
        if action in ('new_transaction', 'edit_transaction'):
            row = self.transaction(ident) if ident else {}
            result.update(title='Editar lançamento' if row else 'Novo lançamento',
                note=('Em compras parceladas identificadas, alterações em estabelecimento e etiquetas '
                      'valem para esta parcela e as seguintes, inclusive em próximas importações. '
                      'Datas, valores e descrição bancária são preservados.') if row else '', fields=[
                account_field(current=row.get('account', filters.account)),
                field('date', 'Data (AAAA-MM-DD ou DD/MM/AAAA)', row.get('date', date.today().isoformat())),
                *([field('bank_description', 'Descrição', row['bank_description'], read_only=True)]
                  if row.get('bank_description') is not None else []),
                field('description', 'Estabelecimento', row.get('description', '')),
                field('amount', 'Valor em reais (despesa negativa)', editable_money(row.get('amount'))),
                field('month', 'Mês da fatura (opcional, AAAA-MM)', row.get('invoice_month', '')),
                field('ownership', 'Titularidade', row.get('ownership') or 'Não informado', ['Não informado', 'Titular', 'Adicional']),
                field('holder', 'Portador', row.get('holder', '')), field('card', 'Final do cartão', row.get('card_number', '')),
                field('tags', 'Etiquetas separadas por vírgula', ', '.join(self.store.transaction_tags(ident)) if row else '')])
        elif action == 'categorize':
            current = self.transaction(ident)['category'] if len(selected) == 1 else 'Sem categoria'
            result.update(title=f'Classificar {len(selected)} lançamentos',
                note=('O vínculo da categoria com um grupo do orçamento determina onde o gasto será contabilizado. '
                      'Em compras parceladas identificadas, a classificação também vale para as parcelas seguintes.'),
                fields=[field('category', 'Categoria da transação', current if current in categories else 'Sem categoria', categories),
                        field('term', 'Regra opcional: texto da descrição')])
        elif action in ('new_category', 'edit_category'):
            result.update(title='Renomear categoria' if ident else 'Nova categoria',
                note='A categoria pode ser usada na conta e no cartão. Vincule-a a um grupo na aba Categorias do orçamento.',
                fields=[field('name', 'Nome', ident or '')])
        elif action == 'delete_category':
            if ident in ('Sem categoria', TRANSFER) or ident not in self.store.categories():
                raise ValueError('Selecione uma categoria editável para excluir.')
            count = self.store.db.execute('SELECT COUNT(*) FROM transactions WHERE category=?', (ident,)).fetchone()[0]
            result.update(title=f'Excluir categoria {ident}?',
                note=(f'{count} lançamentos usam esta categoria diretamente. Lançamentos, regras, rateios e parcelas '
                      'vinculadas passarão à categoria escolhida. O vínculo do destino com o orçamento será usado. '
                      'Nenhum lançamento será apagado. Confirme para excluir a categoria.'),
                fields=[field('replacement', 'Transferir para a categoria', 'Sem categoria', [c for c in categories if c != ident])])
        elif action == 'budget_mapping':
            from budgeting import GOAL_GROUPS, UNASSIGNED
            if ident not in categories:
                raise ValueError('Selecione uma categoria de despesa.')
            choices = [f'{key} · {name}' for key, name, _, _ in GOAL_GROUPS] + [f'{UNASSIGNED} · Não classificado']
            current = self.store.planner.mappings().get(ident, UNASSIGNED)
            result.update(title='Vincular categoria ao orçamento',
                note='O vínculo vale para conta, cartão e todos os meses. Não altera os lançamentos.',
                fields=[field('category', 'Categoria da transação', ident, read_only=True),
                        field('group', 'Grupo do orçamento', next(c for c in choices if c.startswith(current+' · ')), choices)])
        elif action == 'tags':
            result.update(title='Etiquetas do lançamento', fields=[field('tags', 'Etiquetas separadas por vírgula', ', '.join(self.store.transaction_tags(ident)))])
        elif action == 'split':
            row = self.transaction(ident)
            parts = self.store.splits(ident)
            result.update(title='Dividir lançamento', note=f'{row["description"]} — {currency(row["amount"])}. Informe valores positivos; a soma deve corresponder ao original.',
                categories=[c for c in categories if c != TRANSFER], splits=[dict(category=p['category'], amount=editable_money(abs(p['amount']))) for p in parts]
                or [dict(category='Sem categoria', amount=''), dict(category='Sem categoria', amount='')])
        elif action == 'new_account':
            result.update(title='Nova conta / cartão', fields=[field('name', 'Nome'), field('kind', 'Tipo', filters.kind, ['Conta corrente', 'Cartão de crédito'])])
        elif action == 'invoice':
            row = next((r for r in self.store.invoices() if f'{r["account"]}|{r["month"]}' == ident), {})
            if not row and ident:
                # Uma fatura apenas prevista ainda não existe no armazenamento.
                account_id, period = ident.split('|')
                validate_month(period)
                row = dict(account=int(account_id), month=period)
            result.update(title='Dados da fatura', fields=[account_field('Cartão de crédito', row.get('account')),
                field('month', 'Mês (AAAA-MM)', row.get('month', month)), field('due', 'Vencimento (opcional)', row.get('due', '')),
                field('state', 'Situação', row.get('state', 'Aberta'), ['Aberta', 'Fechada', 'A conferir']),
                field('total', 'Total informado (vazio = lançamentos)', editable_money(row.get('total')))])
        elif action == 'closing':
            row = next((r for r in self.store.closings() if f'{r["account"]}|{r["month"]}' == ident), {})
            result.update(title='Fechamento mensal', fields=[account_field('Conta corrente', row.get('account')),
                field('month', 'Mês (AAAA-MM)', row.get('month', month)), field('opening', 'Saldo inicial', editable_money(row.get('opening', 0))),
                field('closing', 'Saldo final informado pelo banco', editable_money(row.get('reported_closing', 0)))])
        elif action == 'budget_income':
            if not filters.month:
                raise ValueError('Escolha o mês do orçamento antes de definir a renda.')
            received = self.store.planner.report(filters.month)['income']
            result.update(title=f'Renda do orçamento · {month_title(month)}', target_month=month,
                note=(f'Receitas registradas nas contas: {currency(received)}. Esse valor é apenas para conferência. '
                      'As metas e porcentagens usam somente a renda definida abaixo, sem criar uma entrada na conta.'),
                fields=[field('income', 'Renda mensal para calcular o orçamento (R$)',
                              editable_money(self.store.planner.planning_income(month)))])
        elif action == 'budget':
            if not filters.month:
                raise ValueError('Escolha um mês para definir o orçamento.')
            row = next((r for r in self.store.budget_report(month) if r['category'] == ident), {})
            result.update(title=f'Orçamento de {month}', fields=[field('category', 'Categoria', ident or categories[0], [c for c in categories if c != TRANSFER]),
                field('amount', 'Limite em reais', editable_money(row.get('limit', 0)))])
        elif action in ('new_rule', 'edit_rule'):
            row = self.store.db.execute('SELECT * FROM rules WHERE term=?', (ident,)).fetchone()
            result.update(title='Regra de categorização', fields=[field('term', 'Texto da descrição', ident),
                field('category', 'Categoria', row['category'] if row else categories[0], categories),
                field('apply', 'Aplicar também aos sem categoria?', 'Não', ['Não', 'Sim'])])
        elif action == 'delete_forecast':
            source, period = ident.split('|')
            validate_month(period)
            row = next((r for r in self.store.forecasts(filters.account)
                        if r['transaction_id'] == int(source) and r['month'] == period), None)
            if not row:
                raise ValueError('A previsão não está mais disponível. Atualize a lista.')
            related = [r for r in self.store.forecasts(filters.account) if r['transaction_id'] == int(source)]
            result.update(title='Excluir lançamento previsto?', target_transaction=int(source), target_month=period,
                note=(f'{row["description"]}\n{row["name"]} · {row["ownership"]} · {row["holder"] or "Portador não informado"}\n'
                      f'{month_title(period)} · {currency(row["amount"])}. '
                      f'Esta origem gera {len(related)} previsões, somando {currency(sum(r["amount"] for r in related))}. '
                      'A exclusão retira os valores previstos da lista e das faturas futuras. '
                      'A compra já importada permanece no histórico.'),
                fields=[field('scope', 'O que excluir?', 'Somente a parcela deste mês',
                              ['Somente a parcela deste mês', 'Todas as previsões deste lançamento'])])
        elif action == 'installment':
            plan = self.store.installment_plan(int(ident.split('|')[0]))
            result.update(title='Ajustar parcelamento', note='Antecipação prevista para o mês seguinte à base importada. Não altera compras reais.', fields=[
                field('current', 'Parcela atual', plan['current_number']), field('total', 'Total de parcelas', plan['total_number']),
                field('anticipated', 'Parcelas a antecipar', plan['anticipated']),
                field('cancelled', 'Cancelar futuras?', 'Sim' if plan['cancelled'] else 'Não', ['Não', 'Sim'])])
        elif action == 'reconcile':
            parts = ident.split('|')
            if parts[0] != 'p':
                raise ValueError('Selecione uma sugestão não conciliada.')
            credit = self.transaction(parts[2])
            choices = ['Sem vínculo de fatura'] + [r['month'] for r in self.store.invoices(credit['account'])]
            result.update(title='Confirmar conciliação', note=f'Vincular pagamento de {currency(credit["amount"])}.', fields=[field('month', 'Fatura paga', choices[0], choices)])
        elif action == 'delete_account':
            impact = self.store.account_impact(int(ident))
            result.update(title='Excluir conta / cartão?', note=f'{impact["name"]}: {impact["transactions"]} lançamentos, {impact["batches"]} importações e {impact["invoices"]} faturas. Os vínculos serão desfeitos. Exclusão sem desfazer; recuperação exige backup ou reimportação.')
        elif action == 'undo':
            batch = self.store.db.execute('SELECT filename FROM batches ORDER BY id DESC LIMIT 1').fetchone()
            if not batch:
                raise ValueError('Não há importações para desfazer.')
            result.update(title='Desfazer última importação?', note=f'Remover os lançamentos do arquivo {batch[0]}. O arquivo original não será apagado.')
        elif action in ('clear_split', 'delete_budget', 'delete_rule', 'unreconcile', 'reset_invoice'):
            result.update(title='Confirmar alteração', note={'clear_split': 'Remover a divisão e usar a categoria original?',
                'delete_budget': f'Remover limite de {ident} em {month}?', 'delete_rule': f'Excluir a regra {ident}?',
                'unreconcile': 'Desfazer o vínculo e restaurar as categorias anteriores?', 'reset_invoice': 'Remover dados informados manualmente e voltar aos dados do extrato?'}[action])
        else:
            raise ValueError('Ação não reconhecida.')
        return result

    def submit(self, form: dict, values: dict, filters: Filters) -> None:
        """Valida entradas do formulário antes de chamar uma operação de domínio."""
        from core import money
        action, selected = form['action'], form['selected']
        ident = selected[0] if selected else ''
        def account() -> int:
            """Extrai a identidade estável do rótulo selecionado, nunca do índice."""
            return int(values['account'].split(' · ')[0])
        def tags() -> list[str]:
            """Valida etiquetas antes de gravar o lançamento para evitar gravação parcial."""
            names = [' '.join(s.split()) for s in values.get('tags', '').split(',') if s.strip()]
            if any(len(s) > 40 for s in names):
                raise ValueError('Cada etiqueta pode ter até 40 caracteres.')
            return names
        if action in ('new_transaction', 'edit_transaction'):
            labels = tags()
            target = self.store.edit_transaction(int(ident) if ident else None, account(), values['date'], values['description'],
                money(values['amount']), self.transaction(ident)['category'] if ident else 'Sem categoria', values['month'],
                '' if values['ownership'] == 'Não informado' else values['ownership'], values['holder'], values['card'])
            self.store.set_transaction_tags(target, labels)
        elif action in ('new_category', 'edit_category'):
            self.store.save_category(values['name'], ident or None)
        elif action == 'delete_category':
            self.store.delete_category(ident, values['replacement'])
        elif action == 'budget_mapping':
            self.store.planner.set_mapping(ident, values['group'].split(' · ')[0])
        elif action == 'tags':
            self.store.set_transaction_tags(int(ident), tags())
        elif action == 'categorize':
            if any(self.store.splits(int(i)) for i in selected):
                raise ValueError('Edite ou remova a divisão antes de categorizar esses lançamentos.')
            self.store.categorize([int(i) for i in selected], values['category'], values.get('term', ''))
        elif action == 'split':
            row = self.transaction(ident)
            if row['category'] == TRANSFER:
                raise ValueError('Pagamentos e transferências não devem ser divididos em despesas.')
            sign = -1 if row['amount'] < 0 else 1
            parts = []
            for part in values['splits']:
                amount = money(part['amount'])
                if amount <= 0:
                    raise ValueError('Informe um valor positivo para cada parte.')
                parts.append((part['category'], amount * sign))
            self.store.set_splits(int(ident), parts)
        elif action == 'clear_split':
            self.store.clear_splits(int(ident))
        elif action == 'new_account':
            if not values['name'].strip() or values['kind'] not in ('Conta corrente', 'Cartão de crédito'):
                raise ValueError('Informe um nome e um tipo de conta válido.')
            self.store.add_account(values['name'], values['kind'])
        elif action == 'delete_account':
            self.store.delete_account(int(ident))
        elif action == 'invoice':
            self.store.set_invoice(account(), values['month'], values['due'], values['state'], money(values['total']) if values['total'] else None)
        elif action == 'reset_invoice':
            account_id, month = ident.split('|')
            with self.store.db:
                self.store.db.execute('DELETE FROM invoice_overrides WHERE account=? AND month=?', (int(account_id), month))
        elif action == 'closing':
            self.store.set_closing(account(), values['month'], money(values['opening']), money(values['closing']))
        elif action == 'budget_income':
            self.store.planner.set_planning_income(form['target_month'], money(values['income']))
        elif action == 'budget':
            self.store.set_budget(filters.month, values['category'], money(values['amount']))
        elif action == 'delete_budget':
            validate_month(filters.month)
            self.store.delete_budget(filters.month, ident)
        elif action in ('new_rule', 'edit_rule'):
            self.store.save_rule(ident, values['term'], values['category'], values['apply'] == 'Sim')
        elif action == 'delete_rule':
            self.store.delete_rule(ident)
        elif action == 'delete_forecast':
            scope = values.get('scope')
            if scope not in ('Somente a parcela deste mês', 'Todas as previsões deste lançamento'):
                raise ValueError('Escolha o alcance da exclusão.')
            self.store.exclude_forecast(form['target_transaction'], form['target_month'],
                                        scope == 'Todas as previsões deste lançamento')
        elif action == 'installment':
            self.store.set_installment_plan(int(ident.split('|')[0]), int(values['current']), int(values['total']), int(values['anticipated']), values['cancelled'] == 'Sim')
        elif action == 'reconcile':
            _, debit, credit = ident.split('|')
            self.store.reconcile(int(debit), int(credit), '' if values['month'] == 'Sem vínculo de fatura' else values['month'])
        elif action == 'unreconcile':
            if not ident.startswith('r|'):
                raise ValueError('Selecione um pagamento conciliado.')
            self.store.unreconcile(int(ident.split('|')[1]))
        elif action == 'undo':
            self.store.undo()
        else:
            raise ValueError('Ação não reconhecida.')
