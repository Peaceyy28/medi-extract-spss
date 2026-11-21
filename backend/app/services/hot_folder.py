"""Watchdog Hot-Folder scanner listener with write-completion debouncing."""

from __future__ import annotations

import logging
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from app.config import get_settings
from app.schemas import ScannerWatchStatus
from app.services.ingestion import ingest_files
from app.services.project_store import get_project_store

_LOGGER = logging.getLogger(__name__)
SUPPORTED_SCAN_EXTENSIONS = {".pdf", ".tif", ".tiff", ".png", ".jpg", ".jpeg"}


def _move_with_retry(src: Path, dest: Path, attempts: int = 4, delay_s: float = 0.2) -> None:
    """Retry file move across brief Windows Explorer / antivirus handles."""
    for attempt in range(attempts):
        try:
            shutil.move(str(src), str(dest))
            return
        except PermissionError:
            if attempt >= attempts - 1:
                raise
            time.sleep(delay_s)


def wait_for_file_stability(
    path: Path, stability_ms: int = 500, max_wait_s: float = 10.0
) -> bool:
    """Wait until file exists, is non-empty, and size stays constant for stability_ms."""
    deadline = time.monotonic() + max_wait_s
    required_stable_s = max(0.05, stability_ms / 1000.0)
    poll_s = min(0.05, required_stable_s / 3.0)

    last_size = -1
    stable_since: float | None = None

    while time.monotonic() < deadline:
        if not path.is_file():
            time.sleep(poll_s)
            continue
        try:
            size = path.stat().st_size
        except OSError:
            time.sleep(poll_s)
            continue

        now = time.monotonic()
        if size > 0 and size == last_size:
            if stable_since is not None and (now - stable_since) >= required_stable_s:
                return True
        else:
            last_size = size
            stable_since = now if size > 0 else None

        time.sleep(poll_s)

    return False


class _ScanQueueEventHandler(FileSystemEventHandler):
    def __init__(self, watcher: HotFolderWatcher) -> None:
        super().__init__()
        self._watcher = watcher

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._watcher.schedule_candidate(Path(str(event.src_path)))

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory and hasattr(event, "dest_path"):
            self._watcher.schedule_candidate(Path(str(event.dest_path)))


class HotFolderWatcher:
    """Watches a local/LAN scanner drop directory and auto-ingests completed scans."""

    def __init__(self, default_watch_folder: str) -> None:
        self._lock = threading.Lock()
        self._observer: Observer | None = None
        self._active = False
        self._project_id: str | None = None
        self._watch_folder = default_watch_folder
        self._debounce_ms = 500
        self._files_processed_count = 0
        self._last_event_at: str | None = None
        self._in_flight: set[Path] = set()

    def start(
        self, project_id: str, watch_folder: str | None = None, debounce_ms: int = 500
    ) -> ScannerWatchStatus:
        self.stop()

        target_dir = Path(watch_folder or self._watch_folder).expanduser().resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "_processed").mkdir(parents=True, exist_ok=True)

        observer = Observer()
        handler = _ScanQueueEventHandler(self)
        observer.schedule(handler, str(target_dir), recursive=False)
        observer.start()

        with self._lock:
            self._observer = observer
            self._active = True
            self._project_id = project_id
            self._watch_folder = str(target_dir)
            self._debounce_ms = debounce_ms

        return self.status()

    def stop(self) -> ScannerWatchStatus:
        with self._lock:
            obs = self._observer
            self._observer = None
            self._active = False

        if obs is not None:
            obs.stop()
            obs.join(timeout=3.0)

        return self.status()

    def status(self) -> ScannerWatchStatus:
        with self._lock:
            return ScannerWatchStatus(
                active=self._active,
                watch_folder=self._watch_folder,
                project_id=self._project_id,
                debounce_ms=self._debounce_ms,
                files_processed_count=self._files_processed_count,
                last_event_at=self._last_event_at,
            )

    def schedule_candidate(self, path: Path) -> None:
        resolved = path.resolve()
        if "_processed" in resolved.parts:
            return
        if resolved.suffix.lower() not in SUPPORTED_SCAN_EXTENSIONS:
            return

        with self._lock:
            if not self._active or self._project_id is None:
                return
            if resolved in self._in_flight:
                return
            self._in_flight.add(resolved)
            project_id = self._project_id
            debounce_ms = self._debounce_ms
            watch_dir = Path(self._watch_folder)

        worker = threading.Thread(
            target=self._process_file,
            args=(resolved, project_id, debounce_ms, watch_dir),
            daemon=True,
        )
        worker.start()

    def _process_file(
        self, path: Path, project_id: str, debounce_ms: int, watch_dir: Path
    ) -> None:
        try:
            if not wait_for_file_stability(path, stability_ms=debounce_ms):
                return
            with self._lock:
                if not self._active:
                    return
            payload = path.read_bytes()
            store = get_project_store()
            ingest_files(
                store=store,
                project_id=project_id,
                files=[(path.name, payload)],
                source="hot_folder",
                description="Auto-ingested from scanner Hot Folder",
            )
            processed_dir = watch_dir / "_processed"
            processed_dir.mkdir(parents=True, exist_ok=True)
            dest = processed_dir / path.name
            if dest.exists():
                stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
                dest = processed_dir / f"{path.stem}_{stamp}{path.suffix}"
            _move_with_retry(path, dest)

            with self._lock:
                self._files_processed_count += 1
                self._last_event_at = datetime.now(timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                )
        except Exception:
            _LOGGER.exception("Failed processing hot-folder file: %s", path)
        finally:
            with self._lock:
                self._in_flight.discard(path)


_WATCHER_LOCK = threading.Lock()
_WATCHER_INSTANCE: HotFolderWatcher | None = None


def get_hot_folder_watcher() -> HotFolderWatcher:
    global _WATCHER_INSTANCE
    with _WATCHER_LOCK:
        if _WATCHER_INSTANCE is None:
            _WATCHER_INSTANCE = HotFolderWatcher(
                default_watch_folder=get_settings().watch_folder
            )
        return _WATCHER_INSTANCE


def reset_hot_folder_watcher() -> None:
    global _WATCHER_INSTANCE
    with _WATCHER_LOCK:
        obs = _WATCHER_INSTANCE
        _WATCHER_INSTANCE = None
    if obs is not None:
        obs.stop()
