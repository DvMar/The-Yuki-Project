"""
Hybrid Search: Combines vector similarity search with knowledge graph traversal.
Three search tiers (Fast, Balanced, Deep) for different latency requirements.
"""

import logging
from typing import Dict, List
from enum import Enum
import time

logger = logging.getLogger(__name__)

class SearchTier(Enum):
    """Search tier definitions."""
    FAST = "fast"          # <100ms, 2 vector results
    BALANCED = "balanced"   # <500ms, 5 vector results  (DEFAULT)
    DEEP = "deep"           # <2s, 10 vector + graph traversal
    AUTO = "auto"           # Automatically choose based on query


class HybridSearch:
    """
    Intelligent search across vector and knowledge graph storage.
    Automatically selects search tier based on query complexity.
    """
    
    def __init__(self, chroma_collections, knowledge_graph):
        """
        Initialize hybrid search.
        
        Args:
            chroma_collections: ChromaDB collection or dict of named collections
            knowledge_graph: KnowledgeGraph instance for entity traversal
        """
        if isinstance(chroma_collections, dict):
            self.collections = {
                str(name): coll for name, coll in chroma_collections.items() if coll is not None
            }
        else:
            self.collections = {"user_memory": chroma_collections}
        self.kg = knowledge_graph
        self.last_trace = None
    
    def search(
        self,
        query: str,
        tier: str = SearchTier.AUTO.value,
        n_results: int = None,
        graph_traverse: bool = False,
        collections: List[str] = None,
    ) -> Dict:
        """
        Unified search across vector and graph stores.
        
        Args:
            query: Search query string
            tier: SearchTier ("fast", "balanced", "deep", "auto")
            n_results: Override number of results
            graph_traverse: Force knowledge graph traversal
        
        Returns:
            Dictionary with:
            - results: List of found documents
            - metadata: Source and relevance info
            - tier_used: Actual tier used
            - duration_ms: Total search time
            - events: Detailed trace of operations
        """
        start_time = time.time()
        events = []
        
        # Auto-detect tier based on query
        if tier == SearchTier.AUTO.value:
            tier = self._detect_tier(query)
            events.append({"event": "tier_auto_detected", "tier": tier})
        
        # Validate tier
        valid_tiers = [t.value for t in SearchTier if t != SearchTier.AUTO]
        if tier not in valid_tiers:
            tier = SearchTier.BALANCED.value
        
        # Determine search parameters
        params = self._get_tier_params(tier, n_results)
        events.append({
            "event": "tier_selected",
            "tier": tier,
            "vector_results": params["vector_results"],
            "enable_graph": params["enable_graph"]
        })
        
        results = []
        metadata = {"sources": [], "combined": False}
        
        # 1. Vector similarity search
        vector_results = self._vector_search(
            query,
            n_results=params["vector_results"],
            collections=collections,
        )
        events.append({
            "event": "vector_search_complete",
            "duration_ms": (time.time() - start_time) * 1000,
            "results_count": len(vector_results)
        })
        
        results.extend(vector_results)
        metadata["sources"].append("vector")
        
        # 2. Knowledge graph traversal (if enabled)
        if params["enable_graph"] or graph_traverse:
            graph_results = self._graph_search(query, depth=params["graph_depth"])
            
            events.append({
                "event": "graph_search_complete",
                "duration_ms": (time.time() - start_time) * 1000,
                "results_count": len(graph_results)
            })
            
            if graph_results:
                results.extend(graph_results)
                metadata["combined"] = True
                metadata["sources"].append("knowledge_graph")
        
        # Calculate total duration
        duration_ms = (time.time() - start_time) * 1000
        
        trace = {
            "query": query,
            "tier": tier,
            "results": results,
            "metadata": metadata,
            "duration_ms": duration_ms,
            "events": events
        }
        self.last_trace = trace
        
        return trace

    def _detect_tier(self, query: str) -> str:
        """
        Auto-detect search tier based on query characteristics.
        
        Rules:
        - Short/simple queries → FAST
        - Medium queries → BALANCED
        - Complex queries (multi-entity, relationships) → DEEP
        """
        # Heuristics
        words = query.lower().split()
        word_count = len(words)
        
        # Look for relationship indicators
        has_relationship = any(
            keyword in query.lower()
            for keyword in ["related", "connected", "between", "all about", "everything", "connections"]
        )
        
        has_entities = any(keyword in query.lower() for keyword in ["who", "what", "where"])
        
        # Decision logic
        if word_count <= 3 and not has_relationship:
            return SearchTier.FAST.value
        elif has_relationship or (word_count > 5 and has_entities):
            return SearchTier.DEEP.value
        else:
            return SearchTier.BALANCED.value
    
    def _get_tier_params(self, tier: str, n_results: int = None) -> Dict:
        """Get search parameters for given tier."""
        tier_configs = {
            SearchTier.FAST.value: {
                "vector_results": 2,
                "enable_graph": False,
                "graph_depth": 0,
                "timeout_ms": 100
            },
            SearchTier.BALANCED.value: {
                "vector_results": 5,
                "enable_graph": False,
                "graph_depth": 0,
                "timeout_ms": 500
            },
            SearchTier.DEEP.value: {
                "vector_results": 10,
                "enable_graph": True,
                "graph_depth": 1,
                "timeout_ms": 2000
            }
        }
        
        params = tier_configs.get(tier, tier_configs[SearchTier.BALANCED.value])
        
        # Override from parameter
        if n_results:
            params["vector_results"] = n_results
        
        return params
    
    def _vector_search(self, query: str, n_results: int = 5, collections: List[str] = None) -> List[Dict]:
        """
        Vector similarity search via ChromaDB.
        
        Returns:
            List of {text, score, metadata} dicts
        """
        try:
            target_names = collections or list(self.collections.keys())
            aggregated = []

            for name in target_names:
                coll = self.collections.get(name)
                if coll is None:
                    continue
                try:
                    if coll.count() == 0:
                        continue

                    results = coll.query(query_texts=[query], n_results=n_results)
                    if not results or not results.get("documents"):
                        continue

                    documents = results["documents"][0]
                    distances = results.get("distances", [[]])[0] if results.get("distances") else []
                    metadatas = results.get("metadatas", [[]])[0] if results.get("metadatas") else []

                    for i, doc in enumerate(documents):
                        distance = distances[i] if i < len(distances) else 0.0
                        similarity = max(0.0, 1.0 - (distance / 2.0))
                        aggregated.append({
                            "text": doc,
                            "score": float(similarity),
                            "metadata": metadatas[i] if i < len(metadatas) else {},
                            "source": name,
                        })
                except Exception as inner_e:
                    logger.error(f"Vector search failed for collection '{name}': {inner_e}")

            aggregated.sort(key=lambda item: item.get("score", 0.0), reverse=True)
            return aggregated[:n_results]
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []
    
    def _graph_search(self, query: str, depth: int = 1) -> List[Dict]:
        """
        Knowledge graph traversal search.
        Extracts entities from query and finds related information.
        
        Returns:
            List of {text, score, metadata} dicts
        """
        graph_results = []
        
        try:
            # Simple entity extraction from query
            # (In production, use NER or embeddings for better extraction)
            query_lower = query.lower()
            
            # Find entities matching query terms
            for node_id, node_attrs in self.kg.graph.nodes(data=True):
                node_name = node_attrs.get("name", node_id)
                
                # Check if node matches query
                if node_name.lower() in query_lower or any(
                    term.lower() == node_name.lower()
                    for term in query_lower.split()
                ):
                    # Found a matching entity, traverse relationships
                    rels = self.kg.get_relationships(node_name)
                    
                    for rel in rels:
                        result_text = f"{rel['source']} {rel['type']} {rel['target']}"
                        graph_results.append({
                            "text": result_text,
                            "score": 0.5,  # Default score for graph results
                            "metadata": {
                                "source_entity": rel["source"],
                                "target_entity": rel["target"],
                                "relation": rel["type"]
                            },
                            "source": "knowledge_graph"
                        })
            
            # Limit results
            return graph_results[:10]
        
        except Exception as e:
            logger.debug(f"Graph search failed: {e}")
            return []
    
    def get_search_stats(self) -> Dict:
        """Return a small summary of the most recent search for UI display."""
        if not self.last_trace:
            return {}

        results = self.last_trace.get("results", [])
        duration_ms = self.last_trace.get("duration_ms")

        return {
            "tier": self.last_trace.get("tier", "-"),
            "duration_ms": int(duration_ms) if duration_ms is not None else None,
            "total_results": len(results)
        }
