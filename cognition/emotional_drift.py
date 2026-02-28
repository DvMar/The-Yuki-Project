"""
Autonomous Emotional Drift Engine — System 2.5

Applies slow, autonomous random walk to a subset of emotional dimensions
each dream cycle. This gives the organism mood *weather*: it can feel
better or worse today without any external cause.

Principles:
  - Drift is small-amplitude Gaussian (σ ≈ 0.012 per cycle)
  - Drift is slightly biased by Enactive state:
      high free_energy     → negative stability bias
      high curiosity drive → positive intellectual_energy / curiosity bias
      high coherence       → positive stability, positive joy
  - Dimensions NOT drifted: warmth, engagement (these remain fully reactive)
  - All values hard-clamped to [0.05, 0.95] after drift

Results are applied back to the live emotional_state dict (in-place on
the dict returned by memory_engine.get_emotional_state()) and then
persisted via memory_engine.apply_emotion_update().
"""

from __future__ import annotations

import logging
import random
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Dimensions eligible for autonomous drift
_DRIFT_DIMS: Tuple[str, ...] = ("stability", "intellectual_energy", "joy", "calmness", "curiosity")

# Base Gaussian σ per cycle — small but perceptible over many cycles
_BASE_SIGMA: float = 0.012

# Hard floor / ceiling to prevent full collapse or saturation
_FLOOR: float = 0.05
_CEIL:  float = 0.95


def _clamp(v: float) -> float:
    return max(_FLOOR, min(_CEIL, v))


class EmotionalDriftEngine:
    """
    Called once per dream cycle. Computes and returns a delta dict that
    should be merged into the organism's emotional state.

    Stateless — all randomness comes from Python's random module; the
    caller owns persistence.
    """

    def compute_drift(
        self,
        emotional_state: Dict[str, float],
        enactive_state: Optional[Dict[str, float]] = None,
    ) -> Dict[str, float]:
        """
        Compute autonomous drift deltas for eligible dimensions.

        Args:
            emotional_state:  current emotional float dict
            enactive_state:   dict with keys free_energy, coherence_score,
                              drives.curiosity (flat, not nested)

        Returns:
            delta dict — same keys as emotional_state, only drifted dims present.
            Values are *deltas*, not absolute values.
        """
        enactive_state = enactive_state or {}
        fe          = float(enactive_state.get("free_energy",    0.42))
        coherence   = float(enactive_state.get("coherence_score", 0.65))
        cur_drive   = float(enactive_state.get("curiosity_drive", 0.55))

        # Build per-dimension bias from enactive state
        # high free_energy  → tension, erodes stability & joy
        # high coherence    → restores stability, lifts joy
        # high curiosity    → energises intellectual_energy + curiosity dim
        biases: Dict[str, float] = {
            "stability":           0.006 * (coherence - 0.5) - 0.004 * (fe - 0.5),
            "intellectual_energy": 0.005 * (cur_drive - 0.5),
            "joy":                 0.004 * (coherence - 0.5) - 0.003 * (fe - 0.5),
            "calmness":            0.004 * (coherence - fe),
            "curiosity":           0.005 * (cur_drive - 0.5),
        }

        deltas: Dict[str, float] = {}
        for dim in _DRIFT_DIMS:
            current = float(emotional_state.get(dim, 0.5))
            # Gaussian noise + small directional bias
            noise = random.gauss(0.0, _BASE_SIGMA)
            bias  = biases.get(dim, 0.0)
            raw_delta = noise + bias

            # Gentle mean-reversion: nudge toward 0.5 if far from it
            reversion = 0.003 * (0.5 - current)
            raw_delta += reversion

            # Only apply if the result stays within bounds
            new_val = _clamp(current + raw_delta)
            deltas[dim] = round(new_val - current, 6)

        logger.debug(
            f"[DRIFT] deltas={deltas}  (fe={fe:.2f} coh={coherence:.2f} cur={cur_drive:.2f})"
        )
        return deltas

    def apply(
        self,
        emotional_state: Dict[str, float],
        enactive_state: Optional[Dict[str, float]] = None,
    ) -> Dict[str, float]:
        """
        Compute drift and return the *new* emotional state dict (copy, not in-place).
        Caller is responsible for persisting.
        """
        deltas = self.compute_drift(emotional_state, enactive_state)
        updated = dict(emotional_state)
        for dim, delta in deltas.items():
            if dim in updated:
                updated[dim] = _clamp(updated[dim] + delta)
        return updated
