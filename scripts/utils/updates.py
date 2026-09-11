"""Vérification (et mise à jour) des librairies Python au lancement."""

from __future__ import annotations

import importlib.metadata
import json
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

# Librairies suivies si requirements.txt est illisible
_FALLBACK_PACKAGES = ("yt-dlp", "yt-dlp-ejs", "PySide6")

# yt-dlp / ejs cassent dès que YouTube change son API : mise à jour auto.
# PySide6 (Qt) est trop lourd / risqué à remplacer pendant le lancement.
_AUTO_UPGRADE = frozenset({"yt-dlp", "yt-dlp-ejs"})

_PYPI_JSON = "https://pypi.org/pypi/{name}/json"
_HTTP_TIMEOUT = 8.0
_PIP_TIMEOUT = 180.0


@dataclass
class PackageStatus:
    name: str
    installed: str | None
    latest: str | None
    outdated: bool
    upgraded: bool = False
    skipped: bool = False
    error: str | None = None
    skip_reason: str | None = None


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _parse_version(text: str) -> tuple[int, ...]:
    """Convertit '2026.8.19' / '6.7.0' en tuple comparable."""
    parts: list[int] = []
    for chunk in str(text).replace("-", ".").replace("_", ".").split("."):
        digits = ""
        for ch in chunk:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts) if parts else (0,)


def is_outdated(installed: str, latest: str) -> bool:
    try:
        return _parse_version(installed) < _parse_version(latest)
    except (TypeError, ValueError):
        return installed.strip() != latest.strip()


def installed_version(name: str) -> str | None:
    for candidate in (name, name.replace("-", "_"), name.replace("_", "-")):
        try:
            return importlib.metadata.version(candidate)
        except importlib.metadata.PackageNotFoundError:
            continue
    return None


def pypi_latest(name: str) -> str | None:
    req = urllib.request.Request(
        _PYPI_JSON.format(name=name),
        headers={"User-Agent": "ArchsAutoClipping-update-check/1.0"},
    )
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
        payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    version = (payload.get("info") or {}).get("version")
    return str(version) if version else None


def packages_from_requirements(root: Path) -> list[str]:
    path = root / "requirements.txt"
    names: list[str] = []
    if path.is_file():
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            pkg = (
                line.split("#", 1)[0]
                .split("[", 1)[0]
                .split("==", 1)[0]
                .split(">=", 1)[0]
                .split("<=", 1)[0]
                .split("~=", 1)[0]
                .split("!=", 1)[0]
                .split("<", 1)[0]
                .split(">", 1)[0]
                .strip()
            )
            if pkg:
                names.append(pkg)
    seen: set[str] = set()
    ordered: list[str] = []
    for name in names or list(_FALLBACK_PACKAGES):
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(name)
    return ordered


def _pip_upgrade(name: str) -> tuple[bool, str]:
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--disable-pip-version-check",
        name,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_PIP_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    blob = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    tail = blob[-400:] if blob else ""
    return proc.returncode == 0, tail


def check_and_apply_startup_updates(
    *,
    root: Path | None = None,
    auto_upgrade: bool = True,
) -> list[PackageStatus]:
    """Interroge PyPI et met à jour yt-dlp si une version plus récente existe.

    Ne bloque jamais le lancement : toute erreur réseau / pip est capturée.
    """
    results: list[PackageStatus] = []
    print("[..] Vérification des mises à jour des librairies…", flush=True)

    if is_frozen():
        status = PackageStatus(
            name="(exécutable figé)",
            installed=None,
            latest=None,
            outdated=False,
            skipped=True,
            skip_reason="Build PyInstaller : pip n'est pas disponible",
        )
        print("[INFO] Exécutable figé — pas de mise à jour pip.", flush=True)
        return [status]

    if root is None:
        try:
            from scripts.utils.paths import get_project_paths

            root = get_project_paths().root
        except Exception:  # noqa: BLE001
            root = Path(__file__).resolve().parents[2]

    for name in packages_from_requirements(root):
        status = PackageStatus(
            name=name, installed=None, latest=None, outdated=False
        )
        try:
            status.installed = installed_version(name)
            try:
                status.latest = pypi_latest(name)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
                status.error = f"PyPI injoignable ({exc})"
                print(f"[ATTENTION] {name}: impossible de joindre PyPI ({exc})", flush=True)
                results.append(status)
                continue

            if status.installed is None:
                status.outdated = True
            elif status.latest:
                status.outdated = is_outdated(status.installed, status.latest)

            should_upgrade = (
                auto_upgrade
                and status.outdated
                and name.lower() in _AUTO_UPGRADE
            )
            if should_upgrade:
                target = status.latest or name
                print(
                    f"[MAJ] {name}: {status.installed or 'absent'} → {target} …",
                    flush=True,
                )
                ok, detail = _pip_upgrade(name)
                status.upgraded = ok
                if ok:
                    status.installed = installed_version(name) or status.latest
                    status.outdated = False
                    print(f"[OK] {name} mis à jour ({status.installed}).", flush=True)
                else:
                    status.error = detail or "échec pip"
                    print(f"[ATTENTION] Échec mise à jour {name}: {status.error}", flush=True)
            elif status.outdated:
                print(
                    f"[INFO] {name}: {status.installed or 'absent'} "
                    f"→ {status.latest} disponible "
                    f"(relancez install.bat / install.sh pour l'appliquer).",
                    flush=True,
                )
            else:
                print(
                    f"[OK] {name}: {status.installed or '?'} (à jour)",
                    flush=True,
                )
        except Exception as exc:  # noqa: BLE001
            status.error = str(exc)
            print(f"[ATTENTION] {name}: {exc}", flush=True)
        results.append(status)

    return results


def format_report_lines(results: list[PackageStatus]) -> list[tuple[str, str]]:
    """Retourne (niveau, texte) pour les logs GUI. Niveau: info/success/warning/error."""
    lines: list[tuple[str, str]] = []
    if not results:
        lines.append(("warning", "Vérification des librairies: aucun résultat."))
        return lines

    lines.append(("info", "Vérification des mises à jour des librairies…"))
    for item in results:
        if item.skipped:
            lines.append(
                ("info", f"{item.name}: ignoré ({item.skip_reason or 'n/a'}).")
            )
            continue
        if item.upgraded:
            lines.append(
                (
                    "success",
                    f"{item.name}: mis à jour → {item.installed or item.latest}.",
                )
            )
            continue
        if item.error and item.latest is None and item.installed:
            lines.append(
                (
                    "warning",
                    f"{item.name}: {item.installed} (vérification PyPI impossible: {item.error}).",
                )
            )
            continue
        if item.error and item.upgraded is False and item.outdated:
            lines.append(
                (
                    "error",
                    f"{item.name}: mise à jour échouée ({item.error[:180]}).",
                )
            )
            continue
        if item.outdated:
            lines.append(
                (
                    "warning",
                    f"{item.name}: {item.installed or 'non installé'} "
                    f"→ {item.latest} disponible. Relancez install.bat / ./install.sh.",
                )
            )
            continue
        lines.append(
            (
                "success",
                f"{item.name}: {item.installed or '?'} (à jour).",
            )
        )
    return lines
