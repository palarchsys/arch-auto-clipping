#!/usr/bin/env python3
"""Telecharge ffmpeg/ffprobe dans tools/ selon l'OS (Windows / Linux)."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

# Racine projet = parent de scripts/
ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"

WIN_ZIP_URL = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
    "ffmpeg-master-latest-win64-gpl.zip"
)

# Plusieurs miroirs Linux (premier qui fonctionne)
LINUX_SOURCES = {
    "x86_64": [
        (
            "BtbN linux64 gpl",
            "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
            "ffmpeg-master-latest-linux64-gpl.tar.xz",
        ),
        (
            "johnvansickle amd64 static",
            "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
        ),
    ],
    "aarch64": [
        (
            "BtbN linuxarm64 gpl",
            "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
            "ffmpeg-master-latest-linuxarm64-gpl.tar.xz",
        ),
        (
            "johnvansickle arm64 static",
            "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz",
        ),
    ],
}

MIN_BYTES = 1_000_000  # ~1 Mo minimum pour un binaire valide


def log(msg: str) -> None:
    print(msg, flush=True)


def download(url: str, dest: Path) -> None:
    log(f"[..] Telechargement: {url}")
    log(f"      -> {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ArchsAutoClipping-install/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp, dest.open("wb") as out:
            total = resp.headers.get("Content-Length")
            total_i = int(total) if total and total.isdigit() else None
            done = 0
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if total_i:
                    pct = min(100, done * 100 // total_i)
                    print(
                        f"\r      {pct}% ({done // (1024 * 1024)} Mo)",
                        end="",
                        flush=True,
                    )
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Echec reseau: {exc}") from exc
    print(flush=True)
    size = dest.stat().st_size
    if size < 100_000:
        raise RuntimeError(
            f"Fichier telecharge trop petit ({size} octets) — URL invalide ou reseau?"
        )
    log(f"[OK] Telecharge: {size // (1024 * 1024)} Mo")


def find_named(root: Path, name: str) -> Path | None:
    """Trouve un fichier par nom exact (insensible a la casse sous Windows)."""
    name_l = name.lower()
    matches: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.name.lower() != name_l:
            continue
        # Ignorer les .exe sous Linux et vice-versa
        matches.append(p)
    if not matches:
        return None
    # Preferer ceux dans un dossier bin/
    matches.sort(
        key=lambda p: (
            0 if p.parent.name.lower() == "bin" else 1,
            len(str(p)),
        )
    )
    return matches[0]


def copy_bin(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    shutil.copy2(src, dest)
    # Droits d'execution (Linux / partage reseau)
    try:
        mode = dest.stat().st_mode
        dest.chmod(mode | 0o755)
    except OSError as exc:
        log(f"[ATTENTION] chmod +x impossible sur {dest}: {exc}")
    size = dest.stat().st_size
    if size < MIN_BYTES:
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"Binaire trop petit apres copie: {dest} ({size} o)")
    log(f"[OK] Installe: {dest} ({size // (1024 * 1024)} Mo)")


def already_ok(names: list[str]) -> bool:
    for n in names:
        p = TOOLS / n
        if not p.is_file() or p.stat().st_size < MIN_BYTES:
            return False
    return True


def extract_archive(archive: Path, extract_dir: Path) -> None:
    """Extrait zip / tar.xz / tar.gz."""
    extract_dir.mkdir(parents=True, exist_ok=True)
    name = archive.name.lower()

    if name.endswith(".zip"):
        log("[..] Extraction ZIP ...")
        with zipfile.ZipFile(archive, "r") as zf:
            zf.extractall(extract_dir)
        return

    if name.endswith((".tar.xz", ".txz", ".tar.gz", ".tgz", ".tar")):
        log("[..] Extraction TAR ...")
        # 1) module tarfile (besoin de lzma pour .xz)
        try:
            mode = "r:xz" if name.endswith((".tar.xz", ".txz")) else "r:*"
            with tarfile.open(archive, mode) as tf:
                # Python 3.12+ : filter pour securite
                try:
                    tf.extractall(extract_dir, filter="data")
                except TypeError:
                    tf.extractall(extract_dir)
            return
        except Exception as exc:  # noqa: BLE001
            log(f"[INFO] tarfile Python a echoue ({exc}), essai avec tar systeme...")

        # 2) binaire tar du systeme
        if shutil.which("tar"):
            cmd = ["tar", "-xf", str(archive), "-C", str(extract_dir)]
            subprocess.run(cmd, check=True)
            return
        raise RuntimeError(
            "Impossible d'extraire l'archive (module lzma manquant et tar absent)."
        )

    raise RuntimeError(f"Format d'archive non supporte: {archive.name}")


def verify_ffmpeg(binary: Path) -> None:
    """Execute ffmpeg -version pour valider le binaire (best-effort)."""
    try:
        result = subprocess.run(
            [str(binary), "-version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if result.returncode != 0:
            log(f"[ATTENTION] {binary.name} -version code={result.returncode}")
            return
        first = (result.stdout or result.stderr or "").splitlines()
        if first:
            log(f"[OK] Test: {first[0][:100]}")
    except OSError as exc:
        log(f"[ATTENTION] Impossible d'executer {binary}: {exc}")


def install_windows() -> None:
    targets = ["ffmpeg.exe", "ffprobe.exe"]
    if already_ok(targets):
        log("[OK] Deja presents dans tools/: " + ", ".join(targets))
        for t in targets:
            verify_ffmpeg(TOOLS / t) if t.startswith("ffmpeg") else None
        return

    with tempfile.TemporaryDirectory(prefix="arch_ff_win_") as tmp:
        tmp_path = Path(tmp)
        zip_path = tmp_path / "ffmpeg.zip"
        extract_dir = tmp_path / "extract"

        download(WIN_ZIP_URL, zip_path)
        extract_archive(zip_path, extract_dir)

        exes = list(extract_dir.rglob("*.exe"))
        log(f"[INFO] {len(exes)} fichier(s) .exe dans l'archive")
        for e in exes[:12]:
            log(f"      - {e.relative_to(extract_dir)}")

        ff = find_named(extract_dir, "ffmpeg.exe")
        fp = find_named(extract_dir, "ffprobe.exe")
        if ff is None:
            raise RuntimeError("ffmpeg.exe introuvable dans l'archive extraite")
        copy_bin(ff, TOOLS / "ffmpeg.exe")
        if fp is not None:
            copy_bin(fp, TOOLS / "ffprobe.exe")
        else:
            log("[ATTENTION] ffprobe.exe absent de l'archive")
        verify_ffmpeg(TOOLS / "ffmpeg.exe")


def _linux_arch_key() -> str:
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "x86_64"
    if machine in ("aarch64", "arm64"):
        return "aarch64"
    raise RuntimeError(
        f"Architecture non supportee pour telechargement auto: {machine}. "
        "Installez ffmpeg: sudo apt install ffmpeg"
    )


def install_linux() -> None:
    """Telecharge ffmpeg + ffprobe Linux dans tools/ (meme logique que Windows)."""
    targets = ["ffmpeg", "ffprobe"]
    if already_ok(targets):
        log("[OK] Deja presents dans tools/: " + ", ".join(targets))
        verify_ffmpeg(TOOLS / "ffmpeg")
        return

    arch_key = _linux_arch_key()
    sources = LINUX_SOURCES[arch_key]
    log(f"[INFO] Architecture: {platform.machine()} -> {arch_key}")
    log(f"[INFO] {len(sources)} source(s) possible(s)")

    last_error: Exception | None = None
    for label, url in sources:
        log(f"[..] Essai source: {label}")
        try:
            with tempfile.TemporaryDirectory(prefix="arch_ff_lin_") as tmp:
                tmp_path = Path(tmp)
                # extension selon URL
                if url.endswith(".zip"):
                    archive = tmp_path / "ffmpeg.zip"
                else:
                    archive = tmp_path / "ffmpeg.tar.xz"
                extract_dir = tmp_path / "extract"

                download(url, archive)
                extract_archive(archive, extract_dir)

                # Lister candidats utiles
                candidates = [
                    p
                    for p in extract_dir.rglob("*")
                    if p.is_file() and p.name in ("ffmpeg", "ffprobe")
                ]
                log(f"[INFO] {len(candidates)} binaire(s) ffmpeg/ffprobe trouves")
                for c in candidates[:10]:
                    log(f"      - {c.relative_to(extract_dir)} ({c.stat().st_size // 1024} Ko)")

                ff = find_named(extract_dir, "ffmpeg")
                fp = find_named(extract_dir, "ffprobe")
                if ff is None or not ff.is_file():
                    raise RuntimeError("ffmpeg introuvable dans l'archive extraite")

                copy_bin(ff, TOOLS / "ffmpeg")
                if fp is not None and fp.is_file():
                    copy_bin(fp, TOOLS / "ffprobe")
                else:
                    raise RuntimeError("ffprobe introuvable dans l'archive extraite")

                verify_ffmpeg(TOOLS / "ffmpeg")
                log(f"[OK] Source utilisee: {label}")
                return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            log(f"[ATTENTION] Echec source {label}: {exc}")
            # Nettoyer eventuels partiels
            for name in targets:
                p = TOOLS / name
                if p.exists() and p.stat().st_size < MIN_BYTES:
                    p.unlink(missing_ok=True)
            continue

    raise RuntimeError(
        "Toutes les sources Linux ont echoue. "
        f"Derniere erreur: {last_error}. "
        "Alternative: sudo apt install ffmpeg"
    )


def main() -> int:
    log(f"[INFO] Projet : {ROOT}")
    log(f"[INFO] tools/ : {TOOLS}")
    TOOLS.mkdir(parents=True, exist_ok=True)

    system = platform.system().lower()
    try:
        if system == "windows" or os.name == "nt":
            log("[INFO] OS detecte: Windows")
            install_windows()
            needed = ["ffmpeg.exe", "ffprobe.exe"]
        elif system == "linux":
            log("[INFO] OS detecte: Linux")
            install_linux()
            needed = ["ffmpeg", "ffprobe"]
        elif system == "darwin":
            log("[INFO] OS detecte: macOS")
            log("      Installez ffmpeg: brew install ffmpeg")
            log("      Puis copiez les binaires dans tools/ si besoin.")
            return 1
        else:
            log(f"[ERREUR] OS non supporte: {system}")
            return 1
    except Exception as exc:  # noqa: BLE001
        log(f"[ERREUR] {exc}")
        return 1

    # Verification finale
    log("[..] Contenu de tools/ :")
    for p in sorted(TOOLS.iterdir()):
        if p.is_file():
            log(f"      {p.name}  ({max(1, p.stat().st_size // (1024 * 1024))} Mo)")

    missing = [n for n in needed if not (TOOLS / n).is_file()]
    if missing:
        log(f"[ERREUR] Fichiers manquants apres install: {', '.join(missing)}")
        return 1

    # Chemins absolus pour l'utilisateur
    for n in needed:
        log(f"[OK] {TOOLS / n}")

    log("[OK] Binaires tools/ prets.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
