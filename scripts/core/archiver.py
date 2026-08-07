"""Archivage des CSV traités vers processeds/YYYY-MM-DD_HH-MM."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from scripts.utils.control import ControlFlags, LogLevel


def archive_processed_files(
    source_files: list[Path],
    processeds_dir: Path,
    control: ControlFlags,
    *,
    stamp: datetime | None = None,
) -> Path | None:
    """Déplace les fichiers CSV traités dans un sous-dossier horodaté.

    Retourne le chemin du dossier d'archive, ou None si rien à déplacer.
    """
    existing = [p for p in source_files if p.is_file()]
    if not existing:
        control.log(
            "Aucun fichier à archiver dans files/.",
            LogLevel.INFO,
            step="archive",
        )
        return None

    when = stamp or datetime.now()
    folder_name = when.strftime("%Y-%m-%d_%H-%M")
    target_dir = processeds_dir / folder_name
    # Éviter collision si re-run dans la même minute
    if target_dir.exists():
        suffix = 1
        while (processeds_dir / f"{folder_name}_{suffix}").exists():
            suffix += 1
        target_dir = processeds_dir / f"{folder_name}_{suffix}"

    target_dir.mkdir(parents=True, exist_ok=True)
    control.log(
        f"Archivage vers processeds/{target_dir.name}/ …",
        LogLevel.INFO,
        step="archive",
    )

    for src in existing:
        dest = target_dir / src.name
        if dest.exists():
            stem, suf = src.stem, src.suffix
            n = 1
            while dest.exists():
                dest = target_dir / f"{stem}_{n}{suf}"
                n += 1
        shutil.move(str(src), str(dest))
        control.log(
            f"Déplacé: {src.name} → processeds/{target_dir.name}/{dest.name}",
            LogLevel.SUCCESS,
            step="archive",
        )

    return target_dir
