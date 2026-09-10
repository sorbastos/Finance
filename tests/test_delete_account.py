import unittest
import test_finance
from finance import FinanceStore,TRANSFER

class DeleteAccountTests(unittest.TestCase):
    setUp=test_finance.FinanceTests.setUp
    tearDown=test_finance.FinanceTests.tearDown

    def test_delete_preserves_other_account_rules_and_budgets(self):
        d=dict(date='2026-10-08',description='FATURA PAGA',amount=-10000,fitid='d',category='Serviços')
        c=dict(date='2026-10-08',description='Pagamento recebido',amount=10000,fitid='c',category=TRANSFER,invoice_month='2026-10')
        for account,name,row in [(1,'d',d),(2,'c',c)]:
            self.store.save(account,name,name.encode(),self.store.preview(account,[row]))
        self.store.set_invoice(2,'2026-10','08/10/2026','Fechada',10000)
        self.store.reconcile(1,2,'2026-10')
        self.store.set_budget('2026-10','Serviços',100)
        self.store.save_rule('','teste','Serviços')
        self.assertEqual(self.store.account_impact(2)['transactions'],1)
        self.store.delete_account(2)
        self.assertEqual(len(self.store.accounts()),1)
        self.assertEqual(self.store.transactions()[0]['category'],'Serviços')
        self.assertEqual(self.store.invoices(),[])
        self.assertEqual(len(self.store.reconciled()),0)
        self.assertEqual(self.store.db.execute('PRAGMA foreign_key_check').fetchall(),[])
        self.assertEqual(len(self.store.budget_report('2026-10')),1)
        self.assertEqual(self.store.category('teste'),'Serviços')
        self.store.delete_account(1)
        self.assertEqual(self.store.accounts(),[])
        path=self.store.path
        self.store.db.close();self.store=FinanceStore(path)
        self.assertEqual(self.store.accounts(),[])
