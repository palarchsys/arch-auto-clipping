"""Modèles de données pour le pipeline Arch's Auto Clipping."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ClipJob:
    """Une ligne CSV = un clip à produire."""

    source_file: Path
    video_title: str
    video_id: str
    video_url: str
    start_time: float
    end_time: float
    sanitized_title: str

    @property
    def duration(self) -> float:
        return max(0.0, self.end_time - self.start_time)

    @property
    def dedupe_key(self) -> str:
        return self.video_id or self.video_url


@dataclass(frozen=True)
class DownloadJob:
    """Une vidéo unique à télécharger."""

    video_title: str
    sanitized_title: str
    video_id: str
    video_url: str

    @property
    def dedupe_key(self) -> str:
        return self.video_id or self.video_url
