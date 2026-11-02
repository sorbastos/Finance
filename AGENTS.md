# Orientações permanentes de desenvolvimento

## Arquitetura

- Instale e execute sempre pelo ambiente `.venv` do projeto. O Python do sistema
  serve apenas para `python3 -m venv .venv`; nunca instale dependências globalmente.
- Declare dependências com versões fixadas em `requirements.txt`. Atualmente não
  existem dependências adicionais exclusivas de desenvolvimento.
- Use `bash instalar.sh`, `bash iniciar.sh` e `.venv/bin/python -m unittest`.

- A interface principal é PySide6 / Qt Quick (pacote `finance_desktop`).
- QML apresenta dados e encaminha ações. Não contém SQL, cálculo monetário nem regras financeiras.
- Serviços Python independentes de Qt coordenam consultas, validações e gravações.
- `core.py`, `finance.py` e `xlsx_itau.py` continuam responsáveis por armazenamento,
  domínio e importadores. A apresentação usa exclusivamente PySide6 / Qt Quick;
  não reintroduza a interface Tkinter nem dependências exclusivas dela.
- Valores monetários são inteiros em centavos. Evite conversão financeira por `float`.
- `bank_description` é o texto bancário imutável; `description` é o nome
  personalizado. Use o original para deduplicação e identificação de parcelas.
- Não mude a localização do banco existente sem migração explícita e testada.

## Legibilidade e comentários (pedido do usuário)

- Escreva docstrings em português para módulos, classes e funções novas, explicando
  responsabilidade, contratos, efeitos persistentes e limitações relevantes.
- Use nomes claros, anotações de tipos e funções pequenas com uma responsabilidade.
- Comente decisões, invariantes financeiras e casos não óbvios. Não narre cada atribuição.
- Comente componentes QML, explicando dados de entrada, sinais e decisões de layout.
- Ao alterar comportamento, atualize documentação e testes relacionados na mesma entrega.
- Centralize paleta, componentes e formatação; não copie estilos entre telas.

## Dados e validação

- Testes e capturas usam bancos temporários e dados sintéticos; nunca altere o banco
  real para testar. Não versione extratos, bancos, logs com dados pessoais ou backups.
- Importação exige escolha de conta, prévia e confirmação. Exclusões exigem confirmação
  com alvo e impacto concretos. Nenhum backup automático ou tooltip deve ser adicionado.
- Preserve alterações locais existentes. Commit e publicação somente quando pedidos.
- Execute a suíte de domínio e a suíte Qt, incluindo abertura do QML nos dois temas.

Consulte `docs/ARQUITETURA.md` e `docs/MIGRACAO_QT.md` antes de ampliar a interface.

## Segurança

- Dados de arquivos e textos do usuário devem ser exibidos como Text.PlainText,
  inclusive nos delegates e no conteúdo dos seletores QML.
- Use security.read_import_file para preservar o limite de 20 MB antes/durante
  a leitura. Não substitua por read_bytes sem limite.
- Preserve a criação privada de bancos/backups em security.prepare_private_database.
- Não versione relatórios pessoais nem credenciais; mantenha o endereço noreply
  nos novos commits deste repositório.
