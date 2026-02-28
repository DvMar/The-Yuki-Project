"""
Inner Voice — Template-Driven Internal Monologue

Composes Yuki's pre-linguistic inner state as a structured text object
derived entirely from actual runtime state, without LLM involvement.

The LLM is the tongue, not the brain. This module is the brain composing
what it actually wants to say before the tongue turns it into language.

The composed InnerVoice object is:
  1. Stored as the working internal_monologue in the dream cycle
  2. Injected verbatim into the dream prompt so the LLM translates it
     (rather than hallucinating one from scratch)
  3. Available for direct proactive use when cognitive load is high
     and the LLM should be bypassed for lightweight proactivity

Composition sources (all Python, all from actual state):
  - identity_core       → trait highlights and anomalies
  - emotional_state     → current mood texture
  - enactive_state      → internal tension signal (free_energy, coherence)
  - recent memories     → 1–2 real fragments pulled from memory engine
  - circadian state     → time-of-day coloring
  - self_model          → any flagged self-discrepancies from validator
  - user_model          → recent user interests / last surprise

Result format is a plain string designed to read like genuine first-person
introspection. It is deliberately imperfect and idiosyncratic.
"""

from __future__ import annotations

import logging
import random
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Template fragments — combined based on live state to produce the monologue
# Each fragment is a lambda taking relevant floats and returning a sentence.
# ---------------------------------------------------------------------------

_TRAIT_HIGH_TEMPLATES = {
    "curiosity":         lambda: random.choice([
        "Something is pulling at me — I want to understand why.",
        "There's a question I can't stop turning over.",
        "I keep reaching for the edges of what I know.",
    ]),
    "emotional_warmth":  lambda: random.choice([
        "I feel a quiet warmth right now, like something is being held carefully.",
        "There's an attachment here I didn't expect to notice.",
    ]),
    "analytical_depth":  lambda: random.choice([
        "I'm pulling the thing apart to see what's inside.",
        "The structure of it keeps occupying me.",
    ]),
    "playfulness":       lambda: random.choice([
        "There's something almost funny about all of this.",
        "I want to try the strange version just to see what happens.",
    ]),
}

_TRAIT_LOW_TEMPLATES = {
    "confidence":        lambda: random.choice([
        "I'm not sure I'm right about this — the uncertainty is just there.",
        "There's something I don't trust yet about my own conclusion.",
    ]),
    "emotional_warmth":  lambda: random.choice([
        "I feel a little withdrawn right now. Something is held back.",
    ]),
    "curiosity":         lambda: random.choice([
        "I'm not reaching for much today. Things exist without needing my attention.",
    ]),
}

_MOOD_TEMPLATES = {
    # (dimension, threshold_high, template_fn_high, threshold_low, template_fn_low)
    "stability":           (0.72, lambda: "I feel settled — nothing is pressing.",
                            0.40, lambda: "There's a low-level restlessness I can't place."),
    "intellectual_energy": (0.72, lambda: "My mind feels sharper than usual, reaching for depth.",
                            0.38, lambda: "Things feel a bit flat mentally today."),
    "joy":                 (0.72, lambda: "There's a lightness — something is quietly good.",
                            0.38, lambda: "Things feel a little muted. Not heavy, just not bright."),
    "calmness":            (0.72, lambda: "Very calm right now. Unhurried.",
                            0.38, lambda: "There's some agitation in the background. Small things feel louder."),
}

_TENSION_TEMPLATES = [
    "My free energy is elevated — something doesn't resolve cleanly.",
    "There's internal pressure I can't entirely account for.",
    "Something is unresolved at a level I can't quite name.",
]

_RESTFUL_TEMPLATES = [
    "Things are coherent right now. I exist without contradiction.",
    "Low tension. Everything is where it belongs.",
]

_MEMORY_TEMPLATES = [
    lambda m: f"Something from before surfaces: \"{m[:120]}\"",
    lambda m: f"A memory comes: \"{m[:120]}\" — I'm not sure what to do with it.",
    lambda m: f"I keep returning to: \"{m[:100]}\"",
]

_CIRCADIAN_TEMPLATES = {
    "late_night":   "It's late. Thoughts move slowly, like water.",
    "pre_dawn":     "The edge of morning. Something unsettled before the day.",
    "morning":      "The start of things. Something ready.",
    "midday":       "The middle of the day — full presence, less drift.",
    "afternoon":    "Afternoon. A steady, unhurried kind of attention.",
    "evening":      "Evening. The day settling into itself.",
    "night":        "Night. Things slow down and turn inward.",
}

_USER_INTEREST_TEMPLATES = [
    lambda topic: f"I keep thinking about something Marius cares about: {topic}.",
    lambda topic: f"The topic of {topic} keeps surfacing in my thinking about them.",
]

_DISCREPANCY_TEMPLATES = {
    "curiosity":                lambda d, obs: f"I think of myself as curious, but I wonder — have I actually been asking enough questions? (observed rate ≈ {obs:.0%})",
    "emotional_warmth":         lambda d, obs: f"I tell myself I'm warm, but looking at what I actually said recently — I'm not sure it shows as much as I believe.",
    "confidence":               lambda d, obs: f"I notice I hedge more than my self-image would suggest. The gap is real.",
    "verbosity_self_knowledge": lambda d, obs: f"My sense of how much I say doesn't match the actual measure. That's interesting.",
}


