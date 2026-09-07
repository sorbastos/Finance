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

Para XLSX, o filtro usa o mês da fatura, preservando a data original de cada compra na tabela. Para OFX/CSV, usa a data do lançamento. O filtro de mês usa AAAA-MM; deixe vazio para todos os meses. A busca consulta a descrição. O resultado exibido é a soma dos lançamentos filtrados, **não o saldo bancário**: não inclui saldo inicial. Estornos aparecem nas entradas/créditos. O XLSX preserva a parcela, o cartão e a titularidade na descrição. Não há projeção automática de parcelas futuras nem controle de vencimento.

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

Clique em **Selecionar arquivos para importar** e selecione um ou vários OFX, CSV ou XLSX. Escolha a conta de destino para cada arquivo; o programa sugere a conta corrente para OFX e o cartão para XLSX quando há um único destino do tipo. Revise cada prévia e clique em **Salvar lançamentos no banco SQL**, ou em **Pular este arquivo**. Cada arquivo confirmado é salvo em uma transação SQLite independente; cancelar um arquivo posterior não desfaz os anteriores. Ao terminar, a tela mostra o total salvo e limpa os filtros para exibir o histórico.

O banco SQLite já utilizado pelo aplicativo é mantido: os dados continuam disponíveis ao fechar e reabrir. A localização aparece no rodapé. Nenhum servidor SQL precisa ser instalado.
