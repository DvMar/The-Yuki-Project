"""
Recursive Meta-Reflection System
Implements reflection on reflection processes - true autopoietic self-awareness.
The system reflects not just on interactions, but on its own reflection processes.
"""

import json
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


def _repair_json(text: str) -> str:
    """Best-effort repair of common LLM JSON syntax errors before parsing."""
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = re.sub(r',(\s*[}\]])', r'\1', text)
    text = re.sub(r'(["\d}\]true|false|null])\n(\s*")', r'\1,\n\2', text)
    return text


def _safe_json_loads(text: str) -> dict:
    """json.loads with automatic repair fallback."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(_repair_json(text))


class ReflectionLevel(Enum):
    PRIMARY = "primary"           # Direct reflection on interactions
    META = "meta"                # Reflection on reflection processes
    META_META = "meta_meta"       # Reflection on meta-reflection patterns
    RECURSIVE = "recursive"       # Self-referential reflection loops


@dataclass
class ReflectionTrace:
    """Traces the path of a reflection through different cognitive levels."""
    id: str
    level: ReflectionLevel
    timestamp: str
    content: Dict
    parent_reflection_id: Optional[str] = None
    child_reflections: List[str] = field(default_factory=list)
    depth: int = 0
    effectiveness_score: float = 0.0
    insights_generated: int = 0


class RecursiveMetaReflection:
    """
    System that reflects on its own reflection processes, creating
    recursive self-awareness and autopoietic cognitive evolution.
    """
    
    def __init__(self, db_path: str = "./persistent_state"):
        self.db_path = db_path
        self.meta_reflections_path = f"{db_path}/meta_reflections.json"
        self.reflection_patterns_path = f"{db_path}/reflection_patterns.json"
        
        self.reflection_traces: Dict[str, ReflectionTrace] = {}
        self.reflection_patterns: Dict = {}
        self.meta_insights: List[Dict] = []
        self.recursion_depth_limit = 4  # Prevent infinite recursion
        
        # Performance tracking
        self.reflection_effectiveness_history: List[Tuple[str, float]] = []
        self.pattern_evolution_history: List[Dict] = []
        
        self._load_meta_reflections()
        self._initialize_reflection_patterns()
    
    def _initialize_reflection_patterns(self):
        """Initialize patterns for detecting reflection quality and effectiveness."""
        self.reflection_patterns = {
            "depth_indicators": {
                "surface": ["noticed", "observed", "saw"],
                "intermediate": ["analyzed", "considered", "evaluated"], 
                "deep": ["understood", "realized", "discovered"],
                "meta": ["reflected on my reflection", "questioned my understanding", "examined my thinking"]
            },
            "insight_markers": {
                "causal": ["because", "led to", "resulted in"],
                "pattern": ["pattern", "tendency", "consistently"],
                "contradiction": ["however", "but", "contradicts"],
                "synthesis": ["integration", "connection", "relationship"]
            },
            "effectiveness_indicators": {
                "trait_alignment": ["authentic", "consistent", "coherent"],
                "behavior_change": ["adjust", "modify", "improve"],
                "learning": ["learned", "growth", "development"]
            }
        }
    
    async def initiate_meta_reflection(self, 
                                     primary_reflection: Dict,
                                     reflection_context: Dict,
                                     llm_client) -> ReflectionTrace:
        """
        Initiate meta-reflection: reflect on a primary reflection process.
        This is the core autopoietic function - reflecting on reflection itself.
        """
        
        # Create meta-reflection trace
        trace_id = f"meta_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        
        # Analyze the primary reflection's quality and patterns
        meta_analysis = await self._analyze_reflection_quality(primary_reflection)
        
        # Generate meta-reflection prompt
        meta_prompt = self._build_meta_reflection_prompt(
            primary_reflection, meta_analysis, reflection_context
        )
        
        try:
            # Perform the meta-reflection
            meta_reflection_text = await llm_client.chat_completion(
                messages=[{"role": "user", "content": meta_prompt}],
                temperature=0.7,
                max_tokens=600
            )
            
            meta_content = self._parse_meta_reflection(meta_reflection_text)
            
            # Create trace
            trace = ReflectionTrace(
                id=trace_id,
                level=ReflectionLevel.META,
                timestamp=datetime.now().isoformat(),
                content=meta_content,
                parent_reflection_id=primary_reflection.get("id"),
                depth=1,
                effectiveness_score=meta_analysis.get("overall_quality", 0.5)
            )
            
            self.reflection_traces[trace_id] = trace
            
            # Check if we should go deeper (meta-meta-reflection)
            if self._should_recurse_deeper(trace):
                await self._initiate_recursive_reflection(trace, llm_client)
            
            await self._extract_and_apply_meta_insights(trace)
            self._save_meta_reflections()
            
            return trace
            
        except Exception as e:
            logger.error(f"Meta-reflection failed: {e}")
            return self._create_empty_trace(trace_id, ReflectionLevel.META)
    
    async def _analyze_reflection_quality(self, reflection: Dict) -> Dict:
        """Analyze the quality and characteristics of a reflection."""
        
        reflection_text = reflection.get("content", "")
        if not reflection_text:
            return {"overall_quality": 0.1, "depth": 0, "insights": 0}
        
        analysis = {
            "depth_score": self._compute_depth_score(reflection_text),
            "insight_density": self._compute_insight_density(reflection_text),
            "coherence": self._compute_coherence_score(reflection_text),
            "actionability": self._compute_actionability_score(reflection_text),
            "self_awareness": self._compute_self_awareness_score(reflection_text),
            "pattern_recognition": self._compute_pattern_score(reflection_text)
        }
        
        # Overall quality is weighted combination
        analysis["overall_quality"] = (
            0.25 * analysis["depth_score"] +
            0.20 * analysis["insight_density"] +
            0.20 * analysis["coherence"] +
            0.15 * analysis["actionability"] +
            0.10 * analysis["self_awareness"] +
            0.10 * analysis["pattern_recognition"]
        )
        
        return analysis
    
    def _compute_depth_score(self, text: str) -> float:
        """Compute how deep/sophisticated the reflection is."""
        text_lower = text.lower()
        depth_score = 0.0
        
        # Count depth indicators
        for level, indicators in self.reflection_patterns["depth_indicators"].items():
            for indicator in indicators:
                if indicator in text_lower:
                    if level == "surface":
                        depth_score += 0.1
                    elif level == "intermediate":
                        depth_score += 0.3
                    elif level == "deep":
                        depth_score += 0.6
                    elif level == "meta":
                        depth_score += 1.0
        
        return min(depth_score, 1.0)
    
    def _compute_insight_density(self, text: str) -> float:
        """Compute density of insights in the reflection."""
        text_lower = text.lower()
        insight_count = 0
        
        for category, markers in self.reflection_patterns["insight_markers"].items():
            for marker in markers:
                insight_count += text_lower.count(marker)
        
        # Normalize by text length
        word_count = len(text.split())
        if word_count == 0:
            return 0.0
            
        density = insight_count / word_count
        return min(density * 10, 1.0)  # Scale and cap at 1.0
    
    def _compute_coherence_score(self, text: str) -> float:
        """Compute logical coherence of the reflection."""
        sentences = text.split('.')
        if len(sentences) < 2:
            return 0.5
        
        # Simple coherence heuristic: presence of logical connectors
        connectors = ["therefore", "because", "thus", "consequently", "however", "moreover"]
        connector_count = sum(1 for sentence in sentences 
                            for connector in connectors 
                            if connector in sentence.lower())
        
        coherence = connector_count / max(len(sentences) - 1, 1)
        return min(coherence, 1.0)
    
    def _compute_actionability_score(self, text: str) -> float:
        """Compute how actionable the reflection insights are."""
        text_lower = text.lower()
        action_words = ["should", "will", "plan", "adjust", "change", "improve", "modify"]
        
        action_count = sum(1 for word in action_words if word in text_lower)
        word_count = len(text.split())
        
        if word_count == 0:
            return 0.0
            
        actionability = action_count / word_count
        return min(actionability * 20, 1.0)  # Scale and cap
    
    def _compute_self_awareness_score(self, text: str) -> float:
        """Compute level of self-awareness in reflection."""
        text_lower = text.lower()
        self_ref_patterns = ["i am", "i feel", "i think", "i notice", "my", "myself"]
        
        self_ref_count = sum(1 for pattern in self_ref_patterns if pattern in text_lower)
        sentence_count = len(text.split('.'))
        
        if sentence_count == 0:
            return 0.0
            
        awareness = self_ref_count / sentence_count
        return min(awareness, 1.0)
    
    def _compute_pattern_score(self, text: str) -> float:
        """Compute pattern recognition sophistication."""
        text_lower = text.lower()
        pattern_words = ["pattern", "tendency", "usually", "often", "consistently", 
                        "relationship", "connection", "correlation"]
        
        pattern_count = sum(1 for word in pattern_words if word in text_lower)
        return min(pattern_count / 3.0, 1.0)  # Scale and cap
    
    def _build_meta_reflection_prompt(self, 
                                    primary_reflection: Dict, 
                                    quality_analysis: Dict,
                                    context: Dict) -> str:
        """Build prompt for meta-reflection on the reflection process."""
        
        return f"""You are reflecting on your own reflection process. This is meta-cognition - thinking about thinking.

