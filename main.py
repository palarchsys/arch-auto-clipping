#!/usr/bin/env python3
"""Point d'entree Arch's Auto Clipping."""

from __future__ import annotations

import multiprocessing
import sys


def main() -> int:
    # Requis sous Windows + PyInstaller pour le multiprocessing
    multiprocessing.freeze_support()
    from scripts.app import run

    return run()


if __name__ == "__main__":
    sys.exit(main())
