# Arquitetura e manutenção

## Fronteiras

```text
iniciar.sh → .venv/bin/python -m finance_desktop
  __main__.py            ciclo de vida de QApplication / engine / SQLite
  controller.py         sinais, slots, navegação e diálogos nativos
  service.py            consultas de apresentação e casos de uso
  importing.py          arquivo → configuração → prévia → confirmação
  formatting.py         centavos e percentuais sem float financeiro
  catalog.py            identificadores de telas e ações
  qml/                  layout, componentes e estado visual
       ↓
  finance.py            categorias, parcelas, faturas e demais regras
  core.py               SQLite, CSV, OFX e detecção de duplicatas
  xlsx_itau.py          leitura e normalização do XLSX
  budgeting.py          renda planejada, receitas reais e metas por categoria
```

O domínio foi reutilizado para manter comportamento e histórico. A apresentação
usa exclusivamente PySide6 / Qt Quick. Serviços não importam Qt, permitindo
testar regras de apresentação sem janela. A interface Tkinter e seus módulos
exclusivos foram removidos em 12/10/2026.

## Contratos importantes

- Dinheiro é inteiro em centavos até a formatação. QML recebe textos e séries
  numéricas prontas; coordenadas gráficas podem usar ponto flutuante.
- `Filters` descreve o recorte. Conta nula e titularidade vazia representam todos
  dentro do tipo escolhido. “Não informado” representa portador vazio no banco.
- `snapshot()` retorna título, tabela, indicadores, séries e ações. Cada linha
  tem uma identidade estável; nunca grave usando posição visual da tabela.
- `form()` prepara dados sem escrever. `submit()` valida e chama o domínio.
  Operações `new_*` descartam qualquer seleção anterior.
- O controlador só fecha o formulário após sucesso. Erros esperados são
  exibidos localmente; logs de falhas inesperadas não incluem dados de extratos.
- A importação mantém o conteúdo original em memória até confirmar, preservando
  hash e contagem de ocorrências usados na deduplicação. Arquivos posteriores
  sempre recebem confirmação própria.
- SQLite pertence à thread principal. Não compartilhe essa conexão com workers.
  Caso arquivos grandes exijam trabalho assíncrono, mova apenas parsing para o
  worker ou crie conexão independente com estratégia explícita de transação.

## Interface

`BudgetPlanner`, em `budgeting.py`, pertence ao domínio e usa a conexão de
`FinanceStore`. As tabelas `budget_goals` e `budget_goal_groups` armazenam somente planejamento. Metas são conjuntos
mensais completos de percentuais inteiros cuja soma é 100%; o último conjunto
anterior é herdado, sem consultar configurações futuras. Categorias das transações
são vinculadas aos sete grupos de metas em `budget_category_groups`.

O orçamento usa apenas lançamentos reais, exclui transferências/pagamentos,
trata créditos do cartão como abatimentos e respeita divisões. Partes de
categorias sem grupo atribuído não entram em gastos, disponível, gráficos ou
percentuais; permanecem em `assignments` para classificação. O método que
distribui a renda manual usa centavos inteiros e maior resto para manter a soma exata.
`budget_income_settings` armazena a renda editável de cada mês, sem herança.
Receitas das contas (`income`) são informativas; planejamento, percentuais e
disponível usam exclusivamente `planning_income`. Sem configuração, essa base
é zero; não existe fallback automático para as entradas das contas.
O relatório por categoria existente compartilha a mesma base de gastos e é
mantido por compatibilidade com os dados anteriores. Limites adicionais não
são exibidos na interface; o orçamento atual utiliza metas percentuais.
`BudgetPanel.qml` mantém somente o rascunho de percentuais e três visualizações;
`FinanceService.household_budget` fornece indicadores e textos monetários. O
domínio revalida a distribuição mesmo quando o botão de salvar está habilitado.

`Main.qml` coordena layout e tema. `ActionButton`, `AppField`, `AppSelect`,
`AppIcon`, `DataTable`, `ChartPanel` e `EditDialog` centralizam componentes.
Não adicione estilos copiados em várias telas. A tabela usa `ListView` com
virtualização e rolagem horizontal. A seleção segue os IDs da fotografia atual.
Após salvar, a posição e a seleção dos IDs sobreviventes são restauradas;
trocas de consulta invalidam essa restauração. As larguras e os alinhamentos
ficam em memória por conjunto de cabeçalhos durante a sessão. A barra lateral
tem rolagem independente.

Formulários recebem campos com `key`, `label`, `value` e `choices`. O componente
mantém os valores temporariamente e envia JSON ao confirmar. Divisão possui
linhas dinâmicas, mas a soma e os sinais são validados no domínio. Não coloque
SQL nem validação financeira definitiva no JavaScript da interface.

## Como ampliar

