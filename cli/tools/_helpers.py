"""Shared helpers for tool handlers."""

from core import count_tokens


def maybe_related_facts(svc, topic: str, top_k: int = 3, width: int = 100) -> str:
    """Append related facts if enabled."""
    hits = svc.memory.recall(topic, top_k=top_k)
    if not hits:
        return ""
    return "\n\n[Related facts]\n" + "\n".join(
        [f"[{f['category']}] {f['fact'][:width]}" for f in hits[:top_k]])
