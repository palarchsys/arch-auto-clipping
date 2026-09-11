"""Tests unitaires des helpers (sans PySide6 ni réseau)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.core.downloader import (  # noqa: E402
    is_incomplete_video,
    is_valid_completed_video,
    youtube_watch_url,
    find_cookiefile,
    _filter_clients,
    _is_retryable_error,
    _is_fatal_error,
)
from scripts.core.models import DownloadJob  # noqa: E402
from scripts.utils.updates import is_outdated, packages_from_requirements  # noqa: E402
from scripts.utils.sanitize import sanitize_filename  # noqa: E402


class IncompleteVideoTests(unittest.TestCase):
    def test_part_suffix(self) -> None:
        self.assertTrue(is_incomplete_video(Path("clip.mp4.part")))
        self.assertTrue(is_incomplete_video(Path("clip.f137.mp4.part")))
        self.assertTrue(is_incomplete_video(Path("clip.ytdl")))
        self.assertFalse(is_incomplete_video(Path("clip.mp4")))


class YoutubeUrlTests(unittest.TestCase):
    def test_prefers_video_id(self) -> None:
        job = DownloadJob(
            video_title="t",
            sanitized_title="t",
            video_id="dQw4w9WgXcQ",
            video_url="https://youtu.be/dQw4w9WgXcQ?si=abc",
        )
        self.assertEqual(
            youtube_watch_url(job),
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )

    def test_shorts_url(self) -> None:
        job = DownloadJob(
            video_title="t",
            sanitized_title="t",
            video_id="",
            video_url="https://www.youtube.com/shorts/dQw4w9WgXcQ",
        )
        self.assertEqual(
            youtube_watch_url(job),
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )


class RetryableTests(unittest.TestCase):
    def test_403_retryable(self) -> None:
        self.assertTrue(_is_retryable_error(RuntimeError("HTTP Error 403: Forbidden")))
        self.assertTrue(_is_retryable_error(RuntimeError("SABR streaming")))
        self.assertTrue(_is_retryable_error(RuntimeError("The page needs to be reloaded.")))

    def test_private_fatal(self) -> None:
        self.assertTrue(_is_fatal_error(RuntimeError("Private video")))
        self.assertFalse(_is_retryable_error(RuntimeError("Private video")))


class CookiefileTests(unittest.TestCase):
    def test_finds_netscape_cookies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cookies = root / "cookies.txt"
            cookies.write_text("# Netscape HTTP Cookie File\n" + ("x" * 100), encoding="utf-8")
            found = find_cookiefile([root])
            self.assertEqual(found, cookies)


class VersionTests(unittest.TestCase):
    def test_ytdlp_calendar_versions(self) -> None:
        self.assertTrue(is_outdated("2024.12.23", "2026.8.19"))
        self.assertFalse(is_outdated("2026.8.19", "2026.8.19"))
        self.assertFalse(is_outdated("2026.10.1", "2026.8.19"))

    def test_requirements_parse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "requirements.txt").write_text(
                "PySide6>=6.6.0\nyt-dlp>=2026.8.19\n", encoding="utf-8"
            )
            self.assertEqual(
                packages_from_requirements(root),
                ["PySide6", "yt-dlp"],
            )


class SanitizeTests(unittest.TestCase):
    def test_windows_forbidden(self) -> None:
        self.assertNotIn(":", sanitize_filename("a:b/c"))
        self.assertEqual(sanitize_filename("CON"), "_CON")


class ValidVideoTests(unittest.TestCase):
    def test_tiny_file_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clip.mp4"
            path.write_bytes(b"tiny")
            self.assertFalse(is_valid_completed_video(path))

    def test_real_sized_mp4_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clip.mp4"
            path.write_bytes(b"0" * 20_000)
            self.assertTrue(is_valid_completed_video(path))


class ClientFilterTests(unittest.TestCase):
    def test_unknown_clients_dropped(self) -> None:
        filtered = _filter_clients(["tv", "not_a_real_client_xyz"])
        self.assertIn("tv", filtered)
        self.assertNotIn("not_a_real_client_xyz", filtered)


if __name__ == "__main__":
    unittest.main()
