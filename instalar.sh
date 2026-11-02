#!/usr/bin/env bash
# O Python do sistema apenas cria o ambiente; instalação e execução usam a .venv.
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [[ ! -x .venv/bin/python ]]; then
    python3 -m venv .venv
fi
.venv/bin/python -m pip install --requirement requirements.txt
.venv/bin/python -m pip check
printf '%s\n' 'Instalação concluída. Abra com: bash iniciar.sh'
