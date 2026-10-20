import unittest
import test_finance
from finance import FinanceStore, TRANSFER

class CategoryTests(unittest.TestCase):
    setUp = test_finance.FinanceTests.setUp
    tearDown = test_finance.FinanceTests.tearDown

    def test_fixed_categories_and_reopen(self):
        """Somente as sete metas e os marcadores internos existem no catálogo."""
        from budgeting import GOAL_GROUPS
        from core import CATEGORIES
        expected = {name for _, name, _, _ in GOAL_GROUPS} | set(CATEGORIES)
        self.assertEqual(set(self.store.categories()), expected)
        self.store.edit_transaction(None, 1, '2026-09-01', 'Consulta', -100, 'Custos fixos')
        self.store.save_rule('', 'consulta', 'Custos fixos')
        path = self.store.path
        self.store.db.close()
        self.store = FinanceStore(path)
        self.assertEqual(set(self.store.categories()), expected)
        self.assertEqual(self.store.category('consulta'), 'Custos fixos')

    def test_protected_duplicates_and_empty(self):
        for name,old in [('',None),('saude',None),('Outra','Sem categoria'),('Outra',TRANSFER),('x'*61,None)]:
            with self.assertRaises(ValueError):self.store.save_category(name,old)
        self.assertIn(TRANSFER,self.store.categories())

    def test_delete_reassigns_and_merges_without_changing_values(self):
        """Exclusão transfere referências e soma rateios no destino sem apagar gastos."""
        ident = self.store.edit_transaction(None, 1, '2026-10-01', 'Compra', -10000, 'Mercado')
        self.store.set_splits(ident, [('Mercado', -6000), ('Moradia', -4000)])
        self.store.save_rule('', 'compra', 'Mercado')
        self.store.planner.set_mapping('Moradia', 'plans')
        with self.store.db:
            self.store.db.execute("INSERT INTO installment_edits(series,month,account,category) VALUES ('teste','2026-10',2,'Mercado')")
        self.store.delete_category('Mercado', 'Moradia')
        self.assertNotIn('Mercado', self.store.categories())
        self.assertEqual(self.store.splits(ident), [{'category':'Moradia', 'amount':-10000}])
        self.assertEqual(self.store.category('compra'), 'Moradia')
        self.assertEqual(self.store.db.execute("SELECT category FROM installment_edits WHERE series='teste'").fetchone()[0], 'Moradia')
        self.assertEqual(next(g['spent'] for g in self.store.planner.report('2026-10')['groups'] if g['id']=='plans'), 10000)
        self.assertEqual(list(self.store.db.execute('PRAGMA foreign_key_check')), [])
        path = self.store.path
        self.store.db.close()
        self.store = FinanceStore(path)
        self.assertNotIn('Mercado', self.store.categories())
        for name, destination in [('Sem categoria', 'Moradia'), (TRANSFER, 'Moradia'), ('Moradia', 'Moradia')]:
            with self.assertRaises(ValueError):
                self.store.delete_category(name, destination)

    def test_restoration_preserves_existing_values_and_custom_links(self):
        """Reabrir uma base já convertida restaura opções sem inventar seu histórico."""
        ident = self.store.edit_transaction(None, 1, '2026-10-01', 'Compra existente', -1234, 'Custos fixos')
        with self.store.db:
            self.store.db.execute("DELETE FROM domain_migrations WHERE name='transaction_categories_restored'")
            self.store.db.execute("DELETE FROM budget_category_groups WHERE category='Mercado'")
            self.store.db.execute("DELETE FROM categories WHERE name='Mercado'")
        path = self.store.path
        self.store.db.close()
        self.store = FinanceStore(path)
        self.assertIn('Mercado', self.store.categories())
        row = self.store.db.execute('SELECT * FROM transactions WHERE id=?', (ident,)).fetchone()
        self.assertEqual((row['description'], row['amount'], row['category']), ('Compra existente', -1234, 'Custos fixos'))
        self.store.planner.set_mapping('Mercado', 'plans')
        self.store.save_category('Supermercado', 'Mercado')
        self.store.db.close()
        self.store = FinanceStore(path)
        self.assertEqual(self.store.planner.mappings()['Supermercado'], 'plans')
        self.assertNotIn('Mercado', self.store.categories())

    def test_reconciliation_remembers_renamed_category(self):
        self.store.edit_transaction(None,1,'2026-09-01','Fatura',-100,'Custos fixos')
        self.store.edit_transaction(None,2,'2026-09-01','Pagamento',100,TRANSFER,'2026-09')
        self.store.reconcile(1,2,'2026-09')
        ident=self.store.db.execute('SELECT id FROM reconciliations').fetchone()[0]
        self.store.unreconcile(ident)
        row=self.store.db.execute('SELECT category FROM transactions WHERE id=1').fetchone()
        self.assertEqual(row[0],'Custos fixos')
