"""c3_validate — Deterministic syntax validation using native language parsers."""

import asyncio
import os
from pathlib import Path


async def handle_validate(file_path: str, svc, finalize) -> str:
    full = Path(svc.project_path) / file_path
    if not full.exists():
        full = Path(file_path)
    if not full.exists():
        return f"Error: File not found: {file_path}"

    ext = full.suffix.lower()
    lang = ext.lstrip('.').upper() if ext else 'unknown'
    hybrid_cfg = svc.hybrid_config or {}
    timeout_seconds = max(1, int(hybrid_cfg.get("validate_timeout_seconds", 35) or 35))

    # Try cached result first (populated by background watcher).
    cached_hit = False
    vcache = getattr(svc, "validation_cache", None)
    if vcache:
        try:
            rel = str(full.resolve().relative_to(Path(svc.project_path).resolve()))
            cached = vcache.get(rel)
            if cached is not None:
                result = cached
                cached_hit = True
        except Exception:
            pass

    if not cached_hit:
        try:
            content = await asyncio.to_thread(full.read_text, encoding="utf-8", errors="replace")
        except Exception as e:
            return f"Error: Could not read {file_path}: {e}"

        from services.parser import check_syntax_native_with_timeout

        try:
            result = await asyncio.to_thread(
                check_syntax_native_with_timeout, content, ext, timeout_seconds,
            )
        except Exception:
            result = {"status": "checker_failed", "checker": "native", "errors": [],
                      "detail": f"Validation failed unexpectedly."}

        # Store result in cache for future calls.
        if vcache:
            try:
                rel = str(full.resolve().relative_to(Path(svc.project_path).resolve()))
                st = os.stat(str(full))
                vcache.put(rel, result, st.st_mtime, st.st_size)
            except Exception:
                pass

    checker = result.get("checker", "native")
    detail = result.get("detail", "")
    errors = result.get("errors", []) or []
    outcome = result.get("status", "checker_failed")

    cache_tag = " [cached]" if cached_hit else ""

    if outcome == "clean":
        status = f"PASS {lang}: no syntax errors (syntax only, not executed). [checker:{checker}]{cache_tag}"
        summary = f"validated clean via {checker}"
    elif outcome == "syntax_error":
        status = f"FAIL {lang}: syntax errors. [checker:{checker}]{cache_tag}\n"
        for err in errors[:10]:
            status += f"- L{err['line']}, Col {err['column']}: {err['text']}\n"
        if len(errors) > 10:
            status += f"- ... and {len(errors) - 10} more errors.\n"
        if detail:
            status += f"[detail] {detail}"
        summary = f"validated syntax_error via {checker}"
    elif outcome == "checker_unavailable":
        status = f"SKIP {lang}: {checker} not found on PATH — install it to enable validation. [checker:{checker}]"
        if detail:
            status += f"\n[detail] {detail}"
        summary = f"validated checker_unavailable via {checker}"
    elif outcome == "checker_timeout":
        status = f"TIMEOUT {lang}: validation exceeded {timeout_seconds}s. [checker:{checker}]"
        if detail:
            status += f"\n[detail] {detail}"
        summary = f"validated checker_timeout via {checker}"
    elif outcome == "unsupported":
        status = f"SKIP {lang}: unsupported file type for native validation. [checker:{checker}]"
        if detail:
            status += f"\n[detail] {detail}"
        summary = f"validated unsupported via {checker}"
    else:
        status = f"ERROR {lang}: validator failed. [checker:{checker}]"
        if detail:
            status += f"\n[detail] {detail}"
        summary = f"validated checker_failed via {checker}"

    return finalize("c3_validate", {"file_path": file_path}, status, summary)
