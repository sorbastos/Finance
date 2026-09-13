import unittest
import test_finance
from finance import FinanceStore, TRANSFER

class CategoryTests(unittest.TestCase):
    setUp = test_finance.FinanceTests.setUp
    tearDown = test_finance.FinanceTests.tearDown

    def test_shared_category_rename_and_reopen(self):
        self.store.save_category('Animais')
        for account in (1,2):
            self.store.edit_transaction(None,account,'2026-09-01','Consulta',-100,'Animais','2026-09' if account==2 else '')
        self.store.save_rule('','consulta','Animais')
        self.store.set_budget('2026-09','Animais',1000)
        self.store.save_category('Pets','Animais')
        self.assertEqual({r['category'] for r in self.store.transactions()},{'Pets'})
        self.assertEqual(self.store.category('consulta'),'Pets')
        self.assertEqual(self.store.budget_report('2026-09')[0]['category'],'Pets')
        self.store.save_category('Supermercado','Mercado')
        path=self.store.path
        self.store.db.close()
        self.store=FinanceStore(path)
        self.assertIn('Pets',self.store.categories())
        self.assertNotIn('Mercado',self.store.categories())
        self.store.categorize([1],'Pets')

    def test_protected_duplicates_and_empty(self):
        for name,old in [('',None),('saude',None),('Outra','Sem categoria'),('Outra',TRANSFER),('x'*61,None)]:
            with self.assertRaises(ValueError):self.store.save_category(name,old)
        self.assertIn(TRANSFER,self.store.categories())

    def test_reconciliation_remembers_renamed_category(self):
        self.store.edit_transaction(None,1,'2026-09-01','Fatura',-100,'Serviços')
        self.store.edit_transaction(None,2,'2026-09-01','Pagamento',100,TRANSFER,'2026-09')
        self.store.reconcile(1,2,'2026-09')
        self.store.save_category('Serviços diversos','Serviços')
        ident=self.store.db.execute('SELECT id FROM reconciliations').fetchone()[0]
        self.store.unreconcile(ident)
        row=self.store.db.execute('SELECT category FROM transactions WHERE id=1').fetchone()
        self.assertEqual(row[0],'Serviços diversos')
