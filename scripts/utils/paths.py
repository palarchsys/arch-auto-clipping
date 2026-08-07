"""Résolution des chemins projet (dev vs exécutable PyInstaller)."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


def _resolve_root() -> Path:
    """Racine de l'application.

    - Exécutable frozen (PyInstaller) : dossier contenant l'exe
    - Développement : racine du dépôt (parent de package scripts)
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    # .../<projet>/scripts/utils/paths.py → racine du projet
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ProjectPaths:
    root: Path
    files: Path
    download: Path
    clips: Path
    processeds: Path

    def ensure_dirs(self) -> None:
        for d in (self.files, self.download, self.clips, self.processeds):
            d.mkdir(parents=True, exist_ok=True)


def get_project_paths(root: Path | None = None) -> ProjectPaths:
    base = root if root is not None else _resolve_root()
    paths = ProjectPaths(
        root=base,
        files=base / "files",
        download=base / "download",
        clips=base / "clips",
        processeds=base / "processeds",
    )
    paths.ensure_dirs()
    return paths
