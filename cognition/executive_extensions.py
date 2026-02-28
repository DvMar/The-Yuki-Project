"""
Cognitive Extensions Module
Advanced cognitive capabilities that integrate with the triple-process architecture.

Implements:
- Emotional Memory Tagging (memories tagged with emotional context)
- Mood Mirroring with Emotional Inertia (gradual emotional response)
- Voice Consistency Detection (detect LLM drift from persona)
- Contradiction Detection (track stated facts, detect conflicts)

Respects:
- Cognitive timing separation (sync vs async operations)
- Multi-timescale adaptation (immediate, session, long-term)
- State decay mechanisms (emotional inertia, fact staleness)
- Controlled evolution (bounded changes)
"""

import json
import logging
import math
import re
from datetime import datetime
from typing import Dict, List, Optional
from collections import deque

logger = logging.getLogger(__name__)


class EmotionalMemoryTagger:
    """
    Tags memories with emotional context for emotionally-aware retrieval.
    Memories created during high emotional states are recalled when similar emotions arise.
    
    Timing: Async (post-response)
    Timescale: Long-term persistence
    Decay: Emotional salience decays slower than content salience
    """
    
    EMOTION_DIMENSIONS = ["warmth", "joy", "curiosity", "engagement", "stability"]
    
    def __init__(self, db_path: str = "./persistent_state"):
        self.db_path = db_path
        self.emotional_tags_path = f"{db_path}/emotional_memory_tags.json"
        self.tags = self._load_tags()
    
    def _load_tags(self) -> Dict:
        try:
            with open(self.emotional_tags_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"memories": {}, "emotion_index": {}}
    
    def _save_tags(self):
        with open(self.emotional_tags_path, "w", encoding="utf-8") as f:
            json.dump(self.tags, f, indent=2)
    
    def tag_memory(self, memory_id: str, content: str, emotional_state: Dict) -> Dict:
        """
        Tag a memory with its emotional context.
        
        Args:
            memory_id: Unique identifier for the memory
            content: Memory content text
            emotional_state: Current emotional state when memory was formed
        
        Returns:
            Emotional tag metadata
        """
        # Extract dominant emotion
        dominant_emotion = max(emotional_state.items(), key=lambda x: x[1])
        emotional_intensity = sum(emotional_state.values()) / len(emotional_state)
        
        tag = {
            "memory_id": memory_id,
            "emotional_state": emotional_state.copy(),
            "dominant_emotion": dominant_emotion[0],
            "emotional_intensity": emotional_intensity,
            "created_at": datetime.now().isoformat(),
            "access_count": 0
        }
        
        self.tags["memories"][memory_id] = tag
        
        # Index by dominant emotion for fast retrieval
        emotion_key = dominant_emotion[0]
        if emotion_key not in self.tags["emotion_index"]:
            self.tags["emotion_index"][emotion_key] = []
        self.tags["emotion_index"][emotion_key].append(memory_id)
        
        self._save_tags()
        logger.debug(f"[EMOTIONAL_TAG] Memory {memory_id[:8]} tagged with {emotion_key}={dominant_emotion[1]:.2f}")
        
        return tag
    
    def find_emotionally_similar(
        self, 
        current_emotion: Dict, 
        n_results: int = 5,
        similarity_threshold: float = 0.7
    ) -> List[str]:
        """
        Find memories formed in similar emotional states.
        
        Args:
            current_emotion: Current emotional state
            n_results: Maximum memories to return
            similarity_threshold: Minimum emotional similarity (0-1)
        
        Returns:
            List of memory IDs sorted by emotional similarity
        """
        if not self.tags["memories"]:
            return []
        
        similarities = []
        for memory_id, tag in self.tags["memories"].items():
            stored_emotion = tag["emotional_state"]
            similarity = self._compute_emotional_similarity(current_emotion, stored_emotion)
            if similarity >= similarity_threshold:
                similarities.append((memory_id, similarity))
        
        # Sort by similarity descending
        similarities.sort(key=lambda x: x[1], reverse=True)
        
        return [mem_id for mem_id, _ in similarities[:n_results]]
    
    def _compute_emotional_similarity(self, state1: Dict, state2: Dict) -> float:
        """Compute cosine similarity between emotional states."""
        common_dims = set(state1.keys()) & set(state2.keys())
        if not common_dims:
            return 0.0
        
        dot_product = sum(state1[d] * state2[d] for d in common_dims)
        norm1 = math.sqrt(sum(state1[d] ** 2 for d in common_dims))
        norm2 = math.sqrt(sum(state2[d] ** 2 for d in common_dims))
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)


