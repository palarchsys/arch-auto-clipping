"""Téléchargement YouTube via yt-dlp (meilleure qualité)."""

from __future__ import annotations

import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from scripts.core.models import ClipJob, DownloadJob
from scripts.utils.control import ControlFlags, LogLevel
from scripts.utils.ffmpeg_bin import find_ffmpeg, install_hint

# Fichiers incomplets yt-dlp / navigateurs
_INCOMPLETE_MARKERS = (
    ".part",
    ".ytdl",
    ".temp",
    ".tmp",
    ".download",
    ".part-Frag",
)

_MIN_VIDEO_BYTES = 10_000  # 10 Ko — en dessous = quasi sûr incomplet
_MAX_DOWNLOAD_ATTEMPTS = 10
_RETRY_DELAY_SEC = 3.0

# Erreurs HTTP / accès pour lesquelles on retente
_RETRYABLE_PATTERNS = re.compile(
    r"(?:"
    r"\b401\b|\b403\b|\b429\b|"
    r"http error 401|http error 403|http error 429|"
    r"http error 5\d{2}|"
    r"unauthorized|forbidden|"
    r"too many requests|"
    r"timed?\s*out|timeout|"
    r"connection (?:reset|aborted|refused|error)|"
    r"temporarily (?:unavailable|blocked)|"
    r"unable to download|"
    r"fragment.*not found|"
    r"network.*unreachable"
    r")",
    re.IGNORECASE,
)


def jobs_to_downloads(clip_jobs: list[ClipJob]) -> list[DownloadJob]:
    """Déduplique les téléchargements par videoId / videoUrl."""
    seen: set[str] = set()
    downloads: list[DownloadJob] = []
    for job in clip_jobs:
        key = job.dedupe_key
        if key in seen:
            continue
        seen.add(key)
        downloads.append(
            DownloadJob(
                video_title=job.video_title,
                sanitized_title=job.sanitized_title,
                video_id=job.video_id,
                video_url=job.video_url,
            )
        )
    return downloads


def is_incomplete_video(path: Path) -> bool:
    """True si le fichier ressemble à un téléchargement partiel (.part, etc.)."""
    name = path.name
    lower = name.lower()
    for marker in _INCOMPLETE_MARKERS:
        if marker.lower() in lower:
            return True
    # ex: video.mp4.part, video.f137.mp4.part
    if lower.endswith(".part") or lower.endswith(".ytdl"):
        return True
    # suffixes multi-ext: .mp4.part
    suffixes = [s.lower() for s in path.suffixes]
    if any(s in {".part", ".ytdl", ".temp", ".tmp"} for s in suffixes):
        return True
    return False


def is_valid_completed_video(path: Path | None) -> bool:
    """Fichier présent, taille raisonnable, pas un .part / temporaire."""
    if path is None or not path.is_file():
        return False
    if is_incomplete_video(path):
        return False
    try:
        if path.stat().st_size < _MIN_VIDEO_BYTES:
            return False
    except OSError:
        return False
    # Extension média plausible
    media_ext = {
        ".mp4",
        ".mkv",
        ".webm",
        ".m4a",
        ".mp3",
        ".mov",
        ".avi",
        ".opus",
    }
    if path.suffix.lower() not in media_ext:
        # yt-dlp peut parfois laisser une extension inhabituelle ; accepter
        # seulement si pas marqué incomplet (déjà filtré)
        pass
    return True


def find_existing_video(download_dir: Path, sanitized_title: str) -> Path | None:
    """Cherche une vidéo complète déjà téléchargée pour ce titre."""
    if not download_dir.is_dir():
        return None

    candidates: list[Path] = []
    for path in download_dir.iterdir():
        if not path.is_file():
            continue
        if is_incomplete_video(path):
            continue
        if path.stem == sanitized_title or path.stem.startswith(sanitized_title):
            if is_valid_completed_video(path):
                candidates.append(path)

    if not candidates:
        return None
    # Préférer correspondance exacte de stem, puis plus gros fichier
    exact = [p for p in candidates if p.stem == sanitized_title]
    pool = exact or candidates
    return max(pool, key=lambda p: p.stat().st_size)


def resolve_video_path(
    download_dir: Path, sanitized_title: str
) -> Path | None:
    return find_existing_video(download_dir, sanitized_title)


