import test_finance
import unittest

from finance import FinanceStore


class AdvancedFeatureTests(unittest.TestCase):
    setUp = test_finance.FinanceTests.setUp
    tearDown = test_finance.FinanceTests.tearDown

    def test_monthly_closing_calculates_difference(self):
        self.store.edit_transaction(None,1,'2026-09-02','Entrada',50000,'Sem categoria')
        self.store.edit_transaction(None,1,'2026-09-03','Saída',-12500,'Custos fixos')
        self.store.set_closing(1,'2026-09',100000,137500)
        closing=self.store.closings('2026-09')[0]
        self.assertEqual(closing['movement'],37500)
        self.assertEqual(closing['calculated'],137500)
        self.assertEqual(closing['difference'],0)
        self.assertEqual(closing['state'],'Conferido')
        with self.assertRaises(ValueError):
            self.store.set_closing(2,'2026-09',0,0)

    def test_split_updates_reports_and_can_be_removed(self):
        ident=self.store.edit_transaction(None,1,'2026-09-03','Compra mista',-10000,'Conforto')
        self.store.set_splits(ident,[('Custos fixos',-7000),('Reserva de emergência',-3000)])
        self.store.set_budget('2026-09','Custos fixos',10000)
        self.store.set_budget('2026-09','Reserva de emergência',5000)
        report={r['category']:r['spent'] for r in self.store.budget_report('2026-09')}
        self.assertEqual(report,{'Custos fixos':7000,'Reserva de emergência':3000})
        comparison={r['category']:r['current'] for r in self.store.comparison('2026-09')}
        self.assertEqual(comparison,{'Custos fixos':7000,'Reserva de emergência':3000})
        with self.assertRaises(ValueError):
            self.store.set_splits(ident,[('Custos fixos',-6000),('Reserva de emergência',-3000)])
        self.store.clear_splits(ident)
        self.assertEqual(self.store.splits(ident),[])

    def test_tags_persist_and_are_shared(self):
        first=self.store.edit_transaction(None,1,'2026-09-03','Táxi',-1000,'Custos fixos')
        second=self.store.edit_transaction(None,2,'2026-09-04','Hotel',-2000,'Prazeres','2026-09')
        self.store.set_transaction_tags(first,['Viagem',' Reembolsável ','Viagem'])
        self.store.set_transaction_tags(second,['Viagem'])
        self.assertEqual(self.store.transaction_tags(first),['Reembolsável','Viagem'])
        self.assertEqual(self.store.tags(),['Reembolsável','Viagem'])
        path=self.store.path;self.store.db.close();self.store=FinanceStore(path)
        self.assertEqual(self.store.transaction_tags(second),['Viagem'])

    def test_installment_correction_anticipation_and_cancellation(self):
        row=test_finance.FinanceTests.purchase(self,month='2026-10',part=2)
        self.store.save(2,'card',b'card',self.store.preview(2,[row]))
        ident=self.store.transactions()[0]['id']
        self.store.set_installment_plan(ident,2,6,2,False)
        forecast=self.store.forecasts(2)
        self.assertEqual(sum(r['amount'] for r in forecast),40000)
        self.assertEqual([r['status'] for r in forecast].count('Antecipado'),1)
        self.assertEqual([r['status'] for r in forecast].count('Previsto'),2)
        self.store.set_installment_plan(ident,2,6,0,True)
        cancelled=self.store.forecasts(2)
        self.assertEqual(len(cancelled),1)
        self.assertEqual(cancelled[0]['status'],'Cancelado')
        self.assertEqual(cancelled[0]['amount'],0)


if __name__ == '__main__':
    unittest.main()
