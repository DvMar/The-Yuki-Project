"""
Session-State / Short-Term Memory (STM) Buffer:
Lightweight working memory persistence across app restarts.
Inspired by memlayer's recall mechanisms.
Uses JSON for fast, deterministic serialization.
"""

import json
import os
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from collections import deque
from state.models import SessionMemoryEntry, SessionState
import logging

logger = logging.getLogger(__name__)


class SessionBuffer:
    """
    Short-term working memory buffer.
    Persists active conversation context to survive app restarts.
    """

    def __init__(self, db_path: str = "./persistent_state", max_entries: int = 50, archive_max_entries: int = 500, reset_on_startup: bool = True):
        """
        Initialize session buffer.

        Args:
            db_path: Path to store session state JSON
            max_entries: Maximum entries to keep in buffer
        """
        self.db_path = db_path
        self.session_filepath = os.path.join(db_path, "session_state.json")
        self.archive_filepath = os.path.join(db_path, "session_archive.json")
        self.max_entries = max_entries
        self.archive_max_entries = archive_max_entries
        self.session_id = str(uuid.uuid4())
        self.created_at = datetime.now()
        self.last_updated = datetime.now()
        self.buffer: deque = deque(maxlen=max_entries)
        self.archive_buffer: deque = deque(maxlen=archive_max_entries)
        self.total_exchanges = 0
        self.reset_on_startup = reset_on_startup

        # Load existing session state if available
        self._load_archive()
        if self.reset_on_startup:
            self.reset_session()
        else:
            self._load_session()

    def add_message(
        self,
        content: str,
        source: str = "user",
        importance: float = 0.5,
        metadata: Dict[str, Any] = None
    ) -> SessionMemoryEntry:
        """
        Add message to session buffer.

        Args:
            content: Message content
            source: "user" or "ai"
            importance: Importance score (0.0-1.0)
            metadata: Optional metadata

        Returns:
            The added SessionMemoryEntry
        """
        entry = SessionMemoryEntry(
            id=str(uuid.uuid4()),
            content=content,
            timestamp=datetime.now(),
            source=source,
            importance=importance,
            metadata=metadata or {}
        )

        if len(self.buffer) >= self.max_entries:
            evicted = self.buffer.popleft()
            self._archive_entry(evicted)

        self.buffer.append(entry)
        self.last_updated = datetime.now()

        if source == "user":
            self.total_exchanges += 1

        # Persist to disk
        self._save_session()

        logger.debug(f"Added {source} message to session buffer (size: {len(self.buffer)})")
        return entry

    def get_messages(
        self,
        limit: Optional[int] = None,
        source: Optional[str] = None,
        min_importance: float = 0.0
    ) -> List[SessionMemoryEntry]:
        """
        Retrieve messages from buffer.

        Args:
            limit: Max number of messages to return
            source: Filter by source ("user" or "ai")
            min_importance: Filter by minimum importance

        Returns:
            List of SessionMemoryEntry
        """
        messages = list(self.buffer)

        # Apply filters
        if source:
            messages = [m for m in messages if m.source == source]

        if min_importance > 0:
            messages = [m for m in messages if m.importance >= min_importance]

        # Return most recent first
        messages.reverse()

        return messages[:limit] if limit else messages

    def get_context_window(self, n_exchanges: int = 5) -> str:
        """
        Get recent conversation context as formatted string.

        Args:
            n_exchanges: Number of user-ai exchanges to include

        Returns:
            Formatted context string for LLM prompt
        """
        messages = self.get_messages(limit=n_exchanges * 2)
        messages.reverse()  # Restore chronological order

        if not messages:
            return "No recent conversation context."

        context_lines = []
        for msg in messages:
            timestamp_str = msg.timestamp.strftime("%H:%M:%S")
            prefix = "👤 User" if msg.source == "user" else "🤖 Assistant"
            context_lines.append(f"[{timestamp_str}] {prefix}: {msg.content[:100]}...")

        return "\n".join(context_lines)

    def clear_old_messages(self, days: int = 7) -> int:
        """
        Clear messages older than N days.

        Args:
            days: Age threshold in days

        Returns:
            Number of messages removed
        """
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(days=days)
        original_size = len(self.buffer)

        # Filter out old messages
        self.buffer = deque(
            (m for m in self.buffer if m.timestamp > cutoff),
            maxlen=self.max_entries
        )

        removed = original_size - len(self.buffer)
        if removed > 0:
            self._save_session()
            logger.info(f"Cleared {removed} old session messages")

        return removed

    def reset_session(self) -> None:
        """Start fresh session."""
        self.session_id = str(uuid.uuid4())
        self.created_at = datetime.now()
        self.last_updated = datetime.now()
        self.buffer.clear()
        self.total_exchanges = 0
        self._save_session()
        logger.info("Session reset")

    def get_session_summary(self) -> Dict[str, Any]:
        """Get session metadata and statistics."""
        messages = list(self.buffer)
        user_messages = [m for m in messages if m.source == "user"]
        ai_messages = [m for m in messages if m.source == "ai"]

        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat(),
            "total_messages": len(messages),
            "user_messages": len(user_messages),
            "ai_messages": len(ai_messages),
            "total_exchanges": self.total_exchanges,
            "buffer_fill_percentage": (len(messages) / self.max_entries) * 100,
            "archive_messages": len(self.archive_buffer),
            "archive_fill_percentage": (len(self.archive_buffer) / self.archive_max_entries) * 100,
            "avg_importance": (
                sum(m.importance for m in messages) / len(messages)
                if messages else 0.0
            )
        }

    def export_session(self) -> SessionState:
        """Export session as Pydantic model."""
        return SessionState(
            session_id=self.session_id,
            created_at=self.created_at,
            last_updated=self.last_updated,
            messages=list(self.buffer),
            context_window=self.max_entries,
            total_exchanges=self.total_exchanges
        )

    # ===== PERSISTENCE =====

    def _save_session(self) -> None:
        """Persist session buffer to JSON."""
        try:
            messages = [
                {
                    "id": m.id,
                    "content": m.content,
                    "timestamp": m.timestamp.isoformat(),
                    "source": m.source,
                    "importance": m.importance,
                    "metadata": m.metadata
                }
                for m in self.buffer
            ]

            session_data = {
                "session_id": self.session_id,
                "created_at": self.created_at.isoformat(),
                "last_updated": datetime.now().isoformat(),
                "total_exchanges": self.total_exchanges,
                "messages": messages
            }

            with open(self.session_filepath, "w", encoding="utf-8") as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error(f"Failed to save session state: {e}")

    def _save_archive(self) -> None:
        """Persist session archive to JSON."""
        try:
            archive_data = {
                "archived_at": datetime.now().isoformat(),
                "max_entries": self.archive_max_entries,
                "messages": list(self.archive_buffer)
            }

            with open(self.archive_filepath, "w", encoding="utf-8") as f:
                json.dump(archive_data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error(f"Failed to save session archive: {e}")

    def _load_session(self) -> None:
        """Load session buffer from JSON."""
        if not os.path.exists(self.session_filepath):
            return

        try:
            with open(self.session_filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.session_id = data.get("session_id", self.session_id)
            self.created_at = datetime.fromisoformat(
                data.get("created_at", self.created_at.isoformat())
            )
            self.last_updated = datetime.fromisoformat(
                data.get("last_updated", self.last_updated.isoformat())
            )
            self.total_exchanges = data.get("total_exchanges", 0)

            # Load messages
            loaded_messages = data.get("messages", [])

            if len(loaded_messages) > self.max_entries:
                overflow = len(loaded_messages) - self.max_entries
                for msg_data in loaded_messages[:overflow]:
                    self._archive_entry(msg_data)
                loaded_messages = loaded_messages[overflow:]

            for msg_data in loaded_messages:
                entry = SessionMemoryEntry(
                    id=msg_data["id"],
                    content=msg_data["content"],
                    timestamp=datetime.fromisoformat(msg_data["timestamp"]),
                    source=msg_data["source"],
                    importance=msg_data.get("importance", 0.5),
                    metadata=msg_data.get("metadata", {})
                )
                self.buffer.append(entry)

            logger.info(f"Loaded session {self.session_id} with {len(self.buffer)} messages")

        except Exception as e:
            logger.error(f"Failed to load session state: {e}")

    def _load_archive(self) -> None:
        """Load session archive from JSON."""
        if not os.path.exists(self.archive_filepath):
            return

        try:
            with open(self.archive_filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            for msg_data in data.get("messages", []):
                self.archive_buffer.append(msg_data)

            logger.info(f"Loaded session archive with {len(self.archive_buffer)} messages")

        except Exception as e:
            logger.error(f"Failed to load session archive: {e}")

    def _archive_entry(self, entry: Any) -> None:
        """Append an evicted entry to the bounded archive."""
        if isinstance(entry, SessionMemoryEntry):
            msg_data = {
                "id": entry.id,
                "content": entry.content,
                "timestamp": entry.timestamp.isoformat(),
                "source": entry.source,
                "importance": entry.importance,
                "metadata": entry.metadata
            }
        else:
            msg_data = entry

        self.archive_buffer.append(msg_data)
        self._save_archive()

    def health_check(self) -> Dict[str, Any]:
        """Health check for session buffer."""
        return {
            "healthy": len(self.buffer) <= self.max_entries,
            "buffer_size": len(self.buffer),
            "max_capacity": self.max_entries,
            "persisted": os.path.exists(self.session_filepath),
            "total_exchanges": self.total_exchanges,
            "archive_size": len(self.archive_buffer),
            "archive_max_capacity": self.archive_max_entries,
            "archive_persisted": os.path.exists(self.archive_filepath)
        }
