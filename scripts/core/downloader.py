"""Téléchargement YouTube via yt-dlp (meilleure qualité, clients rotatifs)."""

from __future__ import annotations

import os
import re
import shutil
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

# Erreurs HTTP / accès pour lesquelles on retente (éventuellement avec un autre client)
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
    r"network.*unreachable|"
    r"the page needs to be reloaded|"
    r"requested format is not available|"
    r"sabr|"
    r"po token|"
    r"nsig|"
    r"sign in|"
    r"confirm you.?re not a bot|"
    r"precondition check failed|"
    r"ssl|"
    r"incomplete|"
    r"gave http error|"
    r"unable to extract|"
    r"failed to download|"
    r"the js runtime|"
    r"unsupported client"
    r")",
    re.IGNORECASE,
)

# Erreurs définitives : inutile de retenter 10 fois
_FATAL_PATTERNS = re.compile(
    r"(?:"
    r"private video|"
    r"video unavailable|"
    r"has been removed|"
    r"account associated with this video has been terminated|"
    r"this video is not available|"
    r"copyright"
    r")",
    re.IGNORECASE,
)

_COOKIE_FILENAMES = ("cookies.txt", "youtube_cookies.txt")

# Ordre : d'abord le défaut yt-dlp (meilleure qualité si EJS/Node OK),
# puis clients Android qui marchent sans runtime JS, puis replis.
_STRATEGIES: tuple[dict[str, object], ...] = (
    {
        "label": "défaut yt-dlp",
        "clients": [],
        "fmt": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo*+bestaudio/best",
    },
    {
        "label": "android",
        "clients": ["android"],
        "fmt": "bestvideo*+bestaudio/best",
    },
    {
        "label": "android_vr",
        "clients": ["android_vr"],
        "fmt": "bestvideo*+bestaudio/best",
        "ipv4": True,
    },
    {
        "label": "web_embedded + tv_downgraded",
        "clients": ["web_embedded", "tv_downgraded"],
        "fmt": "bestvideo*+bestaudio/best",
    },
    {
        "label": "tv",
        "clients": ["tv"],
        "fmt": "bestvideo*+bestaudio/best",
        "ipv4": True,
    },
    {
        "label": "android muxed (18/22)",
        "clients": ["android"],
        "fmt": "18/22/best[ext=mp4]/best",
        "ipv4": True,
    },
    {
        "label": "ios + mweb",
        "clients": ["ios", "mweb"],
        "fmt": "bestvideo*+bestaudio/best",
        "ipv4": True,
    },
    {
        "label": "défaut muxed",
        "clients": [],
        "fmt": "best[ext=mp4]/18/22/best",
        "ipv4": True,
    },
    {
        "label": "android + cookies navigateur",
        "clients": ["android"],
        "fmt": "18/22/best",
        "ipv4": True,
        "browser_cookies": True,
    },
    {
        "label": "tous clients muxed",
        "clients": ["android", "android_vr", "tv", "web_embedded", "ios", "mweb"],
        "fmt": "best/18/22",
        "ipv4": True,
        "browser_cookies": True,
    },
)


class DownloadCancelled(Exception):
    """Arrêt demandé pendant un téléchargement yt-dlp."""


