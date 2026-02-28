import httpx
import os
from openai import AsyncOpenAI
import logging
import time
import asyncio
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

from utils.logging import estimate_tokens, log_llm_call

logger = logging.getLogger(__name__)

# Import sampler profiles — no circular dependency since llama_cpp_backend
# does not import from llama_client.
from llm.llama_cpp_backend import (
    SamplerProfile,
    PROFILE_REFLECTION,
    PROFILE_STRUCTURED,
)


@dataclass
class LLMRequest:
    """Represents a request for LLM processing."""
    messages: List[Dict[str, str]]
    temperature: float = 0.5
    max_tokens: int = 2048
    request_type: str = "chat"  # "chat", "consolidation", "reflection", etc.
    priority: int = 1  # Higher = more important


@dataclass 
class BatchedConsolidationRequest:
    """Request for batched fact/entity/relationship extraction."""
    text: str
    context: str = ""
    extract_facts: bool = True
    extract_entities: bool = True
    extract_relationships: bool = True

class LLMClient:
    def __init__(
        self,
        base_url="http://localhost:8080/v1",
        api_key="sk-no-key-required",
        completion_base_url="http://localhost:8080",
        max_concurrent_requests=4,  # Optimize for Gemma 4B
        request_timeout=30.0,
        connection_pool_size=10
    ):
        # Enhanced client configuration
        self.client = AsyncOpenAI(
            base_url=base_url, 
            api_key=api_key,
            timeout=request_timeout,
            max_retries=2
        )
        self.completion_base_url = completion_base_url.rstrip("/")
        
        # Connection management
        self.max_concurrent_requests = max_concurrent_requests
        self.semaphore = asyncio.Semaphore(max_concurrent_requests)
        
        # Performance tracking
        self.request_stats = {
            "total_requests": 0,
            "failed_requests": 0,
            "avg_response_time": 0.0,
            "batched_requests": 0
        }
        
        # Request queue for batching
        self.pending_consolidations = []
        self.batch_timer = None
        self.batch_delay = 0.5  # Wait 500ms for batch opportunities

    async def chat_completion(self, messages, temperature=0.5, max_tokens=2048, grammar_path=None,
                              profile: Optional[SamplerProfile] = None):
        """Optimized chat completion with connection pooling.

        grammar_path: optional path to a .gbnf grammar file.  When provided the
        grammar string is forwarded to llama-server via extra_body, which
        guarantees the output matches the grammar (llama-server v3+).

        profile: optional SamplerProfile that overrides temperature and adds
        additional sampling parameters via extra_body.
        """
        async with self.semaphore:  # Limit concurrent requests
            start = time.perf_counter()
            token_estimate = estimate_tokens("\n".join(str(m.get("content", "")) for m in messages))

            # Resolve effective temperature and extra sampling params
            effective_temperature = profile.temperature if profile is not None else temperature
            extra: dict = {}
            if profile is not None:
                extra.update(profile.to_extra_body())

            # Read grammar content if supplied
            if grammar_path:
                try:
                    with open(grammar_path, "r", encoding="utf-8") as _f:
                        extra["grammar"] = _f.read()
                except Exception as _e:
                    logger.warning(f"Could not read grammar {grammar_path}: {_e}")
            
            try:
                self.request_stats["total_requests"] += 1
                
                response = await self.client.chat.completions.create(
                    model="local-model",
                    messages=messages,
                    temperature=effective_temperature,
                    max_tokens=max_tokens,
                    extra_body=extra if extra else None,
                )
                
                duration = (time.perf_counter() - start) * 1000
                self._update_stats(duration)
                
                log_llm_call(
                    endpoint="/v1/chat/completions",
                    duration_ms=duration,
                    token_estimate=token_estimate,
                    streaming=False,
                )
                return response.choices[0].message.content
                
            except Exception as e:
                self.request_stats["failed_requests"] += 1
                logger.error(f"Error in LLM chat completion: {e}")
                return f"Error: Could not connect to the local AI server."

    async def chat_completion_stream(self, messages, temperature=0.5, max_tokens=2048,
                                     profile: Optional[SamplerProfile] = None):
        """Optimized streaming with connection pooling.

        profile: optional SamplerProfile that overrides temperature and adds
        additional sampling parameters via extra_body.
        """
        async with self.semaphore:
            start = time.perf_counter()
            token_estimate = estimate_tokens("\n".join(str(m.get("content", "")) for m in messages))

            effective_temperature = profile.temperature if profile is not None else temperature
            extra: dict = profile.to_extra_body() if profile is not None else {}

            try:
                self.request_stats["total_requests"] += 1

                response = await self.client.chat.completions.create(
                    model="local-model",
                    messages=messages,
                    temperature=effective_temperature,
                    max_tokens=max_tokens,
                    stream=True,
                    extra_body=extra if extra else None,
                )
                
                # Stream tokens
                async for chunk in response:
                    if chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                
                duration = (time.perf_counter() - start) * 1000
                self._update_stats(duration)
                
            except Exception as e:
                self.request_stats["failed_requests"] += 1
                logger.error(f"Streaming error: {e}")
                yield f"\n[Streaming Error: {e}]"
            finally:
                log_llm_call(
                    endpoint="/v1/chat/completions",
                    duration_ms=(time.perf_counter() - start) * 1000,
                    token_estimate=token_estimate,
                    streaming=True,
                )

    async def completion(self, prompt: str, temperature=0.6, max_tokens=300, stop=None, grammar_path=None):
        """Raw completion call against llama-server /completion endpoint.
        
        grammar_path: optional path to a .gbnf grammar file that is forwarded
        to llama-server in the payload, guaranteeing grammar-compliant output.
        """
        if not prompt:
            return ""

        start = time.perf_counter()

        payload = {
            "prompt": prompt,
            "temperature": temperature,
            "n_predict": max_tokens,
            "stream": False,
        }
        if stop:
            payload["stop"] = stop
        if grammar_path:
            try:
                with open(grammar_path, "r", encoding="utf-8") as _f:
                    payload["grammar"] = _f.read()
            except Exception as _e:
                logger.warning(f"Could not read grammar {grammar_path}: {_e}")

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.completion_base_url}/completion",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
            log_llm_call(
                endpoint=f"{self.completion_base_url}/completion",
                duration_ms=(time.perf_counter() - start) * 1000,
                token_estimate=estimate_tokens(prompt),
                streaming=False,
            )
        except Exception as e:
            logger.error(f"Error in LLM completion: {e}", exc_info=True)
            logger.debug(f"Failed completion request to {self.completion_base_url}/completion with prompt length: {len(prompt)}")
            return ""

        if isinstance(data, dict):
            if "content" in data and isinstance(data["content"], str):
                return data["content"]
            if "choices" in data and data["choices"]:
                choice = data["choices"][0]
                if isinstance(choice, dict) and isinstance(choice.get("text"), str):
                    return choice["text"]
        return ""
            
    async def get_reflection(self, last_user_msg, last_ai_msg, current_time):
        """
        Get structured trait + emotional + self-model delta reflection with subject-object mapping.
        Returns dict with trait_deltas, emotional_deltas, self_model_deltas, confidence, user_fact, ai_self_update.
        """
        user_reflection_text = (last_user_msg or "").strip().replace("\n", " ")[:320]
        ai_reflection_text = (last_ai_msg or "").strip().replace("\n", " ")[:420]
        reflection_max_tokens = max(64, int(os.getenv("REFLECTION_MAX_TOKENS", "192")))

        prompt = f"""
Current Time: {current_time}
    User said: "{user_reflection_text}"
    You (Yuki the AI) responded: "{ai_reflection_text}"

Subject-Object Mapping Rules (CRITICAL for user_fact extraction):
- "I" / "me" from the user refers to the HUMAN USER (person talking to Yuki).
- "you" from the user refers to the AI (Yuki).
- The AI's name is "Yuki" - NEVER extract "Yuki" as the user's name.
- When extracting user_fact, extract information FROM the human's perspective, not from Yuki's.
- Do NOT confuse the AI's identity/statements with user facts.

Analyze this interaction and determine:
1. Subtle shifts in personality traits and emotional state
2. Optional: Shifts in cognitive style or expressive bias (self-model)

Return ONLY a JSON object with trait_deltas, emotional_deltas, self_model_deltas (optional), confidence, user_fact, ai_self_update.

Output ONLY the raw JSON. Do not include markdown code blocks or conversational text. Ensure every string value is properly escaped.

IMPORTANT Guidelines:
- user_fact: Only PERMANENT, MEANINGFUL facts about the HUMAN USER (name, location, preferences, goals, profession). Do NOT include:
  * The AI's name, identity, or statements about Yuki
  * Greetings, casual phrases, or vague observations
  * Anything the AI said or properties of the AI
- ai_self_update: Only SIGNIFICANT realizations about Yuki's design, capabilities, or operational changes. Do NOT include generic conversational responses.
- self_model_deltas: Only include if interaction reveals something about Yuki's cognitive style or expressive tendencies. Paths use dot notation (e.g. "cognitive_tendencies.systems_orientation", "style_bias.depth_bias"). Very conservative - most interactions should have 0-1 self-model deltas.
- If the user discusses the AI's programming, system, or capabilities, it belongs in ai_self_update or trait_deltas, NEVER in user_fact.
- Leave user_fact and ai_self_update EMPTY ("") unless there's truly valuable information to record.

Available traits:
- confidence, curiosity, analytical_depth, playfulness, emotional_warmth, technical_grounding

Available emotional dimensions:
- stability, engagement, intellectual_energy, warmth

Available self-model paths:
- cognitive_tendencies: structural_thinking, systems_orientation, analytical_bias, expressive_bias
- style_bias: verbosity, depth_bias, warmth_expression

Example output:
{{
  "trait_deltas": {{"curiosity": 0.05, "confidence": -0.02}},
  "emotional_deltas": {{"engagement": 0.03, "warmth": 0.02}},
  "self_model_deltas": {{"cognitive_tendencies.systems_orientation": 0.03}},
  "confidence": 0.72,
  "user_fact": "User lives in London and works as a software engineer",
  "ai_self_update": ""
}}

Only include deltas that changed. Be conservative. Most interactions should have 0-2 trait deltas, 0-1 self-model deltas.
For casual conversations without meaningful facts, return:
{{"trait_deltas": {{}}, "emotional_deltas": {{}}, "self_model_deltas": {{}}, "confidence": 0.5, "user_fact": "", "ai_self_update": ""}}
"""

        messages = [
            {"role": "system", "content": "You are a structured cognition module. Respond only with valid JSON."},
            {"role": "user", "content": prompt}
        ]

        # Use grammar-constrained generation when the grammar file is present
        _grammar_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "models", "grammars", "json_reflection.gbnf"
        )
        if not os.path.exists(_grammar_path):
            _grammar_path = None

        _empty = {
            "trait_deltas": {},
            "emotional_deltas": {},
            "self_model_deltas": {},
            "confidence": 0.0,
            "user_fact": "",
            "ai_self_update": "",
        }

        try:
            response = await self.chat_completion(
                messages,
                temperature=0.2,
                max_tokens=reflection_max_tokens,
                grammar_path=_grammar_path,
                profile=PROFILE_REFLECTION,
            )

            # When grammar is active the output is guaranteed valid JSON.
            # When grammar is unavailable we fall back to a simple extract.
            import json as _json
            raw = response.strip()
            if _grammar_path is None:
                # Best-effort extraction: find the outermost {...} block
                import re as _re
                _m = _re.search(r"\{.*\}", raw, _re.DOTALL)
                raw = _m.group(0) if _m else raw
                # Remove trailing commas (common LLM mistake)
                raw = _re.sub(r',(\s*[}\]])', r'\1', raw)

            payload = _json.loads(raw)

            def _clamp(d):
                if not isinstance(d, dict):
                    return {}
                return {
                    k: max(-0.1, min(0.1, float(v)))
                    for k, v in d.items()
                    if isinstance(v, (int, float))
                }

            confidence = payload.get("confidence", 0.0)
            if not isinstance(confidence, (int, float)):
                confidence = 0.0
            confidence = max(0.0, min(1.0, float(confidence)))

            user_fact = payload.get("user_fact", "")
            if not isinstance(user_fact, str):
                user_fact = ""
            ai_self_update = payload.get("ai_self_update", "")
            if not isinstance(ai_self_update, str):
                ai_self_update = ""

            return {
                "trait_deltas": _clamp(payload.get("trait_deltas")),
                "emotional_deltas": _clamp(payload.get("emotional_deltas")),
                "self_model_deltas": _clamp(payload.get("self_model_deltas")),
                "confidence": confidence,
                "user_fact": user_fact.strip(),
                "ai_self_update": ai_self_update.strip(),
            }

        except Exception as e:
            logger.debug(f"Reflection parse error: {e}")
            return _empty
    
    async def generate_episodic_summary(self, exchanges, metabolic_context=None):
        """Generate a compact summary of recent exchanges for episodic memory."""
        if not exchanges:
            return None
        
        # Build conversation snippet
        conversation = ""
        for ex in exchanges[-10:]:  # Last 10 exchanges
            conversation += f"User: {ex['user']}\n"
            conversation += f"Assistant: {ex['assistant']}\n\n"
        
        metabolic_block = ""
        if isinstance(metabolic_context, dict) and metabolic_context:
            import json as _json
            metabolic_block = f"""

    Metabolic context (historical state signatures):
    {_json.dumps(metabolic_context, ensure_ascii=False, indent=2)[:1200]}
    """

        prompt = f"""Summarize this conversation segment into 2-3 sentences capturing both interaction content and inner metabolic trajectory.

    Rules:
    - Write in first-person organismic voice ("I felt...", "I was quieter...", "I opened up...").
    - Include at least one causal temporal link when context supports it (e.g., prior fatigue + low openness -> quieter, more reflective stance later).
    - Never use assistant/system/programming language.
    - Never mention code, modules, API, backend, telemetry, or implementation terms.
    - Keep concrete, felt, and concise.

{conversation}
    {metabolic_block}

Summary:"""

        messages = [
            {"role": "system", "content": "You are writing autobiographical memory in an organismic first-person voice. Be concise, causal, and experiential."},
            {"role": "user", "content": prompt}
        ]
        
        try:
            response = await self.chat_completion(
                messages,
                temperature=0.3,
                max_tokens=150
            )
            return response.strip() if response else None
        except Exception as e:
            logger.error(f"Episode summarization error: {e}")
            return None

    # ====== NEW: PERFORMANCE OPTIMIZATIONS ======

    async def batched_consolidation(self, batch_requests: List[BatchedConsolidationRequest]) -> Dict[str, Any]:
        """
        Process multiple consolidation requests in a single LLM call.
        Reduces LLM overhead by batching fact/entity/relationship extraction.
        """
        if not batch_requests:
            return {"facts": [], "entities": [], "relationships": []}

        self.request_stats["batched_requests"] += 1
        
        # Resolve grammar file (guarantees valid JSON output on llama-server v3+)
        _grammar_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "models", "grammars", "json_extraction.gbnf"
        )
        if not os.path.exists(_grammar_path):
            _grammar_path = None

        # Build batched prompt
        batch_content = []
        for i, req in enumerate(batch_requests):
            batch_content.append(f"Text {i+1}:")
            batch_content.append(f"Content: {req.text}")
            if req.context:
                batch_content.append(f"Context: {req.context}")
            batch_content.append("")

        prompt = f"""Extract facts, entities, and relationships from the following texts. Return JSON format only.

{chr(10).join(batch_content)}

Return format:
{{
  "results": [
    {{
      "text_index": 1,
      "facts": ["fact1", "fact2"],
      "entities": [
        {{"name": "EntityName", "type": "person", "confidence": 0.9}}
      ],
      "relationships": [
        {{"subject": "A", "predicate": "knows", "object": "B", "confidence": 0.8}}
      ]
    }}
  ]
}}"""

        messages = [
            {"role": "system", "content": "You are a structured data extraction module. Return only valid JSON."},
            {"role": "user", "content": prompt}
        ]

        try:
            response = await self.chat_completion(
                messages, temperature=0.2, max_tokens=1024, grammar_path=_grammar_path,
                profile=PROFILE_STRUCTURED,
            )

            # Parse JSON response
            import json
            try:
                result = json.loads(response.strip())
                return result
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse batched consolidation JSON: {response[:200]}")
                return {"results": []}

        except Exception as e:
            logger.error(f"Batched consolidation error: {e}")
            return {"results": []}

    async def parallel_operations(self, operations: List[Tuple[str, Dict]]) -> Dict[str, Any]:
        """
        Execute multiple LLM operations in parallel with connection limits.
        
        Args:
            operations: List of (operation_type, params) tuples
                       operation_type: "chat", "consolidation", "reflection", etc.
        """
        if not operations:
            return {}

        async def execute_operation(op_type: str, params: Dict) -> Tuple[str, Any]:
            try:
                if op_type == "chat":
                    result = await self.chat_completion(**params)
                elif op_type == "consolidation":
                    result = await self.batched_consolidation([BatchedConsolidationRequest(**params)])
                elif op_type == "reflection":
                    result = await self.get_reflection(**params)
                else:
                    result = f"Unknown operation type: {op_type}"
                
                return op_type, result
            except Exception as e:
                logger.error(f"Parallel operation {op_type} failed: {e}")
                return op_type, None

        # Execute all operations in parallel (limited by semaphore)
        tasks = [execute_operation(op_type, params) for op_type, params in operations]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Organize results — asyncio.gather(return_exceptions=True) may put raw
        # Exception objects (not tuples) in the list; guard against that.
        result_dict = {}
        for i, item in enumerate(results):
            if isinstance(item, Exception):
                logger.error(f"Parallel operation {i} raised: {item}")
                result_dict[f"op_{i}"] = None
            else:
                op_type, result = item
                result_dict[f"{op_type}_{i}"] = result

        return result_dict

    def _update_stats(self, duration_ms: float):
        """Update performance statistics."""
        # Update average response time (exponential moving average)
        if self.request_stats["avg_response_time"] == 0:
            self.request_stats["avg_response_time"] = duration_ms
        else:
            alpha = 0.1  # Smoothing factor
            current_avg = self.request_stats["avg_response_time"]
            self.request_stats["avg_response_time"] = alpha * duration_ms + (1 - alpha) * current_avg

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics."""
        total = max(1, self.request_stats["total_requests"])
        return {
            "total_requests": self.request_stats["total_requests"],
            "failed_requests": self.request_stats["failed_requests"],
            "success_rate": ((total - self.request_stats["failed_requests"]) / total) * 100,
            "avg_response_time_ms": round(self.request_stats["avg_response_time"], 2),
            "batched_requests": self.request_stats["batched_requests"],
            "batch_efficiency": (self.request_stats["batched_requests"] / total) * 100,
            "concurrent_limit": self.max_concurrent_requests
        }
