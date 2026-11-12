#!/usr/bin/env bash
# Lanzador de Sonora. Crea el entorno virtual si no existe y arranca la app.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

PYTHON="${PYTHON:-python3}"

if [ ! -x ".venv/bin/python" ]; then
    echo "· Creando entorno virtual…"
    "$PYTHON" -m venv .venv
    ./.venv/bin/pip install --upgrade pip >/dev/null
    ./.venv/bin/pip install -r requirements.txt
fi

exec ./.venv/bin/python main.py "$@"
