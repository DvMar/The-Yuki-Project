import json
import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, Optional

logger = logging.getLogger("yuki_project.runtime")


def _safe_json(payload: Dict[str, Any]) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, default=str)
    except Exception:
        return json.dumps({"event": "logging_error", "payload_type": str(type(payload))})


def log_structured(event: str, level: int = logging.INFO, **fields: Any) -> None:
    payload = {"event": event, **fields}
    logger.log(level, _safe_json(payload))


def estimate_tokens(text: Optional[str]) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


@contextmanager
def track_async_task(task_name: str, **fields: Any):
    start = time.perf_counter()
    log_structured("async_task_start", task=task_name, **fields)
    try:
        yield
    finally:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        log_structured("async_task_end", task=task_name, duration_ms=duration_ms, **fields)


def log_llm_call(endpoint: str, duration_ms: float, token_estimate: int, streaming: bool) -> None:
    log_structured(
        "llm_call",
        endpoint=endpoint,
        duration_ms=round(duration_ms, 2),
        token_estimate=token_estimate,
        streaming=streaming,
    )


def log_memory_write(store: str, operation: str, size_hint: int = 0, **fields: Any) -> None:
    log_structured(
        "memory_write",
        store=store,
        operation=operation,
        size_hint=size_hint,
        **fields,
    )
