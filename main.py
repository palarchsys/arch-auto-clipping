#!/usr/bin/env python3
"""Point d'entree Arch's Auto Clipping."""

from __future__ import annotations

import multiprocessing
import sys


def main() -> int:
    # Requis sous Windows + PyInstaller pour le multiprocessing
    multiprocessing.freeze_support()
    # Avant d'importer PySide6 / yt-dlp : vérifier (et mettre à jour yt-dlp)
    from scripts.utils.updates import check_and_apply_startup_updates

    startup_report = check_and_apply_startup_updates()
    from scripts.app import run

    return run(startup_report=startup_report)


if __name__ == "__main__":
    sys.exit(main())
