"""Liste et lecture des CSV dans files/ (multiprocessing)."""

from __future__ import annotations

import csv
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from scripts.core.models import ClipJob
from scripts.utils.sanitize import sanitize_filename

# spawn : sûr sous Windows et depuis un QThread (évite fork non-main)
_MP_CTX = mp.get_context("spawn")

REQUIRED_FIELDS = ("videoTitle", "videoUrl", "startTime", "endTime")


def list_csv_files(files_dir: Path) -> list[Path]:
    """Retourne la liste triée des fichiers CSV dans files_dir."""
    if not files_dir.is_dir():
        return []
    found = list(files_dir.glob("*.csv")) + list(files_dir.glob("*.CSV"))
    # Dédupliquer (case-insensitive FS) tout en gardant l'ordre
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in sorted(found, key=lambda x: x.name.lower()):
        resolved = p.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(p)
    return unique


def _parse_time(value: str) -> float:
    text = (value or "").strip()
    if not text:
        raise ValueError("temps vide")
    return float(text)


def _read_csv_file(path_str: str) -> tuple[str, list[dict], list[str]]:
    """Worker process : lit un CSV et retourne des dicts bruts + erreurs.

    Retourne (path_str, rows, errors) pour rester picklable.
    """
    path = Path(path_str)
    rows: list[dict] = []
    errors: list[str] = []

    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with path.open("r", encoding=encoding, newline="") as fh:
                reader = csv.DictReader(fh)
                if not reader.fieldnames:
                    errors.append(f"{path.name}: en-têtes manquants")
                    return path_str, rows, errors

                # Normaliser les noms de colonnes (espaces)
                field_map = {f.strip(): f for f in reader.fieldnames if f}
                missing = [f for f in REQUIRED_FIELDS if f not in field_map]
                if missing:
                    errors.append(
                        f"{path.name}: colonnes manquantes: {', '.join(missing)}"
                    )
                    return path_str, rows, errors

                for line_no, raw in enumerate(reader, start=2):
                    try:
                        title = (raw.get(field_map["videoTitle"]) or "").strip()
                        url = (raw.get(field_map["videoUrl"]) or "").strip()
                        start = _parse_time(raw.get(field_map["startTime"]) or "")
                        end = _parse_time(raw.get(field_map["endTime"]) or "")
                        video_id = ""
                        if "videoId" in field_map:
                            video_id = (raw.get(field_map["videoId"]) or "").strip()

                        if not title:
                            raise ValueError("videoTitle vide")
                        if not url:
                            raise ValueError("videoUrl vide")
                        if end <= start:
                            raise ValueError(
                                f"endTime ({end}) <= startTime ({start})"
                            )

                        rows.append(
                            {
                                "source_file": path_str,
                                "video_title": title,
                                "video_id": video_id,
                                "video_url": url,
                                "start_time": start,
                                "end_time": end,
                            }
                        )
                    except Exception as exc:  # noqa: BLE001
                        errors.append(f"{path.name}:L{line_no}: {exc}")
            break
        except UnicodeDecodeError:
            continue
    else:
        errors.append(f"{path.name}: impossible de décoder le fichier")

    return path_str, rows, errors


def _row_to_job(row: dict) -> ClipJob:
    title = row["video_title"]
    return ClipJob(
        source_file=Path(row["source_file"]),
        video_title=title,
        video_id=row["video_id"],
        video_url=row["video_url"],
        start_time=float(row["start_time"]),
        end_time=float(row["end_time"]),
        sanitized_title=sanitize_filename(title),
    )


def load_all_jobs(
    files_dir: Path,
    *,
    max_workers: int | None = None,
) -> tuple[list[ClipJob], list[str]]:
    """Lit tous les CSV en multiprocessing et retourne (jobs, erreurs)."""
    csv_files = list_csv_files(files_dir)
    if not csv_files:
        return [], []

    workers = max_workers or min(4, len(csv_files))
    all_rows: list[dict] = []
    all_errors: list[str] = []

    if workers <= 1 or len(csv_files) == 1:
        for p in csv_files:
            _, rows, errors = _read_csv_file(str(p))
            all_rows.extend(rows)
            all_errors.extend(errors)
    else:
        with ProcessPoolExecutor(max_workers=workers, mp_context=_MP_CTX) as pool:
            futures = {
                pool.submit(_read_csv_file, str(p)): p for p in csv_files
            }
            for fut in as_completed(futures):
                _, rows, errors = fut.result()
                all_rows.extend(rows)
                all_errors.extend(errors)

    jobs = [_row_to_job(r) for r in all_rows]
    return jobs, all_errors
