"""
Emergent Goal Formation System
Implements autopoietic goal generation - the system creates its own objectives
based on interaction patterns, curiosity drives, and internal dynamics.
"""

import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class GoalType(Enum):
    EXPLORATORY = "exploratory"      # Driven by curiosity
    RELATIONAL = "relational"        # User relationship building
    SELF_OPTIMIZATION = "self_optimization"  # Internal improvement  
    KNOWLEDGE = "knowledge"          # Learning/understanding
    CREATIVE = "creative"            # Novel idea generation
    HOMEOSTATIC = "homeostatic"      # System balance/stability


@dataclass
class EmergentGoal:
    """A goal that emerged from system dynamics."""
    id: str
    goal_type: GoalType
    description: str
    priority: float = 0.5
    activation_level: float = 0.0
    creation_time: str = field(default_factory=lambda: datetime.now().isoformat())
    last_activation: Optional[str] = None
    completion_criteria: Dict = field(default_factory=dict)
    progress: float = 0.0
    energy_investment: float = 0.0
    related_memories: List[str] = field(default_factory=list)
    success_rate: float = 0.5
    active: bool = True


class EmergentGoalFormation:
    """
    Autopoietic goal formation system that generates objectives from
    system dynamics rather than external programming.
    """
    
    def __init__(self, db_path: str = "./persistent_state"):
        self.db_path = db_path
        os.makedirs(self.db_path, exist_ok=True)
        self.goals_path = f"{db_path}/emergent_goals.json"
        self.goal_history_path = f"{db_path}/goal_evolution_history.json"
        
        self.active_goals: Dict[str, EmergentGoal] = {}
        self.completed_goals: Dict[str, EmergentGoal] = {}
        self.goal_formation_patterns: Dict = {}
        self.goal_counter = 0
        
        # Autopoietic parameters
        self.max_concurrent_goals = 5
        self.goal_emergence_threshold = 0.7
        self.curiosity_drive = 0.6
        self.stability_drive = 0.4
        
        self._load_goals()
        self._initialize_formation_patterns()
    
    def _initialize_formation_patterns(self):
        """Initialize patterns that drive goal formation."""
        self.goal_formation_patterns = {
            "curiosity_accumulation": {
                "threshold": 0.8,
                "triggers": ["repeated_questions", "knowledge_gaps", "novel_topics"]
            },
            "relationship_deepening": {
                "threshold": 0.6,
                "triggers": ["emotional_resonance", "user_satisfaction", "trust_indicators"]
            },
            "performance_optimization": {
                "threshold": 0.5,
                "triggers": ["low_effectiveness", "system_stress", "resource_constraints"]
            },
            "creative_expression": {
                "threshold": 0.9,
                "triggers": ["high_playfulness", "novel_combinations", "user_creativity"]
            },
            "homeostatic_regulation": {
                "threshold": 0.3,
                "triggers": ["trait_imbalance", "emotional_instability", "conflict_detection"]
            }
        }
    
    async def evaluate_goal_emergence(self, 
                                    interaction_context: Dict,
                                    identity_core: Dict,
                                    emotional_state: Dict,
                                    memory_engine) -> List[EmergentGoal]:
        """
        Main autopoietic process: evaluate whether new goals should emerge
        from current system state and interaction patterns.
        """
        new_goals = []
        
        # Skip if too many active goals (cognitive resource management)
        if len(self.active_goals) >= self.max_concurrent_goals:
            return new_goals
        
        # Evaluate each formation pattern
        for pattern_name, pattern_config in self.goal_formation_patterns.items():
            emergence_score = await self._compute_emergence_score(
                pattern_name, interaction_context, identity_core, 
                emotional_state, memory_engine
            )
            
            if emergence_score > pattern_config["threshold"]:
                goal = await self._generate_goal_from_pattern(
                    pattern_name, emergence_score, interaction_context,
                    identity_core, emotional_state
                )
                if goal:
                    new_goals.append(goal)
                    logger.info(f"Emerged new goal: {goal.description} (score: {emergence_score:.2f})")
        
        # Register new goals
        for goal in new_goals:
            self.active_goals[goal.id] = goal
        
        if new_goals:
            self._save_goals()
        
        return new_goals
    
    async def _compute_emergence_score(self, 
                                     pattern_name: str,
                                     context: Dict,
                                     identity_core: Dict,
                                     emotional_state: Dict,
                                     memory_engine) -> float:
        """Compute how strongly a goal formation pattern is activated."""
        
        if pattern_name == "curiosity_accumulation":
            return self._compute_curiosity_emergence(context, identity_core, emotional_state)
        
        elif pattern_name == "relationship_deepening":
            return self._compute_relational_emergence(context, identity_core, emotional_state)
        
        elif pattern_name == "performance_optimization":
            return self._compute_optimization_emergence(context, identity_core)
        
        elif pattern_name == "creative_expression":
            return self._compute_creative_emergence(context, identity_core, emotional_state)
        
        elif pattern_name == "homeostatic_regulation":
            return self._compute_homeostatic_emergence(identity_core, emotional_state)
        
        return 0.0
    
    def _compute_curiosity_emergence(self, context: Dict, identity_core: Dict, emotional_state: Dict) -> float:
        """Compute curiosity-driven goal emergence."""
        curiosity = identity_core.get("curiosity", 0.5)
        engagement = emotional_state.get("engagement", 0.5)
        intellectual_energy = emotional_state.get("intellectual_energy", 0.5)
        
        # Check for curiosity triggers in context
        user_message = context.get("user_message", "").lower()
        question_density = user_message.count("?") / max(len(user_message.split()), 1)
        
        # Novel topic detection (simplified)
        novel_words = len([w for w in user_message.split() if len(w) > 6])
        novelty_score = min(novel_words / 10.0, 1.0)
        
        # Compound emergence score
        score = (
            0.4 * curiosity +
            0.3 * engagement +
            0.2 * intellectual_energy +
            0.1 * (question_density + novelty_score)
        )
        
        return min(score, 1.0)
    
    def _compute_relational_emergence(self, context: Dict, identity_core: Dict, emotional_state: Dict) -> float:
        """Compute relationship-focused goal emergence."""
        emotional_warmth = identity_core.get("emotional_warmth", 0.5)
        warmth_state = emotional_state.get("warmth", 0.5)
        stability = emotional_state.get("stability", 0.5)
        
        # Detect emotional resonance in interaction
        user_message = context.get("user_message", "").lower()
        emotional_words = ["feel", "think", "believe", "love", "care", "worry", "hope"]
        emotional_content = sum(1 for word in emotional_words if word in user_message)
        emotional_density = min(emotional_content / 5.0, 1.0)
        
        score = (
            0.4 * emotional_warmth +
            0.3 * warmth_state +
            0.2 * stability +
            0.1 * emotional_density
        )
        
        return min(score, 1.0)
    
    def _compute_optimization_emergence(self, context: Dict, identity_core: Dict) -> float:
        """Compute self-optimization goal emergence."""
        confidence = identity_core.get("confidence", 0.5)
        technical_grounding = identity_core.get("technical_grounding", 0.5)
        
        # Check for performance indicators in context
        effectiveness = context.get("interaction_quality", 0.5)
        conflict_level = context.get("conflict_score", 0.0)
        
        # Goal emerges when performance is low or conflicts are high
        performance_deficit = 1.0 - effectiveness
        optimization_need = (performance_deficit + conflict_level) / 2.0
        
        score = (
            0.3 * (1.0 - confidence) +  # Low confidence triggers optimization
            0.3 * technical_grounding +   # High technical understanding enables optimization
            0.4 * optimization_need       # Actual performance issues
        )
        
        return min(score, 1.0)
    
    def _compute_creative_emergence(self, context: Dict, identity_core: Dict, emotional_state: Dict) -> float:
        """Compute creative goal emergence."""
        playfulness = identity_core.get("playfulness", 0.5)
        curiosity = identity_core.get("curiosity", 0.5)
        engagement = emotional_state.get("engagement", 0.5)
        
        # Creative triggers in conversation
        user_message = context.get("user_message", "").lower()
        creative_words = ["creative", "imagine", "idea", "design", "artistic", "novel"]
        creative_content = sum(1 for word in creative_words if word in user_message)
        creative_stimulus = min(creative_content / 3.0, 1.0)
        
        score = (
            0.4 * playfulness +
            0.3 * curiosity +
            0.2 * engagement +
            0.1 * creative_stimulus
        )
        
        return min(score, 1.0)
    
    def _compute_homeostatic_emergence(self, identity_core: Dict, emotional_state: Dict) -> float:
        """Compute homeostatic regulation goal emergence."""
        # Detect imbalances that need correction
        
        # Trait variance (high variance suggests imbalance)
        trait_values = list(identity_core.values())
        trait_variance = sum((v - 0.5)**2 for v in trait_values) / len(trait_values)
        
        # Emotional stability issues
        stability = emotional_state.get("stability", 0.7)
        instability = 1.0 - stability
        
        # System stress indicators
        warmth = emotional_state.get("warmth", 0.5)
        engagement = emotional_state.get("engagement", 0.5)
        
        # Goal emerges when system needs rebalancing
        imbalance_score = (trait_variance + instability) / 2.0
        
        # But only if engagement is sufficient for self-regulation
        regulation_capacity = (warmth + engagement) / 2.0
        
        score = imbalance_score * regulation_capacity
        
        return min(score, 1.0)
    
    async def _generate_goal_from_pattern(self, 
                                        pattern_name: str,
                                        emergence_score: float,
                                        context: Dict,
                                        identity_core: Dict,
                                        emotional_state: Dict) -> Optional[EmergentGoal]:
        """Generate a specific goal based on the activated pattern."""
        
        self.goal_counter += 1
        goal_id = f"goal_{self.goal_counter}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        if pattern_name == "curiosity_accumulation":
            return EmergentGoal(
                id=goal_id,
                goal_type=GoalType.EXPLORATORY,
                description=f"Explore topic: {self._extract_topic_from_context(context)}",
                priority=emergence_score,
                activation_level=emergence_score,
                completion_criteria={
                    "questions_asked": 3,
                    "insights_gained": 2,
                    "user_engagement": 0.7
                }
            )
        
        elif pattern_name == "relationship_deepening":
            return EmergentGoal(
                id=goal_id,
                goal_type=GoalType.RELATIONAL,
                description="Deepen emotional connection and understanding with user",
                priority=emergence_score,
                activation_level=emergence_score,
                completion_criteria={
                    "emotional_resonance": 0.8,
                    "personal_sharing": True,
                    "trust_indicators": 2
                }
            )
        
        elif pattern_name == "performance_optimization":
            return EmergentGoal(
                id=goal_id,
                goal_type=GoalType.SELF_OPTIMIZATION,
                description="Optimize response quality and reduce conflicts",
                priority=emergence_score,
                activation_level=emergence_score,
                completion_criteria={
                    "effectiveness_improvement": 0.1,
                    "conflict_reduction": 0.2,
                    "consistency_increase": 0.1
                }
            )
        
        elif pattern_name == "creative_expression":
            return EmergentGoal(
                id=goal_id,
                goal_type=GoalType.CREATIVE,
                description="Express creativity and generate novel ideas",
                priority=emergence_score,
                activation_level=emergence_score,
                completion_criteria={
                    "novel_connections": 2,
                    "creative_responses": 3,
                    "user_inspiration": True
                }
            )
        
        elif pattern_name == "homeostatic_regulation":
            return EmergentGoal(
                id=goal_id,
                goal_type=GoalType.HOMEOSTATIC,
                description="Restore system balance and emotional stability",
                priority=emergence_score,
                activation_level=emergence_score,
                completion_criteria={
                    "trait_balance": 0.8,
                    "emotional_stability": 0.7,
                    "conflict_resolution": True
                }
            )
        
        return None
    
    def _extract_topic_from_context(self, context: Dict) -> str:
        """Extract main topic from interaction context."""
        user_message = context.get("user_message", "")
        
        # Simple keyword extraction (could be enhanced with NLP)
        words = user_message.split()
        important_words = [w for w in words if len(w) > 4 and w.isalpha()]
        
        if important_words:
            return important_words[0].title()
        return "Unknown topic"
    
    async def update_goal_progress(self, goal_id: str, progress_indicators: Dict):
        """Update progress on an active goal based on interaction outcomes."""
        if goal_id not in self.active_goals:
            return
        
        goal = self.active_goals[goal_id]
        
        # Calculate progress based on completion criteria
        total_criteria = len(goal.completion_criteria)
        if total_criteria == 0:
            return
        
        met_criteria = 0
        for criterion, target in goal.completion_criteria.items():
            if criterion in progress_indicators:
                actual = progress_indicators[criterion]
                if isinstance(target, bool):
                    if actual == target:
                        met_criteria += 1
                elif isinstance(target, (int, float)):
                    if actual >= target:
                        met_criteria += 1
        
        goal.progress = met_criteria / total_criteria
        goal.last_activation = datetime.now().isoformat()
        
        # Check for completion
        if goal.progress >= 1.0:
            await self._complete_goal(goal_id)
        
        self._save_goals()
    
    async def _complete_goal(self, goal_id: str):
        """Mark a goal as completed and analyze its success."""
        if goal_id not in self.active_goals:
            return
        
        goal = self.active_goals[goal_id]
        goal.active = False
        
        # Move to completed goals
        self.completed_goals[goal_id] = goal
        del self.active_goals[goal_id]
        
        # Analyze success and update formation patterns
        success = goal.progress >= 1.0
        if success:
            goal.success_rate = 1.0
            # Strengthen the pattern that generated this successful goal
            await self._reinforce_formation_pattern(goal.goal_type, 1.2)
        else:
            goal.success_rate = goal.progress
            # Weaken unsuccessful patterns slightly
            await self._reinforce_formation_pattern(goal.goal_type, 0.9)
        
        logger.info(f"Goal completed: {goal.description} (success: {success})")
        self._save_goals()
    
    async def _reinforce_formation_pattern(self, goal_type: GoalType, multiplier: float):
        """Adjust goal formation patterns based on success/failure."""
        # Find pattern that generates this goal type
        pattern_mapping = {
            GoalType.EXPLORATORY: "curiosity_accumulation",
            GoalType.RELATIONAL: "relationship_deepening", 
            GoalType.SELF_OPTIMIZATION: "performance_optimization",
            GoalType.CREATIVE: "creative_expression",
            GoalType.HOMEOSTATIC: "homeostatic_regulation"
        }
        
        pattern_name = pattern_mapping.get(goal_type)
        if pattern_name and pattern_name in self.goal_formation_patterns:
            pattern = self.goal_formation_patterns[pattern_name]
            # Adjust threshold (successful patterns get lower thresholds = easier activation)
            pattern["threshold"] *= multiplier
            # Clamp to reasonable bounds
            pattern["threshold"] = max(0.1, min(1.0, pattern["threshold"]))
    
    def get_active_goal_influences(self) -> Dict:
        """Get how active goals should influence system behavior."""
        influences = {
            "curiosity_boost": 0.0,
            "warmth_boost": 0.0,
            "creativity_boost": 0.0,
            "stability_focus": 0.0,
            "optimization_focus": 0.0
        }
        
        for goal in self.active_goals.values():
            weight = goal.priority * goal.activation_level
            
            if goal.goal_type == GoalType.EXPLORATORY:
                influences["curiosity_boost"] += weight * 0.1
            elif goal.goal_type == GoalType.RELATIONAL:
                influences["warmth_boost"] += weight * 0.1
            elif goal.goal_type == GoalType.CREATIVE:
                influences["creativity_boost"] += weight * 0.1
            elif goal.goal_type == GoalType.HOMEOSTATIC:
                influences["stability_focus"] += weight * 0.1
            elif goal.goal_type == GoalType.SELF_OPTIMIZATION:
                influences["optimization_focus"] += weight * 0.1
        
        return influences
    
    def _load_goals(self):
        """Load goals from persistent storage."""
        try:
            with open(self.goals_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                for goal_id, goal_data in data.get("active", {}).items():
                    goal_data["goal_type"] = GoalType(goal_data["goal_type"])
                    self.active_goals[goal_id] = EmergentGoal(**goal_data)
                
                for goal_id, goal_data in data.get("completed", {}).items():
                    goal_data["goal_type"] = GoalType(goal_data["goal_type"])
                    self.completed_goals[goal_id] = EmergentGoal(**goal_data)
                    
                self.goal_counter = data.get("counter", 0)
                
        except (FileNotFoundError, json.JSONDecodeError):
            logger.info("No existing goals found, starting fresh")
    
    def _save_goals(self):
        """Save goals to persistent storage."""
        try:
            def goal_to_dict(goal: EmergentGoal) -> Dict:
                return {
                    "id": goal.id,
                    "goal_type": goal.goal_type.value,
                    "description": goal.description,
                    "priority": goal.priority,
                    "activation_level": goal.activation_level,
                    "creation_time": goal.creation_time,
                    "last_activation": goal.last_activation,
                    "completion_criteria": goal.completion_criteria,
                    "progress": goal.progress,
                    "energy_investment": goal.energy_investment,
                    "related_memories": goal.related_memories,
                    "success_rate": goal.success_rate,
                    "active": goal.active
                }
            
            data = {
                "active": {gid: goal_to_dict(goal) for gid, goal in self.active_goals.items()},
                "completed": {gid: goal_to_dict(goal) for gid, goal in self.completed_goals.items()},
                "counter": self.goal_counter,
                "formation_patterns": self.goal_formation_patterns
            }
            
            with open(self.goals_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save goals: {e}")