import unittest
import test_core


class MonthTests(unittest.TestCase):
    setUp = test_core.ImportTests.setUp
    tearDown = test_core.ImportTests.tearDown

    def test_months_use_invoice_period_and_account(self):
        self.assertEqual(self.store.months(), [])
        rows = [dict(date='2025-12-31', description='Compra', amount=-100, fitid='1'),
                dict(date='2026-01-01', description='Compra', amount=-100, fitid='2')]
        self.store.save(1, 'conta', b'a', self.store.preview(1, rows))
        card = [dict(date='2026-01-01', invoice_month='2026-10', description='Parcela', amount=-100, fitid='3')]
        self.store.save(2, 'cartao', b'b', self.store.preview(2, card))
        self.assertEqual(self.store.months(), ['2026-10', '2026-01', '2025-12'])
        self.assertEqual(self.store.months(2), ['2026-10'])
        self.assertEqual(len(self.store.transactions('2026-10', 2)), 1)
        self.store.undo()
        self.assertEqual(self.store.months(2), [])
