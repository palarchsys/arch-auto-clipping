#!/usr/bin/env bash
# Arch's Auto Clipping - Lancement
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "[ERREUR] Environnement virtuel introuvable."
  echo "Lancez d'abord:  ./install.sh"
  exit 1
fi

exec .venv/bin/python main.py
