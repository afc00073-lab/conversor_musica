"""Utilidades generales sin dependencias de Qt."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

URL_RE = re.compile(r"https?://[^\s<>\"'\]\[()]+", re.IGNORECASE)
YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
TRAILING_PUNCT = ".,;:!?»”\"')]}"


def extract_urls(text: str) -> list[str]:
    """Extrae enlaces de un texto libre. Acepta también IDs sueltos de YouTube."""
    found: list[str] = []
    seen: set[str] = set()
    for raw in URL_RE.findall(text or ""):
        url = raw.rstrip(TRAILING_PUNCT)
        if url not in seen:
            seen.add(url)
            found.append(url)
    for token in re.split(r"[\s,;]+", text or ""):
        token = token.strip()
        if YOUTUBE_ID_RE.match(token) and token not in seen:
            seen.add(token)
            found.append(f"https://www.youtube.com/watch?v={token}")
    return found


def is_probably_url(text: str) -> bool:
    text = (text or "").strip()
    return bool(URL_RE.match(text)) or bool(YOUTUBE_ID_RE.match(text))


def format_bytes(num: float | int) -> str:
    num = float(num or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024 or unit == "TB":
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"


def format_speed(bps: float | int) -> str:
    if not bps:
        return "—"
    return f"{format_bytes(bps)}/s"


def format_duration(seconds: float | int) -> str:
    seconds = int(seconds or 0)
    if seconds <= 0:
        return "—"
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_eta(seconds: float | int) -> str:
    seconds = int(seconds or 0)
    if seconds <= 0:
        return "—"
    if seconds < 60:
        return f"{seconds} s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} min {secs:02d} s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min"


def time_ago(ts: float) -> str:
    if not ts:
        return "—"
    delta = max(0, datetime.now().timestamp() - ts)
    if delta < 60:
        return "hace un momento"
    if delta < 3600:
        return f"hace {int(delta // 60)} min"
    if delta < 86400:
        return f"hace {int(delta // 3600)} h"
    if delta < 604800:
        return f"hace {int(delta // 86400)} d"
    return datetime.fromtimestamp(ts).strftime("%d/%m/%Y")


def sanitize_filename(name: str) -> str:
    name = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "", name or "")
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:180] or "sin_titulo"


def config_home() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "sonora"


def data_home() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "sonora"


def cache_home() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "sonora"


def default_download_dir() -> Path:
    home = Path.home()
    for name in ("Música", "Music"):
        candidate = home / name
        if candidate.is_dir():
            return candidate / "Sonora"
    return home / "Sonora"


def ensure_dirs() -> None:
    for path in (config_home(), data_home(), cache_home() / "thumbs", cache_home() / "logs"):
        path.mkdir(parents=True, exist_ok=True)


def open_in_file_manager(path: str | Path) -> None:
    """Abre una carpeta (o revela un archivo) en el gestor de archivos del sistema."""
    target = Path(path)
    try:
        if sys.platform.startswith("win"):
            if target.is_file():
                subprocess.Popen(["explorer", "/select,", str(target)])
            else:
                os.startfile(str(target))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            args = ["open", "-R", str(target)] if target.is_file() else ["open", str(target)]
            subprocess.Popen(args)
        else:
            folder = target if target.is_dir() else target.parent
            subprocess.Popen(["xdg-open", str(folder)])
    except Exception:
        pass


def open_media(path: str | Path) -> None:
    """Reproduce un archivo con la aplicación predeterminada del sistema."""
    target = Path(path)
    if not target.exists():
        return
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(target))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])
    except Exception:
        pass


def is_available(command: str) -> bool:
    return shutil.which(command) is not None