def cleanup_partials(download_dir: Path, sanitized_title: str) -> list[str]:
    """Supprime les fichiers incomplets liés à un titre. Retourne les noms supprimés."""
    removed: list[str] = []
    if not download_dir.is_dir():
        return removed
    for path in list(download_dir.iterdir()):
        if not path.is_file():
            continue
        if not (
            path.name.startswith(sanitized_title)
            or path.stem.startswith(sanitized_title)
        ):
            continue
        if is_incomplete_video(path) or (
            path.stem.startswith(sanitized_title)
            and not is_valid_completed_video(path)
            and is_incomplete_video(path)
        ):
            try:
                path.unlink(missing_ok=True)
                removed.append(path.name)
            except OSError:
                pass
        elif is_incomplete_video(path):
            try:
                path.unlink(missing_ok=True)
                removed.append(path.name)
            except OSError:
                pass
    # Seconde passe : tout .part / .ytdl préfixé par le titre
    for path in list(download_dir.iterdir()):
        if not path.is_file():
            continue
        if sanitized_title in path.name and is_incomplete_video(path):
            try:
                path.unlink(missing_ok=True)
                if path.name not in removed:
                    removed.append(path.name)
            except OSError:
                pass
    return removed


def _is_retryable_error(exc: BaseException) -> bool:
    msg = str(exc)
    if _RETRYABLE_PATTERNS.search(msg):
        return True
    # Codes HTTP exposés par yt-dlp
    status = getattr(exc, "status", None) or getattr(exc, "code", None)
    if status in (401, 403, 429) or (
        isinstance(status, int) and 500 <= status < 600
    ):
        return True
    cause = getattr(exc, "__cause__", None) or getattr(exc, "reason", None)
    if cause is not None and cause is not exc:
        return _is_retryable_error(cause) if isinstance(cause, BaseException) else False
    return False


def _run_ytdlp_download(job: DownloadJob, download_dir: Path) -> None:
    """Lance un essai yt-dlp (lève en cas d'échec)."""
    import yt_dlp

    outtmpl = str(download_dir / f"{job.sanitized_title}.%(ext)s")
    ydl_opts: dict = {
        "format": "bestvideo*+bestaudio/best",
        "merge_output_format": "mp4",
        "outtmpl": outtmpl,
        "noprogress": True,
        "quiet": True,
        "no_warnings": True,
        # Retries internes yt-dlp (fragments) — nos 10 essais sont au-dessus
        "retries": 3,
        "fragment_retries": 3,
        "noplaylist": True,
        # Ne pas laisser de .part orphelins sans nettoyage
        "overwrites": True,
    }

    ffmpeg_path = find_ffmpeg()
    if not ffmpeg_path:
        raise RuntimeError(
            "ffmpeg introuvable pour fusionner vidéo+audio (tools/ffmpeg.exe)"
        )
    ydl_opts["ffmpeg_location"] = ffmpeg_path

    env_path = str(Path(ffmpeg_path).parent) + os.pathsep + os.environ.get("PATH", "")
    old_path = os.environ.get("PATH")
    os.environ["PATH"] = env_path
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([job.video_url])
    finally:
        if old_path is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = old_path


