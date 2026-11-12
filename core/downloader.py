"""Motor de descarga y conversión basado en yt-dlp + ffmpeg."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

from core.models import DownloadOptions, Job, MediaFormat
from core.utils import sanitize_filename

ProgressCb = Callable[[dict], None]
LogCb = Callable[[str, str], None]


class CancelledByUser(Exception):
    """Se lanza desde los hooks de yt-dlp para abortar una descarga."""


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def ffmpeg_location() -> str | None:
    """Localiza ffmpeg: variable de entorno, sistema o binario empaquetado."""
    env = os.environ.get("SONORA_FFMPEG")
    if env and Path(env).exists():
        return env
    system = shutil.which("ffmpeg")
    if system:
        return system
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def engine_version() -> str:
    try:
        import yt_dlp

        return yt_dlp.version.__version__
    except Exception:
        return "no disponible"


def parse_rate_limit(value: str) -> int | None:
    """Convierte '2M', '500K' o '800000' en bytes por segundo."""
    value = (value or "").strip().lower().replace(" ", "")
    if not value:
        return None
    match = re.fullmatch(r"(\d+(?:[.,]\d+)?)([kmg]?)", value)
    if not match:
        return None
    number = float(match.group(1).replace(",", "."))
    factor = {"": 1, "k": 1024, "m": 1024**2, "g": 1024**3}[match.group(2)]
    result = int(number * factor)
    return result if result > 0 else None


class _YTLogger:
    def __init__(self, log: LogCb | None) -> None:
        self._log = log

    def debug(self, msg: str) -> None:
        msg = ANSI_RE.sub("", str(msg)).strip()
        if not msg or msg.startswith("[debug]"):
            return
        if self._log:
            self._log("debug", msg)

    def info(self, msg: str) -> None:
        self.debug(msg)

    def warning(self, msg: str) -> None:
        msg = ANSI_RE.sub("", str(msg)).strip()
        if self._log:
            self._log("warning", msg)

    def error(self, msg: str) -> None:
        msg = ANSI_RE.sub("", str(msg)).strip()
        if self._log:
            self._log("error", msg)


def _clean_error(exc: Exception) -> str:
    text = ANSI_RE.sub("", str(exc)).strip()
    text = re.sub(r"^ERROR:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    if len(text) > 420:
        text = text[:417] + "…"
    return text or exc.__class__.__name__


def _format_selector(opts: DownloadOptions) -> str:
    fmt = opts.media_format
    if fmt is MediaFormat.MP4:
        height = "" if opts.quality in ("best", "", None) else f"[height<={opts.quality}]"
        return (
            f"bv*[ext=mp4]{height}+ba[ext=m4a]/"
            f"bv*{height}+ba/"
            f"b{height}/b"
        )
    return "bestaudio/best"


def _audio_quality(fmt: MediaFormat, quality: str) -> str:
    if fmt is MediaFormat.MP3:
        return str(quality or "320")
    return "0"


def build_ydl_options(
    opts: DownloadOptions,
    *,
    progress: ProgressCb | None = None,
    log: LogCb | None = None,
    cancel_event: threading.Event | None = None,
    probe: bool = False,
    flat: bool = False,
) -> dict:
    ffmpeg = ffmpeg_location()
    fmt = opts.media_format
    outdir = Path(opts.outdir).expanduser() if opts.outdir else Path.cwd()
    template = (opts.filename_template or "%(title)s").strip() or "%(title)s"
    template = template.replace("%(ext)s", "").rstrip(".")

    ydl_opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": not opts.include_playlist,
        "ignoreerrors": False,
        "retries": opts.retries,
        "fragment_retries": opts.retries,
        "socket_timeout": 30,
        "trim_file_name": 180,
        "outtmpl": {"default": str(outdir / f"{template}.%(ext)s")},
        "logger": _YTLogger(log),
        "ffmpeg_location": ffmpeg,
        "windowsfilenames": False,
        "restrictfilenames": opts.restrict_filenames,
        "concurrent_fragment_downloads": 4,
        "overwrites": False,
        "continuedl": True,
        "geo_bypass": True,
    }

    if opts.rate_limit:
        rate = parse_rate_limit(opts.rate_limit)
        if rate:
            ydl_opts["ratelimit"] = rate
    if opts.proxy:
        ydl_opts["proxy"] = opts.proxy
    if opts.cookies_file and Path(opts.cookies_file).expanduser().exists():
        ydl_opts["cookiefile"] = str(Path(opts.cookies_file).expanduser())

    if probe:
        ydl_opts.update(
            {
                "skip_download": True,
                "extract_flat": "in_playlist" if flat else False,
                "playlistend": 100,
                "noplaylist": False,
            }
        )
        return ydl_opts

    ydl_opts["format"] = _format_selector(opts)
    ydl_opts["merge_output_format"] = "mp4" if fmt is MediaFormat.MP4 else "mkv"

    postprocessors: list[dict] = []
    if opts.sponsorblock:
        categories = ["sponsor", "selfpromo", "interaction", "intro", "outro", "music_offtopic"]
        postprocessors.append({"key": "SponsorBlock", "categories": categories})
        postprocessors.append({"key": "ModifyChapters", "remove_sponsor_segments": categories})

    if fmt is not MediaFormat.MP4:
        postprocessors.append(
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": fmt.value,
                "preferredquality": _audio_quality(fmt, opts.quality),
                "nopostoverwrites": False,
            }
        )

    if opts.embed_metadata:
        postprocessors.append({"key": "FFmpegMetadata", "add_metadata": True, "add_chapters": True})
    if opts.embed_thumbnail and fmt is not MediaFormat.WAV:
        ydl_opts["writethumbnail"] = True
        postprocessors.append({"key": "EmbedThumbnail", "already_have_thumbnail": False})
    if opts.write_subtitles:
        ydl_opts["writesubtitles"] = True
        ydl_opts["writeautomaticsub"] = True
        ydl_opts["subtitleslangs"] = [x.strip() for x in (opts.subtitle_langs or "es,en").split(",") if x.strip()]
        ydl_opts["subtitlesformat"] = "srt/best"

    ydl_opts["postprocessors"] = postprocessors
    return ydl_opts


POSTPROCESSOR_LABELS = {
    "FFmpegExtractAudio": "Convirtiendo audio",
    "FFmpegVideoConvertor": "Convirtiendo vídeo",
    "FFmpegVideoRemuxer": "Reempaquetando vídeo",
    "EmbedThumbnail": "Incrustando portada",
    "FFmpegMetadata": "Añadiendo metadatos",
    "FFmpegEmbedSubtitle": "Incrustando subtítulos",
    "SponsorBlock": "Eliminando patrocinios",
    "ModifyChapters": "Recortando patrocinios",
    "Merger": "Uniendo pistas",
    "SplitChapters": "Dividiendo capítulos",
}


def _make_progress_hook(progress: ProgressCb, cancel_event: threading.Event):
    def hook(data: dict) -> None:
        if cancel_event.is_set():
            raise CancelledByUser("Descarga cancelada")
        status = data.get("status")
        if status == "downloading":
            total = int(data.get("total_bytes") or data.get("total_bytes_estimate") or 0)
            downloaded = int(data.get("downloaded_bytes") or 0)
            pct = (downloaded / total * 100.0) if total else 0.0
            pct = min(pct, 96.0)
            frag_index = data.get("fragment_index")
            frag_count = data.get("fragment_count")
            if frag_index and frag_count:
                pct = min(96.0, frag_index / max(1, frag_count) * 90.0 + 5)
            progress(
                {
                    "status": "downloading",
                    "progress": pct,
                    "speed": float(data.get("speed") or 0),
                    "eta": float(data.get("eta") or 0),
                    "downloaded": downloaded,
                    "total": total,
                    "stage": "Descargando audio" if data.get("info_dict", {}).get("vcodec") == "none" else "Descargando vídeo",
                }
            )
        elif status == "finished":
            progress(
                {
                    "status": "postprocessing",
                    "progress": 97.0,
                    "speed": 0,
                    "eta": 0,
                    "stage": "Procesando archivo",
                }
            )
        elif status == "error":
            progress({"status": "error", "stage": "Error de descarga"})

    return hook


def _make_pp_hook(progress: ProgressCb, cancel_event: threading.Event, holder: dict):
    def hook(data: dict) -> None:
        if cancel_event.is_set():
            raise CancelledByUser("Descarga cancelada")
        name = str(data.get("postprocessor") or "")
        status = data.get("status")
        if status == "started":
            progress(
                {
                    "status": "postprocessing",
                    "progress": 98.0,
                    "speed": 0,
                    "eta": 0,
                    "stage": POSTPROCESSOR_LABELS.get(name, "Procesando"),
                }
            )
        elif status == "finished":
            info = data.get("info_dict") or {}
            filepath = info.get("filepath") or info.get("_filename")
            if filepath:
                holder["filepath"] = filepath

    return hook


def _find_final_file(holder: dict, opts: DownloadOptions, info: dict) -> str:
    candidates: list[str] = []
    if holder.get("filepath"):
        candidates.append(holder["filepath"])
    for item in info.get("requested_downloads") or []:
        for key in ("filepath", "_filename"):
            if item.get(key):
                candidates.append(item[key])
    for key in ("filepath", "_filename"):
        if info.get(key):
            candidates.append(info[key])
    for candidate in reversed(candidates):
        path = Path(candidate)
        if path.exists() and path.is_file():
            return str(path)
    # Último recurso: buscar por título en la carpeta de salida
    outdir = Path(opts.outdir).expanduser()
    title = sanitize_filename(info.get("title") or "")
    if title and outdir.is_dir():
        matches = sorted(outdir.glob(f"{title}*"), key=lambda p: p.stat().st_mtime, reverse=True)
        for match in matches:
            if match.is_file() and match.suffix.lower() not in (".part", ".ytdl", ".jpg", ".webp", ".png", ".srt", ".vtt"):
                return str(match)
    return ""


def _run_ffmpeg(args: list[str], cancel_event: threading.Event) -> None:
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    while proc.poll() is None:
        if cancel_event.is_set():
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                proc.kill()
            raise CancelledByUser("Cancelado durante el procesado")
        time.sleep(0.12)
    if proc.returncode != 0:
        err = proc.stderr.read().decode("utf-8", "ignore") if proc.stderr else ""
        raise RuntimeError(f"ffmpeg falló: {err.strip()[:300]}")


def _audio_encode_args(fmt: MediaFormat, quality: str) -> list[str]:
    quality = str(quality or "320")
    if fmt is MediaFormat.MP3:
        return ["-c:a", "libmp3lame", "-b:a", f"{quality}k"]
    if fmt is MediaFormat.M4A:
        return ["-c:a", "aac", "-b:a", f"{quality}k"]
    if fmt is MediaFormat.OPUS:
        return ["-c:a", "libopus", "-b:a", f"{min(int(quality or 192), 256)}k"]
    if fmt is MediaFormat.FLAC:
        return ["-c:a", "flac"]
    if fmt is MediaFormat.WAV:
        return ["-c:a", "pcm_s16le"]
    return []


def apply_postprocessing(path: Path, opts: DownloadOptions, cancel_event: threading.Event, progress: ProgressCb) -> None:
    """Normaliza volumen y/o recorta el archivo final con ffmpeg."""
    if not (opts.normalize_audio or opts.trim_start or opts.trim_end):
        return
    ffmpeg = ffmpeg_location()
    if not ffmpeg:
        return
    fmt = opts.media_format
    trim = opts.trim_start > 0 or opts.trim_end > 0
    if opts.trim_end > 0 and opts.trim_end <= opts.trim_start:
        trim = False
    stage = "Normalizando volumen" if opts.normalize_audio else "Recortando"
    progress({"status": "postprocessing", "progress": 98.5, "speed": 0, "eta": 0, "stage": stage})

    tmp = path.with_name(f".{path.stem}.sonora_tmp{path.suffix}")
    args = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
    if opts.trim_start > 0:
        args += ["-ss", f"{opts.trim_start:.3f}"]
    args += ["-i", str(path)]
    if trim:
        duration = (opts.trim_end - opts.trim_start) if opts.trim_end > opts.trim_start else None
        if duration:
            args += ["-t", f"{duration:.3f}"]
    if opts.normalize_audio:
        args += ["-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "44100"]
        if fmt is MediaFormat.MP4:
            args += ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k"]
        else:
            args += _audio_encode_args(fmt, opts.quality)
    else:
        args += ["-c", "copy"]
    args += ["-avoid_negative_ts", "make_zero", str(tmp)]
    try:
        _run_ffmpeg(args, cancel_event)
        if tmp.exists() and tmp.stat().st_size > 0:
            os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except Exception:
                pass


def download(job: Job, progress: ProgressCb, log: LogCb, cancel_event: threading.Event) -> dict:
    """Descarga y convierte un trabajo. Devuelve los metadatos finales."""
    import yt_dlp

    opts = job.options
    outdir = Path(opts.outdir).expanduser()
    outdir.mkdir(parents=True, exist_ok=True)
    info_holder: dict = {}

    progress({"status": "probing", "progress": 0.5, "stage": "Obteniendo información"})
    ydl_opts = build_ydl_options(
        opts,
        progress=lambda data: progress(data),
        log=log,
        cancel_event=cancel_event,
        probe=False,
    )
    ydl_opts["progress_hooks"] = [_make_progress_hook(progress, cancel_event)]
    ydl_opts["postprocessor_hooks"] = [_make_pp_hook(progress, cancel_event, info_holder)]

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(job.url, download=True)
        if info is None:
            raise RuntimeError("yt-dlp no devolvió información del enlace")
        if info.get("_type") == "playlist" and info.get("entries"):
            entries = [e for e in info["entries"] if e]
            if not entries:
                raise RuntimeError("La lista de reproducción está vacía")
            info = entries[0]
        info_holder["info"] = info

    final = _find_final_file(info_holder, opts, info)
    path = Path(final) if final else None

    if path and path.exists():
        apply_postprocessing(path, opts, cancel_event, progress)
        progress({"status": "postprocessing", "progress": 99.5, "stage": "Finalizando"})

    return {
        "title": info.get("title") or job.title,
        "uploader": info.get("uploader") or info.get("channel") or job.uploader,
        "duration": float(info.get("duration") or job.duration or 0),
        "thumbnail": info.get("thumbnail") or job.thumbnail_url,
        "filepath": str(path) if path else "",
        "size": path.stat().st_size if path and path.exists() else 0,
        "webpage_url": info.get("webpage_url") or job.url,
    }


def probe(url: str, opts: DownloadOptions, flat: bool = False, log: LogCb | None = None) -> dict:
    """Obtiene metadatos de un enlace o de una lista sin descargar."""
    import yt_dlp

    ydl_opts = build_ydl_options(opts, log=log, probe=True, flat=flat)
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        raise RuntimeError("No se pudo leer el enlace")
    return normalize_probe(info)


def normalize_probe(info: dict) -> dict:
    entries_raw = info.get("entries")
    is_playlist = info.get("_type") == "playlist" or (entries_raw is not None and info.get("_type") != "url")
    entries: list[dict] = []
    if entries_raw:
        for entry in entries_raw:
            if not entry:
                continue
            entry_url = entry.get("webpage_url") or entry.get("url") or ""
            if re.fullmatch(r"[A-Za-z0-9_-]{11}", str(entry_url)):
                entry_url = f"https://www.youtube.com/watch?v={entry_url}"
            entries.append(
                {
                    "id": entry.get("id") or "",
                    "url": entry_url,
                    "title": entry.get("title") or "Sin título",
                    "uploader": entry.get("uploader") or entry.get("channel") or "",
                    "duration": float(entry.get("duration") or 0),
                    "thumbnail": entry.get("thumbnail")
                    or (entry.get("thumbnails") or [{}])[-1].get("url", ""),
                }
            )
    return {
        "id": info.get("id") or "",
        "title": info.get("title") or "Sin título",
        "uploader": info.get("uploader") or info.get("channel") or "",
        "duration": float(info.get("duration") or 0),
        "thumbnail": info.get("thumbnail") or (info.get("thumbnails") or [{}])[-1].get("url", ""),
        "webpage_url": info.get("webpage_url") or info.get("original_url") or "",
        "is_playlist": bool(is_playlist),
        "entries": entries,
        "count": len(entries),
    }
