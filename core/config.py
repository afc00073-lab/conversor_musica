"""Persistencia de ajustes de Sonora."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from core.models import DownloadOptions, MediaFormat
from core.utils import config_home, default_download_dir, ensure_dirs

APP_NAME = "Sonora"
APP_TAGLINE = "Convierte enlaces en música y vídeo"
APP_VERSION = "1.0.0"
GITHUB_URL = "https://github.com/afc00073-lab/conversor_musica"

ACCENTS: dict[str, tuple[str, str]] = {
    "Violeta": ("#7C5CFF", "#4F8CFF"),
    "Cian": ("#22D3EE", "#3B82F6"),
    "Esmeralda": ("#34D399", "#22D3EE"),
    "Ámbar": ("#FBBF24", "#F97316"),
    "Rosa": ("#F472B6", "#A855F7"),
    "Rojo": ("#FB7185", "#F43F5E"),
}


@dataclass
class Settings:
    theme: str = "dark"
    accent: str = "#7C5CFF"
    outdir: str = field(default_factory=lambda: str(default_download_dir()))

    default_format: str = "mp3"
    mp3_quality: str = "320"
    mp4_quality: str = "1080"
    concurrency: int = 2
    auto_start: bool = True

    embed_thumbnail: bool = True
    embed_metadata: bool = True
    normalize_audio: bool = False
    sponsorblock: bool = False
    write_subtitles: bool = False
    subtitle_langs: str = "es,en"
    include_playlist: bool = False

    filename_template: str = "%(title)s"
    restrict_filenames: bool = False
    cookies_file: str = ""
    proxy: str = ""
    rate_limit: str = ""
    retries: int = 3
    trim_start: float = 0.0
    trim_end: float = 0.0

    clipboard_watch: bool = False
    notifications: bool = True
    close_to_tray: bool = False

    last_page: str = "download"
    window_geometry: str = ""

    def quality_for(self, fmt: str | MediaFormat) -> str:
        fmt = MediaFormat.from_value(fmt.value if isinstance(fmt, MediaFormat) else fmt)
        return self.mp4_quality if fmt is MediaFormat.MP4 else self.mp3_quality

    def options(self, fmt: str | MediaFormat | None = None, quality: str | None = None) -> DownloadOptions:
        chosen = MediaFormat.from_value(fmt.value if isinstance(fmt, MediaFormat) else (fmt or self.default_format))
        return DownloadOptions(
            fmt=chosen.value,
            quality=quality or self.quality_for(chosen),
            outdir=self.outdir,
            embed_thumbnail=self.embed_thumbnail,
            embed_metadata=self.embed_metadata,
            normalize_audio=self.normalize_audio,
            sponsorblock=self.sponsorblock,
            write_subtitles=self.write_subtitles,
            subtitle_langs=self.subtitle_langs,
            include_playlist=self.include_playlist,
            filename_template=self.filename_template or "%(title)s",
            restrict_filenames=self.restrict_filenames,
            cookies_file=self.cookies_file,
            proxy=self.proxy,
            rate_limit=self.rate_limit,
            retries=max(0, int(self.retries)),
            trim_start=max(0.0, float(self.trim_start or 0)),
            trim_end=max(0.0, float(self.trim_end or 0)),
        )


class ConfigStore:
    """Carga/guarda ajustes en JSON de forma atómica."""

    def __init__(self, path: Path | None = None) -> None:
        ensure_dirs()
        self.path = path or (config_home() / "settings.json")
        self._lock = threading.Lock()
        self.settings = self.load()

    def load(self) -> Settings:
        settings = Settings()
        try:
            if self.path.exists():
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                valid = {f.name for f in fields(Settings)}
                for key, value in raw.items():
                    if key in valid:
                        setattr(settings, key, value)
        except Exception:
            pass
        self._normalize(settings)
        return settings

    def save(self, settings: Settings | None = None) -> None:
        if settings is not None:
            self.settings = settings
        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps(asdict(self.settings), ensure_ascii=False, indent=2), encoding="utf-8")
                tmp.replace(self.path)
            except Exception:
                pass

    def update(self, **kwargs) -> Settings:
        for key, value in kwargs.items():
            if hasattr(self.settings, key):
                setattr(self.settings, key, value)
        self._normalize(self.settings)
        self.save()
        return self.settings

    @staticmethod
    def _normalize(settings: Settings) -> None:
        if settings.theme not in ("dark", "light", "system"):
            settings.theme = "dark"
        if not str(settings.outdir or "").strip():
            settings.outdir = str(default_download_dir())
        try:
            settings.concurrency = min(6, max(1, int(settings.concurrency)))
        except Exception:
            settings.concurrency = 2
        if settings.default_format not in {f.value for f in MediaFormat}:
            settings.default_format = "mp3"
        if settings.accent not in {c[0] for c in ACCENTS.values()}:
            settings.accent = "#7C5CFF"
