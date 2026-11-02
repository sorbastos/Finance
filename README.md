# Finance — Minhas despesas

Aplicativo desktop local em português para contas e cartões, com **Python,
PySide6 / Qt Quick e SQLite**. Importa OFX, CSV e faturas XLSX do Itaú. Funciona
sem servidor, cadastro ou conexão com bancos. A interface utiliza exclusivamente
PySide6 / Qt Quick.

## Instalar e abrir

Na pasta do projeto, com Python 3.10 ou superior disponível:

```bash
bash instalar.sh
bash iniciar.sh
```

O instalador cria `.venv` e instala as versões fixadas em `requirements.txt`.
O Python global é usado **somente para criar o ambiente virtual**. A execução e
as dependências ficam dentro da `.venv`, sem `sudo pip` ou pacotes globais.
Não é preciso ativar o ambiente manualmente. Na primeira instalação é necessário
acesso à internet; o aplicativo funciona localmente depois disso.

Validado em Fedora Linux, Python 3.14 e PySide6 6.12.0. Em outro sistema, a
disponibilidade das bibliotecas gráficas Qt precisa ser verificada. Se mover a
pasta do projeto, recrie a `.venv`: ambientes virtuais não são portáveis.

## Rotina de uso

1. Em **Contas e dados**, cadastre a conta corrente e o cartão. Na primeira
   execução com banco novo, duas contas Itaú são criadas como ponto de partida.
2. Clique em **Importar arquivos**. Selecione um ou vários OFX, CSV ou XLSX.
3. Revise a conta de destino de cada arquivo. Para CSV, associe as colunas de
   data, descrição e valor; a coluna ID é opcional. Há opção de inverter sinais.
4. Confira a prévia e clique em **Confirmar importação**. Compras são negativas,
   créditos positivos. Possíveis duplicatas ficam excluídas por padrão.
5. Em **Transações**, selecione linhas para categorizar, editar, dividir valores
   entre categorias ou adicionar etiquetas. Ctrl + clique seleciona várias;
   clique duplo abre a edição. **Categorias** cria e renomeia categorias para
   contas e cartões. **Regras** automatiza a categorização por descrição.

Ao editar um lançamento importado, **Descrição** contém o texto original do banco,
é exibida somente para leitura e pode ser copiada. Use **Estabelecimento** para
dar um nome mais claro à compra. As duas aparecem na tabela de transações e a
busca encontra ambas. A descrição bancária fica protegida também no SQLite.
Reimportações, identificação das parcelas e regras continuam usando o original,
mesmo que o nome personalizado não contenha a numeração das parcelas.

Na atualização, lançamentos já editados recuperam a descrição do banco a partir
do histórico original salvo, preservando o nome personalizado atual. Para os
demais importados, o texto atual é preservado como original. Lançamentos manuais
têm apenas a descrição editável, sem atribuir um texto fictício ao banco.

Ao salvar a edição de um lançamento, a tabela mantém a posição vertical,
horizontal e a seleção das linhas que continuam no resultado. Assim é possível
continuar trabalhando no mesmo trecho. Trocar filtros ou telas atualiza a consulta
normalmente; se uma edição retirar a linha do filtro atual, ela deixa a lista.

Use **Ajustar colunas** para adaptar as larguras aos títulos e textos da tabela.
Também é possível arrastar a borda direita de um cabeçalho ou dar duplo clique
nessa borda para ajustar somente aquela coluna. O botão direito no cabeçalho
oferece alinhamento à esquerda, ao centro ou à direita; título e células seguem
a mesma opção. Valores monetários começam alinhados à direita. Os ajustes são
mantidos durante a sessão para cada conjunto de colunas, inclusive após editar.

Nenhuma linha é salva durante a prévia. Cada arquivo confirmado é salvo em uma
transação SQLite independente. Cancelar um arquivo posterior não desfaz os
anteriores. **Desfazer importação**, em Contas e dados, remove o último lote
global, preservando regras e correções manuais de faturas.

Para importar somente parte do arquivo, clique nas linhas desejadas na prévia;
use **Ctrl + clique** para selecionar várias. Há botões **Selecionar todos** e
**Limpar seleção**. Clique em **Importar selecionados (N)** e confira a seleção
na confirmação. **Importar arquivo completo** mantém o comportamento anterior.
Importações parciais gravam apenas os lançamentos selecionados e preservam os
totais/metadados da fatura. É possível importar outras linhas depois, inclusive
complementando um arquivo anteriormente processado. IDs repetidos e conflitos
continuam bloqueados; possíveis duplicatas só entram quando explicitamente
autorizadas. Uma seleção já processada não é salva novamente.

O XLSX reconhece também créditos **Pagamento Boleto** como pagamento de fatura.
Após importar um pagamento referente ao mês anterior, use **Conciliação** para
conferir o débito da conta e vincular o crédito à fatura efetivamente paga.

