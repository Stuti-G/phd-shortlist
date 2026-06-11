from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

_CACHE_PATH = Path(".cache/openalex.sqlite")


class Cache:
    def __init__(self, path: Path = _CACHE_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT)")
        self._conn.commit()

    def get(self, key: str) -> Optional[Any]:
        row = self._conn.execute("SELECT v FROM kv WHERE k = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)",
                (key, json.dumps(value)),
            )
            self._conn.commit()
