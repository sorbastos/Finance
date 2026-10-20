"""Renda automática e metas por grupo sem contar pagamentos duas vezes."""
import tempfile
import unittest
from pathlib import Path

from budgeting import GOAL_GROUPS
from finance import TRANSFER
from finance_desktop.service import FinanceService, Filters


class BudgetPlannerTests(unittest.TestCase):
    """Cada cenário utiliza somente lançamentos fictícios e SQLite temporário."""

    def setUp(self) -> None:
        """Prepara uma conta e um cartão com o mesmo domínio usado pelo desktop."""
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'budget.sqlite3'
        self.service = FinanceService(self.path)
        self.store = self.service.store
        self.planner = self.store.planner

    def tearDown(self) -> None:
        """Fecha a conexão antes de eliminar o diretório isolado."""
        self.service.close()
        self.temp.cleanup()

    def add(self, amount: int, category: str, account: int = 1,
            month: str = '2026-10', ownership: str = '') -> int:
        """Insere um lançamento manual sintético na competência escolhida."""
        return self.store.edit_transaction(None, account, month+'-05', 'Exemplo', amount, category,
                                           month if account == 2 else '', ownership)

    def test_income_expenses_refunds_and_no_double_counting(self) -> None:
        """Conta forma renda; cartão forma gasto líquido; transferências são excluídas."""
        self.add(100000, 'Sem categoria')
        self.add(-10000, 'Custos fixos')
        self.add(-20000, 'Prazeres', 2)
        self.add(5000, 'Prazeres', 2)
        self.add(-15000, TRANSFER)
        self.add(15000, TRANSFER, 2)
        self.add(30000, TRANSFER)
        self.planner.set_planning_income('2026-10', 100000)
        report = self.planner.report('2026-10')
        self.assertEqual((report['income'], report['spent'], report['remaining']), (100000, 25000, 75000))
        self.assertEqual((report['cash'], report['card']), (10000, 15000))
        self.assertEqual(sum(g['spent'] for g in report['groups']), 25000)
        self.store.set_budget('2026-10', 'Prazeres', 20000)
        self.assertEqual(self.store.budget_report('2026-10')[0]['spent'], 15000)

    def test_card_competence_and_no_forecast_as_expense(self) -> None:
        """Data da compra pode ser antiga; o cartão usa o mês da fatura."""
        self.store.edit_transaction(None, 2, '2026-08-01', 'Loja · Parcela 2 de 4', -10000,
                                    'Conforto', '2026-10', 'Adicional')
        self.assertEqual(self.planner.report('2026-08')['spent'], 0)
        self.assertEqual(self.planner.report('2026-10')['spent'], 10000)
        self.assertTrue(self.store.forecasts())
        self.assertEqual(self.planner.report('2026-11')['spent'], 0)

    def test_split_and_mapping_category_rename(self) -> None:
        """Divisões alimentam os grupos e vínculos acompanham categorias renomeadas."""
        ident = self.add(-10000, 'Conforto')
        self.store.set_splits(ident, [('Custos fixos', -7000), ('Conhecimento', -3000)])
        groups = {g['id']: g['spent'] for g in self.planner.report('2026-10')['groups']}
        self.assertEqual((groups['fixed'], groups['knowledge']), (7000, 3000))
        self.assertEqual(self.planner.mappings()['Custos fixos'], 'fixed')
        self.assertEqual(self.planner.mappings()['Conhecimento'], 'knowledge')

    def test_unmapped_category_visible_and_assignable(self) -> None:
        """Despesa sem grupo não some do orçamento."""
        ident = self.add(-9000, 'Sem categoria')
        self.assertEqual(self.planner.report('2026-10')['unassigned'], 9000)
        self.assertEqual(self.planner.report('2026-10')['spent'], 0)
        self.store.categorize([r['id'] for r in self.store.transactions() if r['category']=='Sem categoria' and (r['amount']<0 or r['kind']=='Cartão de crédito')], 'Metas')
        report = self.planner.report('2026-10')
        self.assertEqual(report['unassigned'], 0)
        self.assertEqual(next(g['spent'] for g in report['groups'] if g['id']=='plans'), 9000)
        self.store.categorize([ident], 'Sem categoria')
        self.assertEqual(self.planner.report('2026-10')['spent'], 0)

    def test_unassigned_excluded_from_totals_percentages_and_chart(self) -> None:
        """Pendências seguem visíveis para classificar, sem consumir a renda planejada."""
        self.planner.set_planning_income('2026-10', 100000)
        self.add(200000, 'Sem categoria')
        self.add(-30000, 'Custos fixos')
        self.add(-10000, 'Prazeres', 2)
        self.add(-10000, 'Sem categoria')
        self.add(-20000, 'Sem categoria', 2)
        self.add(5000, 'Sem categoria', 2)
        report = self.service.household_budget('2026-10')
        self.assertEqual((report['cash'], report['card'], report['spent'], report['remaining']), (30000, 10000, 40000, 60000))
        self.assertEqual(report['income'], 200000)
        self.assertEqual(report['utilization'], '40,0%')
        self.assertNotIn('unassigned', [g['id'] for g in report['groups']])
        self.assertNotIn('Não classificado', [g['label'] for g in report['spendingChart']])
        pending = next(a for a in report['assignments'] if a['category']=='Não classificado')
        self.assertEqual(pending['spent'], 25000)
        self.assertIn('unassigned', [g['id'] for g in report['categoryGroups']])
        self.store.categorize([r['id'] for r in self.store.transactions() if r['category']=='Sem categoria' and (r['amount']<0 or r['kind']=='Cartão de crédito')], 'Metas')
        self.assertEqual(self.service.household_budget('2026-10')['spent'], 65000)

    def test_split_only_counts_parts_with_assigned_group(self) -> None:
        """Uma compra dividida pode ter somente parte incluída no orçamento."""
        ident = self.add(-10000, 'Conforto')
        self.store.set_splits(ident, [('Custos fixos', -4000), ('Sem categoria', -6000)])
        report = self.planner.report('2026-10')
        self.assertEqual(report['spent'], 4000)
        self.assertEqual(report['unassigned'], 6000)

    def test_planned_cents_sum_exactly_to_income(self) -> None:
        """Renda com centavos indivisíveis não cria nem perde dinheiro nas metas."""
        self.add(101, 'Sem categoria')
        self.planner.set_planning_income('2026-10', 101)
        groups = self.planner.report('2026-10')['groups']
        self.assertEqual(sum(g['planned'] for g in groups), 101)
        self.assertTrue(all(type(g['planned']) is int for g in groups))
        self.assertEqual(next(g['planned'] for g in groups if g['id']=='reserve'), 0)

    def test_goals_inheritance_history_and_persistence(self) -> None:
        """Metas novas valem a partir do mês salvo; meses anteriores ficam intactos."""
        values = {key: percent for key, _, percent, _ in GOAL_GROUPS}
        values.update(fixed=40, comfort=5)
        self.planner.set_goals('2026-10', values)
        self.assertEqual(self.planner.goals('2026-09')[0]['fixed'], 30)
        self.assertEqual(self.planner.goals('2026-11')[0]['fixed'], 40)
        self.service.close()
        self.service = FinanceService(self.path)
        self.store = self.service.store
        self.planner = self.store.planner
        self.assertEqual(self.planner.goals('2026-11'), (values, '2026-10'))
        self.assertEqual(self.planner.mappings()['Custos fixos'], 'fixed')

    def test_invalid_goals_are_atomic(self) -> None:
        """Totais diferentes de 100, números fracionários e conjuntos incompletos são rejeitados."""
        valid = {key: percent for key, _, percent, _ in GOAL_GROUPS}
        self.planner.set_goals('2026-10', valid)
        for values in ({}, dict(valid, fixed=31), dict(valid, fixed=30.0), dict(valid, reserve=-1)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.planner.set_goals('2026-10', values)
        self.assertEqual(self.planner.goals('2026-10')[0], valid)

    def test_service_ignores_other_page_filters_and_lists_both_periods(self) -> None:
        """Orçamento é global mesmo após consultar apenas um cartão ou portador."""
        self.add(50000, 'Sem categoria')
        self.add(-5000, 'Custos fixos')
        self.add(-2000, 'Prazeres', 2, ownership='Adicional')
        self.add(-1000, 'Conforto', 2, month='2026-12', ownership='Titular')
        state = self.service.snapshot('budgets', Filters('Cartão de crédito', 2, '2026-10', 'Titular', 'Nada'))
        self.assertEqual(state['budgetData']['incomeLabel'], 'R$ 500,00')
        self.assertEqual(state['budgetData']['spentLabel'], 'R$ 70,00')
        self.assertIn('2026-12', state['months'])
        self.assertNotIn('Todos os meses', state['months'])

    def test_empty_income_and_refunds_above_expenses(self) -> None:
        """Sem renda não há divisão por zero; crédito líquido permanece explícito."""
        self.add(2000, 'Conforto', 2)
        report = self.service.household_budget('2026-10')
        self.assertEqual((report['spent'], report['remaining']), (-2000, 2000))
        self.assertEqual(report['utilization'], '—')
        self.assertEqual(report['spendingChart'], [])
        self.assertTrue(all(g['planned']==0 for g in report['groups']))

    def test_manual_income_is_only_base_and_bank_receipts_remain_separate(self) -> None:
        """Metas e percentuais não seguem os recebimentos automáticos da conta."""
        self.add(500000, 'Sem categoria')
        self.add(-10000, 'Custos fixos')
        self.planner.set_planning_income('2026-10', 200000)
        report = self.service.household_budget('2026-10')
        self.assertEqual((report['income'], report['planning_income'], report['remaining']), (500000, 200000, 190000))
        self.assertEqual(report['utilization'], '5,0%')
        self.assertEqual(sum(g['planned'] for g in report['groups']), 200000)
        fixed = next(g for g in report['groups'] if g['id']=='fixed')
        self.assertEqual(fixed['planned'], 60000)
        self.add(100000, 'Sem categoria')
        updated = self.planner.report('2026-10')
        self.assertEqual(updated['income'], 600000)
        self.assertEqual(updated['planning_income'], 200000)
        self.assertEqual(sum(g['planned'] for g in updated['groups']), 200000)

    def test_unconfigured_month_does_not_use_receipts_or_inherit_manual_income(self) -> None:
        """Sem definição explícita, renda planejada e metas monetárias ficam em zero."""
        self.add(500000, 'Sem categoria', month='2026-11')
        self.planner.set_planning_income('2026-10', 200000)
        report = self.planner.report('2026-11')
        self.assertEqual(report['income'], 500000)
        self.assertEqual(report['planning_income'], 0)
        self.assertFalse(report['income_configured'])
        self.assertEqual(sum(g['planned'] for g in report['groups']), 0)

    def test_manual_income_persists_and_invalid_value_does_not_replace_it(self) -> None:
        """Valor salvo é mensal e não cria transação fictícia para representar renda."""
        self.planner.set_planning_income('2026-10', 123456)
        for value in (-1, 1.5, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.planner.set_planning_income('2026-10', value)
        self.assertEqual(self.store.transactions(), [])
        self.service.close()
        self.service = FinanceService(self.path)
        self.store = self.service.store
        self.planner = self.store.planner
        self.assertEqual(self.planner.planning_income('2026-10'), 123456)

    def test_income_form_saves_frozen_month_not_bank_receipt(self) -> None:
        """A confirmação altera só a renda planejada da competência revisada."""
        self.add(500000, 'Sem categoria')
        filters = Filters(month='2026-10')
        form = self.service.form('budget_income', [], filters)
        self.assertIn('R$ 5.000,00', form['note'])
        filters.month = '2026-11'
        self.service.submit(form, {'income':'2.500,25'}, filters)
        self.assertEqual(self.planner.planning_income('2026-10'), 250025)
        self.assertIsNone(self.planner.planning_income('2026-11'))
        self.assertEqual(len(self.store.transactions()), 1)

    def test_classification_uses_goal_category_directly(self) -> None:
        """O gasto entra diretamente na meta escolhida, sem outra associação."""
        ident = self.add(-2000, 'Custos fixos')
        self.store.categorize([ident], 'Metas')
        self.assertEqual(self.service.transaction(str(ident))['category'], 'Metas')
        self.assertEqual(next(g['spent'] for g in self.planner.report('2026-10')['groups'] if g['id']=='plans'), 2000)
        self.planner.set_mapping('Metas', 'comfort')
        self.assertEqual(next(g['spent'] for g in self.planner.report('2026-10')['groups'] if g['id']=='comfort'), 2000)


if __name__ == '__main__':
    unittest.main()
