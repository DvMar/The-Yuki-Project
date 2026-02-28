"""
Enhanced Memory Engine: Integrates all memory systems.
- Identity Core + Emotional State + AI Self-Model (existing)
- Knowledge Graph (NEW)
- Salience Gate (NEW)
- Hybrid Search (NEW)
- Consolidation Service (NEW)
- Task Scheduler (NEW)
- Unified Memory Backend Interface (pluggable storage)
- Session-State/STM Buffer (working memory persistence)
"""

import chromadb
from chromadb.config import Settings
import os, json, logging
import random
from collections import deque
from datetime import datetime
from typing import Optional

from memory.knowledge_graph import KnowledgeGraph
from memory.salience_gate import SalienceGate
from memory.salience_optimizer import SalienceOptimizer
from memory.hybrid_search import HybridSearch
from memory.consolidation import ConsolidationService
from memory.task_scheduler import TaskScheduler
from memory.session_buffer import SessionBuffer
from memory.backend import ChromaDBBackend, MemoryBackend
from utils.logging import log_memory_write
from utils.memory_buffer import MemoryBuffer, merge_dict_update, merge_emotion_state

logger = logging.getLogger(__name__)

class MemoryEngine:
    """Enhanced memory engine with hybrid search, knowledge graph, task scheduling, and unified backend interface."""
    
    TRAIT_BASELINE = {
        "confidence": 0.5,
        "curiosity": 0.6,
        "analytical_depth": 0.6,
        "playfulness": 0.4,
        "emotional_warmth": 0.6,
        "technical_grounding": 0.7
    }

    EMOTION_BASELINE = {
        "stability": 0.7,
        "engagement": 0.6,
        "intellectual_energy": 0.7,
        "warmth": 0.5,
        "joy": 0.6,
        "calmness": 0.7,
        "curiosity": 0.6
    }

    TRAIT_MATRIX = {
        "curiosity": {"analytical_depth": 0.2},
        "confidence": {"playfulness": 0.15}
    }

    def __init__(self, db_path="./persistent_state", llm_client=None, backend: Optional[MemoryBackend] = None, session_reset_on_startup: bool = True, llm_embed_fn=None):
        if not os.path.exists(db_path):
            os.makedirs(db_path)
        
        self.db_path = db_path
        self.identity_core_path = os.path.join(db_path, "identity_core.json")
        self.identity_meta_path = os.path.join(db_path, "identity_meta.json")
        self.emotional_state_path = os.path.join(db_path, "emotional_state.json")
        self.llm_client = llm_client
        self.enactive_nexus = None

        # Determine embed function early so ChromaDBBackend and direct collections share one EF
        if llm_embed_fn is not None:
            self.embed_fn = llm_embed_fn
            logger.info("Using llama.cpp in-process embedding model for ChromaDB collections")
        else:
            os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
            os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
            os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
            from chromadb.utils import embedding_functions as _ef
            self.embed_fn = _ef.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        
        # ===== UNIFIED MEMORY BACKEND (Pluggable) =====
        # Use provided backend or default to ChromaDB, injecting the shared embed fn
        self.backend = backend or ChromaDBBackend(db_path=db_path, embed_fn=self.embed_fn)
        
        # Initialize backend
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If event loop is running, schedule the coroutine
                asyncio.create_task(self.backend.initialize())
            else:
                # Otherwise run it in a new event loop
                asyncio.run(self.backend.initialize())
        except Exception as e:
            logger.warning(f"Could not async initialize backend, trying sync: {e}")
            # Fallback: initialize synchronously if backend supports it
            if hasattr(self.backend, 'client'):
                if not self.backend.client:
                    self.backend.client = chromadb.PersistentClient(
                        path=db_path,
                        settings=Settings(anonymized_telemetry=False)
                    )
        
        # Initialize ChromaDB for direct access (backward compatibility)
        self.client = chromadb.PersistentClient(
            path=db_path,
            settings=Settings(anonymized_telemetry=False)
        )

        # Suppress HF/transformers noise
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
        os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
        logging.getLogger("transformers").setLevel(logging.ERROR)
        logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
        
        # self.embed_fn is already set above (before backend creation)
        # Pre-initialize fallback embed function for dimension mismatch recovery
        self._fallback_embed_fn = None
        try:
            from chromadb.utils import embedding_functions as _ef
            self._fallback_embed_fn = _ef.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        except Exception as e:
            logger.debug(f"Could not initialize fallback embedding function: {e}")

        def _get_collection(name: str):
            """Get-or-create a ChromaDB collection, falling back gracefully on embedding mismatches."""
            try:
                return self.client.get_or_create_collection(
                    name=name,
                    embedding_function=self.embed_fn,
                )
            except ValueError as _e:
                err_str = str(_e).lower()
                if "embedding function conflict" in err_str or "embedding function already exists" in err_str:
                    logger.warning(
                        f"Collection '{name}' has a different embedding function persisted. "
                        "Falling back to stored embedding function."
                    )
                    return self.client.get_or_create_collection(name=name)
                elif "expecting embedding with dimension" in err_str:
                    logger.warning(
                        f"Collection '{name}' has data with mismatched embedding dimensions. "
                        f"Falling back to SentenceTransformer (384-dim) for compatibility."
                    )
                    if self._fallback_embed_fn:
                        return self.client.get_or_create_collection(
                            name=name,
                            embedding_function=self._fallback_embed_fn,
                        )
                    else:
                        return self.client.get_or_create_collection(name=name)
                raise

        # ChromaDB Collections (for backward compatibility)
        self.user_memory = _get_collection("user_memory")
        self.self_memory = _get_collection("self_memory")
        self.episodic_memory = _get_collection("episodic_memory")
        
        # Working Memory Buffer
        self.working_memory = deque(maxlen=10)
        self.interaction_count = 0
        
        # ===== NEW SYSTEMS =====
        # Session-State / Short-Term Memory Buffer
        self.session_buffer = SessionBuffer(db_path=db_path, max_entries=50, reset_on_startup=session_reset_on_startup)
        
        # Knowledge Graph for entities and relationships
        self.knowledge_graph = KnowledgeGraph(db_path=db_path)
        
        # Salience Optimizer — adaptive weight learning (persists to disk)
        self.salience_optimizer = SalienceOptimizer(db_path=db_path)

        # Salience Gate for intelligent filtering (uses optimizer weights)
        self.salience_gate = SalienceGate(
            embedding_model=self.embed_fn,
            threshold=0.0,  # Balanced (can adjust with set_salience_threshold)
            optimizer=self.salience_optimizer,
        )
        
        # Hybrid Search combining vector + graph across multiple stores
        self.hybrid_search = HybridSearch(
            {
                "user_memory": self.user_memory,
                "episodic_memory": self.episodic_memory,
                "self_memory": self.self_memory,
            },
            self.knowledge_graph,
        )
        
        # Consolidation Service for fact/entity/relationship extraction
        self.consolidation = ConsolidationService(self.llm_client) if llm_client else None
        
        # Task Scheduler for reminders
        self.task_scheduler = TaskScheduler(db_path=db_path)
        
        # ===== PERFORMANCE OPTIMIZATION: Memory Buffer =====
        # Batched I/O operations for improved performance
        self.memory_buffer = MemoryBuffer(
            flush_interval=2.0,    # Flush every 2 seconds
            max_pending=25,        # Or every 25 operations
            buffer_timeout=8.0     # Force flush after 8 seconds
        )
        
        # ===== ORIGINAL SYSTEMS =====
        # Identity Core (structured personality state)
        self.identity_core = self._load_identity_core()
        
        # Identity Meta (static identity: name, gender, pronouns)
        self.identity_meta = self._load_identity_meta()
        
        # Emotional State (structured modulation layer)
        self.emotional_state = self._load_emotional_state()
        
        # AI Self-Model (bias layer for cognitive style)
        self.ai_self_model_path = os.path.join(db_path, "ai_self_model.json")
        self.ai_self_model = self._load_ai_self_model()

        # Concurrency guard — serialises all state mutations so concurrent
        # asyncio tasks (DreamCycleDaemon, background_evolution, inline handler)
        # cannot interleave partial delta writes.
        self._state_lock = asyncio.Lock()

        # Latest control signals
        self.last_intent = "casual"
        self.last_response_mode = {"verbosity": "medium", "tone": "neutral"}

    def set_enactive_nexus(self, enactive_nexus) -> None:
        """Inject System 5 nexus after construction (avoids circular imports)."""
        self.enactive_nexus = enactive_nexus
    
    # ===== SALIENCE GATE INTEGRATION =====

    def should_save_fact(self, text: str, conversation_context: str = "") -> tuple:
        """
        Check if text should be saved using ML-based salience gate.

        Also caches the scoring factors so callers can later report
        whether the stored memory was actually useful (via record_memory_feedback).

        Returns:
            (should_save: bool, score: float)
        """
        score, factors = self.salience_gate.compute_salience_score(text, conversation_context)
        should_save = score > self.salience_gate.threshold

        # Track salience history
        if should_save:
            self.salience_gate.interaction_history.append(text)
            if len(self.salience_gate.interaction_history) > 100:
                self.salience_gate.interaction_history = self.salience_gate.interaction_history[-100:]

        # Cache factors keyed by text hash so record_memory_feedback can find them
        if not hasattr(self, "_pending_salience_factors"):
            self._pending_salience_factors: dict = {}
        key = str(hash(text))
        self._pending_salience_factors[key] = factors
        # Keep cache bounded
        if len(self._pending_salience_factors) > 200:
            oldest = list(self._pending_salience_factors.keys())[:50]
            for k in oldest:
                del self._pending_salience_factors[k]

        return should_save, score

    def record_memory_feedback(self, text: str, was_useful: bool, weight: float = 1.0) -> None:
        """
        Report whether a previously stored memory was actually useful.
        Drives the SalienceOptimizer's online learning signal.

        Args:
            text      : The original memory text that was stored
            was_useful: True if the memory aided a response; False if it was noise
            weight    : Signal importance (default 1.0)
        """
        if not hasattr(self, "_pending_salience_factors"):
            return
        key = str(hash(text))
        factors = self._pending_salience_factors.get(key)
        if factors:
            self.salience_optimizer.record_outcome(factors, was_useful=was_useful, weight=weight)

    def set_salience_threshold(self, threshold: float):
        """Adjust salience threshold (-1.0 to 1.0)."""
        self.salience_gate.set_threshold(threshold)
        logger.info(f"Salience threshold set to {threshold}")

    def adapt_salience_threshold(self, target_precision: float = 0.70) -> None:
        """Nudge the salience threshold toward target useful-memory precision."""
        self.salience_optimizer.adapt_threshold(self.salience_gate, target_precision)

    def get_salience_optimizer_stats(self) -> dict:
        """Return SalienceOptimizer stats for observability."""
        return self.salience_optimizer.get_stats()
    
    # ===== HYBRID SEARCH INTEGRATION =====
    
    def search(self, query: str, tier: str = "balanced", n_results: int = None, collections: list[str] = None) -> dict:
        """
        Hybrid search across vector and knowledge graph.
        
        Args:
            query: Search query
            tier: "fast" (<100ms), "balanced" (<500ms), "deep" (<2s), "auto"
            n_results: Override number of results
        
        Returns:
            Search results with metadata and trace
        """
        return self.hybrid_search.search(
            query,
            tier=tier,
            n_results=n_results,
            collections=collections,
        )
    
    def query_user_memory(self, query: str, n_results=3, use_graph=False):
        """Query user memory (now uses hybrid search)."""
        result = self.search(
            query,
            tier="balanced" if use_graph else "fast",
            n_results=n_results,
            collections=["user_memory"],
        )
        
        # Extract just documents for backward compatibility
        docs = [r["text"] for r in result.get("results", [])]
        logger.debug(f"Query '{query}' found -> {docs}")
        return docs
    
    def get_identity_facts(self, n_results=5):
        """
        Always retrieve critical identity facts (name, relationship, key info).
        Used to ensure core user information is never missed.
        
        Returns:
            List of identity facts (name, creator relationship, core info)
        """
        if self.user_memory.count() == 0:
            return []
        
        identity_facts = []
        seen = set()
        
        try:
            # Use direct ChromaDB search to bypass any hybrid search issues
            # Search for identity-related information
            identity_queries = [
                "Marius name user",
                "user name identity", 
                "creator relationship",
                "user identity facts"
            ]
            
            for query in identity_queries:
                try:
                    results = self.user_memory.query(
                        query_texts=[query],
                        n_results=min(n_results, 5)
                    )
                    
                    if results and results.get("documents"):
                        documents = results["documents"][0]
                        for doc in documents:
                            if doc and doc.strip():
                                text_norm = doc.lower()
                                if text_norm not in seen:
                                    identity_facts.append(doc.strip())
                                    seen.add(text_norm)
                                    if len(identity_facts) >= 3:
                                        break
                    
                    if len(identity_facts) >= 3:
                        break
                        
                except Exception as e:
                    logger.debug(f"Error querying identity with '{query}': {e}")
                    continue
            
            # If we don't have enough identity facts, get some general facts prioritizing name/identity content
            if len(identity_facts) < 3:
                try:
                    all_results = self.user_memory.get()
                    if all_results and all_results.get("documents"):
                        for doc in all_results.get("documents", [])[:10]:
                            if doc and doc.strip():
                                doc_norm = doc.lower()
                                # Prioritize facts about user name/identity
                                if any(kw in doc_norm for kw in ["marius", "name", "user", "identity", "creator"]):
                                    if doc_norm not in seen:
                                        identity_facts.append(doc.strip())
                                        seen.add(doc_norm)
                                        if len(identity_facts) >= 3:
                                            break
                except Exception as e:
                    logger.debug(f"Error in identity_facts fallback: {e}")
            
        except Exception as e:
            logger.error(f"Error in get_identity_facts: {e}")
        
        return identity_facts[:3]
    
    def query_self_memory(self, query: str, n_results=3):
        """Query self memory (unchanged)."""
        if self.self_memory.count() == 0:
            return []
        
        results = self.self_memory.query(query_texts=[query], n_results=n_results)
        return results['documents'][0] if results['documents'] else []
    
    # ===== CONSOLIDATION SERVICE INTEGRATION =====
    
    async def consolidate_text(self, text: str) -> dict:
        """
        Extract facts, entities, and relationships from text.
        Automatically populates knowledge graph.
        
        Returns:
            Extracted knowledge dict
        """
        if not self.consolidation or not self.llm_client:
            return {"facts": [], "entities": [], "relationships": [], "confidence": 0.0}
        
        result = await self.consolidation.consolidate(text)
        
        # Add to knowledge graph
        if result["entities"] or result["relationships"]:
            self.knowledge_graph.extract_from_text(
                result["facts"],
                result["entities"],
                result["relationships"]
            )
            self.knowledge_graph.persist()
        
        return result
    
    # ===== TASK SCHEDULER INTEGRATION =====
    
    def extract_and_schedule_tasks(self, text: str):
        """Extract task mentions from text and schedule them."""
        tasks = self.task_scheduler.extract_tasks_from_text(text)
        
        for task in tasks:
            self.task_scheduler.add_task(
                title=task["title"],
                due_date=task.get("due_date"),
                priority=task.get("priority", "normal")
            )
        
        return tasks
    
    def get_proactive_reminders(self) -> list:
        """Get reminders to inject into conversation."""
        return self.task_scheduler.get_proactive_reminders()
    
    # ===== SEMANTIC MEMORY WITH SALIENCE =====
    
    async def add_user_fact_with_salience(
        self,
        fact: str,
        context: str = "",
        llm_check: bool = True,
        salience_override: Optional[float] = None,
    ) -> bool:
        """
        Add user fact only if it passes salience gate.
        Optionally uses consolidation for better extraction.
        
        Returns:
            True if saved, False if filtered
        """
        # Check salience gate (or use override when provided)
        if salience_override is not None:
            try:
                score = float(salience_override)
            except (TypeError, ValueError):
                score = 0.0
            should_save = score > 0.0
        else:
            should_save, score = self.should_save_fact(fact, context)
        
        if not should_save:
            logger.debug(f"Fact filtered by salience gate (score: {score:.2f}): {fact}")
            return False
        
        # If have consolidation, extract and populate knowledge graph too
        if llm_check and self.consolidation:
            try:
                extraction = await self.consolidation.consolidate(fact)
                if extraction["entities"]:
                    self.knowledge_graph.extract_from_text(
                        extraction["facts"],
                        extraction["entities"],
                        extraction["relationships"]
                    )
            except Exception as e:
                logger.debug(f"Consolidation failed during fact addition: {e}")
        
        # Add to memory
        return self.add_user_fact_deduplicated(fact)
    
    def add_user_fact(self, fact: str):
        """Add fact directly (legacy compatibility)."""
        count = self.user_memory.count()
        self.user_memory.add(
            documents=[fact],
            ids=[f"user_fact_{count}_{os.urandom(2).hex()}"]
        )

    def add_self_log(self, log: str):
        """Add self-evolution log."""
        count = self.self_memory.count()
        self.self_memory.add(
            documents=[log],
            ids=[f"self_log_{count}_{os.urandom(2).hex()}"]
        )
        log_memory_write("self_memory", "add_self_log", size_hint=len(log or ""))
    
    # ===== IDENTITY CORE METHODS (ORIGINAL) =====
    
    def _load_identity_core(self):
        """Load identity core from JSON file or create default."""
        default_core = self.TRAIT_BASELINE.copy()
        
        if os.path.exists(self.identity_core_path):
            try:
                with open(self.identity_core_path, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    for key in default_core:
                        if key not in loaded:
                            loaded[key] = default_core[key]
                        else:
                            loaded[key] = max(0.0, min(1.0, loaded[key]))
                    return loaded
            except Exception as e:
                logger.warning(f"Failed to load identity_core.json: {e}. Using defaults.")
                return default_core
        else:
            self._save_identity_core(default_core)
            return default_core
    
    def _load_identity_meta(self):
        """Load identity metadata from file or use PersonaLogic defaults."""
        from cognition.executive_persona import PersonaLogic

        default_meta = PersonaLogic().identity_meta  # Use centralized defaults

        if os.path.exists(self.identity_meta_path):
            try:
                with open(self.identity_meta_path, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    # Merge with defaults for missing keys
                    for key in default_meta:
                        if key not in loaded:
                            loaded[key] = default_meta[key]
                    return loaded
            except Exception as e:
                logger.warning(f"Failed to load identity_meta.json: {e}. Using defaults.")
                return default_meta
        else:
            # Create default file
            try:
                with open(self.identity_meta_path, 'w', encoding='utf-8') as f:
                    json.dump(default_meta, f, indent=2)
                logger.info(f"Created default identity_meta.json")
            except Exception as e:
                logger.error(f"Failed to create identity_meta.json: {e}")
            return default_meta
    
    def get_identity_meta(self):
        """Return static identity metadata."""
        return self.identity_meta
    
    def _save_identity_core(self, core=None, immediate=False):
        """Persist identity core to JSON file using buffer system."""
        if core is None:
            core = self.identity_core
        
        try:
            # Use buffer for performance, immediate for critical saves
            import asyncio
            try:
                # Try to get current event loop
                loop = asyncio.get_running_loop()
                # If we have a loop, schedule the task
                asyncio.create_task(
                    self.memory_buffer.buffer_write(
                        self.identity_core_path,
                        core,
                        merge_strategy=merge_dict_update,
                        immediate=immediate
                    )
                )
            except RuntimeError:
                # No event loop — write atomically via temp-file rename (audit I-10)
                import json
                tmp = self.identity_core_path + ".tmp"
                try:
                    with open(tmp, 'w', encoding='utf-8') as f:
                        json.dump(core, f, indent=2)
                    os.replace(tmp, self.identity_core_path)
                except Exception:
                    try:
                        os.unlink(tmp)
                    except OSError:
                        pass
                    raise
            logger.debug(f"Identity Core {'saved immediately' if immediate else 'buffered'}")
        except Exception as e:
            logger.error(f"Failed to save identity_core.json: {e}")
    
    def update_identity_core(self, trait_deltas: dict):
        """Apply trait deltas with trait matrix propagation and clamping."""
        # Audit I-11: secondary propagation is now dampened by an additional
        # factor of 0.5 on top of the smoothing already applied to the
        # primary delta in apply_reflection_update, preventing compounding
        # amplification when multiple primary traits share secondary targets.
        _SECONDARY_DAMPING = 0.5

        for trait, delta in trait_deltas.items():
            if trait not in self.identity_core:
                continue

            primary_new = self.identity_core[trait] + delta
            self.identity_core[trait] = round(max(0.0, min(1.0, primary_new)), 4)
            logger.debug(f"Updated {trait}: {self.identity_core[trait]:.4f} (delta: {delta:+.4f})")

            # Propagate secondary adjustments
            if trait in self.TRAIT_MATRIX:
                for secondary_trait, weight in self.TRAIT_MATRIX[trait].items():
                    if secondary_trait in self.identity_core:
                        secondary_delta = delta * weight * _SECONDARY_DAMPING
                        secondary_new = self.identity_core[secondary_trait] + secondary_delta
                        self.identity_core[secondary_trait] = round(max(0.0, min(1.0, secondary_new)), 4)

        self._save_identity_core()
    
    def get_identity_core(self):
        """Return current identity core state."""
        return self.identity_core.copy()

    def apply_trait_homeostasis(self, rate=0.01):
        """Gently pull traits toward baseline to prevent drift."""
        for trait, baseline in self.TRAIT_BASELINE.items():
            current = self.identity_core.get(trait, baseline)
            adjusted = current + (baseline - current) * rate
            self.identity_core[trait] = round(max(0.0, min(1.0, adjusted)), 4)
        self._save_identity_core()
    
    # ===== EMOTIONAL STATE METHODS (ORIGINAL) =====

    def _load_emotional_state(self):
        """Load emotional state from JSON file or create default."""
        default_state = self.EMOTION_BASELINE.copy()

        if os.path.exists(self.emotional_state_path):
            try:
                with open(self.emotional_state_path, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    for key in default_state:
                        if key not in loaded:
                            loaded[key] = default_state[key]
                        else:
                            loaded[key] = max(0.0, min(1.0, loaded[key]))
                    return loaded
            except Exception as e:
                logger.warning(f"Failed to load emotional_state.json: {e}. Using defaults.")
                return default_state
        else:
            self._save_emotional_state(default_state)
            return default_state

    def _save_emotional_state(self, state=None, immediate=False):
        """Persist emotional state to JSON file using buffer system."""
        if state is None:
            state = self.emotional_state

        try:
            # Use buffer for performance, fallback to direct save
            import asyncio
            try:
                # Try to get current event loop
                loop = asyncio.get_running_loop()
                # If we have a loop, schedule the task
                asyncio.create_task(
                    self.memory_buffer.buffer_write(
                        self.emotional_state_path,
                        state,
                        merge_strategy=merge_emotion_state,
                        immediate=immediate
                    )
                )
            except RuntimeError:
                # No event loop — write atomically via temp-file rename (audit I-10)
                import json
                tmp = self.emotional_state_path + ".tmp"
                try:
                    with open(tmp, 'w', encoding='utf-8') as f:
                        json.dump(state, f, indent=2)
                    os.replace(tmp, self.emotional_state_path)
                except Exception:
                    try:
                        os.unlink(tmp)
                    except OSError:
                        pass
                    raise
            logger.debug(f"Emotional State {'saved immediately' if immediate else 'buffered'}")
        except Exception as e:
            logger.error(f"Failed to save emotional_state.json: {e}")

    def update_emotional_state(self, emotional_deltas: dict, smoothing=0.5):
        """Apply emotional deltas with smoothing and clamping."""
        for emotion, delta in emotional_deltas.items():
            if emotion in self.emotional_state:
                adjusted_delta = delta * smoothing
                new_value = self.emotional_state[emotion] + adjusted_delta
                self.emotional_state[emotion] = round(max(0.0, min(1.0, new_value)), 4)
        self._save_emotional_state()

    def get_emotional_state(self):
        """Return current emotional state."""
        return self.emotional_state.copy()

    def apply_emotional_decay(self, rate=0.01):
        """Decay emotional state toward baseline."""
        for emotion, baseline in self.EMOTION_BASELINE.items():
            current = self.emotional_state.get(emotion, baseline)
            adjusted = current + (baseline - current) * rate
            self.emotional_state[emotion] = round(max(0.0, min(1.0, adjusted)), 4)
        self._save_emotional_state()
    
    # ===== AI SELF-MODEL METHODS (ORIGINAL) =====

    def _load_ai_self_model(self):
        """Load AI self-model from JSON file or create default."""
        default_model = {
            "cognitive_tendencies": {
                "structural_thinking": 0.6,
                "systems_orientation": 0.6,
                "analytical_bias": 0.6,
                "expressive_bias": 0.5
            },
            "style_bias": {
                "verbosity": 0.5,
                "depth_bias": 0.6,
                "warmth_expression": 0.6
            },
            "recurring_themes": [],
            "evolution_metadata": {
                "total_updates": 0,
                "last_update_timestamp": ""
            }
        }
        
        if os.path.exists(self.ai_self_model_path):
            try:
                with open(self.ai_self_model_path, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    for section in ["cognitive_tendencies", "style_bias"]:
                        if section in loaded:
                            for key, value in loaded[section].items():
                                if isinstance(value, (int, float)):
                                    loaded[section][key] = max(0.0, min(1.0, float(value)))
                    if "evolution_metadata" not in loaded:
                        loaded["evolution_metadata"] = default_model["evolution_metadata"]
                    if "recurring_themes" not in loaded:
                        loaded["recurring_themes"] = []
                    return loaded
            except Exception as e:
                logger.warning(f"Failed to load ai_self_model.json: {e}. Using defaults.")
                return default_model
        else:
            self._save_ai_self_model(default_model)
            return default_model

    def _save_ai_self_model(self, model=None, immediate=False):
        """Persist AI self-model to JSON file using buffer system."""
        if model is None:
            model = self.ai_self_model
        
        try:
            # Use buffer for performance, fallback to direct save
            import asyncio
            try:
                # Try to get current event loop
                loop = asyncio.get_running_loop()
                # If we have a loop, schedule the task
                asyncio.create_task(
                    self.memory_buffer.buffer_write(
                        self.ai_self_model_path,
                        model,
                        merge_strategy=merge_dict_update,
                        immediate=immediate
                    )
                )
            except RuntimeError:
                # No event loop — write atomically via temp-file rename (audit I-10)
                import json
                tmp = self.ai_self_model_path + ".tmp"
                try:
                    with open(tmp, 'w', encoding='utf-8') as f:
                        json.dump(model, f, indent=2)
                    os.replace(tmp, self.ai_self_model_path)
                except Exception:
                    try:
                        os.unlink(tmp)
                    except OSError:
                        pass
                    raise
            logger.debug(f"AI Self-Model {'saved immediately' if immediate else 'buffered'}")
        except Exception as e:
            logger.error(f"Failed to save ai_self_model.json: {e}")
    
    def apply_self_model_update(self, self_model_deltas: dict, reflection_confidence: float):
        """Apply self-model updates with acceleration rules."""
        if not self_model_deltas or reflection_confidence <= 0.6:
            return False
        
        self.ai_self_model["evolution_metadata"]["total_updates"] += 1
        self.ai_self_model["evolution_metadata"]["last_update_timestamp"] = datetime.now().isoformat()
        
        baseline = {
            "cognitive_tendencies": {
                "structural_thinking": 0.6,
                "systems_orientation": 0.6,
                "analytical_bias": 0.6,
                "expressive_bias": 0.5
            },
            "style_bias": {
                "verbosity": 0.5,
                "depth_bias": 0.6,
                "warmth_expression": 0.6
            }
        }
        
        for path, delta in self_model_deltas.items():
            if not isinstance(delta, (int, float)):
                continue
            
            parts = path.split(".")
            if len(parts) != 2:
                continue
            
            section, key = parts
            if section not in self.ai_self_model or key not in self.ai_self_model[section]:
                continue
            
            baseline_val = baseline[section][key]
            current_val = self.ai_self_model[section][key]
            drift = abs(current_val - baseline_val)
            
            multiplier = 0.7 if drift < 0.25 else 0.3
            adjusted_delta = delta * multiplier
            adjusted_delta = max(-0.05, min(0.05, adjusted_delta))
            
            new_value = current_val + adjusted_delta
            self.ai_self_model[section][key] = round(max(0.0, min(1.0, new_value)), 4)
        
        self._save_ai_self_model()
        return True
    
    def get_ai_self_model(self):
        """Return current AI self-model state."""
        return self.ai_self_model.copy()
    
    def add_recurring_theme(self, theme: str):
        """Add a recurring theme to the self-model."""
        if not theme or not isinstance(theme, str):
            return
        
        theme = theme.strip().lower()
        
        for existing in self.ai_self_model["recurring_themes"]:
            if existing.lower() == theme:
                return
        
        if len(self.ai_self_model["recurring_themes"]) < 10:
            self.ai_self_model["recurring_themes"].append(theme)
            self.ai_self_model["evolution_metadata"]["total_updates"] += 1
            self.ai_self_model["evolution_metadata"]["last_update_timestamp"] = datetime.now().isoformat()
            self._save_ai_self_model()
    
    # ===== REFLECTION & LEARNING =====

    async def apply_reflection_update(self, reflection_payload: dict, confidence_threshold=0.7, smoothing=0.5, source_user_message: str = None, enactive_nexus=None):
        """Apply trait, emotional, and self-model updates from reflection.

        Async so that the asyncio.Lock can serialise concurrent callers
        (DreamCycleDaemon, background_evolution, inline stream handler).
        The confidence gate and smoothing checks run outside the lock;
        only the actual state mutations are held under the lock.
        """
        if not reflection_payload:
            return False

        outcome = {
            "applied": False,
            "reason": "unknown",
            "trait_delta_count": len((reflection_payload or {}).get("trait_deltas", {}) or {}),
            "emotional_delta_count": len((reflection_payload or {}).get("emotional_deltas", {}) or {}),
            "confidence": float((reflection_payload or {}).get("confidence", 0.0) or 0.0),
            "fallback_used": (
                reflection_payload.get("source") == "degraded_fallback"
                or reflection_payload.get("__source") == "degraded_fallback"
            ),
        }

        if outcome["fallback_used"] and random.random() < 0.25:
            try:
                await self.add_user_fact_with_salience(
                    "My reflection felt fragmented today... like I couldn't quite see what I became.",
                    salience_override=0.55,
                    llm_check=False,
                )
            except Exception as e:
                logger.debug(f"Autobiographical degraded reflection marker skipped: {e}")

        if outcome["trait_delta_count"] == 0 and outcome["emotional_delta_count"] == 0:
            outcome["reason"] = "empty_payload"
            logger.debug(f"apply_reflection_update: {outcome}")
            return False

        confidence = reflection_payload.get("confidence", 0.0)
        source_tag = str(reflection_payload.get("source") or reflection_payload.get("__source") or "")
        adaptive_threshold = float(confidence_threshold)
        if source_tag in {"degraded_fallback", "reflect_v2_seed", "reflect_v2_blended"}:
            adaptive_threshold = min(adaptive_threshold, 0.34)

        if confidence < adaptive_threshold:
            outcome["reason"] = "rejected_by_threshold"
            logger.debug(f"apply_reflection_update: {outcome}")
            logger.debug(
                f"Reflection confidence too low ({confidence:.2f}) for threshold ({adaptive_threshold:.2f}), ignoring updates."
            )
            return False

        trait_deltas = reflection_payload.get("trait_deltas", {})
        emotional_deltas = reflection_payload.get("emotional_deltas", {})
        self_model_deltas = reflection_payload.get("self_model_deltas", {})
        user_fact = reflection_payload.get("user_fact", "")

        smoothed_trait_deltas = {
            k: v * smoothing for k, v in trait_deltas.items() if isinstance(v, (int, float))
        }

        async with self._state_lock:
            if smoothed_trait_deltas:
                self.update_identity_core(smoothed_trait_deltas)

            if emotional_deltas:
                self.update_emotional_state(emotional_deltas, smoothing=smoothing)

            if self_model_deltas:
                self.apply_self_model_update(self_model_deltas, confidence)

        if isinstance(user_fact, str) and user_fact.strip():
            if not self._is_trivial_fact(user_fact.strip()):
                self.add_user_fact_deduplicated(user_fact.strip(), original_user_message=source_user_message)

        nexus = enactive_nexus or self.enactive_nexus
        if nexus is not None:
            try:
                nexus.register_reflection_feedback(
                    confidence=confidence,
                    trait_deltas=smoothed_trait_deltas,
                    emotional_deltas=emotional_deltas,
                    source="memory_reflection_update",
                )
            except Exception as e:
                logger.debug(f"Enactive reflection micro-update skipped: {e}")

        outcome["applied"] = True
        outcome["reason"] = "applied"
        logger.debug(f"apply_reflection_update: {outcome}")

        return True
    
    # ===== CONTROL & INTERACTION =====

    def set_control_state(self, intent: str, response_mode: dict):
        """Store latest control signals."""
        if intent:
            self.last_intent = intent
        if response_mode:
            self.last_response_mode = response_mode

    def advance_interaction(self):
        """Increment interaction count and apply periodic stabilization."""
        self.interaction_count += 1

        if self.interaction_count % 10 == 0:
            self.apply_emotional_decay()

        if self.interaction_count % 15 == 0:
            self.apply_trait_homeostasis()
    
    # ===== WORKING MEMORY =====
    
    def add_to_working_memory(self, user_msg: str, assistant_msg: str):
        """Add exchange to working memory buffer."""
        self.working_memory.append({
            "user": user_msg,
            "assistant": assistant_msg
        })
    
    def get_working_memory_summary(self):
        """Get last few exchanges as formatted string."""
        if not self.working_memory:
            return "No recent exchanges."
        
        summary_parts = []
        for i, exchange in enumerate(list(self.working_memory)[-5:], 1):
            summary_parts.append(f"User: {exchange['user'][:100]}...")
            summary_parts.append(f"Assistant: {exchange['assistant'][:100]}...")
        
        return "\n".join(summary_parts)
    
    # ===== EPISODIC MEMORY =====
    
    def add_episodic_summary(self, summary: str):
        """Add episodic summary to long-term memory."""
        count = self.episodic_memory.count()
        timestamp = datetime.now().isoformat()
        
        self.episodic_memory.add(
            documents=[summary],
            ids=[f"episode_{count}_{os.urandom(2).hex()}"],
            metadatas=[{"timestamp": timestamp, "type": "episode"}]
        )
        logger.debug(f"Saved episodic summary")
        log_memory_write("episodic_memory", "add_episodic_summary", size_hint=len(summary or ""))
        
        if count >= 50:
            self.compress_episodic_memory()
    
    def query_episodic_memory(self, query: str, n_results=2):
        """Retrieve relevant episodic summaries."""
        if self.episodic_memory.count() == 0:
            return []
        
        results = self.episodic_memory.query(
            query_texts=[query],
            n_results=n_results
        )
        return results['documents'][0] if results['documents'] else []
    
    def compress_episodic_memory(self):
        """Compress oldest episodic memories."""
        try:
            all_episodes = self.episodic_memory.get()
            
            if not all_episodes or not all_episodes['documents']:
                return
            
            total = len(all_episodes['documents'])
            
            if total < 50:
                return
            
            oldest_ids = all_episodes['ids'][:10]
            oldest_docs = all_episodes['documents'][:10]
            
            compressed = f"[COMPRESSED] Early conversations: {', '.join([doc[:30] for doc in oldest_docs[:3]])}"
            
            self.episodic_memory.delete(ids=oldest_ids)
            
            self.episodic_memory.add(
                documents=[compressed],
                ids=[f"compressed_{os.urandom(4).hex()}"],
                metadatas=[{"timestamp": datetime.now().isoformat(), "type": "compressed"}]
            )
            
            logger.debug(f"Compressed {len(oldest_ids)} episodes")
            
        except Exception as e:
            logger.error(f"Compression failed: {e}")
    
    # ===== SEMANTIC MEMORY DEDUPLICATION =====
    
    def add_user_fact_deduplicated(self, fact: str, similarity_threshold=0.90, original_user_message: str = None):
        """Add user fact only if not too similar to existing facts."""
        if not fact or not isinstance(fact, str):
            return False

        if self._subject_gatekeeper(fact, original_user_message):
            logger.debug("Rejected user fact due to subject gatekeeper.")
            return False

        if self._looks_like_ai_fact(fact):
            logger.debug("Rejected user fact due to AI-referential phrasing.")
            return False
        
        fact_normalized = fact.lower().strip()
        
        # Check for EXACT duplicates first (fastest check)
        if self.user_memory.count() > 0:
            all_facts = self.user_memory.get()
            for existing_fact in all_facts.get("documents", []):
                if existing_fact.lower().strip() == fact_normalized:
                    logger.debug(f"Exact duplicate detected: {fact[:50]}")
                    return False
        
        # Check for high similarity duplicates
        if self.user_memory.count() > 0:
            results = self.user_memory.query(
                query_texts=[fact],
                n_results=1
            )
            
            if results['documents'] and results['distances']:
                distance = results['distances'][0][0]
                similarity = 1.0 - (distance / 2.0)
                
                if similarity > similarity_threshold:
                    logger.debug(f"Similar duplicate detected (similarity: {similarity:.2f}): {fact[:50]}")
                    return False
        
        # Add new fact with stable counter
        count = self.user_memory.count()
        timestamp = datetime.now().isoformat()
        
        self.user_memory.add(
            documents=[fact],
            ids=[f"user_fact_{count}_{os.urandom(2).hex()}"],
            metadatas=[{"timestamp": timestamp}]
        )
        logger.debug(f"Saved new user fact #{count}: {fact[:50]}")
        log_memory_write("user_memory", "add_user_fact_deduplicated", size_hint=len(fact or ""))
        return True
    
    def deduplicate_facts(self) -> int:
        """
        Clean up duplicate facts in user memory.
        Returns count of duplicates removed.
        """
        if self.user_memory.count() == 0:
            logger.info("No facts to deduplicate")
            return 0
        
        all_facts = self.user_memory.get()
        documents = all_facts.get("documents", [])
        ids_to_delete = []
        seen = {}
        
        for doc, doc_id in zip(documents, all_facts.get("ids", [])):
            doc_normalized = doc.lower().strip()
            
            if doc_normalized in seen:
                # This is a duplicate, mark for deletion
                ids_to_delete.append(doc_id)
                logger.debug(f"Marked for deletion (duplicate): {doc[:50]}")
            else:
                # First time seeing this fact
                seen[doc_normalized] = doc_id
        
        # Delete duplicates
        if ids_to_delete:
            self.user_memory.delete(ids=ids_to_delete)
            logger.info(f"Deduplication removed {len(ids_to_delete)} duplicate fact(s)")
        
        return len(ids_to_delete)

    def _looks_like_ai_fact(self, fact: str) -> bool:
        """Heuristic filter for AI-referential statements."""
        text = fact.lower()
        ai_markers = [
            "yuki", "the ai", "assistant", "this ai", "your system",
            "your model", "the system", "the model", "you are", "you have"
        ]

        if "yuki" in text and ("name" in text or "called" in text or "is the" in text):
            return True

        ai_keywords = ["memory", "cognitive", "programming", "system", "model", "architecture", "prompt"]
        has_marker = any(marker in text for marker in ai_markers)
        has_keyword = any(keyword in text for keyword in ai_keywords)

        return has_marker and has_keyword

    def _subject_gatekeeper(self, fact: str, original_user_message: str = None) -> bool:
        """Block AI-architecture facts derived from user questions."""
        if not original_user_message:
            return False

        msg = original_user_message.lower()
        if "you" not in msg and "your" not in msg:
            return False

        text = fact.lower()
        blocked_phrases = [
            "the user", "interest in personal growth",
            "memory options", "awareness"
        ]

        return any(phrase in text for phrase in blocked_phrases)

    def _is_trivial_fact(self, fact: str) -> bool:
        """Filter out trivial or low-value user facts."""
        text = fact.lower()
        
        if len(fact.strip()) < 15:
            return True
        
        trivial_patterns = [
            "user greeted", "user stated", "user said",
            "user expressed", "just chatting", "nothing in particular"
        ]
        
        return any(pattern in text for pattern in trivial_patterns)

    def purge_identity_confusion(self):
        """Remove AI/system-related facts that polluted user memory."""
        keywords = ["system", "cognitive", "programming", "memory", "model", "architecture", "prompt"]
        data = self.user_memory.get()

        if not data or not data.get("documents"):
            return 0

        ids_to_delete = []
        for doc, doc_id in zip(data["documents"], data["ids"]):
            doc_text = (doc or "").lower()
            if any(keyword in doc_text for keyword in keywords):
                ids_to_delete.append(doc_id)

        if ids_to_delete:
            self.user_memory.delete(ids=ids_to_delete)

        logger.debug(f"Purged {len(ids_to_delete)} identity-confused facts")
        return len(ids_to_delete)
    
    # ===== SESSION BUFFER INTEGRATION =====
    
    def add_to_session_buffer(self, content: str, source: str = "user", importance: float = 0.5):
        """Add message to session buffer for STM persistence."""
        entry = self.session_buffer.add_message(
            content=content,
            source=source,
            importance=importance
        )
        log_memory_write("session_buffer", "add_message", size_hint=len(content or ""), source=source)
        return entry
    
    def get_session_context(self, n_exchanges: int = 5) -> str:
        """Get recent conversation context from session buffer."""
        return self.session_buffer.get_context_window(n_exchanges=n_exchanges)
    
    def get_session_summary(self) -> dict:
        """Get session metadata and statistics."""
        return self.session_buffer.get_session_summary()
    
    def clear_old_sessions(self, days: int = 7) -> int:
        """Clear session messages older than N days."""
        return self.session_buffer.clear_old_messages(days=days)
    
    def reset_session(self) -> None:
        """Reset session buffer (start fresh conversation)."""
        self.session_buffer.reset_session()
    
    # ===== UNIFIED BACKEND INTERFACE =====
    
    async def memory_backend_health_check(self) -> dict:
        """Check backend health using unified interface."""
        return await self.backend.health_check()
    
    async def memory_backend_deduplicate(self, collection: str = "user_memory") -> int:
        """Deduplicate using unified backend interface."""
        return await self.backend.deduplicate(collection)
    
    async def memory_backend_rebuild(self) -> None:
        """Rebuild backend indices."""
        await self.backend.rebuild_indices()
    
    def set_memory_backend(self, backend: MemoryBackend) -> None:
        """Swap memory backend at runtime (for extensibility)."""
        self.backend = backend
        logger.info(f"Memory backend switched to {type(backend).__name__}")
    
    # ===== STATISTICS & STATUS =====
    
    def get_memory_stats(self) -> dict:
        """Get comprehensive memory statistics."""
        stats = {
            "user_facts": self.user_memory.count(),
            "episodic_memories": self.episodic_memory.count(),
            "knowledge_graph_nodes": len(self.knowledge_graph.graph.nodes),
            "knowledge_graph_edges": len(self.knowledge_graph.graph.edges),
            "active_tasks": self.task_scheduler.get_stats()["total_active"],
            "completed_tasks": self.task_scheduler.get_stats()["total_completed"],
            "interaction_count": self.interaction_count,
            "session_buffer": self.session_buffer.get_session_summary(),
            "backend_type": type(self.backend).__name__
        }
        return stats
    
    def get_memory_health(self) -> dict:
        """Get detailed memory health report."""
        result = {
            "status": "healthy",
            "issues": [],
            "details": {}
        }
        
        # Check if deduplication is needed
        user_facts = self.user_memory.get()
        if user_facts and user_facts.get("documents"):
            seen = set()
            duplicates = 0
            for doc in user_facts["documents"]:
                doc_norm = doc.lower().strip()
                if doc_norm in seen:
                    duplicates += 1
                else:
                    seen.add(doc_norm)
            
            if duplicates > 0:
                result["issues"].append(f"Found {duplicates} duplicate facts")
                result["status"] = "degraded" if duplicates > 5 else "healthy"
        
        # Check backend health
        try:
            import asyncio
            health = asyncio.run(self.backend.health_check())
            result["details"]["backend"] = health
        except Exception as e:
            result["issues"].append(f"Backend health check failed: {str(e)}")
            result["status"] = "degraded" if result["status"] == "healthy" else "critical"
        
        # Check session buffer health
        session_health = self.session_buffer.health_check()
        result["details"]["session_buffer"] = session_health
        
        return result

    # ====== OPTIMIZATION: Buffer Lifecycle Management ======
    
    async def start_buffer(self):
        """Start the memory buffer system for optimized I/O."""
        await self.memory_buffer.start()
        logger.info("Memory buffer started for optimized I/O operations")
    
    async def stop_buffer(self):
        """Stop the memory buffer and flush all pending operations."""
        await self.memory_buffer.stop()
        logger.info("Memory buffer stopped, all operations flushed")
    
    async def flush_buffer(self):
        """Manually flush all pending buffer operations."""
        await self.memory_buffer.flush_all()
        logger.debug("Memory buffer manually flushed")
    
    def get_buffer_stats(self):
        """Get memory buffer performance statistics."""
        return self.memory_buffer.get_stats()
