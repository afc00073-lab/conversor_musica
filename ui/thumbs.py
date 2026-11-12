"""Carga asíncrona y caché de miniaturas."""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from core.utils import cache_home, ensure_dirs


class ThumbnailLoader(QObject):
    loaded = Signal(str, QPixmap)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        ensure_dirs()
        self.cache_dir = cache_home() / "thumbs"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._manager = QNetworkAccessManager(self)
        self._memory: OrderedDict[str, QPixmap] = OrderedDict()
        self._pending: dict[str, list[str]] = {}
        self._replies: dict[str, QNetworkReply] = {}

    def request(self, key: str, url: str) -> None:
        if not url:
            return
        memory = self._memory.get(url)
        if memory is not None and not memory.isNull():
            self._memory.move_to_end(url)
            self.loaded.emit(key, memory)
            return
        cached = self._cache_path(url)
        if cached.exists():
            pixmap = QPixmap(str(cached))
            if not pixmap.isNull():
                self._remember(url, pixmap)
                self.loaded.emit(key, pixmap)
                return
        if url in self._pending:
            self._pending[url].append(key)
            return
        self._pending[url] = [key]
        request = QNetworkRequest(QUrl(url))
        request.setRawHeader(b"User-Agent", b"Mozilla/5.0 (X11; Linux x86_64) Sonora/1.0")
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute, QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        reply = self._manager.get(request)
        self._replies[url] = reply
        reply.finished.connect(lambda u=url, r=reply: self._on_finished(u, r))

    def _on_finished(self, url: str, reply: QNetworkReply) -> None:
        keys = self._pending.pop(url, [])
        self._replies.pop(url, None)
        try:
            if reply.error() == QNetworkReply.NetworkError.NoError:
                data = reply.readAll()
                pixmap = QPixmap()
                if pixmap.loadFromData(data) and not pixmap.isNull():
                    self._remember(url, pixmap)
                    cached = self._cache_path(url)
                    pixmap.save(str(cached), "JPEG", 88)
                    for key in keys:
                        self.loaded.emit(key, pixmap)
        finally:
            reply.deleteLater()

    def _remember(self, url: str, pixmap: QPixmap) -> None:
        self._memory[url] = pixmap
        self._memory.move_to_end(url)
        while len(self._memory) > 180:
            self._memory.popitem(last=False)

    def _cache_path(self, url: str) -> Path:
        return self.cache_dir / f"{hashlib.md5(url.encode('utf-8')).hexdigest()}.jpg"