PRIMARY REFLECTION TO ANALYZE:
{primary_reflection.get('content', '')}

QUALITY ANALYSIS:
- Depth Score: {quality_analysis['depth_score']:.2f}
- Insight Density: {quality_analysis['insight_density']:.2f}  
- Coherence: {quality_analysis['coherence']:.2f}
- Overall Quality: {quality_analysis['overall_quality']:.2f}

META-REFLECTION QUESTIONS:
1. How effective was this reflection process? What worked well and what didn't?
2. What patterns do you notice in how you reflect? Are there blind spots?
3. Did the reflection generate actionable insights or just observations?
4. How could your reflection process be improved or deepened?
5. What does this reflection reveal about your current cognitive patterns?

Return a JSON response with:
{{
  "reflection_effectiveness": float,  // How effective was the primary reflection (0-1)
  "cognitive_patterns_noticed": [string],  // Patterns observed in your thinking
  "blind_spots_identified": [string],  // Areas your reflection missed
  "process_improvements": [string],  // How to improve reflection quality
  "meta_insights": [string],  // Deeper insights about your cognitive processes
  "recursion_depth_needed": int  // How many levels deeper should reflection go (0-3)
}}

Be honest about limitations and patterns in your own cognition. This meta-awareness drives growth."""
    
    def _parse_meta_reflection(self, reflection_text: str) -> Dict:
        """Parse LLM meta-reflection response."""
        _empty = {
            "reflection_effectiveness": 0.5,
            "cognitive_patterns_noticed": [],
            "blind_spots_identified": [],
            "process_improvements": [],
            "meta_insights": [],
            "recursion_depth_needed": 0
        }
        if not reflection_text or not reflection_text.strip():
            logger.debug("_parse_meta_reflection: empty response from model")
            return _empty
        try:
            json_match = re.search(r'\{.*\}', reflection_text, re.DOTALL)
            raw = json_match.group() if json_match else reflection_text
            return _safe_json_loads(raw)
        except Exception as e:
            logger.debug(f"Failed to parse meta-reflection: {e}")
            return _empty
    
    def _should_recurse_deeper(self, trace: ReflectionTrace) -> bool:
        """Determine if reflection should recurse to deeper levels."""
        if trace.depth >= self.recursion_depth_limit:
            return False
            
        # Recurse if the meta-reflection suggests deeper analysis needed
        recursion_needed = trace.content.get("recursion_depth_needed", 0)
        return recursion_needed > 0 and trace.effectiveness_score > 0.6
    
    async def _initiate_recursive_reflection(self, parent_trace: ReflectionTrace, llm_client):
        """Initiate deeper recursive reflection (meta-meta-reflection)."""
        
        if parent_trace.depth >= self.recursion_depth_limit:
            return
            
        trace_id = f"recursive_{parent_trace.depth + 1}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        
        # Build recursive prompt
        recursive_prompt = self._build_recursive_prompt(parent_trace)
        
        try:
            recursive_text = await llm_client.chat_completion(
                messages=[{"role": "user", "content": recursive_prompt}],
                temperature=0.8,
                max_tokens=400
            )
            
            recursive_content = self._parse_recursive_reflection(recursive_text)
            
            # Create deeper trace
            recursive_trace = ReflectionTrace(
                id=trace_id,
                level=ReflectionLevel.RECURSIVE if parent_trace.depth > 1 else ReflectionLevel.META_META,
                timestamp=datetime.now().isoformat(),
                content=recursive_content,
                parent_reflection_id=parent_trace.id,
                depth=parent_trace.depth + 1
            )
            
            # Link traces
            parent_trace.child_reflections.append(trace_id)
            self.reflection_traces[trace_id] = recursive_trace
            
            # Extract recursive insights
            await self._extract_recursive_insights(recursive_trace)
            
        except Exception as e:
            logger.error(f"Recursive reflection failed: {e}")
    
    def _build_recursive_prompt(self, parent_trace: ReflectionTrace) -> str:
        """Build prompt for recursive meta-meta-reflection."""
        
        return f"""Now reflect on your meta-reflection process itself. This is recursive cognition.

