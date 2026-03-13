"""c3_delegate — Local LLM task offload via Ollama.

Absorbs former c3_intelligence routing logic internally.
Supports task_type='available' for zero-cost Ollama status check.
"""

import hashlib
import time
from pathlib import Path

from core import count_tokens


# Delegate task definitions
DELEGATE_TASKS = {
    "summarize": {
        "default_model": "gemma3n:latest",
        "system": "You are a concise technical summarizer. Keep the answer compact and concrete.",
        "prompt_template": "Context:\n{context}\n\nTask:\n{task}\n\nReturn a compact summary with only the key points.",
        "temperature": 0.2,
    },
    "explain": {
        "default_model": "llama3.2:3b",
        "system": "You explain code precisely and concisely. Prefer short bullet points and specific references.",
        "prompt_template": "Context:\n{context}\n\nQuestion:\n{task}\n\nExplain only what is needed to answer the question.",
        "temperature": 0.2,
    },
    "docstring": {
        "default_model": "gemma3n:latest",
        "system": "Write terse, accurate code documentation.",
        "prompt_template": "Context:\n{context}\n\nTask:\n{task}\n\nProduce a concise docstring or documentation snippet.",
        "temperature": 0.2,
    },
    "review": {
        "default_model": "llama3.2:3b",
        "system": "You are a pragmatic code reviewer. Prioritize bugs, regressions, and missing tests.",
        "prompt_template": "Context:\n{context}\n\nReview task:\n{task}\n\nReturn the most important findings first.",
        "temperature": 0.2,
    },
    "ask": {
        "default_model": "deepseek-r1:1.5b",
        "system": "Answer narrowly and directly from the provided context.",
        "prompt_template": "Context:\n{context}\n\nQuestion:\n{task}\n\nAnswer concisely.",
        "temperature": 0.2,
    },
    "test": {
        "default_model": "llama3.2:3b",
        "system": "Design targeted tests that maximize defect coverage with minimal redundancy.",
        "prompt_template": "Context:\n{context}\n\nTask:\n{task}\n\nProduce focused test ideas or test code.",
        "temperature": 0.2,
    },
    "diagnose": {
        "default_model": "llama3.2:3b",
        "system": "You diagnose failures from logs and execution context. Focus on root cause and next step.",
        "prompt_template": "Context:\n{context}\n\nProblem:\n{task}\n\nIdentify the most likely cause and the next debugging step.",
        "temperature": 0.1,
    },
    "improve": {
        "default_model": "llama3.2:3b",
        "system": "You improve code with minimal, high-value changes.",
        "prompt_template": "Context:\n{context}\n\nTask:\n{task}\n\nSuggest the smallest useful improvement plan.",
        "temperature": 0.2,
    },
}

# Module-level cache and metrics
_delegate_cache: dict[str, tuple[str, int]] = {}
_delegate_metrics = {"total_calls": 0, "tokens_saved": 0}


def get_delegate_metrics() -> dict:
    return dict(_delegate_metrics)


def infer_task_type(task: str, context: str = "") -> str:
    text = f"{task}\n{context}".lower()
    if any(tok in text for tok in ("traceback", "exception", "stack trace", "exit code", "failed", "error")):
        return "diagnose"
    if any(tok in text for tok in ("review", "regression", "bug risk", "audit")):
        return "review"
    if any(tok in text for tok in ("test", "pytest", "unit test", "integration test")):
        return "test"
    if any(tok in text for tok in ("docstring", "document", "documentation")):
        return "docstring"
    if any(tok in text for tok in ("summarize", "summary", "tl;dr")):
        return "summarize"
    if any(tok in text for tok in ("improve", "refactor", "clean up", "optimize")):
        return "improve"
    return "explain"


def resolve_model_name(candidate: str, available: list[str]) -> str:
    if not candidate:
        return ""
    normalized = candidate.strip().lower()
    if not normalized:
        return ""
    for model in available:
        if model.lower() == normalized:
            return model
    base = normalized.split(":", 1)[0]
    for model in available:
        lower = model.lower()
        if lower == base or lower.startswith(base + ":"):
            return model
    for model in available:
        if base in model.lower():
            return model
    return ""


def _fallback_model_order(task_type: str) -> list[str]:
    if task_type in {"ask", "diagnose", "explain"}:
        return ["llama3.2:latest", "llama3.2:3b", "qwen3-coder-next:latest", "llama3.1:latest", "gemma3n:latest"]
    return ["llama3.2:latest", "llama3.2:3b", "qwen3-coder-next:latest", "gemma3n:latest"]


def _estimate_confidence(task_type: str, response: str, response_tokens: int) -> str:
    hedging = [
        "i'm not sure", "i don't know", "it's unclear", "might be",
        "possibly", "i cannot determine", "hard to say", "not enough context",
    ]
    hedge_count = sum(1 for phrase in hedging if phrase in (response or "").lower())
    min_tokens = {"summarize": 15, "explain": 30, "docstring": 10, "review": 20,
                  "ask": 10, "test": 30, "diagnose": 20, "improve": 10}
    too_short = response_tokens < min_tokens.get(task_type, 10)
    if too_short or hedge_count >= 2:
        return "low"
    if hedge_count == 1 or response_tokens < min_tokens.get(task_type, 10) * 2:
        return "medium"
    return "high"


