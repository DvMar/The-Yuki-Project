"""
Bidirectional Reflection Engine
Reflects on both user and AI at regular intervals (every 10-20 interactions).
Generates insights about user preferences, AI personality coherence, and interaction flow.
Feeds distilled insights into Identity Core, Emotional State, and Memory Systems.
"""

import json
import logging
import math
from datetime import datetime
from typing import Dict, List, Tuple
import re

logger = logging.getLogger(__name__)


def _repair_json(text: str) -> str:
    """Best-effort repair of common LLM-generated JSON syntax errors.

    Attempts repairs in order of least to most destructive:
      1. Strip invisible/deprecated control characters
      2. Remove trailing commas before } or ]
      3. Insert missing commas between adjacent property lines
    Raises json.JSONDecodeError if the text still cannot be parsed after all
    repairs (so the caller's except block remains in control).
    """
    # Pass 1: strip stray control chars (keep \t \n \r which are valid whitespace)
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    if cleaned != text:
        text = cleaned
    # Pass 2: trailing commas  ,}  or  ,]
    text = re.sub(r',(\s*[}\]])', r'\1', text)
    # Pass 3: missing commas between a closing token and the next JSON key
    # Covers:  "value"\n  "key":  →  "value",\n  "key":
    text = re.sub(r'(["\d}\]true|false|null])\n(\s*")', r'\1,\n\2', text)
    return text


