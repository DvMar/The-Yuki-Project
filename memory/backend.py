"""
Unified Memory Interface: Abstract base class for pluggable memory backends.
Inspired by memlayer's storage abstraction pattern.
Allows swapping different vector DBs, graph stores, or hybrid configurations.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from state.models import SearchResult, SearchResponse, SearchTierType


class MemoryBackend(ABC):
    """
    Abstract interface for memory storage backends.
    Implementations can use ChromaDB, Pinecone, Weaviate, etc.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the backend (async setup)."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close backend connections gracefully."""
        pass

    # ===== WRITE OPERATIONS =====

    @abstractmethod
    async def write(
        self,
        collection: str,
        content: str,
        metadata: Dict[str, Any] = None,
        document_id: str = None
    ) -> str:
        """
        Write a document to memory.

        Args:
            collection: Collection name ("user_memory", "self_memory", etc.)
            content: Document text
            metadata: Optional metadata dict
            document_id: Optional explicit document ID

        Returns:
            Document ID that was written
        """
        pass

    @abstractmethod
    async def write_batch(
        self,
        collection: str,
        documents: List[str],
        metadatas: List[Dict] = None,
        ids: List[str] = None
    ) -> List[str]:
        """
        Write multiple documents at once.

        Returns:
            List of document IDs that were written
        """
        pass

    # ===== READ OPERATIONS =====

    @abstractmethod
    async def search(
        self,
        query: str,
        collection: Optional[str] = None,
        n_results: int = 5,
        tier: SearchTierType = SearchTierType.BALANCED,
        where: Dict = None
    ) -> SearchResponse:
        """
        Search for documents across memory.

        Args:
            query: Search query string
            collection: Optional specific collection to search
            n_results: Number of results to return
            tier: Search tier (FAST, BALANCED, DEEP)
            where: Optional metadata filter

        Returns:
            SearchResponse with results and metadata
        """
        pass

    @abstractmethod
    async def get_by_id(self, collection: str, document_id: str) -> Optional[str]:
        """Retrieve a specific document by ID."""
        pass

    @abstractmethod
    async def get_collection(
        self,
        collection: str,
        limit: int = None
    ) -> List[Dict[str, Any]]:
        """Get all documents in a collection."""
        pass

    # ===== DELETE OPERATIONS =====

    @abstractmethod
    async def delete(self, collection: str, document_id: str) -> bool:
        """Delete a single document."""
        pass

    @abstractmethod
    async def delete_batch(self, collection: str, document_ids: List[str]) -> int:
        """Delete multiple documents. Returns count deleted."""
        pass

    @abstractmethod
    async def delete_collection(self, collection: str) -> int:
        """Delete all documents in a collection. Returns count deleted."""
        pass

    # ===== UTILITY OPERATIONS =====

    @abstractmethod
    async def count(self, collection: str) -> int:
        """Get document count in collection."""
        pass

    @abstractmethod
    async def deduplicate(self, collection: str) -> int:
        """Remove duplicate documents (by content hash). Returns count removed."""
        pass

    @abstractmethod
    async def rebuild_indices(self) -> None:
        """Rebuild any indices/embeddings (for optimization)."""
        pass

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """
        Run health check on backend.

        Returns:
            {"healthy": bool, "issues": List[str], "details": Dict}
        """
        pass

    # ===== GRAPH OPERATIONS (Optional for Graph-capable backends) =====

    @abstractmethod
    async def add_entity(
        self,
        name: str,
        entity_type: str,
        metadata: Dict = None
    ) -> str:
        """Add entity to knowledge graph (if backend supports it)."""
        pass

    @abstractmethod
    async def add_relationship(
        self,
        subject: str,
        predicate: str,
        object: str,
        metadata: Dict = None
    ) -> str:
        """Add relationship to knowledge graph (if backend supports it)."""
        pass

    @abstractmethod
    async def traverse_graph(
        self,
        start_node: str,
        max_depth: int = 2
    ) -> Dict[str, Any]:
        """Traverse knowledge graph from a node (if backend supports it)."""
        pass


