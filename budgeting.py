"""Orçamento por metas com renda planejada e lançamentos reais separados.

O planejamento não cria receitas nem despesas: apenas agrupa o histórico e
distribui somente a renda editável do mês. Todos os valores são centavos inteiros.
"""
from collections import defaultdict
from typing import TYPE_CHECKING

from core import CATEGORIES

if TYPE_CHECKING:
    from finance import FinanceStore


# Identidades estáveis dos grupos de metas; categorias de transação são vinculadas a eles.
GOAL_GROUPS = (
    ('fixed', 'Custos fixos', 30, '#7cb9e8'),
    ('comfort', 'Conforto', 15, '#98dfc7'),
    ('plans', 'Metas', 15, '#efe58a'),
    ('pleasure', 'Prazeres', 10, '#dca1ea'),
    ('freedom', 'Liberdade financeira', 25, '#7c91ef'),
    ('knowledge', 'Conhecimento', 5, '#efad54'),
    ('reserve', 'Reserva de emergência', 0, '#8794a9'),
)
DEFAULT_MAPPING = {
    'Moradia': 'fixed', 'Mercado': 'fixed', 'Saúde': 'fixed',
    'Transporte': 'fixed', 'Serviços': 'fixed', 'Alimentação': 'comfort',
    'Compras': 'comfort', 'Lazer': 'pleasure', 'Educação': 'knowledge',
}
UNASSIGNED = 'unassigned'


