"""Importação parcial sem alterar linhas não selecionadas ou contornar IDs."""
import tempfile
import unittest
from pathlib import Path

from finance_desktop.importing import ImportSession
from finance_desktop.service import FinanceService
from test_xlsx import fixture


class SelectiveImportTests(unittest.TestCase):
    """Cada caso utiliza SQLite temporário e extratos inteiramente fictícios."""

    def setUp(self) -> None:
        """Prepara fatura com uma compra e um pagamento."""
        self.temp = tempfile.TemporaryDirectory()
        self.service = FinanceService(Path(self.temp.name) / 'test.sqlite3')
        self.path = Path(self.temp.name) / 'fatura.xlsx'
        self.path.write_bytes(fixture())

    def tearDown(self) -> None:
        """Fecha o banco e elimina somente os dados de teste."""
        self.service.close()
        self.temp.cleanup()

    def session(self, path: Path | None = None) -> ImportSession:
        """Repete configuração e prévia como o fluxo do desktop."""
        session = ImportSession(path or self.path, self.service)
        session.prepare({f['key']: f['value'] for f in session.form()['fields']})
        return session

    def test_select_payment_only_and_preserve_invoice_metadata(self) -> None:
        """Um crédito selecionado não traz a compra nem o cabeçalho da fatura."""
        self.service.store.set_invoice(2, '2026-10', '', 'Fechada', 12000)
        session = self.session()
        self.assertEqual(session.save(False, ['1']), 1)
        rows = self.service.store.transactions()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['amount'], 10000)
        self.assertEqual(self.service.store.invoices()[0]['total'], 12000)
        self.assertEqual(self.service.store.db.execute('SELECT count(*) FROM invoice_snapshots').fetchone()[0], 0)

    def test_remaining_rows_can_be_imported_later(self) -> None:
        """O hash de uma seleção não bloqueia o restante do arquivo."""
        self.assertEqual(self.session().save(False, ['1']), 1)
        self.assertEqual(self.session().save(False, ['0']), 1)
        self.assertEqual(len(self.service.store.transactions()), 2)
        with self.assertRaises(ValueError):
            self.session().save(False, ['1'])
        self.assertEqual(len(self.service.store.transactions()), 2)

    def test_missing_payment_from_previously_imported_file(self) -> None:
        """A seleção completa uma importação antiga que deixou de trazer o pagamento."""
        session = self.session()
        self.service.store.save(2, self.path.name, session.raw, session.rows[:1])
        self.assertEqual(self.session().rows[1]['status'], 'Novo')
        self.assertEqual(self.session().save(False, ['1']), 1)
        self.assertEqual(len(self.service.store.transactions()), 2)

    def test_full_import_after_partial_does_not_repeat_payment(self) -> None:
        """O modo completo aplica deduplicação após uma importação parcial."""
        self.session().save(False, ['1'])
        self.assertEqual(self.session().save(False), 1)
        self.assertEqual(len(self.service.store.transactions()), 2)

    def test_multi_selection_and_duplicate_selection_ids(self) -> None:
        """Selecionar várias linhas não insere duas vezes uma identidade repetida."""
        self.assertEqual(self.session().save(False, ['1', '0', '1']), 2)
        self.assertEqual(len(self.service.store.transactions()), 2)

    def test_invalid_selection_never_writes(self) -> None:
        """Seleção vazia ou fora da prévia não gera lote nem transações."""
        for selected in ([], ['-1'], ['2'], ['x'], [0]):
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                self.session().save(False, selected)
        self.assertEqual(self.service.store.transactions(), [])
        self.assertEqual(self.service.store.db.execute('SELECT count(*) FROM batches').fetchone()[0], 0)

    def test_bank_ids_remain_protected(self) -> None:
        """Seleção explícita não desbloqueia FITID repetido nem conflito."""
        path = Path(self.temp.name) / 'extrato.csv'
        path.write_text('data;descricao;valor;id\n01/10/2026;Primeiro;-10;id1\n02/10/2026;Segundo;-20;id2\n')
        self.session(path).save(False, ['0'])
        session = self.session(path)
        self.assertEqual(session.rows[0]['status'], 'Duplicado (ID)')
        self.assertEqual(session.save(True, ['0', '1']), 1)
        self.assertEqual(len(self.service.store.transactions()), 2)


if __name__ == '__main__':
    unittest.main()