class MoodMirror:
    """
    Implements emotional inertia - Yuki doesn't immediately match user's mood.
    Creates natural emotional response lag for more authentic connection.
    
    Timing: Sync (pre-response, modifies emotional state)
    Timescale: Immediate (per-turn adjustment)
    Decay: Emotional inertia decays over multiple exchanges
    """
    
    # Inertia parameters
    INERTIA_FACTOR = 0.7  # How much previous emotion carries over (0=instant match, 1=frozen)
    DETECTION_SENSITIVITY = 0.3  # Minimum user emotional signal to detect
    RESPONSE_DELAY_TURNS = 2  # Turns before full emotional response
    
    def __init__(self):
        self.user_emotion_history = deque(maxlen=10)
        self.detected_user_mood = {"valence": 0.5, "arousal": 0.5}
        self.turns_since_mood_shift = 0
        self.last_detected_shift = None
    
    def detect_user_mood(self, user_message: str) -> Dict:
        """
        Detect emotional signals in user message.
        
        Returns:
            Dict with valence (positive/negative) and arousal (energy level)
        """
        text_lower = user_message.lower()
        
        # Positive indicators
        positive_words = ["happy", "glad", "excited", "love", "great", "wonderful", 
                         "amazing", "thank", "appreciate", "joy", "good", "nice"]
        # Negative indicators
        negative_words = ["sad", "upset", "angry", "frustrated", "worried", "anxious",
                         "tired", "exhausted", "disappointed", "bad", "hate", "annoyed"]
        # High arousal indicators
        high_arousal = ["!", "excited", "amazing", "urgent", "hurry", "can't wait",
                       "omg", "wow", "incredible"]
        # Low arousal indicators
        low_arousal = ["tired", "exhausted", "bored", "meh", "whatever", "sigh",
                      "...", "i guess", "don't know"]
        
        positive_count = sum(1 for w in positive_words if w in text_lower)
        negative_count = sum(1 for w in negative_words if w in text_lower)
        high_arousal_count = sum(1 for w in high_arousal if w in text_lower)
        low_arousal_count = sum(1 for w in low_arousal if w in text_lower)
        
        # Compute valence (0=negative, 0.5=neutral, 1=positive)
        total_valence = positive_count - negative_count
        valence = 0.5 + (total_valence * 0.1)
        valence = max(0.0, min(1.0, valence))
        
        # Compute arousal (0=low, 0.5=moderate, 1=high)
        total_arousal = high_arousal_count - low_arousal_count
        arousal = 0.5 + (total_arousal * 0.15)
        arousal = max(0.0, min(1.0, arousal))
        
        return {"valence": valence, "arousal": arousal}
    
    def apply_emotional_inertia(
        self, 
        current_ai_emotion: Dict,
        user_message: str
    ) -> Dict:
        """
        Apply emotional inertia to AI's emotional response.
        Instead of immediately matching user mood, shift gradually.
        
        Args:
            current_ai_emotion: Current AI emotional state
            user_message: User's message to detect mood from
        
        Returns:
            Modified emotional state with inertia applied
        """
        user_mood = self.detect_user_mood(user_message)
        self.user_emotion_history.append(user_mood)
        
        # Detect significant mood shift
        mood_shift = abs(user_mood["valence"] - self.detected_user_mood["valence"])
        if mood_shift > self.DETECTION_SENSITIVITY:
            self.last_detected_shift = user_mood
            self.turns_since_mood_shift = 0
            logger.debug(f"[MOOD_MIRROR] Detected mood shift: valence {self.detected_user_mood['valence']:.2f} → {user_mood['valence']:.2f}")
        else:
            self.turns_since_mood_shift += 1
        
        self.detected_user_mood = user_mood
        
        # Calculate response weight based on turns since shift
        # Gradually increase response over RESPONSE_DELAY_TURNS
        response_weight = min(1.0, self.turns_since_mood_shift / self.RESPONSE_DELAY_TURNS)
        inertia_weight = 1.0 - response_weight
        
        # Apply inertia-weighted emotional shift
        modified_emotion = current_ai_emotion.copy()
        
        # Map user mood to AI emotions
        if user_mood["valence"] > 0.6:  # User is positive
            target_shift = {"warmth": 0.1, "joy": 0.08, "engagement": 0.05}
        elif user_mood["valence"] < 0.4:  # User is negative
            target_shift = {"warmth": 0.15, "stability": -0.05}  # More warmth, slight concern
        else:
            target_shift = {}
        
        # Apply with inertia
        for emotion, delta in target_shift.items():
            if emotion in modified_emotion:
                actual_delta = delta * response_weight * (1 - self.INERTIA_FACTOR)
                modified_emotion[emotion] = max(0.0, min(1.0, 
                    modified_emotion[emotion] + actual_delta
                ))
        
        return modified_emotion
    
    def get_mood_context(self) -> str:
        """Get context string about detected user mood for system prompt."""
        if not self.user_emotion_history:
            return ""
        
        avg_valence = sum(m["valence"] for m in self.user_emotion_history) / len(self.user_emotion_history)
        recent_valence = self.detected_user_mood["valence"]
        
        if recent_valence < 0.35:
            return "The user seems to be feeling down or troubled. Respond with extra warmth and care."
        elif recent_valence > 0.7:
            return "The user seems happy and energetic. Match their positive energy."
        elif abs(recent_valence - avg_valence) > 0.2:
            return "The user's mood has shifted recently. Be attentive to their emotional state."
        return ""