class BudgetPlanner:
    """Metas mensais e vínculos das categorias de conta/cartão aos grupos de orçamento."""

    def __init__(self, store: 'FinanceStore') -> None:
        """Prepara o planejamento e restaura categorias sem reclassificar o histórico."""
        self.store = store
        self.db = store.db
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS budget_goal_groups(
          id TEXT PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS budget_goals(
          month TEXT NOT NULL, group_id TEXT REFERENCES budget_goal_groups(id),
          percent INTEGER NOT NULL CHECK(percent BETWEEN 0 AND 100),
          PRIMARY KEY(month,group_id));
        CREATE TABLE IF NOT EXISTS budget_category_groups(
          category TEXT PRIMARY KEY REFERENCES categories(name) ON UPDATE CASCADE ON DELETE CASCADE,
          group_id TEXT NOT NULL REFERENCES budget_goal_groups(id));
        CREATE TABLE IF NOT EXISTS budget_income_settings(
          month TEXT PRIMARY KEY, amount INTEGER NOT NULL CHECK(amount>=0));
        ''')
        with self.db:
            self.db.executemany('INSERT OR IGNORE INTO budget_goal_groups VALUES (?,?)',
                               [(key, name) for key, name, _, _ in GOAL_GROUPS] + [(UNASSIGNED, 'Não classificado')])
            categories = set(store.categories())
            self.db.executemany('INSERT OR IGNORE INTO budget_category_groups VALUES (?,?)',
                               [(category, group) for category, group in DEFAULT_MAPPING.items() if category in categories])
        # Restaura o catálogo sem tentar adivinhar categorias que já foram convertidas.
        self.db.execute('CREATE TABLE IF NOT EXISTS domain_migrations(name TEXT PRIMARY KEY)')
        with self.db:
            if not self.db.execute("SELECT 1 FROM domain_migrations WHERE name='transaction_categories_restored'").fetchone():
                self.db.executemany('INSERT OR IGNORE INTO categories VALUES (?)', [(name,) for name in CATEGORIES])
                self.db.executemany('INSERT OR IGNORE INTO categories VALUES (?)', [(g[1],) for g in GOAL_GROUPS])
                self.db.execute("INSERT INTO domain_migrations VALUES ('transaction_categories_restored')")
            self.db.executemany('INSERT OR IGNORE INTO budget_category_groups VALUES (?,?)',
                               [(name, group) for name, group in DEFAULT_MAPPING.items() if name in store.categories()])
            # Classificações diretas já existentes continuam nos mesmos grupos.
            for key, name, _, _ in GOAL_GROUPS:
                if name in store.categories():
                    self.db.execute('INSERT OR IGNORE INTO budget_category_groups VALUES (?,?)', (name, key))

    def planning_income(self, month: str) -> int | None:
        """Lê somente o valor definido para este mês; não herda renda de outro mês."""
        from finance import validate_month
        validate_month(month)
        row = self.db.execute('SELECT amount FROM budget_income_settings WHERE month=?', (month,)).fetchone()
        return row['amount'] if row else None

    def set_planning_income(self, month: str, amount: int) -> None:
        """Salva renda de planejamento, sem criar lançamentos bancários."""
        from finance import validate_month
        validate_month(month)
        if type(amount) is not int or amount < 0:
            raise ValueError('Informe uma renda mensal válida, igual ou maior que zero.')
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO budget_income_settings VALUES (?,?)', (month, amount))

    def goals(self, month: str) -> tuple[dict[str, int], str]:
        """Usa a configuração do mês ou a última anterior; nunca herda do futuro."""
        from finance import validate_month
        validate_month(month)
        row = self.db.execute('SELECT MAX(month) FROM budget_goals WHERE month<=?', (month,)).fetchone()
        source = row[0] or ''
        goals = {key: percent for key, _, percent, _ in GOAL_GROUPS}
        if source:
            goals.update({r['group_id']: r['percent'] for r in self.db.execute('SELECT * FROM budget_goals WHERE month=?', (source,))})
        return goals, source

    def set_goals(self, month: str, values: dict[str, int]) -> None:
        """Grava um conjunto completo e válido, com soma exata de 100%."""
        from finance import validate_month
        validate_month(month)
        expected = {group[0] for group in GOAL_GROUPS}
        if not isinstance(values, dict) or set(values) != expected:
            raise ValueError('Informe o percentual de todos os grupos de metas.')
        if any(type(value) is not int or not 0 <= value <= 100 for value in values.values()) or sum(values.values()) != 100:
            raise ValueError('Os percentuais devem ser inteiros de 0 a 100 e somar 100%.')
        with self.db:
            self.db.executemany('INSERT OR REPLACE INTO budget_goals VALUES (?,?,?)',
                               [(month, key, value) for key, value in values.items()])

    def mappings(self) -> dict[str, str]:
        """Retorna o vínculo global entre categorias das transações e grupos de metas."""
        return {r['category']: r['group_id'] for r in self.db.execute('SELECT * FROM budget_category_groups')}

    def set_mapping(self, category: str, group: str) -> None:
        """Vincula uma categoria ao grupo sem reescrever transações ou seus valores."""
        groups = {g[0] for g in GOAL_GROUPS} | {UNASSIGNED}
        if category not in self.store.categories() or category == CATEGORIES[-1] or group not in groups:
            raise ValueError('Selecione uma categoria e um grupo válidos.')
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO budget_category_groups VALUES (?,?)', (category, group))

    def _planned_amounts(self, income: int, percentages: dict[str, int]) -> dict[str, int]:
        """Distribui os centavos restantes pelo maior resto, sem arredondar por float."""
        amounts = {key: income * percent // 100 for key, percent in percentages.items()}
        remainder = income - sum(amounts.values())
        order = sorted(percentages, key=lambda key: income * percentages[key] % 100, reverse=True)
        for key in order[:remainder]:
            amounts[key] += 1
        return amounts

    def report(self, month: str) -> dict:
        """Consolida receitas reais e metas baseadas na renda mensal editável.

        Transferências/pagamentos de fatura ficam fora dos dois lados. Créditos
        do cartão reduzem despesas; entradas da conta aparecem separadamente
        para conferência. Somente a renda planejada distribui as metas. Divisões
        incluem somente partes com grupo atribuído; não classificados ficam
        visíveis para revisão, fora dos totais. Previsões não são gastos reais.
        """
        goals, source = self.goals(month)
        mapping = self.mappings()
        spent = defaultdict(int)
        income, cash, card = 0, 0, 0
        transactions = self.store.transactions(month)
        for row in transactions:
            if row['category'] == CATEGORIES[-1]:
                continue
            if row['kind'] == 'Conta corrente' and row['amount'] > 0:
                income += row['amount']
                continue
            if row['kind'] not in ('Conta corrente', 'Cartão de crédito'):
                continue
            for part in self.store.allocations(row):
                if part['category'] == CATEGORIES[-1]:
                    continue
                amount = -part['amount']
                spent[part['category']] += amount
                # Mantém o valor na lista de categorias para organização, mas
                # só grupos atribuídos participam dos indicadores do orçamento.
                if mapping.get(part['category'], UNASSIGNED) == UNASSIGNED:
                    continue
                if row['kind'] == 'Conta corrente':
                    cash += amount
                else:
                    card += amount
        configured_income = self.planning_income(month)
        planning_income = configured_income if configured_income is not None else 0
        planned = self._planned_amounts(planning_income, goals)
        by_group = defaultdict(int)
        for category, value in spent.items():
            by_group[mapping.get(category, UNASSIGNED)] += value
        groups = [dict(id=key, name=name, percent=goals[key], color=color, spent=by_group[key],
                       planned=planned[key], remaining=planned[key]-by_group[key])
                  for key, name, _, color in GOAL_GROUPS]
        assignments = [dict(category=c, group=mapping.get(c, UNASSIGNED), spent=spent[c])
                       for c in self.store.categories() if c != CATEGORIES[-1]]
        total = cash + card
        return dict(month=month, income=income, planning_income=planning_income, income_configured=configured_income is not None,
                    cash=cash, card=card, spent=total, remaining=planning_income-total,
                    groups=groups, assignments=assignments, source=source,
                    unassigned=by_group[UNASSIGNED], transaction_count=len(transactions))
