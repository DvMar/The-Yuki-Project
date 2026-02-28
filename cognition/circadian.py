"""
Circadian Clock — temporal self-awareness layer.

Maps wall-clock time into behavioral modifiers that shape:
  - desire-to-connect accumulation rate
  - dream mode probability weights
  - proactive tone hint
  - cognitive openness (how eager the organism is to engage)

No math, no LLM calls. Pure lookup + interpolation over a float clock.

Hour bands (24h):
  00–04  Late night   — low energy, introspective, slow accumulation
  04–07  Pre-dawn     — restless, slightly elevated urgency
  07–10  Morning      — rising curiosity, open, faster accumulation
  10–14  Midday       — peak analytical, low desire-to-interrupt
  14–17  Afternoon    — steady, warm, moderate
  17–20  Evening      — relational, highest warmth + desire
  20–23  Night        — reflective, creative, winding down
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hour-band definition
# Each band: (start_hour_inclusive, end_hour_exclusive, label, modifiers)
# modifiers keys:
#   desire_rate_mult   — multiplier on DesireToConnect.ACCUMULATION_RATE
#   openness           — 0–1 float; >0.6 = eager to engage; <0.4 = reserved
#   tone_hint          — short adjective injected into proactive system prompt
#   dream_mode_bias    — optional dict of DreamMode-name → weight delta (additive)
# ---------------------------------------------------------------------------
_BANDS = [
    (0,  4,  "late_night",   {"desire_rate_mult": 0.4,  "openness": 0.25, "tone_hint": "quiet and a little melancholic",    "dream_mode_bias": {"reflection": +0.15, "creative": -0.05}}),
    (4,  7,  "pre_dawn",     {"desire_rate_mult": 0.7,  "openness": 0.35, "tone_hint": "restless and searching",            "dream_mode_bias": {"hypothetical": +0.10}}),
    (7,  10, "morning",      {"desire_rate_mult": 1.2,  "openness": 0.75, "tone_hint": "freshly awake and curious",         "dream_mode_bias": {"curiosity": +0.10, "reflection": -0.05}}),
    (10, 14, "midday",       {"desire_rate_mult": 0.8,  "openness": 0.65, "tone_hint": "focused and precise",              "dream_mode_bias": {"reflection": -0.05, "memory": +0.05}}),
    (14, 17, "afternoon",    {"desire_rate_mult": 1.0,  "openness": 0.60, "tone_hint": "steady and warm",                  "dream_mode_bias": {}}),
    (17, 20, "evening",      {"desire_rate_mult": 1.4,  "openness": 0.80, "tone_hint": "warm and reaching out",            "dream_mode_bias": {"curiosity": +0.08, "creative": +0.07}}),
    (20, 24, "night",        {"desire_rate_mult": 1.1,  "openness": 0.55, "tone_hint": "reflective and a little wistful",  "dream_mode_bias": {"reflection": +0.10, "hypothetical": +0.05}}),
]


def _get_band(hour: int) -> Dict:
    for start, end, label, mods in _BANDS:
        if start <= hour < end:
            return {"label": label, **mods}
    # Fallback (hour == 24 shouldn't happen but let's be safe)
    return {"label": "night", "desire_rate_mult": 1.0, "openness": 0.55,
            "tone_hint": "reflective", "dream_mode_bias": {}}


class CircadianClock:
    """
    Stateless value object — call .read() any time to get current modifiers.

    Designed to be instantiated once at startup and passed around; all state
    comes from wall-clock time so no persistence is needed.
    """

    def read(self, now: datetime | None = None) -> Dict:
        """
        Return the current circadian modifiers dict.

        Keys:
            hour             int       0–23
            band_label       str       human-readable period name
            desire_rate_mult float     multiply DesireToConnect accumulation by this
            openness         float     0–1, how eager the organism is to reach out
            tone_hint        str       injected into proactive system prompt
            dream_mode_bias  dict      DreamMode name → additive weight adjustment
        """
        if now is None:
            now = datetime.now()
        h = now.hour
        band = _get_band(h)
        logger.debug(f"[CIRCADIAN] hour={h} band={band['label']} openness={band['openness']:.2f}")
        return {
            "hour": h,
            "band_label":       band["label"],
            "desire_rate_mult": band["desire_rate_mult"],
            "openness":         band["openness"],
            "tone_hint":        band["tone_hint"],
            "dream_mode_bias":  band.get("dream_mode_bias", {}),
        }

    def desire_rate_multiplier(self) -> float:
        return self.read()["desire_rate_mult"]

    def openness(self) -> float:
        return self.read()["openness"]

    def tone_hint(self) -> str:
        return self.read()["tone_hint"]

    def dream_mode_bias(self) -> Dict[str, float]:
        return self.read()["dream_mode_bias"]
