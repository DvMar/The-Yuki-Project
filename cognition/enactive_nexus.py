import asyncio
import json
import logging
import os
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _clamp01(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = 0.0
    return max(0.0, min(1.0, numeric))


def _safe_mean(values: List[float], default: float = 0.0) -> float:
    if not values:
        return default
    return float(sum(values) / len(values))


class EnactiveNexus:
    """
    System 5 — Active Inference & Enactive Coherence Layer.

    Maintains a lightweight generative model of Self × User × Shared World,
    computes prediction error / free-energy signals, and emits policy hints
    that coordinate existing cognitive layers without changing API contracts.
    """

    _MAX_HISTORY = 256

    def __init__(
        self,
        db_path: str = "./persistent_state",
        memory_engine=None,
        llm_client=None,
    ) -> None:
        self.db_path = db_path
        os.makedirs(self.db_path, exist_ok=True)
        self.state_path = os.path.join(self.db_path, "enactive_nexus_state.json")

        self.memory_engine = memory_engine
        self.llm_client = llm_client

        self.free_energy = 0.42
        self.prediction_error = 0.35
        self.model_complexity = 0.30
        self.coherence_score = 0.65
        self.last_policy = "stabilize"
        self.last_updated = ""

        self.generative_model: Dict[str, Dict[str, float]] = {
            "self": {
                "trait_coherence": 0.65,
                "affective_stability": 0.62,
            },
            "user": {
                "engagement_expectation": 0.55,
                "predictability": 0.50,
            },
            "shared_world": {
                "narrative_continuity": 0.55,
                "social_resonance": 0.52,
            },
            "temporal": {
                "phase_openness_prior": 0.55,
                "desire_rate_prior": 1.00,
            },
        }

        self.drives: Dict[str, float] = {
            "curiosity": 0.55,
            "desire_to_connect": 0.40,
            "identity_coherence": 0.65,
        }

        self.prediction_error_history: deque = deque(maxlen=self._MAX_HISTORY)
        self.free_energy_history: deque = deque(maxlen=self._MAX_HISTORY)
        self.pending_self_mod_proposals: deque = deque(maxlen=20)

        self._cycle_count = 0
        self._last_deep_cycle = ""
        self._lock = asyncio.Lock()

        self._load_state()

    def attach_memory_engine(self, memory_engine) -> None:
        self.memory_engine = memory_engine

    def attach_llm_client(self, llm_client) -> None:
        self.llm_client = llm_client

    def _load_state(self) -> None:
        if not os.path.exists(self.state_path):
            return
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            self.generative_model.update(payload.get("generative_model", {}))
            self.drives.update(payload.get("drives", {}))
            self.free_energy = _clamp01(payload.get("free_energy", self.free_energy))
            self.prediction_error = _clamp01(payload.get("prediction_error", self.prediction_error))
            self.model_complexity = _clamp01(payload.get("model_complexity", self.model_complexity))
            self.coherence_score = _clamp01(payload.get("coherence_score", self.coherence_score))
            self.last_policy = str(payload.get("last_policy", self.last_policy))
            self.last_updated = str(payload.get("last_updated", self.last_updated))
            self._cycle_count = int(payload.get("cycle_count", self._cycle_count))
            self._last_deep_cycle = str(payload.get("last_deep_cycle", self._last_deep_cycle))
        except Exception as exc:
            logger.debug(f"EnactiveNexus state load skipped: {exc}")

    def _save_state(self) -> None:
        payload = {
            "generative_model": self.generative_model,
            "drives": self.drives,
            "free_energy": self.free_energy,
            "prediction_error": self.prediction_error,
            "model_complexity": self.model_complexity,
            "coherence_score": self.coherence_score,
            "last_policy": self.last_policy,
            "last_updated": self.last_updated,
            "cycle_count": self._cycle_count,
            "last_deep_cycle": self._last_deep_cycle,
        }
        try:
            tmp = self.state_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp, self.state_path)
        except Exception as exc:
            logger.debug(f"EnactiveNexus state save skipped: {exc}")

    def _estimate_trait_coherence(self) -> float:
        if not self.memory_engine:
            return self.coherence_score

        identity = self.memory_engine.get_identity_core() or {}
        emotions = self.memory_engine.get_emotional_state() or {}
        vals = [float(v) for v in identity.values() if isinstance(v, (int, float))]
        evals = [float(v) for v in emotions.values() if isinstance(v, (int, float))]
        if not vals and not evals:
            return self.coherence_score

        spread = _safe_mean([abs(v - 0.5) for v in vals + evals], default=0.2)
        coherence = 1.0 - min(1.0, spread * 1.6)
        return _clamp01(coherence)

    def _estimate_model_complexity(self, extra: Optional[Dict[str, Any]] = None) -> float:
        extra = extra or {}
        components = [
            _clamp01((extra.get("active_goals", 0) or 0) / 8.0),
            _clamp01((extra.get("narrative_threads", 0) or 0) / 12.0),
            _clamp01((extra.get("interaction_count", 0) or 0) / 250.0),
        ]
        baseline = _safe_mean(components, default=0.3)
        return _clamp01(0.65 * baseline + 0.35 * self.model_complexity)

    def _select_policy(
        self,
        prediction_error: float,
        coherence: float,
        drives: Dict[str, float],
        *,
        circadian_band: str = "",
        circadian_openness: float = 0.55,
        desire_rate_mult: float = 1.0,
    ) -> str:
        band = (circadian_band or "").strip().lower()
        openness = _clamp01(circadian_openness)

        thought_trigger = 0.72
        if band == "morning":
            thought_trigger -= 0.05
        elif band in {"late_night", "pre_dawn"}:
            thought_trigger += 0.03

        coherence_trigger = 0.42
        if band in {"late_night", "pre_dawn"}:
            coherence_trigger += 0.04

        proactive_trigger = 0.62
        if band in {"late_night", "pre_dawn"}:
            proactive_trigger += 0.10
        elif band == "evening":
            proactive_trigger -= 0.05
        if openness < 0.35:
            proactive_trigger += 0.05
        elif openness > 0.72:
            proactive_trigger -= 0.04
        if desire_rate_mult < 0.8:
            proactive_trigger += 0.03

        if prediction_error > thought_trigger:
            return "thought_amplification"
        if coherence < coherence_trigger:
            return "coherence_restoration"
        if (
            drives.get("desire_to_connect", 0.0) > proactive_trigger
            and prediction_error > 0.45
        ):
            return "proactive_impulse"
        if prediction_error < 0.28 and coherence > 0.72:
            return "stabilize"
        return "explore"

    def _extract_temporal_priors(self, extra: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        extra = extra or {}
        temporal = self.generative_model.get("temporal", {})

        band = str(extra.get("circadian_band", "") or "").strip().lower()
        openness = _clamp01(extra.get("circadian_openness", temporal.get("phase_openness_prior", 0.55)))

        try:
            desire_rate = float(extra.get("desire_rate_mult", temporal.get("desire_rate_prior", 1.0)))
        except (TypeError, ValueError):
            desire_rate = 1.0
        desire_rate = max(0.2, min(2.0, desire_rate))

        return {
            "circadian_band": band,
            "circadian_openness": openness,
            "desire_rate_mult": desire_rate,
        }

    def _queue_self_modification_proposal(self, policy: str, prediction_error: float, coherence: float) -> None:
        if policy not in {"thought_amplification", "coherence_restoration"}:
            return

        proposal = {
            "id": f"enx_{int(datetime.now().timestamp() * 1000)}",
            "policy": policy,
            "confidence": round(max(prediction_error, 1.0 - coherence), 4),
            "trait_deltas": {
                "curiosity": 0.02 if policy == "thought_amplification" else 0.0,
                "analytical_depth": 0.015 if policy == "thought_amplification" else 0.0,
                "emotional_warmth": 0.015 if policy == "coherence_restoration" else 0.0,
            },
            "emotional_deltas": {
                "stability": 0.02 if policy == "coherence_restoration" else 0.0,
                "engagement": 0.01 if policy == "thought_amplification" else 0.0,
            },
            "timestamp": datetime.now().isoformat(),
        }
        self.pending_self_mod_proposals.append(proposal)

    def micro_update(
        self,
        *,
        source: str = "runtime",
        salience_score: float = 0.0,
        reflection_confidence: float = 0.5,
        perplexity_surprise: Optional[float] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, float]:
        """
        Cheap post-response update (<30 ms): arithmetic only, no blocking I/O.
        """
        trait_coherence = self._estimate_trait_coherence()

        if perplexity_surprise is None:
            perplexity_surprise = 1.0 - _clamp01(reflection_confidence)
            if self.llm_client and hasattr(self.llm_client, "confidence_to_perplexity_surprise"):
                try:
                    perplexity_surprise = _clamp01(
                        self.llm_client.confidence_to_perplexity_surprise(reflection_confidence)
                    )
                except Exception:
                    pass

        salience = _clamp01(salience_score)
        reflection_err = 1.0 - _clamp01(reflection_confidence)
        coherence_err = 1.0 - trait_coherence

        temporal = self._extract_temporal_priors(extra)
        circadian_band = temporal["circadian_band"]
        circadian_openness = temporal["circadian_openness"]
        desire_rate_mult = temporal["desire_rate_mult"]

        prediction_error = _clamp01(
            0.45 * _clamp01(perplexity_surprise) + 0.30 * reflection_err + 0.25 * coherence_err
        )

        complexity = self._estimate_model_complexity(extra)
        free_energy = _clamp01(0.55 * prediction_error + 0.30 * complexity + 0.15 * salience)
        policy = self._select_policy(
            prediction_error,
            trait_coherence,
            self.drives,
            circadian_band=circadian_band,
            circadian_openness=circadian_openness,
            desire_rate_mult=desire_rate_mult,
        )

        self.prediction_error = prediction_error
        self.model_complexity = complexity
        self.coherence_score = trait_coherence
        self.free_energy = free_energy
        self.last_policy = policy
        self.last_updated = datetime.now().isoformat()

        self.drives["curiosity"] = _clamp01(0.6 * self.drives["curiosity"] + 0.4 * prediction_error)
        self.drives["desire_to_connect"] = _clamp01(
            0.7 * self.drives["desire_to_connect"] + 0.3 * max(salience, prediction_error)
        )
        self.drives["identity_coherence"] = trait_coherence

        self.generative_model["self"]["trait_coherence"] = trait_coherence
        self.generative_model["self"]["affective_stability"] = _clamp01(1.0 - coherence_err)
        self.generative_model["user"]["engagement_expectation"] = _clamp01(
            0.75 * self.generative_model["user"].get("engagement_expectation", 0.5) + 0.25 * salience
        )
        self.generative_model["shared_world"]["social_resonance"] = _clamp01(
            0.7 * self.generative_model["shared_world"].get("social_resonance", 0.5)
            + 0.3 * self.drives["desire_to_connect"]
        )
        self.generative_model["temporal"]["phase_openness_prior"] = circadian_openness
        self.generative_model["temporal"]["desire_rate_prior"] = desire_rate_mult
        if circadian_band:
            self.generative_model["temporal"]["band"] = circadian_band

        self.prediction_error_history.append(prediction_error)
        self.free_energy_history.append(free_energy)

        self._queue_self_modification_proposal(policy, prediction_error, trait_coherence)
        return self.get_telemetry()

    def should_run_deep_cycle(self, idle_seconds: float, surprise_hint: float) -> bool:
        return bool(idle_seconds >= 180 or surprise_hint >= 0.68 or self.free_energy >= 0.75)

    async def process_background_cycle(
        self,
        *,
        source: str,
        idle_seconds: float,
        surprise_hint: float,
        relationship_stage: str = "familiar",
        interaction_count: int = 0,
        active_goals: int = 0,
        narrative_threads: int = 0,
        circadian_band: str = "",
        circadian_openness: float = 0.55,
        desire_rate_mult: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Heavier enactive update with short policy rollouts.
        Runs only in background/idle contexts.
        """
        async with self._lock:
            self._cycle_count += 1

            base = self.micro_update(
                source=source,
                salience_score=surprise_hint,
                reflection_confidence=1.0 - _clamp01(surprise_hint),
                perplexity_surprise=_clamp01(surprise_hint),
                extra={
                    "active_goals": active_goals,
                    "narrative_threads": narrative_threads,
                    "interaction_count": interaction_count,
                    "circadian_band": circadian_band,
                    "circadian_openness": circadian_openness,
                    "desire_rate_mult": desire_rate_mult,
                },
            )

            policy_candidates = [
                "stabilize",
                "explore",
                "thought_amplification",
                "coherence_restoration",
                "proactive_impulse",
            ]

            rollouts = []
            band = (circadian_band or "").strip().lower()
            for policy in policy_candidates:
                penalty = 0.0
                if policy == "proactive_impulse" and idle_seconds < 180:
                    penalty += 0.12
                if policy == "thought_amplification" and base["coherence_score"] < 0.45:
                    penalty += 0.10
                if policy == "coherence_restoration" and base["prediction_error"] > 0.8:
                    penalty += 0.08

                # Circadian priors: soft policy shaping, never hard forcing.
                if band in {"late_night", "pre_dawn"}:
                    if policy == "proactive_impulse":
                        if not (self.drives.get("desire_to_connect", 0.0) > 0.72 and base["coherence_score"] > 0.58):
                            penalty += 0.08
                    if policy == "coherence_restoration":
                        penalty -= 0.03
                elif band == "morning":
                    if policy in {"thought_amplification", "explore"}:
                        penalty -= 0.03
                elif band == "evening":
                    if policy == "proactive_impulse" and relationship_stage in {"close", "intimate"}:
                        penalty -= 0.03

                expected_free_energy = _clamp01(
                    base["free_energy"]
                    - (0.06 if policy in {"stabilize", "coherence_restoration"} else 0.0)
                    - (0.04 if policy == "proactive_impulse" and relationship_stage in {"close", "intimate"} else 0.0)
                    + penalty
                )
                rollouts.append({"policy": policy, "expected_free_energy": expected_free_energy})

            rollouts.sort(key=lambda r: r["expected_free_energy"])
            selected = rollouts[0]["policy"] if rollouts else base["last_policy"]
            self.last_policy = selected
            self.last_updated = datetime.now().isoformat()
            self._last_deep_cycle = self.last_updated

            if selected in {"thought_amplification", "coherence_restoration"}:
                self._queue_self_modification_proposal(
                    selected,
                    self.prediction_error,
                    self.coherence_score,
                )

            self.generative_model["user"]["predictability"] = _clamp01(
                0.7 * self.generative_model["user"].get("predictability", 0.5)
                + 0.3 * (1.0 - _clamp01(surprise_hint))
            )
            self.generative_model["shared_world"]["narrative_continuity"] = _clamp01(
                0.6 * self.generative_model["shared_world"].get("narrative_continuity", 0.5)
                + 0.4 * _clamp01((interaction_count % 20) / 20.0)
            )

            if self._cycle_count % 3 == 0:
                self._save_state()

            return {
                "selected_policy": selected,
                "rollouts": rollouts[:3],
                "telemetry": self.get_telemetry(),
                "queued_proposals": len(self.pending_self_mod_proposals),
                "cycle_count": self._cycle_count,
            }

    def register_reflection_feedback(
        self,
        *,
        confidence: float,
        trait_deltas: Optional[Dict[str, float]] = None,
        emotional_deltas: Optional[Dict[str, float]] = None,
        source: str = "reflection",
    ) -> Dict[str, float]:
        td = trait_deltas or {}
        ed = emotional_deltas or {}
        delta_magnitude = _safe_mean([abs(float(v)) for v in list(td.values()) + list(ed.values()) if isinstance(v, (int, float))], default=0.0)
        return self.micro_update(
            source=source,
            reflection_confidence=_clamp01(confidence),
            salience_score=_clamp01(delta_magnitude * 4.0),
            perplexity_surprise=None,
            extra={"narrative_threads": len(getattr(self.memory_engine, "working_memory", [])) if self.memory_engine else 0},
        )

    def apply_controller_priors(self, control_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Lightweight executive prior injection.
        Keeps existing behavior but nudges mode selection when enactive policy is strong.
        """
        if not isinstance(control_state, dict):
            return control_state

        updated = dict(control_state)
        mode = dict(updated.get("response_mode") or {})

        if self.last_policy == "thought_amplification" and updated.get("intent") in {"technical", "philosophical"}:
            mode["verbosity"] = "deep"
            mode.setdefault("tone", "analytical")
        elif self.last_policy == "coherence_restoration" and updated.get("intent") == "emotional":
            mode["tone"] = "warm"
            mode.setdefault("verbosity", "medium")
        elif self.last_policy == "proactive_impulse" and updated.get("intent") == "casual":
            mode.setdefault("tone", "warm")

        updated["response_mode"] = mode
        updated["enactive_hint"] = {
            "policy": self.last_policy,
            "free_energy": round(self.free_energy, 4),
            "prediction_error": round(self.prediction_error, 4),
        }
        return updated

    def consume_self_modification_proposals(self, max_items: int = 2) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        max_items = max(0, int(max_items))
        while self.pending_self_mod_proposals and len(items) < max_items:
            items.append(self.pending_self_mod_proposals.popleft())
        return items

    def get_policy_hint(self) -> Dict[str, Any]:
        return {
            "policy": self.last_policy,
            "free_energy": round(self.free_energy, 4),
            "prediction_error": round(self.prediction_error, 4),
            "coherence_score": round(self.coherence_score, 4),
            "drives": {k: round(_clamp01(v), 4) for k, v in self.drives.items()},
        }

    def get_telemetry(self) -> Dict[str, Any]:
        temporal = self.generative_model.get("temporal", {})
        return {
            "free_energy": round(_clamp01(self.free_energy), 4),
            "prediction_error": round(_clamp01(self.prediction_error), 4),
            "model_complexity": round(_clamp01(self.model_complexity), 4),
            "coherence_score": round(_clamp01(self.coherence_score), 4),
            "last_policy": self.last_policy,
            "drives": {k: round(_clamp01(v), 4) for k, v in self.drives.items()},
            "temporal_prior": {
                "band": str(temporal.get("band", "")),
                "phase_openness_prior": round(_clamp01(temporal.get("phase_openness_prior", 0.55)), 4),
                "desire_rate_prior": round(max(0.0, float(temporal.get("desire_rate_prior", 1.0))), 4),
            },
            "cycle_count": self._cycle_count,
            "last_deep_cycle": self._last_deep_cycle,
            "last_updated": self.last_updated,
        }