class ChromaDBBackend(MemoryBackend):
    """
    Concrete implementation using ChromaDB + NetworkX.
    This is the default backend for The Yuki Project/Yuki.
    """

    def __init__(
        self,
        db_path: str = "./persistent_state",
        embedding_model: str = "all-MiniLM-L6-v2",
        embed_fn=None
    ):
        """
        Initialize ChromaDB backend.

        Args:
            db_path: Path to database directory
            embedding_model: HuggingFace model name for embeddings
            embed_fn: Pre-built ChromaDB embedding function (overrides embedding_model)
        """
        self.db_path = db_path
        self.embedding_model_name = embedding_model
        self.client = None
        self.collections = {}
        self.kg = None  # Knowledge graph instance
        self.embed_fn = embed_fn  # May be injected externally (e.g. llama_cpp_embed)

    async def initialize(self) -> None:
        """Initialize ChromaDB and embedding function."""
        import os
        import chromadb
        from chromadb.config import Settings
        from chromadb.utils import embedding_functions
        from memory.knowledge_graph import KnowledgeGraph

        if not os.path.exists(self.db_path):
            os.makedirs(self.db_path)

        # Suppress transformers/HF noise
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
        os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

        import logging
        logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
        logging.getLogger("transformers").setLevel(logging.ERROR)
        logging.getLogger("sentence_transformers").setLevel(logging.ERROR)

        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=self.db_path,
            settings=Settings(anonymized_telemetry=False)
        )

        # Initialize embedding function (use injected one if provided)
        if self.embed_fn is None:
            self.embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=self.embedding_model_name
            )

        # Get/create default collections
        self.collections["user_memory"] = self.client.get_or_create_collection(
            name="user_memory",
            embedding_function=self.embed_fn
        )
        self.collections["self_memory"] = self.client.get_or_create_collection(
            name="self_memory",
            embedding_function=self.embed_fn
        )
        self.collections["episodic_memory"] = self.client.get_or_create_collection(
            name="episodic_memory",
            embedding_function=self.embed_fn
        )

        # Initialize knowledge graph
        self.kg = KnowledgeGraph(db_path=self.db_path)

    async def close(self) -> None:
        """Clean up resources."""
        if self.client:
            self.client = None
        if self.kg:
            await self.kg.close() if hasattr(self.kg, 'close') else None

    async def write(
        self,
        collection: str,
        content: str,
        metadata: Dict[str, Any] = None,
        document_id: str = None
    ) -> str:
        """Write document to ChromaDB collection."""
        import uuid

        if collection not in self.collections:
            self.collections[collection] = self.client.get_or_create_collection(
                name=collection,
                embedding_function=self.embed_fn
            )

        doc_id = document_id or str(uuid.uuid4())
        meta = metadata or {}

        self.collections[collection].add(
            ids=[doc_id],
            documents=[content],
            metadatas=[meta]
        )

        return doc_id

    async def write_batch(
        self,
        collection: str,
        documents: List[str],
        metadatas: List[Dict] = None,
        ids: List[str] = None
    ) -> List[str]:
        """Write multiple documents to ChromaDB."""
        import uuid

        if collection not in self.collections:
            self.collections[collection] = self.client.get_or_create_collection(
                name=collection,
                embedding_function=self.embed_fn
            )

        doc_ids = ids or [str(uuid.uuid4()) for _ in documents]
        metas = metadatas or [{} for _ in documents]

        self.collections[collection].add(
            ids=doc_ids,
            documents=documents,
            metadatas=metas
        )

        return doc_ids

    async def search(
        self,
        query: str,
        collection: Optional[str] = None,
        n_results: int = 5,
        tier: SearchTierType = SearchTierType.BALANCED,
        where: Dict = None
    ) -> SearchResponse:
        """Search across ChromaDB collections."""
        import time

        start_time = time.time()
        all_results = []

        # Determine search scope
        search_collections = [collection] if collection else list(self.collections.keys())

        for coll_name in search_collections:
            if coll_name not in self.collections:
                continue

            try:
                response = self.collections[coll_name].query(
                    query_texts=[query],
                    n_results=n_results,
                    where=where
                )

                if response and response.get("documents"):
                    for i, doc in enumerate(response["documents"][0]):
                        score = response["distances"][0][i] if response.get("distances") else 0.9
                        # Convert distance to similarity (lower distance = higher similarity)
                        similarity = 1.0 / (1.0 + score)

                        all_results.append(SearchResult(
                            id=response["ids"][0][i],
                            text=doc,
                            source=coll_name,
                            score=similarity,
                            metadata=response["metadatas"][0][i] if response.get("metadatas") else {}
                        ))
            except Exception as e:
                import logging
                logging.error(f"Error searching {coll_name}: {e}")
                continue

        # Sort by score descending
        all_results.sort(key=lambda x: x.score, reverse=True)
        all_results = all_results[:n_results]

        duration_ms = (time.time() - start_time) * 1000

        return SearchResponse(
            results=all_results,
            tier_used=tier,
            duration_ms=duration_ms,
            vector_results_count=len(all_results),
            events=[
                {"event": "search_complete", "collections_searched": len(search_collections)}
            ]
        )

    async def get_by_id(self, collection: str, document_id: str) -> Optional[str]:
        """Get document by ID."""
        if collection not in self.collections:
            return None

        result = self.collections[collection].get(ids=[document_id])
        if result and result.get("documents"):
            return result["documents"][0]
        return None

    async def get_collection(
        self,
        collection: str,
        limit: int = None
    ) -> List[Dict[str, Any]]:
        """Get all documents in a collection."""
        if collection not in self.collections:
            return []

        result = self.collections[collection].get()
        documents = []

        if result.get("documents"):
            for i, doc in enumerate(result["documents"]):
                documents.append({
                    "id": result["ids"][i],
                    "text": doc,
                    "metadata": result["metadatas"][i] if result.get("metadatas") else {}
                })

        return documents[:limit] if limit else documents

    async def delete(self, collection: str, document_id: str) -> bool:
        """Delete a document."""
        if collection not in self.collections:
            return False

        try:
            self.collections[collection].delete(ids=[document_id])
            return True
        except Exception:
            return False

    async def delete_batch(self, collection: str, document_ids: List[str]) -> int:
        """Delete multiple documents."""
        if collection not in self.collections or not document_ids:
            return 0

        try:
            self.collections[collection].delete(ids=document_ids)
            return len(document_ids)
        except Exception:
            return 0

    async def delete_collection(self, collection: str) -> int:
        """Delete entire collection."""
        if collection not in self.collections:
            return 0

        count = self.collections[collection].count()
        try:
            self.client.delete_collection(name=collection)
            del self.collections[collection]
            return count
        except Exception:
            return 0

    async def count(self, collection: str) -> int:
        """Count documents in collection."""
        if collection not in self.collections:
            return 0
        return self.collections[collection].count()

    async def deduplicate(self, collection: str) -> int:
        """Remove duplicates from collection."""
        if collection not in self.collections:
            return 0

        result = self.collections[collection].get()
        if not result.get("documents"):
            return 0

        seen = set()
        to_delete = []

        for i, doc in enumerate(result["documents"]):
            doc_hash = hash(doc)
            if doc_hash in seen:
                to_delete.append(result["ids"][i])
            else:
                seen.add(doc_hash)

        deleted = await self.delete_batch(collection, to_delete)
        return deleted

    async def rebuild_indices(self) -> None:
        """Rebuild ChromaDB indices."""
        # ChromaDB rebuilds automatically, but we can compact
        for collection in self.collections.values():
            try:
                collection.get()  # Forces index rebuild
            except Exception:
                pass

    async def health_check(self) -> Dict[str, Any]:
        """Check backend health."""
        issues = []
        healthy = True

        try:
            for coll_name, coll in self.collections.items():
                count = coll.count()
                if count < 0:
                    issues.append(f"Collection {coll_name} has invalid count")
                    healthy = False
        except Exception as e:
            issues.append(f"ChromaDB access error: {str(e)}")
            healthy = False

        return {
            "healthy": healthy,
            "issues": issues,
            "details": {
                "backend": "ChromaDB",
                "collections": len(self.collections),
                "total_documents": sum(
                    coll.count() for coll in self.collections.values()
                )
            }
        }

    async def add_entity(
        self,
        name: str,
        entity_type: str,
        metadata: Dict = None
    ) -> str:
        """Add entity to knowledge graph."""
        if self.kg:
            return self.kg.add_entity(name, entity_type=entity_type, metadata=metadata)
        return ""

    async def add_relationship(
        self,
        subject: str,
        predicate: str,
        object: str,
        metadata: Dict = None
    ) -> str:
        """Add relationship to knowledge graph."""
        if self.kg:
            return self.kg.add_relationship(subject, predicate, object, metadata=metadata)
        return ""

    async def traverse_graph(
        self,
        start_node: str,
        max_depth: int = 2
    ) -> Dict[str, Any]:
        """Traverse knowledge graph."""
        if self.kg:
            return self.kg.traverse(start_node, max_depth=max_depth)
        return {"nodes": [], "edges": []}