1. Defina o caso de uso e a responsabilidade financeira em `finance.py`.
2. Exponha consulta/formulário/operação no serviço e catálogo, conforme necessário.
3. Reutilize componentes QML. Adicione um componente somente com responsabilidade
   visual clara, entradas explícitas e comentário sobre seu contrato.
4. Cubra a regra com dados sintéticos e a integração com sinais Qt quando aplicável.
5. Atualize README e relatório de migração se o fluxo de uso mudar.

Use docstrings em português, tipos e nomes claros. Comentários explicam decisões,
invariantes e limitações; não precisam repetir operações óbvias. Estas orientações
estão registradas também em `AGENTS.md` para alterações futuras.

## Ambiente reproduzível

O ambiente fica em `.venv`, sem herdar pacotes globais. PySide6, Essentials,
Addons e shiboken6 têm versões alinhadas e fixadas em `requirements.txt`.
Atualizações exigem alterar essas versões juntas, reinstalar na `.venv` e rodar
os testes. Não mova uma `.venv` pronta entre diretórios ou computadores.

## Validação

`test_desktop_service.py` cobre filtros, confirmação de importação, duplicatas,
divisões, etiquetas, orçamento, titularidade, exclusão e criação com seleção
residual. `test_desktop_qml.py` carrega a engine real, renderiza telas nos dois
temas/tamanhos, abre formulários e interage com botões. Avisos QML fazem o teste
falhar. A suíte anterior continua cobrindo os importadores e o domínio.

Para capturas exclusivamente sintéticas, defina `FINANCE_TEST_SCREENSHOTS` para
uma pasta temporária ao executar a suíte Qt. Seletores nativos de arquivo seguem
o sistema operacional; testes da engine offscreen não comprovam aparência desses
diálogos nem todos os aspectos de aceleração gráfica no desktop real.

## Metadados de parcelas vinculadas

`installments.InstallmentLinks` usa a conexão do domínio e não inicia commits.
`installment_edits` guarda alterações por identidade original da compra e mês de
vigência. Cada campo herda seu último valor não nulo; etiquetas usam JSON e lista
vazia significa remoção explícita. Categoria acompanha renomeações por FK, e a
exclusão da conta remove as regras. As regras sobrevivem à remoção de um lote,
permitindo reimportação com os mesmos metadados pessoais.

Edição, categorização e etiquetas registram somente campos modificados. Novos
lotes aplicam a herança depois do enriquecimento de portadores e antes do commit.
A identidade usa dados originais, sem aproximação textual; ocorrências múltiplas
no mesmo mês suspendem a propagação para evitar misturar compras legítimas.
Rateios e conciliações impedem propagação de categoria nessas parcelas. Previsões
continuam calculadas, usando o estabelecimento herdado da última parcela real.

## Classificação das transações e ferramentas do orçamento

Páginas com `budgetOnly` no catálogo são ferramentas internas do orçamento e
não aparecem na barra lateral. Consultas internas de
regras, comparação e `budget_transactions` reutilizam o recorte de
tipo/conta/mês/titularidade e as ações de categorização e rateio existentes.
`Main.qml` fornece retorno explícito ao orçamento. Os painéis de conta/cartão e
a prévia não expõem categoria. Transações exibe a coluna e oferece `categorize`,
compartilhando a mesma classificação persistida usada por `BudgetPlanner`.
A edição comum ignora categoria recebida do
formulário: mantém o valor persistido ou usa Sem categoria ao criar. O domínio
usa categorias detalhadas compartilhadas entre conta e cartão.
Os gráficos da visão do período agregam por categoria, com valores e percentuais;
o indicador de pendências de classificação pertence ao menu Orçamentos.


## Histórico: orçamento com sete categorias fixas (substituído em 20/10/2026)

`direct_budget.migrate_categories` executa uma conversão transacional única,
registrada em `domain_migrations`. Traduz categorias antigas pelo vínculo anterior,
atualiza lançamentos, regras, conciliações e heranças de parcelas; agrega rateios
convergentes antes de remover o catálogo antigo. Limites avulsos obsoletos são
removidos. Metas mensais e renda manual permanecem intactas. Falhas revertem a
conversão inteira; a próxima abertura pode tentar novamente.

`BudgetPlanner.mappings()` agora é somente a correspondência fixa nome/identidade
das sete metas. `budget_category_groups` fica vazia e é lida exclusivamente para
converter bases antigas. `Sem categoria` e a classificação de transferências são
marcadores internos, não categorias adicionais de orçamento. Cadastro, renomeação
e associação foram retirados da apresentação; `save_category`/`set_mapping`
rejeitam chamadas antigas. Testes de migração cobrem integridade, idempotência,
rateios, herança de parcelas e rollback em falha sintética.

## Contraste da seleção em tabelas