def _download_one(
    job: DownloadJob,
    download_dir: Path,
    control: ControlFlags | None = None,
    *,
    max_attempts: int = _MAX_DOWNLOAD_ATTEMPTS,
    retry_delay: float = _RETRY_DELAY_SEC,
) -> tuple[str, bool, str, str | None]:
    """Télécharge une vidéo avec retries (401/403/etc.).

    Retourne (key, ok, message, path_str|None).
    Ne renvoie jamais un chemin vers un .part / fichier incomplet.
    """
    existing = find_existing_video(download_dir, job.sanitized_title)
    if existing is not None:
        return (
            job.dedupe_key,
            True,
            f"Déjà présent (complet), skip: {existing.name}",
            str(existing),
        )

    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        return (
            job.dedupe_key,
            False,
            "yt-dlp non installé (pip install yt-dlp)",
            None,
        )

    last_error = "erreur inconnue"
    for attempt in range(1, max_attempts + 1):
        if control is not None and not control.checkpoint():
            cleanup_partials(download_dir, job.sanitized_title)
            return (
                job.dedupe_key,
                False,
                "Téléchargement interrompu (stop/pause définitive)",
                None,
            )

        # Nettoyer d'éventuels restes partiels avant chaque essai
        cleanup_partials(download_dir, job.sanitized_title)

        try:
            _run_ytdlp_download(job, download_dir)
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc).strip() or type(exc).__name__
            cleanup_partials(download_dir, job.sanitized_title)
            retryable = _is_retryable_error(exc)
            if retryable and attempt < max_attempts:
                if control is not None:
                    control.log(
                        f"  ↳ essai {attempt}/{max_attempts} échoué "
                        f"(retryable: 401/403/réseau…) : {last_error[:200]} "
                        f"— nouvel essai dans {retry_delay:.0f}s",
                        LogLevel.WARNING,
                        step="download",
                    )
                time.sleep(retry_delay)
                continue
            if not retryable:
                return (
                    job.dedupe_key,
                    False,
                    f"Échec téléchargement (non retriable): {last_error}",
                    None,
                )
            # dernier essai retryable
            break

        # Vérifier qu'un fichier COMPLET est bien là
        result = find_existing_video(download_dir, job.sanitized_title)
        if is_valid_completed_video(result):
            return (
                job.dedupe_key,
                True,
                f"Téléchargé: {result.name}"
                + (f" (essai {attempt}/{max_attempts})" if attempt > 1 else ""),
                str(result),
            )

        # Fichier manquant ou incomplet (.part)
        partials = cleanup_partials(download_dir, job.sanitized_title)
        last_error = (
            "fichier incomplet ou manquant après téléchargement"
            + (f" (supprimé: {', '.join(partials)})" if partials else "")
        )
        if attempt < max_attempts:
            if control is not None:
                control.log(
                    f"  ↳ essai {attempt}/{max_attempts}: {last_error} "
                    f"— nouvel essai dans {retry_delay:.0f}s",
                    LogLevel.WARNING,
                    step="download",
                )
            time.sleep(retry_delay)
            continue
        break

    cleanup_partials(download_dir, job.sanitized_title)
    return (
        job.dedupe_key,
        False,
        f"Échec après {max_attempts} essai(s): {last_error}",
        None,
    )


def download_all(
    downloads: list[DownloadJob],
    download_dir: Path,
    control: ControlFlags,
    *,
    max_workers: int = 2,
) -> dict[str, Path]:
    """Télécharge les vidéos uniques. Retourne map dedupe_key → Path complets."""
    download_dir.mkdir(parents=True, exist_ok=True)
    mapping_dict: dict[str, Path] = {}

    if not downloads:
        control.log("Aucune vidéo à télécharger.", LogLevel.INFO, step="download")
        return mapping_dict

    total = len(downloads)
    ff = find_ffmpeg()
    control.log(
        f"Téléchargement de {total} vidéo(s) unique(s)… "
        f"(ffmpeg: {ff or 'INTROUVABLE'}, "
        f"max {_MAX_DOWNLOAD_ATTEMPTS} essais, délai {_RETRY_DELAY_SEC:.0f}s)",
        LogLevel.INFO if ff else LogLevel.ERROR,
        step="download",
    )

    remaining = list(downloads)
    done = 0
    workers = max(1, min(max_workers, total))

    while remaining:
        if not control.checkpoint():
            control.log(
                "Téléchargement interrompu (stop).",
                LogLevel.WARNING,
                step="download",
            )
            break

        batch = remaining[:workers]
        remaining = remaining[workers:]

        with ThreadPoolExecutor(max_workers=len(batch)) as pool:
            futures = {
                pool.submit(_download_one, job, download_dir, control): job
                for job in batch
            }
            for fut in as_completed(futures):
                job = futures[fut]
                key, ok, message, path_str = fut.result()
                done += 1
                progress = 20.0 + (done / total) * 30.0
                level = LogLevel.SUCCESS if ok else LogLevel.ERROR
                control.log(
                    f"[{done}/{total}] {job.sanitized_title}: {message}",
                    level,
                    progress=progress,
                    step="download",
                )
                if ok and path_str:
                    path = Path(path_str)
                    if is_valid_completed_video(path):
                        mapping_dict[key] = path
                        mapping_dict[job.sanitized_title] = path
                    else:
                        control.log(
                            f"  ↳ fichier rejeté (incomplet): {path.name}",
                            LogLevel.ERROR,
                            step="download",
                        )
                        cleanup_partials(download_dir, job.sanitized_title)

    return mapping_dict


def ffmpeg_available() -> bool:
    return find_ffmpeg() is not None


def check_dependencies() -> list[str]:
    """Retourne la liste des dépendances manquantes (messages)."""
    missing: list[str] = []
    if find_ffmpeg() is None:
        missing.append(
            "ffmpeg introuvable (PATH ou tools/). " + install_hint()
        )
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        missing.append("yt-dlp non installé (relancez install.sh / install.bat).")
    return missing
