"""Regressões para parcelas futuras sem repetição entre faturas e lotes."""
import tempfile
import unittest
from pathlib import Path

from finance import FinanceStore


class ForecastDuplicateTests(unittest.TestCase):
    """Usa somente compras fictícias; nenhuma conexão com o banco pessoal."""

    def setUp(self) -> None:
        """Cria um cartão isolado para cada cenário."""
        self.temp = tempfile.TemporaryDirectory()
        self.store = FinanceStore(Path(self.temp.name) / 'test.sqlite3')
        self.store.add_account('Cartão exemplo', 'Cartão de crédito')

    def tearDown(self) -> None:
        """Libera o SQLite antes de remover a pasta de teste."""
        self.store.db.close()
        self.temp.cleanup()

    def save(self, name: str, month: str = '2026-10', number: int = 2,
             copies: int = 1, owner: str = 'Titular', fitid: str = '') -> None:
        """Inclui possíveis duplicatas intencionalmente para testar dados já existentes."""
        rows = [dict(date='2026-08-01', description=f'Loja exemplo · Parcela {number} de 4',
            amount=-10000, fitid=fitid, invoice_month=month, ownership=owner,
            holder='Pessoa exemplo', card_number='****0001') for _ in range(copies)]
        self.store.save(1, name, name.encode(), self.store.preview(1, rows), True)

    def test_reimport_does_not_multiply_forecasts(self) -> None:
        """Mesmo lançamento em dois lotes gera só uma previsão por competência."""
        self.save('primeiro'); self.save('repetido')
        result = self.store.forecasts()
        self.assertEqual(len(result), 2)
        self.assertEqual({r['month'] for r in result}, {'2026-11', '2026-12'})
        self.assertEqual(sum(r['amount'] for r in result), 20000)
        self.assertEqual(len(self.store.transactions()), 2)

    def test_two_equal_purchases_in_same_file_are_preserved(self) -> None:
        """Duas compras iguais no mesmo arquivo não viram uma única compra."""
        self.save('primeiro', copies=2); self.save('repetido', copies=2)
        self.assertEqual(len(self.store.forecasts()), 4)
        self.assertEqual(sum(r['amount'] for r in self.store.forecasts()), 40000)

    def test_newer_invoice_replaces_older_prediction(self) -> None:
        """Uma parcela já importada deixa de ser prevista, mesmo com histórico repetido."""
        self.save('outubro'); self.save('novembro', month='2026-11', number=3)
        self.save('novembro-repetido', month='2026-11', number=3)
        result = self.store.forecasts()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['month'], '2026-12')

    def test_holders_and_distinct_bank_ids_are_not_merged(self) -> None:
        """Titular/adicional e compras com identificadores diferentes são independentes."""
        self.save('titular', fitid='purchase-a')
        self.save('outra-compra', fitid='purchase-b')
        self.save('adicional', owner='Adicional')
        self.assertEqual(len(self.store.forecasts()), 6)

    def test_highest_installment_in_same_month_is_used(self) -> None:
        """Observações de duas etapas da mesma compra não projetam o restante duas vezes."""
        self.save('etapa-dois'); self.save('etapa-tres', number=3)
        result = self.store.forecasts()
        self.assertEqual(len(result), 1)
        self.assertIn('Parcela 4 de 4', result[0]['description'])

    def test_exclude_one_month_preserves_other_month_and_original(self) -> None:
        """Remover novembro não remove dezembro nem o lançamento importado."""
        self.save('outubro')
        original = dict(self.store.transactions()[0])
        self.store.exclude_forecast(original['id'], '2026-11')
        self.assertEqual([r['month'] for r in self.store.forecasts()], ['2026-12'])
        self.assertEqual(dict(self.store.transactions()[0]), original)
        path = self.store.path
        self.store.db.close()
        self.store = FinanceStore(path)
        self.assertEqual([r['month'] for r in self.store.forecasts()], ['2026-12'])

    def test_exclude_all_only_affects_selected_source(self) -> None:
        """Retira uma origem duplicada sem afetar a compra do outro portador."""
        self.save('titular'); self.save('adicional', owner='Adicional')
        selected = next(r for r in self.store.forecasts() if r['ownership'] == 'Titular')
        self.store.exclude_forecast(selected['transaction_id'], selected['month'], True)
        self.assertEqual(len(self.store.forecasts()), 2)
        self.assertEqual({r['ownership'] for r in self.store.forecasts()}, {'Adicional'})
        self.assertEqual(len(self.store.transactions()), 2)

    def test_unavailable_forecast_is_rejected(self) -> None:
        """Uma seleção antiga não pode excluir uma compra ou competência diferente."""
        self.save('outubro')
        ident = self.store.transactions()[0]['id']
        with self.assertRaises(ValueError):
            self.store.exclude_forecast(ident, '2027-01')
        self.assertEqual(len(self.store.forecasts()), 2)


if __name__ == '__main__':
    unittest.main()
