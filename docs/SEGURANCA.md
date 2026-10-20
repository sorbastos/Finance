# Segurança do aplicativo local

## Proteções implementadas em 20/10/2026

- Todos os componentes Text próprios usam Text.PlainText. Seletores também usam
  texto simples no valor atual e nas opções, impedindo interpretação de HTML ou
  carregamento de imagens referenciadas em descrições importadas.
- Importações OFX/CSV/XLSX têm limite de 20 MB. A leitura é limitada a esse teto
  mais um byte; o tamanho informado pelo arquivo não é a única proteção.
- XLSX continua limitado a 50 MB descompactados e não executa macros ou fórmulas.
- Em POSIX, banco e backups são criados/restringidos a 600. O diretório dedicado
  minhas-despesas usa 700. Links simbólicos no arquivo de destino são rejeitados,
  e backups não podem sobrescrever o banco de origem por um hard link.
- PySide6, Essentials, Addons e shiboken6 são fixados em 6.12.0. Os pacotes PDF
  e WebEngine, agora dependências do pacote completo, também têm versões fixadas.
  A aplicação não instancia navegador nem usa esses módulos para importar dados.
- Os commits locais pendentes usam endereço noreply; a configuração é exclusiva
  deste repositório. A revisão preservou o conteúdo dos commits e excluiu o
  relatório pessoal do histórico destinado ao envio.

## Orientações para manutenção

AGENTS.md deve ser versionado: contém padrões de desenvolvimento, não segredos.
Não inserir nele caminhos pessoais, dados bancários, tokens ou credenciais.
Manter extratos, bancos, backups, capturas e relatórios pessoais fora do Git.
Não usar dados financeiros reais em testes ou reproduções de problemas.

As permissões de arquivo não são criptografia. Proteção contra perda/roubo do
computador depende também da segurança da conta e do armazenamento do sistema.
Atualizações de dependências devem ser consultadas em fontes oficiais e testadas
antes da troca; versões fixadas não substituem acompanhamento de vulnerabilidades.
Nenhum backup automático é criado por essas proteções.

## Referências verificadas

- [Qt Text: tratamento de conteúdo não confiável](https://doc.qt.io/qt-6/qml-qtquick-text.html)
- [Avisos de segurança Qt](https://wiki.qt.io/List_of_known_vulnerabilities_in_Qt_products)

A CVE-2026-101201 inclui Qt 6.11.2 entre as versões afetadas; a atualização
substitui esse runtime. Isso não equivale a afirmar que o aplicativo não possa
ter outras vulnerabilidades ou que todos os caminhos dessa CVE fossem usados.

## Validação

122 testes aprovados com Qt 6.12.0, incluindo renderização nos dois temas,
marcação literal em células/seletores, limite de leitura, permissões POSIX,
preservação do banco e rejeição de destinos de backup por links. Bancos de teste
são temporários e sintéticos. Nenhum dado pessoal foi usado como fixture.
