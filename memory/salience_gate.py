"""
Salience Gate: ML-based intelligent filtering for memory storage.
Determines whether information is worth remembering without LLM calls.
Uses semantic similarity and contextual analysis.
"""

import logging
from typing import TYPE_CHECKING, Dict, Optional, Tuple
from sentence_transformers import util

if TYPE_CHECKING:
    from memory.salience_optimizer import SalienceOptimizer

logger = logging.getLogger(__name__)

class SalienceGate:
    """
    Intelligent salience filtering using embeddings.
    Classifies whether text contains salient information.
    """
    
    # High-value patterns (should be remembered)
    SALIENT_KEYWORDS = {
        "personal_facts": [
            "name", "live", "work", "job", "profession",
            "birthday", "anniversary", "family", "partner",
            "goal", "dream", "want", "love", "hate",
            "interested", "hobby", "passion", "skill"
        ],
        "decisions": [
            "decided", "chose", "will do", "plan to",
            "committed", "resolved", "determined"
        ],
        "events": [
            "happened", "occurred", "experienced", "underwent",
            "achieved", "completed", "finished", "started"
        ],
        "preferences": [
            "prefer", "like", "dislike", "favorite",
            "best", "worst", "always", "never"
        ]
    }
    
    # Low-value patterns (should be filtered)
    TRIVIAL_KEYWORDS = {
        "greetings": [
            "hello", "hi ", "hey", "howdy", "good morning",
            "good afternoon", "good evening", "goodbye", "bye"
        ],
        "acknowledgments": [
            "ok", "okay", "alright", "sure", "thanks",
            "thank you", "no problem", "got it", "understood"
        ],
        "filler": [
            "um", "uh", "like", "you know", "kind of",
            "sort of", "basically", "essentially", "anyway"
        ],
        "meta_conversation": [
            "what did you say", "repeat that", "say again",
            "can you clarify", "explain that", "rephrase"
        ]
    }
    
    def __init__(self, embedding_model=None, threshold: float = 0.0, optimizer: Optional["SalienceOptimizer"] = None):
        """
        Initialize salience gate.

        Args:
            embedding_model: Optional sentence-transformers embedding function
            threshold: Salience score threshold (-1.0 to 1.0)
                      -1.0: Very permissive (saves almost everything)
                       0.0: Balanced (default)
                       1.0: Very strict (saves only highly salient information)
            optimizer: Optional SalienceOptimizer for adaptive weight tuning
        """
        self.embedding_model = embedding_model
        self.threshold = max(-1.0, min(1.0, threshold))
        self.optimizer: Optional["SalienceOptimizer"] = optimizer
        self.interaction_history = []  # Track salience scores for learning
    
    def compute_salience_score(
        self,
        text: str,
        conversation_context: str = "",
        user_message: str = ""
    ) -> Tuple[float, Dict]:
        """
        Compute salience score for given text.
        Uses multiple heuristics: keyword matching, length, embedding similarity.
        
        Returns:
            score: Float between -1.0 (trivial) and 1.0 (highly salient)
            metadata: Dict with breakdown of scoring factors
        """
        if not text or not isinstance(text, str):
            return -0.9, {"reason": "empty_or_invalid_text"}
        
        text = text.strip()
        if len(text) < 5:
            return -0.8, {"reason": "too_short"}
        
        score = 0.0
        factors = {}

        # Pull dynamic weights from optimizer (or use built-in defaults)
        w = self.optimizer.get_weights() if self.optimizer else {
            "trivial_penalty":  0.40,
            "salient_boost":    0.50,
            "length_weight":    0.20,
            "statement_weight": 0.15,
            "context_weight":   0.20,
            "novelty_weight":   0.15,
        }

        # 1. Keyword heuristics
        trivial_score = self._score_trivial_keywords(text)
        salient_score = self._score_salient_keywords(text)
        factors["trivial_match"] = trivial_score
        factors["salient_match"] = salient_score

        # Trivial content → low score
        if trivial_score > 0.3:
            score -= (trivial_score * w["trivial_penalty"])

        # Salient content → high score
        if salient_score > 0.2:
            score += (salient_score * w["salient_boost"])

        # 2. Length heuristic (sweet spot: 20-200 chars)
        length_score = self._score_length(len(text))
        factors["length_score"] = length_score
        score += (length_score * w["length_weight"])

        # 3. Dialogue/statement type
        statement_score = self._score_statement_type(text)
        factors["statement_type_score"] = statement_score
        score += (statement_score * w["statement_weight"])

        # 4. Context relevance (if embedding model available)
        if self.embedding_model and (conversation_context or user_message):
            context_score = self._score_context_relevance(
                text,
                conversation_context or user_message
            )
            factors["context_relevance"] = context_score
            score += (context_score * w["context_weight"])

        # 5. Novelty check (avoid redundant information)
        if self.interaction_history:
            novelty_score = self._score_novelty(text)
            factors["novelty_score"] = novelty_score
            score += (novelty_score * w["novelty_weight"])
        
        # Apply threshold adjustment
        score -= self.threshold
        
        # Clamp to [-1.0, 1.0]
        final_score = max(-1.0, min(1.0, score))
        factors["final_score"] = final_score
        factors["passes_threshold"] = final_score > 0.0
        
        return final_score, factors
    
    def _score_trivial_keywords(self, text: str) -> float:
        """Score how trivial the text is (0.0 = not trivial, 1.0 = very trivial)."""
        text_lower = text.lower()
        
        matches = 0
        total_keywords = sum(len(kws) for kws in self.TRIVIAL_KEYWORDS.values())
        
        for keywords in self.TRIVIAL_KEYWORDS.values():
            for kw in keywords:
                if kw in text_lower:
                    matches += 1
        
        return min(1.0, matches / max(1, total_keywords // 3))
    
    def _score_salient_keywords(self, text: str) -> float:
        """Score how salient the text is (0.0 = not salient, 1.0 = very salient)."""
        text_lower = text.lower()
        
        matches = 0
        total_keywords = sum(len(kws) for kws in self.SALIENT_KEYWORDS.values())
        
        for keywords in self.SALIENT_KEYWORDS.values():
            for kw in keywords:
                if kw in text_lower:
                    matches += 1
        
        return min(1.0, matches / max(1, total_keywords // 4))
    
    def _score_length(self, length: int) -> float:
        """Score based on text length (sweet spot: 20-200 chars)."""
        if length < 10:
            return -0.8
        elif length < 20:
            return -0.3
        elif length < 50:
            return 0.8
        elif length < 200:
            return 1.0
        elif length < 500:
            return 0.6
        elif length < 1000:
            return 0.2
        else:
            return -0.5  # Very long text might be redundant
    
    def _score_statement_type(self, text: str) -> float:
        """Score based on statement type (assertions > questions > commands)."""
        text_stripped = text.strip()
        
        if text_stripped.endswith("?"):
            return -0.3  # Questions are less salient
        elif any(text_stripped.startswith(prefix) for prefix in ["please", "can you", "help", "how"]):
            return -0.2  # Commands/requests less salient
        elif any(text_stripped.startswith(prefix) for prefix in ["i", "i've", "i'm", "my", "me"]):
            return 0.7  # First-person assertions are more salient
        else:
            return 0.3
    
    def _score_context_relevance(self, text: str, context: str) -> float:
        """Score relevance to conversation context using embeddings."""
        if not self.embedding_model or not context:
            return 0.0
        
        try:
            text_embed = self.embedding_model([text])[0]
            context_embed = self.embedding_model([context])[0]
            
            # Compute cosine similarity
            similarity = util.pytorch_cos_sim(text_embed, context_embed).item()
            
            # Map similarity [-1, 1] to score [-1, 1]
            return float(similarity)
        except Exception as e:
            logger.debug(f"Context relevance scoring failed: {e}")
            return 0.0
    
    def _score_novelty(self, text: str) -> float:
        """Score novelty based on similarity to recent interactions."""
        if not self.interaction_history:
            return 0.5
        
        try:
            current_embed = self.embedding_model([text])[0]
            
            # Compare to last 10 interactions
            recent_history = self.interaction_history[-10:]
            similarities = []
            
            for prev_text in recent_history:
                prev_embed = self.embedding_model([prev_text])[0]
                sim = util.pytorch_cos_sim(current_embed, prev_embed).item()
                similarities.append(sim)
            
            avg_similarity = sum(similarities) / len(similarities) if similarities else 0.0
            
            # High similarity (repetitive) → low novelty score
            # Low similarity (new) → high novelty score
            novelty = 1.0 - avg_similarity
            return float(novelty)
        except Exception as e:
            logger.debug(f"Novelty scoring failed: {e}")
            return 0.5
    
    def should_save(self, text: str, conversation_context: str = "") -> Tuple[bool, float]:
        """
        Determine if text should be saved to memory.
        
        Returns:
            should_save: Boolean indicating whether to save
            score: Salience score
        """
        score, factors = self.compute_salience_score(text, conversation_context)
        should_save = score > 0.0
        
        # Track for novelty scoring
        if should_save:
            self.interaction_history.append(text)
            # Keep history bounded
            if len(self.interaction_history) > 100:
                self.interaction_history = self.interaction_history[-100:]
        
        return should_save, score
    
    def set_threshold(self, threshold: float):
        """Adjust salience threshold at runtime."""
        self.threshold = max(-1.0, min(1.0, threshold))
        logger.info(f"Salience threshold set to {self.threshold}")