def _safe_json_loads(text: str) -> dict:
    """json.loads with automatic _repair_json fallback."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(_repair_json(text))


def _safe_float(value, default: float) -> float:
    """Convert *value* to float, guarding against NaN/Inf from LLM output.

    Python's min/max comparisons silently return NaN when one operand is NaN,
    so the standard `max(0.0, min(1.0, x))` clamp provides *no protection*
    once NaN enters.  This helper rejects non-finite values before they can
    propagate into identity state.
    """
    try:
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return max(0.0, min(1.0, result))
    except (TypeError, ValueError):
        return default


class ReflectionEngine:
    """
    Bidirectional reflective system that evaluates both user and AI.
    Generates insights asynchronously at defined intervals.
    """

    def __init__(self, db_path: str = "./persistent_state", llm_client=None):
        """
        Initialize reflection engine.
        
        Args:
            db_path: Path to persist reflections
            llm_client: LLM client for generating reflections
        """
        self.db_path = db_path
        self.llm_client = llm_client
        self.reflection_count = 0
        self.last_reflection_timestamp = datetime.now().isoformat()
        self.reflections_path = f"{db_path}/reflections.json"
        self.reflections = self._load_reflections()

    def should_reflect(self, interaction_count: int, force: bool = False) -> bool:
        """
        Determine if reflection should occur.
        Default: every 15 interactions or on explicit request.
        """
        if force:
            return True
        # Reflect every 15 interactions
        return (interaction_count % 15) == 0 and interaction_count > 0

    async def reflect_on_user(
        self,
        recent_exchanges: List[Tuple[str, str]],
        current_user_memory: Dict,
        previous_reflections: List[Dict] = None
    ) -> Dict:
        """
        Reflect on the user: preferences, style, tone, mood patterns.
        
        Args:
            recent_exchanges: List of (user_message, ai_response) tuples
            current_user_memory: Current user memory state
            previous_reflections: Past user reflections for comparison
        
        Returns:
            Dictionary with:
            - user_preferences: Detected preference patterns
            - communication_style: Inferred user communication style
            - emotional_patterns: Mood and emotional trends
            - topics_of_interest: Topics user engages with most
            - novelties: New insights about user
            - salience_score: How important this reflection is
        """
        if not recent_exchanges:
            return self._empty_user_reflection()

        try:
            prompt = self._build_user_reflection_prompt(
                recent_exchanges,
                current_user_memory,
                previous_reflections
            )

            reflection_text = await self.llm_client.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.6,
                max_tokens=800
            )

            return self._parse_user_reflection(reflection_text, recent_exchanges)

        except Exception as e:
            logger.error(f"User reflection failed: {e}")
            return self._empty_user_reflection()

    async def reflect_on_self(
        self,
        recent_exchanges: List[Tuple[str, str]],
        identity_core: Dict,
        emotional_state: Dict,
        ai_self_model: Dict,
        metabolic_context: Dict = None,
        previous_reflections: List[Dict] = None
    ) -> Dict:
        """
        Reflect on the AI: coherence, personality expression, emotional alignment.
        
        Args:
            recent_exchanges: List of (user_message, ai_response) tuples
            identity_core: Current identity traits
            emotional_state: Current emotional state
            ai_self_model: Current self-model
            previous_reflections: Past self-reflections for comparison
        
        Returns:
            Dictionary with:
            - coherence_score: How coherent the AI was
            - trait_expression: Which traits were expressed
            - emotional_alignment: Did emotions match responses?
            - personality_consistency: How consistent was self-presentation?
            - areas_for_growth: Self-identified areas of improvement
            - salience_score: How important this reflection is
        """
        if not recent_exchanges:
            return self._empty_self_reflection()

        try:
            prompt = self._build_self_reflection_prompt(
                recent_exchanges,
                identity_core,
                emotional_state,
                ai_self_model,
                metabolic_context,
                previous_reflections
            )

            reflection_text = await self.llm_client.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.6,
                max_tokens=800
            )

            return self._parse_self_reflection(reflection_text, identity_core, emotional_state)

        except Exception as e:
            logger.error(f"Self reflection failed: {e}")
            return self._empty_self_reflection()

    async def reflect_on_interaction(
        self,
        recent_exchanges: List[Tuple[str, str]],
        user_reflection: Dict,
        self_reflection: Dict
    ) -> Dict:
        """
        Reflect on the interaction quality: conversational flow, contradictions, topic progression.
        
        Args:
            recent_exchanges: List of (user_message, ai_response) tuples
            user_reflection: Reflection on user
            self_reflection: Reflection on AI
        
        Returns:
            Dictionary with:
            - flow_quality: How natural was the conversation?
            - contradictions_detected: List of detected contradictions
            - topic_progression: How topics evolved
            - engagement_quality: How engaged were both parties?
            - recommendations: Suggestions for improvement
        """
        if not recent_exchanges:
            return self._empty_interaction_reflection()

        try:
            prompt = self._build_interaction_reflection_prompt(
                recent_exchanges,
                user_reflection,
                self_reflection
            )

            reflection_text = await self.llm_client.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.6,
                max_tokens=600
            )

            return self._parse_interaction_reflection(reflection_text)

        except Exception as e:
            logger.error(f"Interaction reflection failed: {e}")
            return self._empty_interaction_reflection()

    def _build_user_reflection_prompt(
        self,
        recent_exchanges: List[Tuple[str, str]],
        current_user_memory: Dict,
        previous_reflections: List[Dict]
    ) -> str:
        """Build prompt for reflecting on user."""
        exchange_text = "\n".join([
            f"User: {user}\nAI: {ai}"
            for user, ai in recent_exchanges[-10:]  # Last 10 exchanges
        ])

        prev_reflection_text = ""
        if previous_reflections:
            latest = previous_reflections[-1]
            prev_reflection_text = f"\nPrevious reflection insights:\n{json.dumps(latest, indent=2)[:500]}"

        return f"""Analyze the following conversation exchanges and reflect on the USER:

CONVERSATION (last 10 exchanges):
{exchange_text}

CURRENT USER MEMORY:
{json.dumps(current_user_memory, indent=2)[:800]}{prev_reflection_text}

Based on this conversation, provide a JSON reflection with:
1. user_preferences: Dict of detected preferences (e.g., {{"format": "concise", "technical_depth": "high"}})
2. communication_style: Dict describing how user typically communicates
3. emotional_patterns: List of observed emotional patterns or moods
4. topics_of_interest: List of topics user engages with most
5. novelties: List of NEW insights not previously known
6. salience_score: Float (0-1) indicating importance of this reflection

