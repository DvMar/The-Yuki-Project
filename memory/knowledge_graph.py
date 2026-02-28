"""
Knowledge Graph: Entity and relationship management using NetworkX.
Stores structured knowledge as a directed graph for relationship queries.
"""

import logging
import os
from typing import Dict, List
import networkx as nx
from datetime import datetime

logger = logging.getLogger(__name__)

class KnowledgeGraph:
    """
    Persistent knowledge graph using NetworkX.
    Stores entities (nodes) and relationships (edges) for semantic navigation.
    """
    
    # Entity types for classification
    ENTITY_TYPES = {
        "person": "A person (name, character)",
        "location": "A geographical location or place",
        "organization": "A company, group, or organization",
        "concept": "An abstract concept or idea",
        "event": "An event or occurrence",
        "object": "A physical or digital object",
        "skill": "A capability or expertise",
        "preference": "A like, dislike, or preference"
    }
    
    # Relationship types for classification
    RELATION_TYPES = {
        "is_a": "Classification relationship",
        "located_in": "Location relationship",
        "works_at": "Employment relationship",
        "related_to": "General relation",
        "has_skill": "Possession of skill",
        "prefers": "Preference relationship",
        "knows": "Acquaintance relationship",
        "created": "Creation relationship",
        "participates_in": "Participation relationship"
    }
    
    def __init__(self, db_path: str = "./persistent_state"):
        """
        Initialize knowledge graph.
        
        Args:
            db_path: Path to directory for persistence
        """
        self.db_path = db_path
        self.graph_path = os.path.join(db_path, "knowledge_graph.graphml")
        
        # Initialize or load graph
        if os.path.exists(self.graph_path):
            try:
                self.graph = nx.read_graphml(self.graph_path)
                logger.info(f"Loaded knowledge graph with {len(self.graph.nodes)} nodes")
            except Exception as e:
                logger.warning(f"Failed to load knowledge graph: {e}. Creating new.")
                self.graph = nx.DiGraph()
        else:
            self.graph = nx.DiGraph()
        
        # Statistics
        self.statistics = {
            "total_entities": 0,
            "total_relationships": 0,
            "last_updated": ""
        }
    
    def add_entity(
        self,
        name: str,
        entity_type: str = "concept",
        metadata: Dict = None
    ) -> bool:
        """
        Add entity (node) to knowledge graph.
        
        Args:
            name: Entity name/identifier
            entity_type: Type from ENTITY_TYPES
            metadata: Additional metadata dict
        
        Returns:
            True if added, False if already exists
        """
        if not name or not isinstance(name, str):
            return False
        
        name = name.strip()
        if not name:
            return False
        
        # Normalize to lowercase for consistency
        node_id = name.lower()
        
        # Check if already exists
        if node_id in self.graph.nodes:
            # Update metadata if provided
            if metadata:
                self.graph.nodes[node_id].update(metadata)
            return False
        
        # Add node with attributes
        attrs = {
            "name": name,
            "type": entity_type if entity_type in self.ENTITY_TYPES else "concept",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        if metadata:
            attrs.update(metadata)
        
        self.graph.add_node(node_id, **attrs)
        self.statistics["total_entities"] += 1
        self._update_timestamp()
        
        logger.debug(f"Added entity: {name} (type: {entity_type})")
        return True
    
    def add_relationship(
        self,
        source: str,
        target: str,
        relation_type: str = "related_to",
        metadata: Dict = None
    ) -> bool:
        """
        Add relationship (directed edge) between entities.
        Automatically creates entities if they don't exist.
        
        Args:
            source: Source entity name
            target: Target entity name
            relation_type: Type from RELATION_TYPES
            metadata: Additional metadata
        
        Returns:
            True if added
        """
        if not source or not target:
            return False
        
        source_id = source.strip().lower()
        target_id = target.strip().lower()
        
        if source_id == target_id:
            return False  # No self-loops
        
        # Create entities if needed
        if source_id not in self.graph.nodes:
            self.add_entity(source, "concept")
        if target_id not in self.graph.nodes:
            self.add_entity(target, "concept")
        
        # Check if edge already exists
        if self.graph.has_edge(source_id, target_id):
            # Update metadata if provided
            if metadata:
                self.graph[source_id][target_id].update(metadata)
            return False
        
        # Add edge with attributes
        attrs = {
            "type": relation_type if relation_type in self.RELATION_TYPES else "related_to",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        if metadata:
            attrs.update(metadata)
        
        self.graph.add_edge(source_id, target_id, **attrs)
        self.statistics["total_relationships"] += 1
        self._update_timestamp()
        
        logger.debug(f"Added relationship: {source} --[{relation_type}]--> {target}")
        return True
    
    def get_entity(self, name: str) -> Dict:
        """Get entity attributes."""
        node_id = name.strip().lower()
        
        if node_id not in self.graph.nodes:
            return None
        
        attrs = dict(self.graph.nodes[node_id])
        
        # Include relationships
        attrs["outgoing"] = list(self.graph.successors(node_id))
        attrs["incoming"] = list(self.graph.predecessors(node_id))
        
        return attrs
    
    def get_relationships(
        self,
        entity: str,
        relation_type: str = None,
        direction: str = "both"
    ) -> List[Dict]:
        """
        Get relationships for an entity.
        
        Args:
            entity: Entity name
            relation_type: Filter by type (optional)
            direction: "out" (outgoing), "in" (incoming), or "both"
        
        Returns:
            List of relationship dicts
        """
        node_id = entity.strip().lower()
        
        if node_id not in self.graph.nodes:
            return []
        
        relationships = []
        
        if direction in {"out", "both"}:
            # Outgoing edges
            for successor in self.graph.successors(node_id):
                edge_attrs = dict(self.graph[node_id][successor])
                
                if relation_type and edge_attrs.get("type") != relation_type:
                    continue
                
                rel = {
                    "source": entity,
                    "target": self.graph.nodes[successor].get("name", successor),
                    "type": edge_attrs.get("type", "related_to"),
                    "metadata": edge_attrs
                }
                relationships.append(rel)
        
        if direction in {"in", "both"}:
            # Incoming edges
            for predecessor in self.graph.predecessors(node_id):
                edge_attrs = dict(self.graph[predecessor][node_id])
                
                if relation_type and edge_attrs.get("type") != relation_type:
                    continue
                
                rel = {
                    "source": self.graph.nodes[predecessor].get("name", predecessor),
                    "target": entity,
                    "type": edge_attrs.get("type", "related_to"),
                    "metadata": edge_attrs
                }
                relationships.append(rel)
        
        return relationships
    
    def find_paths(
        self,
        source: str,
        target: str,
        max_depth: int = 2
    ) -> List[List[str]]:
        """
        Find paths between two entities (up to max_depth hops).
        
        Args:
            source: Starting entity
            target: Ending entity
            max_depth: Maximum path length
        
        Returns:
            List of paths (each path is a list of entity names)
        """
        source_id = source.strip().lower()
        target_id = target.strip().lower()
        
        if source_id not in self.graph or target_id not in self.graph:
            return []
        
        try:
            # Use NetworkX to find simple paths
            all_paths = nx.all_simple_paths(
                self.graph,
                source_id,
                target_id,
                cutoff=max_depth
            )
            
            # Convert node IDs back to names
            paths = []
            for path in all_paths:
                named_path = [
                    self.graph.nodes[node_id].get("name", node_id)
                    for node_id in path
                ]
                paths.append(named_path)
            
            return paths[:10]  # Limit to 10 paths
        except nx.NetworkXNoPath:
            return []
    
    def extract_from_text(
        self,
        facts: List[str],
        entities: List[Dict],
        relationships: List[Dict]
    ) -> int:
        """
        Bulk add extracted knowledge from consolidation.
        Used by consolidation service to add facts/entities/relationships.
        
        Args:
            facts: List of fact strings (for logging)
            entities: List of {name, type, metadata} dicts
            relationships: List of {source, target, type, metadata} dicts
        
        Returns:
            Total items added
        """
        added = 0
        
        # Add entities
        for entity in entities:
            if self.add_entity(
                entity.get("name"),
                entity.get("type", "concept"),
                entity.get("metadata")
            ):
                added += 1
        
        # Add relationships
        for rel in relationships:
            if self.add_relationship(
                rel.get("source"),
                rel.get("target"),
                rel.get("type", "related_to"),
                rel.get("metadata")
            ):
                added += 1
        
        logger.info(f"Extracted {added} items into knowledge graph from {len(facts)} facts")
        return added
    
    def get_stats(self) -> Dict:
        """Get knowledge graph statistics."""
        return {
            "total_nodes": len(self.graph.nodes),
            "total_edges": len(self.graph.edges),
            "density": nx.density(self.graph),
            "num_connected_components": nx.number_connected_components(self.graph.to_undirected()),
            "last_updated": self.statistics.get("last_updated", "")
        }
    
    def persist(self):
        """Save knowledge graph to disk."""
        try:
            nx.write_graphml(self.graph, self.graph_path)
            logger.info("Knowledge graph persisted")
        except Exception as e:
            logger.error(f"Failed to persist knowledge graph: {e}")
    
    def _update_timestamp(self):
        """Update last modified timestamp."""
        self.statistics["last_updated"] = datetime.now().isoformat()
