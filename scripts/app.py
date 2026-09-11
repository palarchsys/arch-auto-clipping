"""Initialisation QApplication."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from scripts.gui.main_window import MainWindow
from scripts.utils.paths import get_project_paths
from scripts.utils.updates import PackageStatus


def run(startup_report: list[PackageStatus] | None = None) -> int:
    # Créer les dossiers standards au démarrage
    paths = get_project_paths()
    app = QApplication(sys.argv)
    app.setApplicationName("Arch's Auto Clipping")
    app.setOrganizationName("Arch's Auto Clipping")
    window = MainWindow(paths, startup_report=startup_report)
    window.show()
    return app.exec()
