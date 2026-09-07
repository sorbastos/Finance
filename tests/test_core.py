import tempfile
import unittest
from pathlib import Path
from core import Store, csv_table, parse_csv, parse_ofx, money


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'test.sqlite3')
        self.store.add_account('Itaú conta', 'Conta corrente')
        self.store.add_account('Itaú cartão', 'Cartão de crédito')

    def tearDown(self):
        self.store.db.close()
        self.temp.cleanup()

    def row(self, fitid=''):
        return dict(date='2026-09-01', description='Mercado', amount=-12345, fitid=fitid)

    def test_money(self):
        self.assertEqual(money('R$ -1.234,56'), -123456)
        self.assertEqual(money('0.29'), 29)
        self.assertEqual(money('(45,99)'), -4599)
        for invalid in ('NaN', 'Infinity', '1.234', ''):
            with self.assertRaises(ValueError):
                money(invalid)

    def test_csv_and_invalid_row(self):
        raw = 'data;descricao;valor\n01/09/2026;Café;12,34\n'.encode()
        fields, rows = csv_table(raw)
        mapping = dict(date=fields[0], description=fields[1], amount=fields[2])
        self.assertEqual(parse_csv(rows, mapping, True)[0]['amount'], -1234)
        rows.append(dict(data='31/02/2026', descricao='Inválido', valor='1'))
        with self.assertRaisesRegex(ValueError, 'Linha 3'):
            parse_csv(rows, mapping)

    def test_ofx_sgml_and_xml(self):
        for text in ('<STMTTRN><DTPOSTED>20260901120000[-3:BRT]\n<TRNAMT>-123.45\n<FITID>001\n<NAME>Mercado\n</STMTTRN>',
                     '<STMTTRN><DTPOSTED>20260901</DTPOSTED><TRNAMT>-123.45</TRNAMT><FITID>001</FITID><NAME>Mercado</NAME></STMTTRN>'):
            self.assertEqual(parse_ofx(text.encode()), [self.row('001')])

    def test_duplicate_ids_and_accounts(self):
        rows = self.store.preview(1, [self.row('1'), self.row('1')])
        self.assertEqual([r['status'] for r in rows], ['Novo', 'Duplicado (ID)'])
        self.assertEqual(self.store.save(1, 'a.ofx', b'a', rows), 1)
        self.assertEqual(self.store.preview(1, [self.row('1')])[0]['status'], 'Duplicado (ID)')
        self.assertEqual(self.store.preview(2, [self.row('1')])[0]['status'], 'Novo')
        with self.assertRaises(ValueError):
            self.store.save(1, 'a.ofx', b'a', rows)

    def test_equal_purchases_and_overlapping_periods(self):
        self.store.save(1, 'a.csv', b'a', self.store.preview(1, [self.row(), self.row()]))
        rows = self.store.preview(1, [self.row(), self.row(), self.row()])
        self.assertEqual([r['status'] for r in rows], ['Possível duplicata', 'Possível duplicata', 'Novo'])
        self.assertEqual(self.store.save(1, 'b.csv', b'b', rows), 1)
        self.assertEqual(len(self.store.transactions()), 3)

    def test_conflict_and_atomic_failure(self):
        self.store.save(1, 'a', b'a', self.store.preview(1, [self.row('x')]))
        changed = dict(self.row('x'), amount=-999)
        rows = self.store.preview(1, [changed])
        self.assertEqual(rows[0]['status'], 'Conflito de ID')
        with self.assertRaises(ValueError):
            self.store.save(1, 'b', b'b', rows)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM batches').fetchone()[0], 1)

    def test_rules_undo_and_backup(self):
        self.store.save(1, 'a', b'a', self.store.preview(1, [self.row()]))
        self.store.categorize([1], 'Mercado', 'MERCADO')
        self.assertEqual(self.store.preview(1, [self.row()])[0]['category'], 'Mercado')
        self.store.backup(Path(self.temp.name) / 'backup.sqlite3')
        other = Store(Path(self.temp.name) / 'backup.sqlite3')
        self.assertEqual(other.transactions()[0]['category'], 'Mercado')
        other.db.close()
        self.store.undo()
        self.assertEqual(len(self.store.transactions()), 0)
        self.assertEqual(self.store.preview(1, [self.row()])[0]['status'], 'Novo')


if __name__ == '__main__':
    unittest.main()
