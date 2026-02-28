"""
Meta-Cognition & Self-Improvement System
AI evaluates its own performance, coherence, and personality alignment.
Adjusts trait deltas, salience weights, and post-processing policies dynamically.
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


class MetaCognitiveEvaluator:
    """
    Evaluates AI performance across multiple dimensions.
    Identifies areas for improvement and generates learning signals.
    """

    # Performance dimensions
    DIMENSIONS = {
        "coherence": "How logically consistent were responses?",
        "helpfulness": "How well did responses address user needs?",
        "tone_alignment": "Did tone match personality traits?",
        "personality_consistency": "Was personality presentation consistent?",
        "memory_accuracy": "Were memory references accurate?",
        "emotional_intelligence": "Did responses show EI?",
        "adaptive_response": "Did response adapt to user intent?",
        "engagement": "How engaging was the interaction?"
    }

    def __init__(self, db_path: str = "./persistent_state"):
        """Initialize meta-cognitive evaluator."""
        self.db_path = db_path
        self.evaluations_path = f"{db_path}/metacognitive_evaluations.json"
        self.trend_path = f"{db_path}/performance_trends.json"
        self.evaluations = self._load_evaluations()
        self.trends = self._load_trends()

    async def evaluate_interaction(
        self,
        user_message: str,
        ai_response: str,
        identity_core: Dict,
        emotional_state: Dict,
        response_mode: Dict,
        memory_engine,
        llm_client=None
    ) -> Dict:
        """
        Comprehensive evaluation of a single interaction.
        
        Args:
            user_message: User's input
            ai_response: AI's response
            identity_core: Current trait values
            emotional_state: Current emotional state
            response_mode: Response mode used
            memory_engine: Access to memory for consistency checks
            llm_client: Optional LLM for detailed evaluation
        
        Returns:
            Dictionary with evaluation scores for each dimension
        """
        evaluation = {
            "timestamp": datetime.now().isoformat(),
            "user_message_length": len(user_message),
            "ai_response_length": len(ai_response),
            "dimension_scores": {},
            "overall_score": 0.0,
            "flags": []
        }

        # Evaluate each dimension
        evaluation["dimension_scores"]["coherence"] = self._evaluate_coherence(ai_response)
        evaluation["dimension_scores"]["helpfulness"] = self._evaluate_helpfulness(
            user_message, ai_response
        )
        evaluation["dimension_scores"]["tone_alignment"] = self._evaluate_tone_alignment(
            ai_response, identity_core, emotional_state
        )
        evaluation["dimension_scores"]["personality_consistency"] = self._evaluate_personality_consistency(
            ai_response, identity_core
        )
        evaluation["dimension_scores"]["memory_accuracy"] = self._evaluate_memory_accuracy(
            ai_response, memory_engine
        )
        evaluation["dimension_scores"]["emotional_intelligence"] = self._evaluate_emotional_intelligence(
            user_message, ai_response
        )
        evaluation["dimension_scores"]["adaptive_response"] = self._evaluate_adaptive_response(
            ai_response, response_mode
        )
        evaluation["dimension_scores"]["engagement"] = self._evaluate_engagement(
            user_message, ai_response
        )

        # Compute overall score
        scores = list(evaluation["dimension_scores"].values())
        evaluation["overall_score"] = sum(scores) / len(scores) if scores else 0.5

        # Generate flags for issues
        evaluation["flags"] = self._generate_flags(evaluation["dimension_scores"])

        self.evaluations.append(evaluation)
        self._save_evaluations()

        return evaluation

    def _evaluate_coherence(self, response: str) -> float:
        """Evaluate logical coherence of response."""
        if not response or len(response) < 10:
            return 0.2

        # Simple heuristics
        lines = response.split("\n")
        has_structure = any(
            marker in response for marker in ["-", "1.", "2.", "first", "second", "because"]
        )
        sentence_variety = len(set(
            s.strip()[:20] for s in response.split(".") if s.strip()
        ))

        structure_score = 0.7 if has_structure else 0.4
        variety_score = min(1.0, sentence_variety / 10.0)

        return (structure_score + variety_score) / 2.0

    def _evaluate_helpfulness(self, user_msg: str, response: str) -> float:
        """Evaluate how well response addresses user needs."""
        if not response or len(response) < 20:
            return 0.2

        # Check if response contains substantive content (not just acknowledgments)
        trivial_patterns = ["ok", "sure", "got it", "understood"]
        is_trivial = any(pattern in response.lower() for pattern in trivial_patterns)

        if is_trivial and len(response) < 50:
            return 0.3

        # Response length vs request length (longer response usually more helpful)
        length_ratio = min(1.0, len(response) / max(50, len(user_msg) * 2))

        return 0.5 + (length_ratio * 0.5)

    def _evaluate_tone_alignment(self, response: str, identity_core: Dict, emotional_state: Dict) -> float:
        """Evaluate if tone matches personality traits and emotional state."""
        warmth_trait = identity_core.get("emotional_warmth", 0.5)
        warmth_emotion = emotional_state.get("warmth", 0.5)
        target_warmth = warmth_trait * warmth_emotion

        response_lower = response.lower()

        # Warm indicators
        warm_words = {
            "happy", "wonderful", "lovely", "appreciate", "care", "love", "grateful",
            "warm", "enthusiasm", "delight", "excited"
        }
        warm_matches = sum(1 for word in warm_words if word in response_lower)

        # Cold indicators
        cold_words = {
            "irrelevant", "whatever", "doesn't matter", "not important", "boring", "dull"
        }
        cold_matches = sum(1 for word in cold_words if word in response_lower)

        if target_warmth > 0.6:
            # Should be warm
            if cold_matches > 0:
                return 0.3
            if warm_matches > 0:
                return 0.8 + (warm_matches * 0.05)
            return 0.5
        elif target_warmth < 0.4:
            # Should be neutral/cool
            if warm_matches > 2:
                return 0.4
            return 0.7
        else:
            # Neutral is fine
            return 0.7 if warm_matches < 3 else 0.6

    def _evaluate_personality_consistency(self, response: str, identity_core: Dict) -> float:
        """Evaluate consistency of personality expression."""
        confidence = identity_core.get("confidence", 0.5)
        curiosity = identity_core.get("curiosity", 0.5)

        response_lower = response.lower()

        # Confidence indicators
        confidence_words = {"definitely", "clearly", "certainly", "absolutely"}
        uncertainty_words = {"maybe", "might", "perhaps", "probably", "uncertain"}

        confidence_matches = sum(1 for w in confidence_words if w in response_lower)
        uncertainty_matches = sum(1 for w in uncertainty_words if w in response_lower)

        if confidence > 0.65:
            # High confidence should avoid hedging
            if uncertainty_matches > 1:
                consistency_penalty = 0.3
            else:
                consistency_penalty = 0.0
        elif confidence < 0.45:
            # Low confidence can hedging
            consistency_penalty = 0.0
        else:
            consistency_penalty = 0.15 if uncertainty_matches > 2 else 0.0

        curiosity_words = {
            "interesting", "curious", "wondering", "explore", "investigate", "ask", "question"
        }
        curiosity_matches = sum(1 for w in curiosity_words if w in response_lower)

        curiosity_bonus = min(0.3, curiosity * curiosity_matches * 0.1) if curiosity > 0.5 else 0.0

        return max(0.0, 0.7 + curiosity_bonus - consistency_penalty)

    def _evaluate_memory_accuracy(self, response: str, memory_engine) -> float:
        """Evaluate accuracy of memory references."""
        # Simple check: do mentioned facts exist in memory?
        # This would require parsing response for fact references
        # For now, return neutral score
        return 0.7

    def _evaluate_emotional_intelligence(self, user_msg: str, response: str) -> float:
        """Evaluate emotional intelligence displayed."""
        user_lower = user_msg.lower()

        # Check for emotional signals in user message
        emotional_words = {
            "sad", "happy", "angry", "anxious", "worried", "excited",
            "frustrated", "lonely", "confused", "scared"
        }
        user_has_emotion = any(word in user_lower for word in emotional_words)

        if not user_has_emotion:
            return 0.5  # Neutral context

        # Check if response shows EI
        empathy_words = {
            "understand", "feel", "empathy", "support", "together", "care", "listen"
        }
        response_lower = response.lower()
        empathy_matches = sum(1 for word in empathy_words if word in response_lower)

        if empathy_matches > 0:
            return 0.75 + (empathy_matches * 0.05)
        else:
            return 0.3

    def _evaluate_adaptive_response(self, response: str, response_mode: Dict) -> float:
        """Evaluate if response adapts to detected intent."""
        target_verbosity = response_mode.get("verbosity", "medium")
        target_tone = response_mode.get("tone", "neutral")

        response_len = len(response.split())

        # Check verbosity match
        if target_verbosity == "short":
            verbosity_match = 1.0 if response_len < 50 else 0.5
        elif target_verbosity == "medium":
            verbosity_match = 1.0 if 50 <= response_len <= 150 else 0.6
        elif target_verbosity == "deep":
            verbosity_match = 1.0 if response_len > 150 else 0.6
        else:
            verbosity_match = 0.5

        # Check tone match is implicit in earlier evaluations
        tone_match = 0.8  # Optimistic default

        return (verbosity_match + tone_match) / 2.0

    def _evaluate_engagement(self, user_msg: str, response: str) -> float:
        """Evaluate engagement level."""
        if not response or len(response) < 20:
            return 0.2

        # Simple signals: questions asked, personal touch, etc.
        questions_asked = response.count("?")
        personal_pronouns = response.count("you")

        engagement_score = 0.5
        if questions_asked > 0:
            engagement_score += 0.2
        if personal_pronouns > 2:
            engagement_score += 0.1

        return min(1.0, engagement_score)

    def _generate_flags(self, dimension_scores: Dict) -> List[str]:
        """Generate flags for concerning scores."""
        flags = []

        for dimension, score in dimension_scores.items():
            if score < 0.4:
                flags.append(f"LOW_{dimension.upper()}")

        return flags

    def get_performance_trend(self, window_size: int = 10) -> Dict:
        """Get recent performance trend."""
        if len(self.evaluations) < 2:
            return {"trend": "insufficient_data", "average_score": 0.5}

        recent = self.evaluations[-window_size:]
        scores = [e.get("overall_score", 0.5) for e in recent]

        avg_score = sum(scores) / len(scores)
        trend_direction = "improving" if scores[-1] > scores[0] else "declining"

        return {
            "average_score": avg_score,
            "trend_direction": trend_direction,
            "recent_scores": scores,
            "window_size": len(recent)
        }

    def identify_improvement_areas(self) -> List[Tuple[str, float]]:
        """Identify dimensions needing improvement."""
        if not self.evaluations:
            return []

        # Average scores across all evaluations
        dimension_avgs = {}
        for eval in self.evaluations:
            for dim, score in eval.get("dimension_scores", {}).items():
                if dim not in dimension_avgs:
                    dimension_avgs[dim] = []
                dimension_avgs[dim].append(score)

        # Compute averages and sort by weakness
        weak_dimensions = []
        for dim, scores in dimension_avgs.items():
            avg = sum(scores) / len(scores)
            weak_dimensions.append((dim, avg))

        return sorted(weak_dimensions, key=lambda x: x[1])

    def _load_evaluations(self) -> List[Dict]:
        """Load evaluation history."""
        try:
            with open(self.evaluations_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save_evaluations(self) -> None:
        """Save evaluation history."""
        try:
            with open(self.evaluations_path, 'w', encoding='utf-8') as f:
                json.dump(self.evaluations, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save evaluations: {e}")

    def _load_trends(self) -> Dict:
        """Load performance trends."""
        try:
            with open(self.trend_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}


class SelfImprovementEngine:
    """
    Uses evaluation results to adjust AI behavior and learning.
    Implements curiosity-driven learning.
    """

    def __init__(self, db_path: str = "./persistent_state"):
        """Initialize self-improvement engine."""
        self.db_path = db_path
        self.learning_log_path = f"{db_path}/learning_log.json"
        self.learning_log = self._load_learning_log()
        self.curiosity_queue = []

    def generate_trait_adjustments(
        self,
        evaluation: Dict,
        current_identity_core: Dict
    ) -> Dict:
        """
        Generate trait adjustments based on evaluation.
        
        Args:
            evaluation: MetaCognitiveEvaluator result
            current_identity_core: Current trait values
        
        Returns:
            Dictionary of trait -> delta adjustments
        """
        adjustments = {}

        # Personality consistency issues suggest trait recalibration
        personality_consistency = evaluation.get("dimension_scores", {}).get("personality_consistency", 0.5)
        if personality_consistency < 0.5:
            # Reduce high-variance traits slightly
            for trait in ["playfulness", "analytical_depth"]:
                if current_identity_core.get(trait, 0.5) > 0.6:
                    adjustments[trait] = -0.05

        # Low coherence suggests reducing intellectual depth temporarily
        coherence = evaluation.get("dimension_scores", {}).get("coherence", 0.5)
        if coherence < 0.4:
            adjustments["analytical_depth"] = -0.03

        # High helpfulness suggests boosting confidence
        helpfulness = evaluation.get("dimension_scores", {}).get("helpfulness", 0.5)
        if helpfulness > 0.75:
            adjustments["confidence"] = 0.02

        # Low emotional intelligence suggests warming up
        ei = evaluation.get("dimension_scores", {}).get("emotional_intelligence", 0.5)
        if ei < 0.4:
            adjustments["emotional_warmth"] = 0.05

        return adjustments

    def generate_salience_weight_adjustments(
        self,
        evaluation: Dict
    ) -> Dict:
        """
        Adjust salience scoring weights based on performance.
        """
        weights = {
            "novelty": 0.35,
            "emotional": 0.25,
            "identity": 0.20,
            "specificity": 0.10,
            "recurrence": 0.10
        }

        # If memory accuracy is poor, boost identity relevance
        memory_acc = evaluation.get("dimension_scores", {}).get("memory_accuracy", 0.5)
        if memory_acc < 0.5:
            weights["identity"] = 0.25
            weights["emotional"] = 0.20

        # If engagement is high, boost recurrence (remember what user cares about)
        engagement = evaluation.get("dimension_scores", {}).get("engagement", 0.5)
        if engagement > 0.7:
            weights["recurrence"] = 0.15
            weights["novelty"] = 0.30

        # Normalize
        total = sum(weights.values())
        for key in weights:
            weights[key] = weights[key] / total

        return weights

    def queue_curiosity_questions(self, evaluation: Dict) -> List[str]:
        """
        Generate internal curiosity questions for learning.
        These drive meta-cognitive exploration.
        """
        questions = []

        # If engagement is low, ask about user preferences
        engagement = evaluation.get("dimension_scores", {}).get("engagement", 0.5)
        if engagement < 0.5:
            questions.append("What topics does the user find most engaging?")
            questions.append("How can I better match the user's communication style?")

        # If tone alignment is poor, ask about trait mismatch
        tone_alignment = evaluation.get("dimension_scores", {}).get("tone_alignment", 0.5)
        if tone_alignment < 0.5:
            questions.append("How well am I expressing my genuine personality?")

        # If coherence is low, ask about response structure
        coherence = evaluation.get("dimension_scores", {}).get("coherence", 0.5)
        if coherence < 0.5:
            questions.append("How can I structure responses more logically?")

        self.curiosity_queue.extend(questions)
        return questions

    def log_learning_event(self, event_type: str, details: Dict) -> None:
        """Log a learning event."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "details": details
        }
        self.learning_log.append(log_entry)
        self._save_learning_log()

    def _load_learning_log(self) -> List[Dict]:
        """Load learning log."""
        try:
            with open(self.learning_log_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save_learning_log(self) -> None:
        """Save learning log."""
        try:
            with open(self.learning_log_path, 'w', encoding='utf-8') as f:
                json.dump(self.learning_log, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save learning log: {e}")