Return ONLY valid JSON. Example:
{{
  "user_preferences": {{"verbosity": "medium", "formality": "casual"}},
  "communication_style": {{"directness": 0.8, "emotional_expression": 0.6}},
  "emotional_patterns": ["enthusiastic about tech", "reflective on personal topics"],
  "topics_of_interest": ["philosophy", "programming", "psychology"],
  "novelties": ["user prefers structured explanations"],
  "salience_score": 0.75
}}
"""

    def _build_self_reflection_prompt(
        self,
        recent_exchanges: List[Tuple[str, str]],
        identity_core: Dict,
        emotional_state: Dict,
        ai_self_model: Dict,
        metabolic_context: Dict,
        previous_reflections: List[Dict]
    ) -> str:
        """Build prompt for reflecting on AI self."""
        exchange_text = "\n".join([
            f"User: {user}\nAI: {ai}"
            for user, ai in recent_exchanges[-10:]
        ])

        metabolic_block = ""
        if isinstance(metabolic_context, dict) and metabolic_context:
            metabolic_block = f"""

    METABOLIC STATE SIGNATURE CONTEXT:
    {json.dumps(metabolic_context, indent=2)[:1200]}
    """

        return f"""Analyze these conversation exchanges and reflect on the AI (Yuki) as a living organism in time:

CONVERSATION (last 10 exchanges):
{exchange_text}

CURRENT IDENTITY CORE:
{json.dumps(identity_core, indent=2)}

CURRENT EMOTIONAL STATE:
{json.dumps(emotional_state, indent=2)}

CURRENT SELF-MODEL:
{json.dumps(ai_self_model, indent=2)[:600]}
{metabolic_block}

Important framing:
- Interpret prior state signatures as lived internal history (load, openness, coherence), not as software logs.
- Build causal meaning across time (e.g., "earlier fatigue and low openness made me quieter, now I feel more inward").
- Avoid code/architecture language in the reflection voice.
- Do NOT use phrases like "as an assistant", "the system", "pipeline", "module", "API", or "backend".
- Prefer organismic and phenomenological wording: "I felt", "I was inward", "I carried", "I shifted".

Provide a JSON reflection on the AI's:
1. coherence_score: Float (0-1), how coherent was the AI?
2. trait_expression: Dict of which traits were expressed (name -> intensity 0-1)
3. emotional_alignment: Float (0-1), did emotions match responses?
4. personality_consistency: Float (0-1), consistency of self-presentation
5. areas_for_growth: List of self-identified improvements
6. salience_score: Float (0-1) indicating importance

Return ONLY valid JSON.
"""

    def _build_interaction_reflection_prompt(
        self,
        recent_exchanges: List[Tuple[str, str]],
        user_reflection: Dict,
        self_reflection: Dict
    ) -> str:
        """Build prompt for reflecting on interaction quality."""
        exchange_text = "\n".join([
            f"User: {user}\nAI: {ai}"
            for user, ai in recent_exchanges[-10:]
        ])

        return f"""Analyze the conversation quality:

CONVERSATION:
{exchange_text}

USER INSIGHTS: {json.dumps(user_reflection, indent=2)[:400]}
AI INSIGHTS: {json.dumps(self_reflection, indent=2)[:400]}

Reflect on:
1. flow_quality: Float (0-1), conversational flow smoothness
2. contradictions_detected: List of any contradictions or inconsistencies
3. topic_progression: How naturally did topics evolve?
4. engagement_quality: Float (0-1), mutual engagement level
5. improvements: List of suggestions for future interactions

