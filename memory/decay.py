"""
Memory Decay & Salience Evolution System
Implements layered memory decay with forgetting curves and dynamic salience scoring.
Low-salience facts fade gradually, high-salience facts persist.
Supports threaded narrative memory for recurring themes.
"""

import logging
import json
import math
import os
from datetime import datetime
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)


class MemoryDecaySystem:
    """
    Manages memory decay with forgetting curves.
    Implements Ebbinghaus-inspired spacing and salience-based retention.
    """

    # Decay parameters
    DECAY_RATE = 0.02  # 2% decay per day
    SALIENCE_MULTIPLIER = 0.5  # High-salience memories decay slower
    RECENCY_BOOST = 0.1  # Recent access boosts retention
    MIN_RETENTION = 0.1  # Never decay below 10% salience

    def __init__(self, db_path: str = "./persistent_state"):
        """Initialize memory decay system."""
        self.db_path = db_path
        self.decay_state_path = f"{db_path}/memory_decay_state.json"
        self.decay_state = self._load_decay_state()

    def compute_decay(
        self,
        memory_fact: Dict,
        current_time: datetime,
        access_count: int = 0,
        last_accessed: Optional[datetime] = None
    ) -> float:
        """
        Compute effective salience after decay.
        
        Args:
            memory_fact: Fact dict with 'salience_score', 'created_at'
            current_time: Current timestamp for calculation
            access_count: Number of times fact has been accessed
            last_accessed: When fact was last accessed
        
        Returns:
            Decayed salience score (0.0 to 1.0)
        """
        original_salience = float(memory_fact.get("salience_score", 0.5))
        created_at = memory_fact.get("created_at")

        if not created_at:
            return original_salience

        # Parse timestamps
        try:
            if isinstance(created_at, str):
                created = datetime.fromisoformat(created_at)
            else:
                created = created_at

            # Calculate age in days
            age_days = (current_time - created).days
            if age_days < 0:
                age_days = 0

        except Exception as e:
            logger.error(f"Error parsing timestamp: {e}")
            return original_salience

        # Ebbinghaus-inspired decay curve
        # f(t) = e^(-t / c) where c is time constant based on salience
        if age_days == 0:
            decay_factor = 1.0
        else:
            # Time constant increases with salience (high-salience memories persist longer)
            time_constant = 10.0 + (original_salience * 20.0)  # 10-30 day range
            decay_factor = math.exp(-age_days / time_constant)

        # Recency boost (boost if recently accessed)
        if last_accessed:
            try:
                if isinstance(last_accessed, str):
                    last_access = datetime.fromisoformat(last_accessed)
                else:
                    last_access = last_accessed

                hours_since_access = (current_time - last_access).total_seconds() / 3600.0
                if hours_since_access < 24:
                    # Strong boost for recent access
                    recency_boost = 1.0 + (self.RECENCY_BOOST * (1.0 - hours_since_access / 24.0))
                elif hours_since_access < 7 * 24:
                    # Moderate boost for week-old access
                    recency_boost = 1.0 + (self.RECENCY_BOOST * 0.5)
                else:
                    recency_boost = 1.0

            except Exception:
                recency_boost = 1.0
        else:
            recency_boost = 1.0

        # Combine factors
        decayed_salience = original_salience * decay_factor * recency_boost
        decayed_salience = max(self.MIN_RETENTION, min(1.0, decayed_salience))

        return decayed_salience

    def filter_memories_by_decay(
        self,
        memories: List[Dict],
        current_time: Optional[datetime] = None,
        threshold: float = 0.15
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Filter memories that have decayed below threshold.
        
        Args:
            memories: List of memory facts
            current_time: Current timestamp (default: now)
            threshold: Salience threshold for retention (default: 15%)
        
        Returns:
            Tuple of (retained_memories, forgotten_memories)
        """
        if current_time is None:
            current_time = datetime.now()

        retained = []
        forgotten = []

        for memory in memories:
            decayed = self.compute_decay(memory, current_time)
            if decayed > threshold:
                retained.append(memory)
            else:
                forgotten.append(memory)

        return retained, forgotten

    def update_access_count(self, memory_id: str, current_time: datetime) -> None:
        """Update access metadata for a memory."""
        self.decay_state[memory_id] = {
            "last_accessed": current_time.isoformat(),
            "access_count": self.decay_state.get(memory_id, {}).get("access_count", 0) + 1
        }
        self._save_decay_state()

    def _load_decay_state(self) -> Dict:
        """Load decay state from disk."""
        try:
            with open(self.decay_state_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_decay_state(self) -> None:
        """Save decay state to disk."""
        try:
            with open(self.decay_state_path, 'w', encoding='utf-8') as f:
                json.dump(self.decay_state, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save decay state: {e}")


class DynamicSalienceScorer:
    """
    Dynamically updates salience scores based on interaction history.
    Tracks topic relevance and recurrence for organic growth.
    """

    def __init__(self, db_path: str = "./persistent_state"):
        """Initialize dynamic salience scorer."""
        self.db_path = db_path
        self.salience_history_path = f"{db_path}/salience_history.json"
        self.topic_freq_path = f"{db_path}/topic_frequencies.json"
        self.topic_frequencies = self._load_topic_frequencies()
        # Seed the file immediately if it didn't exist yet
        if not os.path.isfile(self.topic_freq_path):
            self._save_topic_frequencies()

    def update_salience_dynamic(
        self,
        memory_id: str,
        memory_fact: Dict,
        user_input: str,
        current_time: datetime,
        context: Dict = None
    ) -> float:
        """
        Dynamically recalculate salience based on relevance and recurrence.
        
        Args:
            memory_id: Unique ID for the memory
            memory_fact: The memory being scored
            user_input: Current user input context
            current_time: Current datetime
            context: Additional context (topics discussed, etc.)
        
        Returns:
            Updated salience score
        """
        base_salience = float(memory_fact.get("salience_score", 0.5))

        # 1. Recurrence factor: If topic appears again, boost salience
        recurrence_boost = self._compute_recurrence_boost(memory_fact, user_input, context)

        # 2. Topic decay: Topics not discussed recently decrease slightly
        topic_decay = self._compute_topic_decay(memory_fact, current_time, context)

        # 3. Specificity bonus: More specific facts maintain higher salience
        specificity_bonus = self._compute_specificity_bonus(memory_fact)

        # 4. Emotional resonance: Emotionally significant facts remain salient
        emotional_bonus = self._compute_emotional_bonus(memory_fact)

        # Combine factors with smoothing
        updated_salience = (
            base_salience * (1.0 + recurrence_boost - topic_decay) +
            (specificity_bonus * 0.05) +
            (emotional_bonus * 0.03)
        )

        # Clamp to valid range
        updated_salience = max(0.0, min(1.0, updated_salience))

        # Track for trend analysis
        self._record_salience_change(memory_id, base_salience, updated_salience)

        # Persist updated topic frequencies (incremented during recurrence scoring)
        self._save_topic_frequencies()

        return updated_salience

    def _compute_recurrence_boost(self, memory_fact: Dict, user_input: str, context: Dict = None) -> float:
        """Boost salience if topic appears again."""
        if not user_input:
            return 0.0

        fact_text = memory_fact.get("content", "").lower()
        input_text = user_input.lower()

        # Check for keyword overlaps
        fact_words = set(fact_text.split())
        input_words = set(input_text.split())
        overlap = len(fact_words & input_words)

        if overlap > 0:
            # Track topic frequency for each overlapping word
            for word in fact_words & input_words:
                if len(word) > 3:  # Skip short stop-words
                    self.topic_frequencies[word] = self.topic_frequencies.get(word, 0) + 1

            # Normalize overlap (max boost at ~5 overlapping words)
            recurrence_score = min(1.0, overlap / 5.0)
            return recurrence_score * 0.15  # Up to 15% boost

        return 0.0

    def _compute_topic_decay(self, memory_fact: Dict, current_time: datetime, context: Dict = None) -> float:
        """Apply mild decay for topics not recently discussed."""
        created_at = memory_fact.get("created_at")
        if not created_at:
            return 0.0

        try:
            if isinstance(created_at, str):
                created = datetime.fromisoformat(created_at)
            else:
                created = created_at

            days_ago = (current_time - created).days
            
            # Slow decay: 1% per week
            weeks_ago = days_ago / 7.0
            decay = min(0.1, weeks_ago * 0.01)
            return decay

        except Exception:
            return 0.0

    def _compute_specificity_bonus(self, memory_fact: Dict) -> float:
        """More specific facts get higher salience."""
        content = memory_fact.get("content", "")
        
        # Simple heuristic: longer, more detailed facts are more specific
        word_count = len(content.split())
        if word_count < 5:
            specificity = 0.3
        elif word_count < 20:
            specificity = 0.6
        else:
            specificity = 1.0

        return specificity

    def _compute_emotional_bonus(self, memory_fact: Dict) -> float:
        """Emotionally significant facts stay salient."""
        emotional_words = {
            "love", "hate", "passion", "important", "favorite", "dream",
            "goal", "fear", "joy", "sadness", "frustrated", "excited"
        }

        content = memory_fact.get("content", "").lower()
        matches = sum(1 for word in emotional_words if word in content)

        if matches > 0:
            return min(1.0, matches / 3.0)
        return 0.0

    def _record_salience_change(self, memory_id: str, old_score: float, new_score: float) -> None:
        """Record salience change for trend analysis."""
        try:
            with open(self.salience_history_path, 'a', encoding='utf-8') as f:
                record = {
                    "memory_id": memory_id,
                    "timestamp": datetime.now().isoformat(),
                    "old_score": old_score,
                    "new_score": new_score,
                    "delta": new_score - old_score
                }
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.error(f"Failed to record salience change: {e}")

    def _load_topic_frequencies(self) -> Dict:
        """Load topic frequency statistics."""
        try:
            with open(self.topic_freq_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_topic_frequencies(self) -> None:
        """Persist topic frequency statistics."""
        try:
            with open(self.topic_freq_path, 'w', encoding='utf-8') as f:
                json.dump(self.topic_frequencies, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save topic frequencies: {e}")


class ThreadedNarrativeMemory:
    """
    Tracks recurring themes across episodes.
    Maintains narrative threads that evolve over time.
    """

    def __init__(self, db_path: str = "./persistent_state"):
        """Initialize threaded narrative memory."""
        self.db_path = db_path
        self.threads_path = f"{db_path}/narrative_threads.json"
        self.threads = self._load_threads()

    def add_to_thread(
        self,
        theme_name: str,
        episode_content: str,
        timestamp: datetime = None,
        metadata: Dict = None
    ) -> str:
        """
        Add an episode to a narrative thread.
        
        Args:
            theme_name: Name of recurring theme
            episode_content: Content for this episode
            timestamp: When this episode occurred
            metadata: Additional metadata
        
        Returns:
            Thread ID
        """
        if theme_name not in self.threads:
            self.threads[theme_name] = {
                "name": theme_name,
                "episodes": [],
                "created_at": datetime.now().isoformat(),
                "evolution_score": 0.5
            }

        episode = {
            "timestamp": (timestamp or datetime.now()).isoformat(),
            "content": episode_content,
            "metadata": metadata or {}
        }

        self.threads[theme_name]["episodes"].append(episode)
        self._update_evolution_score(theme_name)
        self._save_threads()

        return theme_name

    def get_thread_summary(self, theme_name: str, max_episodes: int = 5) -> str:
        """Get summary of a narrative thread."""
        if theme_name not in self.threads:
            return ""

        thread = self.threads[theme_name]
        episodes = thread.get("episodes", [])[-max_episodes:]

        summary_parts = [f"Theme: {theme_name}"]
        for episode in episodes:
            content_preview = episode.get("content", "")[:100]
            timestamp = episode.get("timestamp", "")[:10]
            summary_parts.append(f"  [{timestamp}] {content_preview}...")

        return "\n".join(summary_parts)

    def _update_evolution_score(self, theme_name: str) -> None:
        """Update how much a theme has evolved."""
        thread = self.threads[theme_name]
        episodes = thread.get("episodes", [])

        if len(episodes) < 2:
            thread["evolution_score"] = 0.5
            return

        # Simple evolution: measure diversity of content
        recent = [e.get("content", "") for e in episodes[-3:]]
        unique_words = set()
        for content in recent:
            unique_words.update(content.lower().split())

        evolution = min(1.0, len(unique_words) / 50.0)
        thread["evolution_score"] = evolution

    def _load_threads(self) -> Dict:
        """Load narrative threads from disk."""
        try:
            with open(self.threads_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_threads(self) -> None:
        """Save narrative threads to disk."""
        try:
            with open(self.threads_path, 'w', encoding='utf-8') as f:
                json.dump(self.threads, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save threads: {e}")
