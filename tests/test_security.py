"""Proteções de arquivos financeiros verificadas somente com conteúdo sintético."""
import os
import stat
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
from core import Store
from security import read_import_file


class FileSecurityTests(unittest.TestCase):
    """Confere limites, permissões e preservação do conteúdo existente."""

    def test_import_limit_and_extension(self) -> None:
        """Valida o limite antes da leitura e limita a própria operação de leitura."""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'extrato.csv'
            path.write_bytes(b'12345')
            with patch('security.MAX_IMPORT_BYTES', 4), self.assertRaises(ValueError):
                read_import_file(path)
            with patch('security.MAX_IMPORT_BYTES', 4), patch('security.os.fstat', return_value=SimpleNamespace(st_size=0)), self.assertRaises(ValueError):
                read_import_file(path)
            with patch('security.MAX_IMPORT_BYTES', 5):
                self.assertEqual(read_import_file(path), b'12345')
            with self.assertRaises(ValueError):
                read_import_file(Path(temp)/'nao-permitido.html')

    @unittest.skipUnless(os.name == 'posix', 'Permissões POSIX')
    def test_database_and_backup_are_private_and_existing_data_survive(self) -> None:
        """Reabertura restringe permissões sem apagar transações ou mudar diretórios gerais."""
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            path = parent/'minhas-despesas'/'teste.sqlite3'
            store = Store(path)
            store.add_account('Conta sintética', 'Conta corrente')
            backup = parent/'backup.sqlite3'
            store.backup(backup)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o600)
            store.db.close()
            path.chmod(0o644)
            path.parent.chmod(0o755)
            reopened = Store(path)
            self.assertEqual(len(reopened.accounts()), 1)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
            linked = parent/'mesmo-banco.sqlite3'
            os.link(path, linked)
            with self.assertRaises(ValueError):
                reopened.backup(linked)
            reopened.db.close()

    @unittest.skipUnless(os.name == 'posix', 'Permissões POSIX')
    def test_backup_does_not_follow_symbolic_link(self) -> None:
        """Um destino redirecionado não sobrescreve outro arquivo do usuário."""
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            store = Store(parent/'teste.sqlite3')
            target = parent/'outro.txt'
            target.write_text('preservar')
            link = parent/'backup.sqlite3'
            link.symlink_to(target)
            with self.assertRaises(OSError):
                store.backup(link)
            self.assertEqual(target.read_text(), 'preservar')
            store.db.close()
