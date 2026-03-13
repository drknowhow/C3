"""c3_compress — Token-efficient file summaries (5 modes: map, dense_map, smart, diff, bug_scan)."""

from pathlib import Path

from core import count_tokens


def handle_compress(file_path: str, mode: str, svc,
                    finalize, maybe_facts) -> str:
    # Validate mode
    valid_modes = ("map", "dense_map", "smart", "diff", "bug_scan")
    if mode not in valid_modes:
        # Graceful migration for removed modes
        if mode in ("structure", "outline"):
            mode = "map"
        else:
            return finalize("c3_compress", {"file_path": file_path, "mode": mode},
                            f"[compress:error] Unknown mode '{mode}'. Use: {', '.join(valid_modes)}",
                            "error")

    full = Path(svc.project_path) / file_path
    if not full.exists():
        full = Path(file_path)

    if mode in ("map", "dense_map"):
        if not full.exists():
            return "[file_map:error] not found"
        rel = str(full.resolve().relative_to(Path(svc.project_path).resolve())).replace("\\", "/")
        queued = svc.file_memory.drain_queue()
        completed = []
        failed = []
        for qp in queued[:10]:
            try:
                if svc.file_memory.update(qp):
                    completed.append(qp)
                else:
                    failed.append(qp)
            except Exception:
                failed.append(qp)
        if completed:
            svc.file_memory.complete_updates(completed)
        if failed:
            svc.file_memory.complete_updates(failed, failed=True)
        res = (svc.file_memory.get_or_build_dense_map(rel)
               if mode == "dense_map"
               else svc.file_memory.get_or_build_map(rel))
        try:
            raw_tokens = count_tokens(full.read_text(encoding="utf-8", errors="replace"))
            map_tokens = count_tokens(res)
            summary = f"{raw_tokens}->{map_tokens}tok"
        except Exception:
            summary = "mapped"
        return finalize("c3_compress", {"file_path": file_path, "mode": mode}, res, summary)

    res = svc.compressor.compress_file(str(full), mode)
    if "error" in res:
        return f"Error: {res['error']}"
    header = f"[compress:{res.get('mode', mode)}] {res['original_tokens']}->{res['compressed_tokens']}tok"
    resp = f"{header}\n{res['compressed']}"
    summary = f"{res['original_tokens']}->{res['compressed_tokens']}tok"
    return finalize("c3_compress", {"file_path": file_path},
                    resp + maybe_facts(svc, Path(file_path).name), summary)
