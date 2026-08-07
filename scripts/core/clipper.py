"""Découpe des clips via ffmpeg (multiprocessing)."""

from __future__ import annotations

import multiprocessing as mp
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from scripts.core.models import ClipJob
from scripts.utils.control import ControlFlags, LogLevel

_MP_CTX = mp.get_context("spawn")


def create_clip_directories(
    jobs: list[ClipJob], clips_dir: Path, control: ControlFlags
) -> set[str]:
    """Crée un dossier par videoTitle (sanitized), sans doublon."""
    titles = sorted({j.sanitized_title for j in jobs})
    for title in titles:
        if not control.checkpoint():
            break
        target = clips_dir / title
        target.mkdir(parents=True, exist_ok=True)
        control.log(
            f"Dossier clips prêt: {target.name}",
            LogLevel.INFO,
            step="folders",
        )
    return set(titles)


def clip_output_path(clips_dir: Path, job: ClipJob) -> Path:
    """clips/{title}/{title}_{start}_{end}.mp4"""
    start = _format_time_token(job.start_time)
    end = _format_time_token(job.end_time)
    name = f"{job.sanitized_title}_{start}_{end}.mp4"
    return clips_dir / job.sanitized_title / name


def _format_time_token(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return str(value).replace(".", "p")


def _cut_one(
    input_path: str,
    output_path: str,
    start: float,
    end: float,
    ffmpeg_bin: str = "ffmpeg",
) -> tuple[bool, str]:
    """Worker process : découpe un clip. Picklable."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Stream copy d'abord (rapide)
    cmd_copy = [
        ffmpeg_bin,
        "-y",
        "-ss",
        str(start),
        "-to",
        str(end),
        "-i",
        input_path,
        "-c",
        "copy",
        "-avoid_negative_ts",
        "make_zero",
        output_path,
    ]
    try:
        result = subprocess.run(
            cmd_copy,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and out.is_file() and out.stat().st_size > 0:
            return True, f"OK (copy): {out.name}"
    except FileNotFoundError:
        return False, f"ffmpeg introuvable ({ffmpeg_bin})"

    # Fallback re-encode
    cmd_re = [
        ffmpeg_bin,
        "-y",
        "-ss",
        str(start),
        "-to",
        str(end),
        "-i",
        input_path,
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-preset",
        "veryfast",
        "-movflags",
        "+faststart",
        output_path,
    ]
    try:
        result = subprocess.run(
            cmd_re,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and out.is_file() and out.stat().st_size > 0:
            return True, f"OK (re-encode): {out.name}"
        err = (result.stderr or result.stdout or "")[-400:]
        return False, f"ffmpeg échec: {err}"
    except FileNotFoundError:
        return False, f"ffmpeg introuvable ({ffmpeg_bin})"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def cut_all_clips(
    jobs: list[ClipJob],
    video_paths: dict[str, Path],
    clips_dir: Path,
    control: ControlFlags,
    *,
    max_workers: int | None = None,
) -> tuple[int, int]:
    """Découpe tous les clips. Retourne (success, failure).

    Toujours re-découpe (écrase).
    """
    if not jobs:
        control.log("Aucun clip à découper.", LogLevel.INFO, step="clips")
        return 0, 0

    from scripts.utils.ffmpeg_bin import find_ffmpeg

    ffmpeg_bin = find_ffmpeg() or "ffmpeg"
    control.log(
        f"ffmpeg: {ffmpeg_bin}",
        LogLevel.INFO,
        step="clips",
    )

    from scripts.core.downloader import is_incomplete_video, is_valid_completed_video

    # Préparer les tâches avec résolution du chemin source
    tasks: list[tuple[ClipJob, Path, Path]] = []
    skipped = 0
    for job in jobs:
        src = video_paths.get(job.dedupe_key) or video_paths.get(job.sanitized_title)
        if src is None or not src.is_file():
            control.log(
                f"Vidéo source absente pour clip: {job.sanitized_title} "
                f"[{job.start_time}-{job.end_time}]",
                LogLevel.ERROR,
                step="clips",
            )
            skipped += 1
            continue
        if is_incomplete_video(src) or not is_valid_completed_video(src):
            control.log(
                f"Vidéo source incomplete/invalide (pas de clip): "
                f"{src.name} [{job.start_time}-{job.end_time}]",
                LogLevel.ERROR,
                step="clips",
            )
            skipped += 1
            continue
        out = clip_output_path(clips_dir, job)
        tasks.append((job, src, out))

    total = len(tasks)
    control.log(
        f"Découpe de {total} clip(s)… ({skipped} ignoré(s) sans source)",
        LogLevel.INFO,
        step="clips",
    )

    success = 0
    failure = skipped
    if not tasks:
        return success, failure

    import os

    workers = max_workers or min(os.cpu_count() or 2, 8)
    workers = max(1, min(workers, total))

    # Lots pour permettre pause/stop entre batches
    remaining = list(tasks)
    done = 0

    while remaining:
        if not control.checkpoint():
            control.log(
                "Découpe interrompue (stop).",
                LogLevel.WARNING,
                step="clips",
            )
            break

        batch = remaining[:workers]
        remaining = remaining[workers:]

        with ProcessPoolExecutor(
            max_workers=len(batch), mp_context=_MP_CTX
        ) as pool:
            futures = {
                pool.submit(
                    _cut_one,
                    str(src),
                    str(out),
                    job.start_time,
                    job.end_time,
                    ffmpeg_bin,
                ): (job, out)
                for job, src, out in batch
            }
            for fut in as_completed(futures):
                job, out = futures[fut]
                ok, message = fut.result()
                done += 1
                progress = 55.0 + (done / max(total, 1)) * 35.0  # ~55-90%
                if ok:
                    success += 1
                    control.log(
                        f"[{done}/{total}] Clip: {message}",
                        LogLevel.SUCCESS,
                        progress=progress,
                        step="clips",
                    )
                else:
                    failure += 1
                    control.log(
                        f"[{done}/{total}] Échec clip "
                        f"{job.sanitized_title}_{job.start_time}_{job.end_time}: "
                        f"{message}",
                        LogLevel.ERROR,
                        progress=progress,
                        step="clips",
                    )

    return success, failure
