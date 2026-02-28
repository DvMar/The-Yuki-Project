
class CognitiveController:
    """
    Lightweight intent and response controller.
    Rule-based and deterministic for local-only usage.
    """

    def __init__(self, enactive_nexus=None):
        self.enactive_nexus = enactive_nexus
        self.intent_rules = [
            ("memory_related", ["remember", "memory", "recall", "what did i say", "do you remember", "episodic", "semantic"]),
            ("technical", ["error", "bug", "stack trace", "code", "api", "python", "fastapi", "debug", "install", "setup", "config"]),
            ("instruction", ["please", "generate", "write", "create", "build", "make", "do this", "help me", "update"]),
            ("emotional", [
                "feel", "sad", "anxious", "worried", "stress", "lonely", "happy", "overwhelmed", "upset", "angry", "love"
            ]),
            ("philosophical", ["meaning", "purpose", "existence", "conscious", "mind", "soul", "identity", "ethics"]),
            ("meta", ["system prompt", "model", "llm", "temperature", "token", "context", "prompt", "AI"]),
            ("casual", ["hi", "hello", "hey", "how are you", "what's up", "thanks", "ok", "cool"]) 
        ]

    def analyze_input(self, user_message: str) -> dict:
        text = user_message.lower().strip()

        intent = "casual"
        confidence = 0.4

        for label, keywords in self.intent_rules:
            for kw in keywords:
                if kw in text:
                    intent = label
                    confidence = 0.75
                    break
            if intent == label:
                break

        # Response mode defaults
        response_mode = {
            "verbosity": "medium",
            "tone": "neutral"
        }

        if intent == "technical":
            response_mode = {"verbosity": "deep", "tone": "analytical"}
        elif intent == "emotional":
            response_mode = {"verbosity": "medium", "tone": "warm"}
        elif intent == "philosophical":
            response_mode = {"verbosity": "deep", "tone": "analytical"}
        elif intent == "casual":
            response_mode = {"verbosity": "short", "tone": "warm"}
        elif intent == "meta":
            response_mode = {"verbosity": "medium", "tone": "neutral"}
        elif intent == "memory_related":
            response_mode = {"verbosity": "short", "tone": "neutral"}
        elif intent == "instruction":
            response_mode = {"verbosity": "medium", "tone": "neutral"}

        # Memory usage decisions
        use_semantic_memory = intent in {"technical", "emotional", "memory_related", "instruction", "philosophical"}
        use_episodic_memory = intent in {"memory_related", "emotional", "philosophical"}

        control_state = {
            "intent": intent,
            "confidence": float(confidence),
            "use_semantic_memory": bool(use_semantic_memory),
            "use_episodic_memory": bool(use_episodic_memory),
            "response_mode": response_mode
        }

        if self.enactive_nexus is not None:
            try:
                control_state = self.enactive_nexus.apply_controller_priors(control_state)
            except Exception:
                pass

        return control_state
