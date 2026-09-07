import tempfile
import unittest
from pathlib import Path
from core import Store


class PersistenceTests(unittest.TestCase):
    def test_saved_import_survives_reopen(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'despesas.sqlite3'
            store = Store(path)
            store.add_account('Cartão', 'Cartão de crédito')
            rows = [dict(date='2026-09-01', description='Compra', amount=-1234, fitid='abc', invoice_month='2026-10')]
            store.save(1, 'fatura.xlsx', b'arquivo', store.preview(1, rows))
            store.db.close()
            reopened = Store(path)
            result = reopened.transactions('2026-10')
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]['amount'], -1234)
            self.assertEqual(reopened.db.execute('SELECT filename FROM batches').fetchone()[0], 'fatura.xlsx')
            self.assertEqual(reopened.preview(1, rows)[0]['status'], 'Duplicado (ID)')
            reopened.db.close()
