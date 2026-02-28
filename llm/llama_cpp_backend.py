"""
In-process llama.cpp backend for The Yuki Project.

Activated when the environment variable LLAMA_CPP_MODEL is set to the path
of a GGUF model file. When active, this backend replaces all HTTP calls to
llama-server with direct llama_cpp calls inside the Python process.

Key benefits over the HTTP backend:
- Grammar-constrained generation (guaranteed valid JSON, no regex repair)
- In-process embeddings via Llama.embed()
- Per-request sampler control (temperature, top_k, top_p, min_p, etc.)
- Zero network overhead for reflection and consolidation calls
- Speculative decoding support (future: LLAMA_CPP_DRAFT_MODEL)

Usage:
    export LLAMA_CPP_MODEL=/path/to/model.gguf
    # HTTP backend is used when this var is unset.
"""

import asyncio
import inspect
import json
import logging
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import ctypes

from llama_cpp import Llama, LlamaGrammar, LlamaDraftModel
import llama_cpp as _llama_cpp_lib

import numpy as np

from utils.logging import estimate_tokens, log_llm_call

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Suppress specific noisy C-level llama.cpp log messages that bypass verbose=False.
# These messages are printed to stderr directly from the native library on every
# embed() call and would overflow the terminal.  We install a one-time log
# callback that filters them out while passing everything else through unchanged.
# ---------------------------------------------------------------------------
_SUPPRESSED_SUBSTRINGS = (
    b"embeddings required but some input tokens were not marked as outputs",
    b"llama_context:",
    b"llama_kv_cache_unified",
    b"create_memory:",
    b"set_abort_callback:",
    b"graph_reserve:",
    b"ggml_gallocr_reserve_n:",
    b"ggml_gallocr_needs_realloc:",
    b"ggml_gallocr_alloc_graph:",
    b"ggml_backend_sched_alloc_splits:",
    b"check_node_graph_compatibility",
    b"output_reserve:",
    b"decode: cannot decode batches",
    b"update_cuda_graph_executable",
)

@ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p)
def _llama_log_filter(level: int, message: bytes, user_data: ctypes.c_void_p) -> None:
    if message and any(s in message for s in _SUPPRESSED_SUBSTRINGS):
        return  # drop this line
    if message:
        import sys
        sys.stderr.write(message.decode("utf-8", errors="replace"))

try:
    _llama_cpp_lib.llama_log_set(_llama_log_filter, ctypes.c_void_p(0))
except Exception:
    pass  # non-fatal: if it fails the messages just keep printing

# Shared thread pool for blocking llama.cpp calls to avoid starving the event loop.
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="llama_cpp")

# Global mutex: llama.cpp is NOT thread-safe for concurrent GPU calls — even across
# separate Llama() instances they share the CUDA device state.  Every path that
# calls into the native library (chat, stream, embed, ChromaDB EF) must hold this
# lock before dispatching to the C library.
_LLAMA_INFERENCE_LOCK = threading.Lock()


def _locked_embed(model, text: str) -> list:
    """Helper: call model.embed() under the global inference lock."""
    with _LLAMA_INFERENCE_LOCK:
        return list(model.embed(text))


# ---------------------------------------------------------------------------
# Sampler profiles (Step 8)
# ---------------------------------------------------------------------------

