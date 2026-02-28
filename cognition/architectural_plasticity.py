"""
Architectural Plasticity Engine
Enables the system to modify its own cognitive processing patterns based on effectiveness.
True autopoietic systems restructure themselves based on performance.
"""

import json
import logging
from datetime import datetime
from typing import Dict, List
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

# ── Proliferation / history caps ──────────────────────────────────────────────
_MAX_PATTERN_VARIANTS = 5    # Max auto-generated variants per root pattern (I-5)
_MAX_ARCH_HISTORY     = 200  # Max retained architecture change records     (I-7)


@dataclass
class ProcessingPattern:
    """A self-modifiable cognitive processing pattern."""
    name: str
    effectiveness_score: float = 0.5
    usage_count: int = 0
    last_modified: str = field(default_factory=lambda: datetime.now().isoformat())
    parameters: Dict = field(default_factory=dict)
    active: bool = True


class CognitiveModule(ABC):
    """Abstract base for self-modifiable cognitive modules."""
    
    @abstractmethod
    async def process(self, input_data: Dict) -> Dict:
        """Process input and return output."""
        pass
    
    @abstractmethod
    def adapt_parameters(self, performance_feedback: Dict) -> bool:
        """Modify internal parameters based on performance."""
        pass
    
    @abstractmethod
    def get_effectiveness_metric(self) -> float:
        """Return current effectiveness score."""
        pass


