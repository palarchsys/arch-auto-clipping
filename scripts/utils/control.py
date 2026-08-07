"""Contrôle coopératif pause / stop partagé entre threads et workers."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from queue import Empty, Queue
from typing import Any, Callable


class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    SUCCESS = "SUCCESS"


class PipelineState(Enum):
    IDLE = auto()
    RUNNING = auto()
    PAUSED = auto()
    STOPPING = auto()
    FINISHED = auto()
    ERROR = auto()


@dataclass
class LogMessage:
    level: LogLevel
    text: str
    progress: float | None = None  # 0.0 – 100.0
    step: str | None = None


@dataclass
class ControlFlags:
    """Flags thread-safe pour pause / stop (orchestrateur dans un QThread)."""

    pause_event: threading.Event = field(default_factory=threading.Event)
    stop_event: threading.Event = field(default_factory=threading.Event)
    log_queue: Queue = field(default_factory=Queue)

    def __post_init__(self) -> None:
        # pause_event set = en pause ; clear = en marche
        self.pause_event.clear()
        self.stop_event.clear()

    def request_pause(self) -> None:
        self.pause_event.set()

    def request_resume(self) -> None:
        self.pause_event.clear()

    def request_stop(self) -> None:
        self.stop_event.set()
        # Débloquer une éventuelle attente de pause
        self.pause_event.clear()

    def is_stop_requested(self) -> bool:
        return self.stop_event.is_set()

    def is_paused(self) -> bool:
        return self.pause_event.is_set()

    def wait_if_paused(self, poll_interval: float = 0.2) -> bool:
        """Bloque tant que en pause. Retourne False si stop demandé."""
        while self.pause_event.is_set():
            if self.stop_event.is_set():
                return False
            time.sleep(poll_interval)
        return not self.stop_event.is_set()

    def checkpoint(self) -> bool:
        """Point de contrôle entre unités de travail.

        Retourne True si on peut continuer, False si stop.
        """
        if self.stop_event.is_set():
            return False
        return self.wait_if_paused()

    def log(
        self,
        text: str,
        level: LogLevel = LogLevel.INFO,
        progress: float | None = None,
        step: str | None = None,
    ) -> None:
        self.log_queue.put(
            LogMessage(level=level, text=text, progress=progress, step=step)
        )

    def drain_logs(self) -> list[LogMessage]:
        messages: list[LogMessage] = []
        while True:
            try:
                messages.append(self.log_queue.get_nowait())
            except Empty:
                break
        return messages


def run_with_checkpoint(
    control: ControlFlags,
    items: list[Any],
    worker: Callable[[Any], Any],
    *,
    on_result: Callable[[Any, Any], None] | None = None,
) -> list[Any]:
    """Exécute worker séquentiellement sur items avec checkpoints pause/stop."""
    results: list[Any] = []
    for item in items:
        if not control.checkpoint():
            break
        result = worker(item)
        results.append(result)
        if on_result is not None:
            on_result(item, result)
    return results
