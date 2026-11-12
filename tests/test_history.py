"""Pruebas de la biblioteca SQLite."""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from core.history import HistoryStore
from core.models import DownloadOptions, Job


def make_job(title: str, fmt: str = "mp3", size: int = 1000, uploader: str = "Artista") -> Job:
    job = Job(
        url=f"https://example.com/{title}",
        options=DownloadOptions(fmt=fmt),
        title=title,
        uploader=uploader,
        filepath=f"/tmp/{title}.{fmt}",
        size=size,
        duration=60,
    )
    return job


class HistoryStoreTests(unittest.TestCase):
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
        self.store = HistoryStore(path=Path(self.temp.name) / "history.db")
        self.addCleanup(self.store.close)

    def test_add_and_stats(self) -> None:
        self.store.add(make_job("Uno", size=100))
        self.store.add(make_job("Dos", fmt="mp4", size=400))
        self.store.add(make_job("Tres", size=500))
        stats = self.store.stats()
        self.assertEqual(stats["count"], 3)
        self.assertEqual(stats["total_size"], 1000)
        self.assertEqual({row["fmt"] for row in stats["formats"]}, {"mp3", "mp4"})

    def test_search_and_filters(self) -> None:
        self.store.add(make_job("Canción de verano", uploader="Sol"))
        self.store.add(make_job("Videoclip", fmt="mp4", uploader="Luna"))
        self.assertEqual(len(self.store.list(search="verano")), 1)
        self.assertEqual(len(self.store.list(search="luna")), 1)
        self.assertEqual(len(self.store.list(kind="audio")), 1)
        self.assertEqual(len(self.store.list(kind="video")), 1)
        self.assertEqual(len(self.store.list(search="nada")), 0)

    def test_sort(self) -> None:
        first = make_job("AAA", size=50)
        second = make_job("BBB", size=900)
        self.store.add(first)
        time.sleep(0.01)
        self.store.add(second)
        self.assertEqual(self.store.list(sort="recent")[0]["title"], "BBB")
        self.assertEqual(self.store.list(sort="oldest")[0]["title"], "AAA")
        self.assertEqual(self.store.list(sort="title")[0]["title"], "AAA")
        self.assertEqual(self.store.list(sort="size")[0]["title"], "BBB")

    def test_favorites(self) -> None:
        self.store.add(make_job("Favorita"))
        entry = self.store.list()[0]
        self.store.set_favorite(entry["id"], True)
        self.assertEqual(len(self.store.list(favorites=True)), 1)
        self.assertEqual(self.store.list()[0]["favorite"], 1)
        self.store.set_favorite(entry["id"], False)
        self.assertEqual(len(self.store.list(favorites=True)), 0)

    def test_delete_and_clear(self) -> None:
        self.store.add(make_job("Uno"))
        self.store.add(make_job("Dos"))
        entry_id = self.store.list()[0]["id"]
        self.store.delete(entry_id)
        self.assertEqual(self.store.stats()["count"], 1)
        self.store.clear()
        self.assertEqual(self.store.stats()["count"], 0)


if __name__ == "__main__":
    unittest.main()