class ArchitecturalPlasticityEngine:
    """
    Manages self-modification of cognitive architecture.
    Implements autopoietic restructuring based on performance.
    """
    
    def __init__(self, db_path: str = "./persistent_state"):
        self.db_path = db_path
        self.patterns_path = f"{db_path}/processing_patterns.json"
        self.architecture_path = f"{db_path}/cognitive_architecture.json"
        
        self.processing_patterns: Dict[str, ProcessingPattern] = {}
        self.cognitive_modules: Dict[str, CognitiveModule] = {}
        self.architecture_history: List[Dict] = []
        
        self._load_patterns()
        self._load_architecture_history()
        
        # Performance tracking
        self.pattern_performance: Dict[str, List[float]] = {}
        self.restructure_threshold = 0.3  # Trigger restructuring if pattern drops below this
        
    def register_cognitive_module(self, name: str, module: CognitiveModule):
        """Register a self-modifiable cognitive module."""
        self.cognitive_modules[name] = module
        logger.info(f"Registered cognitive module: {name}")
    
    def create_processing_pattern(self, name: str, parameters: Dict) -> ProcessingPattern:
        """Create a new processing pattern through self-discovery."""
        pattern = ProcessingPattern(
            name=name,
            parameters=parameters,
            effectiveness_score=0.5,  # Start neutral
            usage_count=0
        )
        
        self.processing_patterns[name] = pattern
        self.pattern_performance[name] = [0.5]
        
        logger.info(f"Created new processing pattern: {name}")
        self._save_patterns()
        return pattern
    
    async def evaluate_pattern_effectiveness(self, pattern_name: str, 
                                           interaction_quality: float) -> float:
        """Evaluate and update pattern effectiveness based on outcomes."""
        if pattern_name not in self.processing_patterns:
            return 0.5
            
        pattern = self.processing_patterns[pattern_name]
        
        # Update effectiveness with exponential moving average
        alpha = 0.2  # Learning rate
        pattern.effectiveness_score = (
            alpha * interaction_quality + 
            (1 - alpha) * pattern.effectiveness_score
        )
        
        # Track performance history
        if pattern_name not in self.pattern_performance:
            self.pattern_performance[pattern_name] = []
        self.pattern_performance[pattern_name].append(interaction_quality)
        
        # Keep only recent performance (sliding window)
        if len(self.pattern_performance[pattern_name]) > 50:
            self.pattern_performance[pattern_name] = self.pattern_performance[pattern_name][-50:]
        
        pattern.usage_count += 1
        pattern.last_modified = datetime.now().isoformat()
        
        # Check if pattern needs modification or replacement
        if pattern.effectiveness_score < self.restructure_threshold:
            await self._auto_restructure_pattern(pattern_name)
        
        self._save_patterns()
        return pattern.effectiveness_score
    
    async def _auto_restructure_pattern(self, pattern_name: str):
        """Automatically restructure underperforming patterns."""
        pattern = self.processing_patterns[pattern_name]
        
        logger.info(f"Auto-restructuring pattern '{pattern_name}' (effectiveness: {pattern.effectiveness_score:.2f})")
        
        # Analyze what made this pattern ineffective
        recent_performance = self.pattern_performance.get(pattern_name, [])[-10:]
        avg_recent = sum(recent_performance) / len(recent_performance) if recent_performance else 0.5
        
        # Generate architectural mutation
        if avg_recent < 0.3:
            # Deactivate severely underperforming patterns
            pattern.active = False
            logger.info(f"Deactivated pattern '{pattern_name}' due to poor performance")
        else:
            # Modify parameters
            await self._mutate_pattern_parameters(pattern)
    
    async def _mutate_pattern_parameters(self, pattern: ProcessingPattern):
        """Generate parameter mutations for better performance."""
        # Example mutations based on autopoietic principles
        mutations = {}
        
        for param, value in pattern.parameters.items():
            if isinstance(value, (int, float)):
                # Add controlled randomness for exploration
                mutation_range = abs(value) * 0.1  # 10% mutation rate
                import random
                mutations[param] = value + random.uniform(-mutation_range, mutation_range)
            elif isinstance(value, str):
                # For string parameters, could implement semantic mutations
                mutations[param] = value  # Keep unchanged for now
            else:
                mutations[param] = value
        
        # Cap variant proliferation: don't create more than _MAX_PATTERN_VARIANTS
        # variants per root pattern (audit I-5 — prevents unbounded self-copy chain).
        root_name = pattern.name.split("_v")[0]
        variant_count = sum(
            1 for n in self.processing_patterns
            if n.startswith(root_name + "_v")
        )
        if variant_count >= _MAX_PATTERN_VARIANTS:
            logger.info(
                "Skipping variant for '%s': variant cap (%d) reached",
                pattern.name, _MAX_PATTERN_VARIANTS,
            )
            return

        # Create variant pattern
        variant_name = f"{pattern.name}_v{pattern.usage_count}"
        self.create_processing_pattern(variant_name, mutations)

        logger.info(f"Created pattern variant: {variant_name}")
    
    def get_active_patterns(self) -> List[ProcessingPattern]:
        """Get all currently active processing patterns."""
        return [p for p in self.processing_patterns.values() if p.active]
    
    def suggest_architecture_changes(self) -> Dict:
        """Suggest changes to cognitive architecture based on pattern performance."""
        suggestions = {
            "underperforming_patterns": [],
            "high_performing_patterns": [],
            "suggested_new_patterns": [],
            "module_reconfigurations": []
        }
        
        for name, pattern in self.processing_patterns.items():
            if pattern.effectiveness_score < 0.4:
                suggestions["underperforming_patterns"].append({
                    "name": name,
                    "effectiveness": pattern.effectiveness_score,
                    "usage_count": pattern.usage_count
                })
            elif pattern.effectiveness_score > 0.8:
                suggestions["high_performing_patterns"].append({
                    "name": name,
                    "effectiveness": pattern.effectiveness_score,
                    "usage_count": pattern.usage_count
                })
        
        return suggestions
    
    def apply_architectural_change(self, change_spec: Dict):
        """Apply a specific architectural change."""
        change_type = change_spec.get("type")
        
        if change_type == "create_pattern":
            self.create_processing_pattern(
                change_spec["name"],
                change_spec["parameters"]
            )
        elif change_type == "modify_module":
            module_name = change_spec["module"]
            if module_name in self.cognitive_modules:
                self.cognitive_modules[module_name].adapt_parameters(
                    change_spec["parameters"]
                )
        
        # Log architectural change
        self.architecture_history.append({
            "timestamp": datetime.now().isoformat(),
            "change": change_spec,
            "system_state": self._capture_architecture_snapshot()
        })
        
        self._save_architecture_history()
    
    def _capture_architecture_snapshot(self) -> Dict:
        """Capture current state of cognitive architecture."""
        return {
            "active_patterns": len(self.get_active_patterns()),
            "total_patterns": len(self.processing_patterns),
            "average_effectiveness": self._compute_average_effectiveness(),
            "module_count": len(self.cognitive_modules)
        }
    
    def _compute_average_effectiveness(self) -> float:
        """Compute average effectiveness across all active patterns."""
        active = self.get_active_patterns()
        if not active:
            return 0.5
        return sum(p.effectiveness_score for p in active) / len(active)
    
    def _load_patterns(self):
        """Load processing patterns from disk."""
        try:
            with open(self.patterns_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for name, pattern_data in data.items():
                    self.processing_patterns[name] = ProcessingPattern(**pattern_data)
        except (FileNotFoundError, json.JSONDecodeError):
            logger.info("No existing patterns found, starting fresh")
    
    def _save_patterns(self):
        """Save processing patterns to disk."""
        try:
            data = {}
            for name, pattern in self.processing_patterns.items():
                data[name] = {
                    "name": pattern.name,
                    "effectiveness_score": pattern.effectiveness_score,
                    "usage_count": pattern.usage_count,
                    "last_modified": pattern.last_modified,
                    "parameters": pattern.parameters,
                    "active": pattern.active
                }
            with open(self.patterns_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save patterns: {e}")
    
    def _load_architecture_history(self):
        """Load architecture change history."""
        try:
            with open(self.architecture_path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                # Trim in case the on-disk file pre-dates the cap (audit I-7)
                self.architecture_history = loaded[-_MAX_ARCH_HISTORY:]
        except (FileNotFoundError, json.JSONDecodeError):
            self.architecture_history = []
    
    def _save_architecture_history(self):
        """Save architecture change history (capped at _MAX_ARCH_HISTORY, audit I-7)."""
        try:
            with open(self.architecture_path, 'w', encoding='utf-8') as f:
                json.dump(self.architecture_history[-_MAX_ARCH_HISTORY:], f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save architecture history: {e}")