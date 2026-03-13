"""Shared utilities for C3 hook scripts — supports Claude Code and Gemini CLI."""
import json
import sys

# Map Gemini CLI built-in tool names → canonical Claude Code equivalents
GEMINI_TOOL_MAP = {
    "run_shell_command": "Bash",
    "read_file": "Read",
    "list_directory": "FindFiles",
    "find_files": "FindFiles",
    "grep": "SearchText",
    "search_in_files_content": "SearchText",
    "find_in_files": "SearchText",
}


def normalize_tool_name(tool_name: str) -> str:
    """Normalize Gemini CLI tool names to their Claude Code equivalents."""
    return GEMINI_TOOL_MAP.get(tool_name, tool_name)


def get_tool_output(data: dict) -> tuple:
    """Extract the output text and detect IDE format from hook stdin data.

    Returns (output_text: str, is_gemini: bool).
    Claude passes tool_response as a plain string.
    Gemini wraps it in {llmContent, returnDisplay}.
    """
    resp = data.get("tool_response", "")
    if isinstance(resp, dict):
        content = resp.get("llmContent", "") or resp.get("returnDisplay", "")
        if isinstance(content, list):
            # llmContent can be a list of content-part dicts like {text: "..."}
            content = "\n".join(
                p.get("text", str(p)) if isinstance(p, dict) else str(p)
                for p in content
            )
        return str(content) if content is not None else "", True
    return resp if isinstance(resp, str) else "", False


def get_tool_input_path(data: dict) -> str:
    """Extract file path from tool_input, handling both Claude (file_path) and Gemini (path)."""
    tool_input = data.get("tool_input", {})
    return tool_input.get("file_path", "") or tool_input.get("path", "")


def emit_additional_context(text: str, is_gemini: bool) -> None:
    """Write additionalContext JSON to stdout in the correct format for the IDE."""
    if is_gemini:
        sys.stdout.write(json.dumps({"hookSpecificOutput": {"additionalContext": text}}))
    else:
        sys.stdout.write(json.dumps({"additionalContext": text}))


def emit_filtered_output(filtered: str, is_gemini: bool) -> None:
    """Write filtered tool output to stdout.

    Claude Code: replaces the tool result entirely via tool_result.
    Gemini CLI: no direct replacement — appends as additionalContext instead.
    """
    if is_gemini:
        sys.stdout.write(json.dumps({"hookSpecificOutput": {"additionalContext": filtered}}))
    else:
        sys.stdout.write(json.dumps({"tool_result": filtered}))
