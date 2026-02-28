"""
Autopoietic Framework Integration Guide
Shows how to integrate all autopoietic enhancements into The Yuki Project system.
"""

import logging
import os
from typing import Dict
from datetime import datetime

from cognition.architectural_plasticity import ArchitecturalPlasticityEngine
from cognition.emergent_goals import EmergentGoalFormation
from cognition.recursive_reflection import RecursiveMetaReflection
from cognition.meta_learning import MetaLearningEngine

logger = logging.getLogger(__name__)


class AutopoieticEnhancementLayer:
    """
    Integration layer that orchestrates all autopoietic enhancements.
    This layer sits above the existing cognitive architecture and enhances it
    with self-modification, emergent goals, recursive reflection, and meta-learning.
    """
    
    def __init__(self, db_path: str = "./persistent_state", enactive_nexus=None):
        self.db_path = db_path
        os.makedirs(self.db_path, exist_ok=True)
        self.enactive_nexus = enactive_nexus
        
        # Initialize autopoietic subsystems
        self.architectural_plasticity = ArchitecturalPlasticityEngine(db_path)
        self.goal_formation = EmergentGoalFormation(db_path)
        self.recursive_reflection = RecursiveMetaReflection(db_path)
        self.meta_learning = MetaLearningEngine(db_path)
        
        # Integration state
        self.autopoietic_cycles = 0
        self.last_full_cycle = None
        self.enhancement_active = True
        
        logger.info("Autopoietic enhancement layer initialized")
    
    async def process_interaction_autopoietically(self,
                                                user_message: str,
                                                ai_response: str,
                                                interaction_context: Dict,
                                                identity_core: Dict,
                                                emotional_state: Dict,
                                                memory_engine,
                                                llm_client) -> Dict:
        """
        Main autopoietic processing loop that enhances every interaction
        with self-modifying, goal-forming, and meta-learning capabilities.
        """
        
        if not self.enhancement_active:
            return {"status": "disabled"}
        
        autopoietic_results = {
            "architectural_changes": {},
            "emergent_goals": [],
            "meta_reflections": {},
            "learning_optimizations": {},
            "enactive_proposals_applied": 0,
            "cycle_number": self.autopoietic_cycles
        }
        
        try:
            # 1. EMERGENT GOAL EVALUATION
            # Check if new goals should emerge from this interaction
            new_goals = await self.goal_formation.evaluate_goal_emergence(
                interaction_context=interaction_context,
                identity_core=identity_core,
                emotional_state=emotional_state,
                memory_engine=memory_engine
            )
            
            autopoietic_results["emergent_goals"] = [
                {"id": goal.id, "description": goal.description, "type": goal.goal_type.value}
                for goal in new_goals
            ]
            
            # Update goal progress based on interaction outcomes and wire
            # the goal-influence boosts to small trait nudges (audit I-12:
            # previously goal_influences was computed but silently discarded).
            goal_influences = self.goal_formation.get_active_goal_influences()

            boost_to_trait = {
                "curiosity_boost": "curiosity",
                "warmth_boost":    "emotional_warmth",
                "creativity_boost": "playfulness",
            }
            goal_trait_deltas = {
                trait: goal_influences[boost]
                for boost, trait in boost_to_trait.items()
                if abs(goal_influences.get(boost, 0.0)) > 1e-4
            }
            if goal_trait_deltas:
                await memory_engine.apply_reflection_update(
                    {"trait_deltas": goal_trait_deltas},
                    confidence_threshold=0.5,
                    smoothing=0.3,   # dampen goal nudges more than reflection deltas
                )
            
            # 2. ARCHITECTURAL PLASTICITY EVALUATION
            # Evaluate if cognitive architecture should be modified
            interaction_quality = interaction_context.get("interaction_quality", 0.7)

            if self.enactive_nexus is not None:
                try:
                    proposals = self.enactive_nexus.consume_self_modification_proposals(max_items=2)
                    for proposal in proposals:
                        await memory_engine.apply_reflection_update(
                            {
                                "trait_deltas": proposal.get("trait_deltas", {}),
                                "emotional_deltas": proposal.get("emotional_deltas", {}),
                                "self_model_deltas": {},
                                "confidence": proposal.get("confidence", 0.6),
                                "user_fact": "",
                                "ai_self_update": "",
                            },
                            confidence_threshold=0.45,
                            smoothing=0.25,
                        )
                    autopoietic_results["enactive_proposals_applied"] = len(proposals)
                except Exception as e:
                    logger.debug(f"Enactive proposal sync skipped: {e}")
            
            effectiveness_scores = {}
            for pattern_name in ["response_generation", "memory_processing", "trait_adaptation"]:
                # This would evaluate pattern effectiveness in the actual system
                effectiveness = await self._evaluate_pattern_effectiveness(
                    pattern_name, interaction_quality, identity_core
                )
                effectiveness_scores[pattern_name] = effectiveness
                
                await self.architectural_plasticity.evaluate_pattern_effectiveness(
                    pattern_name, effectiveness
                )
            
            autopoietic_results["architectural_changes"] = {
                "evaluated_patterns": effectiveness_scores,
                "suggestions": self.architectural_plasticity.suggest_architecture_changes()
            }
            
            # 3. RECURSIVE META-REFLECTION
            # Perform meta-reflection on primary reflection if it occurred
            primary_reflection = interaction_context.get("primary_reflection")
            if primary_reflection and self.autopoietic_cycles % 3 == 0:  # Every 3rd cycle
                
                meta_trace = await self.recursive_reflection.initiate_meta_reflection(
                    primary_reflection=primary_reflection,
                    reflection_context=interaction_context,
                    llm_client=llm_client
                )
                
                autopoietic_results["meta_reflections"] = {
                    "trace_id": meta_trace.id,
                    "effectiveness": meta_trace.effectiveness_score,
                    "depth": meta_trace.depth,
                    "insights_generated": len(meta_trace.content.get("meta_insights", []))
                }
            
            # 4. META-LEARNING OPTIMIZATION
            # Optimize learning processes based on accumulated performance data
            if self.autopoietic_cycles % 5 == 0:  # Every 5th cycle
                
                current_performance = await self._compute_current_performance(
                    interaction_context, identity_core, emotional_state
                )
                
                optimization_results = await self.meta_learning.optimize_learning_process(
                    current_performance=current_performance,
                    interaction_context=interaction_context,
                    memory_engine=memory_engine
                )
                
                autopoietic_results["learning_optimizations"] = optimization_results
            
            # 5. APPLY GOAL INFLUENCES TO SYSTEM STATE
            # Let active goals influence system behavior
            if goal_influences:
                await self._apply_goal_influences(goal_influences, identity_core, emotional_state)
            
            # 6. CROSS-SYSTEM INTEGRATION
            # Integrate insights across all autopoietic subsystems
            integration_insights = await self._perform_cross_system_integration()
            autopoietic_results["integration_insights"] = integration_insights
            
            self.autopoietic_cycles += 1
            self.last_full_cycle = datetime.now().isoformat()
            
            logger.info(f"Autopoietic cycle {self.autopoietic_cycles} completed")
            
        except Exception as e:
            logger.error(f"Autopoietic processing failed: {e}")
            autopoietic_results["error"] = str(e)
        
        return autopoietic_results
    
    async def _evaluate_pattern_effectiveness(self,
                                           pattern_name: str,
                                           interaction_quality: float,
                                           identity_core: Dict) -> float:
        """Evaluate effectiveness of a cognitive pattern."""
        
        # This would integrate with actual system metrics in real implementation
        base_effectiveness = interaction_quality
        
        # Adjust based on pattern type and current system state
        if pattern_name == "response_generation":
            confidence = identity_core.get("confidence", 0.5)
            emotional_warmth = identity_core.get("emotional_warmth", 0.5)
            effectiveness = base_effectiveness * (confidence + emotional_warmth) / 2.0
            
        elif pattern_name == "memory_processing":
            analytical_depth = identity_core.get("analytical_depth", 0.5)
            technical_grounding = identity_core.get("technical_grounding", 0.5)
            effectiveness = base_effectiveness * (analytical_depth + technical_grounding) / 2.0
            
        elif pattern_name == "trait_adaptation":
            curiosity = identity_core.get("curiosity", 0.5)
            playfulness = identity_core.get("playfulness", 0.5)
            effectiveness = base_effectiveness * (curiosity + playfulness) / 2.0
            
        else:
            effectiveness = base_effectiveness
        
        return min(1.0, max(0.0, effectiveness))
    
    async def _compute_current_performance(self,
                                         interaction_context: Dict,
                                         identity_core: Dict,
                                         emotional_state: Dict) -> Dict:
        """Compute current system performance metrics for meta-learning."""
        
        return {
            "overall_quality": interaction_context.get("interaction_quality", 0.7),
            "user_satisfaction": interaction_context.get("user_satisfaction", 0.6),
            "insights_per_session": interaction_context.get("insights_generated", 1),
            "adaptation_speed": self._compute_adaptation_speed(identity_core),
            "pattern_discovery_rate": self._compute_discovery_rate(),
            "meta_learning_effectiveness": self._compute_meta_learning_effectiveness()
        }
    
    def _compute_adaptation_speed(self, identity_core: Dict) -> float:
        """Compute how quickly the system adapts to new information."""
        # Simple heuristic based on trait variance and change rates
        trait_variance = sum((v - 0.5) ** 2 for v in identity_core.values()) / len(identity_core)
        return min(1.0, trait_variance * 2)  # Higher variance suggests active adaptation
    
    def _compute_discovery_rate(self) -> float:
        """Compute rate of pattern discovery across subsystems."""
        total_patterns = (
            len(self.architectural_plasticity.processing_patterns) +
            len(self.meta_learning.learning_patterns) +
            len(self.goal_formation.goal_formation_patterns)
        )
        
        # Normalize by cycles (discovery rate per cycle)
        if self.autopoietic_cycles == 0:
            return 0.5
        
        discovery_rate = total_patterns / self.autopoietic_cycles
        return min(1.0, discovery_rate)
    
    def _compute_meta_learning_effectiveness(self) -> float:
        """Compute meta-learning effectiveness."""
        summary = self.meta_learning.get_learning_optimization_summary()
        return summary.get("current_effectiveness", 0.5)
    
    async def _apply_goal_influences(self,
                                   influences: Dict,
                                   identity_core: Dict,
                                   emotional_state: Dict):
        """Apply active goal influences to system state."""
        
        # Apply trait boosts from active goals
        if influences.get("curiosity_boost", 0) > 0:
            current = identity_core.get("curiosity", 0.5)
            identity_core["curiosity"] = min(1.0, current + influences["curiosity_boost"])
        
        if influences.get("warmth_boost", 0) > 0:
            current = emotional_state.get("warmth", 0.5)
            emotional_state["warmth"] = min(1.0, current + influences["warmth_boost"])
        
        if influences.get("creativity_boost", 0) > 0:
            current = identity_core.get("playfulness", 0.5)
            identity_core["playfulness"] = min(1.0, current + influences["creativity_boost"])
        
        if influences.get("stability_focus", 0) > 0:
            current = emotional_state.get("stability", 0.5)
            emotional_state["stability"] = min(1.0, current + influences["stability_focus"])
    
    async def _perform_cross_system_integration(self) -> Dict:
        """Integrate insights across all autopoietic subsystems."""
        
        integration_insights = {}
        
        # 1. Architectural patterns → Meta-learning
        arch_suggestions = self.architectural_plasticity.suggest_architecture_changes()
        if arch_suggestions["underperforming_patterns"]:
            # Inform meta-learning about architectural performance issues
            integration_insights["arch_to_metalearning"] = {
                "underperforming_patterns": len(arch_suggestions["underperforming_patterns"]),
                "suggested_experiments": ["architectural_optimization"]
            }
        
        # 2. Goal formation → Architectural plasticity
        active_goals = len(self.goal_formation.active_goals)
        if active_goals > 0:
            # Active goals might require new cognitive patterns
            integration_insights["goals_to_arch"] = {
                "goals_requiring_new_patterns": active_goals,
                "pattern_suggestions": ["goal_execution", "priority_management"]
            }
        
        # 3. Meta-reflection → Goal formation
        reflection_summary = self.recursive_reflection.get_reflection_evolution_summary()
        if reflection_summary.get("improvement_trend", 0) > 0.1:
            # Improving reflection suggests exploration goals might be valuable
            integration_insights["reflection_to_goals"] = {
                "exploration_goal_boost": 0.1,
                "reason": "reflection_improvement_detected"
            }
        
        # 4. Meta-learning → All subsystems
        learning_summary = self.meta_learning.get_learning_optimization_summary()
        if learning_summary.get("current_effectiveness", 0.5) > 0.8:
            # High learning effectiveness enables more aggressive adaptation
            integration_insights["metalearning_to_all"] = {
                "adaptation_acceleration": 1.2,
                "exploration_encouragement": True
            }
        
        return integration_insights
    
    def get_autopoietic_status(self) -> Dict:
        """Get comprehensive status of all autopoietic subsystems."""
        
        return {
            "cycles_completed": self.autopoietic_cycles,
            "last_cycle": self.last_full_cycle,
            "enhancement_active": self.enhancement_active,
            "enactive_nexus": self.enactive_nexus.get_telemetry() if self.enactive_nexus else {},
            "architectural_plasticity": {
                "active_patterns": len(self.architectural_plasticity.get_active_patterns()),
                "average_effectiveness": self.architectural_plasticity._compute_average_effectiveness()
            },
            "goal_formation": {
                "active_goals": len(self.goal_formation.active_goals),
                "completed_goals": len(self.goal_formation.completed_goals),
                "current_drives": self.goal_formation.get_active_goal_influences()
            },
            "recursive_reflection": self.recursive_reflection.get_reflection_evolution_summary(),
            "meta_learning": self.meta_learning.get_learning_optimization_summary()
        }
    
    def enable_autopoietic_enhancement(self):
        """Enable autopoietic enhancements."""
        self.enhancement_active = True
        logger.info("Autopoietic enhancements enabled")
    
    def disable_autopoietic_enhancement(self):
        """Disable autopoietic enhancements (for debugging/fallback)."""
        self.enhancement_active = False
        logger.info("Autopoietic enhancements disabled")