@dataclass
class SamplerProfile:
    """
    Encapsulates all sampler hyper-parameters for a single inference call.

    Pass an instance as ``profile=`` to ``chat_completion`` /
    ``chat_completion_stream`` to override the default settings.  When a
    profile is provided the legacy ``temperature`` parameter is ignored
    (the profile's own ``temperature`` field takes precedence).

    Attributes:
        temperature:    Softmax temperature.  Lower → more deterministic.
        top_p:          Nucleus sampling threshold (0.0–1.0).
        top_k:          Keep only the top-k tokens.  0 = disabled.
        min_p:          Minimum probability floor (llama.cpp specific).
        repeat_penalty: Token repetition penalty (1.0 = no penalty).
        mirostat_mode:  0 = off, 1 = Mirostat v1, 2 = Mirostat v2.
        mirostat_tau:   Mirostat target entropy (typically 3.0–8.0).
        mirostat_eta:   Mirostat learning rate (typically 0.05–0.2).
        dry_multiplier: DRY repetition-penalty multiplier (0.0 = off).
    """
    temperature:    float = 0.7
    top_p:          float = 0.9
    top_k:          int   = 40
    min_p:          float = 0.05
    repeat_penalty: float = 1.0
    mirostat_mode:  int   = 0
    mirostat_tau:   float = 5.0
    mirostat_eta:   float = 0.1
    dry_multiplier: float = 0.0

    def to_kwargs(self) -> Dict[str, Any]:
        """Return a dict of sampling kwargs accepted by create_chat_completion."""
        kwargs: Dict[str, Any] = {
            "temperature":    self.temperature,
            "top_p":          self.top_p,
            "top_k":          self.top_k,
            "min_p":          self.min_p,
            "repeat_penalty": self.repeat_penalty,
            "mirostat_mode":  self.mirostat_mode,
            "mirostat_tau":   self.mirostat_tau,
            "mirostat_eta":   self.mirostat_eta,
        }
        if self.dry_multiplier > 0.0:
            kwargs["dry_multiplier"] = self.dry_multiplier
        return kwargs

    def to_extra_body(self) -> Dict[str, Any]:
        """Return extra_body dict suitable for the OpenAI-compatible HTTP API."""
        body: Dict[str, Any] = {
            "top_k":          self.top_k,
            "min_p":          self.min_p,
            "repeat_penalty": self.repeat_penalty,
        }
        if self.mirostat_mode:
            body["mirostat"]     = self.mirostat_mode
            body["mirostat_tau"] = self.mirostat_tau
            body["mirostat_eta"] = self.mirostat_eta
        if self.dry_multiplier > 0.0:
            body["dry_multiplier"] = self.dry_multiplier
        return body


# Pre-built profiles — import from llm or llm.llama_cpp_backend
PROFILE_CHAT = SamplerProfile(
    temperature=0.7, top_p=0.9, top_k=40, min_p=0.05, repeat_penalty=1.1
)
"""Default conversational profile: warm and varied but not chaotic."""

PROFILE_REFLECTION = SamplerProfile(
    temperature=0.2, top_p=0.95, top_k=10, min_p=0.0, repeat_penalty=1.2
)
"""Structured introspection: near-greedy for consistent JSON output."""

PROFILE_CREATIVE = SamplerProfile(
    temperature=0.9, top_p=0.95, top_k=80, min_p=0.03,
    repeat_penalty=1.05, mirostat_mode=2, mirostat_tau=5.0, mirostat_eta=0.1
)
"""High-entropy creative generation via Mirostat v2."""

PROFILE_STRUCTURED = SamplerProfile(
    temperature=0.1, top_p=0.99, top_k=5, min_p=0.0, repeat_penalty=1.05
)
"""Fact extraction / classification: maximum determinism."""


# ---------------------------------------------------------------------------
# Draft model for speculative decoding (Step 10)
# ---------------------------------------------------------------------------

class _LlamaGGUFDraftModel(LlamaDraftModel):
    """
    Concrete LlamaDraftModel that wraps a small GGUF draft model.

    The draft model should be a faster/smaller variant of the main model
    (same tokenizer, smaller parameter count) so that speculation is cheap.

    During each draft step the model runs *greedily* (temp=0, top_k=1) to
    propose candidate tokens.  The main model then verifies them in a single
    forward pass via llama.cpp's built-in speculative-decode path.
    """

    def __init__(
        self,
        model_path: str,
        n_gpu_layers: int = 0,
        n_threads: Optional[int] = None,
        num_draft_tokens: int = 5,
    ) -> None:
        self._llama = Llama(
            model_path=model_path,
            n_ctx=512,            # Small context is enough for draft lookahead
            n_gpu_layers=n_gpu_layers,
            n_threads=n_threads or os.cpu_count(),
            verbose=False,
            embedding=False,
        )
        self._num_draft = num_draft_tokens
        self._eos = self._llama.token_eos()

    def __call__(
        self,
        input_ids: "np.ndarray",
        /,
        **kwargs: Any,
    ) -> "np.ndarray":
        """Generate *num_draft_tokens* candidate tokens for speculative decode."""
        n_draft = kwargs.get("num_draft_tokens", self._num_draft)
        token_list: List[int] = list(input_ids.flatten())

        self._llama.reset()
        self._llama.eval(token_list)

        draft: List[int] = []
        for _ in range(n_draft):
            tok = self._llama.sample(top_k=1, temp=0.0)
            if tok == self._eos:
                break
            draft.append(tok)
            self._llama.eval([tok])

        return np.array(draft, dtype=np.intc)


