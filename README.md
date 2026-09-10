# Minhas despesas

Aplicativo desktop local em português, com Python 3 e Tkinter. Sem servidor, cadastro ou conexão com bancos.

## Abrir

Nesta pasta, execute `bash iniciar.sh` ou `python3 app.py`. O Python e o Tkinter estão disponíveis no ambiente em que o aplicativo foi criado.

## Rotina semanal

1. Crie uma conta corrente ou cartão com um nome que identifique o banco.
2. Clique em **Selecionar arquivos para importar** e escolha a conta de destino de cada arquivo.
3. Escolha um OFX, CSV ou a fatura XLSX do Itaú. Para CSV, associe as colunas de data, descrição, valor e, se existir, identificador. O cabeçalho deve estar na primeira linha. Valores devem estar em uma única coluna com sinal; CSV com débito e crédito em colunas separadas precisa ser adaptado.
4. Se as compras do cartão vierem positivas, marque **Inverter sinais**. Confira sempre a prévia: despesa negativa, crédito positivo.
5. Revise duplicatas e confirme a importação. Linhas inválidas impedem a importação inteira, sem salvar parcialmente.
6. Selecione lançamentos para categorizar. Informe um trecho da descrição para aplicar essa categoria automaticamente às próximas importações. A regra mais específica (maior texto) tem prioridade.

Para XLSX, o filtro usa o mês da fatura, preservando a data original de cada compra na tabela. Para OFX/CSV, usa a data do lançamento. Escolha o mês na lista ou use as setas para navegar entre os meses disponíveis. A opção Todos os meses exibe o histórico completo. Ao abrir, o aplicativo seleciona o mês mais recente disponível. A busca consulta a descrição. O resultado exibido é a soma dos lançamentos filtrados, **não o saldo bancário**: não inclui saldo inicial. Estornos aparecem nas entradas/créditos. O XLSX preserva a parcela, o cartão e a titularidade na descrição. A aba Planejamento e faturas mostra vencimento, situação da fatura e projeção de parcelas futuras separada dos lançamentos reais.

## Transferências e cartões

O XLSX reconhece Pagamento Com Saldo e o OFX reconhece FATURA PAGA como pagamento de fatura nas novas importações. Classifique outras transferências entre suas contas e os pagamentos/recebimentos de fatura como **Transferência / pagamento de fatura** nos dois lados. Essa categoria fica fora dos totais de entradas e despesas, evitando contar compras e pagamento da fatura duas vezes. A identificação dessas operações depende da sua revisão ou das regras que cadastrar.

## Duplicatas

- Arquivo idêntico na mesma conta: bloqueado por hash.
- Identificador bancário (FITID ou coluna ID) repetido na mesma conta: ignorado. Mudança de data ou valor no mesmo ID aparece como conflito para revisão; não atualiza automaticamente o registro anterior.
- Mesma data, descrição e valor sem ID coincidente: possível duplicata, excluída por padrão. É possível incluí-la na prévia quando for uma transação legítima distinta. A comparação considera a quantidade de ocorrências para preservar compras iguais no mesmo extrato.
- A identificação por descrição é aproximada: descrições diferentes entre OFX e CSV podem exigir revisão. Prefira manter um formato de extrato para cada conta.

## Dados e backup

Banco SQLite salvo fora da pasta sincronizada do projeto, em `$XDG_DATA_HOME/minhas-despesas/despesas.sqlite3` ou `~/.local/share/minhas-despesas/despesas.sqlite3`. O programa não envia dados pela rede. O arquivo local não é criptografado. Os extratos originais permanecem onde foram selecionados; são armazenados o nome do arquivo, seu hash e os lançamentos normalizados.

Use **Backup** para copiar o banco. Para restaurar, feche o aplicativo, preserve uma cópia do banco atual e substitua o arquivo de dados pelo backup. **Desfazer última importação** remove o último lote global e suas categorizações; regras permanecem.

## Compatibilidade e testes

OFX com blocos STMTTRN, formato SGML ou XML sem namespace; apenas BRL quando a moeda é declarada e uma conta por arquivo. CSV UTF-8, Windows-1252 ou UTF-16 com BOM; separador vírgula, ponto e vírgula ou tabulação. Layouts específicos de bancos ainda precisam ser validados com amostras reais.

Execute `python3 -m unittest discover -s tests -v` nesta pasta para validar importação, centavos, duplicatas, regras e recuperação.

## Fatura XLSX Itaú

