"""The 'R' in RAG: retrieve pre-approved grounding snippets.

A dependency-free TF-IDF cosine retriever over the knowledge base. Retrieval is
scoped to the analytes present in the report and the tier the rule engine
assigned, then ranked by lexical similarity to a query built from those analytes.
Only medical-director-approved snippets are eligible. The point is that the
explanation is *grounded* in vetted text, never free-form generation.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

from .corpus import Corpus, get_corpus
from .models import Tier

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


@dataclass
class Snippet:
    id: str
    analyte: str
    text: str
    score: float = 0.0


class Retriever:
    def __init__(self, corpus: Corpus) -> None:
        self.docs = [d for d in corpus["documents"]] if isinstance(corpus, dict) else corpus.knowledge["documents"]
        self._tokens = {d["id"]: _tokenize(d["text"] + " " + d.get("analyte", "")) for d in self.docs}
        self._by_id = {d["id"]: d for d in self.docs}

        # IDF over the whole knowledge base.
        df: Counter = Counter()
        for toks in self._tokens.values():
            for t in set(toks):
                df[t] += 1
        n = max(len(self.docs), 1)
        self._idf = {t: math.log((n + 1) / (c + 1)) + 1.0 for t, c in df.items()}

    def _vec(self, tokens: list[str]) -> dict[str, float]:
        tf = Counter(tokens)
        total = max(sum(tf.values()), 1)
        return {t: (c / total) * self._idf.get(t, math.log(len(self.docs) + 1) + 1.0) for t, c in tf.items()}

    @staticmethod
    def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
        if not a or not b:
            return 0.0
        common = set(a) & set(b)
        dot = sum(a[t] * b[t] for t in common)
        na = math.sqrt(sum(v * v for v in a.values()))
        nb = math.sqrt(sum(v * v for v in b.values()))
        return dot / (na * nb) if na and nb else 0.0

    def retrieve(self, analytes: list[str], tier: Tier, k: int = 3) -> list[Snippet]:
        """Top-k approved snippets for these analytes at this tier."""
        want = {a.strip().lower() for a in analytes}
        tier_val = tier.value
        query_vec = self._vec(_tokenize(" ".join(analytes) + " " + tier_val))

        results: list[Snippet] = []
        for doc in self.docs:
            if not doc.get("approved", False):
                continue
            if tier_val not in doc.get("tiers", []):
                continue
            doc_analyte = doc.get("analyte", "").strip().lower()
            if doc_analyte != "*" and doc_analyte not in want:
                continue
            score = self._cosine(query_vec, self._vec(self._tokens[doc["id"]]))
            # Small boost for an exact analyte match over a generic "*" snippet.
            if doc_analyte != "*":
                score += 0.1
            results.append(Snippet(id=doc["id"], analyte=doc.get("analyte", ""), text=doc["text"], score=score))

        results.sort(key=lambda s: s.score, reverse=True)
        return results[:k]


@lru_cache(maxsize=1)
def get_retriever() -> Retriever:
    return Retriever(get_corpus())
