"""
Shared runtime context — all global singleton instances live here.
Other modules (evolution, tasks, server) import from this module so they all
share the same objects without circular dependencies.

`dream_cycle_daemon` and `autopoietic_integration` start as None and are set
during the FastAPI startup event (they depend on a callback that lives in
server.py, so they cannot be initialized here).
"""
import os
from collections import deque

from memory.memory_store import MemoryEngine
from cognition.executive_control import CognitiveController
from llm import get_llm_client
from cognition.executive_persona import PersonaLogic
from cognition.reactive_core import SubconsciousWrapper
from cognition.reactive_conflict import ConflictResolver
from cognition.reflective_engine import ReflectionEngine
from memory.decay import MemoryDecaySystem, DynamicSalienceScorer, ThreadedNarrativeMemory
from cognition.reflective_metacognition import MetaCognitiveEvaluator, SelfImprovementEngine
from cognition.reactive_adaptation import AdaptiveResponseGenerator
from cognition.executive_extensions import CognitiveExtensions
from cognition.reflective_relationships import RelationshipModel
from cognition.enactive_nexus import EnactiveNexus
from cognition.circadian import CircadianClock
from cognition.cognitive_load import CognitiveLoadTracker
from cognition.user_model import UserModel
from cognition.self_model_validator import SelfModelValidator
from memory.state_signatures import StateSignatureStore
from memory.proactive_intentions import ProactiveIntentionStore

# ---------------------------------------------------------------------------
# Core services (initialized at import time)
# ---------------------------------------------------------------------------
llm = get_llm_client()

session_reset_on_startup = (
    os.getenv("SESSION_RESET_ON_STARTUP", "false").strip().lower()
    in {"1", "true", "yes", "y"}
)

# Pass the llama.cpp embedding function to MemoryEngine if available so that
# ChromaDB uses the in-process model instead of sentence-transformers.
_llm_embed_fn = getattr(llm, "get_chroma_embed_fn", lambda: None)()
memory = MemoryEngine(
    llm_client=llm,
    session_reset_on_startup=session_reset_on_startup,
    llm_embed_fn=_llm_embed_fn,
)

enactive_nexus = EnactiveNexus(
    db_path="./persistent_state",
    memory_engine=memory,
    llm_client=llm,
)
memory.set_enactive_nexus(enactive_nexus)

persona = PersonaLogic(identity_meta=memory.get_identity_meta())
controller = CognitiveController(enactive_nexus=enactive_nexus)
subconscious_wrapper = SubconsciousWrapper()
conflict_resolver = ConflictResolver()
adaptive_response = AdaptiveResponseGenerator()

# ---------------------------------------------------------------------------
# Extended cognitive systems
# ---------------------------------------------------------------------------
reflection_engine = ReflectionEngine(db_path="./persistent_state", llm_client=llm)
memory_decay = MemoryDecaySystem(db_path="./persistent_state")
dynamic_salience = DynamicSalienceScorer(db_path="./persistent_state")
threaded_narrative = ThreadedNarrativeMemory(db_path="./persistent_state")
meta_evaluator = MetaCognitiveEvaluator(db_path="./persistent_state")
self_improvement = SelfImprovementEngine(db_path="./persistent_state")

# ---------------------------------------------------------------------------
# Cognitive extensions (v4)
# ---------------------------------------------------------------------------
cognitive_extensions = CognitiveExtensions(db_path="./persistent_state", persona_name=persona.name)
relationship_model = RelationshipModel(db_path="./persistent_state")

# ---------------------------------------------------------------------------
# New organism subsystems (Gap 1–8 from synthetic-life audit)
# ---------------------------------------------------------------------------
circadian     = CircadianClock()
cognitive_load = CognitiveLoadTracker()
user_model    = UserModel(db_path="./persistent_state")
self_validator = SelfModelValidator(db_path="./persistent_state")
state_signature_store = StateSignatureStore(db_path="./persistent_state", max_entries=2000)
proactive_intention_store = ProactiveIntentionStore(db_path="./persistent_state", max_entries=2000)

# ---------------------------------------------------------------------------
# Late-initialized (set during FastAPI startup_event in server.py)
# ---------------------------------------------------------------------------
dream_cycle_daemon = None
autopoietic_integration = None

# ---------------------------------------------------------------------------
# Proactive message queue (dream cycle → frontend)
# ---------------------------------------------------------------------------
proactive_queue: deque = deque(maxlen=20)

# ---------------------------------------------------------------------------
# Autopoietic telemetry (written by evolution loop, read by routes)
# ---------------------------------------------------------------------------
latest_postprocess_telemetry = {
    "salience_score": 0.0,
    "conflict_score": 0.0,
    "memory_candidates": 0,
    "resolution_policy": "allow",
    "enactive_policy": "stabilize",
    "updated_at": "",
}

# ---------------------------------------------------------------------------
# WebSocket telemetry event queue
# Server pushes dicts here; the /ws/telemetry broadcaster drains and sends
# them to all connected frontend clients.
#
# Expected event shapes:
#   { "type": "chroma_retrieval", "label": str, "salience": float, "metadata": dict }
#   (other ad-hoc event types may be added by future subsystems)
# ---------------------------------------------------------------------------
ws_event_queue: deque = deque(maxlen=100)

# ---------------------------------------------------------------------------
# Runtime flags
# ---------------------------------------------------------------------------
last_cognitive_exhausted = False
