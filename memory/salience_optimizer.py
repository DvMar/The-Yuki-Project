"""
Salience Optimizer — adaptive weight tuning for SalienceGate.

Learns which scoring factors best predict whether a stored memory
will actually be useful when retrieved later. Uses a lightweight
online RL signal (reward/penalty per-factor) with JSON persistence.

Integration:
    optimizer = SalienceOptimizer(db_path="./persistent_state")
    gate = SalienceGate(embedding_model=..., optimizer=optimizer)

    # After a memory is retrieved and judged useful/not:
    optimizer.record_outcome(factors=factors_dict, was_useful=True)

Weights — mirror the multipliers in SalienceGate.compute_salience_score():
    trivial_penalty  : penalty applied to trivial keyword match score
    salient_boost    : boost applied to salient keyword match score
    length_weight    : contribution of length heuristic
    statement_weight : contribution of statement-type heuristic
    context_weight   : contribution of embedding context relevance
    novelty_weight   : contribution of novelty vs recent history
"""

import json
import logging
import os
import time
from collections import deque
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

# ── defaults match hardcoded values in SalienceGate ──────────────────────────
_DEFAULT_WEIGHTS: Dict[str, float] = {
    "trivial_penalty":  0.40,
    "salient_boost":    0.50,
    "length_weight":    0.20,
    "statement_weight": 0.15,
    "context_weight":   0.20,
    "novelty_weight":   0.15,
}

# Factors that must never drop below this floor (prevent degenerate collapse)
_WEIGHT_FLOOR: Dict[str, float] = {
    "trivial_penalty":  0.10,
    "salient_boost":    0.10,
    "length_weight":    0.05,
    "statement_weight": 0.05,
    "context_weight":   0.05,
    "novelty_weight":   0.05,
}

# Factors must never exceed this ceiling (prevent unbounded weight drift).
# Weights are multipliers on 0-1 normalised factor values; capping at 2.0
# means any single factor can contribute at most 2.0 to the composite score,
# which is already well beyond the physical max of the factor itself.
_WEIGHT_CEILING: Dict[str, float] = {
    "trivial_penalty":  2.0,
    "salient_boost":    2.0,
    "length_weight":    2.0,
    "statement_weight": 2.0,
    "context_weight":   2.0,
    "novelty_weight":   2.0,
}

# How sensitive each weight is to reward signals (higher = learns faster)
_ADAPT_RATE: Dict[str, float] = {
    "trivial_penalty":  0.8,
    "salient_boost":    1.0,
    "length_weight":    0.5,
    "statement_weight": 0.4,
    "context_weight":   0.9,
    "novelty_weight":   0.7,
}