## Dashboards e filtros

**Contas** mostra entradas, saídas e movimentação líquida, incluindo pagamentos
de fatura e transferências. Movimentação líquida não é saldo bancário: para isso,
informe o saldo inicial em **Fechamento mensal**.

**Cartões** separa compras e estornos dos pagamentos de fatura. O filtro de
titularidade permite consultar Titular, Adicional, Não informado ou todos juntos.
Os indicadores de faturas sempre consolidam titular e adicional para pagamento.

O mês é selecionado pela lista, sem digitação. Para XLSX, o período corresponde
ao mês da fatura; para conta corrente, à data do lançamento. Há filtros por
conta e descrição. Os dashboards oferecem **Barras**, **Rosca** e **Evolução**,
com legendas explícitas e resumo por conta. A evolução usa a data original de
cada compra, mesmo quando ela é parcelada; não representa fluxo de caixa futuro.

O menu reduz sua largura em janelas menores e tem rolagem própria. O conteúdo
também rola sem esconder os filtros. **Modo escuro/claro** fica no rodapé do menu
e a preferência é preservada entre execuções. Não há dicas ao passar o ponteiro.

## Planejamento e conferência

| Tela | Uso |
| --- | --- |
| Faturas | Vencimento, situação, total informado, titular/adicional, pagamentos vinculados e restante. Dados manuais têm prioridade; “Usar extrato” remove essa correção. |
| Parcelas futuras | Somente o mês selecionado, por titularidade ou juntos. Permite corrigir parcelas, antecipar ou cancelar a previsão sem alterar lançamentos reais. |
| Conciliação | Sugestões de débito na conta e crédito no cartão com valores iguais e até três dias de diferença. Revise e vincule à fatura efetivamente paga. |
| Fechamento mensal | Saldo inicial + movimentação comparado ao saldo final informado pelo banco. |
| Orçamentos | Renda editável para metas, receitas das contas para conferência e gastos da conta/cartão. |
| Comparação | Despesas por categoria contra o mês anterior, respeitando tipo, conta e titularidade; não aplica a busca textual. |
| Regras | Texto da descrição → categoria. Aplicação ao histórico é opcional e limitada aos sem categoria. |

### Orçamento doméstico e renda planejada

Escolha o mês em **Orçamentos**. A aba **Orçamento doméstico** mostra renda planejada,
gastos líquidos, disponível no orçamento e percentual da renda utilizado,
além de gráfico por grupo e resumo do gasto, planejado e disponível por meta.
Use **Definir renda** ou **Editar renda** para informar o valor mensal que será
usado exclusivamente nas metas, percentuais e disponível do orçamento.
Esse valor é salvo para cada mês, não cria transações e não é substituído por
novas importações. Renda de um mês não é herdada automaticamente por outro.
Sem renda definida, as metas em reais ficam zeradas e os percentuais de uso
não são calculados, mesmo quando existem receitas importadas.

- **Receitas nas contas:** entradas positivas das contas correntes, excluindo
  Transferência / pagamento de fatura. Esse indicador é automático e serve
  somente para conferência; não é saldo bancário nem base das metas.
- **Renda do orçamento:** valor manual definido para o mês. É a única base
  utilizada na distribuição das metas e no percentual utilizado.
- Gastos: saídas das contas e compras dos cartões, incluindo titular e adicional.
  Créditos/estornos do cartão abatem os gastos líquidos da categoria correspondente.
- Pagamentos de fatura e transferências classificados na categoria de sistema
  ficam fora do cálculo dos dois lados, evitando contar compra e pagamento juntos.
- Conta corrente usa o mês da data do lançamento; cartão usa o mês da fatura.
  Projeções futuras não entram como despesas realizadas.
- Divisões de transações são respeitadas. O disponível é renda manual menos gastos,
  não o saldo bancário. Confira categorias e importações para evitar omissões.

Em **Minhas metas**, ajuste os percentuais pelos controles deslizantes ou pelo
campo numérico. A distribuição inicial sugerida é: Custos fixos 30%, Conforto
15%, Metas 15%, Prazeres 10%, Liberdade financeira 25%, Conhecimento 5% e Reserva
de emergência 0%. A soma precisa ser **100%** antes de salvar. Os valores em
reais são distribuídos a partir da renda manual, com arredondamento em
centavos cuja soma corresponde exatamente à renda.

As metas salvas valem a partir do mês escolhido, até outra configuração. Meses
anteriores não herdam metas do futuro. Os gastos continuam sendo dados reais;
metas de investimento ou poupança não criam movimentações automaticamente.

