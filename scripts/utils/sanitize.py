"""Sanitization des noms de fichiers pour Windows / multi-OS."""

from __future__ import annotations

import re

# Caractères interdits sous Windows + contrôles
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

# Marge pour suffixe _start_end.mp4 sous limite 255
_MAX_BASE_LEN = 180


def sanitize_filename(name: str, max_len: int = _MAX_BASE_LEN) -> str:
    """Retourne un nom de fichier sûr, non vide, sans extension forcée."""
    if name is None:
        return "untitled"

    text = str(name).strip()
    text = _INVALID_CHARS.sub("_", text)
    # Espaces / points en fin de nom (interdit Windows)
    text = text.rstrip(" .")
    # Collapses d'underscores multiples
    text = re.sub(r"_+", "_", text)
    text = text.strip("_")

    if not text:
        text = "untitled"

    # Noms réservés Windows (sans extension)
    stem_upper = text.upper()
    if stem_upper in _RESERVED:
        text = f"_{text}"

    if len(text) > max_len:
        text = text[:max_len].rstrip(" ._")

    return text or "untitled"