Selecione a conta do cartão e importe o XLSX diretamente, sem converter para CSV ou escolher colunas. A tabela é localizada pelo cabeçalho Data / Lançamento / Parcelamento / Valor. Compras positivas no arquivo viram despesas; pagamentos e estornos negativos viram créditos. Pagamentos reconhecidos ficam fora dos totais. O título Fatura Aberta/Fechada define o mês da fatura. Layouts diferentes são rejeitados com mensagem. Não requer instalação de bibliotecas extras.

O banco existente recebe automaticamente uma coluna de mês da fatura, sem excluir lançamentos. Categorias de registros já importados não são alteradas. Os testes com os arquivos fornecidos foram feitos em banco temporário; o histórico pessoal não foi preenchido durante a validação.

## Seleção de vários arquivos na tela inicial

Clique em **Selecionar arquivos para importar** e selecione um ou vários OFX, CSV ou XLSX. Escolha a conta de destino para cada arquivo; o programa sugere a conta corrente para OFX e o cartão para XLSX quando há um único destino do tipo. Revise cada prévia e clique em **Salvar lançamentos no banco SQL**, ou em **Pular este arquivo**. Cada arquivo confirmado é salvo em uma transação SQLite independente; cancelar um arquivo posterior não desfaz os anteriores. Ao terminar, a tela mostra o total salvo, limpa a busca e seleciona o mês mais recente disponível.

O banco SQLite já utilizado pelo aplicativo é mantido: os dados continuam disponíveis ao fechar e reabrir. A localização aparece no rodapé. Nenhum servidor SQL precisa ser instalado.


## Planejamento e faturas

A aba **Planejamento e faturas** contém:

- **Faturas:** situação aberta/fechada, vencimento, total informado, lançamentos líquidos, divisão entre titular e adicional, pagamentos vinculados e restante. O XLSX preenche os dados do cabeçalho. Use **Editar / cadastrar** para informar ou corrigir; dados informados têm prioridade. **Usar dados do extrato** remove a correção manual. Na ausência de total informado, o restante usa os lançamentos disponíveis; uma fatura aberta tem valor parcial. Valores negativos/estornos reduzem o líquido de cada portador.
- **Parcelas futuras:** estimativa dos próximos 12 meses a partir do mês selecionado (ou mês atual quando Todos os meses). Usa a última parcela observada de cada compra e repete seu valor para as seguintes. Não cria lançamentos reais, não considera juros/alterações futuras e não comprova saldo a pagar. Ao importar parcelas posteriores, recalcula a previsão. Compras de mesmo cartão, data, descrição e número de parcelas podem ser indistinguíveis; confira a previsão nesses casos.
- **Conciliação:** todas as contas/períodos. Sugere pagamentos identificados com mesmo valor, sinais opostos e até três dias entre conta corrente e cartão. Revise e escolha a fatura efetivamente paga, que pode ser anterior ao XLSX onde o pagamento aparece. Um pagamento só pode ser associado uma vez. A opção Sem vínculo de fatura relaciona os dois lançamentos, mas não abate uma fatura. Desfazer vínculo restaura as categorias anteriores. Para editar um pagamento conciliado, desfaça primeiro o vínculo.
- **Orçamento:** limite por categoria e mês, consolidado em todas as contas, com gasto, disponível e percentual utilizado. Um disponível negativo indica estouro. Escolha um mês no filtro superior; o filtro de conta/titularidade/busca não altera o orçamento consolidado.
- **Comparação:** despesas por categoria no mês selecionado e no mês calendário anterior, com diferença absoluta e percentual. Respeita conta e titularidade; não usa a busca textual. Ausência de extrato no mês anterior não comprova ausência de gastos.
- **Regras:** criar, editar e excluir regras. Aplicação ao histórico é opcional e afeta somente lançamentos sem categoria. A regra com maior texto tem prioridade.

Na aba **Transações**, use **Novo lançamento** ou **Editar lançamento**. Despesas são negativas, créditos positivos. O mês de fatura é opcional e só se aplica a cartões. A conta de um lançamento importado não pode ser alterada; valores originais ficam preservados para detecção de reimportação. Lançamentos manuais não pertencem aos lotes de importação.

## Titular e cartão adicional

O filtro **Gastos de** separa Titular e Adicional no dashboard e na tabela; conta corrente sem titularidade fica fora desses filtros. O XLSX preenche titularidade, nome do portador e final do cartão. A fatura e o pagamento ficam consolidados na mesma conta do cartão, sem separar em contas bancárias diferentes. A tela Faturas também discrimina os valores líquidos por titularidade. Previsões e orçamentos são consolidados por conta/conjunto de contas conforme descrito acima; a descrição das parcelas identifica o adicional.

