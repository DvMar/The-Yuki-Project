"""LLM integration clients and adapters."""
import os

# Re-export sampler profiles for package-level imports.
from llm.llama_cpp_backend import (
    SamplerProfile,
    PROFILE_CHAT,
    PROFILE_REFLECTION,
    PROFILE_CREATIVE,
    PROFILE_STRUCTURED,
)

__all__ = [
    "get_llm_client",
    "SamplerProfile",
    "PROFILE_CHAT",
    "PROFILE_REFLECTION",
    "PROFILE_CREATIVE",
    "PROFILE_STRUCTURED",
]


def get_llm_client():
    """
    Return the appropriate LLM backend based on the environment.

    - If LLAMA_CPP_MODEL is set to a valid GGUF path → LlmCppBackend (in-process)
    - Otherwise                                        → LLMClient (HTTP to llama-server)

    This is the single place to swap backends; all callers use this factory.
    """
    _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _resolve(p: str) -> str:
        """Resolve and normalize a path relative to the project root."""
        if not p:
            return p
        full = p if os.path.isabs(p) else os.path.join(_project_root, p)
        return os.path.normpath(full)

    model_path = _resolve(os.environ.get("LLAMA_CPP_MODEL", ""))
    if model_path and os.path.isfile(model_path):
        from llm.llama_cpp_backend import LlmCppBackend
        embed_model_path = _resolve(os.environ.get("LLAMA_CPP_EMBED_MODEL", ""))
        draft_model_path = _resolve(os.environ.get("LLAMA_CPP_DRAFT_MODEL", ""))
        return LlmCppBackend(
            model_path=model_path,
            n_ctx=int(os.environ.get("LLAMA_CPP_N_CTX", 32768)),
            n_gpu_layers=int(os.environ.get("LLAMA_CPP_N_GPU_LAYERS", 0)),
            n_threads=int(os.environ.get("LLAMA_CPP_N_THREADS", 0)) or None,
            max_concurrent_requests=int(os.environ.get("LLAMA_CPP_MAX_CONCURRENT", 1)),
            embed_model_path=embed_model_path if embed_model_path and os.path.isfile(embed_model_path) else None,
            draft_model_path=draft_model_path if draft_model_path and os.path.isfile(draft_model_path) else None,
        )

    from llm.llama_client import LLMClient
    base_url = os.environ.get("LLAMA_SERVER_URL", "http://localhost:8080")
    return LLMClient(
        base_url=f"{base_url}/v1",
        completion_base_url=base_url,
    )
