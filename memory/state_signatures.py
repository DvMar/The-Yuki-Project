"""
State Signature Store

Phase A persistence scaffold for organismic causal breadcrumbs.
Stores compact cycle signatures in persistent_state/state_signatures.json
with bounded size and atomic writes.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from typing import Any, Dict, List


class StateSignatureStore:
    """Append-only bounded store for compact state signatures."""

    def __init__(self, db_path: str = "./persistent_state", max_entries: int = 2000) -> None:
        self.db_path = db_path
        self.max_entries = max(100, int(max_entries))
        os.makedirs(self.db_path, exist_ok=True)
        self.path = os.path.join(self.db_path, "state_signatures.json")
        self._lock = threading.Lock()
        self._entries: List[Dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            self._entries = []
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if isinstance(payload, list):
                self._entries = payload[-self.max_entries :]
            else:
                self._entries = []
        except Exception:
            self._entries = []

    def _save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._entries[-self.max_entries :], f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)

    def append(self, signature: Dict[str, Any]) -> None:
        if not isinstance(signature, dict):
            return

        entry = dict(signature)
        entry.setdefault("timestamp", datetime.now().isoformat())

        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self.max_entries:
                self._entries = self._entries[-self.max_entries :]
            self._save()

    def get_recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        n = max(1, int(limit))
        with self._lock:
            return [dict(item) for item in self._entries[-n:]]

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "entries": len(self._entries),
                "max_entries": self.max_entries,
                "path": self.path,
            }