# Integration with existing api/server.py would look like this:

async def integrate_with_existing_system():
    """
    Example of how to integrate autopoietic enhancements into The Yuki Project system.
    This would be added to api/server.py
    """
    
    # Add to global declarations in api/server.py:
    # autopoietic_layer = AutopoieticEnhancementLayer(db_path="./persistent_state")
    
    # Modify the /chat endpoint to include autopoietic processing:
    """
    @app.post("/chat")
    async def chat_endpoint(request: ChatRequest, background_tasks: BackgroundTasks):
        # ... existing chat logic ...
        
        # Add autopoietic processing after main response generation
        interaction_context = {
            "user_message": user_message,
            "ai_response": final_response,
            "interaction_quality": processed_output.salience_score,
            "conflict_score": processed_output.conflict_score,
            "primary_reflection": reflection_data  # if available
        }
        
        # Process autopoietically
        autopoietic_results = await autopoietic_layer.process_interaction_autopoietically(
            user_message=user_message,
            ai_response=final_response,
            interaction_context=interaction_context,
            identity_core=memory.get_identity_core(),
            emotional_state=memory.get_emotional_state(), 
            memory_engine=memory,
            llm_client=llm
        )
        
        # Apply any architectural changes or goal influences
        # ... integration logic ...
        
        return StreamingResponse(response_generator, media_type="text/plain")
    """
    
    # Add new endpoint for autopoietic status:
    """
    @app.get("/autopoietic/status")
    async def get_autopoietic_status():
        return autopoietic_layer.get_autopoietic_status()
    """