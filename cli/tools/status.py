"""c3_status — Budget, health, and notifications (3 views).

Removed views (available via REST API/CLI):
  'why', 'raw', 'optimize' — use `c3 status <view>` CLI command instead.
  'tokens', 'memory' — merged into 'budget' (detailed=True) and 'health' respectively.
"""

import time
from pathlib import Path

from core import count_tokens, format_token_count


def handle_status(view: str, detailed: bool, svc, finalize) -> str:
    if view == "budget":
        return _budget_view(svc, detailed, finalize)

    if view == "health":
        return _health_view(svc, finalize)

    if view == "notifications":
        return _notifications_view(svc, finalize)

    # Graceful migration for removed views
    removed = {
        "tokens": "Merged into 'budget'. Use c3_status(view='budget', detailed=True).",
        "memory": "Merged into 'health'. Use c3_status(view='health').",
        "why": "Available via CLI: `c3 status why`",
        "raw": "Available via CLI: `c3 status raw`",
        "optimize": "Available via CLI: `c3 status optimize`",
    }
    if view in removed:
        return finalize("c3_status", {"view": view},
                        f"[status:moved] '{view}' view removed from MCP. {removed[view]}", "moved")

    return f"[status:error] Unknown view: {view}. Available: budget, health, notifications"


def _budget_view(svc, detailed, finalize):
    snap = svc.session_mgr.get_budget_snapshot()
    if "error" in snap:
        return f"[ctx_status] {snap['error']}"

    tokens = snap["response_tokens"]
    threshold = snap["threshold"]
    pct = round(tokens / threshold * 100) if threshold > 0 else 0

    # Session age
    age_str = ""
    sess = svc.session_mgr.current_session
    if sess:
        started = sess.get("started", "")
        try:
            start_ts = time.mktime(time.strptime(started, "%Y-%m-%dT%H:%M:%S"))
            age_str = f" age:{round((time.time() - start_ts) / 60)}min"
        except Exception:
            pass

    lines = [
        f"[ctx_status] {tokens}tok/{snap['call_count']}calls "
        f"avg:{snap['avg_tokens_per_call']} ({pct}% of {threshold}tok threshold){age_str}"
    ]

    # File memory coverage
    try:
        tracked = svc.file_memory.list_tracked()
        idx_stats = svc.indexer.get_stats()
        total_files = idx_stats.get("files_indexed", 0)
        lines.append(f"[file_memory] {len(tracked)}/{total_files} files indexed")
    except Exception as e:
        lines.append(f"[file_memory] error: {e}")

    # Per-tool token breakdown
    by_tool = snap.get("by_tool", {})
    if by_tool:
        sorted_tools = sorted(by_tool.items(), key=lambda x: -x[1])
        shown = sorted_tools[:6]
        breakdown = " | ".join(f"{n}:{t}tok" for n, t in shown)
        if len(sorted_tools) > 6:
            breakdown += f" (+{len(sorted_tools) - 6} more)"
        lines.append(f"[breakdown] {breakdown}")

    if detailed:
        stats = svc.indexer.get_stats()
        lines.append(f"[index] files:{stats['files_indexed']} "
                      f"tok:{format_token_count(stats['total_tokens_in_codebase'])}")

    # Single warning when over threshold
    if pct >= 100:
        lines.append(f"[warn] Budget exceeded ({pct}%). Run c3_session(action='compact') "
                      "then ask user to /clear + restore.")

    return finalize("c3_status", {"view": "budget"}, "\n".join(lines), f"{pct}%")


def _health_view(svc, finalize):
    parts = []
    ollama_ok = svc.ollama_client and svc.ollama_client.is_available()
    models = svc.ollama_client.list_models() if ollama_ok else []
    parts.append(f"[ollama] {'up (' + str(len(models)) + ' models)' if ollama_ok else 'unavailable'}")
    stats = svc.indexer.get_stats()
    parts.append(f"[index] {stats.get('files_indexed', 0)} files indexed")
    sess = svc.session_mgr.current_session
    if sess:
        started = sess.get("started", "")
        try:
            start_ts = time.mktime(time.strptime(started, "%Y-%m-%dT%H:%M:%S"))
            age_min = round((time.time() - start_ts) / 60)
            parts.append(f"[session] {sess.get('id', '?')[:12]} age:{age_min}min "
                          f"calls:{len(sess.get('tool_calls', []))}")
        except Exception:
            parts.append(f"[session] {sess.get('id', '?')[:12]}")
    else:
        parts.append("[session] none active")
    pending = svc.notifications.get_unacknowledged(limit=5)
    parts.append(f"[notifications] {len(pending)} pending")
    if svc.vector_store:
        try:
            vs = svc.vector_store.get_stats()
            parts.append(f"[sltm] {vs.get('total_records', 0)} records "
                          f"ollama={vs.get('ollama_available', False)}")
        except Exception as e:
            parts.append(f"[sltm] error: {e}")
    else:
        parts.append("[sltm] disabled")
    fact_count = len(svc.memory.facts) if hasattr(svc.memory, 'facts') else 0
    parts.append(f"[memory] {fact_count} facts")
    # Doc index (Local RAG Pipeline)
    if hasattr(svc, "doc_index") and svc.doc_index:
        di_stats = svc.doc_index.get_stats()
        parts.append(f"[doc_index] {di_stats['total_chunks']} chunks "
                      f"({di_stats['files_tracked']} files)")
    else:
        parts.append("[doc_index] disabled")
    # Validation cache stats
    vcache = getattr(svc, "validation_cache", None)
    if vcache:
        vs = vcache.summary()
        err_note = f" ({vs['errors']} errors)" if vs["errors"] else ""
        parts.append(f"[validation] {vs['cached_files']} cached, {vs['clean']} clean{err_note}")
    else:
        parts.append("[validation] disabled")
    # .c3/ directory disk usage
    try:
        c3_dir = Path(svc.project_path) / ".c3"
        if c3_dir.exists():
            total_bytes = sum(f.stat().st_size for f in c3_dir.rglob("*") if f.is_file())
            if total_bytes < 1024 * 1024:
                size_str = f"{total_bytes / 1024:.0f}KB"
            else:
                size_str = f"{total_bytes / (1024 * 1024):.1f}MB"
            parts.append(f"[storage] .c3/ {size_str}")
    except Exception as e:
        parts.append(f"[storage] error: {e}")
    return finalize("c3_status", {"view": "health"}, "\n".join(parts), "ok")


def _notifications_view(svc, finalize):
    pending = svc.notifications.get_unacknowledged(limit=20)
    if not pending:
        return "No pending notifications."
    resp = (f"# Pending ({len(pending)})\n"
            + "\n".join([f"[{n['severity']}] {n['agent']}: {n['title']}" for n in pending]))
    return finalize("c3_status", {"view": "notifications"}, resp, f"{len(pending)}p")
