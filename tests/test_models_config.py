"""Pruebas de modelos y ajustes persistentes."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.config import ACCENTS, ConfigStore, Settings
from core.models import DownloadOptions, Job, JobStatus, MediaFormat


class MediaFormatTests(unittest.TestCase):
    def test_from_value(self) -> None:
        self.assertIs(MediaFormat.from_value("MP4"), MediaFormat.MP4)
        self.assertIs(MediaFormat.from_value("flac"), MediaFormat.FLAC)
        self.assertIs(MediaFormat.from_value("desconocido"), MediaFormat.MP3)
        self.assertIs(MediaFormat.from_value(""), MediaFormat.MP3)

    def test_properties(self) -> None:
        self.assertEqual(MediaFormat.MP4.kind, "video")
        self.assertEqual(MediaFormat.MP3.kind, "audio")
        self.assertEqual(MediaFormat.OPUS.label, "OPUS")


class DownloadOptionsTests(unittest.TestCase):
    def test_copy_for_does_not_mutate_original(self) -> None:
        original = DownloadOptions(fmt="mp3", quality="320", embed_thumbnail=True)
        clone = original.copy_for("mp4", "1080")
        self.assertEqual(clone.fmt, "mp4")
        self.assertEqual(clone.quality, "1080")
        self.assertEqual(original.fmt, "mp3")
        self.assertEqual(original.quality, "320")
        clone.embed_thumbnail = False
        self.assertTrue(original.embed_thumbnail)

    def test_job_defaults(self) -> None:
        job = Job(url="https://example.com/v", options=DownloadOptions())
        self.assertEqual(len(job.id), 12)
        self.assertIs(job.status, JobStatus.QUEUED)
        self.assertEqual(job.display_title, "https://example.com/v")
        job.title = "Canción"
        self.assertEqual(job.display_title, "Canción")
        self.assertEqual(job.to_dict()["status"], "queued")
        self.assertEqual(job.to_dict()["fmt"], "mp3")

    def test_job_status(self) -> None:
        self.assertTrue(JobStatus.DOWNLOADING.is_active)
        self.assertTrue(JobStatus.DONE.is_finished)
        self.assertFalse(JobStatus.QUEUED.is_active)
        self.assertFalse(JobStatus.QUEUED.is_finished)


class SettingsTests(unittest.TestCase):
    def test_quality_for_and_options(self) -> None:
        settings = Settings(mp3_quality="256", mp4_quality="720")
        self.assertEqual(settings.quality_for("mp3"), "256")
        self.assertEqual(settings.quality_for(MediaFormat.MP4), "720")
        options = settings.options(MediaFormat.MP4)
        self.assertEqual(options.fmt, "mp4")
        self.assertEqual(options.quality, "720")
        self.assertEqual(settings.options(MediaFormat.MP3, "128").quality, "128")


class ConfigStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = mock.patch.dict(
            os.environ,
            {
                "XDG_CONFIG_HOME": str(Path(self.temp.name) / "config"),
                "XDG_DATA_HOME": str(Path(self.temp.name) / "data"),
                "XDG_CACHE_HOME": str(Path(self.temp.name) / "cache"),
            },
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.path = Path(self.temp.name) / "settings.json"

    def test_defaults(self) -> None:
        store = ConfigStore(path=self.path)
        self.assertEqual(store.settings.theme, "dark")
        self.assertEqual(store.settings.default_format, "mp3")
        self.assertEqual(store.settings.concurrency, 2)
        self.assertIn(store.settings.accent, {accent[0] for accent in ACCENTS.values()})

    def test_update_persists_and_reloads(self) -> None:
        store = ConfigStore(path=self.path)
        store.update(theme="light", concurrency=4, mp3_quality="192")
        again = ConfigStore(path=self.path)
        self.assertEqual(again.settings.theme, "light")
        self.assertEqual(again.settings.concurrency, 4)
        self.assertEqual(again.settings.mp3_quality, "192")

    def test_normalizes_invalid_values(self) -> None:
        self.path.write_text(
            '{"theme": "neón", "concurrency": 99, "default_format": "ogg", "accent": "#000000", "outdir": ""}',
            encoding="utf-8",
        )
        store = ConfigStore(path=self.path)
        self.assertEqual(store.settings.theme, "dark")
        self.assertEqual(store.settings.concurrency, 6)
        self.assertEqual(store.settings.default_format, "mp3")
        self.assertIn(store.settings.accent, {accent[0] for accent in ACCENTS.values()})
        self.assertTrue(store.settings.outdir)

    def test_ignores_unknown_keys_and_broken_json(self) -> None:
        self.path.write_text('{"desconocida": 1, "theme": "light"}', encoding="utf-8")
        self.assertEqual(ConfigStore(path=self.path).settings.theme, "light")
        self.path.write_text("{roto", encoding="utf-8")
        self.assertEqual(ConfigStore(path=self.path).settings.theme, "dark")


if __name__ == "__main__":
    unittest.main()
