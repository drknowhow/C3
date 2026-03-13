"""Backward-compat shim — LLMCache now lives in ollama_client.py."""
from services.ollama_client import LLMCache

__all__ = ["LLMCache"]