class LlmCppBackend:
    """
    Drop-in replacement for LLMClient that uses llama_cpp in-process.

    The public async interface is identical to LLMClient so all callers
    (api/context.py, cognition/*.py, memory/*.py) require zero changes.
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        n_ctx: int = 32768,  # Match Gemma 3 4B training context (131K is too large for RTX5060)
        n_gpu_layers: int = 0,
        n_threads: Optional[int] = None,
        max_concurrent_requests: int = 1,
        embed_model_path: Optional[str] = None,
        draft_model_path: Optional[str] = None,
    ):
        self.model_path = model_path or os.environ.get("LLAMA_CPP_MODEL", "")
        self.n_ctx = int(n_ctx)
        if not self.model_path:
            raise ValueError(
                "LlmCppBackend requires LLAMA_CPP_MODEL env var or model_path argument."
            )

        # ------------------------------------------------------------------
        # Optional: load a draft model for speculative decoding (Step 10)
        # ------------------------------------------------------------------
        self._draft_model: Optional[_LlamaGGUFDraftModel] = None
        _draft_path = draft_model_path or os.environ.get("LLAMA_CPP_DRAFT_MODEL", "")
        if _draft_path and os.path.isfile(_draft_path):
            logger.info(f"Loading speculative draft model: {_draft_path}")
            try:
                self._draft_model = _LlamaGGUFDraftModel(
                    model_path=_draft_path,
                    n_gpu_layers=n_gpu_layers,
                    n_threads=n_threads or os.cpu_count(),
                )
                logger.info("Draft model loaded — speculative decoding enabled")
            except Exception as _e:
                logger.warning(f"Draft model load failed: {_e}. Continuing without speculative decode.")
                self._draft_model = None

        logger.info(f"Loading llama.cpp model: {self.model_path}")
        load_start = time.perf_counter()

        self._model = Llama(
            model_path=self.model_path,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            n_threads=n_threads or os.cpu_count(),
            verbose=False,
            flash_attn=True,            # Match --flash-attn on from llama-server; ~2-3 GB VRAM saving at 32K ctx
            swa_full=False,             # Use windowed KV cache for SWA layers (Gemma 3: 1024-token window, not 32K)
            embedding=False,
            **({"draft_model": self._draft_model} if self._draft_model is not None else {}),
        )

        load_ms = (time.perf_counter() - load_start) * 1000
        logger.info(f"Chat model loaded in {load_ms:.0f}ms")

        # ------------------------------------------------------------------
        # Optional: load a dedicated embedding model (Step 6)
        # ------------------------------------------------------------------
        self._embed_model: Optional[Llama] = None
        _embed_path = embed_model_path or os.environ.get("LLAMA_CPP_EMBED_MODEL", "")
        if _embed_path and os.path.isfile(_embed_path):
            logger.info(f"Loading llama.cpp embed model: {_embed_path}")
            _embed_start = time.perf_counter()
            try:
                self._embed_model = Llama(
                    model_path=_embed_path,
                    n_ctx=512,              # Nomic-embed and similar use 512-token windows
                    n_batch=512,
                    n_gpu_layers=n_gpu_layers,
                    n_threads=n_threads or os.cpu_count(),
                    verbose=False,
                    embedding=True,         # Must be True for embedding models
                )
                logger.info(
                    f"Embed model loaded in {(time.perf_counter() - _embed_start) * 1000:.0f}ms"
                )
            except Exception as _e:
                logger.warning(f"Could not load embed model {_embed_path}: {_e}. "
                               "Falling back to sentence-transformers.")
                self._embed_model = None

        self.max_concurrent_requests = max(1, int(max_concurrent_requests))
        self.semaphore = asyncio.Semaphore(self.max_concurrent_requests)

        self.request_stats: Dict[str, Any] = {
            "total_requests": 0,
            "failed_requests": 0,
            "avg_response_time": 0.0,
            "batched_requests": 0,
        }

        self._request_seq = 0
        self._debug_enabled = os.getenv("LLAMA_CPP_DEBUG", "false").strip().lower() in {"1", "true", "yes", "y"}
        self._last_error_kind: str = ""
        self._last_error_at: float = 0.0
        self._reflection_fail_streak: int = 0
        self._reflection_cooldown_until: float = 0.0
        self._reflection_cooldown_base_seconds: int = int(os.getenv("REFLECTION_BACKOFF_SECONDS", "90"))
        self._reflection_max_tokens: int = int(os.getenv("REFLECTION_MAX_TOKENS", "192"))

    def _next_request_id(self, prefix: str) -> str:
        self._request_seq += 1
        return f"{prefix}-{self._request_seq}"

    def _infer_caller(self) -> str:
        try:
            this_file = os.path.abspath(__file__)
            for frame in inspect.stack()[2:14]:
                file_name = os.path.abspath(frame.filename)
                if file_name == this_file:
                    continue
                if "\\lib\\asyncio\\" in file_name.lower() or "/lib/asyncio/" in file_name.lower():
                    continue
                return f"{os.path.basename(file_name)}:{frame.function}:{frame.lineno}"
        except Exception:
            pass
        return "unknown"

    def _debug(self, message: str) -> None:
        if self._debug_enabled:
            logger.info(f"[LLAMA_DEBUG] {message}")
            print(f"[LLAMA_DEBUG] {message}")

    def _effective_max_tokens(self, token_estimate: int, requested_max_tokens: int) -> int:
        safety_margin = 256
        available = max(32, self.n_ctx - int(token_estimate) - safety_margin)
        return max(32, min(int(requested_max_tokens), available))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_grammar(self, grammar_path: Optional[str]) -> Optional[LlamaGrammar]:
        """Load a LlamaGrammar from a .gbnf file, returning None on failure."""
        if not grammar_path:
            return None
        try:
            return LlamaGrammar.from_file(grammar_path)
        except Exception as e:
            logger.warning(f"Could not load grammar {grammar_path}: {e}")
            return None

    def _update_stats(self, duration_ms: float) -> None:
        if self.request_stats["avg_response_time"] == 0:
            self.request_stats["avg_response_time"] = duration_ms
        else:
            alpha = 0.1
            self.request_stats["avg_response_time"] = (
                alpha * duration_ms + (1 - alpha) * self.request_stats["avg_response_time"]
            )

    # ------------------------------------------------------------------
    # Public async interface (mirrors LLMClient)
    # ------------------------------------------------------------------

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.5,
        max_tokens: int = 2048,
        grammar_path: Optional[str] = None,
        profile: Optional["SamplerProfile"] = None,
    ) -> str:
        """Non-streaming chat completion. Returns the assistant's reply as a string.

        If *profile* is supplied it takes full control of all sampling
        parameters and the legacy *temperature* argument is ignored.
        """
        request_id = self._next_request_id("chat")
        caller = self._infer_caller()
        async with self.semaphore:
            start = time.perf_counter()
            token_estimate = estimate_tokens(
                "\n".join(str(m.get("content", "")) for m in messages)
            )
            effective_max_tokens = self._effective_max_tokens(token_estimate, max_tokens)
            grammar = self._load_grammar(grammar_path)
            sampler_kwargs = profile.to_kwargs() if profile is not None else {"temperature": temperature}
            lock_wait_ms = 0.0

            self._debug(
                f"{request_id} start caller={caller} msg_count={len(messages)} requested_max_tokens={max_tokens} "
                f"effective_max_tokens={effective_max_tokens} token_estimate={token_estimate} n_ctx={self.n_ctx} "
                f"grammar={'yes' if grammar is not None else 'no'} profile={'yes' if profile is not None else 'no'}"
            )

            if effective_max_tokens < int(max_tokens):
                logger.warning(
                    "chat_completion max_tokens clamped: requested=%s effective=%s token_estimate=%s n_ctx=%s caller=%s",
                    max_tokens,
                    effective_max_tokens,
                    token_estimate,
                    self.n_ctx,
                    caller,
                )

            def _run() -> str:
                nonlocal lock_wait_ms
                lock_wait_start = time.perf_counter()
                with _LLAMA_INFERENCE_LOCK:
                    lock_wait_ms = (time.perf_counter() - lock_wait_start) * 1000
                    response = self._model.create_chat_completion(
                        messages=messages,
                        max_tokens=effective_max_tokens,
                        grammar=grammar,
                        stream=False,
                        **sampler_kwargs,
                    )
                return response["choices"][0]["message"]["content"]

            try:
                self.request_stats["total_requests"] += 1
                loop = asyncio.get_event_loop()
                result: str = await loop.run_in_executor(_EXECUTOR, _run)

                duration = (time.perf_counter() - start) * 1000
                self._update_stats(duration)
                log_llm_call(
                    endpoint="llama_cpp/chat",
                    duration_ms=duration,
                    token_estimate=token_estimate,
                    streaming=False,
                )
                self._debug(
                    f"{request_id} ok caller={caller} duration_ms={duration:.1f} lock_wait_ms={lock_wait_ms:.1f}"
                )
                return result

            except Exception as e:
                self.request_stats["failed_requests"] += 1
                err_text = str(e).lower()
                self._last_error_kind = "access_violation" if "access violation" in err_text else "chat_error"
                self._last_error_at = time.time()
                logger.error(
                    "LlmCppBackend chat_completion error: %s | request_id=%s caller=%s msg_count=%s max_tokens=%s token_estimate=%s",
                    e,
                    request_id,
                    caller,
                    len(messages),
                    effective_max_tokens,
                    token_estimate,
                    exc_info=True,
                )
                print(
                    f"⚠️ [LLM ERROR] chat_completion request_id={request_id} caller={caller} "
                    f"msg_count={len(messages)} max_tokens={effective_max_tokens} token_estimate={token_estimate} n_ctx={self.n_ctx}"
                )
                return "Error: llama.cpp inference failed."

    async def chat_completion_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.5,
        max_tokens: int = 2048,
        grammar_path: Optional[str] = None,
        profile: Optional["SamplerProfile"] = None,
    ) -> AsyncIterator[str]:
        """Streaming chat completion — yields token strings as they arrive.

        If *profile* is supplied it takes full control of all sampling
        parameters and the legacy *temperature* argument is ignored.
        """
        async with self.semaphore:
            start = time.perf_counter()
            token_estimate = estimate_tokens(
                "\n".join(str(m.get("content", "")) for m in messages)
            )
            grammar = self._load_grammar(grammar_path)
            sampler_kwargs = profile.to_kwargs() if profile is not None else {"temperature": temperature}
            loop = asyncio.get_event_loop()
            queue: asyncio.Queue = asyncio.Queue()

            def _produce() -> None:
                try:
                    with _LLAMA_INFERENCE_LOCK:
                        stream = self._model.create_chat_completion(
                            messages=messages,
                            max_tokens=max_tokens,
                            grammar=grammar,
                            stream=True,
                            **sampler_kwargs,
                        )
                        for chunk in stream:
                            delta = chunk["choices"][0]["delta"].get("content", "")
                            if delta:
                                loop.call_soon_threadsafe(queue.put_nowait, delta)
                except Exception as e:
                    logger.error(f"LlmCppBackend stream error: {e}")
                    loop.call_soon_threadsafe(queue.put_nowait, f"\n[Stream Error: {e}]")
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel

            self.request_stats["total_requests"] += 1
            asyncio.ensure_future(loop.run_in_executor(_EXECUTOR, _produce))

            try:
                while True:
                    token = await queue.get()
                    if token is None:
                        break
                    yield token
            finally:
                duration = (time.perf_counter() - start) * 1000
                self._update_stats(duration)
                log_llm_call(
                    endpoint="llama_cpp/chat_stream",
                    duration_ms=duration,
                    token_estimate=token_estimate,
                    streaming=True,
                )

    async def completion(
        self,
        prompt: str,
        temperature: float = 0.6,
        max_tokens: int = 300,
        stop: Optional[List[str]] = None,
        grammar_path: Optional[str] = None,
    ) -> str:
        """Raw prompt completion (no chat template). Mirrors LLMClient.completion()."""
        if not prompt:
            return ""

        request_id = self._next_request_id("completion")
        caller = self._infer_caller()

        start = time.perf_counter()
        grammar = self._load_grammar(grammar_path)
        token_estimate = estimate_tokens(prompt)
        effective_max_tokens = self._effective_max_tokens(token_estimate, max_tokens)
        lock_wait_ms = 0.0

        self._debug(
            f"{request_id} start caller={caller} prompt_chars={len(prompt)} requested_max_tokens={max_tokens} "
            f"effective_max_tokens={effective_max_tokens} token_estimate={token_estimate} n_ctx={self.n_ctx} "
            f"grammar={'yes' if grammar is not None else 'no'}"
        )

        if effective_max_tokens < int(max_tokens):
            logger.warning(
                "completion max_tokens clamped: requested=%s effective=%s token_estimate=%s n_ctx=%s caller=%s",
                max_tokens,
                effective_max_tokens,
                token_estimate,
                self.n_ctx,
                caller,
            )

        def _run() -> str:
            nonlocal lock_wait_ms
            lock_wait_start = time.perf_counter()
            with _LLAMA_INFERENCE_LOCK:
                lock_wait_ms = (time.perf_counter() - lock_wait_start) * 1000
                kwargs: Dict[str, Any] = {
                    "prompt": prompt,
                    "max_tokens": effective_max_tokens,
                    "temperature": temperature,
                    "stream": False,
                }
                if stop:
                    kwargs["stop"] = stop
                if grammar:
                    kwargs["grammar"] = grammar

                result = self._model(**kwargs)
            return result["choices"][0]["text"]

        try:
            loop = asyncio.get_event_loop()
            text: str = await loop.run_in_executor(_EXECUTOR, _run)
            log_llm_call(
                endpoint="llama_cpp/completion",
                duration_ms=(time.perf_counter() - start) * 1000,
                token_estimate=estimate_tokens(prompt),
                streaming=False,
            )
            self._debug(
                f"{request_id} ok caller={caller} duration_ms={(time.perf_counter() - start) * 1000:.1f} "
                f"lock_wait_ms={lock_wait_ms:.1f}"
            )
            return text
        except Exception as e:
            err_text = str(e).lower()
            self._last_error_kind = "access_violation" if "access violation" in err_text else "completion_error"
            self._last_error_at = time.time()
            logger.error(
                "LlmCppBackend completion error: %s | request_id=%s caller=%s prompt_chars=%s max_tokens=%s",
                e,
                request_id,
                caller,
                len(prompt),
                effective_max_tokens,
                exc_info=True,
            )
            print(
                f"⚠️ [LLM ERROR] completion request_id={request_id} caller={caller} "
                f"prompt_chars={len(prompt)} max_tokens={effective_max_tokens} token_estimate={token_estimate} n_ctx={self.n_ctx}"
            )
            return ""

    @property
    def has_embeddings(self) -> bool:
        """True when a dedicated embedding model has been loaded successfully."""
        return self._embed_model is not None

    async def embed(self, text: str) -> List[float]:
        """
        Return a float embedding vector for *text* using the dedicated embed model.

        Falls back to an empty list if no embed model was loaded.
        """
        if self._embed_model is None:
            return []
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                _EXECUTOR, lambda: _locked_embed(self._embed_model, text)
            )
            return result if isinstance(result, list) else list(result)
        except Exception as e:
            logger.warning(f"LlmCppBackend embed error: {e}")
            return []

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of strings.  Returns a list of float vectors."""
        if self._embed_model is None:
            return [[] for _ in texts]
        try:
            loop = asyncio.get_event_loop()

            def _run() -> List[List[float]]:
                with _LLAMA_INFERENCE_LOCK:
                    return [
                        list(self._embed_model.embed(t))
                        for t in texts
                    ]

            return await loop.run_in_executor(_EXECUTOR, _run)
        except Exception as e:
            logger.warning(f"LlmCppBackend embed_batch error: {e}")
            return [[] for _ in texts]

    def get_chroma_embed_fn(self):
        """
        Return a ChromaDB-compatible sync embedding callable, or None.

        Usage in MemoryEngine:
            ef = llm.get_chroma_embed_fn()
            if ef:
                collection = client.get_or_create_collection(..., embedding_function=ef)
        """
        if self._embed_model is None:
            return None

        model = self._embed_model

        class _LlamaCppEF:
            """Minimal ChromaDB EmbeddingFunction wrapper."""
            def name(self) -> str:  # required by ChromaDB ≥ 0.6
                return "llama_cpp_embed"

            def __call__(self, input: List[str]) -> List[List[float]]:  # noqa: A002
                with _LLAMA_INFERENCE_LOCK:
                    return [list(model.embed(t)) for t in input]

            def embed_query(self, input: str) -> List[float]:  # called by ChromaDB on similarity search
                with _LLAMA_INFERENCE_LOCK:
                    return list(model.embed(input))

        return _LlamaCppEF()

    def confidence_to_perplexity_surprise(self, confidence: float) -> float:
        """
        Convert a [0,1] confidence estimate into a [0,1] surprise proxy.

        Higher confidence means lower surprise; this helper keeps the mapping
        consistent for downstream active-inference signals.
        """
        try:
            c = float(confidence)
        except (TypeError, ValueError):
            c = 0.5
        c = max(0.0, min(1.0, c))
        return max(0.0, min(1.0, 1.0 - c))

    # ------------------------------------------------------------------
    # Higher-level helpers (mirror LLMClient)
    # ------------------------------------------------------------------

    async def get_reflection(
        self,
        last_user_msg: str,
        last_ai_msg: str,
        current_time: str,
    ) -> Dict[str, Any]:
        """Lean reflection augmentation call (best-effort, non-blocking for organism continuity)."""
        grammar_path = None

        user_reflection_text = (last_user_msg or "").strip().replace("\n", " ")[:320]
        ai_reflection_text = (last_ai_msg or "").strip().replace("\n", " ")[:360]

        prompt = (
            "Return ONLY JSON with keys trait_deltas, emotional_deltas, self_model_deltas, confidence, user_fact, ai_self_update.\n"
            "Keep deltas tiny (-0.08..0.08). If uncertain, use empty maps with confidence around 0.45.\n"
            "Allowed traits: confidence, curiosity, analytical_depth, playfulness, emotional_warmth, technical_grounding.\n"
            "Allowed emotions: stability, engagement, intellectual_energy, warmth.\n"
            f"Current Time: {current_time}\n"
            f"User: \"{user_reflection_text}\"\n"
            f"Yuki: \"{ai_reflection_text}\"\n"
        )

        _empty = {
            "trait_deltas": {},
            "emotional_deltas": {},
            "self_model_deltas": {},
            "confidence": 0.0,
            "user_fact": "",
            "ai_self_update": "",
            "__source": "llm_reflection_empty",
        }

        now = time.time()
        if now < self._reflection_cooldown_until:
            remaining = int(self._reflection_cooldown_until - now)
            logger.warning(f"get_reflection: reflection cooldown active ({remaining}s remaining) — skipping")
            return _empty

        def _parse_payload(text: str) -> Optional[Dict[str, Any]]:
            text = (text or "").strip()
            if not text:
                return None
            try:
                return json.loads(text)
            except Exception:
                start = text.find("{")
                end = text.rfind("}")
                if start >= 0 and end > start:
                    snippet = text[start:end + 1]
                    try:
                        return json.loads(snippet)
                    except Exception:
                        return None
            return None

        try:
            _max_tokens = max(64, self._reflection_max_tokens)
            if getattr(self, "_reflection_fail_streak", 0) >= 2:
                _max_tokens = min(_max_tokens, 96)

            response = await self.completion(
                prompt=prompt,
                temperature=0.2,
                max_tokens=_max_tokens,
                stop=None,
                grammar_path=grammar_path,
            )

            # Empty response = model produced nothing under grammar constraint;
            # treat as a clean skip rather than a parse error.
            if not response or not response.strip() or response.startswith("Error:"):
                if self._last_error_kind == "access_violation":
                    self._reflection_fail_streak += 1
                    cooldown = min(300, self._reflection_cooldown_base_seconds * max(1, self._reflection_fail_streak))
                    self._reflection_cooldown_until = time.time() + cooldown
                    logger.warning(
                        "get_reflection: access-violation detected, enabling reflection cooldown for %ss (streak=%s)",
                        cooldown,
                        self._reflection_fail_streak,
                    )
                    return _empty
                return _empty

            payload = _parse_payload(response)
            if payload is None:
                logger.debug("get_reflection: could not parse reflection JSON — skipping")
                return _empty

            # Validate and clamp numeric deltas
            def _clamp_deltas(raw: Any) -> Dict[str, float]:
                if not isinstance(raw, dict):
                    return {}
                out: Dict[str, float] = {}
                for k, v in raw.items():
                    if isinstance(v, (int, float)):
                        out[k] = max(-0.1, min(0.1, float(v)))
                return out

            semantic_confidence = payload.get("confidence", 0.5)
            if not isinstance(semantic_confidence, (int, float)):
                semantic_confidence = 0.5
            confidence = max(0.0, min(1.0, float(semantic_confidence)))

            user_fact = payload.get("user_fact", "")
            if not isinstance(user_fact, str):
                user_fact = ""

            ai_self_update = payload.get("ai_self_update", "")
            if not isinstance(ai_self_update, str):
                ai_self_update = ""

            self._reflection_fail_streak = 0

            return {
                "trait_deltas": _clamp_deltas(payload.get("trait_deltas")),
                "emotional_deltas": _clamp_deltas(payload.get("emotional_deltas")),
                "self_model_deltas": _clamp_deltas(payload.get("self_model_deltas")),
                "confidence": confidence,
                "user_fact": user_fact.strip(),
                "ai_self_update": ai_self_update.strip(),
                "__source": "llm_reflection_augment",
            }

        except json.JSONDecodeError as e:
            # Only warn for genuinely malformed (non-empty) responses; empty
            # string is already handled above this block.
            logger.debug(f"Reflection JSON parse error: {e}")
            return _empty
        except Exception as e:
            logger.debug(f"Reflection error: {e}")
            return _empty

    async def generate_episodic_summary(self, exchanges: List[Dict], metabolic_context: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Generate a compact summary of recent exchanges for episodic memory."""
        if not exchanges:
            return None

        conversation = ""
        for ex in exchanges[-10:]:
            conversation += f"User: {ex['user']}\n"
            conversation += f"Assistant: {ex['assistant']}\n\n"

        metabolic_block = ""
        if isinstance(metabolic_context, dict) and metabolic_context:
            metabolic_block = f"""

    Metabolic context (historical state signatures):
    {json.dumps(metabolic_context, ensure_ascii=False, indent=2)[:1200]}
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
            {"role": "user", "content": prompt},
        ]

        try:
            summary = await self.chat_completion(messages, temperature=0.3, max_tokens=150)
            return summary.strip() if summary else None
        except Exception as e:
            logger.error(f"Episode summarization error: {e}")
            return None

    async def batched_consolidation(
        self, batch_requests: List[Any]
    ) -> Dict[str, Any]:
        """
        Grammar-constrained fact/entity/relationship extraction.
        Uses models/grammars/json_extraction.gbnf when available.
        """
        if not batch_requests:
            return {"results": []}

        self.request_stats["batched_requests"] += 1

        grammar_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "models", "grammars", "json_extraction.gbnf"
        )
        if not os.path.exists(grammar_path):
            grammar_path = None

        batch_content = []
        for i, req in enumerate(batch_requests):
            text = req.text if hasattr(req, "text") else str(req)
            context = getattr(req, "context", "")
            batch_content.append(f"Text {i + 1}:")
            batch_content.append(f"Content: {text}")
            if context:
                batch_content.append(f"Context: {context}")
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
            {"role": "user", "content": prompt},
        ]

        try:
            response = await self.chat_completion(
                messages, max_tokens=1024, grammar_path=grammar_path, profile=PROFILE_STRUCTURED
            )
            return json.loads(response.strip())
        except json.JSONDecodeError:
            logger.warning("Failed to parse batched consolidation JSON")
            return {"results": []}
        except Exception as e:
            logger.error(f"Batched consolidation error: {e}")
            return {"results": []}

    async def parallel_operations(
        self, operations: List[Tuple[str, Dict]]
    ) -> Dict[str, Any]:
        """Execute multiple LLM operations in parallel (limited by semaphore)."""
        if not operations:
            return {}

        async def _execute(op_type: str, params: Dict) -> Tuple[str, Any]:
            try:
                if op_type == "chat":
                    return op_type, await self.chat_completion(**params)
                elif op_type == "consolidation":
                    from llm.llama_client import BatchedConsolidationRequest
                    return op_type, await self.batched_consolidation(
                        [BatchedConsolidationRequest(**params)]
                    )
                elif op_type == "reflection":
                    return op_type, await self.get_reflection(**params)
                else:
                    return op_type, f"Unknown operation type: {op_type}"
            except Exception as e:
                logger.error(f"Parallel operation {op_type} failed: {e}")
                return op_type, None

        tasks = [_execute(op_type, params) for op_type, params in operations]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        result_dict: Dict[str, Any] = {}
        for i, item in enumerate(results):
            if isinstance(item, Exception):
                result_dict[f"op_{i}"] = None
            else:
                op_type, result = item
                result_dict[f"{op_type}_{i}"] = result
        return result_dict

    def get_performance_stats(self) -> Dict[str, Any]:
        """Return the same stats shape as LLMClient for dashboard compatibility."""
        total = max(1, self.request_stats["total_requests"])
        return {
            "total_requests": self.request_stats["total_requests"],
            "failed_requests": self.request_stats["failed_requests"],
            "success_rate": (
                (total - self.request_stats["failed_requests"]) / total
            ) * 100,
            "avg_response_time_ms": round(self.request_stats["avg_response_time"], 2),
            "batched_requests": self.request_stats["batched_requests"],
            "batch_efficiency": (self.request_stats["batched_requests"] / total) * 100,
            "concurrent_limit": self.max_concurrent_requests,
            "backend": "llama_cpp",
            "model": os.path.basename(self.model_path),
        }