class SalienceOptimizer:
    """
    Online adaptive optimizer for SalienceGate scoring weights.

    Each time a stored memory is later retrieved (useful) or skipped
    as irrelevant, the weight of whichever factors drove the save/skip
    decision is nudged up or down via a small gradient step.
    """

    def __init__(
        self,
        db_path: str = "./persistent_state",
        learning_rate: float = 0.005,
        history_window: int = 500,
    ):
        self.db_path = db_path
        self.learning_rate = learning_rate
        self._weights_path = os.path.join(db_path, "salience_weights.json")

        # Rolling window of recent outcomes for stats
        self._history: deque = deque(maxlen=history_window)

        # Running counters
        self._total_saves = 0
        self._total_useful = 0
        self._total_noise = 0
        self._last_persist = 0.0

        # Load persisted weights or fall back to defaults
        self.weights: Dict[str, float] = self._load_weights()

        # Seed the file immediately if it doesn't exist yet so it's available
        # from the first session, not only after the first record_outcome() call.
        if not os.path.isfile(self._weights_path):
            self._persist(force=True)

        logger.info(
            "SalienceOptimizer ready | weights=%s",
            {k: round(v, 3) for k, v in self.weights.items()},
        )

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load_weights(self) -> Dict[str, float]:
        """Load weights from disk, filling missing keys from defaults."""
        if os.path.isfile(self._weights_path):
            try:
                with open(self._weights_path, "r", encoding="utf-8") as fh:
                    persisted = json.load(fh).get("weights", {})
                weights = dict(_DEFAULT_WEIGHTS)
                weights.update({k: float(v) for k, v in persisted.items() if k in weights})
                return weights
            except Exception as exc:
                logger.warning("Could not load salience weights (%s); using defaults", exc)
        return dict(_DEFAULT_WEIGHTS)

    def _persist(self, force: bool = False) -> None:
        """Save weights to disk at most once every 60 s (or on force)."""
        now = time.monotonic()
        if not force and (now - self._last_persist) < 60.0:
            return
        try:
            os.makedirs(self.db_path, exist_ok=True)
            payload = {
                "weights": {k: round(v, 6) for k, v in self.weights.items()},
                "stats": self._current_stats(),
            }
            with open(self._weights_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
            self._last_persist = now
        except Exception as exc:
            logger.warning("Could not persist salience weights: %s", exc)

    # ── Public API ────────────────────────────────────────────────────────────

    def get_weights(self) -> Dict[str, float]:
        """Return a copy of current weights for use by SalienceGate."""
        return dict(self.weights)

    def record_outcome(
        self,
        factors: Dict[str, float],
        was_useful: bool,
        weight: float = 1.0,
    ) -> None:
        """
        Nudge weights after observing whether a stored memory was useful.

        Args:
            factors   : The factor dict returned by SalienceGate.compute_salience_score()
            was_useful: True → memory aided a response; False → noise/irrelevant
            weight    : Importance of this signal (default 1.0; use >1 for
                        high-confidence signals like explicit user feedback)
        """
        self._total_saves += 1
        if was_useful:
            self._total_useful += 1
        else:
            self._total_noise += 1

        reward = 1.0 if was_useful else -1.0
        effective_lr = self.learning_rate * max(0.1, min(2.0, float(weight)))

        # Map gate factor keys → optimizer weight keys
        factor_map: Dict[str, Tuple[str, float]] = {
            # gate key          : (optimizer weight key, sign)
            "trivial_match":    ("trivial_penalty",  -1.0),  # higher trivial → bad
            "salient_match":    ("salient_boost",     1.0),  # higher salient → good
            "length_score":     ("length_weight",     1.0),
            "statement_type_score": ("statement_weight", 1.0),
            "context_relevance":  ("context_weight",  1.0),
            "novelty_score":    ("novelty_weight",    1.0),
        }

        for factor_key, (weight_key, sign) in factor_map.items():
            factor_val = float(factors.get(factor_key, 0.0))
            if abs(factor_val) < 1e-6:
                continue
            adapt = _ADAPT_RATE[weight_key]
            delta = effective_lr * reward * sign * abs(factor_val) * adapt
            self.weights[weight_key] = max(
                _WEIGHT_FLOOR[weight_key],
                min(_WEIGHT_CEILING[weight_key], self.weights[weight_key] + delta),
            )

        self._history.append(
            {"useful": was_useful, "factors": {k: round(v, 3) for k, v in factors.items()}}
        )
        self._persist()

    def batch_adapt(self, outcomes: List[Dict[str, Any]]) -> None:
        """
        Apply multiple outcomes at once (e.g. from a periodic evaluation pass).

        Each item: {"factors": dict, "was_useful": bool, "weight": float (optional)}
        """
        for item in outcomes:
            self.record_outcome(
                factors=item.get("factors", {}),
                was_useful=bool(item.get("was_useful", False)),
                weight=float(item.get("weight", 1.0)),
            )
        self._persist(force=True)

    def adapt_threshold(self, gate, target_precision: float = 0.70) -> None:
        """
        Adjust SalienceGate threshold so that recent precision approaches target.

        Precision = useful / (useful + noise) over the last 100 outcomes.
        Called periodically by long-running background tasks.

        Args:
            gate            : SalienceGate instance to adjust
            target_precision: Desired useful-memory ratio (0.0–1.0)
        """
        recent = list(self._history)[-100:]
        if len(recent) < 20:
            return  # Not enough data yet

        n_useful = sum(1 for r in recent if r["useful"])
        precision = n_useful / len(recent)
        error = precision - target_precision  # positive → too permissive

        # Nudge threshold proportionally to error
        delta = error * 0.05
        new_threshold = max(-0.5, min(0.5, gate.threshold + delta))
        if abs(new_threshold - gate.threshold) > 0.005:
            gate.set_threshold(new_threshold)
            logger.debug(
                "SalienceOptimizer: threshold %.3f → %.3f (precision=%.2f, target=%.2f)",
                gate.threshold, new_threshold, precision, target_precision,
            )

    def reset_to_defaults(self) -> None:
        """Reset weights to built-in defaults and persist."""
        self.weights = dict(_DEFAULT_WEIGHTS)
        self._persist(force=True)
        logger.info("SalienceOptimizer: weights reset to defaults")

    def get_stats(self) -> Dict[str, Any]:
        """Return current weights + runtime statistics for observability."""
        return self._current_stats()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _current_stats(self) -> Dict[str, Any]:
        total = self._total_useful + self._total_noise
        precision = self._total_useful / total if total else 0.0
        recent = list(self._history)[-100:]
        recent_total = len(recent)
        recent_useful = sum(1 for r in recent if r["useful"])
        return {
            "weights": {k: round(v, 4) for k, v in self.weights.items()},
            "total_saves": self._total_saves,
            "total_useful": self._total_useful,
            "total_noise": self._total_noise,
            "all_time_precision": round(precision, 4),
            "recent_precision": round(recent_useful / recent_total, 4) if recent_total else 0.0,
            "history_window": recent_total,
        }
