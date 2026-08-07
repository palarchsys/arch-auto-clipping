"""Initialisation QApplication."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from scripts.gui.main_window import MainWindow
from scripts.utils.paths import get_project_paths


def run() -> int:
    # Créer les dossiers standards au démarrage
    paths = get_project_paths()
    app = QApplication(sys.argv)
    app.setApplicationName("Arch's Auto Clipping")
    app.setOrganizationName("Arch's Auto Clipping")
    window = MainWindow(paths)
    window.show()
    return app.exec()