Em **Categorias**, associe categorias aos grupos de metas. A lista tem colunas
alinhadas para categoria, grupo, gasto do mês e ação, com busca por nome e filtro
por grupo. As
associações valem globalmente e não alteram as categorias dos lançamentos.
Algumas categorias comuns recebem uma sugestão inicial; as demais ficam em
**Não classificado**, fora dos totais, gráficos e porcentagens do orçamento até
serem associadas a uma meta. Seus valores continuam visíveis em Categorias para
conferência e organização. A exclusão também vale para partes de transações
divididas e para estornos sem grupo. Renomear
uma categoria preserva o vínculo. A seção de limites adicionais foi removida
da interface; o planejamento é feito pelas metas percentuais.

Sem renda manual no mês, o painel mostra essa condição e não inventa percentuais de
uso. Estornos acima das compras podem resultar em gasto líquido negativo;
a tabela mostra esse crédito e o gráfico inclui apenas grupos com gasto positivo.

Em **Parcelas futuras**, use as setas para trocar de mês ou escolha o mês pelo
nome na lista. Os botões **Todos juntos**, **Titular**, **Adicional** e **Não
informado** mostram a quantidade de previsões. Os cartões mantêm os subtotais
de todos os portadores no mês; o cabeçalho da tabela informa o total do filtro.
A numeração da parcela tem coluna própria.

Para retirar uma previsão duplicada, selecione uma linha e clique em **Excluir
lançamento**, ao lado de **Ajustar parcelas**. Confira descrição, portador e
valor na confirmação. Escolha **Somente a parcela deste mês** ou **Todas as
previsões deste lançamento**. A exclusão afeta as projeções e os totais das
faturas futuras; a compra já importada continua no histórico. A decisão fica
salva no SQLite e vinculada ao lançamento de origem; uma nova origem importada
é avaliada separadamente.

Em **Faturas**, meses que só possuem parcelas projetadas aparecem como
**Prevista**. Há uma linha por cartão e mês, reunindo titular e adicional.
**Total estimado** soma lançamentos disponíveis e parcelas previstas, sem somar
novamente o **Total informado** no arquivo. São bases distintas: o extrato pode
ter um total informado diferente do conjunto de lançamentos disponível.
**Restante confirmado** mantém apenas o cálculo da fatura importada/cadastrada.
Uma previsão não cria compras nem valores de fatura no SQLite.

Para evitar duplicar previsões, a parcela mais recente substitui as etapas
anteriores da mesma compra. Repetições sem ID entre lotes usam a maior quantidade
observada em um lote, sem somar reimportações. Compras iguais no mesmo lote e
compras com IDs bancários diferentes são preservadas. Titular, portador e cartão
participam da identificação. Sem identificadores suficientes, compras idênticas
em arquivos distintos podem ser indistinguíveis e precisam de conferência.

Faturas abertas têm valores parciais. O restante depende de pagamentos
conciliados. Pagamentos no XLSX podem se referir à fatura anterior. Previsões
não são lançamentos nem comprovação do valor futuro a pagar. Compras com mesma
data, descrição, cartão e quantidade de parcelas podem ser indistinguíveis.

## Formatos e duplicatas

- OFX: blocos STMTTRN em SGML/XML sem namespace, uma conta por arquivo e BRL.
- CSV: UTF-8, Windows-1252 ou UTF-16 com BOM; cabeçalho na primeira linha,
  separador vírgula, ponto e vírgula ou tabulação. O valor precisa estar em uma
  única coluna com sinal; colunas separadas de débito/crédito exigem adaptação.
- XLSX Itaú: cabeçalho Data / Lançamento / Parcelamento / Valor, títulos de
  fatura Aberta, Fechada ou Paga. Preserva competência, portador e cartão.
- Mesmo arquivo na mesma conta é bloqueado por hash. IDs bancários repetidos
  são ignorados; conflitos não atualizam o histórico automaticamente.
- Sem ID, data/descrição/valor iguais geram possível duplicata. A revisão pode
  permitir compras distintas iguais. Prefira o mesmo formato para cada conta.

Linhas inválidas impedem a gravação do arquivo inteiro. Novos layouts precisam
ser validados antes de ampliar os importadores.

## Dados e segurança

O banco existente é preservado em
`$XDG_DATA_HOME/minhas-despesas/despesas.sqlite3` ou
`~/.local/share/minhas-despesas/despesas.sqlite3`. Não fica na pasta sincronizada
do código. O aplicativo não envia dados pela rede; SQLite local não é criptografado.

**Backup manual**, em Contas e dados, usa a API do SQLite. Para restaurar, feche
o aplicativo, preserve o banco atual e substitua-o pelo backup. Não há backup
automático. **Excluir conta** mostra impacto e pede confirmação; afeta somente
a conta selecionada e seus vínculos. Não há desfazer dessa exclusão.

Não publique `.venv`, bancos, extratos, backups, credenciais ou capturas pessoais.
O `.gitignore` local já protege esses padrões. Revise o conteúdo preparado antes
de qualquer commit, mesmo em repositório privado.

