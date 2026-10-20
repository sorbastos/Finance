"""Descrição personalizada independente do texto bancário imutável."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from contextlib import closing

from finance_desktop.service import FinanceService, Filters


class DescriptionTests(unittest.TestCase):
    """Valida preservação, migração e uso do original em dados sintéticos."""

    def setUp(self) -> None:
        """Prepara domínio e conta sem acessar dados pessoais."""
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'test.sqlite3'
        self.service = FinanceService(self.path)
        self.store = self.service.store
        self.original = 'LOJA XYZ · Parcela 2 de 4 · ****0001 · Titular'
        self.source = dict(date='2026-08-01', description=self.original, amount=-10000,
                           fitid='sample-id', invoice_month='2026-10', ownership='Titular',
                           holder='Pessoa fictícia', card_number='****0001')
        self.store.save(2, 'sample', b'sample', self.store.preview(2, [self.source]))
        self.ident = self.store.transactions()[0]['id']

    def tearDown(self) -> None:
        """Fecha a conexão antes de limpar o diretório temporário."""
        self.service.close()
        self.temp.cleanup()

    def rename(self, name: str) -> None:
        """Edita o campo pessoal pelo serviço, como o formulário da interface."""
        form = self.service.form('edit_transaction', [str(self.ident)], Filters())
        values = {f['key']: f['value'] for f in form['fields']}
        values.update(description=name, bank_description='Tentativa de alterar o original')
        self.service.submit(form, values, Filters())

    def test_alias_changes_without_changing_bank_description(self) -> None:
        """Mesmo com um original falsificado no payload, somente o nome pessoal muda."""
        self.rename('Notebook'); self.rename('Notebook do escritório')
        row = self.service.transaction(str(self.ident))
        self.assertEqual(row['description'], 'Notebook do escritório')
        self.assertEqual(row['bank_description'], self.original)
        form = self.service.form('edit_transaction', [str(self.ident)], Filters())
        original = next(f for f in form['fields'] if f['key'] == 'bank_description')
        self.assertTrue(original['read_only'])
        self.assertEqual(original['value'], self.original)

    def test_database_rejects_bank_description_update(self) -> None:
        """A proteção não depende somente de um campo QML bloqueado."""
        with self.assertRaises(sqlite3.IntegrityError), self.store.db:
            self.store.db.execute('UPDATE transactions SET bank_description=? WHERE id=?', ('Outro texto', self.ident))
        self.assertEqual(self.service.transaction(str(self.ident))['bank_description'], self.original)

    def test_search_and_reimport_use_both_descriptions(self) -> None:
        """Renomear não esconde a busca bancária nem transforma reimportação em compra nova."""
        self.rename('Notebook')
        self.assertEqual(len(self.store.transactions(search='Notebook')), 1)
        self.assertEqual(len(self.store.transactions(search='LOJA XYZ')), 1)
        self.assertEqual(self.store.preview(2, [self.source])[0]['status'], 'Duplicado (ID)')
        self.assertEqual(self.store.preview(2, [dict(self.source, fitid='')])[0]['status'], 'Possível duplicata')

    def test_alias_keeps_forecasts_and_installment_plan(self) -> None:
        """O nome personalizado não precisa conter a palavra Parcela."""
        self.rename('Notebook')
        rows = self.store.forecasts()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r['description'].startswith('Notebook · Parcela') for r in rows))
        self.assertEqual(self.store.installment_plan(self.ident)['current_number'], 2)

    def test_rules_match_original_after_alias_edit(self) -> None:
        """Regras bancárias continuam encontrando a descrição da origem."""
        self.rename('Notebook')
        self.store.save_rule('', 'loja xyz', 'Conforto', True)
        self.assertEqual(self.service.transaction(str(self.ident))['category'], 'Conforto')

    def test_migration_recovers_original_saved_before_update(self) -> None:
        """Simula esquema antigo com descrição editada e snapshot do original."""
        self.rename('Notebook')
        self.service.close()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('DROP TRIGGER protect_bank_description')
            connection.execute('ALTER TABLE transactions DROP COLUMN bank_description')
        self.service = FinanceService(self.path)
        self.store = self.service.store
        row = self.service.transaction(str(self.ident))
        self.assertEqual(row['description'], 'Notebook')
        self.assertEqual(row['bank_description'], self.original)
        self.service.close()
        self.service = FinanceService(self.path)
        self.store = self.service.store
        self.assertEqual(self.service.transaction(str(self.ident))['bank_description'], self.original)

    def test_manual_transaction_has_no_fabricated_bank_description(self) -> None:
        """Lançamentos manuais continuam editáveis sem atribuir texto ao banco."""
        ident = self.store.edit_transaction(None, 1, '2026-10-01', 'Manual', -100, 'Conforto')
        self.store.edit_transaction(ident, 1, '2026-10-01', 'Manual corrigido', -100, 'Conforto')
        row = self.service.transaction(str(ident))
        self.assertIsNone(row['bank_description'])
        form = self.service.form('edit_transaction', [str(ident)], Filters())
        self.assertNotIn('bank_description', [f['key'] for f in form['fields']])


if __name__ == '__main__':
    unittest.main()
