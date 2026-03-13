"""c3_memory — Facts and cross-session recall with TF-IDF fallback."""


def handle_memory(action: str, query: str, fact: str, category: str,
                  top_k: int, svc, finalize, fact_id: str = "") -> str:
    if action == "add":
        sid = (svc.session_mgr.current_session or {}).get("id", "")
        res = svc.memory.remember(fact, category, sid)
        return finalize("c3_memory", {"action": action},
                        f"[remembered:{res['id']}] total:{res['total_facts']}", res['id'])

    if action == "recall":
        results = svc.memory.recall(query, top_k=top_k)
        backend = "tfidf"
        if svc.vector_store:
            v_res = svc.vector_store.search(query, top_k=top_k)
            for r in v_res:
                semantic_text = (r.get("content") or r.get("text") or r.get("fact") or "").strip()
                if not semantic_text:
                    continue
                if not any(f.get("fact") == semantic_text for f in results):
                    metadata = r.get("metadata") or {}
                    results.append({
                        "category": metadata.get("category", r.get("category", "semantic")),
                        "fact": semantic_text,
                    })
            if v_res:
                backend = "hybrid"

        # Local RAG Pipeline: auto-retrieve project docs on first recall
        precontext = ""
        if hasattr(svc, "preloader") and svc.preloader:
            session_id = (svc.session_mgr.current_session or {}).get("id", "")
            if session_id:
                precontext = svc.preloader.preload(query, session_id, top_k=top_k)

        if not results and not precontext:
            return finalize("c3_memory", {"action": action},
                            f"[memory:recall:{query}] 0 results (backend:{backend})", "0")
        parts = [f"[{f['category']}] {f['fact']}"
                 for f in results[:top_k]]
        recall_text = f"[recall:{query}] {len(results)} facts (backend:{backend})\n" + "\n".join(parts)

        if precontext:
            recall_text = precontext + recall_text

        return finalize("c3_memory", {"action": action}, recall_text, f"{len(results)}f")

    if action == "query":
        res = svc.memory.query_all(query, top_k=top_k)
        backend = "tfidf"
        if svc.vector_store and svc.vector_store.vector_enabled:
            backend = "hybrid"
        parts = [f"[{f['category']}] {f['fact'][:80]}" for f in res['facts']]
        parts += [f"[session:{s['session_id'][:12]}] {s.get('summary', '')[:80]}"
                  for s in res.get('sessions', [])]
        parts += [f"[conversation:{c['session_id'][:12]}] {(c.get('snippet') or c.get('text', ''))[:80]}"
                  for c in res.get('conversations', [])[:top_k]]
        parts += [f"[file:{f['path']}] {(f.get('summary') or '')[:80]}"
                  for f in res.get('files', [])[:top_k]]
        return finalize("c3_memory", {"action": action},
                        f"[query:{query}] {len(parts)} hits (backend:{backend})\n" + "\n".join(parts),
                        f"{len(parts)}h")

    if action == "update":
        if not fact_id:
            return "[memory:error] update requires fact_id"
        res = svc.memory.update_fact(fact_id, fact=fact, category=category)
        if res.get("error"):
            return f"[memory:error] {res['error']} (id={fact_id})"
        return finalize("c3_memory", {"action": action},
                        f"[updated:{fact_id}]", fact_id)

    if action == "delete":
        if not fact_id:
            return "[memory:error] delete requires fact_id"
        res = svc.memory.delete_fact(fact_id)
        if res.get("error"):
            return f"[memory:error] {res['error']} (id={fact_id})"
        return finalize("c3_memory", {"action": action},
                        f"[deleted:{fact_id}]", fact_id)

    if action == "list":
        facts = svc.memory.facts
        if category:
            facts = [f for f in facts if f.get("category") == category]
        facts = [f for f in facts if f.get("lifecycle") != "archived"]
        if not facts:
            return finalize("c3_memory", {"action": action},
                            "[memory:list] 0 facts stored", "0")
        by_cat: dict = {}
        for f in facts:
            by_cat.setdefault(f.get("category", "general"), []).append(f)
        lines = [f"[memory:list] {len(facts)} fact(s)"]
        for cat, entries in sorted(by_cat.items()):
            lines.append(f"  [{cat}]")
            for e in entries:
                rc = e.get("relevance_count", 0)
                lines.append(f"    {e['id']} (rc={rc}) {e['fact'][:80]}")
        return finalize("c3_memory", {"action": action},
                        "\n".join(lines), f"{len(facts)}f")

    if action == "review":
        facts = [f for f in svc.memory.facts if f.get("lifecycle") != "archived"]
        total = len(facts)
        # Unused: never recalled
        unused = [f for f in facts if f.get("relevance_count", 0) == 0]
        # Simple Jaccard duplicate detection (no external deps)
        def _tokens(text):
            return set(text.lower().split())
        pairs = []
        for i in range(len(facts)):
            for j in range(i + 1, len(facts)):
                a, b = facts[i], facts[j]
                ta, tb = _tokens(a["fact"]), _tokens(b["fact"])
                if not ta or not tb:
                    continue
                sim = len(ta & tb) / len(ta | tb)
                if sim >= 0.6:
                    pairs.append((a, b, round(sim, 2)))
            if len(pairs) >= 5:
                break
        lines = [f"[memory:review] {total} facts total"]
        if pairs:
            lines.append(f"  Potential duplicates ({len(pairs)}):")
            for a, b, sim in pairs[:5]:
                lines.append(f"    {a['id']} ≈ {b['id']} (sim={sim})")
                lines.append(f"      A: {a['fact'][:60]}")
                lines.append(f"      B: {b['fact'][:60]}")
                lines.append(f"      → merge: c3_memory(action='update', fact_id='{a['id']}', fact='<merged>')")
                lines.append(f"        then:  c3_memory(action='delete', fact_id='{b['id']}')")
        if unused:
            lines.append(f"  Never-recalled facts ({len(unused)}) — consider deleting:")
            for f in unused[:5]:
                lines.append(f"    {f['id']} [{f.get('category','?')}] {f['fact'][:70]}")
                lines.append(f"      → c3_memory(action='delete', fact_id='{f['id']}')")
        if not pairs and not unused:
            lines.append("  No issues found.")
        return finalize("c3_memory", {"action": action},
                        "\n".join(lines), f"{total}f")

    if action == "export":
        facts = [f for f in svc.memory.facts if f.get("lifecycle") != "archived"]
        if category and category != "general":
            facts = [f for f in facts if f.get("category") == category]
        if not facts:
            return finalize("c3_memory", {"action": action},
                            "[memory:export] 0 facts to export", "0")
        # Sort by relevance_count desc, then recency
        facts.sort(key=lambda f: (f.get("relevance_count", 0), f.get("last_accessed_at") or ""), reverse=True)
        # Group by category
        by_cat: dict = {}
        for f in facts:
            by_cat.setdefault(f.get("category", "general"), []).append(f)
        lines = ["# C3 Memory Export", ""]
        for cat, entries in sorted(by_cat.items()):
            lines.append(f"## {cat}")
            lines.append("")
            for e in entries:
                lines.append(f"- {e['fact']}")
            lines.append("")
        md = "\n".join(lines).rstrip() + "\n"
        return finalize("c3_memory", {"action": action}, md, f"{len(facts)}f")

    if action == "consolidate":
        if not hasattr(svc, "auto_memory"):
            return finalize("c3_memory", {"action": action},
                            "[memory:consolidate] auto_memory not available", "skip")
        stats = svc.auto_memory.consolidate()
        lines = [
            f"[memory:consolidate] done",
            f"  Merged: {stats['merged']} duplicate pairs",
            f"  Archived: {stats['archived']} stale auto-facts",
            f"  Remaining: {stats['total']} facts",
        ]
        return finalize("c3_memory", {"action": action},
                        "\n".join(lines), f"m{stats['merged']}a{stats['archived']}")

    return f"[memory:error] Unknown action: {action}"
