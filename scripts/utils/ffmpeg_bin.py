"""Localisation de ffmpeg / ffprobe (PATH, tools/, chemins courants)."""

from __future__ import annotations

import os
import shutil
import sys
from functools import lru_cache
from pathlib import Path

from scripts.utils.paths import get_project_paths


def _candidate_names(binary: str) -> list[str]:
    """Noms de fichiers à tester pour un binaire.

    Sous Windows on ne prend QUE les .exe : le dossier tools/ peut
    contenir aussi les binaires Linux (sans extension) d'un partage
    multi-OS ; yt-dlp les prendrait sinon et échouerait.
    """
    if sys.platform == "win32":
        return [f"{binary}.exe"]
    # Linux : binaire sans extension uniquement (évite de lancer un .exe)
    return [binary]


def _search_dirs() -> list[Path]:
    """Dossiers où chercher un binaire local.

    Priorité : tools/ du projet (binaires embarqués), puis chemins système.
    """
    dirs: list[Path] = []
    try:
        root = get_project_paths().root
        # tools/ en premier : portabilité (pas besoin d'installer ffmpeg système)
        dirs.extend(
            [
                root / "tools",
                root / "tools" / "bin",
                root / "tools" / "ffmpeg" / "bin",
                root / "tools" / "ffmpeg",
                root / "bin",
                root,
            ]
        )
    except Exception:  # noqa: BLE001
        pass

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        dirs.extend([exe_dir / "tools", exe_dir / "bin", exe_dir])

    # Emplacements Linux / Windows fréquents
    dirs.extend(
        [
            Path("/usr/bin"),
            Path("/usr/local/bin"),
            Path("/snap/bin"),
            Path(r"C:\ffmpeg\bin"),
            Path(r"C:\Program Files\ffmpeg\bin"),
            Path(r"C:\ProgramData\chocolatey\bin"),
        ]
    )

    # PATH
    for part in os.environ.get("PATH", "").split(os.pathsep):
        if part:
            dirs.append(Path(part))

    seen: set[str] = set()
    unique: list[Path] = []
    for d in dirs:
        key = str(d)
        if key not in seen:
            seen.add(key)
            unique.append(d)
    return unique


@lru_cache(maxsize=4)
def find_binary(name: str = "ffmpeg") -> str | None:
    """Retourne le chemin absolu de ffmpeg/ffprobe, ou None.

    Ordre : 1) tools/ embarqué  2) PATH  3) chemins système.
    """
    # 1) Binaires embarqués dans tools/ (priorité pour portabilité)
    try:
        root = get_project_paths().root
        tools_first = [
            root / "tools",
            root / "tools" / "bin",
            root / "tools" / "ffmpeg" / "bin",
        ]
        for directory in tools_first:
            if not directory.is_dir():
                continue
            for candidate in _candidate_names(name):
                path = directory / candidate
                if path.is_file():
                    return _usable_path(path)
    except Exception:  # noqa: BLE001
        pass

    # 2) PATH système
    for candidate in _candidate_names(name):
        found = shutil.which(candidate)
        if found:
            return str(Path(found).resolve())

    # 3) Autres dossiers candidats
    for directory in _search_dirs():
        if not directory.is_dir():
            continue
        for candidate in _candidate_names(name):
            path = directory / candidate
            if path.is_file():
                return _usable_path(path)
    return None


def _usable_path(path: Path) -> str:
    """Assure l'exécutabilité si possible (FS partagé Linux/Windows)."""
    if sys.platform != "win32":
        try:
            mode = path.stat().st_mode
            if not (mode & 0o111):
                path.chmod(mode | 0o111)
        except OSError:
            pass
    return str(path.resolve())


def find_ffmpeg() -> str | None:
    return find_binary("ffmpeg")


def find_ffprobe() -> str | None:
    return find_binary("ffprobe")


def ffmpeg_available() -> bool:
    return find_ffmpeg() is not None


def clear_cache() -> None:
    find_binary.cache_clear()


def install_hint() -> str:
    if sys.platform == "win32":
        return (
            "Relancez install.bat (télécharge tools\\ffmpeg.exe) "
            "ou copiez ffmpeg.exe + ffprobe.exe dans tools\\ "
            "ou: winget install Gyan.FFmpeg"
        )
    return (
        "Relancez ./install.sh (télécharge tools/ffmpeg) "
        "ou: sudo apt install ffmpeg "
        "ou copiez le binaire dans tools/ffmpeg"
    )
