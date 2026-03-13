"""c3_search — Code, file, and transcript discovery."""

import re
import time
from pathlib import Path

from core import count_tokens


def handle_search(query: str, action: str, top_k: int, max_tokens: int,
                  svc, finalize, maybe_facts) -> str:
    top_k = max(1, min(int(top_k), 10))
    max_tokens = max(200, int(max_tokens))

    if action == "exact":
        return _exact_search(query, top_k, svc, finalize)

    if action == "files":
        return _files_search(query, top_k, svc, finalize)

    if action == "transcript":
        return _transcript_search(query, top_k, max_tokens, svc, finalize)

    if action == "semantic":
        return _semantic_search(query, top_k, max_tokens, svc, finalize, maybe_facts)

    # Default: Code Search
    return _code_search(query, top_k, max_tokens, svc, finalize, maybe_facts)


def _exact_search(query, top_k, svc, finalize):
    try:
        pat = re.compile(query)
    except Exception as e:
        return finalize("c3_search", {"action": "exact"},
                        f"[search:exact:error] Invalid regex: {e}", "error")

    tracked = svc.file_memory.list_tracked()
    matched_parts = []
    total_tokens = 0
    file_count = 0

    for rel in tracked:
        full = Path(svc.project_path) / rel
        if not full.exists():
            continue
        try:
            lines = full.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue

        file_matches = []
        for i, line in enumerate(lines):
            if pat.search(line):
                start = max(0, i - 1)
                end = min(len(lines), i + 2)
                for j in range(start, end):
                    marker = ">" if j == i else " "
                    entry = f"{marker}L{j+1}: {lines[j][:200]}"
                    if entry not in file_matches:
                        file_matches.append(entry)
                if file_matches and file_matches[-1] != "---":
                    file_matches.append("---")

        if file_matches:
            file_count += 1
            matched_parts.append(f"--- {rel} ---")
            matched_parts.extend(file_matches)
            total_tokens += sum(count_tokens(m) for m in file_matches)
            if len(matched_parts) >= top_k * 10:
                break

    if not matched_parts:
        return finalize("c3_search", {"action": "exact"},
                        f"[search:exact:{query}] 0 results", "0")

    limited = matched_parts[:top_k * 10]
    resp = f"[search:exact:{query}] {file_count} files matched, {total_tokens}tok\n" + "\n".join(limited)
    return finalize("c3_search", {"action": "exact"}, resp, f"{file_count}f")


def _files_search(query, top_k, svc, finalize):
    res = svc.indexer.search(query, top_k=top_k, include_content=False)
    if not res:
        return finalize("c3_search", {"action": "files"},
                        f"[search:files:{query}] 0 results", "0")
    parts = []
    for r in res:
        meta = f"- {r['file']} (L{r['lines']})"
        if r.get('name'):
            meta += f" — contains {r['type']} '{r['name']}'"
        if len(parts) == 0:
            try:
                rel = r['file'].replace("\\", "/")
                if svc.file_memory.needs_update(rel):
                    svc.file_memory.update(rel)
                fmap = svc.file_memory.get_or_build_map(rel)
                if fmap:
                    meta += f"\n  {fmap.replace(chr(10), chr(10) + '  ')}"
            except Exception:
                pass
        parts.append(meta)
    return finalize("c3_search", {"action": "files"},
                    f"[search:files:{query}] {len(res)} results\n" + "\n".join(parts),
                    f"{len(res)}f")


