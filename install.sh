#!/usr/bin/env bash
# Arch's Auto Clipping - Installation (Linux / macOS)
set -euo pipefail
cd "$(dirname "$0")"

echo "============================================"
echo "  Arch's Auto Clipping - Installation"
echo "============================================"
echo

PYTHON=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      PYTHON="$candidate"
      break
    fi
  fi
done

if [[ -z "$PYTHON" ]]; then
  echo "[ERREUR] Python 3.10+ introuvable dans le PATH."
  echo
  echo "Installez Python en ligne de commande, par exemple :"
  echo "  Debian/Ubuntu:  sudo apt update && sudo apt install -y python3 python3-venv python3-pip"
  echo "  Fedora:         sudo dnf install -y python3 python3-pip"
  echo "  Arch:           sudo pacman -S python"
  echo
  echo "Details: DOCUMENTATION.md"
  exit 1
fi

echo "[OK] Interpréteur: $PYTHON ($($PYTHON --version 2>&1))"
echo

create_venv() {
  if "$PYTHON" -m venv .venv 2>/tmp/arch_clip_venv_err.$$; then
    return 0
  fi
  if command -v uv >/dev/null 2>&1; then
    echo "[INFO] venv standard indisponible, essai avec uv ..."
    rm -rf .venv
    uv venv .venv --python "$PYTHON"
    return 0
  fi
  if command -v virtualenv >/dev/null 2>&1; then
    echo "[INFO] venv standard indisponible, essai avec virtualenv ..."
    rm -rf .venv
    virtualenv -p "$PYTHON" .venv
    return 0
  fi
  echo "[ERREUR] Impossible de créer le venv."
  if [[ -f /tmp/arch_clip_venv_err.$$ ]]; then
    cat /tmp/arch_clip_venv_err.$$
    rm -f /tmp/arch_clip_venv_err.$$
  fi
  echo "Sur Debian/Ubuntu: sudo apt install python3-venv"
  return 1
}

if [[ -x ".venv/bin/python" ]]; then
  echo "[INFO] Environnement virtuel .venv déjà présent."
else
  if [[ -d ".venv" ]]; then
    echo "[INFO] Suppression d'un .venv incomplet ..."
    rm -rf .venv
  fi
  echo "[..] Création du venv dans .venv ..."
  create_venv
  echo "[OK] Venv créé: $(pwd)/.venv"
fi
rm -f /tmp/arch_clip_venv_err.$$ 2>/dev/null || true

VENV_PY="$(pwd)/.venv/bin/python"
if [[ ! -x "$VENV_PY" ]]; then
  echo "[ERREUR] $VENV_PY introuvable après création du venv."
  exit 1
fi

echo
echo "[..] Mise à jour de pip ..."
if ! "$VENV_PY" -m pip install --upgrade pip 2>/dev/null; then
  if command -v uv >/dev/null 2>&1; then
    echo "[INFO] pip via uv ..."
    uv pip install --python "$VENV_PY" --upgrade pip
  else
    echo "[ERREUR] pip indisponible dans le venv."
    exit 1
  fi
fi

echo
echo "[..] Installation des dépendances (requirements.txt) ..."
if ! "$VENV_PY" -m pip install -r "$(pwd)/requirements.txt" 2>/dev/null; then
  if command -v uv >/dev/null 2>&1; then
    echo "[INFO] installation via uv pip ..."
    uv pip install --python "$VENV_PY" -r "$(pwd)/requirements.txt"
  else
    echo "[ERREUR] Échec installation des dépendances."
    exit 1
  fi
fi

mkdir -p files download clips processeds tools

PROJECT_ROOT="$(pwd)"
TOOLS_DIR="${PROJECT_ROOT}/tools"

echo
echo "[..] Téléchargement des binaires Linux dans tools/ (ffmpeg + ffprobe) ..."
echo "      Cible: ${TOOLS_DIR}"

# Préférer le Python du venv ; repli sur le Python système
FETCH_OK=0
if "$VENV_PY" "${PROJECT_ROOT}/scripts/fetch_tools.py"; then
  FETCH_OK=1
else
  echo "[ATTENTION] Échec avec le Python du venv, essai avec ${PYTHON} ..."
  if "$PYTHON" "${PROJECT_ROOT}/scripts/fetch_tools.py"; then
    FETCH_OK=1
  fi
fi

if [[ "$FETCH_OK" -ne 1 ]]; then
  echo "[ERREUR] Échec installation des binaires dans tools/"
  echo "        Alternative manuelle:"
  echo "          sudo apt install -y ffmpeg"
  echo "        ou relancez:  python3 scripts/fetch_tools.py"
  exit 1
fi

# Droits d'exécution (FS partagé Windows parfois sans +x)
if [[ -f "${TOOLS_DIR}/ffmpeg" ]]; then
  chmod +x "${TOOLS_DIR}/ffmpeg" 2>/dev/null || true
fi
if [[ -f "${TOOLS_DIR}/ffprobe" ]]; then
  chmod +x "${TOOLS_DIR}/ffprobe" 2>/dev/null || true
fi

echo
echo "[..] Contenu de tools/ :"
ls -lah "${TOOLS_DIR}" || true

if [[ ! -f "${TOOLS_DIR}/ffmpeg" || ! -f "${TOOLS_DIR}/ffprobe" ]]; then
  echo "[ERREUR] tools/ffmpeg et/ou tools/ffprobe absents après install."
  exit 1
fi

# Test rapide d'exécution
if "${TOOLS_DIR}/ffmpeg" -version >/dev/null 2>&1; then
  echo "[OK] tools/ffmpeg exécutable"
else
  echo "[ATTENTION] tools/ffmpeg présent mais non exécutable (droits / FS?)"
  echo "            Essayez: chmod +x tools/ffmpeg tools/ffprobe"
fi

echo
echo "============================================"
echo "  Installation terminée."
echo "  Arch's Auto Clipping est prêt."
echo "  Lancez le programme avec:  ./run.sh"
echo
echo "  Binaires locaux Linux:"
echo "    ${TOOLS_DIR}/ffmpeg"
echo "    ${TOOLS_DIR}/ffprobe"
echo "============================================"
