
# Relatório — migração para PySide6 / Qt Quick

Data: 25/09/2026.

## Entrega

- Nova entrada `finance_desktop`, usando PySide6 com interface QML.
- Ambiente `.venv`, dependências fixadas, instalação e inicialização próprias.
- Camadas separadas para apresentação, controlador, serviço, formatação e importação.
- Componentes comentados, docstrings e orientação permanente em `AGENTS.md`.
- Dashboards separados de conta/cartão, gráficos de barras/rosca/evolução,
  resumo por conta, temas claro/escuro e menu que se adapta à largura.
- Importação OFX/CSV/XLSX com destino, mapeamento CSV, prévia e confirmação.
- Transações, categorias compartilhadas, regras, etiquetas e divisões de valores.
- Faturas, pagamentos conciliados, fechamento, orçamento e comparação mensal.
- Parcelas futuras restritas ao mês selecionado, por titularidade ou juntas.
- Cadastro/exclusão de contas, desfazer importação e backup exclusivamente manual.
- Testes independentes dos dados pessoais e testes de renderização QML.

## Preservação dos dados e código existente

O banco permanece no mesmo caminho. Não há importação automática de extratos,
reset de categorias ou movimentações de dados pessoais. O núcleo financeiro e
os importadores existentes continuam sendo usados, com sua suíte de regressão.
Alterações locais anteriores foram preservadas. Não houve alteração de
`data_regional`, commit ou envio ao GitHub durante esta migração.

Durante a transição de setembro, a interface Tkinter permaneceu disponível.
Em 12/10/2026, ela foi removida junto com seus módulos, inicializador, teste de
gráficos e documentação exclusivos. A interface atual é somente PySide6 / Qt
Quick; as instruções de execução estão no README principal.

## Ajustes verificados durante a migração

- Criar item não reaproveita a identidade de um item selecionado.
- Comparações não misturam conta corrente e cartão quando “Todas” está selecionado.
- Titularidade “Não informado” encontra registros sem identificação.
- Etiquetas inválidas são rejeitadas antes de criar/editar uma transação.
- Destino de importação é validado também no serviço, além do seletor visual.
- Erros de formulário mantêm os campos abertos para correção.
- Objetos QML são destruídos antes do controlador, evitando bindings nulos no encerramento.
- A conexão temporária do backup manual passa a ser fechada explicitamente.

## Limites e próximas manutenções

Processamento e consultas ainda ocorrem na thread principal, como no aplicativo
anterior. A tabela virtualiza as linhas visíveis, mas relatórios fazem consultas
em memória; bases muito grandes podem exigir paginação e parsing assíncrono.
Não foi adicionado backup automático. A migração não muda as limitações dos
layouts bancários nem a natureza estimada das parcelas futuras.

Validação em Linux, por ambiente virtual: suíte financeira existente, casos de
uso da interface nova, abertura QML, formulários, temas claro/escuro, janelas
largas/estreitas e três modos de gráfico. Capturas de revisão usam dados fictícios.
