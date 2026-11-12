"""Modelos de datos compartidos por el núcleo y la interfaz."""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum


class MediaFormat(str, Enum):
    MP3 = "mp3"
    M4A = "m4a"
    FLAC = "flac"
    WAV = "wav"
    OPUS = "opus"
    MP4 = "mp4"

    @property
    def kind(self) -> str:
        return "video" if self is MediaFormat.MP4 else "audio"

    @property
    def label(self) -> str:
        return {
            "mp3": "MP3",
            "m4a": "M4A",
            "flac": "FLAC",
            "wav": "WAV",
            "opus": "OPUS",
            "mp4": "MP4",
        }[self.value]

    @classmethod
    def from_value(cls, value: str) -> "MediaFormat":
        try:
            return cls((value or "mp3").lower())
        except ValueError:
            return cls.MP3


AUDIO_FORMATS = [MediaFormat.MP3, MediaFormat.M4A, MediaFormat.FLAC, MediaFormat.WAV, MediaFormat.OPUS]

AUDIO_QUALITIES = ["320", "256", "192", "128"]
VIDEO_QUALITIES = ["best", "2160", "1440", "1080", "720", "480", "360"]


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROBING = "probing"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"

    @property
    def label(self) -> str:
        return {
            "queued": "En cola",
            "probing": "Analizando",
            "downloading": "Descargando",
            "processing": "Procesando",
            "done": "Completado",
            "error": "Error",
            "cancelled": "Cancelado",
        }[self.value]

    @property
    def is_active(self) -> bool:
        return self in (JobStatus.PROBING, JobStatus.DOWNLOADING, JobStatus.PROCESSING)

    @property
    def is_finished(self) -> bool:
        return self in (JobStatus.DONE, JobStatus.ERROR, JobStatus.CANCELLED)


@dataclass
class DownloadOptions:
    """Instantánea de opciones aplicada a cada trabajo."""

    fmt: str = "mp3"
    quality: str = "320"
    outdir: str = ""
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

    @property
    def media_format(self) -> MediaFormat:
        return MediaFormat.from_value(self.fmt)

    def copy_for(self, fmt: str, quality: str) -> "DownloadOptions":
        clone = DownloadOptions(**asdict(self))
        clone.fmt = fmt
        clone.quality = quality
        return clone


@dataclass
class Job:
    url: str
    options: DownloadOptions
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: JobStatus = JobStatus.QUEUED
    title: str = ""
    uploader: str = ""
    duration: float = 0.0
    thumbnail_url: str = ""
    thumbnail_path: str = ""
    progress: float = 0.0
    speed: float = 0.0
    eta: float = 0.0
    downloaded: int = 0
    total: int = 0
    filepath: str = ""
    size: int = 0
    error: str = ""
    stage: str = ""
    added_at: float = field(default_factory=time.time)
    finished_at: float = 0.0
    playlist_title: str = ""
    meta_loaded: bool = False

    @property
    def fmt(self) -> MediaFormat:
        return self.options.media_format

    @property
    def display_title(self) -> str:
        if self.title:
            return self.title
        return self.url

    def to_dict(self) -> dict:
        data = asdict(self)
        data["status"] = self.status.value
        data["fmt"] = self.fmt.value
        return data
