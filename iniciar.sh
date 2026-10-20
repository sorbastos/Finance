#!/usr/bin/env bash
# Falhar claramente evita executar acidentalmente com dependências globais.
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [[ ! -x .venv/bin/python ]]; then
    printf '%s\n' 'Ambiente virtual ausente. Execute: bash instalar.sh' >&2
    exit 1
fi
exec .venv/bin/python -m finance_desktop "$@"
