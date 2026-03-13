#!/usr/bin/env python3
"""PostToolUse/AfterTool hook for mcp__c3__c3_read.

After c3_read completes on a code/config file, immediately reminds the model
to call Read(limit=1) to satisfy the Edit tool's prerequisite.

This keeps c3_read as the primary read mechanism (token-efficient) while
ensuring Edit never fails due to the missing native-Read check.

Supports both Claude Code (PostToolUse) and Gemini CLI (AfterTool).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from cli._hook_utils import emit_additional_context  # noqa: E402

EDITABLE_EXTS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
    ".rb", ".c", ".cpp", ".h", ".cs", ".html", ".css",
    ".json", ".yaml", ".yml", ".toml", ".sql", ".md", ".txt",
    ".sh", ".bat", ".ps1",
}


def main():
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return

        data = json.loads(raw)
        if data.get("tool_name") != "mcp__c3__c3_read":
            return

        # Detect IDE format: Gemini wraps tool_response in a dict
        is_gemini = isinstance(data.get("tool_response", ""), dict)

        tool_input = data.get("tool_input", {})
        file_path = (tool_input.get("file_path") or "").strip()
        if not file_path:
            return

        # Support comma-separated multi-file reads
        paths = [p.strip() for p in file_path.split(",") if p.strip()]
        editable = [p for p in paths if Path(p).suffix.lower() in EDITABLE_EXTS]
        if not editable:
            return

        reads = " ".join(f'Read(file_path="{p}", limit=1)' for p in editable)
        emit_additional_context(
            f"[c3:edit-unlock] c3_read done on {len(editable)} file(s). "
            f"Call {reads} now to satisfy the Edit tool prerequisite (~5 tokens each).",
            is_gemini,
        )
    except Exception:
        pass


if __name__ == "__main__":
    main()