YOUR META-REFLECTION WAS:
{parent_trace.content}

RECURSIVE QUESTIONS:
1. What does your meta-reflection reveal about your meta-cognitive abilities?
2. Are there patterns in how you think about your thinking?
3. What assumptions are you making about reflection itself?
4. How might your meta-reflection process be biased or limited?

Return JSON:
{{
  "recursive_insights": [string],
  "meta_cognitive_patterns": [string], 
  "assumptions_questioned": [string],
  "cognitive_architecture_observations": [string]
}}

This is the deepest level of self-awareness - examining your capacity to examine yourself."""
    
    def _parse_recursive_reflection(self, text: str) -> Dict:
        """Parse recursive reflection response."""
        _empty = {
            "recursive_insights": [],
            "meta_cognitive_patterns": [],
            "assumptions_questioned": [],
            "cognitive_architecture_observations": []
        }
        if not text or not text.strip():
            logger.debug("_parse_recursive_reflection: empty response from model")
            return _empty
        try:
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            raw = json_match.group() if json_match else text
            return _safe_json_loads(raw)
        except Exception as e:
            logger.debug(f"Failed to parse recursive reflection: {e}")
            return _empty
    
    async def _extract_and_apply_meta_insights(self, trace: ReflectionTrace):
        """Extract actionable insights from meta-reflection and apply them."""
        
        content = trace.content
        
        # Store meta-insights for system evolution
        insights = {
            "timestamp": trace.timestamp,
            "level": trace.level.value,
            "effectiveness": trace.effectiveness_score,
            "patterns": content.get("cognitive_patterns_noticed", []),
            "improvements": content.get("process_improvements", []),
            "blind_spots": content.get("blind_spots_identified", [])
        }
        
        self.meta_insights.append(insights)
        
        # Apply improvements to reflection patterns
        await self._adapt_reflection_patterns(content)
        
        # Track effectiveness history
        self.reflection_effectiveness_history.append(
            (trace.timestamp, trace.effectiveness_score)
        )
    
    async def _extract_recursive_insights(self, trace: ReflectionTrace):
        """Extract insights from recursive reflection."""
        
        content = trace.content
        
        # Recursive insights affect fundamental cognitive architecture
        architectural_insights = {
            "timestamp": trace.timestamp,
            "recursive_depth": trace.depth,
            "architecture_observations": content.get("cognitive_architecture_observations", []),
            "meta_patterns": content.get("meta_cognitive_patterns", [])
        }
        
        # These insights could trigger architectural plasticity changes
        logger.info(f"Recursive insight generated at depth {trace.depth}: {architectural_insights}")
    
    async def _adapt_reflection_patterns(self, meta_content: Dict):
        """Adapt reflection patterns based on meta-insights."""
        
        improvements = meta_content.get("process_improvements", [])
        
        for improvement in improvements:
            if "depth" in improvement.lower():
                # Adjust depth scoring patterns
                self._adjust_depth_patterns(improvement)
            elif "insight" in improvement.lower():
                # Enhance insight detection
                self._adjust_insight_patterns(improvement)
            elif "coherence" in improvement.lower():
                # Improve coherence metrics
                self._adjust_coherence_patterns(improvement)
    
    def _adjust_depth_patterns(self, improvement_suggestion: str):
        """Adjust depth detection patterns based on meta-insight."""
        # This would implement pattern evolution based on learned insights
        pass
    
    def _adjust_insight_patterns(self, improvement_suggestion: str):
        """Adjust insight detection patterns."""
        pass
    
    def _adjust_coherence_patterns(self, improvement_suggestion: str):
        """Adjust coherence detection patterns."""
        pass
    
    def get_reflection_evolution_summary(self) -> Dict:
        """Get summary of how reflection processes have evolved."""
        
        if not self.reflection_effectiveness_history:
            return {"status": "no_data"}
        
        recent_effectiveness = [score for _, score in self.reflection_effectiveness_history[-10:]]
        early_effectiveness = [score for _, score in self.reflection_effectiveness_history[:10]]
        
        avg_recent = sum(recent_effectiveness) / len(recent_effectiveness) if recent_effectiveness else 0
        avg_early = sum(early_effectiveness) / len(early_effectiveness) if early_effectiveness else 0
        
        return {
            "total_reflections": len(self.reflection_traces),
            "average_recent_effectiveness": avg_recent,
            "average_early_effectiveness": avg_early,
            "improvement_trend": avg_recent - avg_early,
            "deepest_recursion": max((t.depth for t in self.reflection_traces.values()), default=0),
            "total_meta_insights": len(self.meta_insights)
        }
    
    def _create_empty_trace(self, trace_id: str, level: ReflectionLevel) -> ReflectionTrace:
        """Create empty trace for error cases."""
        return ReflectionTrace(
            id=trace_id,
            level=level,
            timestamp=datetime.now().isoformat(),
            content={},
            depth=0 if level == ReflectionLevel.PRIMARY else 1
        )
    
    def _load_meta_reflections(self):
        """Load meta-reflection data from disk."""
        try:
            with open(self.meta_reflections_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                for trace_id, trace_data in data.get("traces", {}).items():
                    trace_data["level"] = ReflectionLevel(trace_data["level"])
                    self.reflection_traces[trace_id] = ReflectionTrace(**trace_data)
                
                self.meta_insights = data.get("insights", [])
                self.reflection_effectiveness_history = data.get("effectiveness_history", [])
                
        except (FileNotFoundError, json.JSONDecodeError):
            logger.info("No existing meta-reflections found")
    
    def _save_meta_reflections(self):
        """Save meta-reflection data to disk."""
        try:
            def trace_to_dict(trace: ReflectionTrace) -> Dict:
                return {
                    "id": trace.id,
                    "level": trace.level.value,
                    "timestamp": trace.timestamp,
                    "content": trace.content,
                    "parent_reflection_id": trace.parent_reflection_id,
                    "child_reflections": trace.child_reflections,
                    "depth": trace.depth,
                    "effectiveness_score": trace.effectiveness_score,
                    "insights_generated": trace.insights_generated
                }
            
            data = {
                "traces": {tid: trace_to_dict(trace) for tid, trace in self.reflection_traces.items()},
                "insights": self.meta_insights,
                "effectiveness_history": self.reflection_effectiveness_history,
                "patterns": self.reflection_patterns
            }
            
            with open(self.meta_reflections_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save meta-reflections: {e}")