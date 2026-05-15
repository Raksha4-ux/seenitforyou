"""Persistent store of processed Gmail message IDs to prevent duplicate alerts."""

import json
import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)


class ProcessedMessageStore:
    """Thread-safe JSON-backed set of Gmail message IDs."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._ids: set[str] = set()
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, list):
                self._ids = {str(x) for x in data}
            else:
                logger.warning("State file format invalid; starting fresh")
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not load state file %s: %s", self._path, exc)

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = sorted(self._ids)
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def contains(self, message_id: str) -> bool:
        with self._lock:
            return message_id in self._ids

    def add(self, message_id: str) -> None:
        with self._lock:
            if message_id in self._ids:
                return
            self._ids.add(message_id)
            self._save()

    def count(self) -> int:
        with self._lock:
            return len(self._ids)
