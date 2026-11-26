#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PY_BIN=""
for candidate in python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PY_BIN="$candidate"
    break
  fi
done

if [ -z "$PY_BIN" ]; then
  echo "Erreur : Python 3.10 à 3.12 est requis (https://www.python.org/downloads/)."
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "Création de l'environnement Python avec $PY_BIN..."
  "$PY_BIN" -m venv .venv
  echo "Installation des dépendances (une seule fois)..."
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
fi

exec .venv/bin/python frankleboeuf.py
