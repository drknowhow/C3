"""Durable facts store with unified semantic identity and retrieval hooks."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from services.text_index import TextIndex


class MemoryStore:
    """Persistent fact store with incremental lexical indexing."""

    def __init__(self, project_path: str, data_dir: str = ".c3/facts", vector_store=None):
        self.project_path = Path(project_path)
        self.data_dir = self.project_path / data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.facts_file = self.data_dir / "facts.json"
        self.vector_store = vector_store
        self.retrieval_broker = None
        self.facts = self._load_facts()
        self._facts_by_id = {fact["id"]: fact for fact in self.facts if fact.get("id")}
        self._text_index = TextIndex()
        self._rebuild_index()

    def set_retrieval_broker(self, broker):
        self.retrieval_broker = broker

    def remember(self, fact: str, category: str = "general", source_session: str = "") -> dict:
        fact_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        entry = {
            "id": fact_id,
            "fact": fact,
            "category": category,
            "source_session": source_session,
            "timestamp": now,
            "last_accessed_at": None,
            "relevance_count": 0,
            "confidence": 1.0,
            "source_quality": "user",
            "lifecycle": "active",
            "vector_id": fact_id,
        }
        self.facts.append(entry)
        self._facts_by_id[fact_id] = entry
        self._index_fact(entry)

        if self.vector_store:
            try:
                self.vector_store.add(
                    fact,
                    category,
                    metadata={
                        "fact_id": fact_id,
                        "source_session": source_session,
                        "source": "memory_store",
                    },
                    record_id=fact_id,
                )
            except Exception:
                pass

        self._save_facts()
        return {"stored": True, "id": fact_id, "total_facts": len(self.facts)}

    def recall(self, query: str, top_k: int = 5) -> list[dict]:
        if not self.facts:
            return []

        lexical_scores = dict(self._text_index.search(query, top_k=max(top_k * 5, 20)))
        semantic_scores = {}
        if self.vector_store:
            try:
                for result in self.vector_store.search(query, top_k=max(top_k * 3, top_k)):
                    fact_id = (result.get("metadata") or {}).get("fact_id") or result.get("id")
                    if fact_id:
                        semantic_scores[fact_id] = max(semantic_scores.get(fact_id, 0.0), float(result.get("score", 0.0)))
            except Exception:
                pass

        candidate_ids = set(lexical_scores) | set(semantic_scores)
        if not candidate_ids:
            return []

        max_lexical = max(lexical_scores.values()) if lexical_scores else 1.0
        max_lexical = max(max_lexical, 0.001)
        now = datetime.now(timezone.utc).isoformat()
        results = []
        for fact_id in candidate_ids:
            fact = self._facts_by_id.get(fact_id)
            if not fact or fact.get("lifecycle") == "archived":
                continue
            lexical = lexical_scores.get(fact_id, 0.0) / max_lexical
            semantic = semantic_scores.get(fact_id, 0.0)
            score = 0.55 * lexical + 0.45 * semantic if semantic_scores else lexical
            results.append({**fact, "score": round(score, 4), "search_method": "hybrid" if semantic_scores else "tfidf"})
        results.sort(key=lambda item: item.get("score", 0.0), reverse=True)
        results = results[:top_k]

        changed = False
        for result in results:
            fact = self._facts_by_id.get(result["id"])
            if not fact:
                continue
            fact["relevance_count"] = int(fact.get("relevance_count", 0)) + 1
            fact["last_accessed_at"] = now
            changed = True
            result["relevance_count"] = fact["relevance_count"]
            result["last_accessed_at"] = now
        if changed:
            self._save_facts()
        return results

    def query_all(self, query: str, top_k: int = 5) -> dict:
        if self.retrieval_broker:
            return self.retrieval_broker.search(query, top_k=top_k)
        return {"facts": self.recall(query, top_k=top_k), "results": []}

    def update_fact(self, fact_id: str, fact: str = "", category: str = "") -> dict:
        entry = self._facts_by_id.get(fact_id)
        if not entry:
            return {"error": "not found", "id": fact_id}
        if fact:
            entry["fact"] = fact
        if category:
            entry["category"] = category
        entry["last_accessed_at"] = datetime.now(timezone.utc).isoformat()
        self._index_fact(entry)
        if self.vector_store and fact:
            try:
                self.vector_store.delete(entry.get("vector_id") or fact_id)
                self.vector_store.add(fact, entry["category"],
                                      metadata={"fact_id": fact_id, "source": "memory_store"},
                                      record_id=fact_id)
            except Exception:
                pass
        self._save_facts()
        return {"updated": True, "id": fact_id}

    def delete_fact(self, fact_id: str) -> dict:
        entry = self._facts_by_id.get(fact_id)
        if not entry:
            return {"error": "not found", "id": fact_id}

        self.facts = [fact for fact in self.facts if fact.get("id") != fact_id]
        self._facts_by_id.pop(fact_id, None)
        self._text_index.remove(fact_id)
        vector_deleted = False
        if self.vector_store:
            try:
                vector_deleted = bool(self.vector_store.delete(entry.get("vector_id") or fact_id).get("deleted"))
            except Exception:
                vector_deleted = False
        self._save_facts()
        return {"deleted": True, "id": fact_id, "vector_deleted": vector_deleted}

    def _index_fact(self, fact: dict):
        doc = " ".join(
            str(part)
            for part in (
                fact.get("fact", ""),
                fact.get("category", ""),
                fact.get("source_quality", ""),
                fact.get("source_session", ""),
            )
            if part
        )
        self._text_index.add_or_update(fact["id"], doc)

    def _rebuild_index(self):
        docs = {}
        for fact in self.facts:
            if not fact.get("id"):
                continue
            docs[fact["id"]] = " ".join(
                str(part)
                for part in (
                    fact.get("fact", ""),
                    fact.get("category", ""),
                    fact.get("source_quality", ""),
                    fact.get("source_session", ""),
                )
                if part
            )
        self._text_index.rebuild(docs)

    def _load_facts(self) -> list:
        if not self.facts_file.exists():
            return []
        try:
            with open(self.facts_file, encoding="utf-8") as handle:
                facts = json.load(handle)
        except Exception:
            return []

        normalized = []
        for fact in facts:
            fact_id = fact.get("id") or uuid.uuid4().hex[:12]
            normalized.append({
                "id": fact_id,
                "fact": fact.get("fact", ""),
                "category": fact.get("category", "general"),
                "source_session": fact.get("source_session", ""),
                "timestamp": fact.get("timestamp", ""),
                "last_accessed_at": fact.get("last_accessed_at"),
                "relevance_count": int(fact.get("relevance_count", 0)),
                "confidence": float(fact.get("confidence", 1.0)),
                "source_quality": fact.get("source_quality", "legacy"),
                "lifecycle": fact.get("lifecycle", "active"),
                "vector_id": fact.get("vector_id") or fact_id,
            })
        return normalized

    def _save_facts(self):
        with open(self.facts_file, "w", encoding="utf-8") as handle:
            json.dump(self.facts, handle, indent=2)
