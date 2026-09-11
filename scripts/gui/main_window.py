"""Fenêtre principale Arch's Auto Clipping — Start / Pause / Stop + logs."""

from __future__ import annotations

from PySide6.QtCore import QThread, QTimer, Signal, Slot
from PySide6.QtGui import QCloseEvent, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from scripts.core.pipeline import Pipeline, PipelineResult
from scripts.gui.styles import APP_STYLESHEET
from scripts.utils.control import ControlFlags, LogLevel, PipelineState
from scripts.utils.paths import ProjectPaths, get_project_paths
from scripts.utils.updates import PackageStatus, format_report_lines


class PipelineWorker(QThread):
    """Exécute le pipeline hors du thread UI."""

    finished_result = Signal(object)
    failed = Signal(str)

    def __init__(self, control: ControlFlags, paths: ProjectPaths) -> None:
        super().__init__()
        self._control = control
        self._paths = paths

    def run(self) -> None:
        try:
            pipeline = Pipeline(self._control, self._paths)
            result = pipeline.run()
            self.finished_result.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(
        self,
        paths: ProjectPaths | None = None,
        startup_report: list[PackageStatus] | None = None,
    ) -> None:
        super().__init__()
        self.paths = paths or get_project_paths()
        self.control = ControlFlags()
        self.worker: PipelineWorker | None = None
        self._paused = False

        self.setWindowTitle("Arch's Auto Clipping")
        self.resize(900, 620)
        self.setStyleSheet(APP_STYLESHEET)

        self._build_ui()
        self._set_idle_state()

        self._log_timer = QTimer(self)
        self._log_timer.setInterval(150)
        self._log_timer.timeout.connect(self._poll_logs)

        self._append_log(
            LogLevel.INFO,
            f"Prêt. Dossier projet: {self.paths.root}",
        )
        self._append_log(
            LogLevel.INFO,
            f"Placez vos CSV dans: {self.paths.files}",
        )
        self._log_startup_report(startup_report)

    def _log_startup_report(self, report: list[PackageStatus] | None) -> None:
        if not report:
            return
        level_map = {
            "info": LogLevel.INFO,
            "success": LogLevel.SUCCESS,
            "warning": LogLevel.WARNING,
            "error": LogLevel.ERROR,
        }
        for kind, text in format_report_lines(report):
            self._append_log(level_map.get(kind, LogLevel.INFO), text)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("Arch's Auto Clipping")
        title.setObjectName("titleLabel")
        layout.addWidget(title)

        self.status_label = QLabel("Statut: en attente")
        self.status_label.setObjectName("statusLabel")
        layout.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        self.log_view = QTextEdit()
        self.log_view.setObjectName("logView")
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        self.start_btn = QPushButton("Start")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.clicked.connect(self.on_start)
        btn_row.addWidget(self.start_btn)

        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setObjectName("pauseBtn")
        self.pause_btn.clicked.connect(self.on_pause_resume)
        btn_row.addWidget(self.pause_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.clicked.connect(self.on_stop)
        btn_row.addWidget(self.stop_btn)

        btn_row.addStretch(1)
        layout.addLayout(btn_row)

    # ----- États UI -----

    def _set_idle_state(self) -> None:
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setText("Pause")
        self.stop_btn.setEnabled(False)
        self._paused = False
        self.status_label.setText("Statut: en attente")

    def _set_running_state(self) -> None:
        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.pause_btn.setText("Pause")
        self.stop_btn.setEnabled(True)
        self._paused = False
        self.status_label.setText("Statut: en cours…")

    def _set_paused_state(self) -> None:
        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.pause_btn.setText("Resume")
        self.stop_btn.setEnabled(True)
        self._paused = True
        self.status_label.setText("Statut: en pause")

    def _set_stopping_state(self) -> None:
        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("Statut: arrêt en cours…")

    # ----- Actions -----

    @Slot()
    def on_start(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return

        # Nouveau contrôle pour chaque run
        self.control = ControlFlags()
        self.progress.setValue(0)
        self._append_log(LogLevel.INFO, "——— Démarrage du traitement ———")

        self.worker = PipelineWorker(self.control, self.paths)
        self.worker.finished_result.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

        self._set_running_state()
        self._log_timer.start()

    @Slot()
    def on_pause_resume(self) -> None:
        if self.worker is None or not self.worker.isRunning():
            return
        if self._paused:
            self.control.request_resume()
            self._append_log(LogLevel.INFO, "Reprise demandée.")
            self._set_running_state()
        else:
            self.control.request_pause()
            self._append_log(LogLevel.WARNING, "Pause demandée…")
            self._set_paused_state()

    @Slot()
    def on_stop(self) -> None:
        if self.worker is None or not self.worker.isRunning():
            return
        self.control.request_stop()
        self._append_log(LogLevel.WARNING, "Stop demandé…")
        self._set_stopping_state()

    @Slot(object)
    def _on_finished(self, result: object) -> None:
        self._poll_logs()
        self._log_timer.stop()
        if isinstance(result, PipelineResult):
            level = (
                LogLevel.WARNING
                if result.stopped
                else (
                    LogLevel.ERROR
                    if result.state == PipelineState.ERROR
                    else LogLevel.SUCCESS
                )
            )
            self._append_log(level, f"Résultat: {result.message}")
            if result.errors:
                self._append_log(
                    LogLevel.WARNING,
                    f"{len(result.errors)} avertissement(s)/erreur(s) de lecture.",
                )
        self.worker = None
        self._set_idle_state()

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self._poll_logs()
        self._log_timer.stop()
        self._append_log(LogLevel.ERROR, f"Échec: {message}")
        QMessageBox.critical(
            self, "Arch's Auto Clipping", f"Erreur fatale:\n{message}"
        )
        self.worker = None
        self._set_idle_state()

    # ----- Logs -----

    @Slot()
    def _poll_logs(self) -> None:
        for msg in self.control.drain_logs():
            self._append_log(msg.level, msg.text)
            if msg.progress is not None:
                self.progress.setValue(int(max(0, min(100, msg.progress))))

    def _append_log(self, level: LogLevel, text: str) -> None:
        color = {
            LogLevel.DEBUG: "#6c7086",
            LogLevel.INFO: "#cdd6f4",
            LogLevel.WARNING: "#f9e2af",
            LogLevel.ERROR: "#f38ba8",
            LogLevel.SUCCESS: "#a6e3a1",
        }.get(level, "#cdd6f4")
        safe = (
            text.replace("&", "&")
            .replace("<", "<")
            .replace(">", ">")
        )
        html = (
            f'<span style="color:{color}">'
            f"[{level.value}] {safe}</span>"
        )
        self.log_view.append(html)
        self.log_view.moveCursor(QTextCursor.MoveOperation.End)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self.worker is not None and self.worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Arch's Auto Clipping",
                "Un traitement est en cours. Arrêter et quitter ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.control.request_stop()
            self.worker.wait(5000)
        self._log_timer.stop()
        event.accept()