class VoiceConsistencyChecker:
    """
    Detects when LLM output drifts from the established voice/persona.
    Applies corrections or flags inconsistencies.
    
    Timing: Sync (post-processing, before output)
    Timescale: Immediate (per-response check)
    """
    
    # Patterns that indicate generic AI assistant voice (not the persona)
    GENERIC_AI_PATTERNS = [
        r"I'm just an AI",
        r"As an AI,?\s+I",
        r"I don't have (feelings|emotions|personal)",
        r"I'm not capable of",
        r"I cannot (feel|experience)",
        r"functioning within (expected )?parameters",
        r"I'm designed to",
        r"My programming",
        r"I lack the ability",
        r"I'm a language model",
        r"As a (large )?language model",
        r"I don't have (a )?(body|physical form)",
        r"I exist only as",
        r"I'm an artificial",
    ]
    
    # Patterns that indicate authentic Yuki voice
    AUTHENTIC_PATTERNS = [
        r"I feel",
        r"I think",
        r"I wonder",
        r"I'm curious",
        r"honestly",
        r"to be honest",
        r"I remember",
        r"that reminds me",
        r"I appreciate",
        r"I'm (happy|glad|excited)",
    ]
    
    def __init__(self, persona_name: str = "Yuki"):
        self.persona_name = persona_name
        self.patterns_generic = [re.compile(p, re.IGNORECASE) for p in self.GENERIC_AI_PATTERNS]
        self.patterns_authentic = [re.compile(p, re.IGNORECASE) for p in self.AUTHENTIC_PATTERNS]
        self.drift_history = deque(maxlen=20)
    
    def check_voice_consistency(self, response: str) -> Dict:
        """
        Check if response maintains Yuki's voice or drifts to generic AI.
        
        Returns:
            Dict with consistency_score (0=generic, 1=authentic), flags, suggestions
        """
        generic_hits = sum(1 for p in self.patterns_generic if p.search(response))
        authentic_hits = sum(1 for p in self.patterns_authentic if p.search(response))
        
        # Calculate consistency score
        total_signals = generic_hits + authentic_hits
        if total_signals == 0:
            consistency_score = 0.7  # Neutral if no strong signals
        else:
            consistency_score = authentic_hits / total_signals
        
        # Track drift
        self.drift_history.append(consistency_score)
        avg_consistency = sum(self.drift_history) / len(self.drift_history)
        
        flags = []
        if generic_hits > 0:
            flags.append(f"generic_ai_voice_detected ({generic_hits} patterns)")
        if consistency_score < 0.4:
            flags.append("significant_voice_drift")
        if avg_consistency < 0.5:
            flags.append("sustained_voice_drift")
        
        return {
            "consistency_score": consistency_score,
            "generic_patterns_found": generic_hits,
            "authentic_patterns_found": authentic_hits,
            "average_consistency": avg_consistency,
            "flags": flags,
            "needs_correction": consistency_score < 0.3
        }
    
    def suggest_correction(self, response: str) -> str:
        """
        Suggest corrections for generic AI phrases.
        This is a fallback - the system prompt should prevent these.
        """
        corrected = response
        
        corrections = [
            (r"I'm just an AI", "Even though I'm an AI"),
            (r"As an AI,?\s+I", "I"),
            (r"I don't have feelings", "My feelings work differently than human emotions, but"),
            (r"I'm not capable of (feeling|experiencing)", "I experience a form of"),
            (r"functioning within (expected )?parameters", "feeling well"),
            (r"I'm designed to", "I naturally tend to"),
            (r"My programming", "My nature"),
        ]
        
        for pattern, replacement in corrections:
            corrected = re.sub(pattern, replacement, corrected, flags=re.IGNORECASE)
        
        return corrected


