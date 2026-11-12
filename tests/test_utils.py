"""Pruebas de las utilidades del núcleo (sin Qt)."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from core.utils import (
    extract_urls,
    format_bytes,
    format_duration,
    format_eta,
    format_speed,
    is_probably_url,
    sanitize_filename,
    time_ago,
)


class ExtractUrlsTests(unittest.TestCase):
    def test_extracts_and_deduplicates(self) -> None:
        text = "Mira https://youtu.be/abc12345678 y otra vez https://youtu.be/abc12345678."
        self.assertEqual(extract_urls(text), ["https://youtu.be/abc12345678"])

    def test_strips_trailing_punctuation(self) -> None:
        text = "(https://example.com/video?a=1), ¿lo ves?"
        self.assertEqual(extract_urls(text), ["https://example.com/video?a=1"])

    def test_accepts_bare_youtube_id(self) -> None:
        self.assertEqual(extract_urls("dQw4w9WgXcQ"), ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"])

    def test_empty_text(self) -> None:
        self.assertEqual(extract_urls(""), [])
        self.assertEqual(extract_urls("solo palabras sueltas"), [])

    def test_is_probably_url(self) -> None:
        self.assertTrue(is_probably_url("https://example.com"))
        self.assertTrue(is_probably_url("dQw4w9WgXcQ"))
        self.assertFalse(is_probably_url("hola"))


class FormatTests(unittest.TestCase):
    def test_bytes(self) -> None:
        self.assertEqual(format_bytes(0), "0 B")
        self.assertEqual(format_bytes(512), "512 B")
        self.assertEqual(format_bytes(1024), "1.0 KB")
        self.assertEqual(format_bytes(1_500_000), "1.4 MB")
        self.assertEqual(format_bytes(1024**3), "1.0 GB")

    def test_speed(self) -> None:
        self.assertEqual(format_speed(0), "—")
        self.assertEqual(format_speed(1024), "1.0 KB/s")

    def test_duration(self) -> None:
        self.assertEqual(format_duration(0), "—")
        self.assertEqual(format_duration(65), "1:05")
        self.assertEqual(format_duration(3725), "1:02:05")

    def test_eta(self) -> None:
        self.assertEqual(format_eta(0), "—")
        self.assertEqual(format_eta(30), "30 s")
        self.assertEqual(format_eta(63), "1 min 03 s")
        self.assertEqual(format_eta(3661), "1 h 01 min")

    def test_sanitize_filename(self) -> None:
        self.assertEqual(sanitize_filename('A/B:C*?"<>|'), "ABC")
        self.assertEqual(sanitize_filename("  nombre   con espacios  "), "nombre con espacios")
        self.assertEqual(sanitize_filename(""), "sin_titulo")


class TimeAgoTests(unittest.TestCase):
    def test_recent(self) -> None:
        self.assertEqual(time_ago(0), "—")
        self.assertEqual(time_ago(datetime.now().timestamp()), "hace un momento")

    def test_minutes_and_hours(self) -> None:
        now = datetime.now()
        self.assertEqual(time_ago((now - timedelta(minutes=2)).timestamp()), "hace 2 min")
        self.assertEqual(time_ago((now - timedelta(hours=3)).timestamp()), "hace 3 h")

    def test_days_and_absolute_date(self) -> None:
        now = datetime.now()
        self.assertEqual(time_ago((now - timedelta(days=2)).timestamp()), "hace 2 d")
        old = datetime(2020, 1, 2, 3, 4, 5)
        self.assertEqual(time_ago(old.timestamp()), "02/01/2020")


if __name__ == "__main__":
    unittest.main()
