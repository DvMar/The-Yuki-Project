"""
Pydantic models for The Yuki Project data structures.
Provides type safety and validation for all memory-related operations.
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from datetime import datetime
from enum import Enum


# ====== SEARCH & RETRIEVAL ======

class SearchResult(BaseModel):
    """Represents a single search result."""
    id: str
    text: str
    source: str  # "user_memory", "self_memory", "episodic_memory", "graph"
    score: float
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SearchTierType(str, Enum):
    """Search tier enumeration."""
    FAST = "fast"
    BALANCED = "balanced"
    DEEP = "deep"
    AUTO = "auto"


class SearchResponse(BaseModel):
    """Unified search response with metadata and trace."""
    results: List[SearchResult]
    tier_used: SearchTierType
    duration_ms: float
    vector_results_count: int
    graph_results_count: int = 0
    events: List[Dict[str, Any]] = Field(default_factory=list)


# ====== MEMORY OPERATIONS ======

class MemoryStorageType(str, Enum):
    """Memory storage backend type."""
    VECTOR = "vector"  # ChromaDB/vector-only
    GRAPH = "graph"    # NetworkX/graph-only
    HYBRID = "hybrid"  # Both vector + graph


class MemoryModeType(str, Enum):
    """Operation mode for memory filtering and storage."""
    LOCAL = "local"      # Local embeddings (sentence-transformers)
    ONLINE = "online"    # API embeddings (would require external)
    LIGHTWEIGHT = "lightweight"  # Keyword-only


class MemoryStats(BaseModel):
    """Statistics about current memory state."""
    user_memory_count: int
    self_memory_count: int
    episodic_memory_count: int
    knowledge_graph_nodes: int
    knowledge_graph_edges: int
    total_facts: int
    duplicate_facts: int
    session_buffer_size: int


# ====== KNOWLEDGE EXTRACTION ======

class FactExtraction(BaseModel):
    """Extracted fact from text."""
    fact: str
    confidence: float
    timestamp: Optional[datetime] = None


class EntityExtraction(BaseModel):
    """Extracted entity from text."""
    name: str
    entity_type: str  # "person", "organization", "event", etc.
    confidence: float


class RelationshipExtraction(BaseModel):
    """Extracted relationship between entities."""
    subject: str
    predicate: str  # e.g., "works_at", "located_in"
    object: str
    confidence: float


class ConsolidationResult(BaseModel):
    """Result of text consolidation (fact/entity/relationship extraction)."""
    facts: List[FactExtraction]
    entities: List[EntityExtraction]
    relationships: List[RelationshipExtraction]
    overall_confidence: float
    source_text: Optional[str] = None
    timestamp: Optional[datetime] = None


# ====== SALIENCE & FILTERING ======

class SalienceScore(BaseModel):
    """Salience evaluation result."""
    should_save: bool
    score: float  # -1.0 to 1.0
    reasoning: Optional[str] = None
    category: Optional[str] = None  # "personal", "decision", "event", etc.


# ====== MESSAGE ORIGIN & METADATA ======

class MessageOrigin(str, Enum):
    """Source/origin of a message."""
    USER = "user"
    ASSISTANT = "assistant"
    DREAMCYCLE = "dreamcycle"  # Self-initiated from Dream Cycle daemon


class ChatMessage(BaseModel):
    """Chat message with origin metadata."""
    role: str  # "user" or "assistant"
    content: str
    origin: MessageOrigin = MessageOrigin.USER  # Default to user for backward compatibility
    internal: bool = False  # Is this an internal/self-initiated message?
    timestamp: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ====== SESSION STATE ======

class SessionMemoryEntry(BaseModel):
    """Entry in session/short-term memory buffer."""
    id: str
    content: str
    timestamp: datetime
    source: str  # "user" or "ai" or "dreamcycle"
    importance: float = 0.5
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SessionState(BaseModel):
    """Session state for working memory persistence."""
    session_id: str
    created_at: datetime
    last_updated: datetime
    messages: List[SessionMemoryEntry]
    context_window: int = 10
    total_exchanges: int = 0


# ====== TASK SCHEDULING ======

class TaskReminder(BaseModel):
    """Proactive task reminder."""
    task_id: str
    description: str
    due_date: datetime
    created_at: datetime
    is_active: bool = True
    check_frequency_seconds: int = 3600


# ====== MEMORY OPERATIONS INTERFACE ======

class MemoryWriteRequest(BaseModel):
    """Generic memory write operation."""
    content: str
    collection: str  # "user", "self", "episodic"
    metadata: Dict[str, Any] = Field(default_factory=dict)
    check_salience: bool = True


class MemoryReadRequest(BaseModel):
    """Generic memory read operation."""
    query: str
    collection: Optional[str] = None  # None = search all
    n_results: int = 5
    tier: SearchTierType = SearchTierType.BALANCED
    use_graph: bool = False


# ====== MEMORY HEALTH ======

class MemoryHealthReport(BaseModel):
    """Comprehensive memory health report."""
    status: str  # "healthy", "degraded", "critical"
    total_facts: int
    duplicates: int
    missing_indices: int
    corrupted_entries: int
    last_check: datetime
    recommendations: List[str] = Field(default_factory=list)


# ====== IDENTITY & STATE ======

class PersonalityTrait(BaseModel):
    """Single personality trait."""
    name: str
    value: float  # 0.0 to 1.0
    timestamp: Optional[datetime] = None


class EmotionalDimension(BaseModel):
    """Single emotional dimension."""
    name: str
    value: float  # 0.0 to 1.0
    timestamp: Optional[datetime] = None


class IdentityCore(BaseModel):
    """AI's identity core (personality)."""
    name: str
    traits: Dict[str, float]  # trait_name -> value
    description: Optional[str] = None
    last_updated: Optional[datetime] = None


class EmotionalState(BaseModel):
    """AI's emotional state."""
    dimensions: Dict[str, float]  # dimension_name -> value
    stability: float
    last_updated: Optional[datetime] = None
