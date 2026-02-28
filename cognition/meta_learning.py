"""
Meta-Learning Engine
Implements learning how to learn - the system optimizes its own learning processes.
This is a core autopoietic capability: improving the mechanisms of self-improvement.
"""

import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

# ── History / parameter caps ──────────────────────────────────────────────────
_MAX_OPTIMIZATION_HISTORY = 500   # Retained optimization-cycle records         (I-6)

# Hard bounds for each learning parameter to prevent runaway drift             (I-8)
_LEARNING_PARAM_BOUNDS: Dict[str, Tuple[float, float]] = {
    "trait_adjustment_rate":      (0.001,  0.1),
    "reflection_frequency":       (3.0,   50.0),
    "curiosity_threshold":        (0.1,    0.95),
    "memory_consolidation_delay": (5.0,  600.0),
    "salience_gate_threshold":    (0.1,    0.9),
    "emotional_adaptation_rate":  (0.001,  0.1),
    "goal_emergence_sensitivity": (0.1,    0.95),
}


class LearningStrategy(Enum):
    EXPERIENTIAL = "experiential"      # Learning from interaction patterns
    REFLECTIVE = "reflective"          # Learning from self-analysis
    ADAPTIVE = "adaptive"              # Learning through parameter adjustment
    EMERGENT = "emergent"              # Learning through pattern discovery
    RECURSIVE = "recursive"            # Learning about learning processes


@dataclass
class LearningExperiment:
    """A controlled learning experiment with measurable outcomes."""
    id: str
    strategy: LearningStrategy
    hypothesis: str
    parameters: Dict
    start_time: str
    end_time: Optional[str] = None
    baseline_metrics: Dict = field(default_factory=dict)
    result_metrics: Dict = field(default_factory=dict)
    success: Optional[bool] = None
    insights: List[str] = field(default_factory=list)
    active: bool = True


class LearningPattern:
    """Represents a discovered pattern in how learning occurs."""
    
    def __init__(self, pattern_id: str, pattern_type: str, effectiveness: float):
        self.id = pattern_id
        self.pattern_type = pattern_type  # e.g., "trait_adjustment", "reflection_timing"
        self.effectiveness = effectiveness
        self.usage_count = 0
        self.success_rate = 0.5
        self.parameters = {}
        self.discovered_at = datetime.now().isoformat()