`DataTable.highlight` deriva da superfície e da cor do texto quando o chamador
não fornece uma cor. No resumo do orçamento, o destaque mistura a superfície
com o dourado do painel. Isso mantém a seleção visível e o texto legível nos
dois temas. A regressão Qt verifica a linha selecionada e contraste mínimo de
4,5:1 entre o texto e seu fundo, sem consultar dados pessoais.

## Menu temporal compartilhado

`Main.qml` reutiliza um único Flow para setas, seleção mensal e botões de portador.
`periodOptions` é o contrato comum de valores AAAA-MM e rótulos localizados;
inclui o mês selecionado mesmo sem dados. Somente telas que aceitam histórico
completo oferecem valor vazio (Todos os meses). Identificadores budget/forecast
foram mantidos para testes e automação existentes.

O serviço calcula `ownerOptions` nas consultas de gastos de cartão a partir dos
mesmos filtros, removendo somente a titularidade. Contagens não encolhem ao clicar
em um portador. Orçamento permanece global; faturas permanecem consolidadas.
Classificar gastos também expõe agora tipo, conta e busca, que já faziam parte do
contrato de consulta, ao lado do menu temporal compartilhado.


## Categorias detalhadas e vínculo ao orçamento — modelo atual

A inicialização de `BudgetPlanner` não chama mais `direct_budget.migrate_categories`.
O marcador `transaction_categories_restored` repõe o catálogo base uma única vez;
isso impede recriar categorias que o usuário renomear depois. Classificações já
convertidas não são inferidas nem apagadas. Seus nomes de grupo permanecem como
categorias compatíveis, vinculadas ao mesmo grupo para conservar os totais.

`budget_category_groups` volta a ser a fonte global de associações. Novas bases
recebem os vínculos sugeridos; `INSERT OR IGNORE` preserva escolhas explícitas,
inclusive Não classificado. Relatórios continuam somando por alocação e excluindo
transferências, pagamentos e categorias sem vínculo. `save_category` atualiza
referências e usa as FKs de associações/heranças de parcelas ao renomear.

O cadastro é acessível pelo orçamento e o formulário `budget_mapping` altera só
o vínculo, nunca as categorias dos lançamentos. A classificação em Transações,
os menus mensais recentes e o contraste do resumo são preservados. Não existe
recuperação exata dos nomes específicos já removidos pela migração histórica.

## Contornos dos campos editáveis

`AppField` e `AppSelect` desenham borda permanente de 1 px nos controles
habilitados e editáveis, misturando a cor do texto com o fundo da paleta. O foco
usa 2 px e a cor de destaque. Campos `readOnly` e controles desabilitados não
recebem esse sinal de edição. O padrão centralizado cobre formulários e rateios,
sem duplicar estilos em cada diálogo; campos bancários originais permanecem
imutáveis. A regressão Qt verifica bordas com/sem foco nos dois temas.

## Ajuste visual de 20/10/2026

A faixa de atalhos de navegação de `BudgetPanel` foi removida por solicitação.
O painel mantém suas três abas internas e os formulários de metas, renda e vínculo
de categorias. A classificação de lançamentos continua acessível em Transações.

## Categorias na visão do período

`FinanceService.dashboard` agrega despesas pelas categorias de `allocations`,
respeitando rateios e filtros. A legenda da série de categorias traz valor e
percentual sobre a soma das saídas do recorte. O cálculo usa Decimal; grupos
menores reunidos em Demais itens usam o total original como denominador.
Créditos/entradas não compõem esse denominador. O gráfico diário e a série de
portadores preservam o comportamento anterior; contas incluem transferências
nas saídas e cartões excluem pagamentos, conforme os indicadores existentes.

## Gerenciamento de categorias pelo menu lateral

`categories` é uma página visível no menu, com criação, renomeação e exclusão.
`delete_category` prepara confirmação com nome, quantidade de lançamentos diretos
e categoria de destino. `FinanceStore.delete_category` transfere referências em
uma transação; soma rateios/limites convergentes, atualiza regras, históricos de
conciliação e heranças de parcelas e só depois remove a categoria. O vínculo do
destino prevalece, sem alterar valores de lançamentos. Marcadores internos e
substituições inválidas são rejeitados. A restauração do catálogo tem marcador
único e não recria a categoria excluída na próxima abertura.

## Segurança de entrada e armazenamento

`security.py` centraliza `read_import_file` (20 MB antes e durante a leitura) e
`prepare_private_database` (600 POSIX, diretório dedicado 700, sem truncar dados).
`Store` aplica a preparação antes de conectar, inclusive no backup. Diretórios
arbitrários existentes não têm suas permissões alteradas. Textos QML próprios,
conteúdo atual e delegates de AppSelect usam explicitamente texto simples.
O conjunto Qt passou para 6.12.0 com testes de regressão; detalhes e limites
estão em SEGURANCA.md. O relatório pessoal permanece fora do versionamento.
