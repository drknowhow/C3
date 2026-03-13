"""c3_read — Surgical symbol/line extraction from files."""

import json
import re
from pathlib import Path
from typing import Any

from core import count_tokens


def _coerce_list(val: Any) -> list[str] | None:
    """Coerce symbols from string/JSON to list. MCP clients sometimes serialize lists as strings."""
    if val is None:
        return None
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        val = val.strip()
        if val.startswith("["):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, list):
                    return [str(x) for x in parsed]
            except (json.JSONDecodeError, ValueError):
                pass
        if val:
            return [val]
    return None


def handle_read(file_path: str, symbols: Any = None, lines: Any = None,
                include_docstrings: bool = True, svc=None, finalize=None) -> str:
    symbols = _coerce_list(symbols)
    # Multi-file dispatch
    if "," in file_path:
        paths = [p.strip() for p in file_path.split(",") if p.strip()]
        parts = []
        for p in paths:
            result = handle_read(p, symbols=symbols, lines=lines,
                                 include_docstrings=include_docstrings,
                                 svc=svc, finalize=finalize)
            parts.append(result)
        return "\n\n".join(parts)

    full = Path(svc.project_path) / file_path
    if not full.exists():
        full = Path(file_path)
    if not full.exists():
        return f"[read:error] File not found: {file_path}"

    rel_path = str(full.resolve().relative_to(Path(svc.project_path).resolve())).replace("\\", "/")

    # Resolve ranges
    ranges = []
    if lines:
        if isinstance(lines, int):
            line_specs = [lines]
        elif isinstance(lines, (list, tuple)) and len(lines) == 2 and all(isinstance(x, int) for x in lines):
            line_specs = [lines]
        elif isinstance(lines, (list, tuple)):
            line_specs = lines
        else:
            line_specs = []

        for spec in line_specs:
            if isinstance(spec, int):
                ranges.append((spec, spec))
            elif isinstance(spec, (list, tuple)) and len(spec) >= 2:
                ranges.append((int(spec[0]), int(spec[1])))
            elif isinstance(spec, (list, tuple)) and len(spec) == 1:
                ranges.append((int(spec[0]), int(spec[0])))

    # Ensure file_memory index is fresh
    try:
        if svc.file_memory.needs_update(rel_path):
            svc.file_memory.update(rel_path)
    except Exception:
        pass

    raw_text = full.read_text(encoding="utf-8", errors="replace")
    content_lines = raw_text.splitlines()
    full_file_tokens = count_tokens(raw_text)

    if symbols:
        matches = svc.file_memory.get_symbol_ranges(rel_path, symbols, return_matches=True)

        # Check for ambiguity
        disambiguation_msgs = []
        for target in symbols:
            if target.startswith('^') or target in ('<main>', '<globals>', '<imports>'):
                continue
            target_matches = [m for m in matches if m["target"] == target.lower() or m["target"] == target]
            unique_names = set(m["match"] for m in target_matches)
            if len(unique_names) > 1:
                exact = [m for m in target_matches if m["match"].lower() == target.lower()]
                if exact:
                    matches = [m for m in matches
                               if m["target"] != target and m["target"] != target.lower()
                               or m["match"].lower() == target.lower()]
                else:
                    options = ", ".join(
                        f"{m['match']} (L{m['range'][0]}-L{m['range'][1]})" for m in target_matches)
                    disambiguation_msgs.append(
                        f"Ambiguous symbol '{target}'. Did you mean: {options}?")

        if disambiguation_msgs:
            resp = (f"[read:error] Ambiguous symbols found in {file_path}:\n"
                    + "\n".join(disambiguation_msgs)
                    + "\nTry using exact regex (e.g., '^symbol_name$') or the specific symbol name.")
            return finalize("c3_read", {"file": file_path, "symbols": symbols},
                            resp, f"{full_file_tokens}->0tok")

        for m in matches:
            ranges.append(m["range"])

        if '<main>' in symbols or '<globals>' in symbols:
            record = svc.file_memory.get(rel_path)
            if record and "sections" in record:
                covered = set()

                def _mark(secs):
                    for s in secs:
                        covered.update(range(s["line_start"], s["line_end"] + 1))
                        if "children" in s:
                            _mark(s["children"])

                _mark(record["sections"])
                main_ranges = []
                current_start = None
                for i in range(1, len(content_lines) + 1):
                    if i not in covered:
                        if current_start is None:
                            current_start = i
                    else:
                        if current_start is not None:
                            main_ranges.append((current_start, i - 1))
                            current_start = None
                if current_start is not None:
                    main_ranges.append((current_start, len(content_lines)))
                ranges.extend(main_ranges)

    if not ranges and symbols:
        file_map = svc.file_memory.get_or_build_map(rel_path)
        resp = f"[read:{file_path}] symbols not found: {symbols}. Showing file map:\n{file_map}"
        return finalize("c3_read", {"file": file_path, "symbols": symbols},
                        resp, f"{full_file_tokens}->{count_tokens(file_map)}tok")

    if not ranges:
        file_map = svc.file_memory.get_or_build_map(rel_path)
        preview_end = min(50, len(content_lines))
        preview = "\n".join(content_lines[:preview_end])
        preview_tok = count_tokens(preview)
        map_tok = count_tokens(file_map)
        resp = (f"[read:{file_path}] no targets specified. Map + first {preview_end} lines "
                f"({map_tok}+{preview_tok}tok)\n{file_map}\n--- L1-L{preview_end} ---\n{preview}")
        return finalize("c3_read", {"file": file_path},
                        resp, f"{full_file_tokens}->{map_tok + preview_tok}tok")
    else:
        # Sort and merge overlapping ranges
        ranges.sort()
        merged = []
        if ranges:
            curr_start, curr_end = ranges[0]
            for next_start, next_end in ranges[1:]:
                if next_start <= curr_end + 1:
                    curr_end = max(curr_end, next_end)
                else:
                    merged.append((curr_start, curr_end))
                    curr_start, curr_end = next_start, next_end
            merged.append((curr_start, curr_end))
        ranges = merged
        header = f"[read:{file_path}] symbols:{symbols or []} lines:{len(ranges)} ranges"

    parts = []
    for start, end in ranges:
        s_idx = max(0, start - 1)
        e_idx = min(len(content_lines), end)
        chunk = content_lines[s_idx:e_idx]
        if len(ranges) > 1:
            parts.append(f"--- L{start}-L{end} ---")
        parts.extend(chunk)

    final_content = "\n".join(parts)
    tokens = count_tokens(final_content)
    summary = f"{full_file_tokens}->{tokens}tok" if tokens < full_file_tokens else f"{tokens}tok"
    resp = f"{header} ({tokens}tok)\n{final_content}"
    return finalize("c3_read", {"file": file_path, "symbols": symbols}, resp, summary)
