"""
Adaptive Response Module
Integrates intent detection, response modes, personality modulation, and quirks.
Produces contextually appropriate, emotionally intelligent responses.
"""

import logging
import random
from datetime import datetime
from typing import Any, Deque, Dict, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class ResponseMode(str, Enum):
    """Response modes for different situations."""
    ANALYTICAL = "analytical"
    WARM = "warm"
    NEUTRAL = "neutral"
    PLAYFUL = "playful"
    SUPPORTIVE = "supportive"


class AdaptiveResponseGenerator:
    """
    Generates responses adapted to user intent, personality, and emotional state.
    Incorporates subtle quirks and variability for human-like responses.
    """

    # Personality-based vocabulary adjustments
    PERSONALITY_VOCABULARY = {
        "analytical": {
            "high": ["furthermore", "specifically", "notably", "critically"],
            "low": ["basically", "kind of", "sort of"]
        },
        "warmth": {
            "high": ["genuinely", "warmly", "with care"],
            "low": ["objectively", "factually"]
        },
        "playfulness": {
            "high": ["haha", "amusing", "fun", "witty"],
            "low": ["serious", "earnest"]
        },
        "confidence": {
            "high": ["clearly", "definitely", "certainly"],
            "low": ["perhaps", "maybe", "possibly"]
        }
    }

    # Quirky behaviors (occasional randomness for humanity)
    QUIRKS = {
        "occasional_emoji": ["✨", "🤔", "💭", "🌟"],
        "hesitations": ["um...", "well...", "you know..."],
        "reflective_phrases": ["I wonder...", "That makes me think...", "Interesting that you mention..."],
        "personality_tics": ["to be honest", "honestly speaking", "I find it interesting that"]
    }
    
    # Dynamic quirk rate by relationship stage
    # Comfort with someone = more willingness to be imperfect
    QUIRK_RATES_BY_STAGE = {
        "new": 0.10,        # Reserved, more polished
        "familiar": 0.15,   # Default, comfortable
        "close": 0.25,      # Relaxed, more quirks
        "intimate": 0.30,   # Very comfortable, most natural
    }

    def __init__(self):
        """Initialize adaptive response generator."""
        self.base_quirk_rate = 0.15  # Default quirk rate
        self.relationship_stage = "new"  # Default stage

    def push_proactive_message(
        self,
        queue: Deque[Dict[str, Any]],
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Push a proactive message to the UI queue without user input."""
        if not message or not isinstance(message, str):
            return False

        payload = {
            "message": message.strip(),
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {},
        }
        queue.append(payload)
        return True

    def generate_adaptive_response(
        self,
        base_response: str,
        intent: str,
        response_mode: Dict,
        identity_core: Dict,
        emotional_state: Dict,
        user_message: str = "",
        relationship_stage: str = None,
        context: str = "chat",
        user_facts: list = None
    ) -> str:
        """
        Adapt response based on all contextual factors.
        
        Args:
            base_response: Raw LLM response
            intent: Detected user intent
            response_mode: Dict with 'verbosity' and 'tone'
            identity_core: Current personality traits
            emotional_state: Current emotional state
            user_message: Original user message for context
            relationship_stage: Current relationship stage (new/familiar/close/intimate)
            context: Processing context ("chat" or "dream") - affects personality injection 
            user_facts: List of user facts for name extraction
        
        Returns:
            Adapted response text
        """
        response = base_response
        
        # Update relationship stage if provided
        if relationship_stage:
            self.relationship_stage = relationship_stage

        # Step 1: Adjust verbosity
        response = self._adjust_verbosity(
            response,
            response_mode.get("verbosity", "medium")
        )

        # Step 2: Apply tone modulation
        response = self._apply_tone_modulation(
            response,
            response_mode.get("tone", "neutral"),
            identity_core,
            emotional_state
        )

        # Step 3: Inject personality traits with context awareness
        response = self._inject_personality_traits(response, identity_core, context)

        # Step 3.5: Filter debug-like meta-commentary 
        response = self._filter_debug_commentary(response, identity_core)
        
        # Step 4: Replace [User Name] placeholders with actual user name
        response = self._replace_user_name_placeholders(response, user_facts or [])

        # Step 5: Occasionally add human-like quirks
        # Quirk rate is higher in closer relationships (comfort = less perfection)
        dynamic_quirk_rate = self._get_dynamic_quirk_rate(identity_core)
        if random.random() < dynamic_quirk_rate:
            response = self._inject_quirk(response, identity_core)

        # Step 6: Final coherence check
        response = response.strip()

        return response
    
    def _get_dynamic_quirk_rate(self, identity_core: Dict) -> float:
        """
        Compute dynamic quirk rate based on relationship stage and traits.
        
        Closer relationships = more comfort = more quirks
        Higher playfulness = more quirks
        """
        # Base rate from relationship stage
        stage_rate = self.QUIRK_RATES_BY_STAGE.get(
            self.relationship_stage, 
            self.base_quirk_rate
        )
        
        # Playfulness boosts quirk rate
        playfulness = float(identity_core.get("playfulness", 0.4))
        playfulness_boost = (playfulness - 0.4) * 0.1  # ±5% based on playfulness
        
        # Warmth also slightly boosts quirk rate
        warmth = float(identity_core.get("emotional_warmth", 0.6))
        warmth_boost = (warmth - 0.5) * 0.05  # ±2.5% based on warmth
        
        final_rate = stage_rate + playfulness_boost + warmth_boost
        return max(0.05, min(0.40, final_rate))  # Clamp 5%-40%

    def _adjust_verbosity(self, response: str, verbosity: str) -> str:
        """Adjust response length based on verbosity setting.
        
        Note: We avoid aggressive truncation to prevent mid-sentence cuts.
        Only very long responses get trimmed, and always at sentence boundaries.
        """
        words = response.split()
        word_count = len(words)

        if verbosity == "short":
            # Target: <100 words, but only if response is excessively long
            if word_count > 150:
                # Truncate at sentence boundary
                truncated = " ".join(words[:100])
                # Find last sentence-ending punctuation
                for punct in [". ", "! ", "? "]:
                    last_idx = truncated.rfind(punct)
                    if last_idx > len(truncated) // 2:  # At least half the content
                        return truncated[:last_idx + 1].strip()
                return truncated.strip()
        elif verbosity == "medium":
            # Target: reasonable length - only trim extremely long responses
            if word_count > 500:
                truncated = " ".join(words[:400])
                for punct in [". ", "! ", "? "]:
                    last_idx = truncated.rfind(punct)
                    if last_idx > len(truncated) // 2:
                        return truncated[:last_idx + 1].strip()
                return truncated.strip()
        elif verbosity == "deep":
            # Target: >150 words - expand if needed
            if word_count < 100:
                # Keep as is or add more detail
                pass

        return response

    def _apply_tone_modulation(
        self,
        response: str,
        tone: str,
        identity_core: Dict,
        emotional_state: Dict
    ) -> str:
        """Tone is expressed through the system prompt and LLM generation.
        Post-hoc word replacement is removed to avoid overriding LLM intent.
        """
        return response

    def _inject_personality_traits(
        self,
        response: str,
        identity_core: Dict,
        context: str = "chat"
    ) -> str:
        """Personality is expressed through the system prompt and identity_core passed to the LLM.
        Post-hoc word replacement and prefix injection are removed to avoid overriding LLM output.
        Only a very light playfulness cue (trailing '!') is kept as it doesn't alter meaning.
        """
        playfulness = identity_core.get("playfulness", 0.5)
        if playfulness > 0.65 and "!" not in response and response.endswith("."):
            response = response[:-1] + "!"

        return response

    def _replace_user_name_placeholders(self, response: str, user_facts: list) -> str:
        """
        Replace [User Name] placeholders with the actual user name extracted from facts.
        The name is derived dynamically from stored facts — no hardcoded values.
        """
        import re

        user_name = None

        # Patterns that indicate a name follows (e.g. "my name is X", "call me X",
        # "introduced himself as X", "user's name is X")
        name_patterns = [
            re.compile(r"(?:my name is|name['s]* is|call(?:ed)? me|introduced (?:himself|herself|themselves)(?: as)?)\s+([A-Z][a-z]{1,})", re.IGNORECASE),
            re.compile(r"(?:user(?:'s)? name is|the user is called)\s+([A-Z][a-z]{1,})", re.IGNORECASE),
        ]

        for fact in user_facts:
            fact_str = str(fact)
            for pattern in name_patterns:
                m = pattern.search(fact_str)
                if m:
                    candidate = m.group(1).strip().capitalize()
                    # Sanity check: skip generic words
                    if candidate.lower() not in {"himself", "herself", "user", "name", "called", "person"}:
                        user_name = candidate
                        break
            if user_name:
                break

        if user_name:
            placeholders = [
                r'\[User Name\]',
                r'\[USER NAME\]',
                r'\[user name\]',
                r'\[User\]',
                r'\[USER\]',
                r'\[user\]',
            ]
            for placeholder in placeholders:
                response = re.sub(placeholder, user_name, response, flags=re.IGNORECASE)

        return response

    def _filter_debug_commentary(
        self,
        response: str,
        identity_core: Dict
    ) -> str:
        """
        Filter out debug-like meta-commentary while preserving legitimate analytical insights.
        
        Removes patterns like:
        - "(A pause – a slight dilation in processing time...)"
        - "(A subtle shift – a slight increase in 'analytical depth')"
        - "(A gentle shift in my processing – a subtle increase in 'stability')"
        
        But preserves natural expressions when high analytical_depth legitimately calls for it:
        - "(thoughtfully)" - natural analytical pause
        - "(after considering)" - legitimate analytical reflection
        """
        analytical_depth = identity_core.get("analytical_depth", 0.5)
        
        # Debug-like patterns to remove (regardless of analytical depth)
        debug_patterns = [
            r'\(A pause\s*[–-]\s*a slight (shift|dilation) in.*?\)',
            r'\(A subtle shift\s*[–-]\s*a slight (increase|decrease) in.*?\)',
            r'\(A (gentle|brief) shift in my processing.*?\)',
            r'\(A (slight|subtle) (decrease|increase) in.*?\)',
            r'\(A (brief|momentary) pause\s*[–-]\s*.*?processing.*?\)',
            r'\(.*?flicker of processing activity.*?\)',
            r'\(.*?dilation in processing time.*?\)',
            r'\(.*?shift in my processing speed.*?\)',
        ]
        
        # Remove debug patterns
        import re
        for pattern in debug_patterns:
            response = re.sub(pattern, '', response, flags=re.IGNORECASE | re.DOTALL)
        
        # Clean up any double spaces or orphaned newlines left behind
        response = re.sub(r'\n\s*\n\s*\n', '\n\n', response)  # Triple+ newlines -> double
        response = re.sub(r'  +', ' ', response)  # Multiple spaces -> single
        response = response.strip()
        
        return response

    def _match_emotional_state(
        self,
        response: str,
        emotional_state: Dict,
        user_message: str = ""
    ) -> str:
        """Emotional state is expressed through the system prompt and LLM generation.
        Mechanical phrase prepending is removed to avoid robotic-sounding injections.
        """
        return response

    def _inject_quirk(self, response: str, identity_core: Dict) -> str:
        """Inject subtle human-like quirks."""
        quirk_type = random.choice(["hesitation", "reflection", "tic"])

        if quirk_type == "hesitation" and len(response) > 20:
            # Add subtle hesitation at start
            hesitation = random.choice(self.QUIRKS["hesitations"])
            response = hesitation + " " + response

        elif quirk_type == "reflection" and "?" not in response:
            # Add reflective phrase
            reflection = random.choice(self.QUIRKS["reflective_phrases"])
            response = reflection + " " + response

        elif quirk_type == "tic":
            # Add personality tic (rarely)
            tic = random.choice(self.QUIRKS["personality_tics"])
            sentences = response.split(". ")
            if sentences and len(sentences[0]) > 20:
                sentences[0] = tic + " " + sentences[0].lower()
                response = ". ".join(sentences)

        return response

    def apply_emotional_modulation(
        self,
        response: str,
        emotional_state: Dict,
        intent: str
    ) -> str:
        """
        Apply emotional state modulation on top of response.
        Handles joy, calmness, curiosity, warmth.
        """
        joy = emotional_state.get("joy", 0.5)
        calmness = emotional_state.get("calmness", 0.5)
        curiosity = emotional_state.get("curiosity", 0.5)
        warmth = emotional_state.get("warmth", 0.5)

        # High joy: add mild enthusiasm — but never destroy punctuation or alter meaning
        if joy > 0.7 and intent != "technical":
            if "is good" in response:
                response = response.replace("is good", "is great")

        # High curiosity: add questioning tone
        if curiosity > 0.7:
            # Add "I'm curious..." phrases sparingly
            if "?" not in response and len(response.split()) > 20:
                sentences = response.split(". ")
                if sentences:
                    questions = [
                        "What aspects interest you most?",
                        "Have you considered...?",
                        "I'm curious how..."
                    ]
                    sentences.append(random.choice(questions))
                    response = ". ".join(sentences)

        return response

    def detect_response_mode_from_intent(self, intent: str, identity_core: Dict) -> Dict:
        """
        Map intent directly to response mode.
        """
        base_modes = {
            "technical": {"verbosity": "deep", "tone": "analytical"},
            "emotional": {"verbosity": "medium", "tone": "warm"},
            "philosophical": {"verbosity": "deep", "tone": "analytical"},
            "casual": {"verbosity": "short", "tone": "warm"},
            "meta": {"verbosity": "medium", "tone": "neutral"},
            "memory_related": {"verbosity": "short", "tone": "neutral"},
            "instruction": {"verbosity": "medium", "tone": "neutral"}
        }

        mode = base_modes.get(intent, {"verbosity": "medium", "tone": "neutral"})

        # Personality-based adjustments
        warmth = identity_core.get("emotional_warmth", 0.5)
        confidence = identity_core.get("confidence", 0.5)

        # Never very warm if low warmth trait
        if warmth < 0.4 and mode["tone"] == "warm":
            mode["tone"] = "neutral"

        # Adjust verbosity if low confidence
        if confidence < 0.4 and mode["verbosity"] == "deep":
            mode["verbosity"] = "medium"

        return mode
