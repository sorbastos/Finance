"""Contratos financeiros da nova apresentação, usando apenas dados sintéticos."""
import tempfile
import unittest
from pathlib import Path

from finance_desktop.catalog import PAGES
from finance_desktop.formatting import currency
from finance_desktop.importing import ImportSession
from finance_desktop.service import FinanceService, Filters
from test_xlsx import fixture


class DesktopServiceTests(unittest.TestCase):
    """Exercita casos de uso reais sem depender de widgets ou banco pessoal."""

    def setUp(self) -> None:
        """Cada teste recebe um banco independente e duas contas iniciais."""
        self.temp = tempfile.TemporaryDirectory()
        self.service = FinanceService(Path(self.temp.name) / 'finance.sqlite3')
        self.filters = Filters(month='2026-09')

    def tearDown(self) -> None:
        """Fecha o SQLite antes de remover a pasta temporária."""
        self.service.close()
        self.temp.cleanup()

    def submit(self, action: str, values: dict, selected: list | None = None) -> None:
        """Usa o mesmo contrato de abertura/confirmacão utilizado pelo desktop."""
        form = self.service.form(action, selected or [], self.filters)
        self.service.submit(form, values, self.filters)

    def purchase(self, account: int = 1, owner: str = '', value: int = -10000) -> int:
        """Inclui um lançamento manual fictício na competência controlada."""
        return self.service.store.edit_transaction(None, account, '2026-09-03', 'Compra exemplo', value,
            'Custos fixos', '2026-09' if account == 2 else '', owner)

    def test_all_pages_with_data(self) -> None:
        """Todas as consultas precisam aceitar uma base populada, não só vazia."""
        self.purchase(); self.purchase(2, 'Adicional')
        for page in PAGES:
            with self.subTest(page=page['id']):
                snapshot = self.service.snapshot(page['id'], self.filters)
                self.assertIn('rows', snapshot)
                self.assertTrue(snapshot['title'])

    def test_custom_categories_and_budget_link(self) -> None:
        """Categoria compartilhada muda o grupo calculado sem alterar valores."""
        self.submit('new_category', {'name':'Pets'}, ['Mercado'])
        self.assertIn('Mercado', self.service.store.categories())
        self.submit('edit_category', {'name':'Animais'}, ['Pets'])
        ids = [self.purchase(), self.purchase(2, 'Adicional', -2000)]
        self.submit('categorize', {'category':'Animais'}, [str(i) for i in ids])
        self.submit('budget_mapping', {'group':'plans · Metas'}, ['Animais'])
        report = self.service.household_budget('2026-09')
        self.assertEqual(next(g['spent'] for g in report['groups'] if g['id']=='plans'), 12000)
        self.submit('edit_category', {'name':'Cuidados animais'}, ['Animais'])
        self.assertEqual(self.service.store.planner.mappings()['Cuidados animais'], 'plans')

    def test_filters_and_comparison_do_not_mix_accounts(self) -> None:
        """Compara só o tipo selecionado e distingue portador desconhecido."""
        self.purchase(); self.purchase(2, 'Adicional', -20000); self.purchase(2, '', -3000)
        snapshot = self.service.snapshot('comparison', self.filters)
        self.assertEqual(snapshot['rows'][0]['cells'][2], currency(10000))
        self.filters.kind, self.filters.ownership = 'Cartão de crédito', 'Não informado'
        self.assertEqual(len(self.service.transactions(self.filters)), 1)
        snapshot = self.service.snapshot('comparison', self.filters)
        self.assertEqual(snapshot['rows'][0]['cells'][2], currency(3000))

    def test_split_tags_and_budget(self) -> None:
        """Divisão reflete no orçamento e etiquetas sobrevivem ao fechamento."""
        ident = str(self.purchase())
        self.submit('split', {'splits': [{'category': 'Custos fixos', 'amount': '70,00'}, {'category': 'Reserva de emergência', 'amount': '30,00'}]}, [ident])
        self.submit('budget', {'category': 'Reserva de emergência', 'amount': '50,00'})
        self.submit('tags', {'tags': 'Reembolso, Viagem'}, [ident])
        report = self.service.snapshot('budgets', self.filters)
        self.assertEqual(report['headers'], [])
        self.assertEqual(report['actions'], [])
        health = next(r for r in report['budgetData']['assignments'] if r['category'] == 'Reserva de emergência')
        self.assertEqual(health['spentLabel'], 'R$ 30,00')
        self.assertEqual(self.service.store.transaction_tags(ident), ['Reembolso', 'Viagem'])
        with self.assertRaises(ValueError):
            self.submit('split', {'splits': [{'category': 'Reserva de emergência', 'amount': '1,00'}]}, [ident])
        self.assertEqual(len(self.service.store.splits(ident)), 2)

    def test_forecast_month_and_owner(self) -> None:
        """Previsões exibem somente a competência escolhida, juntas ou separadas."""
        for owner in ('Titular', 'Adicional'):
            self.service.store.edit_transaction(None, 2, '2026-08-01', 'Loja · Parcela 2 de 4', -10000,
                'Conforto', '2026-09', owner, owner, '****0001' if owner == 'Titular' else '****0002')
        self.filters = Filters('Cartão de crédito', month='2026-10')
        both = self.service.snapshot('forecasts', self.filters)
        self.assertEqual(len(both['rows']), 2)
        self.assertEqual(both['metrics'][-1]['value'], 'R$ 200,00')
        self.filters.ownership = 'Adicional'
        self.assertEqual(len(self.service.snapshot('forecasts', self.filters)['rows']), 1)
        self.filters.month = '2026-12'
        self.assertEqual(self.service.snapshot('forecasts', self.filters)['rows'], [])

    def test_forecast_keeps_monthly_totals_while_filtering_owner(self) -> None:
        """O recorte de portador muda a lista sem apagar a comparação mensal."""
        for owner, amount in [('Titular', -10000), ('Adicional', -7000), ('', -3000)]:
            self.service.store.edit_transaction(None, 2, '2026-08-01', f'Compra {owner} · Parcela 2 de 4',
                amount, 'Conforto', '2026-09', owner)
        self.filters = Filters('Cartão de crédito', 2, '2026-10', 'Adicional')
        snapshot = self.service.snapshot('forecasts', self.filters)
        self.assertEqual([m['value'] for m in snapshot['metrics']], ['R$ 100,00', 'R$ 70,00', 'R$ 30,00', 'R$ 200,00'])
        self.assertEqual(len(snapshot['rows']), 1)
        self.assertIn('Outubro de 2026 · Adicional · 1 previsão · R$ 70,00', snapshot['forecastCaption'])
        self.assertEqual([o['count'] for o in snapshot['ownerOptions']], [3, 1, 1, 1])
        self.filters.month = '2027-01'
        empty = self.service.snapshot('forecasts', self.filters)
        self.assertIn('2027-01', [m['value'] for m in empty['forecastMonths']])
        self.assertEqual(empty['rows'], [])

    def test_future_invoices_combine_holders_without_writing(self) -> None:
        """Parcelas futuras viram uma fatura estimada por cartão e competência."""
        for owner, amount in [('Titular', -10000), ('Adicional', -7000)]:
            self.service.store.edit_transaction(None, 2, '2026-08-01', f'Compra {owner} · Parcela 2 de 4',
                amount, 'Conforto', '2026-09', owner)
        before = len(self.service.store.transactions())
        projections = self.service.invoice_projection(2)
        october = next(r for r in projections if r['month'] == '2026-10')
        self.assertEqual((october['state'], october['titular'], october['adicional'], october['estimate']),
                         ('Prevista', 10000, 7000, 17000))
        self.assertIsNone(october['total'])
        self.assertIsNone(october['remaining'])
        self.assertEqual(len(self.service.store.transactions()), before)
        self.assertNotIn('2026-10', [r['month'] for r in self.service.store.invoices(2)])
        self.filters = Filters('Cartão de crédito', 2, '2026-10', 'Titular')
        rows = self.service.snapshot('invoices', self.filters)['rows']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['cells'][3], 'R$ 170,00')
        form = self.service.form('invoice', ['2|2026-10'], self.filters)
        values = {f['key']: f['value'] for f in form['fields']}
        self.assertEqual(values['month'], '2026-10')
        self.assertTrue(values['account'].startswith('2 · '))

    def test_invoice_estimate_does_not_add_reported_total_twice(self) -> None:
        """Total informado fica separado da soma de lançamentos e projeções."""
        self.service.store.edit_transaction(None, 2, '2026-08-01', 'Loja · Parcela 2 de 4',
            -10000, 'Conforto', '2026-09', 'Adicional')
        self.service.store.edit_transaction(None, 2, '2026-10-01', 'Compra avulsa',
            -5000, 'Conforto', '2026-10', 'Titular')
        self.service.store.set_invoice(2, '2026-10', '', 'Aberta', 15000)
        october = next(r for r in self.service.invoice_projection(2) if r['month'] == '2026-10')
        self.assertEqual((october['calculated'], october['projected'], october['estimate'], october['total']),
                         (5000, 10000, 15000, 15000))

    def test_manual_forecast_deletion_updates_future_invoices(self) -> None:
        """Exclusão confirmada atualiza tabela, totais e faturas sem apagar compras."""
        self.service.store.edit_transaction(None, 2, '2026-08-01', 'Compra · Parcela 2 de 4',
            -10000, 'Conforto', '2026-09', 'Adicional')
        self.filters = Filters('Cartão de crédito', 2, '2026-10')
        snapshot = self.service.snapshot('forecasts', self.filters)
        selected = snapshot['rows'][0]['id']
        form = self.service.form('delete_forecast', [selected], self.filters)
        self.assertIn('R$ 100,00', form['note'])
        self.assertEqual(len(self.service.store.forecasts()), 2)
        self.service.submit(form, {'scope': 'Somente a parcela deste mês'}, self.filters)
        self.assertEqual(self.service.snapshot('forecasts', self.filters)['rows'], [])
        self.assertEqual(self.service.snapshot('invoices', self.filters)['rows'], [])
        self.assertEqual(self.service.snapshot('forecasts', self.filters)['metrics'][-1]['value'], 'R$ 0,00')
        self.assertEqual(len(self.service.store.transactions()), 1)
        self.assertEqual([r['month'] for r in self.service.store.forecasts()], ['2026-11'])

    def test_forecast_deletion_requires_selection_and_valid_scope(self) -> None:
        """Impede exclusões com seleção vazia, múltipla ou alcance desconhecido."""
        with self.assertRaises(ValueError):
            self.service.form('delete_forecast', [], self.filters)
        with self.assertRaises(ValueError):
            self.service.form('delete_forecast', ['1|2026-10', '2|2026-10'], self.filters)
        with self.assertRaises(ValueError):
            self.service.submit({'action': 'delete_forecast', 'selected': []}, {'scope': 'Inválido'}, self.filters)

    def test_import_preview_then_confirmation_and_duplicate(self) -> None:
        """Prévia é somente leitura; OFX, CSV e XLSX chegam ao mesmo SQLite."""
        examples = [('extrato.ofx', b'<STMTTRN><DTPOSTED>20260901<TRNAMT>-12.00<FITID>sample<NAME>Loja</STMTTRN>'),
                    ('extrato.csv', b'data;descricao;valor;id\n02/09/2026;Padaria;-5,00;csv1\n'),
                    ('fatura.xlsx', fixture(state='Paga', month='Setembro'))]
        for filename, raw in examples:
            path = Path(self.temp.name) / filename
            path.write_bytes(raw)
            session = ImportSession(path, self.service)
            values = {f['key']: f['value'] for f in session.form()['fields']}
            before = len(self.service.store.transactions())
            preview = session.prepare(values)
            self.assertGreater(len(preview['rows']), 0)
            self.assertEqual(len(self.service.store.transactions()), before)
            self.assertGreater(session.save(False), 0)
            duplicate = ImportSession(path, self.service)
            duplicate.prepare(values)
            with self.assertRaisesRegex(ValueError, 'já foi importado'):
                duplicate.save(False)
            self.assertEqual(len(self.service.store.transactions()), before + len(preview['rows']))

    def test_invalid_import_does_not_save(self) -> None:
        """Uma linha inválida não deixa parte do CSV no banco."""
        path = Path(self.temp.name) / 'invalid.csv'
        path.write_text('data;descricao;valor\n01/09/2026;A;-10\ninvalid;B;-20\n')
        session = ImportSession(path, self.service)
        values = {f['key']: f['value'] for f in session.form()['fields']}
        with self.assertRaises(ValueError):
            session.prepare(values)
        self.assertEqual(self.service.store.transactions(), [])

    def test_account_deletion_preserves_other_data(self) -> None:
        """A confirmação descreve o impacto e só a conta selecionada é removida."""
        self.purchase(); self.purchase(2, 'Titular')
        form = self.service.form('delete_account', ['1'], self.filters)
        self.assertIn('1 lançamentos', form['note'])
        self.service.submit(form, {}, self.filters)
        self.assertEqual([r['account'] for r in self.service.store.transactions()], [2])

    def test_new_transaction_with_selection_creates_and_validates_first(self) -> None:
        """Etiquetas inválidas são rejeitadas antes de inserir o lançamento."""
        original = str(self.purchase())
        form = self.service.form('new_transaction', [original], self.filters)
        values = {f['key']: f['value'] for f in form['fields']}
        values.update(description='Novo exemplo', amount='-12,34', tags='x' * 41)
        with self.assertRaises(ValueError):
            self.service.submit(form, values, self.filters)
        self.assertEqual(len(self.service.store.transactions()), 1)
        values['tags'] = 'Teste'
        self.service.submit(form, values, self.filters)
        self.assertEqual(len(self.service.store.transactions()), 2)
        self.assertEqual(self.service.transaction(original)['description'], 'Compra exemplo')

    def test_closing_invoice_rule_and_reconciliation_forms(self) -> None:
        """Fluxos de conferência usam centavos e preservam o vínculo de pagamento."""
        self.purchase()
        self.submit('closing', {'account': '1 · Conta', 'month': '2026-09', 'opening': '200,00', 'closing': '100,00'})
        self.assertEqual(self.service.store.closings()[0]['difference'], 0)
        self.submit('invoice', {'account': '2 · Cartão', 'month': '2026-09', 'due': '10/09/2026', 'state': 'Fechada', 'total': '100,00'})
        self.assertEqual(self.service.store.invoices()[0]['total'], 10000)
        self.submit('new_rule', {'term': 'loja', 'category': 'Conforto', 'apply': 'Sim'})
        self.submit('edit_rule', {'term': 'mercado', 'category': 'Custos fixos', 'apply': 'Não'}, ['loja'])
        self.assertEqual(self.service.store.category('Mercado Exemplo'), 'Custos fixos')
        from finance import TRANSFER
        debit = self.service.store.edit_transaction(None, 1, '2026-09-10', 'FATURA PAGA', -10000, TRANSFER)
        credit = self.service.store.edit_transaction(None, 2, '2026-09-11', 'Pagamento Com Saldo', 10000, TRANSFER, '2026-09')
        self.submit('reconcile', {'month': '2026-09'}, [f'p|{debit}|{credit}'])
        self.assertEqual(self.service.store.invoices()[0]['remaining'], 0)
        link = self.service.store.reconciled()[0]['id']
        self.submit('unreconcile', {}, [f'r|{link}'])
        self.assertEqual(self.service.store.invoices()[0]['remaining'], 10000)

    def test_chart_grouping_keeps_total(self) -> None:
        """Agrupar categorias menores mantém os valores e o percentual do total."""
        for index in range(8):
            category = f'Categoria {index}'
            self.service.store.save_category(category)
            self.service.store.edit_transaction(None, 1, '2026-09-01', f'Loja {index}', -100, category)
        data = self.service.snapshot('accounts', self.filters)['charts'][0]
        self.assertEqual(len(data), 6)
        self.assertEqual(sum(point['value'] for point in data), 800)

    def test_category_chart_uses_splits_and_percentages_on_account_and_card(self) -> None:
        """Valor e percentual usam saídas do recorte, respeitando as categorias dos rateios."""
        for account, kind, page in ((1, 'Conta corrente', 'accounts'), (2, 'Cartão de crédito', 'cards')):
            ident = self.purchase(account)
            self.service.store.set_splits(ident, [('Mercado', -7000), ('Educação', -3000)])
            self.purchase(account, value=1000)
            state = self.service.snapshot(page, Filters(kind=kind, month='2026-09', account=account))
            points = {p['label']: p for p in state['charts'][0]}
            self.assertEqual(set(points), {'Mercado', 'Educação'})
            self.assertEqual(points['Mercado']['value'], 7000)
            self.assertEqual(points['Mercado']['formatted'], 'R$ 70,00 · 70,0%')
            self.assertEqual(points['Educação']['formatted'], 'R$ 30,00 · 30,0%')
            self.assertEqual(sum(p['value'] for p in points.values()), 10000)
        self.assertEqual(self.service.snapshot('accounts', self.filters)['chartTitles'][1], 'Saídas por dia')

    def test_shared_period_and_owner_menu_contract(self) -> None:
        """Contagens ignoram o portador selecionado e mantêm meses sem movimentos."""
        self.purchase(2, 'Titular')
        self.purchase(2, 'Adicional')
        self.purchase(2, '')
        filters = Filters(kind='Cartão de crédito', month='2026-09', ownership='Titular')
        for page in ('cards', 'transactions', 'comparison', 'budget_transactions'):
            state = self.service.snapshot(page, filters)
            self.assertEqual([o['count'] for o in state['ownerOptions']], [3, 1, 1, 1])
            self.assertEqual([o['value'] for o in state['ownerOptions']], ['', 'Titular', 'Adicional', 'Não informado'])
        filters.month = '2028-02'
        for page in ('accounts', 'cards', 'transactions', 'invoices', 'closings', 'comparison', 'budget_transactions', 'budgets'):
            state = self.service.snapshot(page, filters)
            self.assertIn('2028-02', [m['value'] for m in state['periodOptions']])
        self.assertNotIn('ownerOptions', self.service.snapshot('budgets', filters))

    def test_transaction_categories_are_shared_with_budget(self) -> None:
        """Classificar na lista altera o mesmo gasto usado nos totais do orçamento."""
        ident = self.purchase()
        for page in ('accounts', 'cards'):
            state = self.service.snapshot(page, self.filters)
            self.assertNotIn('Categoria', state['headers'])
            self.assertNotIn('categorize', [a['id'] for a in state['actions']])
            self.assertEqual(state['chartTitles'][0], 'Despesas por categoria')
            self.assertTrue(all(len(r['cells']) == len(state['headers']) for r in state['rows']))
        form = self.service.form('edit_transaction', [str(ident)], self.filters)
        self.assertNotIn('category', [f['key'] for f in form['fields']])
        values = {f['key']: f['value'] for f in form['fields']}
        values['description'] = 'Nome editado'
        self.service.submit(form, values, self.filters)
        self.assertEqual(self.service.transaction(str(ident))['category'], 'Custos fixos')
        transactions = self.service.snapshot('transactions', self.filters)
        self.assertIn('Categoria', transactions['headers'])
        self.assertIn('categorize', [a['id'] for a in transactions['actions']])
        self.assertTrue(all(len(r['cells']) == len(transactions['headers']) for r in transactions['rows']))
        budget = self.service.snapshot('budget_transactions', self.filters)
        self.assertIn('Categoria', budget['headers'])
        self.assertIn('categorize', [a['id'] for a in budget['actions']])
        self.submit('categorize', {'category': 'Reserva de emergência'}, [str(ident)])
        self.assertEqual(self.service.transaction(str(ident))['category'], 'Reserva de emergência')
        report = self.service.snapshot('budgets', self.filters)['budgetData']
        self.assertEqual(next(g['spent'] for g in report['groups'] if g['id']=='reserve'), 10000)
        self.assertEqual(next(g['spent'] for g in report['groups'] if g['id']=='fixed'), 0)
        self.assertTrue(all(p.get('budgetOnly') for p in PAGES if p['id'] in ('rules','budget_transactions')))
        self.assertFalse(next(p for p in PAGES if p['id']=='categories').get('budgetOnly', False))


if __name__ == '__main__':
    unittest.main()
