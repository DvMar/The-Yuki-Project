"""
Persistent Proactive Intention Store

Delta 3 Phase C:
- Persist proactive intentions to disk
- Hydrate unresolved intentions into runtime queue on startup
- Resolve delivered intentions when surfaced to user
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4


class ProactiveIntentionStore:
    """Durable store for proactive intentions with bounded retention."""

    _DEFAULT_HALFLIFE_MINUTES = {
        "curiosity": 30,
        "reflection": 90,
        "memory": 180,
        "creative": 90,
        "hypothetical": 90,
    }

    def __init__(self, db_path: str = "./persistent_state", max_entries: int = 2000) -> None:
        self.db_path = db_path
        self.max_entries = max(200, int(max_entries))
        os.makedirs(self.db_path, exist_ok=True)
        self.path = os.path.join(self.db_path, "proactive_intentions.json")
        self._lock = threading.Lock()
        self._items: List[Dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            self._items = []
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            self._items = payload if isinstance(payload, list) else []
        except Exception:
            self._items = []

    def _save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._items[-self.max_entries :], f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)

    @staticmethod
    def _parse_dt(value: str) -> Optional[datetime]:
        try:
            return datetime.fromisoformat(value)
        except Exception:
            return None

    def _default_expires_at(self, dream_mode: str) -> str:
        minutes = self._DEFAULT_HALFLIFE_MINUTES.get((dream_mode or "").strip().lower(), 90)
        return (datetime.now() + timedelta(minutes=minutes)).isoformat()

    def _expire_locked(self) -> int:
        now = datetime.now()
        changed = 0
        for item in self._items:
            if item.get("status") != "pending":
                continue
            exp = self._parse_dt(str(item.get("expires_at", "")))
            if exp and exp < now:
                item["status"] = "expired"
                item["resolved_at"] = now.isoformat()
                changed += 1
        return changed

    def create_intention(
        self,
        *,
        message: str,
        dream_mode: str = "",
        salience: float = 0.0,
        urgency: float = 0.0,
        desire_snapshot: float = 0.0,
        source: str = "dreamcycle",
    ) -> Dict[str, Any]:
        now = datetime.now().isoformat()
        item = {
            "id": f"intent_{uuid4().hex}",
            "created_at": now,
            "expires_at": self._default_expires_at(dream_mode),
            "status": "pending",
            "dream_mode": (dream_mode or "").strip().lower(),
            "salience": round(float(salience or 0.0), 4),
            "urgency": round(float(urgency or 0.0), 4),
            "desire_snapshot": round(float(desire_snapshot or 0.0), 4),
            "message": str(message or "").strip(),
            "source": source,
        }
        with self._lock:
            self._items.append(item)
            self._expire_locked()
            if len(self._items) > self.max_entries:
                self._items = self._items[-self.max_entries :]
            self._save()
        return dict(item)

    def mark_status(self, intention_id: str, status: str) -> bool:
        status = (status or "").strip().lower()
        if status not in {"pending", "delivered", "expired", "suppressed"}:
            return False
        with self._lock:
            for item in self._items:
                if item.get("id") == intention_id:
                    item["status"] = status
                    item["resolved_at"] = datetime.now().isoformat()
                    self._save()
                    return True
        return False

    def get_pending(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            changed = self._expire_locked()
            if changed:
                self._save()
            pending = [i for i in self._items if i.get("status") == "pending"]
            return [dict(item) for item in pending[-max(1, int(limit)) :]]

    def get_recent_by_status(self, status: str, limit: int = 20) -> List[Dict[str, Any]]:
        status = (status or "").strip().lower()
        if status not in {"pending", "delivered", "expired", "suppressed"}:
            return []
        with self._lock:
            changed = self._expire_locked()
            if changed:
                self._save()
            rows = [i for i in self._items if i.get("status") == status]
            return [dict(item) for item in rows[-max(1, int(limit)) :]]

    def suppress_pending(self, reason: str = "cognitive_exhaustion") -> int:
        with self._lock:
            changed = self._expire_locked()
            now = datetime.now().isoformat()
            count = 0
            for item in self._items:
                if item.get("status") == "pending":
                    item["status"] = "suppressed"
                    item["resolved_at"] = now
                    item["suppression_reason"] = reason
                    count += 1
            if count or changed:
                self._save()
            return count

    def hydrate_runtime_queue(self, queue, max_items: int = 20) -> int:
        pending = self.get_pending(limit=max_items)
        if not pending:
            return 0

        existing_ids = set()
        try:
            for item in list(queue):
                iid = item.get("intention_id") or (item.get("metadata", {}) or {}).get("intention_id")
                if iid:
                    existing_ids.add(iid)
        except Exception:
            pass

        added = 0
        for item in pending:
            iid = item.get("id")
            if iid in existing_ids:
                continue
            payload = {
                "message": item.get("message", ""),
                "timestamp": item.get("created_at", datetime.now().isoformat()),
                "origin": "dreamcycle",
                "intention_id": iid,
                "metadata": {
                    "source": item.get("source", "dreamcycle"),
                    "dream_mode": item.get("dream_mode", ""),
                    "salience": item.get("salience", 0.0),
                    "urgency": item.get("urgency", 0.0),
                    "desire_snapshot": item.get("desire_snapshot", 0.0),
                    "hydrated": True,
                    "intention_id": iid,
                },
            }
            queue.append(payload)
            added += 1
        return added

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            self._expire_locked()
            total = len(self._items)
            pending = sum(1 for i in self._items if i.get("status") == "pending")
            delivered = sum(1 for i in self._items if i.get("status") == "delivered")
            expired = sum(1 for i in self._items if i.get("status") == "expired")
            suppressed = sum(1 for i in self._items if i.get("status") == "suppressed")
            return {
                "total": total,
                "pending": pending,
                "delivered": delivered,
                "expired": expired,
                "suppressed": suppressed,
                "path": self.path,
            }