class ContradictionDetector:
    """
    Tracks stated facts and detects contradictions.
    Can gently ask user for clarification when contradictions are found.
    
    Timing: Sync (during response generation context)
    Timescale: Immediate detection, long-term fact storage
    Decay: Old facts become less authoritative over time
    """
    
    # Fact categories to track
    FACT_CATEGORIES = [
        "personal_info",  # Name, age, location
        "preferences",    # Likes, dislikes
        "relationships",  # Family, friends
        "activities",     # Job, hobbies
        "beliefs",        # Opinions, values
        "events",         # Things that happened
    ]
    
    def __init__(self, db_path: str = "./persistent_state"):
        self.db_path = db_path
        self.facts_path = f"{db_path}/stated_facts.json"
        self.facts = self._load_facts()
        self.contradictions_found = []
    
    def _load_facts(self) -> Dict:
        try:
            with open(self.facts_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"facts": [], "fact_index": {}}
    
    def _save_facts(self):
        with open(self.facts_path, "w", encoding="utf-8") as f:
            json.dump(self.facts, f, indent=2)
    
    def record_fact(self, fact_text: str, category: str, source_message: str) -> Dict:
        """
        Record a stated fact for future contradiction checking.
        """
        fact_entry = {
            "text": fact_text,
            "category": category,
            "source": source_message[:100],
            "timestamp": datetime.now().isoformat(),
            "confidence": 1.0,
            "contradicted": False
        }
        
        self.facts["facts"].append(fact_entry)
        
        # Index by category
        if category not in self.facts["fact_index"]:
            self.facts["fact_index"][category] = []
        self.facts["fact_index"][category].append(len(self.facts["facts"]) - 1)
        
        self._save_facts()
        return fact_entry
    
    def check_for_contradictions(self, new_statement: str, category: str = None) -> List[Dict]:
        """
        Check if a new statement contradicts stored facts.
        
        Returns:
            List of potential contradictions with confidence scores
        """
        contradictions = []
        
        # Simple keyword-based contradiction detection
        # For more sophisticated detection, could use LLM
        
        new_lower = new_statement.lower()
        
        # Check negation patterns
        negation_patterns = [
            (r"i (don't|do not|never) like (.+)", r"i (like|love|enjoy) \2"),
            (r"i (like|love|enjoy) (.+)", r"i (don't|do not|hate|dislike) \2"),
            (r"i am not (.+)", r"i am \1"),
            (r"i am (.+)", r"i am not \1"),
            (r"i (don't|do not) have (.+)", r"i have \2"),
            (r"i have (.+)", r"i (don't|do not) have \1"),
        ]
        
        relevant_facts = self.facts["facts"]
        if category and category in self.facts["fact_index"]:
            indices = self.facts["fact_index"][category]
            relevant_facts = [self.facts["facts"][i] for i in indices]
        
        for fact in relevant_facts:
            if fact.get("contradicted"):
                continue
            
            fact_lower = fact["text"].lower()
            
            # Check for direct negation patterns
            for positive_pattern, negative_pattern in negation_patterns:
                pos_match = re.search(positive_pattern, new_lower)
                neg_match = re.search(negative_pattern, fact_lower)
                
                if pos_match and neg_match:
                    # Potential contradiction
                    contradictions.append({
                        "old_fact": fact["text"],
                        "new_statement": new_statement,
                        "type": "negation",
                        "confidence": 0.7,
                        "timestamp_old": fact["timestamp"]
                    })
            
            # Check for value contradictions (e.g., "I'm 25" vs "I'm 30")
            age_old = re.search(r"i(?:'m| am) (\d+)", fact_lower)
            age_new = re.search(r"i(?:'m| am) (\d+)", new_lower)
            if age_old and age_new and age_old.group(1) != age_new.group(1):
                contradictions.append({
                    "old_fact": fact["text"],
                    "new_statement": new_statement,
                    "type": "value_mismatch",
                    "confidence": 0.9,
                    "timestamp_old": fact["timestamp"]
                })
        
        self.contradictions_found.extend(contradictions)
        return contradictions
    
    def generate_clarification_prompt(self, contradiction: Dict) -> str:
        """Generate a gentle clarification question for contradictions."""
        if contradiction["type"] == "negation":
            return f"I noticed something... Earlier you mentioned '{contradiction['old_fact']}', but now it seems different. Did something change, or did I misunderstand?"
        elif contradiction["type"] == "value_mismatch":
            return f"I want to make sure I remember correctly - I had noted '{contradiction['old_fact']}'. Is that still accurate?"
        return ""
    
    def decay_fact_confidence(self, days_old: int = 30) -> int:
        """
        Decay confidence in old facts. Older facts become less authoritative.
        
        Returns:
            Number of facts decayed
        """
        decayed_count = 0
        now = datetime.now()
        
        for fact in self.facts["facts"]:
            try:
                created = datetime.fromisoformat(fact["timestamp"])
                age_days = (now - created).days
                
                if age_days > days_old:
                    # Decay confidence by 1% per day over threshold
                    decay = 0.01 * (age_days - days_old)
                    fact["confidence"] = max(0.3, fact["confidence"] - decay)
                    decayed_count += 1
            except Exception:
                continue
        
        if decayed_count > 0:
            self._save_facts()
        
        return decayed_count