## Desenvolvimento e testes

```bash
.venv/bin/python -m pip check
.venv/bin/python -m unittest discover -s tests -v
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software .venv/bin/python -m finance_desktop --database /tmp/finance-teste.sqlite3 --smoke-test
```

Os testes usam dados sintéticos. `--database` permite desenvolvimento isolado.
`--smoke-test` e `--screenshot` exigem um banco explicitamente escolhido, para
evitar abrir dados pessoais por acidente. A suíte usa `unittest` e QtTest, já
disponíveis com o Python e as dependências de `requirements.txt`.

Leia [Arquitetura](docs/ARQUITETURA.md), [Migração Qt](docs/MIGRACAO_QT.md) e
[Orientações de manutenção](AGENTS.md).

### Edição de compras parceladas

Ao editar uma parcela, mudanças em **Estabelecimento**, **Categoria** e
**Etiquetas** também valem para as parcelas seguintes da mesma compra. O vínculo
considera a descrição original, data da compra, valor, número total de parcelas,
conta, portador e final do cartão. Meses anteriores permanecem como estavam.
Próximas importações herdam as alterações; ajustes feitos em um mês posterior têm
prioridade a partir daquele mês. A descrição bancária, valores, datas e números
das parcelas não são propagados. Compras idênticas no mesmo mês não são vinculadas
automaticamente. Categorias de parcelas com rateio ou pagamento conciliado são
preservadas e precisam ser ajustadas pelo fluxo próprio.

### Categorias de transação vinculadas ao orçamento

Classifique conta e cartão usando **Alimentação, Mercado, Transporte, Moradia,
Saúde, Educação, Lazer, Compras, Serviços** ou categorias que você cadastrar.
Em **Transações → Classificar categoria**, selecione um ou vários lançamentos.
Em **Orçamentos → Categorias → Alterar grupo**, vincule cada categoria a **Custos
fixos, Conforto, Metas, Prazeres, Liberdade financeira, Conhecimento** ou **Reserva
de emergência**. O vínculo é global e atualiza todos os meses, sem duplicar gastos.
Categorias sem vínculo continuam fora dos totais até serem associadas.

Use **Gerenciar categorias** para criar ou renomear; o vínculo acompanha a
renomeação. As regras de importação e as parcelas seguintes continuam usando a
categoria da transação. A renda manual e os percentuais permanecem independentes.

A primeira abertura restaura o catálogo sem reclassificar o histórico. Categorias
já convertidas para nomes de grupos ficam disponíveis e vinculadas ao mesmo grupo
para preservar os totais. Não é possível recuperar exatamente classificações
específicas removidas pela conversão anterior; ajuste esses lançamentos conforme
necessário. Valores, datas e descrições são mantidos.

### Menu de mês e titularidade

Contas, Cartões, Transações, Faturas, Fechamento mensal, Comparação e Classificar
 gastos usam o mesmo menu com setas de mês das Parcelas futuras e do Orçamento.
Você pode navegar para meses sem lançamentos; a seleção mostra o mês consultado.
Nas consultas que já permitiam consultar todo o histórico, Todos os meses continua
disponível. Listas de gastos de cartão usam botões Todos juntos, Titular, Adicional
e Não informado, com contagens que respeitam mês, conta e busca. Faturas e
Orçamentos mantêm os totais consolidados dos portadores.

### Gerenciar categorias

No menu lateral, abra **Categorias**. Use **Nova categoria** para cadastrar ou
selecione uma linha e escolha **Renomear** ou **Excluir categoria**. Para excluir,
confirme qual categoria receberá os lançamentos, regras, rateios e vínculos de
parcelas. Nenhum lançamento é apagado. O grupo do orçamento da categoria de
destino passa a valer; partes do mesmo gasto que convergirem são somadas.
As categorias internas Sem categoria e Transferência / pagamento de fatura são
protegidas. O vínculo com os grupos continua em **Orçamentos → Categorias**.

### Proteções de segurança

Os dados exibidos são tratados como texto simples, inclusive nos seletores:
marcações contidas em descrições e nomes não carregam imagens externas. Cada
arquivo importado tem limite de **20 MB**, validado antes e durante a leitura;
planilhas XLSX mantêm também o limite de **50 MB descompactados**.

Em Linux/POSIX, o banco e os backups são criados com permissão **600** (somente
seu usuário); o diretório dedicado do aplicativo usa **700**. Bancos existentes
têm as permissões restringidas ao abrir, sem alterar o conteúdo. Diretórios
genéricos escolhidos pelo usuário não têm suas permissões modificadas. Essas
permissões não são criptografia e não protegem contra acesso pela mesma conta
ou por administrador do sistema. Veja [Segurança](docs/SEGURANCA.md).
