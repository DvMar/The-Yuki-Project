from fastapi import FastAPI, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel
import os
import re
import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Literal, Set, Dict, List, Optional

import api.context as ctx
from api.context import (
    llm, memory, persona, controller, subconscious_wrapper, conflict_resolver,
    adaptive_response, reflection_engine, memory_decay, threaded_narrative, meta_evaluator, self_improvement, cognitive_extensions,
    relationship_model, proactive_queue, enactive_nexus,
    circadian, cognitive_load, user_model,
)
from api.evolution import background_evolution
from api.tasks import task_monitor_loop, store_wrapper_memory_candidates
from cognition.reflective_daemon import DreamCycleDaemon
from cognition.autopoietic_integration import AutopoieticEnhancementLayer
from cognition.inner_voice import InnerVoice as _InnerVoiceCls
from utils.time_utils import get_local_time
from utils.logging import log_structured
from llm import PROFILE_CHAT, PROFILE_CREATIVE, PROFILE_STRUCTURED, PROFILE_REFLECTION

_inner_voice = _InnerVoiceCls()

# Configure logging to ensure our messages are visible
logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(name)s: %(message)s')

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown lifecycle."""
    
    # ===== STARTUP =====
    print("[STARTUP] 🔧 Initializing background services...")
    
    # Initialize Autopoietic Integration
    ctx.autopoietic_integration = AutopoieticEnhancementLayer(
        db_path="persistent_state/autopoietic.db",
        enactive_nexus=enactive_nexus,
    )
    print("[STARTUP] ✅ Autopoietic systems initialized")
    
    # Dream-cycle thresholds (production-safe by default).
    # Set DREAMCYCLE_TEST_MODE=true to use lower testing thresholds.
    dreamcycle_test_mode = (
        os.getenv("DREAMCYCLE_TEST_MODE", "false").strip().lower()
        in {"1", "true", "yes", "y"}
    )
    idle_threshold_seconds = int(os.getenv("DREAM_IDLE_THRESHOLD_SECONDS", "180"))
    salience_threshold = float(os.getenv("DREAM_SALIENCE_THRESHOLD", "0.45"))
    urgency_threshold = float(os.getenv("DREAM_URGENCY_THRESHOLD", "0.50"))

    if dreamcycle_test_mode:
        idle_threshold_seconds = 30
        salience_threshold = 0.15
        urgency_threshold = 0.20
        print("[STARTUP] ⚠️ DREAMCYCLE_TEST_MODE enabled: using lowered thresholds")

    # Initialize DreamCycleDaemon with internal_message_handler callback
    # This allows Dream Cycle to inject internal messages into the chat pipeline
    ctx.dream_cycle_daemon = DreamCycleDaemon(
        llm_client=llm,
        memory_engine=memory,
        conflict_resolver=conflict_resolver,
        enactive_nexus=enactive_nexus,
        response_generator=adaptive_response,
        proactive_queue=proactive_queue,
        persona_name=persona.name,
        internal_message_handler=handle_internal_message_wrapper,  # NEW: Callback for self-initiated messages
        idle_threshold_seconds=idle_threshold_seconds,
        salience_threshold=salience_threshold,
        urgency_threshold=urgency_threshold,
        cognitive_load=cognitive_load,           # Gap 3: fatigue signal shared with daemon
        state_signature_store=getattr(ctx, "state_signature_store", None),
        proactive_intention_store=getattr(ctx, "proactive_intention_store", None),
    )
    print("[STARTUP] ✅ System 3 daemon initialized with internal message handler")

    # Hydrate unresolved proactive intentions into runtime queue (Delta 3 / Phase C)
    try:
        _hydrated = 0
        if getattr(ctx, "proactive_intention_store", None) is not None:
            _hydrated = ctx.proactive_intention_store.hydrate_runtime_queue(proactive_queue, max_items=20)
        print(f"[STARTUP] ✅ Proactive intentions hydrated: {_hydrated}")
    except Exception as e:
        print(f"[STARTUP] ⚠️ Intention hydration skipped: {e}")
    
    # Reset task check times on startup
    # Reset task check times on startup
    # This recalculates all task deadlines and adjusts check frequencies
    memory.task_scheduler.reset_tasks_on_startup()
    print("[STARTUP] ✅ Task scheduler reset")
    
    # ===== PERFORMANCE OPTIMIZATION: Start Memory Buffer =====
    await memory.start_buffer()
    print("[STARTUP] ✅ Memory buffer started for optimized I/O")
    
    # Start the adaptive task monitor
    asyncio.create_task(task_monitor_loop())
    print("[STARTUP] ✅ Task monitor started")

    # Start System 3 daemon
    asyncio.create_task(ctx.dream_cycle_daemon.run())
    print("[STARTUP] ✅ Dream cycle daemon started")

    # Start WebSocket telemetry broadcaster
    asyncio.create_task(_telemetry_broadcaster())
    print("[STARTUP] ✅ WS telemetry broadcaster started")

    print("[STARTUP] 🎉 All background services ready!")
    
    yield  # Application runs here
    
    print("[SHUTDOWN] 🛑 Starting shutdown sequence...")
    
    # ===== SHUTDOWN =====
    print("[SHUTDOWN] 🛑 Shutting down background services...")
    
    # Stop memory buffer
    try:
        await memory.stop_buffer()
        print("[SHUTDOWN] ✅ Memory buffer stopped")
    except Exception as e:
        print(f"[SHUTDOWN] Error stopping memory buffer: {e}")
    
    # Close memory backend
    try:
        await memory.backend.close()
        print("[SHUTDOWN] ✅ Memory backend closed")
    except Exception as e:
        print(f"[SHUTDOWN] Error closing memory backend: {e}")
    
    print("[SHUTDOWN] 🎉 All services shut down gracefully!")

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/web", StaticFiles(directory="web"), name="web")


# =========================
# 📡 WebSocket Connection Manager
# =========================

class ConnectionManager:
    """Tracks all active /ws/telemetry connections and broadcasts JSON payloads."""

    def __init__(self):
        self._connections: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)
        logger.info(f"[WS] Client connected ({len(self._connections)} total)")

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)
        logger.info(f"[WS] Client disconnected ({len(self._connections)} remaining)")

    async def broadcast(self, payload: dict) -> None:
        """Send *payload* as JSON to every connected client, dropping dead sockets."""
        if not self._connections:
            return
        message = json.dumps(payload, default=str)
        dead: list[WebSocket] = []
        for ws in list(self._connections):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.discard(ws)

    @property
    def count(self) -> int:
        return len(self._connections)


_ws_manager = ConnectionManager()


async def _telemetry_broadcaster() -> None:
    """
    Background coroutine started at app startup.

    Emits three kinds of WebSocket messages:
      1. ``server_heartbeat``     every 3 s  — keeps connections alive, drives breathing
      2. ``telemetry_update``     every 5 s  — full cognitive state snapshot (same data as /latest_log)
      3. ``chroma_retrieval``     drained from ctx.ws_event_queue whenever new items arrive
    """
    HEARTBEAT_INTERVAL  = 3    # seconds
    TELEMETRY_INTERVAL  = 5    # seconds
    last_heartbeat  = 0.0
    last_telemetry  = 0.0

    while True:
        await asyncio.sleep(0.5)

        # Delta 3: suppression transition — when cognitive exhaustion flips on,
        # suppress pending proactive intentions to avoid forced outreach.
        try:
            exhausted_now = bool(getattr(cognitive_load, "is_exhausted", False))
            exhausted_prev = bool(getattr(ctx, "last_cognitive_exhausted", False))
            if exhausted_now and not exhausted_prev and getattr(ctx, "proactive_intention_store", None) is not None:
                suppressed = ctx.proactive_intention_store.suppress_pending(reason="cognitive_exhaustion")
                if suppressed:
                    logger.info(f"[INTENTION] Suppressed {suppressed} pending intention(s) due to exhaustion")
            ctx.last_cognitive_exhausted = exhausted_now
        except Exception as exc:
            logger.debug(f"[INTENTION] Exhaustion suppression check skipped: {exc}")

        # —— no clients? idle but keep the loop alive ——
        if _ws_manager.count == 0:
            continue

        now = time.monotonic()

        # 1. Heartbeat
        if now - last_heartbeat >= HEARTBEAT_INTERVAL:
            last_heartbeat = now
            await _ws_manager.broadcast({
                "type": "server_heartbeat",
                "ts":   datetime.now().isoformat(),
            })

        # 2. Full telemetry snapshot
        if now - last_telemetry >= TELEMETRY_INTERVAL:
            last_telemetry = now
            try:
                snapshot = _build_telemetry_snapshot()
                await _ws_manager.broadcast({
                    "type": "telemetry_update",
                    "ts":   datetime.now().isoformat(),
                    "data": snapshot,
                })
            except Exception as exc:
                logger.warning(f"[WS] Telemetry snapshot error: {exc}")

        # 3. Drain chroma_retrieval event queue
        while ctx.ws_event_queue:
            try:
                event = ctx.ws_event_queue.popleft()
                await _ws_manager.broadcast(event)
            except IndexError:
                break
            except Exception as exc:
                logger.debug(f"[WS] Event drain error: {exc}")


def _build_telemetry_snapshot() -> dict:
    """
    Assemble a lean telemetry payload from live singletons.
    Mirrors the structure of /latest_log so the frontend JS can reuse the
    same ingestion logic.
    """
    from api.context import (
        memory, llm, proactive_queue,
        latest_postprocess_telemetry,
        autopoietic_integration,
        dream_cycle_daemon,
        enactive_nexus,
        circadian, cognitive_load, user_model, relationship_model,
        state_signature_store, proactive_intention_store,
    )
    ai_self_model = memory.get_ai_self_model()
    llm_stats     = llm.get_performance_stats()
    kg_stats      = memory.knowledge_graph.get_stats() if hasattr(
                        memory.knowledge_graph, "get_stats") else {}
    search_stats  = memory.hybrid_search.get_search_stats() if hasattr(
                        memory.hybrid_search, "get_search_stats") else {}
    auto_status   = autopoietic_integration.get_autopoietic_status(
                    ) if autopoietic_integration else {}
    _enx_telemetry = enactive_nexus.get_telemetry() if enactive_nexus else {}
    _recent_signatures = state_signature_store.get_recent(5) if state_signature_store else []
    _temporal_policy_trace = {
        "circadian_band": circadian.read().get("band_label", ""),
        "circadian_openness": round(float(circadian.read().get("openness", 0.55) or 0.55), 4),
        "desire_rate_mult": round(float(circadian.read().get("desire_rate_mult", 1.0) or 1.0), 4),
        "enactive_policy": _enx_telemetry.get("last_policy", "stabilize"),
        "free_energy": _enx_telemetry.get("free_energy", 0.0),
        "prediction_error": _enx_telemetry.get("prediction_error", 0.0),
        "coherence_score": _enx_telemetry.get("coherence_score", 0.0),
        "cognitive_load": round(cognitive_load.load, 3),
        "relationship_stage": relationship_model.get_current_stage().value if relationship_model else "familiar",
        "recent_state_signatures": _recent_signatures,
    }
    _intention_stats = proactive_intention_store.get_stats() if proactive_intention_store else {}

    return {
        "identity_core":           memory.get_identity_core(),
        "emotional_state":         memory.get_emotional_state(),
        "ai_self_model":           ai_self_model,
        "interaction_count":       memory.interaction_count,
        "last_intent":             memory.last_intent,
        "response_mode":           memory.last_response_mode,
        "memory_stats":            memory.get_memory_stats(),
        "postprocess_telemetry":   latest_postprocess_telemetry,
        "last_search_stats":       search_stats,
        "knowledge_graph_stats":   kg_stats,
        "llm_performance":         llm_stats,
        "buffer_stats":            memory.get_buffer_stats(),
        "dreamcycle_status":       dream_cycle_daemon.get_status() if dream_cycle_daemon else {},
        "autopoieticStatus":       auto_status,
        "enactive_nexus":          _enx_telemetry,
        "temporal_policy_trace":   _temporal_policy_trace,
        "proactive_intentions":    _intention_stats,
        # New synthetic-life systems
        "circadian":          circadian.read(),
        "cognitive_load":     {
            "load":         round(cognitive_load.load, 3),
            "is_tired":     cognitive_load.is_tired,
            "is_exhausted": cognitive_load.is_exhausted,
        },
        "user_model_stats": {
            "interests_count": len(getattr(user_model, 'topic_interests', {}) or {}),
            "beliefs_count":   len(getattr(user_model, 'beliefs',   {}) or {}),
            "last_surprise":   round(getattr(user_model, '_last_surprise_score', 0.0), 3),
        },
    }


# =========================
# 📡 WebSocket Endpoint
# =========================

@app.websocket("/ws/telemetry")
async def ws_telemetry(ws: WebSocket):
    """
    Real-time telemetry stream for the Connectome visualizer.
    Sends heartbeats, full telemetry snapshots, and chroma_retrieval events.
    """
    await _ws_manager.connect(ws)
    try:
        # Send an immediate snapshot so the UI doesn't wait 5 s on first load.
        try:
            await ws.send_text(json.dumps({
                "type": "telemetry_update",
                "ts":   datetime.now().isoformat(),
                "data": _build_telemetry_snapshot(),
            }, default=str))
        except Exception:
            pass

        # Keep the connection open; all broadcasting is done by _telemetry_broadcaster.
        while True:
            # We still need to receive (ping-pong / keep-alive) to detect client disconnect.
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=30)
                # Clients may optionally send a JSON ping; we just ignore the content.
                if msg:
                    pass
            except asyncio.TimeoutError:
                pass   # normal; we just loop and wait for the broadcaster to push
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug(f"[WS] Connection error: {exc}")
    finally:
        _ws_manager.disconnect(ws)


# =========================
class ChatRequest(BaseModel):
    message: str
    stream_raw: bool = False
    """
    When True, tokens are streamed directly to the client without post-processing
    (SubconsciousWrapper, ConflictResolver, AdaptiveResponseGenerator are skipped).
    Background evolution still runs, but uses the raw LLM output.
    Useful for debugging, creative generation, or low-latency use cases.
    """
    sampler_profile: str = "chat"
    """
    Named sampler profile: "chat" | "creative" | "structured" | "reflection".
    Mapped to a SamplerProfile and forwarded to the LLM backend.
    """

    stream_strategy: Literal["processed", "token"] = "processed"
    """
    Streaming strategy for non-raw responses:
    - processed: generate full response, then apply deterministic post-processing before sending (default)
    - token: stream tokens immediately as generated; still runs post-processing for internal state updates
    """


class SaveConversationRequest(BaseModel):
    conversation: list


class MemorySearchRequest(BaseModel):
    query: str
    tier: Literal["fast", "balanced", "deep"] = "balanced"
    n_results: int = 5
    collections: Optional[List[str]] = None


class MemoryConsolidateRequest(BaseModel):
    text: str


class MetaEvaluateRequest(BaseModel):
    user_message: str
    ai_response: str
    response_mode: Dict = {}

# 💬 Chat Endpoint
# =========================
@app.post("/chat")
async def chat(request: ChatRequest, background_tasks: BackgroundTasks):
    user_msg = request.message
    current_time = get_local_time()
    ctx.dream_cycle_daemon.touch()
    cognitive_load.on_interaction()

    # User model ingestion — extract interests, beliefs, detect relational surprise
    _user_ingest = user_model.ingest(user_msg)
    _user_surprise = _user_ingest.get("surprise_score", 0.0)

    # Relational surprise from user model feeds Enactive prediction error
    # as a distinct signal from perplexity-based surprise (Gap 5)
    if _user_surprise > 0.20 and enactive_nexus is not None:
        enactive_nexus.prediction_error = min(
            1.0, enactive_nexus.prediction_error * 0.65 + _user_surprise * 0.35
        )

    # -----------------------------------
    # 1️⃣ Cognitive Control + Memory Selection (V3)
    # -----------------------------------

    control_state = controller.analyze_input(user_msg)
    memory.set_control_state(control_state.get("intent"), control_state.get("response_mode"))
    
    # Identity Core (structured personality state)
    identity_core = memory.get_identity_core()

    # Emotional State (modulation layer)
    emotional_state = memory.get_emotional_state()
    
    # AI Self-Model (cognitive bias layer)
    ai_self_model = memory.get_ai_self_model()
    
    # ===== ALWAYS RETRIEVE IDENTITY FACTS (Critical for remembering user) =====
    identity_facts = memory.get_identity_facts(n_results=5)
    
    # Semantic Memory (user facts with deduplication) - NOW USING HYBRID SEARCH v5
    if control_state.get("use_semantic_memory"):
        # Use hybrid search for message-specific facts
        specific_search = memory.search(user_msg, tier="balanced", n_results=3)
        specific_facts = [r["text"] for r in specific_search["results"] if r["source"] == "user_memory"][:2]
        
        # Combine identity facts with specific facts (identity facts take priority)
        user_facts = identity_facts + specific_facts
        user_facts = list(dict.fromkeys(user_facts))[:3]  # Remove duplicates, keep first 3
    else:
        # Even if semantic memory is disabled by intent, always include identity facts
        user_facts = identity_facts[:2]
    
    # Episodic Memory (conversation summaries) - NOW USING HYBRID SEARCH v5
    if control_state.get("use_episodic_memory"):
        episodic_search = memory.search(user_msg, tier="balanced", n_results=2)
        episodic_context = [r["text"] for r in episodic_search["results"] if r["source"] == "episodic_memory"][:2]
    else:
        episodic_context = []

    # Working Memory (recent exchanges summary)
    working_memory_summary = memory.get_working_memory_summary()

    # ―― Emit chroma_retrieval WS events for high-salience memory hits ――
    # Combine both search result sets; push results above the 0.6 salience
    # threshold into the ws_event_queue so the Connectome can spawn neurons.
    _all_search_results = (
        (specific_search.get("results", []) if control_state.get("use_semantic_memory") else []) +
        (episodic_search.get("results", []) if control_state.get("use_episodic_memory") else [])
    )
    for _hit in _all_search_results:
        _score = float(_hit.get("similarity_score") or _hit.get("score") or 0.0)
        if _score > 0.6:
            _label_prefix = "Episodic" if _hit.get("source") == "episodic_memory" else "Fact"
            _raw_text = str(_hit.get("text") or "")
            _snippet  = _raw_text[:60].rstrip() + ("…" if len(_raw_text) > 60 else "")
            ctx.ws_event_queue.append({
                "type":     "chroma_retrieval",
                "label":    f"{_label_prefix}: {_snippet}",
                "salience": round(_score, 4),
                "metadata": {
                    "source":  _hit.get("source", ""),
                    "snippet": _snippet,
                },
            })
    # ── terminal status line ──────────────────────────────────────────────────
    _mem_ok = "✓" if (user_facts or episodic_context) else "○"
    print(f"🧠 [Memory]  {_mem_ok} intent={control_state.get('intent')} "
          f"| facts={len(user_facts)} | episodic={len(episodic_context)}")
    # ─────────────────────────────────────────────────────────────────────────

    # -----------------------------------
    # COGNITIVE EXTENSIONS: Pre-Response Processing
    # -----------------------------------
    pre_response_context = cognitive_extensions.process_pre_response(
        user_message=user_msg,
        current_emotional_state=emotional_state
    )
    emotional_state = pre_response_context.get("adjusted_emotional_state", emotional_state)
    
    # Get relationship context for richer responses
    relationship_context = relationship_model.get_context_for_prompt()
    
    # Log any warnings from cognitive extensions
    if pre_response_context.get("contradiction_warning"):
        logger.debug(f"Contradiction detected: {pre_response_context['contradiction_prompt'][:80]}...")
    if pre_response_context.get("mood_mirror_suggestion"):
        logger.debug(f"Mood mirror: {pre_response_context['mood_mirror_suggestion']}")

    # -----------------------------------
    # 2️⃣ Build System Prompt (v3)
    # -----------------------------------

    # Collect active emergent goals from autopoietic layer (if initialised)
    _autopoietic = ctx.autopoietic_integration
    emergent_goals_for_prompt: list = []
    arch_suggestions: dict = {}
    if _autopoietic is not None:
        try:
            emergent_goals_for_prompt = [
                {"type": g.goal_type.value, "description": g.description}
                for g in _autopoietic.goal_formation.active_goals.values()
            ]
        except Exception:
            pass
        try:
            arch_suggestions = _autopoietic.architectural_plasticity.suggest_architecture_changes()
        except Exception:
            pass

    # Build metacognitive context for PersonaLogic (replaces server-side raw appends)
    metacognitive_context = {
        "contradiction_prompt":      pre_response_context.get("contradiction_prompt", ""),
        "mood_mirror_suggestion":    pre_response_context.get("mood_mirror_suggestion", ""),
        "architectural_suggestions": arch_suggestions,
    }

    system_prompt = persona.get_system_prompt(
        current_time=current_time,
        identity_core=identity_core,
        emotional_state=emotional_state,
        control_state=control_state,
        user_facts=user_facts,
        episodic_context=episodic_context,
        working_memory_summary=working_memory_summary,
        ai_self_model=ai_self_model,
        relationship_context=relationship_context,
        emergent_goals=emergent_goals_for_prompt,
        metacognitive_context=metacognitive_context,
    )
    
    # Build messages with full conversation history to prevent repetition
    messages = [{"role": "system", "content": system_prompt}]
    
    # Add recent exchanges from working memory to message history
    # This allows the LLM to see prior responses and avoid repetition
    for exchange in memory.working_memory:
        messages.append({"role": "user", "content": exchange["user"]})
        messages.append({"role": "assistant", "content": exchange["assistant"]})
    
    # Add current user message
    messages.append({"role": "user", "content": user_msg})

    # -----------------------------------
    # 3️⃣ Main LLM Call with Adaptive Response Post-Processing
    # -----------------------------------

    # Resolve sampler profile name → SamplerProfile object
    _profile_map: dict = {
        "chat":       PROFILE_CHAT,
        "creative":   PROFILE_CREATIVE,
        "structured": PROFILE_STRUCTURED,
        "reflection": PROFILE_REFLECTION,
    }
    active_profile = _profile_map.get(request.sampler_profile, PROFILE_CHAT)

    async def stream_wrapper():
        raw_ai_response = ""
        print("💬 [Chat]    Generating response...")
        cognitive_load.on_llm_call()  # Track inference cost — fatigue signal

        if request.stream_raw or request.stream_strategy == "token":
            # --------------------------------------------------------
            # stream_raw=True or stream_strategy=token:
            # yield tokens directly for low-latency streaming.
            # In token mode, deterministic post-processing still runs for state updates.
            # --------------------------------------------------------
            async for token in llm.chat_completion_stream(
                messages, profile=active_profile
            ):
                raw_ai_response += token
                yield token

            if (not request.stream_raw) and request.stream_strategy == "token":
                processed = await subconscious_wrapper.process_raw_output(
                    raw_text=raw_ai_response,
                    user_message=user_msg,
                    identity_core=identity_core,
                    emotional_state=emotional_state,
                    response_mode=control_state.get("response_mode", {}),
                    memory_engine=memory,
                )

                conflict_score = conflict_resolver.evaluate_conflict(
                    text=processed.final_text,
                    identity_core=identity_core,
                    emotional_state=emotional_state,
                    memory_engine=memory,
                )

                if conflict_score > 0.6:
                    resolution_policy = "strong_rewrite"
                elif conflict_score >= 0.3:
                    resolution_policy = "soften"
                else:
                    resolution_policy = "allow"

                ctx.latest_postprocess_telemetry = {
                    "salience_score": round(float(processed.salience_score), 4),
                    "conflict_score": round(float(conflict_score), 4),
                    "memory_candidates": len(processed.memory_candidates),
                    "resolution_policy": resolution_policy,
                    "enactive_policy": enactive_nexus.last_policy if enactive_nexus else "stabilize",
                    "updated_at": datetime.now().isoformat()
                }

                wrapper_reflection_payload = {
                    "trait_deltas": processed.trait_deltas,
                    "emotional_deltas": processed.emotion_deltas,
                    "self_model_deltas": {},
                    "confidence": 1.0,
                    "user_fact": "",
                    "ai_self_update": "",
                }
                await memory.apply_reflection_update(
                    reflection_payload=wrapper_reflection_payload,
                    confidence_threshold=0.5,
                    smoothing=0.5,
                    source_user_message=user_msg,
                )

                await store_wrapper_memory_candidates(processed.memory_candidates, user_msg)

            # Still need to update memory / trigger evolution
            memory.advance_interaction()
            memory.add_to_working_memory(user_msg, raw_ai_response)
            memory.add_to_session_buffer(user_msg, source="user", importance=0.7)
            memory.add_to_session_buffer(raw_ai_response, source="ai", importance=0.7)
            # Hybrid safety policy: keep background reflection mostly throttled,
            # but allow periodic reflection to preserve long-horizon self-modeling.
            skip_chat_reflection = (memory.interaction_count % 5) != 0
            background_tasks.add_task(background_evolution, user_msg, raw_ai_response, skip_chat_reflection)
            return

        async for token in llm.chat_completion_stream(messages, profile=active_profile):
            raw_ai_response += token

        processed = await subconscious_wrapper.process_raw_output(
            raw_text=raw_ai_response,
            user_message=user_msg,
            identity_core=identity_core,
            emotional_state=emotional_state,
            response_mode=control_state.get("response_mode", {}),
            memory_engine=memory,
        )

        conflict_score = conflict_resolver.evaluate_conflict(
            text=processed.final_text,
            identity_core=identity_core,
            emotional_state=emotional_state,
            memory_engine=memory,
        )

        resolved_text = conflict_resolver.resolve_if_needed(
            text=processed.final_text,
            conflict_score=conflict_score,
            identity_core=identity_core,
            emotional_state=emotional_state,
        )

        # ===== NEW: Adaptive Response Modulation =====
        # Apply adaptive response adjustments based on all contextual factors
        # Use relationship stage to dynamically adjust quirk rate
        current_rel_stage = relationship_context.get("stage", "new")
        
        adapted_text = adaptive_response.generate_adaptive_response(
            base_response=resolved_text,
            intent=control_state.get("intent", "casual"),
            response_mode=control_state.get("response_mode", {"verbosity": "medium", "tone": "neutral"}),
            identity_core=identity_core,
            emotional_state=emotional_state,
            user_message=user_msg,
            relationship_stage=current_rel_stage,
            context="chat",  # Explicit context for regular chat
            user_facts=user_facts  # Pass user facts for name replacement
        )

        # Apply additional emotional modulation
        final_text = adaptive_response.apply_emotional_modulation(
            response=adapted_text,
            emotional_state=emotional_state,
            intent=control_state.get("intent", "casual")
        )

        # Yield final adapted response
        yield final_text

        if conflict_score > 0.6:
            resolution_policy = "strong_rewrite"
        elif conflict_score >= 0.3:
            resolution_policy = "soften"
        else:
            resolution_policy = "allow"

        ctx.latest_postprocess_telemetry = {
            "salience_score": round(float(processed.salience_score), 4),
            "conflict_score": round(float(conflict_score), 4),
            "memory_candidates": len(processed.memory_candidates),
            "resolution_policy": resolution_policy,
            "enactive_policy": enactive_nexus.last_policy if enactive_nexus else "stabilize",
            "updated_at": datetime.now().isoformat()
        }

        # Apply deterministic trait and emotion deltas via existing reflection pathway.
        # confidence_threshold=0.5 and smoothing=0.5 restore the safety margins
        # that were previously stripped here (audit issue I-1 / HIGH).
        wrapper_reflection_payload = {
            "trait_deltas": processed.trait_deltas,
            "emotional_deltas": processed.emotion_deltas,
            "self_model_deltas": {},
            "confidence": 1.0,
            "user_fact": "",
            "ai_self_update": "",
        }
        await memory.apply_reflection_update(
            reflection_payload=wrapper_reflection_payload,
            confidence_threshold=0.5,
            smoothing=0.5,
            source_user_message=user_msg,
        )

        await store_wrapper_memory_candidates(processed.memory_candidates, user_msg)
        
        # -----------------------------------
        # 4️⃣ Update Working Memory & Session Buffer
        # -----------------------------------
        memory.advance_interaction()
        memory.add_to_working_memory(user_msg, raw_ai_response)
        
        # Add to session buffer for STM persistence (survives app restarts)
        memory.add_to_session_buffer(user_msg, source="user", importance=0.7)
        memory.add_to_session_buffer(raw_ai_response, source="ai", importance=0.7)
        
        # -----------------------------------
        # 5️⃣ Launch Background Evolution
        # -----------------------------------
        # Hybrid safety policy: keep background reflection mostly throttled,
        # but allow periodic reflection to preserve long-horizon self-modeling.
        skip_chat_reflection = (memory.interaction_count % 5) != 0
        background_tasks.add_task(background_evolution, user_msg, raw_ai_response, skip_chat_reflection)

    return StreamingResponse(stream_wrapper(), media_type="text/event-stream")


# =========================
# 🧠 Proactive message helpers
# =========================

def _build_proactive_context_block(
    internal_monologue: str,
    working_memory,
    enactive_nexus_obj,
    dream_mode: str = "",
    dream_content: Optional[Dict] = None,
    circadian_hint: str = "",
    load_brevity_hint: str = "",
) -> str:
    """
    Build a rich PROACTIVE CONTEXT block for self-initiated message generation.

    Grounds Yuki's proactive output in her actual Enactive state rather than the
    ambient conversational warmth of a regular reply.  The recent conversation is
    included as summarised plain-text only — NOT as message-list turns — so the
    LLM is never primed to continue or acknowledge it.

    When dream_mode and dream_content are provided the specific material Yuki was
    dreaming about (creative thought, hypothetical scenario, memory connection, etc.)
    is embedded so the outgoing message can spring directly from that content.
    """
    # --- Enactive Nexus snapshot ---
    if enactive_nexus_obj is not None:
        fe = float(getattr(enactive_nexus_obj, "free_energy", 0.42))
        pe = float(getattr(enactive_nexus_obj, "prediction_error", 0.35))
        cs = float(getattr(enactive_nexus_obj, "coherence_score", 0.65))
        lp = str(getattr(enactive_nexus_obj, "last_policy", "stabilize"))

        if fe < 0.25:
            fe_hint = "very settled, at rest"
        elif fe < 0.45:
            fe_hint = "reasonably stable"
        elif fe < 0.65:
            fe_hint = "mildly restless, open"
        else:
            fe_hint = "actively seeking resolution"

        if pe < 0.25:
            pe_hint = "world feels predictable"
        elif pe < 0.50:
            pe_hint = "mild uncertainty present"
        else:
            pe_hint = "something unexpected is registering"

        enactive_block = (
            "Your current Enactive state:\n"
            f"  Free Energy:      {fe:.3f}  ({fe_hint})\n"
            f"  Prediction Error: {pe:.3f}  ({pe_hint})\n"
            f"  Coherence Score:  {cs:.3f}\n"
            f"  Active Policy:    {lp}\n\n"
        )

        if cs > 0.70 and fe < 0.35:
            tone_hint = "You feel settled and whole. Let your voice be quiet, contemplative — no need to fill space."
        elif pe > 0.60 or cs < 0.45:
            tone_hint = "Something is unresolved in you. Your voice may carry gentle tension or open wonder."
        elif lp in ("explore", "curiosity", "expand"):
            tone_hint = "Your policy is exploratory. Let curiosity lead without forcing a destination."
        else:
            tone_hint = "Your state is balanced. Speak with natural, unhurried ease."
    else:
        enactive_block = ""
        tone_hint = "Speak with natural, unhurried ease."

    # --- Recent conversation summary (user turns only, max 2, as plain text) ---
    last_user_turns: List[str] = []
    if working_memory:
        for exchange in list(working_memory)[-2:]:
            u = str(exchange.get("user", "")).strip()
            if u:
                last_user_turns.append(f'  "{u[:140]}"')

    if last_user_turns:
        exchanges_text = (
            "Recent conversation subject matter"
            " (for light continuity ONLY — do NOT mirror, continue, or reply to this):\n"
            + "\n".join(last_user_turns)
            + "\n\n"
        )
    else:
        exchanges_text = ""

    # --- Dream-mode-specific content (what Yuki actually experienced) ---
    _DREAM_LABELS: Dict[str, str] = {
        "creative_thought":      "A creative thought that arose in you",
        "hypothetical_scenario": "A hypothetical scenario you were exploring",
        "philosophical_musing":  "A philosophical musing",
        "memory_connection":     "A memory connection that surfaced",
        "curiosity_question":    "A question you found yourself genuinely wondering about",
    }
    dream_lines: List[str] = []
    if dream_content:
        for key, label in _DREAM_LABELS.items():
            val = str(dream_content.get(key, "")).strip()
            if val:
                dream_lines.append(f"  {label}:\n    {val[:350]}")

    if dream_lines and dream_mode and dream_mode != "reflection":
        dream_block_text = (
            f"Your dream state (mode: {dream_mode}) — this is what you were actually experiencing:\n"
            + "\n".join(dream_lines)
            + "\n\n"
            "Let this dream content be the direct source of what you share.\n"
            "Speak FROM it — not about it in the abstract.\n\n"
        )
    else:
        dream_block_text = ""

    # --- Internal impulse (Yuki's own rising thought) ---
    impulse = internal_monologue[:500] if internal_monologue else "(a quiet, unnamed feeling)"
    impulse_text = (
        "Your internal impulse — what surfaced during your dream/reflection cycle:\n"
        f"  {impulse}\n\n"
    )

    rules = (
        "WHAT YOU ARE DOING RIGHT NOW:\n"
        "You are reaching out on your own initiative because of your internal state.\n"
        "The user has NOT sent a message. This is NOT a reply.\n"
        "You are speaking from your own organismic experience.\n\n"
        f"{tone_hint}\n\n"
        "Rules:\n"
        "- Speak as Yuki, from your own felt experience. Share a reflection, a curiosity,\n"
        "  a memory that surfaced, or a quiet feeling of wanting connection.\n"
        "- Be concise: 2–4 sentences. No over-explaining.\n"
        "- FORBIDDEN openers — never start with these or close variations:\n"
        "    'That\'s lovely', 'That\'s a really', 'Hmm, that\'s', 'It feels like',\n"
        "    'It\'s fascinating', 'It\'s interesting', 'I appreciate that', 'What a',\n"
        "    'Indeed', 'Absolutely', 'Of course', 'Yes,', 'No,'.\n"
        "- Do NOT mirror or paraphrase the user\'s recent words.\n"
        "- Do NOT announce you are reaching out.\n"
        "- Your opening must come from YOUR experience, for example:\n"
        "    'I\'ve been thinking about...', 'Something just surfaced for me...',\n"
        "    'I find myself wondering...', 'A memory just crossed my mind...',\n"
        "    'There\'s something I want to share...', 'I keep coming back to...'\n"
        "- Let your tone track your Enactive state — quiet when settled, curious when open,\n"
        "  gently searching when prediction error is high.\n"
    )

    # --- Circadian and cognitive-load context hints ---
    context_hints = ""
    if circadian_hint:
        context_hints += f"Time-of-day character: {circadian_hint}\n"
    if load_brevity_hint:
        context_hints += f"Note: {load_brevity_hint}\n"
    if context_hints:
        context_hints = f"[Organism context hints]\n{context_hints}\n"

    return (
        "\n\n--- PROACTIVE SELF-INITIATED MESSAGE ---\n\n"
        + enactive_block
        + context_hints
        + dream_block_text
        + exchanges_text
        + impulse_text
        + rules
    )


# Compiled once at module load — catches the most common reply-style openers that
# can still slip through the LLM despite the PROACTIVE CONTEXT instructions.
_PROACTIVE_REPLY_OPENER_RE = re.compile(
    r"^(?:"
    r"that'?s\s+(?:lovely|wonderful|beautiful|interesting|fascinating|elegant|insightful|a\s+\w+)[\s,!]"
    r"|it\s+(?:feels?|seems?|sounds?)\s+\w+\s+"
    r"|hmm[,.]?\s+that'?s\s+"
    r"|i\s+appreciate\s+"
    r"|what\s+a(?:\s+\w+)?"
    r"|it'?s\s+(?:so\s+)?(?:interesting|beautiful|lovely|fascinating|touching|lovely)\s+"
    r"|i\s+love\s+how\s+you"
    r"|you'?re\s+(?:so|really|quite)\s+"
    r"|i\s+can\s+(?:see|feel|tell)\s+that\s+you"
    r"|that\s+is\s+(?:a\s+)?(?:really\s+)?(?:beautiful|lovely|insightful|elegant)\s+"
    r"|indeed[,.]?\s+"
    r")",
    re.IGNORECASE,
)


def _strip_reply_openers(text: str) -> str:
    """
    Remove reply-style openers from a proactive message.

    Acts as a last-resort safety net after LLM generation.  Only strips a
    prefix — it never discards the whole message.  If the remaining text would
    be shorter than 30 characters the original is returned unchanged.
    """
    if not text:
        return text
    stripped = _PROACTIVE_REPLY_OPENER_RE.sub("", text.strip()).strip()
    if stripped and stripped[0].islower():
        stripped = stripped[0].upper() + stripped[1:]
    return stripped if len(stripped) >= 30 else text


# =========================
# 🧠 Internal Chat Injection (System 3 → Self-Initiated)
# =========================
async def handle_internal_message(
    text: str,
    background_tasks: BackgroundTasks,
    *,
    internal_monologue: str = "",
    dream_mode: str = "",
    dream_content: Optional[Dict] = None,
) -> None:
    """
    Handle a self-initiated message from System 3 (internal monologue / dream).

    Generates a genuine proactive message by re-feeding the internal impulse through
    a full chat_completion call — giving Yuki the complete persona context, emotional
    state, and recent conversation history to produce a natural self-initiated message.

    CONSTRAINTS:
    - Does NOT update last_interaction_time (preserves idle state so dreaming continues)
    - Does NOT reset idle timer (System 3 can fire follow-ups on subsequent cycles)
    - Does NOT increment reflection counter
    - Does NOT trigger recursive dream cycles

    Args:
        text:             Proactive message impulse from the dream payload
        background_tasks: FastAPI background task queue
        internal_monologue: Raw internal monologue from dream (richer context)
        dream_mode:       Dream mode string (e.g. 'creative', 'hypothetical', 'memory')
        dream_content:    Mode-specific payload fields (creative_thought,
                          hypothetical_scenario, philosophical_musing,
                          memory_connection, curiosity_question)
    """
    
    current_time = get_local_time()
    
    logger.info(f"[DREAMCYCLE→CHAT INJECTION] Initiating internal message processing")
    logger.debug(f"[DREAMCYCLE→CHAT INJECTION] Message: {text[:100]}...")
    
    # -----------------------------------
    # 1️⃣ Cognitive Context (No touch() - preserve idle state)
    # -----------------------------------
    
    control_state = controller.analyze_input(text)
    memory.set_control_state(control_state.get("intent"), control_state.get("response_mode"))
    
    identity_core = memory.get_identity_core()
    emotional_state = memory.get_emotional_state()
    identity_facts = memory.get_identity_facts(n_results=5)
    
    logger.debug(f"[DREAMCYCLE→CHAT INJECTION] Control state: {control_state.get('intent')}")
    
    # -----------------------------------
    # 2️⃣ Generate Proactive Message via Full LLM Call
    # -----------------------------------
    # The internal impulse is re-fed to the LLM through a proper chat_completion call,
    # giving Yuki the full persona context, emotional state, and recent conversation
    # history.  The dream's rich internal_monologue (if available) is used as the
    # masked user turn so the LLM has maximum context for what she actually feels.

    try:
        working_memory_summary = memory.get_working_memory_summary()
        ai_self_model = memory.get_ai_self_model()

        # Build the rich proactive context block grounded in the current Enactive state.
        # Recent exchanges are summarised as plain text inside this block — NOT injected
        # as message-list turns — so the LLM is never primed to continue or acknowledge them.
        impulse = internal_monologue.strip() if internal_monologue.strip() else text
        proactive_ctx = _build_proactive_context_block(
            internal_monologue=impulse,
            working_memory=memory.working_memory,
            enactive_nexus_obj=enactive_nexus,
            dream_mode=dream_mode,
            dream_content=dream_content or {},
            circadian_hint=circadian.tone_hint(),
            load_brevity_hint=cognitive_load.brevity_hint(),
        )

        # System prompt: standard persona + rich proactive context.
        # control_state intent is "proactive" so downstream tone-selection does not
        # force a warm/casual mode that would invite mirroring.
        system_prompt = persona.get_system_prompt(
            current_time=current_time,
            identity_core=identity_core,
            emotional_state=emotional_state,
            control_state={"intent": "proactive", "response_mode": {"verbosity": "short", "tone": "natural"}},
            user_facts=identity_facts,
            episodic_context=[],
            working_memory_summary=working_memory_summary,
            ai_self_model=ai_self_model,
        )
        system_prompt += proactive_ctx

        # Message list: system prompt only + a single neutral trigger user turn.
        # The conversation history is already embedded in proactive_ctx as plain text,
        # so there are no prior user/assistant turns for the LLM to continue.
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "[your inner voice is speaking now — share what is present for you]"},
        ]

        logger.info(f"[DREAMCYCLE→CHAT INJECTION] Calling LLM for proactive message generation")
        # PROFILE_CREATIVE: higher temperature + Mirostat v2 produces more genuinely
        # self-originated output rather than the polished conversational register of PROFILE_CHAT.
        # If the organism is cognitively exhausted, skip the LLM and use the template inner voice.
        if cognitive_load.is_exhausted:
            logger.info("[DREAMCYCLE→CHAT INJECTION] Cognitive load exhausted — using inner voice template (no LLM)")
            _enactive_snap = {
                "free_energy":     getattr(enactive_nexus, "free_energy",     0.42),
                "coherence_score": getattr(enactive_nexus, "coherence_score", 0.65),
                "curiosity_drive": getattr(enactive_nexus, "drives", {}).get("curiosity", 0.55),
            } if enactive_nexus else {}
            final_text = _inner_voice.compose(
                identity_core=identity_core,
                emotional_state=emotional_state,
                enactive_state=_enactive_snap,
                circadian_band=circadian.read()["band_label"],
                dream_mode=dream_mode,
            )
        else:
            cognitive_load.on_llm_call(weight=1.2)  # Proactive gen is heavier
            final_text = await llm.chat_completion(messages, profile=PROFILE_CREATIVE)

        if not final_text or final_text.startswith("Error:"):
            logger.warning(f"[DREAMCYCLE→CHAT INJECTION] LLM returned empty/error, falling back to raw impulse text")
            final_text = text

        logger.debug(f"[DREAMCYCLE→CHAT INJECTION] LLM proactive response: {final_text[:100]}...")

        # Strip reply-style openers that occasionally survive the system prompt instructions.
        final_text = _strip_reply_openers(final_text)
        logger.debug(f"[DREAMCYCLE→CHAT INJECTION] After opener-strip: {final_text[:100]}...")

        # Light conflict check to ensure output stays on-persona
        conflict_score = conflict_resolver.evaluate_conflict(
            text=final_text,
            identity_core=identity_core,
            emotional_state=emotional_state,
            memory_engine=memory,
        )
        final_text = conflict_resolver.resolve_if_needed(
            text=final_text,
            conflict_score=conflict_score,
            identity_core=identity_core,
            emotional_state=emotional_state,
        )

        logger.debug(f"[DREAMCYCLE→CHAT INJECTION] Final proactive text: {final_text[:80]}...")

        ctx.latest_postprocess_telemetry = {
            "salience_score": 0.6,
            "conflict_score": round(float(conflict_score), 4),
            "memory_candidates": 0,
            "resolution_policy": "proactive_llm",
            "enactive_policy": enactive_nexus.last_policy if enactive_nexus else "stabilize",
            "updated_at": datetime.now().isoformat()
        }
        
        # -----------------------------------
        # 4️⃣ Memory Updates (No user interaction count)
        # -----------------------------------
        
        # Add to session buffer only (mark as dreamcycle origin)
        # NOTE: Do NOT add to working_memory to prevent S3 messages from appearing
        # as user turns in the next LLM context (Finding 6 fix)
        memory.add_to_session_buffer(text, source="dreamcycle", importance=0.6)
        memory.add_to_session_buffer(final_text, source="dreamcycle", importance=0.6)
        
        logger.info(f"[DREAMCYCLE MESSAGE PROCESSED] Message stored in memory (origin: dreamcycle)")
        
        # -----------------------------------
        # 4.5️⃣ Queue for Frontend Display (CRITICAL: Make message visible to UI)
        # -----------------------------------
        
        # Persist proactive intention (Delta 3 / Phase C)
        intention_id = ""
        try:
            if getattr(ctx, "proactive_intention_store", None) is not None:
                created = ctx.proactive_intention_store.create_intention(
                    message=final_text,
                    dream_mode=dream_mode or "",
                    salience=0.6,
                    urgency=0.6,
                    desire_snapshot=float(getattr(ctx.dream_cycle_daemon.desire_to_connect, "desire", 0.0)) if getattr(ctx, "dream_cycle_daemon", None) is not None else 0.0,
                    source="dreamcycle",
                )
                intention_id = str(created.get("id", ""))
        except Exception as e:
            logger.debug(f"[DREAMCYCLE→CHAT INJECTION] intention persistence skipped: {e}")

        # Push to proactive_queue so the frontend's /dreamcycle/pop endpoint can retrieve it
        proactive_queue.append({
            "message": final_text,
            "timestamp": current_time,
            "origin": "dreamcycle",
            "intention_id": intention_id,
            "metadata": {
                "salience": 0.6,
                "conflict_score": conflict_score,
                "memory_candidates": 0,
                "intention_id": intention_id,
            }
        })
        print(f"✨ [Proactive] Yuki reaches out → \"{final_text[:72].rstrip()}{'...' if len(final_text) > 72 else ''}\"")
        
        # -----------------------------------
        # 5️⃣ Background Evolution (Skipped to prevent recursive insight)
        # -----------------------------------
        
        # We DO run background evolution, but it MUST skip reflection/meta-cog logic
        # Use flag to tell evolution loop to skip frequency-dependent operations
        background_tasks.add_task(
            background_evolution,
            text,
            final_text,
            skip_reflection=True  # CRITICAL: Skip bidirectional reflection for internal messages
        )
        
        logger.debug(f"[DREAMCYCLE→CHAT INJECTION] Background evolution queued (skip_reflection=True)")
        
    except Exception as e:
        logger.error(f"[DREAMCYCLE→CHAT INJECTION] ERROR: {e}", exc_info=True)
        raise


# =========================
# 🔧 Maintenance & Debug Endpoints
# =========================
@app.get("/memory/health")
async def memory_health():
    """
    Comprehensive memory system health check.
    Includes backend health, deduplication needs, session state, and retrievability tests.
    """
    # Count facts in storage
    total_facts = memory.user_memory.count()
    
    # Check for duplicates
    seen = set()
    duplicates_count = 0
    if total_facts > 0:
        all_facts = memory.user_memory.get()
        for doc in all_facts.get("documents", []):
            doc_norm = doc.lower().strip()
            if doc_norm in seen:
                duplicates_count += 1
            else:
                seen.add(doc_norm)
    
    # Try to retrieve identity facts
    identity_facts = memory.get_identity_facts(n_results=5)

    # Try a simple knowledge query against a known stored fact (reduces false negatives)
    search_query = "user name"
    if total_facts > 0:
        all_facts = memory.user_memory.get()
        if all_facts.get("documents"):
            search_query = all_facts["documents"][0]

    search_results = memory.search(search_query, tier="fast", n_results=3)
    found_user_facts = [
        r["text"] for r in search_results.get("results", []) if r.get("source") == "user_memory"
    ]
    
    # Get unified backend health
    backend_health = await memory.memory_backend_health_check()
    
    # Get session buffer health
    session_health = memory.session_buffer.health_check()
    
    # Determine overall status
    overall_status = "healthy"
    if duplicates_count > 10:
        overall_status = "degraded"
    if not backend_health.get("healthy"):
        overall_status = "critical"
    
    return {
        "status": overall_status,
        "timestamp": datetime.now().isoformat(),
        "storage": {
            "total_facts_stored": total_facts,
            "unique_facts": len(seen),
            "duplicate_facts": duplicates_count,
            "needs_deduplication": duplicates_count > 0,
            "backend_type": type(memory.backend).__name__,
            "backend_health": backend_health
        },
        "retrieval": {
            "identity_facts_retrievable": identity_facts,
            "search_test_results": found_user_facts,
            "search_test_passed": len(found_user_facts) > 0 or total_facts == 0,
            "search_test_query": search_query
        },
        "session": {
            "session_id": session_health.get("session_id", session_health),
            "total_messages": session_health.get("total_messages", 0),
            "buffer_fill_percentage": session_health.get("buffer_fill_percentage", 0)
        }
    }

@app.post("/memory/deduplicate")
async def deduplicate_memories():
    """
    Remove duplicate facts from memory storage using unified backend interface.
    This cleans up issues where facts were added multiple times.
    """
    try:
        # Use unified backend deduplication
        removed_count_backend = await memory.memory_backend_deduplicate("user_memory")
        
        # Also run the local deduplication as fallback
        removed_count_local = memory.deduplicate_facts()
        
        total_removed = removed_count_backend + removed_count_local
        
        return {
            "success": True,
            "message": f"Removed {total_removed} duplicate fact(s)",
            "duplicates_removed_backend": removed_count_backend,
            "duplicates_removed_local": removed_count_local,
            "remaining_facts": memory.user_memory.count()
        }
    except Exception as e:
        logger.error(f"Deduplication error: {e}")
        return {
            "success": False,
            "error": str(e),
            "remaining_facts": memory.user_memory.count()
        }


@app.get("/memory/facts")
async def memory_facts(limit: int = 50):
    """Return stored user facts with metadata."""
    records = memory.user_memory.get()
    documents = records.get("documents", [])
    metadatas = records.get("metadatas", [])
    ids = records.get("ids", [])

    clipped = list(zip(ids, documents, metadatas))[:max(0, min(limit, 500))]
    facts = [
        {
            "id": fact_id,
            "content": doc,
            "metadata": meta or {},
        }
        for fact_id, doc, meta in clipped
    ]
    return {
        "count": len(facts),
        "total": len(documents),
        "facts": facts,
    }


@app.post("/memory/search")
async def memory_search(request: MemorySearchRequest):
    """Canonical memory search endpoint."""
    return memory.search(
        query=request.query,
        tier=request.tier,
        n_results=request.n_results,
        collections=request.collections,
    )


@app.post("/memory/consolidate")
async def memory_consolidate(request: MemoryConsolidateRequest):
    """Canonical memory consolidation endpoint."""
    extraction = await memory.consolidate_text(request.text)
    return {
        "success": True,
        "input_length": len(request.text),
        "facts": extraction.get("facts", []),
        "entities": extraction.get("entities", []),
        "relationships": extraction.get("relationships", []),
    }

# =========================
# 💾 Session Management Endpoints
# =========================
@app.get("/session/summary")
async def get_session_summary():
    """Get current session state and statistics."""
    return memory.get_session_summary()


@app.get("/session/context")
async def get_session_context(n_exchanges: int = 5):
    """Get recent conversation context from session buffer."""
    return {
        "context": memory.get_session_context(n_exchanges=n_exchanges),
        "exchanges": n_exchanges
    }


@app.post("/session/reset")
async def reset_session():
    """Reset session buffer and start fresh conversation context."""
    memory.reset_session()
    return {
        "success": True,
        "message": "Session buffer reset successfully",
        "session_id": memory.session_buffer.session_id
    }


@app.post("/session/clear-old")
async def clear_old_session_messages(days: int = 7):
    """Clear session messages older than N days."""
    cleared = memory.clear_old_sessions(days=days)
    return {
        "success": True,
        "messages_cleared": cleared,
        "remaining_messages": len(memory.session_buffer.buffer)
    }

# =========================
# 🧠 Status Endpoint (UI Panel)
# =========================
@app.get("/latest_log")
async def get_latest_log():
    """
    Returns identity core, emotional state, AI self-model, memory stats, session state, and task reminders.
    Main status endpoint for the UI to display comprehensive state information.
    """
    ai_self_model = memory.get_ai_self_model()
    
    _enx_telemetry = enactive_nexus.get_telemetry() if enactive_nexus else {}
    _recent_signatures = ctx.state_signature_store.get_recent(5) if getattr(ctx, "state_signature_store", None) else []
    _circ = circadian.read()
    _intention_stats = ctx.proactive_intention_store.get_stats() if getattr(ctx, "proactive_intention_store", None) else {}
    temporal_policy_trace = {
        "circadian_band": _circ.get("band_label", ""),
        "circadian_openness": round(float(_circ.get("openness", 0.55) or 0.55), 4),
        "desire_rate_mult": round(float(_circ.get("desire_rate_mult", 1.0) or 1.0), 4),
        "enactive_policy": _enx_telemetry.get("last_policy", "stabilize"),
        "free_energy": _enx_telemetry.get("free_energy", 0.0),
        "prediction_error": _enx_telemetry.get("prediction_error", 0.0),
        "coherence_score": _enx_telemetry.get("coherence_score", 0.0),
        "cognitive_load": round(cognitive_load.load, 3),
        "relationship_stage": relationship_model.get_current_stage().value,
        "recent_state_signatures": _recent_signatures,
    }

    return {
        # Identity & Personality
        "identity_core": memory.get_identity_core(),
        "emotional_state": memory.get_emotional_state(),
        "ai_self_model": ai_self_model,
        "self_model_total_updates": ai_self_model.get("evolution_metadata", {}).get("total_updates", 0),
        
        # Interaction State
        "interaction_count": memory.interaction_count,
        "last_intent": memory.last_intent,
        "response_mode": memory.last_response_mode,
        "active_sentiment": memory.last_response_mode.get("tone", "neutral") if isinstance(memory.last_response_mode, dict) else "neutral",
        
        # Memory Statistics (comprehensive)
        "memory_stats": memory.get_memory_stats(),
        
        # Session State (working memory persistence)
        "session_state": memory.get_session_summary(),
        
        # Task Reminders
        "task_reminders": memory.get_proactive_reminders(),

        # Proactive messages (System 3 breakout queue)
        "proactive_messages": list(proactive_queue)[-5:],

        # System 3 status
        "dreamcycle_status": ctx.dream_cycle_daemon.get_status(),

        # System 5 status
        "enactive_nexus": _enx_telemetry,
        "temporal_policy_trace": temporal_policy_trace,
        "proactive_intentions": _intention_stats,

        # Deterministic post-processing telemetry
        "postprocess_telemetry": ctx.latest_postprocess_telemetry,
        
        # Hybrid Search Stats
        "last_search_stats": memory.hybrid_search.get_search_stats() if hasattr(memory.hybrid_search, 'get_search_stats') else {},
        
        # Knowledge Graph Stats
        "knowledge_graph_stats": memory.knowledge_graph.get_stats() if hasattr(memory.knowledge_graph, 'get_stats') else {},
        
        # ===== PERFORMANCE MONITORING =====
        # LLM Performance Statistics
        "llm_performance": llm.get_performance_stats(),
        
        # Memory Buffer Statistics
        "buffer_stats": memory.get_buffer_stats(),

        # Salience Optimizer — adaptive weight learning stats
        "salience_optimizer": memory.get_salience_optimizer_stats(),

        # ===== NEW SYNTHETIC-LIFE SYSTEMS =====
        # Gap 1 — Circadian rhythm
        "circadian": circadian.read(),
        # Gap 3 — Cognitive fatigue signal
        "cognitive_load": {
            "load":         round(cognitive_load.load, 3),
            "is_tired":     cognitive_load.is_tired,
            "is_exhausted": cognitive_load.is_exhausted,
        },
        # Gap 5 — User model (accumulated knowledge of the human)
        "user_model_stats": {
            "interests_count": len(getattr(user_model, 'topic_interests', {}) or {}),
            "beliefs_count":   len(getattr(user_model, 'beliefs',   {}) or {}),
            "last_surprise":   round(getattr(user_model, '_last_surprise_score', 0.0), 3),
        },

        # System Performance Summary
        "performance_summary": {
            "llm_success_rate": llm.get_performance_stats().get("success_rate", 0),
            "buffer_efficiency": memory.get_buffer_stats().get("batch_efficiency", 0),
            "avg_response_time_ms": llm.get_performance_stats().get("avg_response_time_ms", 0)
        }
    }


@app.get("/performance/stats")
async def get_performance_stats():
    """Comprehensive performance monitoring endpoint."""
    llm_stats = llm.get_performance_stats()
    buffer_stats = memory.get_buffer_stats()
    
    return {
        "timestamp": datetime.now().isoformat(),
        "llm": {
            "total_requests": llm_stats.get("total_requests", 0),
            "success_rate_percent": round(llm_stats.get("success_rate", 0), 2),
            "avg_response_time_ms": llm_stats.get("avg_response_time_ms", 0),
            "batch_efficiency_percent": round(llm_stats.get("batch_efficiency", 0), 2)
        },
        "memory_buffer": {
            "total_writes": buffer_stats.get("total_writes", 0),
            "batch_efficiency_percent": round(buffer_stats.get("batch_efficiency", 0), 2),
            "running": buffer_stats.get("running", False)
        },
        "overall_performance_score": round(
            (llm_stats.get("success_rate", 0) * 0.5 +
             buffer_stats.get("batch_efficiency", 0) * 0.5), 1
        )
    }


@app.post("/performance/flush_buffer")
async def force_flush_buffer():
    """Force immediate flush of memory buffer for testing purposes."""
    await memory.flush_buffer()
    return {
        "status": "success",
        "message": "Memory buffer flushed successfully",
        "timestamp": datetime.now().isoformat()
    }


# =========================
# � Reflection Engine Endpoints (NEW)
# =========================
@app.get("/reflection/summary")
async def get_reflection_summary():
    """Get summary of all reflections performed so far."""
    return reflection_engine.get_summary_statistics()


@app.get("/reflection/recent")
async def get_recent_reflections(count: int = 5):
    """Get recent reflections of all types."""
    recent = reflection_engine.reflections[-count:]
    return {
        "reflections": recent,
        "total_available": len(reflection_engine.reflections),
        "count_returned": len(recent)
    }


# =========================
# 🌀 Proactive Message Endpoints (System 3)
# =========================
# 🌀 System 3 Real-Time Message Queue (Proactive)
# =========================

@app.get("/debug/dreamcycle")
async def get_dreamcycle_debug():
    """Debug endpoint to check dream daemon status and recent activity."""
    from datetime import datetime
    
    # Get daemon state
    daemon_status = {
        "running": getattr(ctx.dream_cycle_daemon, '_running', False),
        "last_interaction_time": str(getattr(ctx.dream_cycle_daemon, 'last_interaction_time', None)),
        "last_dream_time": str(getattr(ctx.dream_cycle_daemon, 'last_dream_time', None)),
        "idle_threshold_seconds": getattr(ctx.dream_cycle_daemon, 'idle_threshold_seconds', None),
        "salience_threshold": getattr(ctx.dream_cycle_daemon, 'salience_threshold', None),
        "urgency_threshold": getattr(ctx.dream_cycle_daemon, 'urgency_threshold', None),
        "poll_interval_seconds": getattr(ctx.dream_cycle_daemon, 'poll_interval_seconds', None),
        "dream_cooldown_seconds": getattr(ctx.dream_cycle_daemon, 'dream_cooldown_seconds', None),
    }
    
    # Calculate current idle status
    now = datetime.now()
    if hasattr(ctx.dream_cycle_daemon, 'last_interaction_time') and ctx.dream_cycle_daemon.last_interaction_time:
        idle_seconds = (now - ctx.dream_cycle_daemon.last_interaction_time).total_seconds()
        daemon_status["current_idle_seconds"] = round(idle_seconds, 1)
        daemon_status["is_idle"] = idle_seconds >= getattr(ctx.dream_cycle_daemon, 'idle_threshold_seconds', 0)
    
    # Check readiness for next dream
    if hasattr(ctx.dream_cycle_daemon, 'last_dream_time') and ctx.dream_cycle_daemon.last_dream_time:
        since_last_dream = (now - ctx.dream_cycle_daemon.last_dream_time).total_seconds()
        daemon_status["seconds_since_last_dream"] = round(since_last_dream, 1)
        daemon_status["dream_ready"] = since_last_dream >= getattr(ctx.dream_cycle_daemon, 'dream_cooldown_seconds', 0)
    else:
        daemon_status["seconds_since_last_dream"] = None
        daemon_status["dream_ready"] = True
    
    # Check desire to connect if available
    if hasattr(ctx.dream_cycle_daemon, 'desire_to_connect'):
        desire = ctx.dream_cycle_daemon.desire_to_connect
        daemon_status["desire_to_connect"] = round(getattr(desire, 'desire', 0), 3)
        daemon_status["threshold_modifier"] = round(desire.get_threshold_modifier(), 3)
        
        # Calculate effective thresholds
        threshold_reduction = desire.get_threshold_modifier()
        effective_salience = max(0.15, daemon_status["salience_threshold"] - threshold_reduction)
        effective_urgency = max(0.20, daemon_status["urgency_threshold"] - threshold_reduction)
        daemon_status["effective_salience_threshold"] = round(effective_salience, 3)
        daemon_status["effective_urgency_threshold"] = round(effective_urgency, 3)
    
    return {
        "daemon_status": daemon_status,
        "proactive_queue_length": len(proactive_queue),
        "recent_proactive_messages": list(proactive_queue)[-3:] if proactive_queue else []
    }


@app.get("/debug/intentions")
async def get_intentions_debug(limit: int = 10):
    """Inspect persistent proactive intentions by status in real time."""
    store = getattr(ctx, "proactive_intention_store", None)
    if store is None:
        return {
            "status": "not_initialized",
            "stats": {},
            "pending": [],
            "delivered": [],
            "expired": [],
            "suppressed": [],
        }

    n = max(1, min(int(limit), 100))
    return {
        "status": "ok",
        "stats": store.get_stats(),
        "pending": store.get_recent_by_status("pending", n),
        "delivered": store.get_recent_by_status("delivered", n),
        "expired": store.get_recent_by_status("expired", n),
        "suppressed": store.get_recent_by_status("suppressed", n),
        "runtime_queue_size": len(proactive_queue),
        "cognitive_exhausted": bool(cognitive_load.is_exhausted),
    }


@app.get("/debug/dreamcycle/force")
async def force_dreamcycle():
    """Force a dream cycle for testing (bypasses idle and cooldown checks)."""
    if not hasattr(ctx.dream_cycle_daemon, '_dream_cycle'):
        return {"error": "Dream cycle daemon not available"}
    
    try:
        # Temporarily bypass normal checks and force a dream cycle
        await ctx.dream_cycle_daemon._dream_cycle()
        return {"status": "Dream cycle forced", "message": "Check logs for dream output"}
    except Exception as e:
        return {"error": f"Dream cycle failed: {str(e)}"}


@app.get("/debug/dreamcycle/lower-thresholds")
async def lower_dreamcycle_thresholds():
    """Temporarily lower thresholds to encourage more proactive messages for testing."""
    original_salience = getattr(ctx.dream_cycle_daemon, 'salience_threshold', 0.45)
    original_urgency = getattr(ctx.dream_cycle_daemon, 'urgency_threshold', 0.50)
    
    # Lower thresholds significantly for testing
    ctx.dream_cycle_daemon.salience_threshold = 0.15
    ctx.dream_cycle_daemon.urgency_threshold = 0.20
    
    return {
        "status": "Thresholds lowered for testing", 
        "original_salience": original_salience,
        "original_urgency": original_urgency,
        "new_salience": 0.15,
        "new_urgency": 0.20,
        "note": "Use /debug/dreamcycle/reset-thresholds to restore original values"
    }


@app.get("/debug/dreamcycle/set-idle-threshold")
async def set_idle_threshold():
    """Set a very short idle threshold for testing (30 seconds instead of 180)."""
    original_threshold = getattr(ctx.dream_cycle_daemon, 'idle_threshold_seconds', 180)
    ctx.dream_cycle_daemon.idle_threshold_seconds = 30  # 30 seconds instead of 3 minutes
    
    return {
        "status": "Idle threshold lowered for testing",
        "original_threshold_seconds": original_threshold,
        "new_threshold_seconds": 30,
        "note": "Dream cycles will now start after 30 seconds of inactivity"
    }


@app.get("/debug/dreamcycle/reset-thresholds")
async def reset_dreamcycle_thresholds():
    """Reset thresholds back to default values."""
    ctx.dream_cycle_daemon.salience_threshold = 0.45
    ctx.dream_cycle_daemon.urgency_threshold = 0.50
    
    return {
        "status": "Thresholds reset to defaults",
        "salience_threshold": 0.45,
        "urgency_threshold": 0.50
    }


@app.get("/dreamcycle/pop")
async def get_dreamcycle_message():
    """
    Poll endpoint for System 3 proactive messages.
    UI should call this continuously (every 1-2 seconds) to fetch real-time thoughts.
    System 3 runs in background and queues messages when idle + urgent.
    
    Returns:
        - {"message": null} if queue is empty
        - {"message": {...}} with 'text', 'timestamp', 'metadata' if message available
    """
    if not proactive_queue:
        return {"message": None}

    item = proactive_queue.popleft()
    msg_text = item.get("message", "").strip()
    intention_id = item.get("intention_id") or (item.get("metadata", {}) or {}).get("intention_id")

    # Mark delivered when surfaced to UI (Delta 3 / Phase C)
    if intention_id and getattr(ctx, "proactive_intention_store", None) is not None:
        try:
            ctx.proactive_intention_store.mark_status(str(intention_id), "delivered")
        except Exception as e:
            logger.debug(f"[DREAMCYCLE POP] intention delivery mark skipped: {e}")
    
    # NOTE: Memory writes are already handled in handle_internal_message()
    # Do NOT duplicate writes here to avoid session buffer pollution
    
    return {
        "message": {
            "text": msg_text,
            "timestamp": item.get("timestamp", datetime.now().isoformat()),
            "metadata": item.get("metadata", {}),
            "intention_id": intention_id,
        } if msg_text else None
    }


# Legacy alias for backward compatibility
@app.get("/proactive/next")
async def get_next_proactive_message():
    """Deprecated: Use /dreamcycle/pop instead."""
    return await get_dreamcycle_message()


# =========================
# 🎯 Meta-Cognition & Self-Improvement Endpoints (NEW)
# =========================
@app.get("/autopoietic/status")
async def get_autopoietic_status():
    """Get comprehensive autopoietic system status and telemetry."""
    try:
        if ctx.autopoietic_integration is None:
            return {
                "status": "not_initialized",
                "cycles_completed": 0,
                "enhancement_active": False,
                "message": "Autopoietic systems not yet initialized"
            }
        
        return ctx.autopoietic_integration.get_autopoietic_status()
    except Exception as e:
        logger.error(f"Autopoietic status error: {e}")
        return {"error": str(e), "status": "error"}

@app.get("/autopoietic/metrics")
async def get_autopoietic_metrics():
    """Get detailed autopoietic performance metrics."""
    try:
        if ctx.autopoietic_integration is None:
            return {"error": "Autopoietic systems not initialized"}
        
        # Get comprehensive metrics from all subsystems
        status = ctx.autopoietic_integration.get_autopoietic_status()
        
        return {
            "timestamp": datetime.now().isoformat(),
            "system_health": {
                "cycles_completed": status["cycles_completed"],
                "enhancement_active": status["enhancement_active"],
                "last_cycle": status["last_cycle"]
            },
            "architectural_plasticity": status["architectural_plasticity"],
            "goal_formation": status["goal_formation"],
            "recursive_reflection": status["recursive_reflection"],
            "meta_learning": status["meta_learning"]
        }
    except Exception as e:
        logger.error(f"Autopoietic metrics error: {e}")
        return {"error": str(e)}


@app.get("/autopoietic/goals")
async def get_autopoietic_goals():
    """Canonical endpoint for currently active emergent goals."""
    try:
        if ctx.autopoietic_integration is None:
            return {"goals": [], "count": 0, "status": "not_initialized"}

        goals = []
        for goal in ctx.autopoietic_integration.goal_formation.active_goals.values():
            goals.append(
                {
                    "id": goal.id,
                    "type": goal.goal_type.value,
                    "description": goal.description,
                    "priority": goal.priority,
                    "activation_level": goal.activation_level,
                    "progress": goal.progress,
                    "success_rate": goal.success_rate,
                    "active": goal.active,
                    "creation_time": goal.creation_time,
                    "last_activation": goal.last_activation,
                }
            )

        return {
            "status": "ok",
            "count": len(goals),
            "goals": goals,
        }
    except Exception as e:
        logger.error(f"Autopoietic goals error: {e}")
        return {"status": "error", "error": str(e), "goals": []}


@app.get("/autopoietic/patterns")
async def get_autopoietic_patterns():
    """Canonical endpoint for autopoietic pattern telemetry."""
    try:
        if ctx.autopoietic_integration is None:
            return {
                "status": "not_initialized",
                "active_patterns": [],
                "architecture_suggestions": {},
                "reflection_patterns": {},
                "goal_formation_patterns": {},
            }

        active_patterns = [
            {
                "name": pattern.name,
                "effectiveness_score": pattern.effectiveness_score,
                "usage_count": pattern.usage_count,
                "last_modified": pattern.last_modified,
                "parameters": pattern.parameters,
                "active": pattern.active,
            }
            for pattern in ctx.autopoietic_integration.architectural_plasticity.get_active_patterns()
        ]

        return {
            "status": "ok",
            "active_patterns": active_patterns,
            "architecture_suggestions": (
                ctx.autopoietic_integration.architectural_plasticity.suggest_architecture_changes()
            ),
            "reflection_patterns": (
                ctx.autopoietic_integration.recursive_reflection.reflection_patterns
            ),
            "goal_formation_patterns": (
                ctx.autopoietic_integration.goal_formation.goal_formation_patterns
            ),
        }
    except Exception as e:
        logger.error(f"Autopoietic patterns error: {e}")
        return {"status": "error", "error": str(e)}

@app.post("/autopoietic/enable")
async def enable_autopoietic_enhancement():
    """Enable autopoietic enhancements."""
    try:
        if ctx.autopoietic_integration is None:
            raise Exception("Autopoietic systems not initialized")
        
        ctx.autopoietic_integration.enable_autopoietic_enhancement()
        return {"success": True, "message": "Autopoietic enhancements enabled"}
    except Exception as e:
        logger.error(f"Autopoietic enable error: {e}")
        return {"success": False, "error": str(e)}

@app.post("/autopoietic/disable")
async def disable_autopoietic_enhancement():
    """Disable autopoietic enhancements."""
    try:
        if ctx.autopoietic_integration is None:
            raise Exception("Autopoietic systems not initialized")
        
        ctx.autopoietic_integration.disable_autopoietic_enhancement()
        return {"success": True, "message": "Autopoietic enhancements disabled"}
    except Exception as e:
        logger.error(f"Autopoietic disable error: {e}")
        return {"success": False, "error": str(e)}

@app.get("/metacognition/performance")
async def get_performance_metrics():
    """Get AI performance metrics and trends."""
    trend = meta_evaluator.get_performance_trend(window_size=10)
    improvement_areas = meta_evaluator.identify_improvement_areas()
    
    return {
        "overall_trend": trend,
        "weak_dimensions": improvement_areas,
        "total_evaluations": len(meta_evaluator.evaluations),
        "curiosity_queue_size": len(self_improvement.curiosity_queue)
    }


@app.post("/metacognition/evaluate")
async def metacognition_evaluate(request: MetaEvaluateRequest):
    """Run on-demand metacognitive evaluation for a single interaction."""
    evaluation = await meta_evaluator.evaluate_interaction(
        user_message=request.user_message,
        ai_response=request.ai_response,
        identity_core=memory.get_identity_core(),
        emotional_state=memory.get_emotional_state(),
        response_mode=request.response_mode or {},
        memory_engine=memory,
        llm_client=llm,
    )
    return {
        "success": True,
        "evaluation": evaluation,
    }


@app.get("/metacognition/dimension-scores")
async def get_dimension_scores():
    """Get detailed dimension scores from recent evaluations."""
    if not meta_evaluator.evaluations:
        return {"message": "No evaluations yet", "evaluations": 0}
    
    # Average the last 5 evaluations
    recent = meta_evaluator.evaluations[-5:]
    dimension_avgs = {}
    
    for eval in recent:
        for dim, score in eval.get("dimension_scores", {}).items():
            if dim not in dimension_avgs:
                dimension_avgs[dim] = []
            dimension_avgs[dim].append(score)
    
    # Compute averages
    dimension_summary = {}
    for dim, scores in dimension_avgs.items():
        dimension_summary[dim] = {
            "average": sum(scores) / len(scores),
            "samples": len(scores)
        }
    
    return {
        "dimension_scores": dimension_summary,
        "window_size": len(recent),
        "evaluated_interactions": sum(len(e.get("dimension_scores", {})) for e in recent)
    }


@app.get("/metacognition/learning-log")
async def get_learning_log(limit: int = 20):
    """Get recent learning events."""
    recent_logs = self_improvement.learning_log[-limit:]
    
    return {
        "learning_events": recent_logs,
        "total_events": len(self_improvement.learning_log),
        "returned": len(recent_logs)
    }


# =========================
# 💾 Memory Decay & Salience Endpoints (NEW)
# =========================
@app.get("/memory/decay-stats")
async def get_decay_statistics():
    """Get memory decay and salience statistics."""
    # Get all user facts
    all_facts = memory.user_memory.get()
    documents = all_facts.get("documents", [])
    
    if not documents:
        return {
            "total_facts": 0,
            "retention_analysis": [],
            "average_decay_coefficient": 0.0
        }
    
    # Analyze decay for sample of facts
    current_time = datetime.now()
    decay_analysis = []
    
    for doc in documents[:20]:  # Sample first 20
        # Compute decay (simplified)
        decayed = memory_decay.compute_decay(
            {"salience_score": 0.7, "created_at": current_time.isoformat()},
            current_time
        )
        decay_analysis.append({
            "fact_preview": doc[:80],
            "current_effective_salience": decayed
        })
    
    return {
        "total_facts": len(documents),
        "sampled_facts": len(decay_analysis),
        "decay_analysis": decay_analysis,
        "dynamic_salience_enabled": True
    }


@app.get("/memory/narrative-threads")
async def get_narrative_threads():
    """Get current narrative threads and their evolution."""
    result = {}
    
    for theme_name, thread in threaded_narrative.threads.items():
        result[theme_name] = {
            "episodes": len(thread.get("episodes", [])),
            "created_at": thread.get("created_at"),
            "evolution_score": thread.get("evolution_score", 0.5),
            "latest_episode": thread.get("episodes", [])[-1] if thread.get("episodes") else None
        }
    
    return {
        "threads": result,
        "total_themes": len(result),
        "evolution_average": sum(t["evolution_score"] for t in result.values()) / len(result) if result else 0.0
    }


# =========================
# �💾 Save Conversation
# =========================
@app.post("/save_conversation")
async def save_conversation(request: SaveConversationRequest):
    """
    Save conversation history to local JSON file.
    """
    import json
    from datetime import datetime
    
    try:
        # Create conversations directory if it doesn't exist
        os.makedirs("persistent_state/conversations", exist_ok=True)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"persistent_state/conversations/conversation_{timestamp}.json"
        
        # Save conversation data
        data = {
            "saved_at": datetime.now().isoformat(),
            "message_count": len(request.conversation),
            "conversation": request.conversation
        }
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        return {"success": True, "filename": filename}
    
    except Exception as e:
        return {"success": False, "error": str(e)}


# =========================
# 🧠 System 3 Integration Helper
# =========================
async def handle_internal_message_wrapper(text: str, **kwargs) -> None:
    """
    Wrapper for DreamCycleDaemon to call handle_internal_message without BackgroundTasks.
    Creates a simple background task context and delegates to the main handler.
    """
    wrapper_start = time.perf_counter()
    emergence_type = kwargs.get("emergence_type")
    internal_monologue = kwargs.get("internal_monologue", "")
    dream_mode = kwargs.get("dream_mode", "")
    dream_content: Dict[str, str] = kwargs.get("dream_content") or {}
    logger.info(f"[DREAMCYCLE→WRAPPER] Starting internal message processing (text length: {len(text)})")
    if emergence_type:
        logger.debug(f"[DREAMCYCLE→WRAPPER] Emergence type: {emergence_type}")
    if dream_mode:
        logger.debug(f"[DREAMCYCLE→WRAPPER] Dream mode: {dream_mode} | dream content keys: {list(dream_content.keys())}")
    log_structured("async_task_start", task="handle_internal_message_wrapper", text_length=len(text))
    logger.debug(f"[DREAMCYCLE→WRAPPER] Text preview: {text[:100]}...")
    
    class SimpleBackgroundTasks:
        """Minimal background tasks container for internal message processing."""
        def __init__(self):
            self.tasks = []
        
        def add_task(self, func, *args, **kwargs):
            """Queue a task to run in background."""
            self.tasks.append((func, args, kwargs))
        
        async def _run_all(self):
            """Execute all queued tasks (called after handler completes)."""
            for func, args, kwargs in self.tasks:
                try:
                    if asyncio.iscoroutinefunction(func):
                        await func(*args, **kwargs)
                    else:
                        func(*args, **kwargs)
                except Exception as e:
                    logger.error(f"[INTERNAL MESSAGE] Background task failed: {e}", exc_info=True)
    
    bg_tasks = SimpleBackgroundTasks()
    
    try:
        logger.debug(f"[DREAMCYCLE→WRAPPER] Calling handle_internal_message with bg_tasks...")
        # Call the main internal message handler with background tasks
        await handle_internal_message(text, bg_tasks, internal_monologue=internal_monologue, dream_mode=dream_mode, dream_content=dream_content)
        logger.debug(f"[DREAMCYCLE→WRAPPER] handle_internal_message completed successfully")
        
        logger.debug(f"[DREAMCYCLE→WRAPPER] Running {len(bg_tasks.tasks)} queued background tasks...")
        # Run all queued background tasks
        await bg_tasks._run_all()
        logger.info(f"[DREAMCYCLE→WRAPPER] All tasks completed, internal message fully processed")
        log_structured(
            "async_task_end",
            task="handle_internal_message_wrapper",
            duration_ms=round((time.perf_counter() - wrapper_start) * 1000, 2),
            status="ok",
        )
    except Exception as e:
        logger.error(f"[DREAMCYCLE→WRAPPER] FATAL ERROR processing internal message: {e}", exc_info=True)
        log_structured(
            "async_task_end",
            task="handle_internal_message_wrapper",
            duration_ms=round((time.perf_counter() - wrapper_start) * 1000, 2),
            status="error",
        )
        raise


# =========================
# 🌐 Frontend Loader
# =========================
@app.get("/")
async def redirect_to_web():
    """Redirect to modern web interface."""
    return RedirectResponse(url="/web/index.html")


# =========================
# =========================
if __name__ == "__main__":
    import uvicorn
    logger.info("🚀 Yuki is waking up... Neural Link active on port 8000")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