class MetaLearningEngine:
    """
    Autopoietic meta-learning system that optimizes how the AI learns and adapts.
    Implements learning to learn better.
    """
    
    def __init__(self, db_path: str = "./persistent_state"):
        self.db_path = db_path
        os.makedirs(self.db_path, exist_ok=True)
        self.experiments_path = f"{db_path}/learning_experiments.json"
        self.patterns_path = f"{db_path}/learning_patterns.json"
        self.optimization_history_path = f"{db_path}/learning_optimization_history.json"
        
        # Core data structures
        self.active_experiments: Dict[str, LearningExperiment] = {}
        self.completed_experiments: Dict[str, LearningExperiment] = {}
        self.learning_patterns: Dict[str, LearningPattern] = {}
        self.optimization_history: List[Dict] = []
        
        # Learning parameters that the system optimizes
        self.learning_parameters = {
            "trait_adjustment_rate": 0.02,
            "reflection_frequency": 10,
            "curiosity_threshold": 0.7,
            "memory_consolidation_delay": 60,
            "salience_gate_threshold": 0.65,
            "emotional_adaptation_rate": 0.01,
            "goal_emergence_sensitivity": 0.6
        }
        
        # Performance tracking
        self.learning_effectiveness_history: List[Tuple[str, float]] = []
        self.parameter_evolution_log: List[Dict] = []
        
        # Meta-learning state
        self.experiment_counter = 0
        self.discovery_counter = 0
        
        self._load_learning_data()
        self._initialize_baseline_experiments()
    
    def _load_learning_data(self):
        """Load learning experiments and patterns from persistent storage."""
        try:
            # Load experiments
            with open(self.experiments_path, 'r', encoding='utf-8') as f:
                exp_data = json.load(f)
                for exp_id, exp_dict in exp_data.get("active", {}).items():
                    exp_dict["strategy"] = LearningStrategy(exp_dict["strategy"])
                    self.active_experiments[exp_id] = LearningExperiment(**exp_dict)
                for exp_id, exp_dict in exp_data.get("completed", {}).items():
                    exp_dict["strategy"] = LearningStrategy(exp_dict["strategy"])
                    self.completed_experiments[exp_id] = LearningExperiment(**exp_dict)
                    
            # Load patterns
            with open(self.patterns_path, 'r', encoding='utf-8') as f:
                pattern_data = json.load(f)
                for pattern_id, pattern_dict in pattern_data.items():
                    pattern = LearningPattern(
                        pattern_dict["id"],
                        pattern_dict["pattern_type"],
                        pattern_dict["effectiveness"]
                    )
                    pattern.usage_count = pattern_dict.get("usage_count", 0)
                    pattern.success_rate = pattern_dict.get("success_rate", 0.5)
                    pattern.parameters = pattern_dict.get("parameters", {})
                    self.learning_patterns[pattern_id] = pattern
                    
            # Load optimization history
            with open(self.optimization_history_path, 'r', encoding='utf-8') as f:
                self.optimization_history = json.load(f)
                
        except (FileNotFoundError, json.JSONDecodeError):
            logger.info("No existing meta-learning data found, starting fresh")
    
    def _initialize_baseline_experiments(self):
        """Initialize baseline learning experiments for comparison."""
        if not self.active_experiments and not self.completed_experiments:
            
            # Baseline trait adjustment experiment
            self._create_experiment(
                LearningStrategy.ADAPTIVE,
                "Optimize trait adjustment rate for better personality consistency",
                {"adjustment_rate_range": [0.005, 0.05], "evaluation_period": 50}
            )
            
            # Reflection timing experiment  
            self._create_experiment(
                LearningStrategy.REFLECTIVE,
                "Find optimal reflection frequency for insight generation",
                {"frequency_range": [5, 25], "insight_threshold": 2}
            )
    
    async def optimize_learning_process(self, 
                                      current_performance: Dict,
                                      interaction_context: Dict,
                                      memory_engine) -> Dict:
        """
        Main optimization loop: analyze current learning effectiveness
        and adjust learning parameters accordingly.
        """
        
        optimization_results = {
            "parameter_adjustments": {},
            "new_experiments": [],
            "completed_experiments": [],
            "discovered_patterns": []
        }
        
        # 1. Evaluate active experiments
        completed = await self._evaluate_active_experiments(current_performance)
        optimization_results["completed_experiments"] = [exp.id for exp in completed]
        
        # 2. Discover new learning patterns from completed experiments
        patterns = await self._discover_learning_patterns(completed)
        optimization_results["discovered_patterns"] = [p.id for p in patterns]
        
        # 3. Apply successful patterns to optimize parameters
        adjustments = await self._apply_pattern_optimizations(patterns)
        optimization_results["parameter_adjustments"] = adjustments
        
        # 4. Generate new experiments based on performance gaps
        new_experiments = await self._generate_adaptive_experiments(current_performance)
        optimization_results["new_experiments"] = [exp.id for exp in new_experiments]
        
        # 5. Update learning effectiveness tracking
        overall_effectiveness = self._compute_learning_effectiveness(current_performance)
        self.learning_effectiveness_history.append(
            (datetime.now().isoformat(), overall_effectiveness)
        )
        
        # 6. Log optimization cycle
        self.optimization_history.append({
            "timestamp": datetime.now().isoformat(),
            "performance": current_performance,
            "results": optimization_results,
            "effectiveness": overall_effectiveness
        })

        # Cap histories to prevent unbounded memory / disk growth (audit I-6)
        if len(self.optimization_history) > _MAX_OPTIMIZATION_HISTORY:
            self.optimization_history = self.optimization_history[-_MAX_OPTIMIZATION_HISTORY:]
        if len(self.learning_effectiveness_history) > _MAX_OPTIMIZATION_HISTORY:
            self.learning_effectiveness_history = (
                self.learning_effectiveness_history[-_MAX_OPTIMIZATION_HISTORY:]
            )

        self._save_learning_data()
        
        return optimization_results
    
    async def _evaluate_active_experiments(self, performance: Dict) -> List[LearningExperiment]:
        """Evaluate active experiments and complete those that have sufficient data."""
        
        completed_experiments = []
        
        for exp in list(self.active_experiments.values()):
            
            # Check if experiment has run long enough
            start_time = datetime.fromisoformat(exp.start_time)
            elapsed = datetime.now() - start_time
            
            evaluation_period = exp.parameters.get("evaluation_period", 50)
            if elapsed.total_seconds() < evaluation_period * 60:  # Convert to seconds
                continue
            
            # Evaluate experiment results
            success = await self._evaluate_experiment_success(exp, performance)
            
            # Complete the experiment
            exp.end_time = datetime.now().isoformat()
            exp.result_metrics = performance.copy()
            exp.success = success
            exp.active = False
            
            # Generate insights
            exp.insights = await self._extract_experiment_insights(exp)
            
            # Move to completed
            self.completed_experiments[exp.id] = exp
            del self.active_experiments[exp.id]
            
            completed_experiments.append(exp)
            
            logger.info(f"Completed learning experiment: {exp.id} (success: {success})")
        
        return completed_experiments
    
    async def _evaluate_experiment_success(self, exp: LearningExperiment, performance: Dict) -> bool:
        """Determine if a learning experiment was successful."""
        
        if exp.strategy == LearningStrategy.ADAPTIVE:
            # For parameter optimization experiments
            baseline_score = exp.baseline_metrics.get("overall_quality", 0.5)
            current_score = performance.get("overall_quality", 0.5)
            return current_score > baseline_score + 0.05  # 5% improvement threshold
        
        elif exp.strategy == LearningStrategy.REFLECTIVE:
            # For reflection optimization experiments
            baseline_insights = exp.baseline_metrics.get("insights_per_session", 1)
            current_insights = performance.get("insights_per_session", 1)
            return current_insights > baseline_insights * 1.2  # 20% improvement
        
        elif exp.strategy == LearningStrategy.EXPERIENTIAL:
            # For interaction learning experiments
            baseline_satisfaction = exp.baseline_metrics.get("user_satisfaction", 0.5)
            current_satisfaction = performance.get("user_satisfaction", 0.5)
            return current_satisfaction > baseline_satisfaction + 0.1
        
        elif exp.strategy == LearningStrategy.EMERGENT:
            # For pattern discovery experiments
            return performance.get("novel_patterns_discovered", 0) > 0
        
        elif exp.strategy == LearningStrategy.RECURSIVE:
            # For meta-learning experiments
            baseline_meta = exp.baseline_metrics.get("meta_learning_effectiveness", 0.5)
            current_meta = performance.get("meta_learning_effectiveness", 0.5)
            return current_meta > baseline_meta + 0.05
        
        return False
    
    async def _extract_experiment_insights(self, exp: LearningExperiment) -> List[str]:
        """Extract actionable insights from completed experiments."""
        insights = []
        
        if exp.success:
            if exp.strategy == LearningStrategy.ADAPTIVE:
                insights.append(f"Parameter optimization successful: {exp.parameters}")
            elif exp.strategy == LearningStrategy.REFLECTIVE:
                insights.append(f"Reflection timing optimization effective: {exp.hypothesis}")
            elif exp.strategy == LearningStrategy.EXPERIENTIAL:
                insights.append(f"Interaction learning pattern validated: {exp.hypothesis}")
        else:
            insights.append(f"Strategy {exp.strategy.value} ineffective for: {exp.hypothesis}")
        
        # Analyze what made it succeed or fail
        baseline = exp.baseline_metrics
        results = exp.result_metrics
        
        for metric, baseline_value in baseline.items():
            if metric in results:
                change = results[metric] - baseline_value
                if abs(change) > 0.05:  # Significant change
                    direction = "improved" if change > 0 else "degraded"
                    insights.append(f"Metric {metric} {direction} by {change:.3f}")
        
        return insights
    
    async def _discover_learning_patterns(self, completed_experiments: List[LearningExperiment]) -> List[LearningPattern]:
        """Discover new learning patterns from successful experiments."""
        
        discovered_patterns = []
        
        # Group experiments by strategy and success
        successful_experiments = [exp for exp in completed_experiments if exp.success]
        
        if not successful_experiments:
            return discovered_patterns
        
        # Pattern discovery for parameter optimization
        param_experiments = [exp for exp in successful_experiments 
                           if exp.strategy == LearningStrategy.ADAPTIVE]
        
        for exp in param_experiments:
            pattern = self._extract_parameter_pattern(exp)
            if pattern:
                discovered_patterns.append(pattern)
        
        # Pattern discovery for timing optimization
        timing_experiments = [exp for exp in successful_experiments
                            if exp.strategy == LearningStrategy.REFLECTIVE]
        
        for exp in timing_experiments:
            pattern = self._extract_timing_pattern(exp)
            if pattern:
                discovered_patterns.append(pattern)
        
        # Register discovered patterns
        for pattern in discovered_patterns:
            self.learning_patterns[pattern.id] = pattern
            self.discovery_counter += 1
            logger.info(f"Discovered learning pattern: {pattern.id}")
        
        return discovered_patterns
    
    def _extract_parameter_pattern(self, exp: LearningExperiment) -> Optional[LearningPattern]:
        """Extract parameter optimization pattern from successful experiment."""
        
        if not exp.success or exp.strategy != LearningStrategy.ADAPTIVE:
            return None
        
        pattern_id = f"param_pattern_{self.discovery_counter + 1}"
        
        # Analyze what parameter changes led to success
        effectiveness = self._compute_pattern_effectiveness(exp)
        
        pattern = LearningPattern(pattern_id, "parameter_optimization", effectiveness)
        pattern.parameters = exp.parameters.copy()
        
        return pattern
    
    def _extract_timing_pattern(self, exp: LearningExperiment) -> Optional[LearningPattern]:
        """Extract timing optimization pattern from successful experiment."""
        
        if not exp.success or exp.strategy != LearningStrategy.REFLECTIVE:
            return None
        
        pattern_id = f"timing_pattern_{self.discovery_counter + 1}"
        effectiveness = self._compute_pattern_effectiveness(exp)
        
        pattern = LearningPattern(pattern_id, "timing_optimization", effectiveness)
        pattern.parameters = exp.parameters.copy()
        
        return pattern
    
    def _compute_pattern_effectiveness(self, exp: LearningExperiment) -> float:
        """Compute how effective a learning pattern is."""
        
        if not exp.result_metrics or not exp.baseline_metrics:
            return 0.5
        
        # Compute improvement across key metrics
        improvements = []
        
        for metric in ["overall_quality", "user_satisfaction", "insights_per_session"]:
            if metric in exp.baseline_metrics and metric in exp.result_metrics:
                baseline = exp.baseline_metrics[metric]
                result = exp.result_metrics[metric]
                if baseline > 0:
                    improvement = (result - baseline) / baseline
                    improvements.append(improvement)
        
        if not improvements:
            return 0.5
        
        avg_improvement = sum(improvements) / len(improvements)
        # Normalize to 0-1 range (0.2 improvement = 0.8 effectiveness)
        effectiveness = 0.5 + min(avg_improvement, 0.5)
        
        return max(0.0, min(1.0, effectiveness))
    
    async def _apply_pattern_optimizations(self, patterns: List[LearningPattern]) -> Dict:
        """Apply successful learning patterns to optimize system parameters."""
        
        adjustments = {}
        
        for pattern in patterns:
            if pattern.effectiveness > 0.7:  # Only apply highly effective patterns
                
                if pattern.pattern_type == "parameter_optimization":
                    # Apply parameter adjustments
                    adjustments.update(self._apply_parameter_pattern(pattern))
                
                elif pattern.pattern_type == "timing_optimization":
                    # Apply timing adjustments
                    adjustments.update(self._apply_timing_pattern(pattern))
                
                # Track pattern usage
                pattern.usage_count += 1
        
        # Update learning parameters
        for param, new_value in adjustments.items():
            if param in self.learning_parameters:
                old_value = self.learning_parameters[param]
                # Clamp to known safe bounds before applying (audit I-8)
                if param in _LEARNING_PARAM_BOUNDS:
                    lo, hi = _LEARNING_PARAM_BOUNDS[param]
                    new_value = max(lo, min(hi, new_value))
                self.learning_parameters[param] = new_value

                # Log parameter evolution
                self.parameter_evolution_log.append({
                    "timestamp": datetime.now().isoformat(),
                    "parameter": param,
                    "old_value": old_value,
                    "new_value": new_value,
                    "reason": f"Applied pattern with effectiveness {pattern.effectiveness:.2f}"
                })
        
        return adjustments
    
    def _apply_parameter_pattern(self, pattern: LearningPattern) -> Dict:
        """Apply parameter optimization pattern."""
        adjustments = {}
        
        # Extract optimal parameters from pattern
        for param, value in pattern.parameters.items():
            if isinstance(value, (int, float)) and param.endswith("_rate"):
                # Apply the learned optimal rate
                adjustments[param] = value
        
        return adjustments
    
    def _apply_timing_pattern(self, pattern: LearningPattern) -> Dict:
        """Apply timing optimization pattern."""
        adjustments = {}
        
        # Extract optimal timing parameters
        frequency = pattern.parameters.get("optimal_frequency")
        if frequency:
            adjustments["reflection_frequency"] = frequency
        
        return adjustments
    
    async def _generate_adaptive_experiments(self, performance: Dict) -> List[LearningExperiment]:
        """Generate new learning experiments based on performance gaps."""
        
        new_experiments = []
        
        # Don't create too many concurrent experiments
        if len(self.active_experiments) >= 3:
            return new_experiments
        
        # Identify performance gaps and create targeted experiments
        
        # 1. If overall quality is low, experiment with trait adjustment rates
        if performance.get("overall_quality", 0.5) < 0.6:
            exp = self._create_experiment(
                LearningStrategy.ADAPTIVE,
                "Optimize trait adjustment for better quality",
                {"target_metric": "overall_quality", "adjustment_range": [0.01, 0.04]}
            )
            if exp:
                new_experiments.append(exp)
        
        # 2. If insight generation is low, experiment with reflection timing
        if performance.get("insights_per_session", 1) < 2:
            exp = self._create_experiment(
                LearningStrategy.REFLECTIVE,
                "Optimize reflection frequency for insight generation",
                {"target_metric": "insights_per_session", "frequency_range": [8, 20]}
            )
            if exp:
                new_experiments.append(exp)
        
        # 3. If learning effectiveness is declining, try recursive optimization
        if self._is_learning_effectiveness_declining():
            exp = self._create_experiment(
                LearningStrategy.RECURSIVE,
                "Optimize meta-learning parameters",
                {"target_metric": "meta_learning_effectiveness"}
            )
            if exp:
                new_experiments.append(exp)
        
        return new_experiments
    
    def _create_experiment(self, strategy: LearningStrategy, hypothesis: str, parameters: Dict) -> Optional[LearningExperiment]:
        """Create a new learning experiment."""
        
        self.experiment_counter += 1
        exp_id = f"exp_{self.experiment_counter}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        experiment = LearningExperiment(
            id=exp_id,
            strategy=strategy,
            hypothesis=hypothesis,
            parameters=parameters,
            start_time=datetime.now().isoformat(),
            baseline_metrics=self._capture_baseline_metrics()
        )
        
        self.active_experiments[exp_id] = experiment
        
        logger.info(f"Created learning experiment: {hypothesis}")
        return experiment
    
    def _capture_baseline_metrics(self) -> Dict:
        """Capture current performance metrics as baseline."""
        # This would capture current system performance metrics
        return {
            "overall_quality": 0.7,  # Would be computed from actual metrics
            "user_satisfaction": 0.6,
            "insights_per_session": 1.5,
            "meta_learning_effectiveness": 0.5
        }
    
    def _is_learning_effectiveness_declining(self) -> bool:
        """Check if learning effectiveness is declining over time."""
        
        if len(self.learning_effectiveness_history) < 10:
            return False
        
        recent = [score for _, score in self.learning_effectiveness_history[-5:]]
        earlier = [score for _, score in self.learning_effectiveness_history[-10:-5]]
        
        avg_recent = sum(recent) / len(recent)
        avg_earlier = sum(earlier) / len(earlier)
        
        return avg_recent < avg_earlier - 0.05  # 5% decline threshold
    
    def _compute_learning_effectiveness(self, performance: Dict) -> float:
        """Compute overall learning effectiveness score."""
        
        # Weighted combination of learning indicators
        effectiveness = (
            0.3 * performance.get("overall_quality", 0.5) +
            0.2 * performance.get("user_satisfaction", 0.5) +
            0.2 * performance.get("insights_per_session", 1) / 3.0 +  # Normalize
            0.15 * performance.get("adaptation_speed", 0.5) +
            0.15 * performance.get("pattern_discovery_rate", 0.5)
        )
        
        return max(0.0, min(1.0, effectiveness))
    
    def get_learning_optimization_summary(self) -> Dict:
        """Get summary of learning optimization progress."""
        
        return {
            "total_experiments": len(self.active_experiments) + len(self.completed_experiments),
            "active_experiments": len(self.active_experiments),
            "discovered_patterns": len(self.learning_patterns),
            "parameter_optimizations": len(self.parameter_evolution_log),
            "current_effectiveness": (
                self.learning_effectiveness_history[-1][1] 
                if self.learning_effectiveness_history else 0.5
            ),
            "learning_parameters": self.learning_parameters.copy()
        }
    
    def _save_learning_data(self):
        """Save all learning data to persistent storage."""
        try:
            # Save experiments
            exp_data = {
                "active": {eid: self._experiment_to_dict(exp) for eid, exp in self.active_experiments.items()},
                "completed": {eid: self._experiment_to_dict(exp) for eid, exp in self.completed_experiments.items()},
                "counter": self.experiment_counter
            }
            with open(self.experiments_path, 'w', encoding='utf-8') as f:
                json.dump(exp_data, f, indent=2)
            
            # Save patterns
            pattern_data = {}
            for pid, pattern in self.learning_patterns.items():
                pattern_data[pid] = {
                    "id": pattern.id,
                    "pattern_type": pattern.pattern_type,
                    "effectiveness": pattern.effectiveness,
                    "usage_count": pattern.usage_count,
                    "success_rate": pattern.success_rate,
                    "parameters": pattern.parameters
                }
            with open(self.patterns_path, 'w', encoding='utf-8') as f:
                json.dump(pattern_data, f, indent=2)
            
            # Save optimization history
            with open(self.optimization_history_path, 'w', encoding='utf-8') as f:
                json.dump(self.optimization_history, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save learning data: {e}")
    
    def _experiment_to_dict(self, exp: LearningExperiment) -> Dict:
        """Convert experiment to dictionary for serialization."""
        return {
            "id": exp.id,
            "strategy": exp.strategy.value,
            "hypothesis": exp.hypothesis,
            "parameters": exp.parameters,
            "start_time": exp.start_time,
            "end_time": exp.end_time,
            "baseline_metrics": exp.baseline_metrics,
            "result_metrics": exp.result_metrics,
            "success": exp.success,
            "insights": exp.insights,
            "active": exp.active
        }