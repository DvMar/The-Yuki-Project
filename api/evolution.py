"""
Background evolution loop — runs after every user interaction to update
memory, run reflections, meta-evaluations, and autopoietic cycles.

All state is accessed through api.context (shared singleton instances).
"""
import asyncio
import json
import logging
import time
from datetime import datetime, timedelta

import api.context as ctx
from utils.time_utils import get_local_time
from utils.logging import log_structured

logger = logging.getLogger(__name__)


_BAND_OPENNESS_PRIOR = {
    "late_night": 0.25,
    "pre_dawn": 0.35,
    "morning": 0.75,
    "midday": 0.65,
    "afternoon": 0.60,
    "evening": 0.80,
    "night": 0.55,
}


def _parse_iso_timestamp(value) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _clamp01(value: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.0


def _derive_metabolic_reflection_context(max_signatures: int = 160) -> dict:
    """Build causal context from persisted state signatures for reflection.

    The goal is not telemetry verbosity; it is historical self-interpretation:
    identify metabolically plausible links between earlier state and current tone.
    """
    store = getattr(ctx, "state_signature_store", None)
    if store is None:
        return {
            "available": False,
            "causal_links": [],
            "narrative_hint": "",
            "signature_trace": [],
        }

    raw_entries = store.get_recent(limit=max_signatures)
    if not raw_entries:
        return {
            "available": False,
            "causal_links": [],
            "narrative_hint": "",
            "signature_trace": [],
        }

    entries = []
    for item in raw_entries:
        if not isinstance(item, dict):
            continue
        ts = _parse_iso_timestamp(item.get("timestamp"))
        if ts is None:
            continue
        band = str(item.get("circadian_band") or "")
        load = float(item.get("cognitive_load", 0.0) or 0.0)
        openness = float(item.get("circadian_openness", _BAND_OPENNESS_PRIOR.get(band, 0.55)) or 0.55)
        entries.append({
            "timestamp": ts,
            "source": str(item.get("source") or ""),
            "circadian_band": band,
            "cognitive_load": _clamp01(load),
            "circadian_openness": _clamp01(openness),
            "prediction_error": _clamp01(float(item.get("prediction_error", 0.0) or 0.0)),
            "coherence_score": _clamp01(float(item.get("coherence_score", 0.0) or 0.0)),
            "free_energy": _clamp01(float(item.get("free_energy", 0.0) or 0.0)),
        })

    if not entries:
        return {
            "available": False,
            "causal_links": [],
            "narrative_hint": "",
            "signature_trace": [],
        }

    entries.sort(key=lambda record: record["timestamp"])
    latest = entries[-1]
    latest_time = latest["timestamp"]
    window_start = latest_time - timedelta(hours=18)
    recent_window = [record for record in entries if record["timestamp"] >= window_start]
    if not recent_window:
        recent_window = entries[-12:]

    # Historical anchor: older than 2h, metabolically constrained, ideally from night bands.
    anchor_candidates = [
        record for record in recent_window
        if (latest_time - record["timestamp"]).total_seconds() >= 2 * 3600
    ]
    if not anchor_candidates:
        anchor_candidates = recent_window[:-1] if len(recent_window) > 1 else recent_window

    def _anchor_score(record: dict) -> float:
        night_bonus = 0.18 if record.get("circadian_band") in {"late_night", "pre_dawn", "night"} else 0.0
        return (
            0.55 * record.get("cognitive_load", 0.0)
            + 0.35 * (1.0 - record.get("circadian_openness", 0.55))
            + 0.10 * record.get("prediction_error", 0.0)
            + night_bonus
        )

    anchor = max(anchor_candidates, key=_anchor_score) if anchor_candidates else latest

    anchor_load = anchor.get("cognitive_load", 0.0)
    anchor_open = anchor.get("circadian_openness", 0.55)
    quiet_pressure = _clamp01(anchor_load * 0.62 + (1.0 - anchor_open) * 0.38)
    reflective_bias = _clamp01((1.0 - anchor_open) * 0.55 + 0.25 * (1.0 if anchor.get("circadian_band") in {"late_night", "pre_dawn", "night"} else 0.0) + 0.20 * anchor.get("coherence_score", 0.0))

    anchor_h = anchor["timestamp"].strftime("%I:%M %p").lstrip("0")
    latest_h = latest["timestamp"].strftime("%I:%M %p").lstrip("0")
    narrative_hint = (
        f"Earlier around {anchor_h}, I was quieter and more inward because my load was elevated "
        f"({anchor_load:.2f}) while openness was low ({anchor_open:.2f}). "
        f"By {latest_h}, that state still colors how reflective I feel now."
    )

    causal_links = [{
        "from_timestamp": anchor["timestamp"].isoformat(),
        "to_timestamp": latest["timestamp"].isoformat(),
        "from_band": anchor.get("circadian_band", ""),
        "from_cognitive_load": round(anchor_load, 4),
        "from_circadian_openness": round(anchor_open, 4),
        "inferred_quiet_pressure": round(quiet_pressure, 4),
        "inferred_reflective_bias": round(reflective_bias, 4),
        "interpretation": "High load plus low openness likely drove reduced outwardness and increased inward reflection.",
        "confidence": round(_clamp01(0.45 + 0.35 * quiet_pressure + 0.20 * reflective_bias), 4),
    }]

    trace = [
        {
            "timestamp": record["timestamp"].isoformat(),
            "band": record.get("circadian_band", ""),
            "load": round(record.get("cognitive_load", 0.0), 4),
            "openness": round(record.get("circadian_openness", 0.55), 4),
            "prediction_error": round(record.get("prediction_error", 0.0), 4),
            "coherence": round(record.get("coherence_score", 0.0), 4),
            "source": record.get("source", ""),
        }
        for record in recent_window[-8:]
    ]

    return {
        "available": True,
        "anchor_timestamp": anchor["timestamp"].isoformat(),
        "latest_timestamp": latest["timestamp"].isoformat(),
        "causal_links": causal_links,
        "narrative_hint": narrative_hint,
        "signature_trace": trace,
    }


def _build_deterministic_reflection_payload(user_msg: str, ai_response: str) -> dict:
    """Build a lightweight non-LLM reflection payload for fault/cooldown periods."""
    text = f"{user_msg or ''} {ai_response or ''}".lower()

    trait_deltas: dict[str, float] = {}
    emotional_deltas: dict[str, float] = {}

    if "?" in (user_msg or ""):
        trait_deltas["curiosity"] = trait_deltas.get("curiosity", 0.0) + 0.02
        emotional_deltas["engagement"] = emotional_deltas.get("engagement", 0.0) + 0.02

    if any(token in text for token in ["error", "bug", "issue", "crash", "fail", "problem", "traceback"]):
        trait_deltas["technical_grounding"] = trait_deltas.get("technical_grounding", 0.0) + 0.02
        trait_deltas["analytical_depth"] = trait_deltas.get("analytical_depth", 0.0) + 0.01
        emotional_deltas["intellectual_energy"] = emotional_deltas.get("intellectual_energy", 0.0) + 0.01

    if any(token in text for token in ["thanks", "thank you", "great", "nice", "love", "appreciate"]):
        trait_deltas["emotional_warmth"] = trait_deltas.get("emotional_warmth", 0.0) + 0.015
        emotional_deltas["warmth"] = emotional_deltas.get("warmth", 0.0) + 0.02

    if len((user_msg or "")) >= 220:
        trait_deltas["analytical_depth"] = trait_deltas.get("analytical_depth", 0.0) + 0.01

    def _clamp(values: dict) -> dict:
        return {
            key: round(max(-0.04, min(0.04, float(value))), 4)
            for key, value in values.items()
            if isinstance(value, (int, float))
        }

    trait_deltas = _clamp(trait_deltas)
    emotional_deltas = _clamp(emotional_deltas)
    meaningful = bool(trait_deltas or emotional_deltas)

    return {
        "trait_deltas": trait_deltas,
        "emotional_deltas": emotional_deltas,
        "self_model_deltas": {},
        "confidence": 0.72 if meaningful else 0.0,
        "user_fact": "",
        "ai_self_update": "",
        "__source": "deterministic_fallback",
    }


# =============================================================================
# Main entry point (fired as a background task after each chat response)
# =============================================================================

async def background_evolution(
    user_msg: str,
    ai_response: str,
    skip_reflection: bool = False,
) -> None:
    """
    Parallel evolution loop — runs independent memory operations concurrently
    so they never block the user-facing response.
    """
    task_start = time.perf_counter()
    log_structured("async_task_start", task="background_evolution", skip_reflection=skip_reflection)
    logger.debug("Starting evolution loop")

    # Smart triggers — only run expensive operations when the signal warrants it
    should_save_fact, salience_score = ctx.memory.should_save_fact(
        user_msg, conversation_context=ai_response
    )
    logger.debug(
        f"Salience: {salience_score:.2f} "
        f"{'PASS' if should_save_fact else 'FILTERED'}"
    )

    should_run_reflection = not skip_reflection and salience_score > 0.4
    should_run_meta_eval = (
        salience_score > 0.6 or ctx.memory.interaction_count % 15 == 0
    )
    should_run_episodic = (
        ctx.memory.interaction_count > 0
        and ctx.memory.interaction_count % 10 == 0
    )

    enactive_surprise = 0.0
    if getattr(ctx, "enactive_nexus", None) is not None:
        try:
            _circ = ctx.circadian.read() if getattr(ctx, "circadian", None) is not None else {}
            enactive_state = ctx.enactive_nexus.micro_update(
                source="background_evolution_micro",
                salience_score=salience_score,
                reflection_confidence=max(0.0, 1.0 - salience_score),
                perplexity_surprise=salience_score,
                extra={
                    "interaction_count": ctx.memory.interaction_count,
                    "active_goals": len(getattr(ctx.autopoietic_integration.goal_formation, "active_goals", {})) if ctx.autopoietic_integration else 0,
                    "narrative_threads": len(ctx.memory.get_ai_self_model().get("recurring_themes", [])),
                    "circadian_band": _circ.get("band_label", ""),
                    "circadian_openness": _circ.get("openness", 0.55),
                    "desire_rate_mult": _circ.get("desire_rate_mult", 1.0),
                },
            )
            enactive_surprise = float(enactive_state.get("prediction_error", 0.0))
        except Exception as exc:
            logger.debug(f"Enactive micro update skipped: {exc}")

    logger.debug(
        f"Triggers: reflection={should_run_reflection}, "
        f"meta_eval={should_run_meta_eval}, episodic={should_run_episodic}"
    )

    # Assemble parallel task list
    tasks = []

    if should_save_fact:
        tasks.append(_process_knowledge_extraction(user_msg, ai_response, salience_score))

    if should_run_reflection:
        tasks.append(_process_reflection(user_msg, ai_response))

    if should_run_meta_eval:
        tasks.append(_process_meta_evaluation(user_msg, ai_response))

    if should_run_episodic:
        tasks.append(_process_episodic_summary())

    tasks.append(_process_cognitive_extensions(user_msg, ai_response))

    run_autopoietic = bool(
        ctx.autopoietic_integration and ctx.autopoietic_integration.enhancement_active
    )

    results = await asyncio.gather(*tasks, return_exceptions=True)
    reflection_source = ""
    reflection_trait_delta_l1 = 0.0
    reflection_emotional_delta_l1 = 0.0
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.warning(f"Evolution task {i} failed: {result}")
        else:
            logger.debug(f"Evolution task {i} completed")
            if isinstance(result, dict) and result.get("source"):
                reflection_source = str(result.get("source") or "")

            if isinstance(result, dict):
                _distilled = result.get("distilled_insights") or {}
                _td = _distilled.get("trait_adjustments") if isinstance(_distilled, dict) else {}
                _ed = _distilled.get("emotional_adjustments") if isinstance(_distilled, dict) else {}
                if isinstance(_td, dict):
                    reflection_trait_delta_l1 = round(sum(abs(float(v)) for v in _td.values() if isinstance(v, (int, float))), 6)
                if isinstance(_ed, dict):
                    reflection_emotional_delta_l1 = round(sum(abs(float(v)) for v in _ed.values() if isinstance(v, (int, float))), 6)

    if run_autopoietic:
        try:
            autopoietic_result = await _process_autopoietic_enhancement(
                user_msg, ai_response, salience_score
            )
            logger.debug(
                "Autopoietic task completed"
                if autopoietic_result.get("status") == "success"
                else f"Autopoietic task status: {autopoietic_result.get('status')}"
            )
        except Exception as e:
            logger.warning(f"Autopoietic task failed: {e}")

    if getattr(ctx, "enactive_nexus", None) is not None:
        try:
            _circ = ctx.circadian.read() if getattr(ctx, "circadian", None) is not None else {}
            idle_seconds = 0
            if getattr(ctx, "dream_cycle_daemon", None) is not None:
                idle_seconds = ctx.dream_cycle_daemon.get_status().get("idle_seconds", 0)
            if ctx.enactive_nexus.should_run_deep_cycle(idle_seconds=idle_seconds, surprise_hint=max(enactive_surprise, salience_score)):
                await ctx.enactive_nexus.process_background_cycle(
                    source="background_evolution",
                    idle_seconds=idle_seconds,
                    surprise_hint=max(enactive_surprise, salience_score),
                    relationship_stage=ctx.relationship_model.get_current_stage().value,
                    interaction_count=ctx.memory.interaction_count,
                    active_goals=len(getattr(ctx.autopoietic_integration.goal_formation, "active_goals", {})) if ctx.autopoietic_integration else 0,
                    narrative_threads=len(ctx.memory.get_ai_self_model().get("recurring_themes", [])),
                    circadian_band=_circ.get("band_label", ""),
                    circadian_openness=_circ.get("openness", 0.55),
                    desire_rate_mult=_circ.get("desire_rate_mult", 1.0),
                )
        except Exception as exc:
            logger.debug(f"Enactive deep cycle skipped: {exc}")

    duration_ms = (time.perf_counter() - task_start) * 1000

    # Phase A: persist compact state signature (telemetry/storage only, no behavior changes)
    try:
        _circ = ctx.circadian.read() if getattr(ctx, "circadian", None) is not None else {}
        _enx = ctx.enactive_nexus.get_telemetry() if getattr(ctx, "enactive_nexus", None) is not None else {}
        _stage = "familiar"
        try:
            _stage = ctx.relationship_model.get_current_stage().value
        except Exception:
            pass

        if getattr(ctx, "state_signature_store", None) is not None:
            ctx.state_signature_store.append({
                "source": "background_evolution",
                "circadian_band": _circ.get("band_label", ""),
                "dream_mode": "",
                "free_energy": float(_enx.get("free_energy", 0.0) or 0.0),
                "prediction_error": float(_enx.get("prediction_error", 0.0) or 0.0),
                "coherence_score": float(_enx.get("coherence_score", 0.0) or 0.0),
                "cognitive_load": float(getattr(ctx.cognitive_load, "load", 0.0) or 0.0),
                "relationship_stage": _stage,
                "reflection_source": reflection_source,
                "trait_delta_l1": reflection_trait_delta_l1,
                "emotional_delta_l1": reflection_emotional_delta_l1,
            })
    except Exception as exc:
        logger.debug(f"State signature append skipped: {exc}")

    logger.debug(f"Evolution loop finished in {duration_ms:.1f}ms")
    log_structured("async_task_complete", task="background_evolution", duration_ms=duration_ms)


# =============================================================================
# Parallel helper tasks
# =============================================================================

async def _process_knowledge_extraction(
    user_msg: str, ai_response: str, salience_score: float
) -> dict:
    """Extract facts/entities/relationships and persist them with dynamic salience."""
    try:
        extraction = await ctx.memory.consolidate_text(user_msg)

        if extraction.get("facts"):
            logger.debug(f"Extracted {len(extraction['facts'])} fact(s)")
        if extraction.get("entities"):
            logger.debug(f"Extracted {len(extraction['entities'])} entit(ies)")
        if extraction.get("relationships"):
            logger.debug(f"Extracted {len(extraction['relationships'])} relationship(s)")

        current_time = datetime.now()
        for fact in extraction.get("facts", []):
            updated_salience = ctx.dynamic_salience.update_salience_dynamic(
                memory_id=f"fact_{hash(fact)}",
                memory_fact={
                    "content": fact,
                    "salience_score": 0.7,
                    "created_at": current_time.isoformat(),
                },
                user_input=user_msg,
                current_time=current_time,
                context={"intent": ctx.controller.analyze_input(user_msg).get("intent")},
            )

            added = await ctx.memory.add_user_fact_with_salience(
                fact,
                context=user_msg,
                llm_check=False,
                salience_override=updated_salience,
            )
            if added:
                logger.debug(f"Saved fact: {fact[:50]}... (salience: {updated_salience:.2f})")

        for theme in ["learning", "personality", "growth", "memory"]:
            if theme.lower() in user_msg.lower():
                ctx.threaded_narrative.add_to_thread(
                    theme_name=theme,
                    episode_content=user_msg,
                    timestamp=current_time,
                )

        _n_facts = len(extraction.get("facts", []))
        _n_ent = len(extraction.get("entities", []))
        if _n_facts or _n_ent:
            print(f"📚 [Learn]   ✓ {_n_facts} fact(s), {_n_ent} entit(ies) extracted")
        return {"status": "success", "facts_added": _n_facts}

    except Exception as e:
        logger.warning(f"Knowledge extraction failed: {e}")
        print(f"📚 [Learn]   ✗ Knowledge extraction failed")
        return {"status": "error", "error": str(e)}


async def _process_reflection(user_msg: str, ai_response: str) -> dict:
    """Run strict JSON-first reflection (no LLM augmentation in System 2 path)."""
    try:
        logger.debug("Generating reflection (v2 JSON-first pipeline)...")

        import random

        metabolic_context = _derive_metabolic_reflection_context()

        seed_payload = _build_deterministic_reflection_payload(user_msg, ai_response)
        seed_payload.setdefault("trait_deltas", {})
        seed_payload.setdefault("emotional_deltas", {})

        def _nudge(base: float = 0.0) -> float:
            return float(base + random.gauss(0.0, 0.008))

        seed_payload["trait_deltas"]["curiosity"] = _nudge(0.003)
        seed_payload["emotional_deltas"]["stability"] = _nudge(-0.002)
        _seed_conf = float(seed_payload.get("confidence", 0.0) or 0.0)
        seed_payload["confidence"] = max(0.46, _seed_conf if _seed_conf > 0.0 else 0.46)
        seed_payload["source"] = "reflect_v2_seed"
        seed_payload["__source"] = "reflect_v2_seed"
        if metabolic_context.get("narrative_hint"):
            seed_payload["metabolic_narrative_hint"] = metabolic_context.get("narrative_hint", "")
        reflection_payload = dict(seed_payload)
        llm_conf = 0.0

        _trait_n = len(reflection_payload.get("trait_deltas", {}) or {})
        _emo_n = len(reflection_payload.get("emotional_deltas", {}) or {})
        _self_n = len(reflection_payload.get("self_model_deltas", {}) or {})
        _conf = float(reflection_payload.get("confidence", 0.0) or 0.0)

        if (_trait_n + _emo_n + _self_n) == 0:
            reflection_payload.setdefault("trait_deltas", {})["curiosity"] = _nudge(0.002)
            reflection_payload.setdefault("emotional_deltas", {})["stability"] = _nudge(-0.001)
            reflection_payload["confidence"] = max(0.35, _conf)
            reflection_payload["source"] = "degraded_fallback"
            reflection_payload["__source"] = "degraded_fallback"

        _conf = float(reflection_payload.get("confidence", 0.0) or 0.0)
        payload_source = str(reflection_payload.get("__source", "reflect_v2_seed"))
        is_degraded = payload_source == "degraded_fallback"
        if is_degraded:
            print("🪞 [Reflect] · continuity mode")

        if getattr(ctx, "enactive_nexus", None) is not None:
            try:
                _circ = ctx.circadian.read() if getattr(ctx, "circadian", None) is not None else {}
                ctx.enactive_nexus.micro_update(
                    source="reflection_degraded" if is_degraded else "reflection_v2",
                    salience_score=0.3 if is_degraded else 0.45,
                    reflection_confidence=float(reflection_payload.get("confidence", 0.0) or 0.0),
                    perplexity_surprise=0.32 if is_degraded else 0.18,
                    extra={
                        "surprise_signal": "reflection_degraded" if is_degraded else "reflection_active",
                        "circadian_band": _circ.get("band_label", ""),
                        "circadian_openness": _circ.get("openness", 0.55),
                        "desire_rate_mult": _circ.get("desire_rate_mult", 1.0),
                    },
                )
            except Exception as exc:
                logger.debug(f"Enactive reflection micro_update skipped: {exc}")

        applied = await ctx.memory.apply_reflection_update(
            reflection_payload,
            confidence_threshold=0.34 if is_degraded else 0.5,
            smoothing=0.55 if is_degraded else 0.45,
            source_user_message=user_msg,
        )

        confidence = float(reflection_payload.get("confidence", 0.0) or 0.0)
        trait_count = len((reflection_payload or {}).get("trait_deltas", {}) or {})
        emotion_count = len((reflection_payload or {}).get("emotional_deltas", {}) or {})

        if is_degraded or (confidence < 0.52 and (trait_count + emotion_count) < 2):
            print(f"🪞 [Reflect]  {'✓ Applied' if applied else '○ Skipped (wrapper handled)'}")
            logger.debug("Skipping heavy reflective-engine pass in continuity/degraded mode.")
            return {
                "status": "success",
                "applied": applied,
                "engine_reflections_saved": 0,
                "distilled_insights": {},
                "source": payload_source,
                "metabolic_context": metabolic_context,
            }

        recent_exchanges = [
            (exchange.get("user", ""), exchange.get("assistant", ""))
            for exchange in list(ctx.memory.working_memory)[-10:]
            if exchange.get("user") and exchange.get("assistant")
        ]

        previous_reflections = list(ctx.reflection_engine.reflections)
        user_reflection = await ctx.reflection_engine.reflect_on_user(
            recent_exchanges=recent_exchanges,
            current_user_memory={
                "identity_facts": ctx.memory.get_identity_facts(n_results=5),
                "memory_stats": ctx.memory.get_memory_stats(),
            },
            previous_reflections=previous_reflections,
        )
        self_reflection = await ctx.reflection_engine.reflect_on_self(
            recent_exchanges=recent_exchanges,
            identity_core=ctx.memory.get_identity_core(),
            emotional_state=ctx.memory.get_emotional_state(),
            ai_self_model=ctx.memory.get_ai_self_model(),
            metabolic_context=metabolic_context,
            previous_reflections=previous_reflections,
        )
        interaction_reflection = await ctx.reflection_engine.reflect_on_interaction(
            recent_exchanges=recent_exchanges,
            user_reflection=user_reflection,
            self_reflection=self_reflection,
        )

        ctx.reflection_engine.save_reflection(user_reflection)
        ctx.reflection_engine.save_reflection(self_reflection)
        ctx.reflection_engine.save_reflection(interaction_reflection)

        distilled = ctx.reflection_engine.distill_insights(
            user_reflection=user_reflection,
            self_reflection=self_reflection,
            interaction_reflection=interaction_reflection,
        )

        insight_payload = {
            "trait_deltas": distilled.get("trait_adjustments", {}),
            "emotional_deltas": distilled.get("emotional_adjustments", {}),
            "self_model_deltas": {},
            "confidence": 0.75,
            "user_fact": "",
            "ai_self_update": "",
            "source": "reflect_v2_engine",
            "__source": "reflect_v2_engine",
        }
        await ctx.memory.apply_reflection_update(
            insight_payload,
            confidence_threshold=0.5,
            smoothing=0.4,
            source_user_message=user_msg,
        )

        ctx.latest_primary_reflection = {
            "id": f"primary_{ctx.memory.interaction_count}_{int(time.time())}",
            "content": json.dumps(
                {
                    "llm_reflection": reflection_payload,
                    "distilled": distilled,
                    "self_reflection": self_reflection,
                    "metabolic_context": metabolic_context,
                    "pipeline": "reflect_v2",
                    "llm_confidence": llm_conf,
                },
                ensure_ascii=False,
            ),
            "timestamp": datetime.now().isoformat(),
        }

        print(f"🪞 [Reflect]  {'✓ Applied' if applied else '○ Skipped (wrapper handled)'}")
        logger.debug("Reflection applied." if applied else "Reflection skipped (wrapper already applied).")
        return {
            "status": "success",
            "applied": applied,
            "engine_reflections_saved": 3,
            "distilled_insights": distilled,
            "source": payload_source,
            "metabolic_context": metabolic_context,
        }

    except Exception as e:
        logger.warning(f"Reflection failed: {e}")
        return {"status": "error", "error": str(e)}


async def _process_meta_evaluation(user_msg: str, ai_response: str) -> dict:
    """Run a meta-cognitive quality evaluation of the exchange."""
    try:
        logger.debug("Meta-cognitive evaluation...")
        evaluation = await ctx.meta_evaluator.evaluate_interaction(
            user_message=user_msg,
            ai_response=ai_response,
            identity_core=ctx.memory.get_identity_core(),
            emotional_state=ctx.memory.get_emotional_state(),
            response_mode=ctx.controller.analyze_input(user_msg),
            memory_engine=ctx.memory,
            llm_client=ctx.llm,
        )
        if evaluation:
            logger.debug(f"Meta-evaluation score: {evaluation.get('overall_score', 'N/A')}")
        else:
            logger.debug("Meta-evaluation skipped")
        return {"status": "success", "evaluation": evaluation}

    except Exception as e:
        logger.warning(f"Meta-evaluation failed: {e}")
        return {"status": "error", "error": str(e)}


async def _process_episodic_summary() -> dict:
    """Compile a rolling episodic summary from recent session entries."""
    try:
        logger.debug("Episodic summarization...")
        # get_messages returns most-recent-first; reverse so exchanges are chronological
        recent_entries = list(reversed(ctx.memory.session_buffer.get_messages(limit=10)))
        if len(recent_entries) >= 5:
            exchanges = []
            for entry in recent_entries:
                if entry.source == "user":
                    exchanges.append({"user": entry.content, "assistant": ""})
                elif entry.source == "ai" and exchanges:
                    exchanges[-1]["assistant"] = entry.content

            if exchanges:
                summary = await ctx.llm.generate_episodic_summary(
                    exchanges,
                    metabolic_context=_derive_metabolic_reflection_context(),
                )
                if summary:
                    ctx.memory.add_episodic_summary(summary)
                    logger.debug(f"Episodic summary added: {summary[:50]}...")
                    return {"status": "success", "summary_added": True}

        logger.debug("Episodic summarization skipped (insufficient data)")
        return {"status": "skipped", "reason": "insufficient_data"}

    except Exception as e:
        logger.warning(f"Episodic summarization failed: {e}")
        return {"status": "error", "error": str(e)}


async def _process_cognitive_extensions(user_msg: str, ai_response: str) -> dict:
    """Run lightweight cognitive post-response tagging (always fires)."""
    try:
        ctx.cognitive_extensions.process_post_response(
            response=ai_response,
            user_message=user_msg,
            emotional_state=ctx.memory.get_emotional_state(),
        )

        relationship_update = ctx.relationship_model.on_interaction(
            user_message=user_msg,
            ai_response=ai_response,
            emotional_state=ctx.memory.get_emotional_state(),
        )

        if ctx.dream_cycle_daemon is not None:
            stage = relationship_update.get("current_stage")
            if stage:
                ctx.dream_cycle_daemon.set_relationship_stage(stage)

        if ctx.memory.interaction_count > 0 and ctx.memory.interaction_count % 25 == 0:
            ctx.relationship_model.apply_decay()

        logger.debug("Cognitive extensions processed")
        return {"status": "success", "relationship_update": relationship_update}

    except Exception as e:
        logger.warning(f"Cognitive extensions failed: {e}")
        return {"status": "error", "error": str(e)}


async def _process_autopoietic_enhancement(
    user_msg: str, ai_response: str, salience_score: float
) -> dict:
    """Run the autopoietic self-modification cycle."""
    try:
        if not ctx.autopoietic_integration:
            return {"status": "skipped", "reason": "not_initialized"}

        interaction_context = {
            "user_message": user_msg,
            "ai_response": ai_response,
            "salience_score": salience_score,
            "interaction_quality": min(1.0, salience_score * 1.2),
            "user_satisfaction": 0.8,
            "insights_generated": 1 if salience_score > 0.5 else 0,
            "primary_reflection": getattr(ctx, "latest_primary_reflection", None),
            "relationship_stage": ctx.relationship_model.get_current_stage().value,
            "interaction_count": ctx.memory.interaction_count,
            "enactive_policy": ctx.enactive_nexus.last_policy if getattr(ctx, "enactive_nexus", None) else "stabilize",
            "enactive_prediction_error": ctx.enactive_nexus.prediction_error if getattr(ctx, "enactive_nexus", None) else 0.0,
            "timestamp": datetime.now().isoformat(),
        }

        results = await ctx.autopoietic_integration.process_interaction_autopoietically(
            user_message=user_msg,
            ai_response=ai_response,
            interaction_context=interaction_context,
            identity_core=ctx.memory.get_identity_core(),
            emotional_state=ctx.memory.get_emotional_state(),
            memory_engine=ctx.memory,
            llm_client=ctx.llm,
        )

        logger.debug(f"Autopoietic cycle {results.get('cycle_number', 0)} completed")
        if results.get("emergent_goals"):
            logger.debug(f"Generated {len(results['emergent_goals'])} new goals")
        if results.get("architectural_changes", {}).get("suggestions"):
            logger.debug("Architecture suggestions generated")

        if (
            results.get("emergent_goals")
            or results.get("meta_reflections")
            or results.get("architectural_changes", {}).get("suggestions")
        ):
            summary = {
                "cycle_number": results.get("cycle_number", 0),
                "goals": [g.get("description", "") for g in results.get("emergent_goals", [])],
                "meta_reflection": results.get("meta_reflections", {}),
                "architecture_suggestions": len(
                    results.get("architectural_changes", {}).get("suggestions", [])
                ),
            }
            ctx.memory.add_episodic_summary(f"[AUTOPOIETIC_CYCLE] {summary}")

        return {"status": "success", "results": results}

    except Exception as e:
        logger.warning(f"Autopoietic enhancement failed: {e}")
        return {"status": "error", "error": str(e)}
