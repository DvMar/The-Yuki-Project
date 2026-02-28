import re
from typing import Dict, List

from pydantic import BaseModel


class MemoryCandidate(BaseModel):
    content: str
    memory_type: str  # semantic, episodic, identity, belief, goal
    confidence: float
    salience: float
    # Affective context at storage time — enables mood-congruent retrieval
    valence: float = 0.5   # 0=negative, 0.5=neutral, 1=positive
    arousal: float = 0.5   # 0=low activation, 1=high activation


class ProcessedOutput(BaseModel):
    final_text: str
    memory_candidates: List[MemoryCandidate]
    trait_deltas: Dict[str, float]
    emotion_deltas: Dict[str, float]
    salience_score: float
    conflict_score: float


class SubconsciousWrapper:
    """Deterministic post-processor for local cognitive regulation."""

    _HEDGING_PATTERNS = [
        (r"\bmaybe\b", ""),
        (r"\bperhaps\b", ""),
        (r"\bi think\b", ""),
        (r"\bit seems\b", ""),
        (r"\bprobably\b", ""),
    ]

    _STRONG_EMOTION_WORDS = {
        "love", "hate", "terrified", "anxious", "furious", "excited", "devastated", "thrilled", "overwhelmed"
    }

    _EMOTION_WORDS = {
        "happy", "sad", "angry", "afraid", "worried", "stressed", "calm", "excited", "lonely", "confused"
    }

    _STRUCTURE_MARKERS = ("first", "second", "third", "because", "therefore", "however", ":", ";")

    async def process_raw_output(
        self,
        raw_text: str,
        user_message: str,
        identity_core,
        emotional_state,
        response_mode,
        memory_engine,
    ) -> ProcessedOutput:
        # Compute affective snapshot once — shared by all candidates this turn
        mem_valence, mem_arousal = self._compute_memory_affect(user_message, emotional_state or {})

        extracted = self._extract_user_grounded_candidates(user_message)

        selected_candidates: List[MemoryCandidate] = []
        salience_values: List[float] = []

        for candidate in extracted:
            novelty_score = self._novelty_score(candidate["content"], memory_engine)
            emotional_intensity = self._emotional_intensity(user_message)
            identity_relevance = self._identity_relevance(candidate["content"], candidate["memory_type"])
            user_specificity = self._user_specificity(user_message)
            recurrence_signal = self._recurrence_signal(candidate["content"], memory_engine)

            salience = (
                0.35 * novelty_score
                + 0.25 * emotional_intensity
                + 0.20 * identity_relevance
                + 0.10 * user_specificity
                + 0.10 * recurrence_signal
            )
            salience = self._clamp(salience, 0.0, 1.0)
            salience_values.append(salience)

            if salience > 0.65:
                storage_type = "semantic"
            elif salience >= 0.45:
                storage_type = "episodic"
            else:
                continue

            selected_candidates.append(
                MemoryCandidate(
                    content=candidate["content"],
                    memory_type=storage_type,
                    confidence=candidate["confidence"],
                    salience=salience,
                    valence=mem_valence,
                    arousal=mem_arousal,
                )
            )

        trait_deltas = self._compute_trait_deltas(raw_text, user_message)
        emotion_deltas = self._compute_emotion_deltas(raw_text, user_message)
        final_text = self._modulate_text(raw_text, identity_core, emotional_state, response_mode)

        return ProcessedOutput(
            final_text=final_text,
            memory_candidates=selected_candidates,
            trait_deltas=trait_deltas,
            emotion_deltas=emotion_deltas,
            salience_score=(sum(salience_values) / len(salience_values)) if salience_values else 0.0,
            conflict_score=0.0,
        )

    def _extract_user_grounded_candidates(self, user_message: str) -> List[Dict[str, float]]:
        text = user_message.strip()
        lowered = text.lower()
        if not text:
            return []

        blocked_phrases = (
            "if i were",
            "maybe i",
            "could be",
            "might be",
            "suppose",
            "imagine",
        )
        if any(phrase in lowered for phrase in blocked_phrases):
            return []

        candidates: List[Dict[str, float]] = []
        patterns = [
            ("identity", re.compile(r"\b(?:i am|i'm)\s+([^.!?\n]+)", re.IGNORECASE), 0.86),
            ("semantic", re.compile(r"\b(?:i work as|i study|my job is|my job)\s+([^.!?\n]+)", re.IGNORECASE), 0.84),
            ("goal", re.compile(r"\b(?:i want to|i plan to)\s+([^.!?\n]+)", re.IGNORECASE), 0.81),
            ("belief", re.compile(r"\b(?:i feel)\s+([^.!?\n]+)", re.IGNORECASE), 0.80),
        ]

        for memory_type, pattern, confidence in patterns:
            for match in pattern.finditer(text):
                full_match = match.group(0).strip()
                captured = match.group(1).strip() if match.lastindex else ""
                extracted = self._normalize_candidate_text(memory_type, full_match, captured)
                extracted_lower = extracted.lower()

                if any(marker in extracted_lower for marker in ("you are", "assistant", "ai", "hypothetical", "maybe", "might")):
                    continue

                if extracted:
                    candidates.append(
                        {
                            "content": extracted,
                            "memory_type": memory_type,
                            "confidence": confidence,
                        }
                    )

        dedup = []
        seen = set()
        for item in candidates:
            key = item["content"].lower().strip()
            if key in seen:
                continue
            seen.add(key)
            dedup.append(item)
        return dedup

    def _normalize_candidate_text(self, memory_type: str, full_match: str, captured: str) -> str:
        if not full_match:
            return ""

        lowered = full_match.lower()
        captured = captured.strip()

        if memory_type == "identity":
            if lowered.startswith("i'm") or lowered.startswith("i am"):
                return f"I am {captured}".strip()

        if memory_type == "semantic":
            if lowered.startswith("i work as"):
                return f"I work as {captured}".strip()
            if lowered.startswith("i study"):
                return f"I study {captured}".strip()
            if lowered.startswith("my job"):
                return f"My job is {captured}".strip()

        if memory_type == "goal":
            if lowered.startswith("i plan to"):
                return f"I plan to {captured}".strip()
            return f"I want to {captured}".strip()

        if memory_type == "belief":
            return f"I feel {captured}".strip()

        return full_match[:1].upper() + full_match[1:]

    def _novelty_score(self, text: str, memory_engine) -> float:
        try:
            if memory_engine.user_memory.count() == 0:
                return 1.0

            result = memory_engine.user_memory.query(query_texts=[text], n_results=1)
            distances = result.get("distances", [[]])
            if not distances or not distances[0]:
                return 1.0

            distance = float(distances[0][0])
            max_similarity = self._clamp(1.0 - (distance / 2.0), 0.0, 1.0)
            return self._clamp(1.0 - max_similarity, 0.0, 1.0)
        except Exception:
            return 0.5

    def _emotional_intensity(self, text: str) -> float:
        lowered = text.lower()
        tokens = re.findall(r"\w+", lowered)
        if not tokens:
            return 0.0

        strong_hits = sum(1 for t in tokens if t in self._STRONG_EMOTION_WORDS)
        emotion_hits = sum(1 for t in tokens if t in self._EMOTION_WORDS)
        exclamations = text.count("!")

        sentiment_magnitude = self._clamp((strong_hits * 1.5 + emotion_hits * 0.7 + exclamations * 0.5) / 6.0, 0.0, 1.0)
        return sentiment_magnitude

    def _identity_relevance(self, text: str, memory_type: str) -> float:
        lowered = text.lower()
        score = 0.0

        if memory_type in {"identity", "goal", "belief"}:
            score += 0.55

        identity_keywords = ["name", "work", "study", "believe", "value", "plan", "goal", "family", "prefer"]
        score += min(0.45, sum(0.12 for word in identity_keywords if word in lowered))
        return self._clamp(score, 0.0, 1.0)

    def _user_specificity(self, text: str) -> float:
        lowered = text.lower()
        pronouns = [" i ", " my ", " me ", " i'm ", " i am "]
        padded = f" {lowered} "
        hits = sum(1 for p in pronouns if p in padded)
        return self._clamp(0.25 + hits * 0.2, 0.0, 1.0)

    def _recurrence_signal(self, text: str, memory_engine) -> float:
        try:
            result = memory_engine.search(text, tier="fast", n_results=5)
            matches = result.get("results", []) if isinstance(result, dict) else []
            if not matches:
                return 0.0

            words = set(re.findall(r"\w+", text.lower()))
            words = {w for w in words if len(w) > 3}
            if not words:
                return 0.0

            overlap_count = 0
            for item in matches:
                match_text = (item.get("text") or "").lower()
                if any(word in match_text for word in words):
                    overlap_count += 1

            return self._clamp(overlap_count / 5.0, 0.0, 1.0)
        except Exception:
            return 0.0

    def _compute_memory_affect(self, user_message: str, emotional_state: dict):
        """
        Compute (valence, arousal) for memory storage based on the current
        emotional_state snapshot and message-level emotional intensity.

        valence:  derived from joy, warmth, stability  (higher = more positive)
        arousal:  derived from intellectual_energy, engagement, emotional intensity

        Returns (valence: float, arousal: float) each in [0.0, 1.0].
        """
        joy       = float(emotional_state.get("joy",                0.5))
        warmth    = float(emotional_state.get("warmth",             0.5))
        stability = float(emotional_state.get("stability",          0.5))
        energy    = float(emotional_state.get("intellectual_energy", 0.5))
        engage    = float(emotional_state.get("engagement",         0.5))

        intensity = self._emotional_intensity(user_message)

        valence = self._clamp(0.40 * joy + 0.35 * warmth + 0.25 * stability, 0.0, 1.0)
        arousal = self._clamp(0.35 * energy + 0.35 * engage + 0.30 * intensity, 0.0, 1.0)
        return round(valence, 4), round(arousal, 4)

    def _compute_trait_deltas(self, raw_text: str, user_message: str) -> Dict[str, float]:
        deltas = {
            "confidence": 0.0,
            "curiosity": 0.0,
            "analytical_depth": 0.0,
            "playfulness": 0.0,
            "emotional_warmth": 0.0,
            "technical_grounding": 0.0,
        }

        structured_hits = sum(1 for marker in self._STRUCTURE_MARKERS if marker in raw_text.lower())
        if structured_hits >= 2:
            deltas["analytical_depth"] += 0.02

        question_marks = user_message.count("?") + raw_text.count("?")
        if question_marks >= 2:
            deltas["curiosity"] += 0.02

        assertive_hits = len(re.findall(r"\b(definitely|clearly|certainly|always|must)\b", raw_text.lower()))
        if assertive_hits >= 1:
            deltas["confidence"] += 0.02

        emotion_hits = len(re.findall(r"\b(understand|support|care|feel|appreciate|sorry)\b", raw_text.lower()))
        if emotion_hits >= 1:
            deltas["emotional_warmth"] += 0.02

        # Technical content detection
        technical_hits = len(re.findall(r"\b(code|api|algorithm|debug|config|system|technical|data|implementation)\b", raw_text.lower()))
        if technical_hits >= 1:
            deltas["technical_grounding"] += 0.02

        # Playfulness detection
        playful_hits = len(re.findall(r"\b(haha|lol|fun|funny|amusing|😊|🙂|😄)\b", raw_text.lower())) + raw_text.count("!")
        if playful_hits >= 2:
            deltas["playfulness"] += 0.01

        return {k: self._clamp(v, -0.03, 0.03) for k, v in deltas.items() if abs(v) > 1e-6}

    def _compute_emotion_deltas(self, raw_text: str, user_message: str) -> Dict[str, float]:
        """Compute emotion state nudges proportional to observed signal strength.

        Deltas scale with actual signal intensity rather than firing a flat step
        whenever a threshold is crossed.
        """
        deltas: Dict[str, float] = {}

        # engagement: longer responses indicate active, engaged generation
        word_count = len(raw_text.split())
        if word_count > 20:
            deltas["engagement"] = self._clamp((word_count / 200) * 0.03, 0.0, 0.03)

        # intellectual_energy: reasoning language signals mental engagement
        reasoning_hits = len(re.findall(r"\b(because|therefore|reason|step|since|thus|hence)\b", raw_text.lower()))
        if reasoning_hits > 0:
            deltas["intellectual_energy"] = self._clamp(reasoning_hits * 0.007, 0.0, 0.03)

        # warmth: supportive / positive vocabulary
        warmth_hits = len(re.findall(r"\b(understand|glad|happy|support|appreciate|love|care)\b", raw_text.lower()))
        if warmth_hits > 0:
            deltas["warmth"] = self._clamp(warmth_hits * 0.007, 0.0, 0.03)

        # stability: low emotional intensity in the user message suggests calm exchange
        emotional_intensity = self._emotional_intensity(user_message)
        if emotional_intensity < 0.3:
            deltas["stability"] = self._clamp((0.3 - emotional_intensity) * 0.05, 0.0, 0.02)

        return {k: v for k, v in deltas.items() if abs(v) > 1e-6}

    def _modulate_text(self, raw_text: str, identity_core: dict, emotional_state: dict, response_mode: dict) -> str:
        """Pass the LLM output through unchanged.

        All vocabulary, hedging, tone, and emoji choices belong to the LLM.
        Post-hoc word replacement is removed to prevent mechanical distortion of
        the model's intent.  Personality and emotional state are injected upstream
        via the system prompt, so no further surgery is needed here.
        """
        return (raw_text or "").strip()

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, float(value)))
