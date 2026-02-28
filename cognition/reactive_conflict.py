import re
import random


class ConflictResolver:
    """
    Deterministic cognitive conflict detection and rewrite layer.
    
    Enhanced with:
    - Soft-pass mode for minor conflicts (preserves personality texture)
    - Configurable bypass probability (allows occasional "raw" responses)
    - Authenticity dial to balance coherence vs. aliveness
    """

    _ABSOLUTE_WORDS = {"always", "never", "definitely", "certainly", "must", "guaranteed"}
    _COLD_WORDS = {"irrelevant", "whatever", "doesn't matter", "not my concern", "not important"}
    
    # New: Configuration for aliveness vs. coherence
    DEFAULT_BYPASS_PROBABILITY = 0.12  # 12% of responses skip conflict resolution
    SOFT_PASS_THRESHOLD = 0.35         # Conflicts below this pass unchanged
    
    def __init__(
        self,
        bypass_probability: float = None,
        soft_pass_threshold: float = None,
        authenticity_mode: bool = True
    ):
        """
        Initialize ConflictResolver with aliveness settings.
        
        Args:
            bypass_probability: Chance to skip resolution entirely (0.0-0.25)
            soft_pass_threshold: Conflicts below this score pass unchanged
            authenticity_mode: When True, allows more personality variance
        """
        self.bypass_probability = bypass_probability if bypass_probability is not None else self.DEFAULT_BYPASS_PROBABILITY
        self.soft_pass_threshold = soft_pass_threshold if soft_pass_threshold is not None else self.SOFT_PASS_THRESHOLD
        self.authenticity_mode = authenticity_mode
        
        # Track bypass statistics for debugging
        self.bypass_count = 0
        self.soft_pass_count = 0
        self.total_calls = 0

    def evaluate_conflict(
        self,
        text: str,
        identity_core,
        emotional_state,
        memory_engine,
    ) -> float:
        tone_trait_mismatch = self._tone_trait_mismatch(text, identity_core)
        memory_contradiction = self._memory_contradiction(text, memory_engine)
        emotional_drift = self._emotional_drift(text, identity_core, emotional_state)

        conflict_score = (
            0.4 * tone_trait_mismatch
            + 0.4 * memory_contradiction
            + 0.2 * emotional_drift
        )
        return self._clamp(conflict_score, 0.0, 1.0)

    def resolve_if_needed(
        self,
        text: str,
        conflict_score: float,
        identity_core,
        emotional_state,
        force_resolve: bool = False
    ) -> str:
        """
        Resolve conflicts in text based on conflict score.
        
        Args:
            text: The response text to potentially modify
            conflict_score: Score from evaluate_conflict (0.0-1.0)
            identity_core: Current identity traits
            emotional_state: Current emotional state
            force_resolve: If True, skip bypass/soft-pass checks
        
        Returns:
            Original or modified text
        """
        self.total_calls += 1
        
        # === DYNAMIC SOFT-PASS THRESHOLD ("Allowable Drift" Zone) ===
        # High playfulness/warmth/joy = more tolerance for inconsistency
        # Strict logic is for analytical mode; emotional warmth allows messiness
        dynamic_threshold = self._compute_dynamic_threshold(identity_core, emotional_state)
        
        # === BYPASS CHECK (preserves aliveness) ===
        # Random chance to skip resolution entirely, letting "raw" personality through
        if not force_resolve and self.authenticity_mode:
            # Dynamic bypass probability: increase when warmth/playfulness high
            warmth = float(emotional_state.get("warmth", 0.5))
            playfulness = float(identity_core.get("playfulness", 0.4))
            dynamic_bypass = self.bypass_probability + (warmth * 0.05) + (playfulness * 0.05)
            
            if random.random() < dynamic_bypass:
                self.bypass_count += 1
                # Only bypass for non-severe conflicts
                if conflict_score < 0.6:
                    return text
        
        # === SOFT-PASS MODE ===
        # Minor conflicts pass unchanged to preserve personality texture
        if not force_resolve and self.authenticity_mode:
            if conflict_score < dynamic_threshold:
                self.soft_pass_count += 1
                return text
        
        # === STANDARD RESOLUTION ===
        if conflict_score > 0.6:
            return self._strong_rewrite(text, identity_core, emotional_state)
        if 0.3 <= conflict_score <= 0.6:
            return self._soften_tone(text, emotional_state)
        return text
    
    def get_stats(self) -> dict:
        """Get resolution statistics for debugging."""
        return {
            "total_calls": self.total_calls,
            "bypass_count": self.bypass_count,
            "soft_pass_count": self.soft_pass_count,
            "bypass_rate": self.bypass_count / max(1, self.total_calls),
            "soft_pass_rate": self.soft_pass_count / max(1, self.total_calls),
            "authenticity_mode": self.authenticity_mode
        }

    def _compute_dynamic_threshold(self, identity_core: dict, emotional_state: dict) -> float:
        """
        Compute dynamic soft-pass threshold based on current traits/emotions.
        
        "Allowable Drift" Zone: 
        - High playfulness/warmth/joy = more tolerance for messiness
        - Low engagement/analytical mode = stricter consistency
        
        Base threshold: 0.35
        Range: 0.25 (strict) to 0.50 (permissive)
        """
        base = self.soft_pass_threshold
        
        # Traits that INCREASE tolerance (allow more messiness)
        playfulness = float(identity_core.get("playfulness", 0.4))
        emotional_warmth = float(identity_core.get("emotional_warmth", 0.6))
        warmth = float(emotional_state.get("warmth", 0.5))
        
        # High values = more tolerance
        permissive_factor = (playfulness * 0.08) + (emotional_warmth * 0.05) + (warmth * 0.07)
        
        # Traits that DECREASE tolerance (require more consistency)
        confidence = float(identity_core.get("confidence", 0.5))
        analytical_depth = float(identity_core.get("analytical_depth", 0.6))
        
        # High confidence + analytical = less tolerance  
        strict_factor = ((confidence - 0.5) * 0.05) + ((analytical_depth - 0.5) * 0.03)
        
        # Compute final threshold
        dynamic = base + permissive_factor - strict_factor
        
        # Clamp to reasonable range
        return self._clamp(dynamic, 0.25, 0.50)

    def _tone_trait_mismatch(self, text: str, identity_core: dict) -> float:
        confidence = float(identity_core.get("confidence", 0.5))
        lowered = text.lower()
        absolute_hits = sum(1 for word in self._ABSOLUTE_WORDS if re.search(rf"\b{re.escape(word)}\b", lowered))
        if confidence < 0.4 and absolute_hits > 0:
            return self._clamp(0.45 + (absolute_hits * 0.15), 0.0, 1.0)

        hedges = len(re.findall(r"\b(maybe|perhaps|i think|it seems|might)\b", lowered))
        if confidence > 0.7 and hedges >= 2:
            return self._clamp(0.30 + hedges * 0.1, 0.0, 1.0)
        return 0.0

    def _memory_contradiction(self, text: str, memory_engine) -> float:
        if not text or memory_engine.user_memory.count() == 0:
            return 0.0

        score = 0.0
        claims = self._extract_user_claims(text)
        if not claims:
            return 0.0

        for claim in claims:
            try:
                query = memory_engine.user_memory.query(query_texts=[claim], n_results=1)
                distances = query.get("distances", [[]])
                docs = query.get("documents", [[]])
                if not distances or not distances[0] or not docs or not docs[0]:
                    continue

                distance = float(distances[0][0])
                memory_text = str(docs[0][0])
                similarity = self._clamp(1.0 - (distance / 2.0), 0.0, 1.0)

                if similarity < 0.65:
                    continue

                neg_claim = self._has_negation(claim)
                neg_memory = self._has_negation(memory_text)
                if neg_claim != neg_memory:
                    score = max(score, 0.75)
                    continue

                entity_conflict = self._entity_conflict(claim, memory_text)
                if entity_conflict:
                    score = max(score, 0.65)
            except Exception:
                continue

        return self._clamp(score, 0.0, 1.0)

    def _emotional_drift(self, text: str, identity_core: dict, emotional_state: dict) -> float:
        warmth_target = float(identity_core.get("emotional_warmth", 0.6)) * float(emotional_state.get("warmth", 0.5))
        lowered = text.lower()
        cold_hits = sum(1 for token in self._COLD_WORDS if token in lowered)

        if warmth_target >= 0.5 and cold_hits > 0:
            return self._clamp(0.4 + (cold_hits * 0.2), 0.0, 1.0)
        return 0.0

    def _strong_rewrite(self, text: str, identity_core: dict, emotional_state: dict) -> str:
        softened = self._soften_tone(text, emotional_state)
        softened = re.sub(r"\b(always|never|definitely|guaranteed)\b", "generally", softened, flags=re.IGNORECASE)

        if not re.search(r"\b(based on what you shared|from your context)\b", softened, re.IGNORECASE):
            softened = f"Based on what you shared, {softened[0].lower() + softened[1:] if softened else softened}"

        return softened.strip()

    def _soften_tone(self, text: str, emotional_state: dict) -> str:
        softened = text.strip()
        softened = re.sub(r"\bmust\b", "can", softened, flags=re.IGNORECASE)
        softened = re.sub(r"\bshould\b", "could", softened, flags=re.IGNORECASE)
        softened = re.sub(r"\bwrong\b", "not fully aligned", softened, flags=re.IGNORECASE)

        warmth = float(emotional_state.get("warmth", 0.5))

        return softened.strip()

    def _extract_user_claims(self, text: str):
        patterns = [
            re.compile(r"\byou are\s+([^.!?\n]+)", re.IGNORECASE),
            re.compile(r"\byour\s+([a-zA-Z_ ]+?)\s+is\s+([^.!?\n]+)", re.IGNORECASE),
            re.compile(r"\byou\s+(work as|study|live in)\s+([^.!?\n]+)", re.IGNORECASE),
        ]

        claims = []
        for pattern in patterns:
            for match in pattern.findall(text):
                if isinstance(match, tuple):
                    claim = " ".join([m for m in match if m]).strip()
                else:
                    claim = str(match).strip()
                if claim:
                    claims.append(claim)
        return claims

    @staticmethod
    def _has_negation(text: str) -> bool:
        return bool(re.search(r"\b(not|never|no|don't|doesn't|isn't|aren't|can't|won't)\b", text.lower()))

    @staticmethod
    def _entity_conflict(claim: str, memory_text: str) -> bool:
        claim_tokens = re.findall(r"\b[a-zA-Z][a-zA-Z0-9_-]{2,}\b", claim.lower())
        memory_tokens = re.findall(r"\b[a-zA-Z][a-zA-Z0-9_-]{2,}\b", memory_text.lower())

        claim_set = set(claim_tokens)
        memory_set = set(memory_tokens)
        overlap = claim_set.intersection(memory_set)

        if len(overlap) <= 1 and len(claim_set) >= 2 and len(memory_set) >= 2:
            return True
        return False

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, float(value)))