def handle_delegate(task: str, task_type: str, context: str, file_path: str,
                    svc, finalize) -> str:
    dcfg = svc.delegate_config or {}
    if not dcfg.get("enabled", True):
        return "[delegate:disabled]"

    # New: availability check (zero-cost, no Ollama generation needed)
    if task_type == "available":
        ollama = svc.ollama_client
        if not ollama:
            return finalize("c3_delegate", {"task_type": "available"},
                            "[delegate:available] ollama_client=None", "unavailable")
        available = ollama.is_available()
        models = ollama.list_models() if available else []
        status = "up" if available else "down"
        return finalize("c3_delegate", {"task_type": "available"},
                        f"[delegate:available] ollama={status} models={len(models or [])}"
                        + (f" [{', '.join(models[:5])}]" if models else ""),
                        status)

    if task_type == "auto":
        task_type = infer_task_type(task, context)

    tdef = DELEGATE_TASKS.get(task_type)
    if not tdef:
        return f"[delegate:error] Unknown type: {task_type}"
    ollama = svc.ollama_client
    if not ollama or not ollama.is_available():
        return "[delegate:error] Ollama unavailable. Requires Ollama for local LLM tasks."

    # Context enrichment
    enriched = context
    if file_path and dcfg.get("auto_compress", True):
        for p in [p.strip() for p in file_path.split(",") if p.strip()]:
            try:
                res = svc.compressor.compress_file(str(Path(svc.project_path) / p), "smart")
                if isinstance(res, dict) and res.get("compressed"):
                    enriched += f"\n--- file: {p} ---\n{res['compressed']}"
            except Exception:
                continue

    if task_type == "diagnose" and dcfg.get("auto_activity_log", True):
        recent = svc.activity_log.get_recent(limit=8)
        if recent:
            enriched += "\nRecent Activity:\n" + "\n".join(
                [f"[{e.get('timestamp','').split('T')[-1][:8]}] {e.get('tool','')}..."
                 for e in reversed(recent)])

    max_context_tokens = max(200, int(dcfg.get("max_context_tokens", 1400) or 1400))
    if count_tokens(enriched) > max_context_tokens:
        enriched = enriched[:max_context_tokens * 4]

    # Model resolution
    req_model = dcfg.get(f"{task_type}_model") or dcfg.get("preferred_model") or tdef["default_model"]
    avail = ollama.list_models() or []
    model = resolve_model_name(req_model, avail)
    if not model:
        for cand in _fallback_model_order(task_type) + avail:
            model = resolve_model_name(cand, avail)
            if model:
                break
    if not model:
        return "[delegate:error] No compatible local model found"

    # Cache check
    ckey = hashlib.md5(f"{task_type}|{model}|{enriched}|{task}".encode()).hexdigest()
    if ckey in _delegate_cache:
        cached_resp, _ = _delegate_cache[ckey]
        return finalize("c3_delegate", {"task_type": task_type, "cached": True},
                        cached_resp, "cached")

    # Generate
    timeout_s = int(dcfg.get("timeout", 90) or 90)
    _t0 = time.monotonic()
    resp = ollama.generate(
        prompt=tdef["prompt_template"].format(context=enriched, task=task),
        model=model, system=tdef["system"],
        temperature=tdef.get("temperature", 0.3),
        max_tokens=int(dcfg.get("max_tokens", 512) or 512),
        timeout=timeout_s)
    _elapsed = round(time.monotonic() - _t0, 1)
    if resp is None:
        return finalize("c3_delegate", {"task_type": task_type, "model": model},
                        f"[delegate:timeout] No response from {model} after {_elapsed}s "
                        f"(limit {timeout_s}s)", "timeout")

    # Self-correction: retry with fallback model on low confidence
    conf = _estimate_confidence(task_type, resp, count_tokens(resp))
    if conf == "low" and dcfg.get("allow_model_fallback", True):
        tried = {model}
        for fallback_cand in _fallback_model_order(task_type) + avail:
            fallback = resolve_model_name(fallback_cand, avail)
            if not fallback or fallback in tried:
                continue
            tried.add(fallback)
            retry_resp = ollama.generate(
                prompt=tdef["prompt_template"].format(context=enriched, task=task),
                model=fallback, system=tdef["system"],
                temperature=tdef.get("temperature", 0.3),
                max_tokens=int(dcfg.get("max_tokens", 512) or 512),
            )
            retry_conf = _estimate_confidence(task_type, retry_resp, count_tokens(retry_resp))
            if retry_conf != "low":
                resp = retry_resp
                conf = retry_conf
                model = fallback
                break
            if retry_conf == "low" and count_tokens(retry_resp) > count_tokens(resp):
                resp = retry_resp
                model = fallback
                conf = "medium"

    _delegate_metrics["total_calls"] += 1
    _delegate_cache[ckey] = (resp, count_tokens(resp))
    return finalize("c3_delegate", {"task": task_type, "model": model, "elapsed": f"{_elapsed}s"},
                    resp, conf)