class _CaptureLogger:
    """Récupère les messages yt-dlp (sinon quiet=True masque la vraie erreur)."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def debug(self, msg: object) -> None:
        text = str(msg)
        if text.startswith("[debug]"):
            return
        # Garder les avertissements YouTube même en debug
        lower = text.lower()
        if any(
            token in lower
            for token in ("warning", "error", "sabr", "po token", "403", "401", "nsig")
        ):
            self.lines.append(text)

    def info(self, msg: object) -> None:
        self.lines.append(str(msg))

    def warning(self, msg: object) -> None:
        self.lines.append(str(msg))

    def error(self, msg: object) -> None:
        self.lines.append(str(msg))

    def last(self, n: int = 6) -> str:
        useful = [ln.strip() for ln in self.lines if ln and ln.strip()]
        if not useful:
            return ""
        return " | ".join(useful[-n:])[:500]


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
    if lower.endswith(".part") or lower.endswith(".ytdl"):
        return True
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


def youtube_watch_url(job: DownloadJob) -> str:
    """Normalise l'URL (watch?v=ID est plus fiable que youtu.be / shorts)."""
    vid = (job.video_id or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
        return f"https://www.youtube.com/watch?v={vid}"
    url = (job.video_url or "").strip()
    match = re.search(
        r"(?:youtu\.be/|youtube\.com/(?:watch\?v=|shorts/|embed/|live/))([A-Za-z0-9_-]{11})",
        url,
    )
    if match:
        return f"https://www.youtube.com/watch?v={match.group(1)}"
    return url


def find_cookiefile(search_roots: list[Path]) -> Path | None:
    """cookies.txt Netscape (export Brave / Chrome) s'il est présent."""
    for root in search_roots:
        for name in _COOKIE_FILENAMES:
            path = root / name
            try:
                if path.is_file() and path.stat().st_size > 80:
                    return path
            except OSError:
                continue
    return None


def _innertube_clients() -> set[str]:
    for module_name in (
        "yt_dlp.extractor.youtube._base",
        "yt_dlp.extractor.youtube",
    ):
        try:
            module = __import__(module_name, fromlist=["INNERTUBE_CLIENTS"])
            clients = getattr(module, "INNERTUBE_CLIENTS", None)
            if isinstance(clients, dict) and clients:
                return {str(key) for key in clients}
        except Exception:  # noqa: BLE001
            continue
    return {
        "tv",
        "tv_downgraded",
        "tv_simply",
        "tv_embedded",
        "web_embedded",
        "android_sdkless",
        "android_vr",
        "android",
        "ios",
        "mweb",
        "web",
        "web_safari",
        "web_creator",
    }


def _filter_clients(wanted: list[str]) -> list[str]:
    available = _innertube_clients()
    return [name for name in wanted if name in available]


def _js_runtime_opts() -> dict:
    """Active le solveur JS YouTube (EJS) si Node/Deno/Bun est dans le PATH."""
    opts: dict = {"remote_components": ["ejs:github"]}
    for name in ("node", "deno", "bun"):
        path = shutil.which(name)
        if path:
            opts["js_runtimes"] = {name: {"path": path}}
            break
    return opts


def _brave_cookies_available() -> bool:
    home = Path.home()
    candidates = [
        home / "AppData/Local/BraveSoftware/Brave-Browser/User Data/Default/Network/Cookies",
        home / "AppData/Local/BraveSoftware/Brave-Browser/User Data/Default/Cookies",
        home / ".config/BraveSoftware/Brave-Browser/Default/Network/Cookies",
        home / ".config/BraveSoftware/Brave-Browser/Default/Cookies",
        home / "Library/Application Support/BraveSoftware/Brave-Browser/Default/Cookies",
    ]
    return any(path.is_file() for path in candidates)


def _is_retryable_error(exc: BaseException) -> bool:
    msg = str(exc)
    if _FATAL_PATTERNS.search(msg):
        return False
    if _RETRYABLE_PATTERNS.search(msg):
        return True
    status = getattr(exc, "status", None) or getattr(exc, "code", None)
    if status in (401, 403, 429) or (
        isinstance(status, int) and 500 <= status < 600
    ):
        return True
    cause = getattr(exc, "__cause__", None) or getattr(exc, "reason", None)
    if cause is not None and cause is not exc:
        return _is_retryable_error(cause) if isinstance(cause, BaseException) else False
    return False


def _is_fatal_error(exc: BaseException) -> bool:
    return bool(_FATAL_PATTERNS.search(str(exc)))


def _progress_hook(control: ControlFlags | None):
    def hook(status: dict) -> None:
        if control is not None and control.is_stop_requested():
            raise DownloadCancelled("Téléchargement interrompu (stop)")

    return hook


def _build_ydl_opts(
    job: DownloadJob,
    download_dir: Path,
    strategy: dict[str, object],
    *,
    cookiefile: Path | None,
    logger: _CaptureLogger,
    control: ControlFlags | None,
) -> dict:
    outtmpl = str(download_dir / f"{job.sanitized_title}.%(ext)s")
    fmt = str(strategy.get("fmt") or "bestvideo*+bestaudio/best")
    ydl_opts: dict = {
        "format": fmt,
        "merge_output_format": "mp4",
        "outtmpl": outtmpl,
        "noprogress": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 5,
        "fragment_retries": 10,
        "extractor_retries": 3,
        "file_access_retries": 3,
        "noplaylist": True,
        "overwrites": True,
        "geo_bypass": True,
        "socket_timeout": 30,
        "concurrent_fragment_downloads": 3,
        "logger": logger,
        "progress_hooks": [_progress_hook(control)],
        "windowsfilenames": os.name == "nt",
        "cachedir": False,
    }

    ffmpeg_path = find_ffmpeg()
    if ffmpeg_path:
        ydl_opts["ffmpeg_location"] = ffmpeg_path
    else:
        # Sans ffmpeg : formats déjà muxés uniquement
        ydl_opts["format"] = "best[ext=mp4]/18/22/best"
        ydl_opts.pop("merge_output_format", None)

    clients = _filter_clients(list(strategy.get("clients") or []))
    if clients:
        ydl_opts["extractor_args"] = {"youtube": {"player_client": clients}}

    ydl_opts.update(_js_runtime_opts())

    if cookiefile is not None:
        ydl_opts["cookiefile"] = str(cookiefile)
    elif strategy.get("browser_cookies") and _brave_cookies_available():
        ydl_opts["cookiesfrombrowser"] = ("brave",)

    if strategy.get("ipv4"):
        # YouTube renvoie souvent 403 sur IPv6
        ydl_opts["source_address"] = "0.0.0.0"

    return ydl_opts


def _run_ytdlp_download(
    job: DownloadJob,
    download_dir: Path,
    strategy: dict[str, object],
    *,
    cookiefile: Path | None,
    control: ControlFlags | None = None,
) -> str:
    """Lance un essai yt-dlp. Lève en cas d'échec. Retourne un résumé logger."""
    import yt_dlp

    logger = _CaptureLogger()
    ydl_opts = _build_ydl_opts(
        job,
        download_dir,
        strategy,
        cookiefile=cookiefile,
        logger=logger,
        control=control,
    )
    url = youtube_watch_url(job)

    ffmpeg_path = find_ffmpeg()
    old_path = os.environ.get("PATH")
    if ffmpeg_path:
        os.environ["PATH"] = str(Path(ffmpeg_path).parent) + os.pathsep + (old_path or "")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except DownloadCancelled:
        raise
    except Exception as exc:  # noqa: BLE001
        extra = logger.last()
        if extra and extra not in str(exc):
            raise RuntimeError(f"{exc} — {extra}") from exc
        raise
    finally:
        if ffmpeg_path:
            if old_path is None:
                os.environ.pop("PATH", None)
            else:
                os.environ["PATH"] = old_path
    return logger.last()


def _download_one(
    job: DownloadJob,
    download_dir: Path,
    control: ControlFlags | None = None,
    *,
    max_attempts: int = _MAX_DOWNLOAD_ATTEMPTS,
    retry_delay: float = _RETRY_DELAY_SEC,
    cookiefile: Path | None = None,
) -> tuple[str, bool, str, str | None]:
    """Télécharge une vidéo avec retries (401/403/SABR/etc.) et rotation de clients.

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
    attempts = min(max_attempts, len(_STRATEGIES))
    for attempt in range(1, attempts + 1):
        if control is not None and not control.checkpoint():
            cleanup_partials(download_dir, job.sanitized_title)
            return (
                job.dedupe_key,
                False,
                "Téléchargement interrompu (stop/pause définitive)",
                None,
            )

        cleanup_partials(download_dir, job.sanitized_title)
        strategy = _STRATEGIES[attempt - 1]
        label = str(strategy.get("label") or f"essai {attempt}")

        try:
            _run_ytdlp_download(
                job,
                download_dir,
                strategy,
                cookiefile=cookiefile,
                control=control,
            )
        except DownloadCancelled:
            cleanup_partials(download_dir, job.sanitized_title)
            return (
                job.dedupe_key,
                False,
                "Téléchargement interrompu (stop)",
                None,
            )
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc).strip() or type(exc).__name__
            cleanup_partials(download_dir, job.sanitized_title)
            if _is_fatal_error(exc):
                return (
                    job.dedupe_key,
                    False,
                    f"Échec téléchargement (définitif): {last_error}",
                    None,
                )
            retryable = _is_retryable_error(exc)
            if retryable and attempt < attempts:
                if control is not None:
                    control.log(
                        f"  ↳ essai {attempt}/{attempts} [{label}] échoué "
                        f": {last_error[:220]} "
                        f"— nouvel essai ({retry_delay:.0f}s)",
                        LogLevel.WARNING,
                        step="download",
                    )
                time.sleep(retry_delay)
                continue
            if not retryable:
                return (
                    job.dedupe_key,
                    False,
                    f"Échec téléchargement (non retriable) [{label}]: {last_error}",
                    None,
                )
            break

        result = find_existing_video(download_dir, job.sanitized_title)
        if is_valid_completed_video(result):
            return (
                job.dedupe_key,
                True,
                f"Téléchargé: {result.name}"
                + (
                    f" (essai {attempt}/{attempts}, {label})"
                    if attempt > 1
                    else ""
                ),
                str(result),
            )

        partials = cleanup_partials(download_dir, job.sanitized_title)
        last_error = (
            f"fichier incomplet ou manquant après [{label}]"
            + (f" (supprimé: {', '.join(partials)})" if partials else "")
        )
        if attempt < attempts:
            if control is not None:
                control.log(
                    f"  ↳ essai {attempt}/{attempts}: {last_error} "
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
        f"Échec après {attempts} essai(s): {last_error}",
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
    cookiefile = find_cookiefile(
        [download_dir.parent, download_dir.parent / "tools", download_dir.parent / "files"]
    )
    cookie_note = f", cookies: {cookiefile.name}" if cookiefile else ""
    ytdlp_ver = "?"
    try:
        import yt_dlp

        ytdlp_ver = getattr(yt_dlp.version, "__version__", "?")
    except Exception:  # noqa: BLE001
        pass

    js_note = ""
    js_opts = _js_runtime_opts()
    runtimes = js_opts.get("js_runtimes") or {}
    if runtimes:
        js_note = f", JS: {', '.join(runtimes)}"
    else:
        js_note = ", JS: aucun (Node/Deno recommandé pour la 1080p)"

    control.log(
        f"Téléchargement de {total} vidéo(s) unique(s)… "
        f"(yt-dlp {ytdlp_ver}, ffmpeg: {ff or 'INTROUVABLE'}, "
        f"max {_MAX_DOWNLOAD_ATTEMPTS} essais, délai {_RETRY_DELAY_SEC:.0f}s"
        f"{cookie_note}{js_note})",
        LogLevel.INFO if ff else LogLevel.WARNING,
        step="download",
    )
    if cookiefile is None:
        control.log(
            "Astuce: placez un cookies.txt (export Brave) à la racine du projet "
            "si YouTube renvoie 403 / « sign in ».",
            LogLevel.INFO,
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
                pool.submit(
                    _download_one,
                    job,
                    download_dir,
                    control,
                    cookiefile=cookiefile,
                ): job
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