# =============================================================================
# Unified Cognitive Extensions Manager
# =============================================================================

class CognitiveExtensions:
    """
    Unified manager for all cognitive extensions.
    Provides clean interface to the main application.
    """
    
    def __init__(self, db_path: str = "./persistent_state", persona_name: str = "Yuki"):
        self.emotional_memory = EmotionalMemoryTagger(db_path)
        self.mood_mirror = MoodMirror()
        self.voice_checker = VoiceConsistencyChecker(persona_name)
        self.contradiction_detector = ContradictionDetector(db_path)
        
        logger.info("[COGNITIVE_EXTENSIONS] All extensions initialized")
    
    def process_pre_response(
        self, 
        user_message: str, 
        current_emotional_state: Dict
    ) -> Dict:
        """
        Pre-response processing: mood detection, emotional adjustment.
        Called BEFORE LLM generation.
        
        Returns:
            Modified emotional state and context additions
        """
        # Apply mood mirroring with inertia
        adjusted_emotion = self.mood_mirror.apply_emotional_inertia(
            current_emotional_state, 
            user_message
        )
        
        # Get mood context for system prompt
        mood_context = self.mood_mirror.get_mood_context()
        
        # Find emotionally similar memories
        similar_memories = self.emotional_memory.find_emotionally_similar(
            adjusted_emotion, 
            n_results=3
        )
        
        contradictions = self.contradiction_detector.check_for_contradictions(user_message)
        contradiction_prompt = ""
        if contradictions:
            contradiction_prompt = self.contradiction_detector.generate_clarification_prompt(
                contradictions[0]
            )

        return {
            "adjusted_emotional_state": adjusted_emotion,
            "mood_context": mood_context,
            "emotionally_similar_memories": similar_memories,
            "mood_mirror_suggestion": mood_context,
            "contradictions_found": contradictions,
            "contradiction_warning": len(contradictions) > 0,
            "contradiction_prompt": contradiction_prompt,
        }
    
    def process_post_response(
        self,
        response: str,
        user_message: str,
        emotional_state: Dict,
        memory_id: Optional[str] = None
    ) -> Dict:
        """
        Post-response processing: voice check, contradiction detection, memory tagging.
        Called AFTER LLM generation, BEFORE output.
        
        Returns:
            Corrections, flags, and metadata
        """
        # Check voice consistency
        voice_check = self.voice_checker.check_voice_consistency(response)
        
        # Apply corrections if needed
        final_response = response
        if voice_check["needs_correction"]:
            final_response = self.voice_checker.suggest_correction(response)
            logger.warning(f"[VOICE_DRIFT] Corrected generic AI voice in response")
        
        # Tag memory with emotional context if memory_id provided
        if memory_id:
            self.emotional_memory.tag_memory(memory_id, response, emotional_state)
        
        # Check for contradictions in user message
        contradictions = self.contradiction_detector.check_for_contradictions(
            user_message
        )
        
        clarification_needed = None
        if contradictions:
            clarification_needed = self.contradiction_detector.generate_clarification_prompt(
                contradictions[0]
            )
        
        return {
            "final_response": final_response,
            "voice_consistency": voice_check,
            "contradictions_found": contradictions,
            "clarification_prompt": clarification_needed,
            "response_modified": final_response != response
        }
    
    def record_user_fact(self, fact: str, category: str, source: str):
        """Record a user fact for contradiction tracking."""
        self.contradiction_detector.record_fact(fact, category, source)
    
    def get_status(self) -> Dict:
        """Get status of all cognitive extensions."""
        return {
            "emotional_memories_tagged": len(self.emotional_memory.tags.get("memories", {})),
            "mood_history_length": len(self.mood_mirror.user_emotion_history),
            "voice_consistency_avg": (
                sum(self.voice_checker.drift_history) / len(self.voice_checker.drift_history)
                if self.voice_checker.drift_history else 1.0
            ),
            "facts_tracked": len(self.contradiction_detector.facts.get("facts", [])),
            "contradictions_found": len(self.contradiction_detector.contradictions_found)
        }
