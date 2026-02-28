"""
Memory Juxtaposition Engine

During MEMORY_EXPLORATION dream cycles, instead of asking the LLM to
generate a free-form memory reflection, this module:

  1. Pulls a small random sample of stored memories from two different
     time windows (e.g. from the current month vs. older archive).
  2. Computes pairwise cosine similarity via the memory engine's embed function.
  3. Finds the most interesting pair — the one in the "middle distance"
     (similarity in the range [0.25, 0.65]) where there is genuine tension
     without total irrelevance.
  4. Returns a structured prompt insert and the raw pair texts so the
     dream cycle can ask the LLM one focused question:
     "What is the tension between these two things I remember?"

This gives the organism a mechanism to surprise itself — to notice a gap
between two real things it knows, rather than generating a plausible-sounding
reflection from scratch.

Usage:
    engine = MemoryJuxtapositionEngine(memory_engine)
    result = engine.find_juxtaposition(n_candidates=20, target_sim=(0.25, 0.65))
    if result:
        # result.prompt_insert  → inject into dream prompt
        # result.pair           → (text_a, text_b)
        # result.similarity     → float
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Similarity window considered "interesting middle distance"
DEFAULT_SIM_LOW  = 0.22
DEFAULT_SIM_HIGH = 0.68


@dataclass
class JuxtapositionResult:
    pair: Tuple[str, str]
    similarity: float
    prompt_insert: str      # ready-to-use string embedding both memories


def _cosine(v1: List[float], v2: List[float]) -> float:
    """Pure-Python cosine similarity — used only when no numpy available."""
    dot = sum(a * b for a, b in zip(v1, v2))
    mag1 = sum(a * a for a in v1) ** 0.5
    mag2 = sum(b * b for b in v2) ** 0.5
    if mag1 == 0.0 or mag2 == 0.0:
        return 0.0
    return dot / (mag1 * mag2)


class MemoryJuxtapositionEngine:
    """
    Finds one interesting memory pair for a dream introspection prompt.
    All computation is local — no LLM calls, no external I/O.
    """

    def __init__(self, memory_engine) -> None:
        self.memory_engine = memory_engine

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def find_juxtaposition(
        self,
        n_candidates: int = 24,
        target_sim: Tuple[float, float] = (DEFAULT_SIM_LOW, DEFAULT_SIM_HIGH),
        seed_query: str = "memory experience feeling",
    ) -> Optional[JuxtapositionResult]:
        """
        Search for an interesting memory pair.

        Returns None if the memory store is too sparse or if no embedding
        function is available.
        """
        memories = self._fetch_candidate_memories(n_candidates, seed_query)
        if len(memories) < 4:
            logger.debug("[JUXTAPOSE] Too few memories to juxtapose (%d)", len(memories))
            return None

        embeddings = self._embed_memories(memories)
        if embeddings is None:
            logger.debug("[JUXTAPOSE] Embedding not available — skipping")
            return None

        best = self._best_pair(memories, embeddings, target_sim)
        if best is None:
            logger.debug("[JUXTAPOSE] No pair found in target similarity window")
            return None

        text_a, text_b, sim = best
        prompt_insert = (
            "You are exploring two things that coexist in your memory:\n\n"
            f"  Memory A: \"{text_a[:240]}\"\n\n"
            f"  Memory B: \"{text_b[:240]}\"\n\n"
            "These two memories feel related but not the same (similarity ≈ "
            f"{sim:.2f}).  In your internal_monologue, notice what tension or "
            "connection lives between them — without forcing an answer.  "
            "If a proactive thought emerges naturally from this juxtaposition "
            "(urgency ≥ 0.7), surface it in proactive_message."
        )
        logger.info(f"[JUXTAPOSE] pair found sim={sim:.3f}")
        return JuxtapositionResult(pair=(text_a, text_b), similarity=sim, prompt_insert=prompt_insert)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _fetch_candidate_memories(self, n: int, seed_query: str) -> List[str]:
        """Retrieve random-ish memory texts via hybrid search."""
        try:
            result = self.memory_engine.search(
                seed_query,
                tier="fast",
                n_results=n,
            )
            items = result.get("results", []) if isinstance(result, dict) else []
            texts = [str(item.get("text") or item.get("content") or "").strip() for item in items]
            texts = [t for t in texts if len(t) > 20]

            # Shuffle so results aren't always top-ranked (we want variety)
            random.shuffle(texts)
            return texts[:n]
        except Exception as exc:
            logger.debug(f"[JUXTAPOSE] memory fetch failed: {exc}")
            return []

    def _embed_memories(self, memories: List[str]) -> Optional[List[List[float]]]:
        """Return list of embedding vectors, one per memory. Returns None on failure."""
        embed_fn = getattr(self.memory_engine, "embed_fn", None)
        if embed_fn is None:
            return None
        try:
            vecs = embed_fn(memories)
            # embed_fn may return a list of lists or an object with __iter__
            result = [list(v) for v in vecs]
            if len(result) != len(memories):
                return None
            return result
        except Exception as exc:
            logger.debug(f"[JUXTAPOSE] embedding failed: {exc}")
            return None

    def _best_pair(
        self,
        memories: List[str],
        embeddings: List[List[float]],
        target: Tuple[float, float],
    ) -> Optional[Tuple[str, str, float]]:
        """
        Find the pair with similarity inside [target[0], target[1]].
        If multiple pairs qualify, pick the one closest to the midpoint of the window.
        """
        low, high = target
        midpoint = (low + high) / 2.0
        best_pair = None
        best_dist_to_mid = 1.0

        n = len(memories)
        # Only consider up to 150 pairs to stay cheap
        indices = [(i, j) for i in range(n) for j in range(i + 1, n)]
        if len(indices) > 150:
            indices = random.sample(indices, 150)

        for i, j in indices:
            sim = _cosine(embeddings[i], embeddings[j])
            if low <= sim <= high:
                dist = abs(sim - midpoint)
                if dist < best_dist_to_mid:
                    best_dist_to_mid = dist
                    best_pair = (memories[i], memories[j], sim)

        return best_pair