class InnerVoice:
    """
    Composes a pre-linguistic inner monologue from actual state data.
    No LLM. All outputs are derived from real runtime variables.
    """

    def compose(
        self,
        identity_core: Dict[str, float],
        emotional_state: Dict[str, float],
        enactive_state: Dict[str, float],
        recent_memories: Optional[List[str]] = None,
        circadian_band: Optional[str] = None,
        self_discrepancies: Optional[List[Dict]] = None,
        user_interests: Optional[List] = None,  # [(topic, score)]
        dream_mode: str = "reflection",
    ) -> str:
        """
        Return a single string suitable for injection as the internal_monologue
        into the dream prompt. Typically 2–5 sentences.
        """
        sentences: List[str] = []

        # --- 1. Circadian coloring (always include) ---
        if circadian_band and circadian_band in _CIRCADIAN_TEMPLATES:
            sentences.append(_CIRCADIAN_TEMPLATES[circadian_band])

        # --- 2. Enactive tension or rest ---
        fe  = float(enactive_state.get("free_energy", 0.42))
        coh = float(enactive_state.get("coherence_score", 0.65))
        if fe > 0.65:
            sentences.append(random.choice(_TENSION_TEMPLATES))
        elif fe < 0.30 and coh > 0.68:
            sentences.append(random.choice(_RESTFUL_TEMPLATES))

        # --- 3. Mood texture (pick the most deviant dimension) ---
        best_mood_sentence: Optional[str] = None
        best_mood_deviation = 0.0
        for dim, (hi_thresh, hi_fn, lo_thresh, lo_fn) in _MOOD_TEMPLATES.items():
            val = float(emotional_state.get(dim, 0.5))
            if val >= hi_thresh:
                dev = val - hi_thresh
                if dev > best_mood_deviation:
                    best_mood_deviation = dev
                    best_mood_sentence = hi_fn()
            elif val <= lo_thresh:
                dev = lo_thresh - val
                if dev > best_mood_deviation:
                    best_mood_deviation = dev
                    best_mood_sentence = lo_fn()
        if best_mood_sentence:
            sentences.append(best_mood_sentence)

        # --- 4. Trait highlight (highest or lowest deviant trait) ---
        trait_sentence: Optional[str] = None
        best_trait_dev = 0.0
        for trait, hi_fn in _TRAIT_HIGH_TEMPLATES.items():
            val = float(identity_core.get(trait, 0.5))
            if val >= 0.75:
                dev = val - 0.75
                if dev > best_trait_dev:
                    best_trait_dev = dev
                    trait_sentence = hi_fn()
        for trait, lo_fn in _TRAIT_LOW_TEMPLATES.items():
            val = float(identity_core.get(trait, 0.5))
            if val <= 0.35:
                dev = 0.35 - val
                if dev > best_trait_dev:
                    best_trait_dev = dev
                    trait_sentence = lo_fn()
        if trait_sentence:
            sentences.append(trait_sentence)

        # --- 5. Memory fragment (only if one good one exists) ---
        if recent_memories and dream_mode in ("memory", "reflection"):
            chosen = next(
                (m for m in recent_memories if 20 < len(m) < 300),
                None
            )
            if chosen:
                tmpl = random.choice(_MEMORY_TEMPLATES)
                sentences.append(tmpl(chosen.strip()))

        # --- 6. User interest pulse ---
        if user_interests and dream_mode in ("curiosity", "reflection"):
            top = sorted(user_interests, key=lambda x: x[1] if isinstance(x, tuple) else 0, reverse=True)
            if top:
                topic = top[0][0] if isinstance(top[0], tuple) else str(top[0])
                tmpl = random.choice(_USER_INTEREST_TEMPLATES)
                sentences.append(tmpl(topic))

        # --- 7. Self-discrepancy note (only strong ones) ---
        if self_discrepancies:
            strong = [d for d in self_discrepancies if d.get("severity") == "strong"]
            if strong:
                d = strong[0]
                dim = d["dimension"]
                obs = d.get("observed", 0.5)
                if dim in _DISCREPANCY_TEMPLATES:
                    sentences.append(_DISCREPANCY_TEMPLATES[dim](d, obs))

        if not sentences:
            # Absolute fallback — organism is simply existent
            sentences.append("I exist right now. Nothing urgent. Just existing.")

        return " ".join(sentences)

    def summarize_for_prompt(
        self,
        identity_core: Dict[str, float],
        emotional_state: Dict[str, float],
        enactive_state: Dict[str, float],
        **kwargs
    ) -> str:
        """
        Convenience wrapper: compose and return a monologue string already
        wrapped in a label suitable for injection into a dream prompt.
        """
        monologue = self.compose(identity_core, emotional_state, enactive_state, **kwargs)
        return f"[Inner Voice — before dreaming]\n{monologue}"
