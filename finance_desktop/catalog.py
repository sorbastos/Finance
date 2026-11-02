"""Metadados das telas e ações; os identificadores são contratos com o QML."""

PAGES = [
    dict(id='accounts', title='Contas', group='VISÃO GERAL', icon='wallet', description='Entradas e saídas das suas contas.'),
    dict(id='cards', title='Cartões', group='VISÃO GERAL', icon='card', description='Compras e faturas consolidadas por cartão.'),
    dict(id='transactions', title='Transações', group='MOVIMENTAÇÕES', icon='list', description='Edite lançamentos e classifique os gastos nas categorias do orçamento.'),
    dict(id='invoices', title='Faturas', group='MOVIMENTAÇÕES', icon='document', description='Titular e adicional reunidos para um único pagamento.'),
    dict(id='closings', title='Fechamento mensal', group='MOVIMENTAÇÕES', icon='check', description='Confira o saldo calculado com o saldo do banco.'),
    dict(id='forecasts', title='Parcelas futuras', group='PLANEJAMENTO', icon='calendar', description='Previsões do mês selecionado, por titularidade.'),
    dict(id='payments', title='Conciliação', group='PLANEJAMENTO', icon='link', description='Confira os dois lançamentos e vincule o pagamento à fatura.'),
    dict(id='budgets', title='Orçamentos', group='PLANEJAMENTO', icon='chart', description='Renda planejada, receitas das contas e gastos reais do mês.'),
    dict(id='comparison', title='Orçamento · Comparação', budgetOnly=True, group='ORÇAMENTO', icon='chart', description='Despesas por categoria comparadas ao mês anterior.'),
    dict(id='rules', title='Orçamento · Regras', budgetOnly=True, group='ORÇAMENTO', icon='settings', description='Classificação automática para o orçamento.'),
    dict(id='categories', title='Categorias', group='ORGANIZAÇÃO', icon='tag', description='Crie, renomeie ou exclua categorias compartilhadas entre conta e cartão.'),
    dict(id='budget_transactions', title='Orçamento · Classificar gastos', budgetOnly=True, group='ORÇAMENTO', icon='list', description='Classifique os lançamentos usados no orçamento.'),
    dict(id='settings', title='Contas e dados', group='ORGANIZAÇÃO', icon='settings', description='Cadastro de contas e backup manual dos dados locais.'),
]

# Cada par liga uma ação estável ao rótulo legível. A execução fica no serviço.
ACTIONS = {
    'categories': [('new_category', 'Nova categoria'), ('edit_category', 'Renomear'), ('delete_category', 'Excluir categoria')],
    'transactions': [('new_transaction', 'Novo lançamento'), ('edit_transaction', 'Editar'), ('categorize', 'Classificar categoria'), ('tags', 'Etiquetas')],
    'budget_transactions': [('categorize', 'Categorizar'), ('split', 'Dividir'), ('clear_split', 'Remover divisão')],
    'invoices': [('invoice', 'Registrar / editar'), ('reset_invoice', 'Usar extrato')],
    'closings': [('closing', 'Registrar / editar')],
    'forecasts': [('installment', 'Ajustar parcelas'), ('delete_forecast', 'Excluir lançamento')],
    'payments': [('reconcile', 'Conciliar'), ('unreconcile', 'Desfazer vínculo')],
    'rules': [('new_rule', 'Nova regra'), ('edit_rule', 'Editar'), ('delete_rule', 'Excluir')],
    'settings': [('new_account', 'Nova conta / cartão'), ('delete_account', 'Excluir conta'), ('undo', 'Desfazer importação'), ('backup', 'Backup manual')],
}
