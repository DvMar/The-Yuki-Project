"""
Cognitive Load Tracker — somatic fatigue signal.

Accumulates load with each LLM inference call and decays each dream cycle.
The load float is exposed to:
  - api/server.py  → sampler profile selection (high load → prefer PROFILE_CHAT)
  - reflective_daemon.py → desire-to-connect accumulation rate
  - server.py proactive builder → brevity hint in system prompt

Load scale:
  0.0 – 0.3   rested          — no modification
  0.3 – 0.6   moderate load   — slight preference for shorter responses
  0.6 – 0.8   tired           — significant brevity pressure, slower desire build
  0.8 – 1.0   exhausted       — strong brevity, proactive breakout suppressed

Accumulation & decay constants are tuned for a typical conversation pace of
~1 message / minute. At that rate the organism reaches "tired" after ~10
consecutive turns and recovers in ~7 minutes of quiet.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# How much load each LLM call adds
_LOAD_PER_CALL: float = 0.07

# How much a dream-cycle tick decays the load (multiplicative)
_DECAY_FACTOR: float = 0.88   # per tick; at 2-min ticks, ~60% decay per 10 min

# If load exceeds this, inject a brevity hint in the proactive block
LOAD_BREVITY_THRESHOLD: float = 0.60

# If load exceeds this, suppress proactive breakout entirely
LOAD_SUPPRESS_THRESHOLD: float = 0.82


class CognitiveLoadTracker:
    """
    Thread-safe cognitive load accumulator.

    Designed to be instantiated once at startup (as a global in api/context.py)
    and shared across the async web layer and the daemon.
    """

    def __init__(self) -> None:
        self._load: float = 0.0
        self._lock = threading.Lock()
        self._last_call_time: Optional[datetime] = None
        self._total_calls: int = 0

    # ------------------------------------------------------------------
    # Mutators
    # ------------------------------------------------------------------

    def on_llm_call(self, weight: float = 1.0) -> float:
        """
        Call immediately before each LLM inference.
        weight > 1.0 for heavier calls (e.g. structured JSON reflection).
        Returns new load.
        """
        with self._lock:
            delta = _LOAD_PER_CALL * max(0.1, weight)
            self._load = min(1.0, self._load + delta)
            self._last_call_time = datetime.now()
            self._total_calls += 1
            logger.debug(f"[LOAD] llm_call +{delta:.3f} → {self._load:.3f}")
        return self._load

    def on_dream_cycle(self) -> float:
        """
        Call once per dream cycle tick (idle time).
        Applies multiplicative decay — the organism rests between cycles.
        Returns new load.
        """
        with self._lock:
            self._load = max(0.0, self._load * _DECAY_FACTOR)
            logger.debug(f"[LOAD] dream_decay → {self._load:.3f}")
        return self._load

    def on_interaction(self) -> float:
        """
        Call when user sends a message. Adds a small load bump
        (reading + processing), but less than inference.
        Returns new load.
        """
        with self._lock:
            # Just a tiny read-cost, main cost comes from on_llm_call
            self._load = min(1.0, self._load + 0.02)
        return self._load

    # ------------------------------------------------------------------
    # Readers
    # ------------------------------------------------------------------

    @property
    def load(self) -> float:
        """Current load [0.0 – 1.0]."""
        with self._lock:
            return self._load

    @property
    def is_tired(self) -> bool:
        return self.load >= LOAD_BREVITY_THRESHOLD

    @property
    def is_exhausted(self) -> bool:
        return self.load >= LOAD_SUPPRESS_THRESHOLD

    def desire_rate_modifier(self) -> float:
        """
        Multiplier for DesireToConnect accumulation rate.
        Tired organism accumulates desire more slowly (too drained to reach out).
        """
        load = self.load
        if load < 0.30:
            return 1.0
        if load < 0.60:
            return 0.80
        if load < 0.82:
            return 0.55
        return 0.30

    def brevity_hint(self) -> str:
        """One-sentence hint to inject into proactive system prompt."""
        load = self.load
        if load < LOAD_BREVITY_THRESHOLD:
            return ""
        if load < LOAD_SUPPRESS_THRESHOLD:
            return "You've been thinking hard — keep it short and unhurried, one or two sentences."
        return "You're tired. A single sentence is enough. Don't force it."

    def get_state(self) -> dict:
        return {
            "load":         round(self.load, 3),
            "is_tired":     self.is_tired,
            "is_exhausted": self.is_exhausted,
            "total_calls":  self._total_calls,
            "last_call":    self._last_call_time.isoformat() if self._last_call_time else "",
        }
