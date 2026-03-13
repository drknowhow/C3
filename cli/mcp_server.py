#!/usr/bin/env python3
"""
C3 MCP Server - Claude Code Companion as a native MCP tool server.

Exposes 9 C3 tools as MCP endpoints. Tool logic lives in cli/tools/.

Usage:
    python cli/mcp_server.py --project <path>
"""
import os
import sys
import time
import argparse
from datetime import datetime, timezone
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Any

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastmcp import FastMCP, Context
from core import count_tokens
from services.transcript_index import TranscriptIndex
from services.context_snapshot import ContextSnapshot
from services.runtime import C3Runtime, build_runtime, start_runtime, stop_runtime
from services.auto_memory import AutoMemory
from core.ide import load_ide_config, get_profile

# Tool handlers
from cli.tools._helpers import maybe_related_facts
from cli.tools.search import handle_search
from cli.tools.session import handle_session
from cli.tools.memory import handle_memory
from cli.tools.read import handle_read
from cli.tools.compress import handle_compress
from cli.tools.validate import handle_validate
from cli.tools.filter import handle_filter
from cli.tools.status import handle_status
from cli.tools.delegate import handle_delegate


def _get_project_path() -> str:
    """Parse --project from sys.argv (before FastMCP takes over)."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--project", default=".")
    args, _ = parser.parse_known_args()
    return str(Path(args.project).resolve())


PROJECT_PATH = _get_project_path()
_IDE_NAME = load_ide_config(PROJECT_PATH)
_IDE_PROFILE = get_profile(_IDE_NAME)


def _build_instructions(ide_name: str) -> str:
    """Build compact MCP instructions. Optimized for minimal token overhead."""
    return (
        "C3 provides local code intelligence: search, compress, session tracking, and persistent memory.\n"
        "Call `c3_memory(action='recall')` at task start for cross-session context.\n"
        "Log decisions via `c3_session(action='log')`. Use `c3_session(action='snapshot')` before /clear.\n"
        "Use `c3_filter(text=...)` for terminal output >10 lines. Keep responses concise."
    )


@asynccontextmanager
async def lifespan(server):
    """Initialize all services, auto-start session, start file watcher."""
    project = PROJECT_PATH
    services = build_runtime(project, ide_name=_IDE_NAME)
    transcript_index = TranscriptIndex(project)
    services.transcript_index = transcript_index
    snapshots = services.snapshots or ContextSnapshot(project)
    services.snapshots = snapshots

    if _IDE_PROFILE.supports_transcripts:
        if not (Path(project) / ".c3" / "transcript_index" / "index.json").exists():
            transcript_index.build_index()
        else:
            transcript_index._load_index()
            transcript_index._load_manifest()

    if not (Path(project) / ".c3" / "index" / "index.json").exists():
        import threading

        def _bg_build():
            try:
                services.indexer.build_index()
            except Exception:
                pass
            # After code index is built, build embedding index
            if services.embedding_index and services.embedding_index.ready:
                try:
                    services.embedding_index.build(services.indexer)
                except Exception:
                    pass
            # Build doc index for Local RAG Pipeline
            if services.doc_index:
                try:
                    services.doc_index.build()
                except Exception:
                    pass

        threading.Thread(target=_bg_build, daemon=True, name="c3-initial-index").start()
    else:
        services.indexer._load_index()
        # Build/update embedding index in background
        if services.embedding_index and services.embedding_index.ready:
            import threading

            def _bg_embed():
                try:
                    services.embedding_index.build(services.indexer)
                except Exception:
                    pass

            threading.Thread(target=_bg_embed, daemon=True, name="c3-embed-index").start()

        # Build/update doc index in background for Local RAG Pipeline
        if services.doc_index:
            import threading

            def _bg_doc_index():
                try:
                    services.doc_index.build()
                except Exception:
                    pass

            threading.Thread(target=_bg_doc_index, daemon=True, name="c3-doc-index").start()

    started_session = services.session_mgr.start_session("MCP server session", source_system=_IDE_NAME)
    start_runtime(services)

    convo_store = services.convo_store
    services.convo_store = convo_store
    if _IDE_PROFILE.supports_transcripts:
        try:
            convo_store.sync(source="claude")
            if services.retrieval:
                services.retrieval.mark_sessions_dirty()
        except Exception:
            pass

    import threading
    _convo_sync_stop = threading.Event()
    if _IDE_PROFILE.supports_transcripts:
        def _bg_convo_sync():
            while not _convo_sync_stop.wait(timeout=60):
                try:
                    convo_store.sync(source="claude")
                    if services.retrieval:
                        services.retrieval.mark_sessions_dirty()
                except Exception:
                    pass
        threading.Thread(target=_bg_convo_sync, daemon=True, name="c3-convo-sync").start()

    # Auto-memory: background learning from tool calls.
    auto_mem_cfg = (services.hybrid_config or {}).get("auto_memory", {})
    services.auto_memory = AutoMemory(services.memory, services.session_mgr, auto_mem_cfg)

    if services.session_mgr.current_session:
        services.activity_log.log("session_start", {
            "session_id": services.session_mgr.current_session["id"],
            "source_system": started_session.get("source_system", ""),
        })

    # Auto-restore latest snapshot if recent (< 30 min).
    # Skipped in benchmark mode to prevent snapshot budget from carrying over between tasks.
    if not os.environ.get("C3_BENCHMARK_MODE"):
        try:
            latest = snapshots._load_snapshot("latest")
            if "error" not in latest and "created" in latest:
                created_dt = datetime.fromisoformat(latest["created"])
                age_sec = (datetime.now(timezone.utc) - created_dt).total_seconds()
                if age_sec < 1800:
                    res = snapshots.restore("latest", memory_store=services.memory, level=1)
                    if "error" not in res:
                        services.session_mgr.reset_budget(initial_tokens=res.get("tokens", 0))
                        services.notifications.add(
                            agent="c3",
                            severity="info",
                            title="Session Auto-Restored",
                            message=f"Restored latest context from {round(age_sec/60)}m ago: {res['briefing']}"
                        )
                        services.activity_log.log("auto_restore", {
                            "snapshot_id": res["snapshot_id"], "age_min": round(age_sec/60)})
        except Exception:
            pass

    # Background validation sweep: check recently-errored files and notify.
    if services.validation_cache:
        import threading as _t

        def _bg_validation_sweep():
            import time
            time.sleep(8)  # Let watcher populate cache from initial file events.
            errors = services.validation_cache.get_errors()
            if errors:
                names = ", ".join(e["path"] for e in errors[:5])
                more = f" (+{len(errors) - 5} more)" if len(errors) > 5 else ""
                services.notifications.add(
                    agent="c3", severity="warning",
                    title="Syntax Errors Detected",
                    message=f"{len(errors)} file(s) have syntax errors: {names}{more}",
                )
        _t.Thread(target=_bg_validation_sweep, daemon=True, name="c3-validate-sweep").start()

    try:
        yield services
    finally:
        _convo_sync_stop.set()
        # Auto-memory: extract remaining learnings and generate session summary.
        if hasattr(services, "auto_memory"):
            try:
                services.auto_memory.on_session_end()
            except Exception:
                pass
        stop_runtime(services)
        services.session_mgr._persist_budget()
        services.session_mgr.save_session()
        if _IDE_PROFILE.supports_transcripts:
            try:
                convo_store.sync(source="claude", force=True)
                if services.retrieval:
                    services.retrieval.mark_sessions_dirty()
            except Exception:
                pass


mcp = FastMCP("C3 - Context Control", instructions=_build_instructions(_IDE_NAME), lifespan=lifespan)

# ─── Helper Functions ─────────────────────────────────────────────

def _svc(ctx: Context) -> C3Runtime:
    return ctx.request_context.lifespan_context


_last_tool_call_time: float = 0.0


def _finalize_response(ctx: Context, tool_name: str, args: dict,
                       response: str, summary: str = "") -> str:
    global _last_tool_call_time
    svc = _svc(ctx)

    # Detect new conversation after /clear: if >30s gap since last tool call,
    # auto-reset budget so the UI stays in sync with the fresh conversation.
    now = time.time()
    if _last_tool_call_time > 0 and (now - _last_tool_call_time) > 30:
        svc.session_mgr.reset_budget()
        svc.activity_log.log("budget_auto_reset", {"gap_seconds": round(now - _last_tool_call_time)})
    _last_tool_call_time = now

    svc.session_mgr.log_tool_call(tool_name, args, summary)
    svc.activity_log.log("tool_call", {"tool": tool_name, "args": args, "result_summary": summary})

    # Auto-memory: background extraction (non-blocking).
    if hasattr(svc, "auto_memory"):
        svc.auto_memory.on_tool_complete(tool_name, args, summary, response)

    # Track budget on the core response BEFORE adding overhead
    svc.session_mgr.track_response(tool_name, response)

    hybrid_cfg = svc.hybrid_config or {}

    # Append notification badge (doesn't inflate budget)
    if hybrid_cfg.get("prepend_notifications"):
        count = svc.notifications.get_pending_count()
        if count:
            badge = f"[c3:agents: {count} alert{'s' if count != 1 else ''} — use c3_status(view='notifications') to review]"
            response = badge + "\n" + response

    # Append single-threshold budget nudge
    if hybrid_cfg.get("show_context_nudges"):
        response += svc.session_mgr.get_context_nudge()

    return response


# ─── TOOL REGISTRATIONS (9 tools) ────────────────────────────────

@mcp.tool()
def c3_search(query: str, action: str = "code", top_k: int = 3,
              max_tokens: int = 1200, ctx: Context = None) -> str:
    """Consolidated search for code or transcripts.
    action: 'code' (default) - search project code via TF-IDF.
            'exact' - exact code or regex match across tracked files.
            'files' - ranked file discovery with structural metadata.
            'transcript' - search past conversations from supported providers/imports.
            'semantic' - embedding-based semantic search (requires Ollama + nomic-embed-text)."""
    svc = _svc(ctx)

    def finalize(name, args, resp, summ):
        return _finalize_response(ctx, name, args, resp, summ)

    return handle_search(query, action, top_k, max_tokens, svc,
                         finalize, maybe_related_facts)


@mcp.tool()
def c3_session(action: str, data: str = "", reasoning: str = "",
               description: str = "", summary: str = "",
               event_type: str = "auto", ctx: Context = None) -> str:
    """Consolidated session management.
    action: 'start' - begin new session. Use 'description'.
            'save' - persist current session. Use 'summary'.
            'log' - record decision or file change. Use 'data' and 'reasoning'. Use 'event_type' (decision|file_change|auto).
            'plan' - store/update a named plan. Use 'data' for plan text.
            'snapshot' - capture work state before /clear. Use 'data' for task description, 'reasoning' for next-step notes, 'summary' for comma-separated key file paths to embed structural maps (e.g. "services/foo.py,cli/bar.py").
            'restore' - reinstate context after /clear. Use 'data' for snapshot_id (default: 'latest').
            'compact' - snapshot + reset budget. Use 'data' for task description.
            'convo_log' - zero-token turn logger. Use 'data' for text, 'event_type' for role (user|assistant)."""
    svc = _svc(ctx)

    def finalize(name, args, resp, summ):
        return _finalize_response(ctx, name, args, resp, summ)

    return handle_session(action, data, reasoning, description, summary,
                          event_type, svc, finalize)


@mcp.tool()
def c3_memory(action: str, query: str = "", fact: str = "",
              category: str = "general", top_k: int = 3,
              fact_id: str = "", ctx: Context = None) -> str:
    """Consolidated memory management (facts and Semantic LT Memory).
    action: 'add' - store a fact. Use 'fact' and 'category'.
            'recall' - search stored facts + semantic memory. Use 'query'.
            'query' - deep cross-session query. Use 'query'.
            'update' - update an existing fact. Use 'fact_id' + 'fact'/'category'.
            'delete' - remove a fact permanently. Use 'fact_id'.
            'list' - browse all stored facts. Optional: 'category' to filter.
            'review' - show duplicates and never-recalled facts with delete/merge commands.
            'consolidate' - auto-merge duplicate facts and archive stale auto-generated facts.
            'export' - format all facts as markdown for pasting into MEMORY.md topic files. Optional: 'category' to filter."""
    svc = _svc(ctx)

    def finalize(name, args, resp, summ):
        return _finalize_response(ctx, name, args, resp, summ)

    return handle_memory(action, query, fact, category, top_k, svc, finalize,
                         fact_id=fact_id)


@mcp.tool()
def c3_read(file_path: str, symbols: Any = None, lines: Any = None,
            include_docstrings: bool = True, ctx: Context = None) -> str:
    """Surgically read specific sections (symbols or line ranges) of a file.
    file_path: single file OR comma-separated paths for multi-file reads (e.g. "a.py,b.py").
    symbols: list of class or function names to extract (supports partial/substring match).
    lines: line specification. Can be:
           - A single integer: 5
           - A single range: [5, 10]
           - A list of ranges or integers: [[1, 5], 10, [20, 25]]
    include_docstrings: if True, ensures symbol docstrings are included."""
    svc = _svc(ctx)

    def finalize(name, args, resp, summ):
        return _finalize_response(ctx, name, args, resp, summ)

    return handle_read(file_path, symbols, lines, include_docstrings, svc, finalize)


@mcp.tool()
def c3_compress(file_path: str, mode: str = "smart", ctx: Context = None) -> str:
    """Compress a source file to a token-efficient summary.
    Saves 40-70% tokens. Modes: map, dense_map, smart, diff, bug_scan.
    map/dense_map: structural map (classes/functions) with line numbers. Use before reading a file.
    bug_scan: structure map + annotated exception-handling hotspots with line numbers. Use for bug/quality analysis tasks."""
    svc = _svc(ctx)

    def finalize(name, args, resp, summ):
        return _finalize_response(ctx, name, args, resp, summ)

    return handle_compress(file_path, mode, svc, finalize, maybe_related_facts)


@mcp.tool()
async def c3_validate(file_path: str, ctx: Context = None) -> str:
    """Syntax-check a file using native language parsers — no AI, no external services.
    py->ast  json->json.loads  yaml->yaml  xml/svg->ElementTree  toml->tomllib
    js/jsx->node  ts->tsc(->node)  tsx->tsc  java->javac  go->gofmt  rs->rustc
    r->Rscript  sh/bash->bash -n  html->lxml  css->tinycss2
    Subprocess tools are skipped gracefully when not installed."""
    svc = _svc(ctx)

    def finalize(name, args, resp, summ):
        return _finalize_response(ctx, name, args, resp, summ)

    return await handle_validate(file_path, svc, finalize)


@mcp.tool()
def c3_filter(file_path: str = "", text: str = "", pattern: str = "",
              max_lines: int = 50, depth: str = "smart",
              use_llm: bool = True, ctx: Context = None) -> str:
    """Filter terminal output or extract from files. Two modes:
    - text mode: pass 'text' for terminal output filtering (strips noise, collapses pass/fail).
    - file mode: pass 'file_path' to extract from logs/data. Use 'pattern' for regex grep.
    depth: 'fast' (regex only), 'smart' (regex + heuristics, default), 'deep' (regex + heuristics + LLM)."""
    svc = _svc(ctx)

    def finalize(name, args, resp, summ):
        return _finalize_response(ctx, name, args, resp, summ)

    return handle_filter(file_path, text, pattern, max_lines, depth, use_llm,
                         svc, finalize)


@mcp.tool()
def c3_status(view: str = "budget", detailed: bool = False,
              ctx: Context = None) -> str:
    """Consolidated status and observability.
    view: 'budget' (default) - context token count, threshold, per-tool breakdown, and restart guidance.
          'health' - quick system diagnostics (Ollama, index, notifications, session, SLTM, memory).
          'notifications' - list/ack background agent notifications. Use data param: 'ack_all' to acknowledge."""
    svc = _svc(ctx)

    def finalize(name, args, resp, summ):
        return _finalize_response(ctx, name, args, resp, summ)

    return handle_status(view, detailed, svc, finalize)


@mcp.tool()
def c3_delegate(task: str, task_type: str = "ask", context: str = "",
                file_path: str = "", ctx: Context = None) -> str:
    """Delegate heavy tasks (explain, diagnose, test, review) to local Ollama LLMs.
    Requires Ollama. Returns graceful error with suggestion if unavailable.
    task_type: 'available' - zero-cost check returning Ollama status + loaded models.
               'auto' - infer task type from content. Or specify: summarize, explain,
               docstring, review, ask, test, diagnose, improve.
    Supports multi-file paths and automated activity log injection for diagnoses."""
    svc = _svc(ctx)

    def finalize(name, args, resp, summ):
        return _finalize_response(ctx, name, args, resp, summ)

    return handle_delegate(task, task_type, context, file_path, svc, finalize)


if __name__ == "__main__":
    mcp.run(transport="stdio", show_banner=False, log_level="ERROR")
