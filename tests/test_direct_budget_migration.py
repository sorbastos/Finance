"""Migração das categorias legadas com integridade, retomada e valores preservados."""
import tempfile
import unittest
from pathlib import Path

from budgeting import GOAL_GROUPS
from direct_budget import migrate_categories
from finance import FinanceStore, TRANSFER


class DirectBudgetMigrationTests(unittest.TestCase):
    """Reproduz o esquema anterior apenas em banco temporário sintético."""

    def setUp(self) -> None:
        """Prepara categorias antigas, rateio convergente e regras persistidas."""
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'legacy.sqlite3'
        self.store = FinanceStore(self.path)
        self.store.add_account('Conta fictícia', 'Conta corrente')
        self.store.add_account('Cartão fictício', 'Cartão de crédito')
        self.ident = self.store.edit_transaction(None, 1, '2026-10-02', 'Compra fictícia', -10000, 'Custos fixos')
        self.pending = self.store.edit_transaction(None, 1, '2026-10-03', 'Outra compra', -3000, 'Sem categoria')
        self.store.planner.set_planning_income('2026-10', 100000)
        self.goals = {key: percent for key, _, percent, _ in GOAL_GROUPS}
        self.store.planner.set_goals('2026-10', self.goals)
        self.store.set_transaction_tags(self.ident, ['Casa'])
        with self.store.db:
            self.store.db.execute("DELETE FROM domain_migrations WHERE name='direct_budget_categories'")
            self.store.db.executemany('INSERT OR IGNORE INTO categories VALUES (?)', [('Mercado',), ('Moradia',), ('Pessoal',), ('Curso',)])
            self.store.db.executemany('INSERT OR REPLACE INTO budget_category_groups VALUES (?,?)',
                                     [('Mercado', 'fixed'), ('Moradia', 'fixed'), ('Curso', 'knowledge')])
            self.store.db.execute('UPDATE transactions SET category=? WHERE id=?', ('Mercado', self.ident))
            self.store.db.execute('UPDATE transactions SET category=? WHERE id=?', ('Pessoal', self.pending))
            self.store.db.executemany('INSERT INTO transaction_splits VALUES (?,?,?)',
                                     [(self.ident, 'Mercado', -6000), (self.ident, 'Moradia', -4000)])
            self.store.db.execute("INSERT INTO rules VALUES ('curso','Curso')")
            self.store.db.execute("INSERT INTO installment_edits(series,month,account,category) VALUES ('compra','2026-10',2,'Curso')")
            self.store.db.execute("INSERT INTO budgets VALUES ('2026-10','Mercado',20000)")

    def tearDown(self) -> None:
        """Fecha somente a conexão de teste e limpa seu diretório."""
        self.store.db.close()
        self.temp.cleanup()

    def test_conversion_is_complete_and_idempotent(self) -> None:
        """Conversão soma rateios, traduz regras e remove categorias antigas de vez."""
        before = [(r['id'], r['date'], r['description'], r['amount']) for r in self.store.transactions()]
        migrate_categories(self.store, GOAL_GROUPS)
        self.store.db.close()
        self.store = FinanceStore(self.path)
        expected = {name for _, name, _, _ in GOAL_GROUPS} | {'Sem categoria', TRANSFER}
        self.assertEqual(set(self.store.categories()), expected)
        self.assertEqual(self.store.splits(self.ident), [{'category':'Custos fixos', 'amount':-10000}])
        self.assertEqual(self.store.category('curso'), 'Conhecimento')
        self.assertEqual(self.store.db.execute('SELECT category FROM installment_edits').fetchone()[0], 'Conhecimento')
        self.assertEqual(self.store.db.execute('SELECT category FROM transactions WHERE id=?', (self.pending,)).fetchone()[0], 'Sem categoria')
        self.assertEqual(self.store.transaction_tags(self.ident), ['Casa'])
        self.assertEqual(before, [(r['id'], r['date'], r['description'], r['amount']) for r in self.store.transactions()])
        self.assertEqual(self.store.planner.planning_income('2026-10'), 100000)
        self.assertEqual(self.store.planner.goals('2026-10')[0], self.goals)
        self.assertEqual(self.store.planner.report('2026-10')['spent'], 10000)
        self.assertEqual(list(self.store.db.execute('PRAGMA foreign_key_check')), [])
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM budget_category_groups').fetchone()[0], 7)
        migrate_categories(self.store, GOAL_GROUPS)
        self.assertEqual(self.store.splits(self.ident)[0]['amount'], -10000)

    def test_failure_rolls_back_the_whole_conversion(self) -> None:
        """Falha no fim da migração não deixa metade dos lançamentos convertida."""
        self.store.db.executescript('''
            CREATE TRIGGER block_category_deletion BEFORE DELETE ON categories
            BEGIN SELECT RAISE(ABORT,'Falha sintética'); END;
        ''')
        with self.assertRaisesRegex(Exception, 'Falha sintética'):
            migrate_categories(self.store, GOAL_GROUPS)
        self.assertEqual(self.store.db.execute('SELECT category FROM transactions WHERE id=?', (self.ident,)).fetchone()[0], 'Mercado')
        self.assertEqual(len(self.store.splits(self.ident)), 2)
        self.assertFalse(self.store.db.execute("SELECT 1 FROM domain_migrations WHERE name='direct_budget_categories'").fetchone())
        self.store.db.execute('DROP TRIGGER block_category_deletion')
        migrate_categories(self.store, GOAL_GROUPS)
        self.assertNotIn('Mercado', self.store.categories())
