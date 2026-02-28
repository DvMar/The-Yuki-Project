"""
Consolidation Service: Automatic extraction of facts, entities, and relationships.
Backgroundable pipeline for knowledge extraction from conversations.
"""

import logging
import json
import re
from typing import Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)

class ConsolidationService:
    """
    Extracts structured knowledge from text.
    Uses LLM for fact/entity/relationship extraction with confidence scoring.
    """
    
    def __init__(self, llm_client):
        """
        Initialize consolidation service.
        
        Args:
            llm_client: LLMClient instance for extraction
        """
        self.llm_client = llm_client
        self.extraction_count = 0
    
    async def consolidate(
        self,
        text: str,
        metadata: Dict = None
    ) -> Dict:
        """
        Extract facts, entities, and relationships from text.
        
        Args:
            text: Text to extract from
            metadata: Optional metadata (e.g., timestamp, user)
        
        Returns:
            Dictionary with:
            - facts: List of factual statements
            - entities: List of {name, type} dicts
            - relationships: List of {source, target, type} dicts
            - confidence: Overall extraction confidence
            - raw_extraction: Raw LLM response for debugging
        """
        if not text or len(text.strip()) < 10:
            return {
                "facts": [],
                "entities": [],
                "relationships": [],
                "confidence": 0.0,
                "raw_extraction": ""
            }
        
        try:
            # Call LLM for extraction
            extraction = await self._extract_with_llm(text)
            
            if not extraction:
                return {
                    "facts": [],
                    "entities": [],
                    "relationships": [],
                    "confidence": 0.0,
                    "raw_extraction": ""
                }
            
            self.extraction_count += 1
            
            return {
                "facts": extraction.get("facts", []),
                "entities": extraction.get("entities", []),
                "relationships": extraction.get("relationships", []),
                "confidence": extraction.get("confidence", 0.5),
                "raw_extraction": extraction.get("raw", "")
            }
        
        except Exception as e:
            logger.error(f"Consolidation failed: {e}")
            return {
                "facts": [],
                "entities": [],
                "relationships": [],
                "confidence": 0.0,
                "raw_extraction": ""
            }
    
    async def _extract_with_llm(self, text: str) -> Dict:
        """
        Use LLM to extract facts, entities, and relationships.
        
        Returns:
            Extracted data dict or None on failure
        """
        prompt = f"""Analyze this text and extract structured knowledge:

TEXT TO ANALYZE:
"{text}"

EXTRACTION INSTRUCTIONS:

1. FACTS: Extract key factual statements (standalone truths stated)
   - Include personal information (name, location, job, interests, goals)
   - Include decisions, plans, or commitments
   - Ignore greetings, questions, or vague statements
   - Max 5 facts

2. ENTITIES: Extract named entities and classify by type
   - Types: person, location, organization, concept, skill, event, object
   - Each entity: {{"name": "...", "type": "..."}}
   - Max 10 entities

3. RELATIONSHIPS: Extract entity relationships
   - Format: {{"source": "entity1", "target": "entity2", "type": "relation_type"}}
   - Types: works_at, located_in, knows, has_skill, interested_in, created, participates_in, related_to
   - Only extract clear relationships
   - Max 5 relationships

4. CONFIDENCE: Overall extraction confidence (0.0-1.0)
   - 0.9-1.0: Very clear and complete extraction
   - 0.7-0.9: Clear extraction with some ambiguity
   - 0.5-0.7: Partial extraction with some gaps
   - <0.5: Uncertain or low-quality extraction

Return ONLY a JSON object (no markdown, no explanation):
{{
  "facts": ["fact1", "fact2"],
  "entities": [{{"name": "Alice", "type": "person"}}, {{"name": "London", "type": "location"}}],
  "relationships": [{{"source": "Alice", "target": "London", "type": "located_in"}}],
  "confidence": 0.8
}}

If no facts/entities/relationships found, return empty arrays.
"""
        
        messages = [
            {"role": "system", "content": "You are a knowledge extraction module. Extract facts, entities, and relationships. Return only valid JSON."},
            {"role": "user", "content": prompt}
        ]
        
        try:
            response = await self.llm_client.chat_completion(
                messages,
                temperature=0.1,  # Low temperature for consistency
                max_tokens=500
            )
            
            # Parse response
            return self._parse_extraction(response)
        
        except Exception as e:
            logger.error(f"LLM extraction call failed: {e}")
            return None
    
    def _parse_extraction(self, raw_response: str) -> Dict:
        """Parse and validate LLM extraction response."""
        if not raw_response:
            return None
        
        try:
            # Extract JSON from response (handle markdown code blocks)
            json_match = re.search(r"\{.*\}", raw_response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                
                # Clean up common JSON issues
                json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)  # Remove trailing commas
                
                data = json.loads(json_str)
                
                # Validate structure
                facts = data.get("facts", [])
                if not isinstance(facts, list):
                    facts = []
                
                entities = data.get("entities", [])
                if not isinstance(entities, list):
                    entities = []
                
                relationships = data.get("relationships", [])
                if not isinstance(relationships, list):
                    relationships = []
                
                confidence = data.get("confidence", 0.5)
                if not isinstance(confidence, (int, float)):
                    confidence = 0.5
                confidence = max(0.0, min(1.0, float(confidence)))
                
                # Validate entities
                validated_entities = []
                for ent in entities:
                    if isinstance(ent, dict) and "name" in ent:
                        validated_entities.append({
                            "name": str(ent["name"]).strip(),
                            "type": str(ent.get("type", "concept")).strip()
                        })
                
                # Validate relationships
                validated_relationships = []
                for rel in relationships:
                    if isinstance(rel, dict) and "source" in rel and "target" in rel:
                        validated_relationships.append({
                            "source": str(rel["source"]).strip(),
                            "target": str(rel["target"]).strip(),
                            "type": str(rel.get("type", "related_to")).strip()
                        })
                
                # Filter empty/trivial facts
                validated_facts = [
                    f.strip() for f in facts
                    if isinstance(f, str) and f.strip() and len(f.strip()) > 15
                ]
                
                return {
                    "facts": validated_facts[:5],
                    "entities": validated_entities[:10],
                    "relationships": validated_relationships[:5],
                    "confidence": confidence,
                    "raw": raw_response
                }
        
        except json.JSONDecodeError as e:
            logger.debug(f"Failed to parse extraction JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"Extraction parsing failed: {e}")
            return None
    
    async def consolidate_conversation(
        self,
        conversation: List[Dict]
    ) -> Dict:
        """
        Extract knowledge from a multi-turn conversation.
        
        Args:
            conversation: List of {role, content} dicts
        
        Returns:
            Consolidated knowledge across all turns
        """
        all_facts = []
        all_entities = []
        all_relationships = []
        
        # Extract from each user message
        for msg in conversation:
            if msg.get("role") != "user":
                continue
            
            content = msg.get("content", "")
            if not content:
                continue
            
            extraction = await self.consolidate(content)
            
            all_facts.extend(extraction.get("facts", []))
            all_entities.extend(extraction.get("entities", []))
            all_relationships.extend(extraction.get("relationships", []))
        
        # Deduplicate
        all_facts = list(set(all_facts))
        all_entities = self._deduplicate_entities(all_entities)
        all_relationships = self._deduplicate_relationships(all_relationships)
        
        return {
            "facts": all_facts[:10],
            "entities": all_entities[:15],
            "relationships": all_relationships[:10],
            "consolidation_timestamp": datetime.now().isoformat()
        }
    
    def _deduplicate_entities(self, entities: List[Dict]) -> List[Dict]:
        """Deduplicate entities by name (case-insensitive)."""
        seen = {}
        deduplicated = []
        
        for ent in entities:
            name_lower = ent.get("name", "").lower()
            if name_lower not in seen:
                seen[name_lower] = True
                deduplicated.append(ent)
        
        return deduplicated
    
    def _deduplicate_relationships(self, relationships: List[Dict]) -> List[Dict]:
        """Deduplicate relationships."""
        seen = set()
        deduplicated = []
        
        for rel in relationships:
            key = (
                rel.get("source", "").lower(),
                rel.get("target", "").lower(),
                rel.get("type", "").lower()
            )
            if key not in seen:
                seen.add(key)
                deduplicated.append(rel)
        
        return deduplicated
    
    def get_stats(self) -> Dict:
        """Get consolidation statistics."""
        return {
            "total_extractions": self.extraction_count
        }