def _transcript_search(query, top_k, max_tokens, svc, finalize):
    sync_result = svc.convo_store.sync(source="all")
    available = sync_result.get("available_sources", {})
    available_names = [name for name, present in available.items() if present]
    if not available_names:
        resp = ("[transcript:unavailable] No supported transcript sources found for this project. "
                "Supported sources: Claude Code, Gemini CLI, and imported transcripts under .c3/conversations/imports.")
        return finalize("c3_search", {"action": "transcript"}, resp, "unavailable")

    results = svc.convo_store.search(query, limit=max(top_k * 3, top_k))
    if not results:
        srcs = ",".join(sorted(available_names))
        return finalize("c3_search", {"action": "transcript"},
                        f"[transcript:{query}] 0 results sources:{srcs}", "0")
    parts = []
    total_tokens = 0
    emitted = 0
    for r in results:
        tokens = int(r.get("tokens", 0) or count_tokens(r.get("text", "")))
        if total_tokens + tokens > max_tokens and parts:
            break
        total_tokens += tokens
        ts_raw = r.get("ts", 0)
        try:
            ts_str = time.strftime("%Y-%m-%d", time.localtime(float(ts_raw))) if ts_raw else ""
        except Exception:
            ts_str = ""
        source = r.get("source") or r.get("turn_source") or "manual"
        role = r.get("role", "")
        session_id = r.get("session_id", "")
        header = f"--- {source}:{session_id} [{ts_str}] role:{role} score:{r['score']}"
        text = r.get("text", "")
        parts.extend([header, text])
        emitted += 1
        if emitted >= top_k:
            break
    resp = f"[transcript:{query}] {emitted}r,{total_tokens}tok\n" + "\n".join(parts)
    return finalize("c3_search", {"action": "transcript"}, resp, f"{emitted}r")


def _semantic_search(query, top_k, max_tokens, svc, finalize, maybe_facts):
    ei = getattr(svc, "embedding_index", None)
    if not ei or not ei.ready:
        # Fallback to TF-IDF code search when embeddings unavailable
        return _code_search(query, top_k, max_tokens, svc, finalize, maybe_facts)

    results = ei.search(query, top_k=top_k, max_tokens=max_tokens)
    if not results:
        return finalize("c3_search", {"query": query, "action": "semantic"},
                        f"[semantic:{query}] 0 results (falling back to code search)",
                        "0→fallback")

    lines = []
    total_tokens = 0
    for r in results:
        name = f" {r['name']}" if r.get('name') else ""
        ref = f"--- {r['file']}:L{r['lines']}{name} ({r['type']},{r['tokens']}tok,s={r.get('score', 0):.4f})"
        lines.extend([ref, r['content']] if r.get('content') else [ref])
        total_tokens += r['tokens']

    resp = f"[semantic:{query}] {len(results)} results, {total_tokens}tok\n" + "\n".join(lines)
    resp += maybe_facts(svc, query, top_k=2)
    return finalize("c3_search", {"query": query, "action": "semantic"}, resp, f"{len(results)}r,{total_tokens}tok")


def _code_search(query, top_k, max_tokens, svc, finalize, maybe_facts):
    results = svc.indexer.search(query, top_k=max(top_k + 1, top_k * 2),
                                 max_tokens=max_tokens, include_content=True)
    if not results:
        return finalize("c3_search", {"query": query}, f"[search:{query}] 0 results", "0")

    best_score = max((r.get("score", 0.0) for r in results), default=0.0)
    if best_score > 0:
        results = [r for r in results if r.get("score", 0.0) >= (best_score * 0.2)]

    deduped = []
    seen = set()
    for r in results:
        key = (r.get("file"), r.get("lines"))
        if key not in seen:
            seen.add(key)
            deduped.append(r)
            if len(deduped) >= top_k:
                break

    lines = []
    total_tokens = 0
    for r in deduped:
        name = f" {r['name']}" if r['name'] else ""
        ref = f"--- {r['file']}:L{r['lines']}{name} ({r['type']},{r['tokens']}tok,s={r.get('score', 0):.3f})"
        lines.extend([ref, r['content']] if r.get('content') else [ref])
        total_tokens += r['tokens']

    resp = f"[search:{query}] {len(deduped)} results, {total_tokens}tok\n" + "\n".join(lines)
    resp += maybe_facts(svc, query, top_k=2)
    full_tokens = sum(r.get("file_tokens", r["tokens"]) for r in deduped)
    summary = f"{full_tokens}->{total_tokens}tok" if total_tokens < full_tokens else f"{len(deduped)}r"
    return finalize("c3_search", {"query": query, "top_k": top_k}, resp, summary)
