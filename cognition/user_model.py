"""
User Model — belief-accumulating model of the person talking to Yuki.

Builds a lightweight structured picture of the user from what they say,
and detects genuine relational surprise when new input contradicts an
existing belief. Surprise feeds back into S5 (Enactive Nexus) as a
qualitatively different signal than perplexity-surprise.

Architecture:
  - topic_interests: {topic: score 0–1}  (EWM-smoothed keyword hits)
  - beliefs:         [{claim, confidence, last_seen, source_text}]
                     max 30 entries, evicted by lowest confidence
  - contradiction detection: simple claim negation + antonym check
  - persist: JSON file in persistent_state/

This is intentionally non-LLM.  All extraction is pattern-based.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

MAX_BELIEFS = 30
MAX_INTERESTS = 50

# Patterns that reveal user beliefs/claims about themselves
_CLAIM_PATTERNS: List[Tuple[str, float]] = [
    (r"\b(?:i am|i'm)\s+([^.!?\n]{4,60})",                        0.85),
    (r"\b(?:i believe|i think|i feel that|i know)\s+([^.!?\n]{4,60})", 0.70),
    (r"\b(?:i love|i hate|i dislike|i enjoy|i prefer)\s+([^.!?\n]{4,60})", 0.78),
    (r"\b(?:i always|i never|i usually|i often)\s+([^.!?\n]{4,60})", 0.72),
    (r"\b(?:my favourite|my favorite|my job|my work|my family)\s+(?:is|are)?\s*([^.!?\n]{4,60})", 0.80),
]

# Antonym pairs used for contradiction detection (simple, not exhaustive)
_ANTONYMS: List[Tuple[str, str]] = [
    ("love", "hate"), ("like", "dislike"), ("enjoy", "hate"),
    ("always", "never"), ("agree", "disagree"), ("believe", "doubt"),
    ("trust", "distrust"), ("happy", "sad"), ("optimist", "pessimist"),
    ("introvert", "extrovert"), ("morning person", "night person"),
]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _extract_topics(text: str) -> List[str]:
    """Very lightweight topic extraction — nouns / noun-like tokens after prepositions."""
    tokens = re.findall(r"\b(?:about|regarding|on|into|with)\s+(\w+(?:\s+\w+)?)", text.lower())
    # Also grab any capitalized multi-word that isn't a sentence start
    tokens += re.findall(r"(?<=[a-z] )([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", text)
    return [t.strip().lower() for t in tokens if len(t.strip()) > 2]


def _contradicts(claim_a: str, claim_b: str) -> bool:
    """Return True if claim_b looks like it directly contradicts claim_a."""
    a, b = _normalize(claim_a), _normalize(claim_b)
    for word1, word2 in _ANTONYMS:
        if word1 in a and word2 in b:
            return True
        if word2 in a and word1 in b:
            return True
    # Negation flip: "I am X" vs "I am not X" (or vice versa)
    if re.search(r"\bnot\b|\bno\b", b) and not re.search(r"\bnot\b|\bno\b", a):
        # strip negation from b, see if the remainder is close to a
        stripped = re.sub(r"\b(?:not|no)\b\s*", "", b)
        if stripped and (stripped in a or a in stripped):
            return True
    return False


class UserModel:
    """
    Tracks topic interests and stated beliefs of the user.
    Detects when new input contradicts stored beliefs (relational surprise).
    """

    def __init__(self, db_path: str = "./persistent_state") -> None:
        self.db_path = db_path
        self._path = os.path.join(db_path, "user_model.json")
        self.topic_interests: Dict[str, float] = {}  # topic → smoothed score
        self.beliefs: List[Dict] = []                 # list of belief dicts
        self._last_surprise_score: float = 0.0        # exposed to telemetry
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self.topic_interests = data.get("topic_interests", {})
            self.beliefs = data.get("beliefs", [])
        except Exception as exc:
            logger.debug(f"[USER_MODEL] load failed: {exc}")

    def _save(self) -> None:
        try:
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"topic_interests": self.topic_interests, "beliefs": self.beliefs}, fh, indent=2)
            os.replace(tmp, self._path)
        except Exception as exc:
            logger.debug(f"[USER_MODEL] save failed: {exc}")

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def ingest(self, user_message: str) -> Dict:
        """
        Process one user message. Updates interests and beliefs.

        Returns:
            {
                "surprise_score":  float 0–1,   (0 = nothing new / contradicting)
                "new_beliefs":     List[str],    newly stored claims
                "contradictions":  List[str],    existing beliefs that were challenged
                "topics_seen":     List[str],
            }
        """
        text = user_message.strip()
        new_beliefs: List[str] = []
        contradictions: List[str] = []

        # --- topic interests (EWM update) ---
        topics = _extract_topics(text)
        for topic in topics:
            old = self.topic_interests.get(topic, 0.0)
            self.topic_interests[topic] = round(old * 0.85 + 0.15, 4)
        # gentle decay on all existing topics
        for k in list(self.topic_interests.keys()):
            self.topic_interests[k] = round(self.topic_interests[k] * 0.98, 4)
            if self.topic_interests[k] < 0.02:
                del self.topic_interests[k]
        # cap size
        if len(self.topic_interests) > MAX_INTERESTS:
            trimmed = sorted(self.topic_interests.items(), key=lambda x: x[1], reverse=True)[:MAX_INTERESTS]
            self.topic_interests = dict(trimmed)

        # --- belief extraction ---
        for pattern, base_conf in _CLAIM_PATTERNS:
            for m in re.finditer(pattern, text, re.IGNORECASE):
                claim = _normalize(m.group(1) if m.lastindex else m.group(0))
                if len(claim) < 5:
                    continue

                # check for contradiction with existing beliefs
                for existing in self.beliefs:
                    if _contradicts(existing["claim"], claim):
                        contradictions.append(existing["claim"])
                        existing["confidence"] *= 0.65   # weaken contradicted belief
                        logger.info(f"[USER_MODEL] Contradiction detected: '{claim}' vs '{existing['claim']}'")

                # check if already stored (approximate duplicate)
                already = any(
                    existing["claim"] == claim or claim in existing["claim"] or existing["claim"] in claim
                    for existing in self.beliefs
                )
                if not already:
                    new_beliefs.append(claim)
                    self.beliefs.append({
                        "claim":       claim,
                        "confidence":  base_conf,
                        "last_seen":   datetime.now().isoformat(),
                        "source_text": text[:120],
                    })
                    # enforce cap
                    if len(self.beliefs) > MAX_BELIEFS:
                        self.beliefs.sort(key=lambda b: b["confidence"])
                        self.beliefs.pop(0)

        # --- surprise score ---
        surprise = 0.0
        if contradictions:
            surprise = min(1.0, 0.55 + 0.15 * len(contradictions))
        elif new_beliefs:
            surprise = min(0.50, 0.12 * len(new_beliefs))

        self._save()
        self._last_surprise_score = round(surprise, 4)
        return {
            "surprise_score": round(surprise, 4),
            "new_beliefs":    new_beliefs,
            "contradictions": contradictions,
            "topics_seen":    topics,
        }

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_top_interests(self, n: int = 5) -> List[Tuple[str, float]]:
        return sorted(self.topic_interests.items(), key=lambda x: x[1], reverse=True)[:n]

    def get_high_confidence_beliefs(self, threshold: float = 0.70) -> List[Dict]:
        return [b for b in self.beliefs if b["confidence"] >= threshold]

    def get_state(self) -> Dict:
        return {
            "total_beliefs":       len(self.beliefs),
            "top_interests":       self.get_top_interests(5),
            "high_conf_beliefs":   len(self.get_high_confidence_beliefs()),
        }
