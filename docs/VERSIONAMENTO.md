# Arquivos para versionamento e privacidade

Revisão de 20/10/2026, antes do commit da migração Qt e das melhorias financeiras.

## Pode entrar no repositório

| Conteúdo | Finalidade |
| --- | --- |
| `core.py`, `finance.py`, `budgeting.py`, `installments.py`, `xlsx_itau.py` | Código de domínio e importadores, sem dados bancários embutidos |
| `direct_budget.py` | Migração histórica coberta por testes; não é chamada pela inicialização atual |
| `finance_desktop/` | Interface PySide6/QML e serviços |
| `tests/` | Testes e arquivos bancários sintéticos gerados em memória ou em diretórios temporários |
| `requirements.txt` | Dependências reproduzíveis; testes não exigem pacotes adicionais |
| `instalar.sh`, `iniciar.sh` | Instalação em ambiente virtual e inicialização |
| `README.md`, `AGENTS.md`, `docs/` | Instruções e documentação revisadas, sem extratos ou valores pessoais |
| `.gitignore` | Regras compartilhadas para impedir inclusão acidental de arquivos locais |

As exclusões dos módulos da interface Tkinter também pertencem ao commit: o
projeto atual utiliza exclusivamente a interface Qt.

## Deve ficar fora

- Ambiente `.venv`, caches, artefatos de compilação, configurações locais do editor.
- Bancos SQLite/DB e seus arquivos auxiliares, dumps SQL e backups.
- Extratos OFX/CSV, faturas XLS/XLSX, outros arquivos bancários, TSV/ODS e PDFs.
- Pastas de dados, importações, exportações, capturas e logs pessoais.
- Arquivos `.env`, chaves, certificados, credenciais JSON e tokens.
- `data_regional`, que não faz parte deste projeto.

Os arquivos pessoais continuam no computador. Esta revisão não os apaga nem cria
backup automático. O banco usado pela aplicação fica no diretório de dados do
usuário, fora do repositório; testes nunca usam esse banco.

## Resultado da revisão

Não foram encontrados extratos, bancos, backups ou credenciais entre os arquivos
candidatos ao commit. A inspeção dos nomes de arquivos registrados no histórico
local também não encontrou esses formatos. A busca por padrões de credenciais e
referências pessoais nos textos revisados não retornou ocorrências.

A suíte de 118 testes passou, incluindo Qt nos dois temas, e a verificação das
dependências não encontrou incompatibilidades. Esta é uma revisão dos arquivos
locais, não uma garantia sobre arquivos que forem adicionados no futuro.

O `.gitignore` é versionado para proteger também outros clones. Suas regras não
retiram arquivos que já estejam no histórico. A identidade de autor dos commits
(nome/e-mail configurados no Git) integra os metadados: ignorar arquivos não a
oculta. O commit local não publica alterações no GitHub; o envio é uma ação
separada.

O relatório pessoal `RELATORIO_ALTERACOES_*.md` fica somente no computador,
fora dos commits e do envio ao GitHub, protegido pelo `.gitignore`.
