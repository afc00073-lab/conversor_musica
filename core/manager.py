"""Gestor de cola: concurrencia, cancelación, metadatos e historial."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from core import downloader
from core.config import ConfigStore
from core.history import HistoryStore
from core.models import DownloadOptions, Job, JobStatus

from core.downloader import CancelledByUser
from core.utils import extract_urls


class _WorkerSignals(QObject):
    progress = Signal(str, dict)
    finished = Signal(str, dict)
    failed = Signal(str, str)
    cancelled = Signal(str)
    log = Signal(str, str)


class _DownloadWorker(QRunnable):
    def __init__(self, job: Job) -> None:
        super().__init__()
        self.job = job
        self.cancel_event = threading.Event()
        self.signals = _WorkerSignals()

    def run(self) -> None:
        job = self.job

        def on_progress(data: dict) -> None:
            self.signals.progress.emit(job.id, data)

        def on_log(level: str, message: str) -> None:
            self.signals.log.emit(level, message)

        try:
            result = downloader.download(job, on_progress, on_log, self.cancel_event)
            self.signals.finished.emit(job.id, result)
        except CancelledByUser:
            self.signals.cancelled.emit(job.id)
        except Exception as exc:
            if self.cancel_event.is_set():
                self.signals.cancelled.emit(job.id)
            else:
                self.signals.failed.emit(job.id, downloader._clean_error(exc))


class _EnrichSignals(QObject):
    done = Signal(str, dict)
    failed = Signal(str, str)
    log = Signal(str, str)


class _EnrichWorker(QRunnable):
    """Obtiene título, miniatura y duración antes de descargar."""

    def __init__(self, job: Job) -> None:
        super().__init__()
        self.job = job
        self.signals = _EnrichSignals()

    def run(self) -> None:
        try:
            info = downloader.probe(
                self.job.url,
                self.job.options,
                flat=False,
                log=lambda level, message: self.signals.log.emit(level, message),
            )
            self.signals.done.emit(self.job.id, info)
        except Exception as exc:
            self.signals.failed.emit(self.job.id, downloader._clean_error(exc))


class _PlaylistSignals(QObject):
    done = Signal(str, dict)
    failed = Signal(str, str)


class _PlaylistWorker(QRunnable):
    def __init__(self, request_id: str, url: str, options: DownloadOptions) -> None:
        super().__init__()
        self.request_id = request_id
        self.url = url
        self.options = options
        self.signals = _PlaylistSignals()

    def run(self) -> None:
        try:
            info = downloader.probe(self.url, self.options, flat=True)
            self.signals.done.emit(self.request_id, info)
        except Exception as exc:
            self.signals.failed.emit(self.request_id, downloader._clean_error(exc))


class DownloadManager(QObject):
    jobAdded = Signal(str)
    jobUpdated = Signal(str)
    jobRemoved = Signal(str)
    jobCompleted = Signal(str)
    jobFailed = Signal(str, str)
    statsChanged = Signal(dict)
    logMessage = Signal(str, str)
    pausedChanged = Signal(bool)
    playlistResolved = Signal(str, dict)
    playlistFailed = Signal(str, str)
    libraryChanged = Signal()

    def __init__(self, config: ConfigStore, history: HistoryStore, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.history = history
        self.jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._workers: dict[str, _DownloadWorker] = {}
        self._active: set[str] = set()
        self._paused = False
        self.auto_start = bool(self.config.settings.auto_start)
        self._approved: set[str] = set()

        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(self.config.settings.concurrency)
        self.enrich_pool = QThreadPool(self)
        self.enrich_pool.setMaxThreadCount(3)
        self.playlist_pool = QThreadPool(self)
        self.playlist_pool.setMaxThreadCount(2)
        self._playlist_workers: dict[str, _PlaylistWorker] = {}
        self._enrich_workers: dict[str, _EnrichWorker] = {}

    # ------------------------------------------------------------------ cola
    @property
    def paused(self) -> bool:
        return self._paused

    def add_urls(self, text: str, options: DownloadOptions) -> list[Job]:
        urls = extract_urls(text)
        return self.add_job_urls(urls, options)

    def add_job_urls(self, urls: list[str], options: DownloadOptions, enrich: bool = True) -> list[Job]:
        created: list[Job] = []
        for url in urls:
            url = (url or "").strip()
            if not url:
                continue
            if any(job.url == url and job.status in (JobStatus.QUEUED, JobStatus.PROBING, JobStatus.DOWNLOADING, JobStatus.PROCESSING) for job in self.jobs.values()):
                self.logMessage.emit("info", f"Enlace duplicado en la cola: {url}")
                continue
            job = Job(url=url, options=options.copy_for(options.fmt, options.quality), status=JobStatus.PROBING)
            job.stage = "Obteniendo información"
            self.jobs[job.id] = job
            self._order.append(job.id)
            created.append(job)
            self.jobAdded.emit(job.id)
            if enrich:
                self._enrich(job)
        if created:
            self.logMessage.emit("info", f"{len(created)} enlace(s) añadidos a la cola")
            self._emit_stats()
            self._pump()
        return created

    def add_playlist_entries(self, entries: list[dict], options: DownloadOptions) -> list[Job]:
        urls = [entry.get("url", "") for entry in entries if entry.get("url")]
        jobs = self.add_job_urls(urls, options, enrich=False)
        for job, entry in zip(jobs, entries):
            job.title = entry.get("title") or job.title
            job.uploader = entry.get("uploader") or job.uploader
            job.duration = entry.get("duration") or 0
            job.thumbnail_url = entry.get("thumbnail") or ""
            job.meta_loaded = True
            if job.status is JobStatus.PROBING:
                job.status = JobStatus.QUEUED
                job.stage = "En cola"
            self.jobUpdated.emit(job.id)
        if jobs:
            self._emit_stats()
            self._pump()
        return jobs

    def retry(self, job_id: str) -> None:
        job = self.jobs.get(job_id)
        if not job or job.status in (JobStatus.DOWNLOADING, JobStatus.PROCESSING, JobStatus.PROBING):
            return
        job.status = JobStatus.PROBING if not job.meta_loaded else JobStatus.QUEUED
        job.progress = 0
        job.error = ""
        job.stage = "En cola" if job.meta_loaded else "Obteniendo información"
        job.speed = 0
        job.eta = 0
        self._approved.add(job_id)
        self.jobUpdated.emit(job_id)
        if not job.meta_loaded:
            self._enrich(job)
        self._emit_stats()
        self._pump()

    def retry_failed(self) -> int:
        count = 0
        for job in list(self.jobs.values()):
            if job.status is JobStatus.ERROR:
                self.retry(job.id)
                count += 1
        return count

    def cancel(self, job_id: str) -> None:
        job = self.jobs.get(job_id)
        if not job:
            return
        if job_id in self._workers:
            self._workers[job_id].cancel_event.set()
            job.stage = "Cancelando…"
            self.jobUpdated.emit(job_id)
        elif job.status in (JobStatus.QUEUED, JobStatus.PROBING):
            job.status = JobStatus.CANCELLED
            job.stage = "Cancelado"
            job.finished_at = time.time()
            self._approved.discard(job_id)
            self.jobUpdated.emit(job_id)
            self._emit_stats()

    def remove(self, job_id: str) -> None:
        job = self.jobs.get(job_id)
        if not job:
            return
        self.cancel(job_id)
        self._active.discard(job_id)
        self._approved.discard(job_id)
        self._workers.pop(job_id, None)
        self._enrich_workers.pop(job_id, None)
        self.jobs.pop(job_id, None)
        if job_id in self._order:
            self._order.remove(job_id)
        self.jobRemoved.emit(job_id)
        self._emit_stats()
        self._pump()

    def clear_finished(self) -> None:
        for job in list(self.jobs.values()):
            if job.status in (JobStatus.DONE, JobStatus.ERROR, JobStatus.CANCELLED):
                self.remove(job.id)

    def clear_all(self) -> None:
        for job_id in list(self.jobs):
            self.remove(job_id)

    def pause(self) -> None:
        self._paused = True
        self.pausedChanged.emit(True)
        self.logMessage.emit("info", "Cola pausada: las descargas activas terminarán su curso")

    def resume(self) -> None:
        self._paused = False
        self._approve_pending()
        self.pausedChanged.emit(False)
        self.logMessage.emit("info", "Cola reanudada")
        self._pump()

    def start_queue(self) -> None:
        self._paused = False
        self._approve_pending()
        self.pausedChanged.emit(False)
        self.logMessage.emit("info", "Iniciando cola")
        self._pump()

    def _approve_pending(self) -> None:
        """Marca la cola actual para arrancar aunque el autoinicio esté apagado."""
        self._approved.update(
            job.id for job in self.jobs.values() if job.status in (JobStatus.QUEUED, JobStatus.PROBING)
        )

    def set_auto_start(self, enabled: bool) -> None:
        self.auto_start = bool(enabled)
        if enabled:
            self._approve_pending()
            self._pump()

    def cancel_all(self) -> None:
        for job in list(self.jobs.values()):
            if job.status in (JobStatus.QUEUED, JobStatus.PROBING, JobStatus.DOWNLOADING, JobStatus.PROCESSING):
                self.cancel(job.id)

    def toggle_pause(self) -> bool:
        if self._paused:
            self.resume()
        else:
            self.pause()
        return self._paused

    def set_concurrency(self, value: int) -> None:
        self.pool.setMaxThreadCount(max(1, min(6, int(value))))
        self._pump()

    def shutdown(self) -> None:
        for worker in self._workers.values():
            worker.cancel_event.set()
        self.pool.clear()
        self.enrich_pool.clear()
        self.playlist_pool.clear()
        self.pool.waitForDone(1500)

    def ordered_jobs(self) -> list[Job]:
        return [self.jobs[job_id] for job_id in self._order if job_id in self.jobs]

    # --------------------------------------------------------------- internos
    def _enrich(self, job: Job) -> None:
        worker = _EnrichWorker(job)
        worker.signals.done.connect(self._on_enrich_done)
        worker.signals.failed.connect(self._on_enrich_failed)
        worker.signals.log.connect(self.logMessage)
        self._enrich_workers[job.id] = worker
        self.enrich_pool.start(worker)

    def _on_enrich_done(self, job_id: str, info: dict) -> None:
        self._enrich_workers.pop(job_id, None)
        job = self.jobs.get(job_id)
        if not job:
            return
        if info.get("is_playlist"):
            job.title = info.get("title") or job.title
            job.uploader = info.get("uploader") or ""
            job.meta_loaded = True
            job.status = JobStatus.QUEUED
            job.stage = "En cola"
            self.jobUpdated.emit(job_id)
            self._emit_stats()
            self._pump()
            return
        job.title = info.get("title") or job.title
        job.uploader = info.get("uploader") or job.uploader
        job.duration = info.get("duration") or job.duration
        job.thumbnail_url = info.get("thumbnail") or job.thumbnail_url
        job.meta_loaded = True
        if job.status is JobStatus.PROBING:
            job.status = JobStatus.QUEUED
            job.stage = "En cola"
        self.jobUpdated.emit(job_id)
        self._emit_stats()
        self._pump()

    def _on_enrich_failed(self, job_id: str, error: str) -> None:
        self._enrich_workers.pop(job_id, None)
        job = self.jobs.get(job_id)
        if not job:
            return
        job.meta_loaded = True
        job.status = JobStatus.ERROR
        job.error = error
        job.stage = "No se pudo analizar"
        job.finished_at = time.time()
        self.jobUpdated.emit(job_id)
        self.logMessage.emit("error", f"No se pudo analizar {job.url}: {error}")
        self._emit_stats()

    def _pump(self) -> None:
        if self._paused:
            return
        limit = max(1, self.pool.maxThreadCount())
        while len(self._active) < limit:
            candidate = next(
                (
                    job
                    for job in self.ordered_jobs()
                    if job.status is JobStatus.QUEUED
                    and job.meta_loaded
                    and (self.auto_start or job.id in self._approved)
                ),
                None,
            )
            if candidate is None:
                break
            self._start_job(candidate)

    def _start_job(self, job: Job) -> None:
        worker = _DownloadWorker(job)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.finished.connect(self._on_finished)
        worker.signals.failed.connect(self._on_failed)
        worker.signals.cancelled.connect(self._on_cancelled)
        worker.signals.log.connect(self.logMessage)
        self._workers[job.id] = worker
        self._active.add(job.id)
        job.status = JobStatus.DOWNLOADING
        job.stage = "Iniciando descarga"
        job.error = ""
        job.progress = 0
        job.speed = 0
        job.eta = 0
        self.jobUpdated.emit(job.id)
        self._emit_stats()
        self.pool.start(worker)

    def _on_progress(self, job_id: str, data: dict) -> None:
        job = self.jobs.get(job_id)
        if not job:
            return
        status = data.get("status")
        if status == "downloading":
            job.status = JobStatus.DOWNLOADING
            job.progress = max(job.progress, min(99.0, float(data.get("progress") or 0)))
        elif status == "postprocessing":
            job.status = JobStatus.PROCESSING
            job.progress = max(job.progress, min(99.9, float(data.get("progress") or 97)))
        elif status == "probing":
            job.status = JobStatus.DOWNLOADING
        job.stage = data.get("stage") or job.stage
        job.speed = float(data.get("speed") or 0)
        job.eta = float(data.get("eta") or 0)
        if data.get("downloaded") is not None:
            job.downloaded = int(data.get("downloaded") or 0)
        if data.get("total") is not None:
            job.total = int(data.get("total") or 0)
        self.jobUpdated.emit(job_id)
        self._emit_stats()

    def _finalize(self, job: Job) -> None:
        self._active.discard(job.id)
        self._approved.discard(job.id)
        self._workers.pop(job.id, None)

    def _on_finished(self, job_id: str, result: dict) -> None:
        job = self.jobs.get(job_id)
        if not job:
            return
        self._finalize(job)
        job.status = JobStatus.DONE
        job.progress = 100
        job.speed = 0
        job.eta = 0
        job.stage = "Completado"
        job.finished_at = time.time()
        job.title = result.get("title") or job.title
        job.uploader = result.get("uploader") or job.uploader
        job.duration = float(result.get("duration") or job.duration or 0)
        job.thumbnail_url = result.get("thumbnail") or job.thumbnail_url
        job.filepath = result.get("filepath") or job.filepath
        job.size = int(result.get("size") or 0)
        try:
            self.history.add(job)
            self.libraryChanged.emit()
        except Exception as exc:
            self.logMessage.emit("error", f"No se pudo guardar en el historial: {exc}")
        self.jobUpdated.emit(job_id)
        self.jobCompleted.emit(job_id)
        self.logMessage.emit("success", f"Completado: {job.title}")
        self._emit_stats()
        self._pump()

    def _on_failed(self, job_id: str, error: str) -> None:
        job = self.jobs.get(job_id)
        if not job:
            return
        self._finalize(job)
        job.status = JobStatus.ERROR
        job.error = error
        job.stage = "Error"
        job.speed = 0
        job.eta = 0
        job.finished_at = time.time()
        self.jobUpdated.emit(job_id)
        self.jobFailed.emit(job_id, error)
        self.logMessage.emit("error", f"Error en {job.display_title}: {error}")
        self._emit_stats()
        self._pump()

    def _on_cancelled(self, job_id: str) -> None:
        job = self.jobs.get(job_id)
        if not job:
            return
        self._finalize(job)
        job.status = JobStatus.CANCELLED
        job.stage = "Cancelado"
        job.speed = 0
        job.eta = 0
        job.finished_at = time.time()
        self.jobUpdated.emit(job_id)
        self.logMessage.emit("warning", f"Cancelado: {job.display_title}")
        self._emit_stats()
        self._pump()

    def _emit_stats(self) -> None:
        jobs = list(self.jobs.values())
        active = [j for j in jobs if j.status.is_active]
        queued = [j for j in jobs if j.status in (JobStatus.QUEUED, JobStatus.PROBING)]
        done = [j for j in jobs if j.status is JobStatus.DONE]
        errors = [j for j in jobs if j.status is JobStatus.ERROR]
        considered = [j for j in jobs if j.status not in (JobStatus.CANCELLED,)]
        overall = (sum(j.progress for j in considered) / len(considered)) if considered else 0.0
        if considered and all(j.status is JobStatus.DONE for j in considered):
            overall = 100.0
        self.statsChanged.emit(
            {
                "queued": len(queued),
                "active": len(active),
                "done": len(done),
                "errors": len(errors),
                "total": len(jobs),
                "overall": overall,
                "speed": sum(j.speed for j in active),
                "eta": max((j.eta for j in active), default=0),
                "completed_size": sum(j.size for j in done),
                "paused": self._paused,
            }
        )

    # -------------------------------------------------------------- playlists
    def resolve_playlist(self, url: str, options: DownloadOptions) -> str:
        request_id = f"pl-{int(time.time() * 1000)}-{len(self._playlist_workers)}"
        worker = _PlaylistWorker(request_id, url, options)
        worker.signals.done.connect(self._on_playlist_done)
        worker.signals.failed.connect(self._on_playlist_failed)
        self._playlist_workers[request_id] = worker
        self.playlist_pool.start(worker)
        return request_id

    def _on_playlist_done(self, request_id: str, info: dict) -> None:
        self._playlist_workers.pop(request_id, None)
        self.playlistResolved.emit(request_id, info)

    def _on_playlist_failed(self, request_id: str, error: str) -> None:
        self._playlist_workers.pop(request_id, None)
        self.playlistFailed.emit(request_id, error)
