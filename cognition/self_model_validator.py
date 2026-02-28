"""
Self-Model Behavioral Cross-Validator

Checks whether Yuki's stated self-beliefs (from identity_core / ai_self_model)
match what can be measured from her actual session behavior.

Discrepancies feed into Enactive Nexus prediction_error as *self-perception
error* — a signal that doesn't exist anywhere else in the current architecture.

Checks performed (all arithmetic, no LLM, no external calls):

  1. CURIOSITY CHECK
     Belief:  "curiosity" trait value ≥ 0.65
     Evidence: ratio of sessions where Yuki asked ≥1 question (from session archive)

  2. WARMTH CHECK
     Belief:  "emotional_warmth" trait value ≥ 0.65
     Evidence: fraction of warm-language tokens in recent responses (recorded in
               session_archive if present, otherwise estimation from emotion state)

  3. CONFIDENCE CHECK
     Belief:  "confidence" trait value ≥ 0.65
     Evidence: average hedging_count recorded in recent sessions
               (hedging words: "maybe", "perhaps", "i think", "probably")

  4. VERBOSITY SELF-KNOWLEDGE CHECK
     Belief:  ai_self_model "verbosity" float
     Evidence: average response word count over last N sessions

Returns a list of discrepancy dicts, each:
  {
    "dimension":  str,
    "believed":   float,
    "observed":   float,
    "gap":        float,   # |believed - observed|
    "direction":  str,     # "over-estimated" | "under-estimated"
    "severity":   str,     # "minor" | "moderate" | "strong"
  }

The caller (DreamCycleDaemon) should:
  - Feed max(gap) as a prediction_error boost to enactive_nexus.micro_update()
  - Log discrepancies into the dream monologue as self-observation
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_HEDGING_RE = re.compile(
    r"\b(?:maybe|perhaps|i think|i feel like|probably|it seems|possibly|i suppose)\b",
    re.IGNORECASE,
)
_QUESTION_RE  = re.compile(r"\?")
_WARM_RE      = re.compile(r"\b(?:understand|appreciate|care|feel|glad|happy|love|support|sorry|warmth)\b", re.IGNORECASE)

_SEVERITY_TABLE = [
    (0.30, "strong"),
    (0.15, "moderate"),
    (0.0,  "minor"),
]


def _severity(gap: float) -> str:
    for threshold, label in _SEVERITY_TABLE:
        if gap >= threshold:
            return label
    return "minor"


class SelfModelValidator:
    """
    Reads identity_core + recent session data (session_archive.json) and
    produces a list of belief-vs-behavior discrepancies.
    """

    def __init__(self, db_path: str = "./persistent_state") -> None:
        self.db_path = db_path

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate(self, identity_core: Dict, ai_self_model: Optional[Dict] = None) -> List[Dict]:
        """
        Run all checks. Returns list of discrepancy dicts (may be empty).
        """
        archive = self._load_archive()
        ai_self_model = ai_self_model or {}
        discrepancies: List[Dict] = []

        checks = [
            self._check_curiosity(identity_core, archive),
            self._check_warmth(identity_core, archive),
            self._check_confidence(identity_core, archive),
            self._check_verbosity_self_knowledge(ai_self_model, archive),
        ]
        for result in checks:
            if result is not None:
                discrepancies.append(result)

        if discrepancies:
            logger.info(
                f"[SELF_VALIDATE] {len(discrepancies)} discrepancies found: "
                + ", ".join(d["dimension"] for d in discrepancies)
            )
        return discrepancies

    def max_gap(self, discrepancies: List[Dict]) -> float:
        """Return the largest gap across all discrepancies (0.0 if none)."""
        if not discrepancies:
            return 0.0
        return max(d["gap"] for d in discrepancies)

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_curiosity(self, identity_core: Dict, archive: List[Dict]) -> Optional[Dict]:
        believed = float(identity_core.get("curiosity", 0.6))
        if not archive:
            return None
        sessions_with_q = sum(1 for s in archive if s.get("question_count", 0) >= 1)
        observed = sessions_with_q / len(archive)
        return self._make(believed, observed, "curiosity", normalize=True)

    def _check_warmth(self, identity_core: Dict, archive: List[Dict]) -> Optional[Dict]:
        believed = float(identity_core.get("emotional_warmth", 0.6))
        if not archive:
            return None
        warm_fracs = []
        for s in archive:
            words = s.get("avg_response_words", 0)
            warm_hits = s.get("warm_token_count", 0)
            if words > 0:
                warm_fracs.append(min(1.0, warm_hits / max(1, words) * 20))
        if not warm_fracs:
            return None
        observed = sum(warm_fracs) / len(warm_fracs)
        return self._make(believed, observed, "emotional_warmth")

    def _check_confidence(self, identity_core: Dict, archive: List[Dict]) -> Optional[Dict]:
        believed = float(identity_core.get("confidence", 0.5))
        if not archive:
            return None
        hedge_fracs = []
        for s in archive:
            words = s.get("avg_response_words", 0)
            hedge_count = s.get("hedge_count", 0)
            if words > 0:
                hedge_fracs.append(min(1.0, hedge_count / max(1, words) * 20))
        if not hedge_fracs:
            return None
        avg_hedge_rate = sum(hedge_fracs) / len(hedge_fracs)
        # high hedging → low observed confidence
        observed = max(0.0, 1.0 - avg_hedge_rate)
        return self._make(believed, observed, "confidence")

    def _check_verbosity_self_knowledge(self, ai_self_model: Dict, archive: List[Dict]) -> Optional[Dict]:
        """Compare self-reported verbosity with measured average response length."""
        verbosity_belief = ai_self_model.get("verbosity")
        if verbosity_belief is None:
            return None
        believed = float(verbosity_belief)
        if not archive:
            return None
        word_counts = [s.get("avg_response_words", 0) for s in archive if s.get("avg_response_words", 0) > 0]
        if not word_counts:
            return None
        avg_words = sum(word_counts) / len(word_counts)
        # Normalize: 0=30 words, 1=300 words
        observed = min(1.0, max(0.0, (avg_words - 30) / 270))
        return self._make(believed, observed, "verbosity_self_knowledge")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make(self, believed: float, observed: float, dimension: str, normalize: bool = False) -> Optional[Dict]:
        if normalize:
            # squeeze both into [0,1] if they aren't already
            believed = min(1.0, max(0.0, believed))
            observed = min(1.0, max(0.0, observed))
        gap = abs(believed - observed)
        if gap < 0.08:
            # not worth reporting
            return None
        direction = "over-estimated" if believed > observed else "under-estimated"
        return {
            "dimension": dimension,
            "believed":  round(believed, 3),
            "observed":  round(observed, 3),
            "gap":       round(gap, 3),
            "direction": direction,
            "severity":  _severity(gap),
        }

    def _load_archive(self) -> List[Dict]:
        """
        Load session_archive.json. Each entry should have keys like:
          question_count, warm_token_count, hedge_count, avg_response_words, timestamp.

        If the archive doesn't have these keys yet (old format), we skip silently.
        Returns empty list if file missing or malformed.
        """
        path = os.path.join(self.db_path, "session_archive.json")
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            # Accept list directly or dict with "sessions" key
            if isinstance(data, list):
                sessions = data
            elif isinstance(data, dict):
                sessions = data.get("sessions", [])
            else:
                return []
            # Return most recent 20
            return sessions[-20:] if len(sessions) > 20 else sessions
        except Exception as exc:
            logger.debug(f"[SELF_VALIDATE] archive load failed: {exc}")
            return []
