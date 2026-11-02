"""Verifica herança de metadados sem usar dados ou arquivos pessoais."""
import unittest
import test_finance
from finance import FinanceStore


class InstallmentLinkTests(unittest.TestCase):
    """Exercita compras sintéticas, reabertura, novas faturas e ambiguidades."""
    setUp = test_finance.FinanceTests.setUp
    tearDown = test_finance.FinanceTests.tearDown
    purchase = test_finance.FinanceTests.purchase
    save_rows = test_finance.FinanceTests.save_rows

    def seed(self) -> list[int]:
        """Importa três meses da mesma compra e uma compra do adicional."""
        for index, month in enumerate(('2026-09', '2026-10', '2026-11'), 1):
            self.save_rows(2, month, [self.purchase(month, index)])
        self.save_rows(2, 'adicional', [self.purchase('2026-11', 3, 'Adicional')])
        return [r[0] for r in self.store.db.execute('SELECT id FROM transactions ORDER BY id')]

    def edit(self, ident: int, name: str, category: str | None = None) -> None:
        """Salva o formulário mantendo os campos financeiros desta parcela."""
        row = self.store.db.execute('SELECT * FROM transactions WHERE id=?', (ident,)).fetchone()
        self.store.edit_transaction(ident, row['account'], row['date'], name, row['amount'], category or row['category'],
                                    row['invoice_month'], row['ownership'], row['holder'], row['card_number'])

    def test_following_only_and_future_import(self):
        """Mantém passado, portador e original; novas faturas herdam após reabrir."""
        ids = self.seed()
        original = dict(self.store.db.execute('SELECT * FROM transactions WHERE id=?', (ids[2],)).fetchone())
        self.edit(ids[1], 'Minha loja', 'Custos fixos')
        self.store.set_transaction_tags(ids[1], ['Casa'])
        rows = list(self.store.db.execute('SELECT * FROM transactions ORDER BY id'))
        self.assertNotEqual(rows[0]['description'], 'Minha loja')
        self.assertEqual(rows[2]['description'], 'Minha loja')
        self.assertNotEqual(rows[3]['description'], 'Minha loja')
        for key in ('bank_description', 'date', 'amount', 'invoice_month'):
            self.assertEqual(rows[2][key], original[key])
        self.assertEqual(self.store.transaction_tags(ids[2]), ['Casa'])
        path = self.store.path
        self.store.db.close()
        self.store = FinanceStore(path)
        row = self.purchase('2026-12', 4)
        self.save_rows(2, 'dezembro', [row])
        latest = self.store.db.execute('SELECT * FROM transactions ORDER BY id DESC').fetchone()
        self.assertEqual((latest['description'], latest['category']), ('Minha loja', 'Custos fixos'))
        self.assertEqual(self.store.transaction_tags(latest['id']), ['Casa'])
        self.assertEqual(self.store.preview(2, [row])[0]['status'], 'Possível duplicata')

    def test_later_edit_wins_per_field_and_category_rename(self):
        """Um ajuste posterior tem precedência sem impedir herança dos demais campos."""
        ids = self.seed()
        self.edit(ids[2], 'Nome novembro')
        self.edit(ids[1], 'Nome outubro')
        self.store.categorize([ids[1]], 'Reserva de emergência')
        self.save_rows(2, 'dezembro', [self.purchase('2026-12', 4)])
        latest = self.store.db.execute('SELECT * FROM transactions ORDER BY id DESC').fetchone()
        self.assertEqual(latest['description'], 'Nome novembro')
        self.assertEqual(latest['category'], 'Reserva de emergência')
        self.store.set_transaction_tags(ids[1], ['Teste'])
        self.store.set_transaction_tags(ids[1], [])
        self.assertEqual(self.store.transaction_tags(latest['id']), [])

    def test_ambiguous_equal_purchases_are_not_linked(self):
        """Não mistura duas compras iguais presentes no mesmo mês."""
        self.save_rows(2, 'duas', [self.purchase(), self.purchase()])
        ids = [r[0] for r in self.store.db.execute('SELECT id FROM transactions ORDER BY id')]
        self.edit(ids[0], 'Apenas uma')
        row = self.store.db.execute('SELECT description FROM transactions WHERE id=?', (ids[1],)).fetchone()
        self.assertNotEqual(row[0], 'Apenas uma')
