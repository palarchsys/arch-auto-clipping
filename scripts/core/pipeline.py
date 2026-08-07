"""Orchestration des 6 étapes du pipeline Arch's Auto Clipping."""

from __future__ import annotations

from dataclasses import dataclass, field

from scripts.core.archiver import archive_processed_files
from scripts.core.clipper import create_clip_directories, cut_all_clips
from scripts.core.csv_loader import list_csv_files, load_all_jobs
from scripts.core.downloader import (
    check_dependencies,
    download_all,
    find_existing_video,
    is_valid_completed_video,
    jobs_to_downloads,
)
from scripts.core.models import ClipJob
from scripts.utils.control import ControlFlags, LogLevel, PipelineState
from scripts.utils.paths import ProjectPaths, get_project_paths


@dataclass
class PipelineResult:
    state: PipelineState = PipelineState.FINISHED
    files_count: int = 0
    jobs_count: int = 0
    downloads_ok: int = 0
    clips_ok: int = 0
    clips_fail: int = 0
    stopped: bool = False
    errors: list[str] = field(default_factory=list)
    message: str = ""


class Pipeline:
    """Exécute le traitement complet avec contrôle pause/stop."""

    def __init__(
        self,
        control: ControlFlags,
        paths: ProjectPaths | None = None,
        *,
        download_workers: int = 2,
        clip_workers: int | None = None,
    ) -> None:
        self.control = control
        self.paths = paths or get_project_paths()
        self.download_workers = download_workers
        self.clip_workers = clip_workers

    def run(self) -> PipelineResult:
        result = PipelineResult()
        control = self.control
        paths = self.paths
        paths.ensure_dirs()

        try:
            # --- Prérequis ---
            missing = check_dependencies()
            if missing:
                for msg in missing:
                    control.log(msg, LogLevel.ERROR, step="init")
                result.state = PipelineState.ERROR
                result.message = "Dépendances manquantes"
                result.errors.extend(missing)
                return result

            # --- 1. Lister les fichiers ---
            control.log(
                "Étape 1/6 — Liste des fichiers CSV dans files/",
                LogLevel.INFO,
                progress=2.0,
                step="list",
            )
            if not control.checkpoint():
                return self._stopped(result)

            csv_files = list_csv_files(paths.files)
            result.files_count = len(csv_files)
            if not csv_files:
                control.log(
                    "Aucun fichier CSV trouvé dans files/. Rien à traiter.",
                    LogLevel.WARNING,
                    progress=100.0,
                    step="list",
                )
                result.message = "Aucun fichier CSV"
                result.state = PipelineState.FINISHED
                return result

            for p in csv_files:
                control.log(f"  • {p.name}", LogLevel.INFO, step="list")
            control.log(
                f"{len(csv_files)} fichier(s) trouvé(s).",
                LogLevel.SUCCESS,
                progress=8.0,
                step="list",
            )

            # --- 2. Lecture multiprocessing ---
            control.log(
                "Étape 2/6 — Lecture des CSV (multiprocessing)…",
                LogLevel.INFO,
                progress=10.0,
                step="read",
            )
            if not control.checkpoint():
                return self._stopped(result)

            jobs, read_errors = load_all_jobs(paths.files)
            for err in read_errors:
                control.log(err, LogLevel.WARNING, step="read")
                result.errors.append(err)

            result.jobs_count = len(jobs)
            control.log(
                f"{len(jobs)} ligne(s) / clip(s) valide(s) chargé(s).",
                LogLevel.SUCCESS,
                progress=18.0,
                step="read",
            )
            if not jobs:
                control.log(
                    "Aucune ligne valide — arrêt du pipeline.",
                    LogLevel.WARNING,
                    progress=100.0,
                    step="read",
                )
                result.message = "Aucune ligne valide"
                return result

            if not control.checkpoint():
                return self._stopped(result)

            # --- 3. Téléchargements ---
            control.log(
                "Étape 3/6 — Téléchargement YouTube (meilleure qualité)…",
                LogLevel.INFO,
                progress=20.0,
                step="download",
            )
            downloads = jobs_to_downloads(jobs)
            control.log(
                f"{len(downloads)} vidéo(s) unique(s) à traiter.",
                LogLevel.INFO,
                step="download",
            )

            video_map = download_all(
                downloads,
                paths.download,
                control,
                max_workers=self.download_workers,
            )
            # Compléter la map pour les skips / titres (fichiers complets uniquement)
            for d in downloads:
                if d.dedupe_key not in video_map:
                    existing = find_existing_video(
                        paths.download, d.sanitized_title
                    )
                    if existing is not None and is_valid_completed_video(existing):
                        video_map[d.dedupe_key] = existing
                        video_map[d.sanitized_title] = existing

            # Purger toute entrée vers un fichier incomplet / .part
            video_map = {
                k: v
                for k, v in video_map.items()
                if is_valid_completed_video(v)
            }

            result.downloads_ok = sum(
                1
                for d in downloads
                if (
                    (d.dedupe_key in video_map and is_valid_completed_video(video_map[d.dedupe_key]))
                    or (
                        d.sanitized_title in video_map
                        and is_valid_completed_video(video_map[d.sanitized_title])
                    )
                )
            )
            failed_dl = len(downloads) - result.downloads_ok
            control.log(
                f"Téléchargements OK: {result.downloads_ok}/{len(downloads)}"
                + (f" — {failed_dl} échec(s), clips associés ignorés" if failed_dl else ""),
                LogLevel.INFO if failed_dl == 0 else LogLevel.WARNING,
                progress=50.0,
                step="download",
            )

            if not control.checkpoint():
                return self._stopped(result)

            # --- 4. Dossiers clips ---
            control.log(
                "Étape 4/6 — Création des dossiers clips/…",
                LogLevel.INFO,
                progress=52.0,
                step="folders",
            )
            create_clip_directories(jobs, paths.clips, control)
            control.log(
                "Dossiers clips créés.",
                LogLevel.SUCCESS,
                progress=55.0,
                step="folders",
            )

            if not control.checkpoint():
                return self._stopped(result)

            # --- 5. Découpe ---
            control.log(
                "Étape 5/6 — Découpe des clips (multiprocessing)…",
                LogLevel.INFO,
                progress=55.0,
                step="clips",
            )
            # Enrichir video_map par dedupe_key depuis les jobs
            video_map = self._enrich_video_map(jobs, video_map)

            ok, fail = cut_all_clips(
                jobs,
                video_map,
                paths.clips,
                control,
                max_workers=self.clip_workers,
            )
            result.clips_ok = ok
            result.clips_fail = fail
            control.log(
                f"Clips: {ok} succès, {fail} échec(s).",
                LogLevel.INFO if fail == 0 else LogLevel.WARNING,
                progress=90.0,
                step="clips",
            )

            if not control.checkpoint():
                return self._stopped(result)

            # --- 6. Archivage ---
            control.log(
                "Étape 6/6 — Archivage des CSV vers processeds/…",
                LogLevel.INFO,
                progress=92.0,
                step="archive",
            )
            # Re-lister les fichiers encore présents (ceux qu'on a traités)
            to_archive = list_csv_files(paths.files)
            archive_dir = archive_processed_files(
                to_archive, paths.processeds, control
            )
            if archive_dir is not None:
                control.log(
                    f"Archivage terminé: {archive_dir}",
                    LogLevel.SUCCESS,
                    progress=98.0,
                    step="archive",
                )

            control.log(
                "Traitement terminé avec succès.",
                LogLevel.SUCCESS,
                progress=100.0,
                step="done",
            )
            result.state = PipelineState.FINISHED
            result.message = (
                f"OK — {result.clips_ok} clip(s), "
                f"{result.downloads_ok} vidéo(s), "
                f"{result.files_count} fichier(s)"
            )
            return result

        except Exception as exc:  # noqa: BLE001
            control.log(f"Erreur fatale: {exc}", LogLevel.ERROR, step="error")
            result.state = PipelineState.ERROR
            result.message = str(exc)
            result.errors.append(str(exc))
            return result

    def _stopped(self, result: PipelineResult) -> PipelineResult:
        self.control.log(
            "Arrêté par l'utilisateur — pas d'archivage des CSV.",
            LogLevel.WARNING,
            step="stop",
        )
        result.stopped = True
        result.state = PipelineState.FINISHED
        result.message = "Arrêté par l'utilisateur"
        return result

    def _enrich_video_map(
        self, jobs: list[ClipJob], video_map: dict
    ) -> dict:
        """Assure que chaque job a une entrée dedupe_key si un fichier COMPLET existe.

        Ignore les .part et autres fichiers incomplets.
        """
        from pathlib import Path

        enriched: dict = {}
        for k, v in video_map.items():
            path = Path(v) if not isinstance(v, Path) else v
            if is_valid_completed_video(path):
                enriched[k] = path

        for job in jobs:
            if job.dedupe_key in enriched and is_valid_completed_video(
                enriched[job.dedupe_key]
            ):
                continue
            if job.sanitized_title in enriched and is_valid_completed_video(
                enriched[job.sanitized_title]
            ):
                enriched[job.dedupe_key] = enriched[job.sanitized_title]
                continue
            existing = find_existing_video(
                self.paths.download, job.sanitized_title
            )
            if existing is not None and is_valid_completed_video(existing):
                enriched[job.dedupe_key] = existing
                enriched[job.sanitized_title] = existing
            else:
                candidate = self.paths.download / f"{job.sanitized_title}.mp4"
                if is_valid_completed_video(candidate):
                    enriched[job.dedupe_key] = candidate
                    enriched[job.sanitized_title] = candidate
        return enriched
