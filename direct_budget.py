"""Migração atômica das categorias antigas para as sete categorias do orçamento."""
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from finance import FinanceStore


def migrate_categories(store: 'FinanceStore', groups: tuple) -> None:
    """Converte classificações conhecidas e remove o catálogo anterior uma única vez.

    Mantém valores, descrições e parcelas. Rateios que convergem para a mesma
    categoria são somados. Categorias sem meta ficam pendentes de classificação.
    Todas as referências são atualizadas antes de excluir o catálogo antigo.
    """
    db = store.db
    db.execute('CREATE TABLE IF NOT EXISTS domain_migrations(name TEXT PRIMARY KEY)')
    if db.execute("SELECT 1 FROM domain_migrations WHERE name='direct_budget_categories'").fetchone():
        return
    names = {key: name for key, name, _, _ in groups}
    names['unassigned'] = 'Sem categoria'
    mapping = {r['category']: names.get(r['group_id'], 'Sem categoria')
               for r in db.execute('SELECT * FROM budget_category_groups')}
    mapping.update({name: name for name in names.values()})
    transfer = 'Transferência / pagamento de fatura'
    mapping[transfer] = transfer

    def target(category: str) -> str:
        """Resolve o destino sem inferir a finalidade de categorias desconhecidas."""
        return mapping.get(category, 'Sem categoria')

    with db:
        db.executemany('INSERT OR IGNORE INTO categories VALUES (?)', [(name,) for name in names.values()])
        db.execute('INSERT OR IGNORE INTO categories VALUES (?)', (transfer,))
        for table, column in (('transactions', 'category'), ('rules', 'category'),
                              ('reconciliations', 'old_debit_category'),
                              ('reconciliations', 'old_credit_category'), ('installment_edits', 'category')):
            for row in db.execute(f'SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL').fetchall():
                db.execute(f'UPDATE {table} SET {column}=? WHERE {column}=?', (target(row[0]), row[0]))
        parts = defaultdict(int)
        for row in db.execute('SELECT * FROM transaction_splits'):
            parts[(row['transaction_id'], target(row['category']))] += row['amount']
        db.execute('DELETE FROM transaction_splits')
        db.executemany('INSERT INTO transaction_splits VALUES (?,?,?)',
                       [(ident, category, amount) for (ident, category), amount in parts.items()])
        # Limites avulsos e vínculos categoria/grupo deixam de fazer parte do modelo.
        db.execute('DELETE FROM budgets')
        db.execute('DELETE FROM budget_category_groups')
        for category in store.categories():
            if category not in names.values() and category != transfer:
                db.execute('DELETE FROM categories WHERE name=?', (category,))
        db.execute("INSERT INTO domain_migrations VALUES ('direct_budget_categories')")