Registros antigos que já têm Titular/Adicional na descrição recebem essa identificação na atualização do banco. Reimporte o XLSX antigo uma vez para preencher vencimento, total, situação e nomes que não estavam armazenados: os lançamentos repetidos não são criados novamente. Extratos antigos sem identificação precisam de correção manual. A interface indica A conferir/Não informado quando não há dados suficientes.

## Atualização do banco

As novas tabelas são criadas no banco SQLite existente sem excluir o histórico. Dados de fatura extraídos ficam ligados ao lote de importação; desfazer o lote recupera os metadados da importação anterior. Correções manuais de fatura e regras permanecem. Reimportar uma fatura com metadados novos pode salvar um lote com zero lançamentos novos. Não foi implementado backup automático; o botão Backup continua manual.


## Dashboards separados

No seletor superior, escolha **Conta corrente** ou **Cartão de crédito**. Selecionar uma conta específica também muda o dashboard automaticamente. A opção Todas reúne apenas contas do tipo do dashboard, sem misturar conta corrente e cartão. A lista de meses e a tabela acompanham esse tipo.

- Conta corrente: entradas e saídas reais do extrato, incluindo transferências e pagamentos de fatura, movimentação líquida e pendências de categorização. Gráficos de saídas por categoria e por dia. A movimentação líquida não é o saldo bancário, pois não considera saldo inicial. O filtro de titularidade fica desabilitado.
- Cartão: compras e estornos/créditos conforme os filtros; total e restante das faturas consolidados por mês e cartão. Os dois indicadores de faturas ignoram busca e titularidade para manter titular e adicional no mesmo pagamento. Faturas abertas têm total parcial; sem metadados, usa-se o valor dos lançamentos. O restante depende dos pagamentos vinculados na Conciliação. Gráficos de compras por categoria e titularidade.

## Excluir conta ou cartão

Escolha uma conta/cartão no filtro e clique em **Excluir conta / cartão**. A confirmação informa os lançamentos, importações e faturas afetados. A exclusão apaga os dados dessa conta e desfaz as conciliações relacionadas, restaurando a categoria do lançamento da outra conta. Outras contas, regras e orçamentos globais permanecem. Os arquivos originais de extrato não são apagados.

A exclusão não possui desfazer no aplicativo; restauração exige backup manual anterior ou reimportação dos extratos. Nenhuma conta real é excluída apenas por instalar a atualização. Contas excluídas não são recriadas ao reiniciar.


## Aparência e gráficos

A interface usa fundo claro, painéis brancos e uma paleta discreta em verde. No dashboard, escolha **Barras**, **Rosca** ou **Evolução** em Visualização. Barras comparam os valores; rosca mostra a participação de cada grupo (categorias menores reunidas em Demais itens); evolução mostra entradas/créditos e saídas/compras por data, preenchendo dias sem lançamentos com zero no intervalo observado.

No cartão, Evolução usa a data original da compra, inclusive para parcelas; o recorte continua sendo o mês de fatura selecionado. Ela não representa uma previsão de caixa. O dashboard tem rolagem vertical para manter os gráficos legíveis em janelas menores. Os filtros de conta, mês e titularidade permanecem disponíveis.


## Navegação lateral e aparência desktop

A versão atual usa navegação lateral para Visão geral, Contas, Cartões, Transações, Faturas, Parcelas futuras, Conciliação, Orçamentos, Comparação e Regras. As ações de cadastrar/excluir conta, desfazer importação e backup manual ficam na parte inferior da barra. A importação permanece no cabeçalho e a categorização fica na tela Transações.

O visual foi inspirado na apresentação desktop do Minhas Finanças (https://minhasfinancas.app.br/desktop): fundo azul-claro, painéis brancos, destaque azul na navegação e cores para indicadores. O aplicativo mantém sua implementação local e não utiliza logotipos ou imagens do serviço de referência.

O dashboard também traz Resumo por conta, com entradas/créditos, saídas/compras e movimento líquido no recorte selecionado. Movimento líquido não é saldo bancário. A tabela acompanha os filtros e a separação entre conta corrente e cartão; pagamentos de fatura entram nas saídas da conta, enquanto o cartão exclui a categoria de pagamento/transferência das compras.


## Modo escuro

Ative **Modo escuro** no topo do menu lateral. A mudança se aplica aos painéis, tabelas, gráficos e formulários do aplicativo. A preferência é salva no banco local e restaurada ao reabrir. Desmarque para voltar ao modo claro. Diálogos nativos do sistema, como seleção de arquivos, podem seguir o tema do sistema operacional.