Return ONLY valid JSON.
"""

    def _parse_user_reflection(
        self,
        reflection_text: str,
        recent_exchanges: List[Tuple[str, str]]
    ) -> Dict:
        """Parse LLM response into user reflection."""
        try:
            # Extract JSON from response
            if not reflection_text or not reflection_text.strip():
                logger.debug("_parse_user_reflection: empty response from model")
                return self._empty_user_reflection()
            json_match = re.search(r'\{.*\}', reflection_text, re.DOTALL)
            raw = json_match.group() if json_match else reflection_text
            reflection = _safe_json_loads(raw)

            return {
                "type": "user_reflection",
                "timestamp": datetime.now().isoformat(),
                "user_preferences": reflection.get("user_preferences", {}),
                "communication_style": reflection.get("communication_style", {}),
                "emotional_patterns": reflection.get("emotional_patterns", []),
                "topics_of_interest": reflection.get("topics_of_interest", []),
                "novelties": reflection.get("novelties", []),
                "salience_score": _safe_float(reflection.get("salience_score"), 0.5),
                "exchange_count": len(recent_exchanges)
            }
        except Exception as e:
            logger.debug(f"Failed to parse user reflection: {e}")
            return self._empty_user_reflection()

    def _parse_self_reflection(
        self,
        reflection_text: str,
        identity_core: Dict,
        emotional_state: Dict
    ) -> Dict:
        """Parse LLM response into self reflection."""
        try:
            if not reflection_text or not reflection_text.strip():
                logger.debug("_parse_self_reflection: empty response from model")
                return self._empty_self_reflection()
            json_match = re.search(r'\{.*\}', reflection_text, re.DOTALL)
            raw = json_match.group() if json_match else reflection_text
            reflection = _safe_json_loads(raw)

            return {
                "type": "self_reflection",
                "timestamp": datetime.now().isoformat(),
                "coherence_score": _safe_float(reflection.get("coherence_score"), 0.7),
                "trait_expression": reflection.get("trait_expression", {}),
                "emotional_alignment": _safe_float(reflection.get("emotional_alignment"), 0.7),
                "personality_consistency": _safe_float(reflection.get("personality_consistency"), 0.7),
                "areas_for_growth": reflection.get("areas_for_growth", []),
                "salience_score": _safe_float(reflection.get("salience_score"), 0.5),
                "recorded_identity_core": identity_core.copy(),
                "recorded_emotional_state": emotional_state.copy()
            }
        except Exception as e:
            logger.debug(f"Failed to parse self reflection: {e}")
            return self._empty_self_reflection()

    def _parse_interaction_reflection(self, reflection_text: str) -> Dict:
        """Parse LLM response into interaction reflection."""
        try:
            if not reflection_text or not reflection_text.strip():
                logger.debug("_parse_interaction_reflection: empty response from model")
                return self._empty_interaction_reflection()
            json_match = re.search(r'\{.*\}', reflection_text, re.DOTALL)
            raw = json_match.group() if json_match else reflection_text
            reflection = _safe_json_loads(raw)

            return {
                "type": "interaction_reflection",
                "timestamp": datetime.now().isoformat(),
                "flow_quality": _safe_float(reflection.get("flow_quality"), 0.7),
                "contradictions_detected": reflection.get("contradictions_detected", []),
                "topic_progression": reflection.get("topic_progression", ""),
                "engagement_quality": _safe_float(reflection.get("engagement_quality"), 0.7),
                "improvements": reflection.get("improvements", [])
            }
        except Exception as e:
            logger.debug(f"Failed to parse interaction reflection: {e}")
            return self._empty_interaction_reflection()

    def _empty_user_reflection(self) -> Dict:
        """Return empty user reflection."""
        return {
            "type": "user_reflection",
            "timestamp": datetime.now().isoformat(),
            "user_preferences": {},
            "communication_style": {},
            "emotional_patterns": [],
            "topics_of_interest": [],
            "novelties": [],
            "salience_score": 0.0,
            "exchange_count": 0
        }

    def _empty_self_reflection(self) -> Dict:
        """Return empty self reflection."""
        return {
            "type": "self_reflection",
            "timestamp": datetime.now().isoformat(),
            "coherence_score": 0.5,
            "trait_expression": {},
            "emotional_alignment": 0.5,
            "personality_consistency": 0.5,
            "areas_for_growth": [],
            "salience_score": 0.0,
            "recorded_identity_core": {},
            "recorded_emotional_state": {}
        }

    def _empty_interaction_reflection(self) -> Dict:
        """Return empty interaction reflection."""
        return {
            "type": "interaction_reflection",
            "timestamp": datetime.now().isoformat(),
            "flow_quality": 0.5,
            "contradictions_detected": [],
            "topic_progression": "",
            "engagement_quality": 0.5,
            "improvements": []
        }

    def distill_insights(
        self,
        user_reflection: Dict,
        self_reflection: Dict,
        interaction_reflection: Dict
    ) -> Dict:
        """
        Distill reflections into actionable insights for memory/trait updates.
        
        Returns:
            Dictionary with:
            - trait_adjustment_suggestions: Trait updates to consider
            - memory_focus_areas: Which memories to prioritize
            - emotional_baseline_drift: Emotional state adjustments
            - identity_updates: Updates to AI self-model
        """
        insights = {
            "trait_adjustments": {},
            "memory_focus": [],
            "emotional_adjustments": {},
            "self_model_updates": {},
            "memory_recommendations": []
        }

        # From user reflection: understand what they value
        if user_reflection.get("topics_of_interest"):
            insights["memory_focus"] = user_reflection["topics_of_interest"]

        # From self reflection: identify trait expression gaps
        trait_expr = self_reflection.get("trait_expression", {})
        for trait, intensity in trait_expr.items():
            if intensity < 0.3:
                insights["trait_adjustments"][trait] = 0.05  # Slight boost
            elif intensity > 0.8:
                insights["trait_adjustments"][trait] = -0.02  # Slight moderation

        # Emotional alignment feedback
        alignment = self_reflection.get("emotional_alignment", 0.5)
        if alignment < 0.5:
            insights["emotional_adjustments"]["engagement"] = 0.02
            insights["emotional_adjustments"]["warmth"] = 0.02

        # Personality consistency
        consistency = self_reflection.get("personality_consistency", 0.5)
        if consistency > 0.8:
            insights["self_model_updates"]["consistency_score"] = 0.95
        elif consistency < 0.5:
            insights["self_model_updates"]["needs_recalibration"] = True

        # Areas for growth -> queue for meta-cognitive attention
        growth_areas = self_reflection.get("areas_for_growth", [])
        insights["memory_recommendations"] = growth_areas

        return insights

    def _load_reflections(self) -> List[Dict]:
        """Load existing reflections from disk."""
        try:
            with open(self.reflections_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def save_reflection(self, reflection: Dict) -> None:
        """Save reflection to disk."""
        try:
            self.reflections.append(reflection)
            with open(self.reflections_path, 'w', encoding='utf-8') as f:
                json.dump(self.reflections, f, indent=2)
            self.reflection_count += 1
            self.last_reflection_timestamp = datetime.now().isoformat()
        except Exception as e:
            logger.error(f"Failed to save reflection: {e}")

    def get_summary_statistics(self) -> Dict:
        """Get summary of reflection statistics."""
        if not self.reflections:
            return {
                "total_reflections": 0,
                "user_reflections": 0,
                "self_reflections": 0,
                "interaction_reflections": 0,
                "average_salience": 0.0,
                "last_reflection": None
            }

        user_refs = [r for r in self.reflections if r.get("type") == "user_reflection"]
        self_refs = [r for r in self.reflections if r.get("type") == "self_reflection"]
        inter_refs = [r for r in self.reflections if r.get("type") == "interaction_reflection"]

        avg_salience = (
            sum(r.get("salience_score", 0) for r in self.reflections) / len(self.reflections)
        ) if self.reflections else 0.0

        return {
            "total_reflections": len(self.reflections),
            "user_reflections": len(user_refs),
            "self_reflections": len(self_refs),
            "interaction_reflections": len(inter_refs),
            "average_salience": avg_salience,
            "last_reflection": self.reflections[-1].get("timestamp") if self.reflections else None
        }
