"""
Relationship Model Module
Models the evolving relationship between Yuki and the user.

Implements:
- Conversation Arc Tracking (story of the relationship)
- Relationship Stage Awareness (new → familiar → close → intimate)
- Response Style Learning (learn user's preferred interaction style)

Respects:
- Multi-timescale adaptation (session, long-term)
- State decay mechanisms (relationship stages have inertia)
- Controlled evolution (stage transitions are gradual)
- Proactive emergence gating (relationship insights surface appropriately)
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional
from collections import deque
from enum import Enum

logger = logging.getLogger(__name__)


class RelationshipStage(Enum):
    """Relationship development stages with progression thresholds."""
    NEW = "new"                    # 0-10 interactions, formal/exploratory
    FAMILIAR = "familiar"          # 10-50 interactions, comfortable
    CLOSE = "close"                # 50-150 interactions, personal
    INTIMATE = "intimate"          # 150+ interactions, deep connection


class ConversationArcTracker:
    """
    Tracks the narrative arc of the relationship over time.
    Records milestones, recurring themes, growth moments, and shared memories.
    
    Timing: Background (every 10 interactions)
    Timescale: Long-term (persists across sessions)
    Decay: Arc salience decays for old, unreferenced events
    """
    
    ARC_EVENT_TYPES = [
        "first_meeting",
        "milestone",           # Significant interaction count
        "breakthrough",        # Emotional breakthrough moment
        "shared_discovery",    # Learning something together
        "recurring_joke",      # Humor that gets referenced
        "support_moment",      # User needed support
        "growth_moment",       # User showed growth
        "conflict",            # Disagreement/tension
        "resolution",          # Resolved a conflict
        "deep_conversation",   # Particularly meaningful exchange
    ]
    
    def __init__(self, db_path: str = "./persistent_state"):
        self.db_path = db_path
        self.arc_path = f"{db_path}/conversation_arc.json"
        self.arc = self._load_arc()
    
    def _load_arc(self) -> Dict:
        try:
            with open(self.arc_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {
                "events": [],
                "themes": {},
                "milestones": [],
                "interaction_count": 0,
                "first_interaction": None,
                "relationship_summary": "",
                "last_updated": None
            }
    
    def _save_arc(self):
        self.arc["last_updated"] = datetime.now().isoformat()
        with open(self.arc_path, "w", encoding="utf-8") as f:
            json.dump(self.arc, f, indent=2)
    
    def record_interaction(self) -> int:
        """Record an interaction and return current count."""
        if not self.arc["first_interaction"]:
            self.arc["first_interaction"] = datetime.now().isoformat()
            self.add_event("first_meeting", "Our conversation began", salience=1.0)
        
        self.arc["interaction_count"] += 1
        count = self.arc["interaction_count"]
        
        # Check for milestones
        milestones = [10, 25, 50, 100, 150, 200, 300, 500, 1000]
        if count in milestones:
            self.add_event(
                "milestone", 
                f"We've had {count} conversations together",
                salience=0.8
            )
            self.arc["milestones"].append({
                "count": count,
                "timestamp": datetime.now().isoformat()
            })
        
        self._save_arc()
        return count
    
    def add_event(
        self, 
        event_type: str, 
        description: str, 
        salience: float = 0.5,
        context: str = ""
    ) -> Dict:
        """
        Add a significant event to the conversation arc.
        
        Args:
            event_type: Type from ARC_EVENT_TYPES
            description: Human-readable description
            salience: Importance score (0-1)
            context: Additional context from the conversation
        """
        event = {
            "type": event_type,
            "description": description,
            "salience": salience,
            "context": context[:200] if context else "",
            "timestamp": datetime.now().isoformat(),
            "interaction_number": self.arc["interaction_count"],
            "referenced_count": 0
        }
        
        self.arc["events"].append(event)
        logger.info(f"[ARC] New event: {event_type} - {description[:50]}")
        
        self._save_arc()
        return event
    
    def track_theme(self, theme: str, salience: float = 0.5):
        """
        Track a recurring theme in conversations.
        Themes that appear repeatedly gain salience.
        """
        if theme not in self.arc["themes"]:
            self.arc["themes"][theme] = {
                "first_seen": datetime.now().isoformat(),
                "occurrences": 0,
                "salience": salience,
                "last_seen": None
            }
        
        self.arc["themes"][theme]["occurrences"] += 1
        self.arc["themes"][theme]["last_seen"] = datetime.now().isoformat()
        
        # Boost salience for recurring themes
        current = self.arc["themes"][theme]["salience"]
        self.arc["themes"][theme]["salience"] = min(1.0, current + 0.05)
        
        self._save_arc()
    
    def get_significant_events(self, n: int = 5, min_salience: float = 0.5) -> List[Dict]:
        """Get most significant events for context injection."""
        events = [e for e in self.arc["events"] if e["salience"] >= min_salience]
        events.sort(key=lambda x: x["salience"], reverse=True)
        return events[:n]
    
    def get_arc_summary(self) -> str:
        """Generate a narrative summary of the relationship arc."""
        if not self.arc["events"]:
            return ""
        
        count = self.arc["interaction_count"]
        first = self.arc["first_interaction"]
        
        # Calculate relationship duration
        if first:
            try:
                start = datetime.fromisoformat(first)
                duration = datetime.now() - start
                duration_str = f"{duration.days} days" if duration.days > 0 else "today"
            except:
                duration_str = "some time"
        else:
            duration_str = "recently"
        
        # Get top themes
        top_themes = sorted(
            self.arc["themes"].items(),
            key=lambda x: x[1]["salience"],
            reverse=True
        )[:3]
        themes_str = ", ".join([t[0] for t in top_themes]) if top_themes else "various topics"
        
        # Get recent significant events
        recent_events = [e for e in self.arc["events"][-5:] if e["salience"] > 0.6]
        
        summary = f"We've been talking for {duration_str} ({count} conversations). "
        summary += f"We often discuss {themes_str}. "
        
        if recent_events:
            latest = recent_events[-1]
            summary += f"Recently: {latest['description']}."
        
        return summary
    
    def decay_event_salience(self) -> int:
        """
        Decay salience of old, unreferenced events.
        Called periodically to prevent arc bloat.
        """
        decayed = 0
        now = datetime.now()
        
        for event in self.arc["events"]:
            try:
                created = datetime.fromisoformat(event["timestamp"])
                age_days = (now - created).days
                
                # Events older than 30 days with low reference count decay
                if age_days > 30 and event["referenced_count"] < 2:
                    decay = 0.01 * (age_days - 30)
                    event["salience"] = max(0.1, event["salience"] - decay)
                    decayed += 1
            except:
                continue
        
        if decayed > 0:
            self._save_arc()
        
        return decayed


class RelationshipStageModel:
    """
    Models the current relationship stage and manages transitions.
    Stage affects communication style, formality, and intimacy of responses.
    
    Timing: Background (updated during reflection)
    Timescale: Long-term (stages evolve slowly)
    Inertia: Stage transitions require sustained interaction patterns
    """
    
    # Stage thresholds (interaction count, emotional depth score)
    STAGE_THRESHOLDS = {
        RelationshipStage.NEW: (0, 0.0),
        RelationshipStage.FAMILIAR: (10, 0.3),
        RelationshipStage.CLOSE: (50, 0.5),
        RelationshipStage.INTIMATE: (150, 0.7),
    }
    
    # Stage transition inertia (interactions needed to confirm transition)
    TRANSITION_INERTIA = 5
    
    def __init__(self, db_path: str = "./persistent_state"):
        self.db_path = db_path
        self.stage_path = f"{db_path}/relationship_stage.json"
        self.state = self._load_state()
    
    def _load_state(self) -> Dict:
        try:
            with open(self.stage_path, "r", encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {
                "current_stage": RelationshipStage.NEW.value,
                "interaction_count": 0,
                "emotional_depth_score": 0.0,
                "transition_progress": 0,
                "stage_history": [],
                "last_updated": None
            }
    
    def _save_state(self):
        self.state["last_updated"] = datetime.now().isoformat()
        with open(self.stage_path, "w", encoding='utf-8') as f:
            json.dump(self.state, f, indent=2)
    
    def get_current_stage(self) -> RelationshipStage:
        """Get current relationship stage."""
        return RelationshipStage(self.state["current_stage"])
    
    def update_metrics(
        self, 
        interaction_count: int,
        emotional_state: Dict,
        user_message: str,
        ai_response: str
    ) -> Optional[RelationshipStage]:
        """
        Update relationship metrics and check for stage transition.
        
        Returns:
            New stage if transition occurred, None otherwise
        """
        self.state["interaction_count"] = interaction_count
        
        # Compute emotional depth from interaction
        depth_signals = self._compute_emotional_depth(
            emotional_state, user_message, ai_response
        )
        
        # Exponential moving average for emotional depth
        alpha = 0.1
        self.state["emotional_depth_score"] = (
            alpha * depth_signals + 
            (1 - alpha) * self.state["emotional_depth_score"]
        )
        
        # Check for stage transition
        current = self.get_current_stage()
        potential_next = self._get_potential_stage(
            interaction_count, 
            self.state["emotional_depth_score"]
        )
        
        if potential_next != current:
            # Increment transition progress
            self.state["transition_progress"] += 1
            
            if self.state["transition_progress"] >= self.TRANSITION_INERTIA:
                # Transition confirmed
                self._transition_to(potential_next)
                return potential_next
        else:
            # Reset transition progress if conditions not met
            self.state["transition_progress"] = max(0, 
                self.state["transition_progress"] - 1
            )
        
        self._save_state()
        return None
    
    def _compute_emotional_depth(
        self, 
        emotional_state: Dict,
        user_message: str,
        ai_response: str
    ) -> float:
        """Compute emotional depth score for an interaction."""
        depth = 0.0
        
        # High warmth indicates deeper connection
        depth += emotional_state.get("warmth", 0.5) * 0.3
        
        # Engagement level
        depth += emotional_state.get("engagement", 0.5) * 0.2
        
        # Message length suggests investment
        user_words = len(user_message.split())
        if user_words > 50:
            depth += 0.2
        elif user_words > 20:
            depth += 0.1
        
        # Personal disclosure patterns
        personal_patterns = [
            r"\bi feel\b", r"\bi think\b", r"\bi believe\b",
            r"\bmy (life|family|friend|work)\b",
            r"\bhonestly\b", r"\bto be honest\b"
        ]
        import re
        for pattern in personal_patterns:
            if re.search(pattern, user_message.lower()):
                depth += 0.05
        
        return min(1.0, depth)
    
    def _get_potential_stage(
        self, 
        interaction_count: int, 
        emotional_depth: float
    ) -> RelationshipStage:
        """Determine which stage the relationship should be in."""
        # Work backwards from most advanced stage
        stages = [
            RelationshipStage.INTIMATE,
            RelationshipStage.CLOSE,
            RelationshipStage.FAMILIAR,
            RelationshipStage.NEW,
        ]
        
        for stage in stages:
            count_threshold, depth_threshold = self.STAGE_THRESHOLDS[stage]
            if interaction_count >= count_threshold and emotional_depth >= depth_threshold:
                return stage
        
        return RelationshipStage.NEW
    
    def _transition_to(self, new_stage: RelationshipStage):
        """Execute stage transition."""
        old_stage = self.state["current_stage"]
        self.state["current_stage"] = new_stage.value
        self.state["transition_progress"] = 0
        
        self.state["stage_history"].append({
            "from": old_stage,
            "to": new_stage.value,
            "timestamp": datetime.now().isoformat(),
            "interaction_count": self.state["interaction_count"]
        })
        
        logger.info(f"[RELATIONSHIP] Stage transition: {old_stage} → {new_stage.value}")
        self._save_state()
    
    def get_stage_modifiers(self) -> Dict:
        """
        Get response modifiers based on current relationship stage.
        Used to adjust system prompt and response style.
        """
        stage = self.get_current_stage()
        
        modifiers = {
            RelationshipStage.NEW: {
                "formality": 0.7,
                "personal_disclosure": 0.2,
                "familiarity": 0.2,
                "emotional_openness": 0.3,
                "style_note": "Be friendly but somewhat formal. Building initial trust."
            },
            RelationshipStage.FAMILIAR: {
                "formality": 0.4,
                "personal_disclosure": 0.5,
                "familiarity": 0.6,
                "emotional_openness": 0.5,
                "style_note": "Comfortable and natural. Reference shared history when relevant."
            },
            RelationshipStage.CLOSE: {
                "formality": 0.2,
                "personal_disclosure": 0.7,
                "familiarity": 0.8,
                "emotional_openness": 0.7,
                "style_note": "Personal and warm. Share thoughts openly. Use inside references."
            },
            RelationshipStage.INTIMATE: {
                "formality": 0.1,
                "personal_disclosure": 0.9,
                "familiarity": 0.95,
                "emotional_openness": 0.9,
                "style_note": "Deep connection. Be fully authentic and emotionally present."
            },
        }
        
        return modifiers.get(stage, modifiers[RelationshipStage.NEW])


class ResponseStyleLearner:
    """
    Learns user's preferred response style over time.
    Adapts length, depth, formality, and humor based on implicit feedback.
    
    Timing: Async (post-response)
    Timescale: Long-term (preferences evolve slowly)
    Decay: Preferences decay toward neutral over time without reinforcement
    """
    
    # Style dimensions to learn
    STYLE_DIMENSIONS = {
        "preferred_length": 0.5,      # 0=short, 1=long
        "preferred_depth": 0.5,       # 0=surface, 1=deep
        "preferred_formality": 0.5,   # 0=casual, 1=formal
        "humor_appreciation": 0.5,    # 0=serious, 1=playful
        "directness": 0.5,            # 0=soft, 1=direct
        "emotional_support": 0.5,     # 0=logical, 1=emotional
    }
    
    # Learning rate and decay
    LEARNING_RATE = 0.05
    DECAY_RATE = 0.001  # Decay per interaction toward baseline
    BASELINE = 0.5
    
    def __init__(self, db_path: str = "./persistent_state"):
        self.db_path = db_path
        self.prefs_path = f"{db_path}/response_style_prefs.json"
        self.preferences = self._load_preferences()
        self.feedback_history = deque(maxlen=100)
    
    def _load_preferences(self) -> Dict:
        try:
            with open(self.prefs_path, "r", encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {
                "dimensions": self.STYLE_DIMENSIONS.copy(),
                "confidence": {dim: 0.0 for dim in self.STYLE_DIMENSIONS},
                "last_updated": None
            }
    
    def _save_preferences(self):
        self.preferences["last_updated"] = datetime.now().isoformat()
        with open(self.prefs_path, "w", encoding='utf-8') as f:
            json.dump(self.preferences, f, indent=2)
    
    def infer_feedback(
        self, 
        user_message: str,
        ai_response: str,
        user_response_time_seconds: float = None,
        response_length: int = None
    ) -> Dict:
        """
        Infer implicit feedback about response style from user behavior.
        
        Signals:
        - Quick follow-up question = engaged (positive)
        - Very short response = disengaged or satisfied (neutral/negative)
        - Long response = engaged (positive)
        - Questions about the topic = interested (positive)
        - "Thanks" / acknowledgment = satisfied (positive)
        - Changing topic = disengaged (negative)
        """
        feedback = {}
        user_lower = user_message.lower()
        user_words = len(user_message.split())
        ai_words = len(ai_response.split())
        
        # Length preference inference
        if user_words > 50 and ai_words > 100:
            # User engaged with long response, likes depth
            feedback["preferred_length"] = 1.0
            feedback["preferred_depth"] = 0.8
        elif user_words < 10 and ai_words > 100:
            # Short response to long answer - might prefer brevity
            feedback["preferred_length"] = 0.3
        
        # Formality inference
        casual_markers = ["lol", "haha", "yeah", "nah", "gonna", "wanna", "ur", "btw"]
        formal_markers = ["please", "would you", "could you", "thank you", "appreciate"]
        
        casual_count = sum(1 for m in casual_markers if m in user_lower)
        formal_count = sum(1 for m in formal_markers if m in user_lower)
        
        if casual_count > formal_count:
            feedback["preferred_formality"] = 0.3
        elif formal_count > casual_count:
            feedback["preferred_formality"] = 0.7
        
        # Humor appreciation
        humor_responses = ["haha", "lol", "lmao", "😂", "🤣", "that's funny", "good one"]
        if any(h in user_lower for h in humor_responses):
            feedback["humor_appreciation"] = 0.9
        
        # Emotional support preference
        if any(w in user_lower for w in ["thank", "helps", "feel better", "appreciate"]):
            feedback["emotional_support"] = 0.8
        
        # Directness (if user asks for clarity)
        if any(p in user_lower for p in ["what do you mean", "can you explain", "i don't understand"]):
            feedback["directness"] = 0.8
        
        self.feedback_history.append({
            "timestamp": datetime.now().isoformat(),
            "feedback": feedback
        })
        
        return feedback
    
    def update_preferences(self, feedback: Dict):
        """Update style preferences based on inferred feedback."""
        for dimension, signal in feedback.items():
            if dimension in self.preferences["dimensions"]:
                current = self.preferences["dimensions"][dimension]
                
                # Move toward signal with learning rate
                delta = (signal - current) * self.LEARNING_RATE
                self.preferences["dimensions"][dimension] = max(0, min(1, current + delta))
                
                # Increase confidence
                self.preferences["confidence"][dimension] = min(1.0,
                    self.preferences["confidence"][dimension] + 0.02
                )
        
        self._save_preferences()
    
    def apply_decay(self):
        """Decay preferences toward baseline over time."""
        for dimension in self.preferences["dimensions"]:
            current = self.preferences["dimensions"][dimension]
            
            # Decay toward baseline
            if current > self.BASELINE:
                self.preferences["dimensions"][dimension] = max(
                    self.BASELINE, current - self.DECAY_RATE
                )
            elif current < self.BASELINE:
                self.preferences["dimensions"][dimension] = min(
                    self.BASELINE, current + self.DECAY_RATE
                )
            
            # Decay confidence
            self.preferences["confidence"][dimension] = max(0,
                self.preferences["confidence"][dimension] - 0.005
            )
        
        self._save_preferences()
    
    def get_style_modifiers(self) -> Dict:
        """
        Get response style modifiers based on learned preferences.
        Returns values only for dimensions with sufficient confidence.
        """
        modifiers = {}
        confidence_threshold = 0.3
        
        for dimension, value in self.preferences["dimensions"].items():
            confidence = self.preferences["confidence"][dimension]
            if confidence >= confidence_threshold:
                modifiers[dimension] = {
                    "value": value,
                    "confidence": confidence
                }
        
        return modifiers
    
    def get_style_prompt_additions(self) -> str:
        """Generate system prompt additions based on learned style."""
        modifiers = self.get_style_modifiers()
        if not modifiers:
            return ""
        
        additions = []
        
        if "preferred_length" in modifiers:
            v = modifiers["preferred_length"]["value"]
            if v > 0.7:
                additions.append("The user appreciates detailed, thorough responses.")
            elif v < 0.3:
                additions.append("The user prefers concise, to-the-point responses.")
        
        if "humor_appreciation" in modifiers:
            v = modifiers["humor_appreciation"]["value"]
            if v > 0.7:
                additions.append("The user enjoys light humor and playfulness.")
            elif v < 0.3:
                additions.append("Keep responses more serious and straightforward.")
        
        if "preferred_formality" in modifiers:
            v = modifiers["preferred_formality"]["value"]
            if v > 0.7:
                additions.append("Maintain a professional, polished tone.")
            elif v < 0.3:
                additions.append("Be casual and relaxed in your communication style.")
        
        if "emotional_support" in modifiers:
            v = modifiers["emotional_support"]["value"]
            if v > 0.7:
                additions.append("Prioritize emotional warmth and supportive language.")
        
        return " ".join(additions)


# =============================================================================
# Unified Relationship Model Manager
# =============================================================================

class RelationshipModel:
    """
    Unified manager for relationship modeling components.
    Provides clean interface for main application.
    """
    
    def __init__(self, db_path: str = "./persistent_state"):
        self.arc_tracker = ConversationArcTracker(db_path)
        self.stage_model = RelationshipStageModel(db_path)
        self.style_learner = ResponseStyleLearner(db_path)
        
        logger.info("[RELATIONSHIP_MODEL] All components initialized")
    
    def on_interaction(
        self,
        user_message: str,
        ai_response: str,
        emotional_state: Dict
    ) -> Dict:
        """
        Process an interaction through all relationship components.
        Called after each interaction in background.
        
        Returns:
            Relationship insights and any stage transitions
        """
        # Record interaction in arc
        interaction_count = self.arc_tracker.record_interaction()
        
        # Update stage model
        stage_transition = self.stage_model.update_metrics(
            interaction_count,
            emotional_state,
            user_message,
            ai_response
        )
        
        # Infer and update style preferences
        feedback = self.style_learner.infer_feedback(user_message, ai_response)
        self.style_learner.update_preferences(feedback)
        
        return {
            "interaction_count": interaction_count,
            "current_stage": self.stage_model.get_current_stage().value,
            "stage_transition": stage_transition.value if stage_transition else None,
            "style_feedback": feedback
        }
    
    def add_arc_event(
        self, 
        event_type: str, 
        description: str,
        salience: float = 0.5,
        context: str = ""
    ):
        """Add a significant event to the conversation arc."""
        self.arc_tracker.add_event(event_type, description, salience, context)
    
    def track_theme(self, theme: str, salience: float = 0.5):
        """Track a recurring theme."""
        self.arc_tracker.track_theme(theme, salience)
    
    def get_context_for_prompt(self) -> Dict:
        """
        Get relationship context for system prompt injection.
        """
        stage_modifiers = self.stage_model.get_stage_modifiers()
        style_additions = self.style_learner.get_style_prompt_additions()
        arc_summary = self.arc_tracker.get_arc_summary()
        significant_events = self.arc_tracker.get_significant_events(n=3)
        
        return {
            "stage": self.stage_model.get_current_stage().value,
            "stage_modifiers": stage_modifiers,
            "style_additions": style_additions,
            "arc_summary": arc_summary,
            "significant_events": [e["description"] for e in significant_events]
        }
    
    def apply_decay(self):
        """Apply decay to all relationship components."""
        self.arc_tracker.decay_event_salience()
        self.style_learner.apply_decay()
    
    def get_status(self) -> Dict:
        """Get status of relationship model."""
        return {
            "interaction_count": self.arc_tracker.arc["interaction_count"],
            "current_stage": self.stage_model.get_current_stage().value,
            "themes_tracked": len(self.arc_tracker.arc["themes"]),
            "events_recorded": len(self.arc_tracker.arc["events"]),
            "style_preferences": self.style_learner.get_style_modifiers()
        }

    def get_current_stage(self) -> RelationshipStage:
        """Get current relationship stage (delegation to stage_model)."""
        return self.stage_model.get_current_stage()
