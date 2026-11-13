"""Span-level retrieval inside a pinned corpus snapshot.

Every query filters by matter and snapshot membership in SQL before any text is returned, so
text outside the authorized, pinned corpus never reaches Python, the model, or the UI.
Vector search runs in PostgreSQL with pgvector's cosine-distance operator ``<=>``.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.embeddings import LocalHashEmbeddingClient, get_embedding_client

RRF_K = 60

PROFILES: dict[str, dict] = {
    "lexical_v1": {"lexical": True, "semantic": None},
    "hash_hybrid_baseline": {"lexical": True, "semantic": "hash-v1"},
    "semantic_exact_v2": {"lexical": False, "semantic": "minilm-l6-v2-ollama"},
    "semantic_hybrid_v2": {"lexical": True, "semantic": "minilm-l6-v2-ollama"},
}

_STOP = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "by", "for", "with", "was", "were", "is",
    "are", "be", "been", "it", "this", "that", "what", "which", "who", "when", "how", "did", "do",
    "does", "has", "have", "had", "any", "could", "would", "should", "can", "after", "before",
    "there", "their", "its", "as", "at", "from", "into", "about",
}
# Words that signal a qualification, reversal or dispute. Matched with a regex on raw span text
# because PostgreSQL's english config treats several of them ("not", "no", "but") as stopwords.
CHALLENGE_TERMS = (
    "not", "no", "never", "hold", "held", "pending", "unless", "subject", "condition",
    "conditional", "conditions", "only", "except", "exception", "however", "but", "correction",
    "corrected", "revised", "withdraw", "withdrawn", "revoke", "revoked", "rescind", "cancel",
    "cancelled", "dispute", "disputed", "cannot", "unable", "denied", "deny", "reject", "rejected",
    "until", "provided", "notwithstanding", "missing", "never", "instead", "unpaid", "late",
)
CHALLENGE_REGEX = r"\m(" + "|".join(sorted(set(CHALLENGE_TERMS))) + r")\M"


@dataclass(frozen=True, slots=True)
class Candidate:
    source_span_id: UUID
    score: float
    retriever: str
    rank: int


def resolve_profile(name: str | None = None) -> str:
    profile = (name or settings.retrieval_profile or "auto").strip()
    if profile == "auto":
        return "semantic_hybrid_v2" if settings.embedding_provider == "ollama" else "hash_hybrid_baseline"
    if profile not in PROFILES:
        raise ValueError(f"unknown retrieval profile {profile!r}")
    return profile


def profile_config_sha256(profile: str, k: int) -> str:
    payload = {"profile": profile, **PROFILES[profile], "k": k, "rrf_k": RRF_K,
               "challenge_terms": sorted(set(CHALLENGE_TERMS))}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def query_terms(query: str) -> list[str]:
    seen: list[str] = []
    for token in re.findall(r"[a-z0-9]+", query.lower()):
        if token not in _STOP and len(token) > 1 and token not in seen:
            seen.append(token)
    return seen[:24]


def anchor_terms(claim: str) -> list[str]:
    """Identifiers and specific nouns that any counterevidence must share with the claim."""
    terms = query_terms(claim)
    anchors = [t for t in terms if any(c.isdigit() for c in t)]
    anchors += [t.lower() for t in re.findall(r"\b[A-Z][a-z]{2,}\b", claim)
                if t.lower() not in _STOP and t.lower() not in anchors]
    return anchors or terms[:4]


def _or_tsquery(terms: Sequence[str]) -> str:
    return " | ".join(terms)


def _embedder_for(profile_id: str):
    if profile_id == "hash-v1":
        return LocalHashEmbeddingClient()
    embedder = get_embedding_client("ollama") if profile_id == "minilm-l6-v2-ollama" else None
    if embedder is None:
        raise ValueError(f"no runtime embedder for profile {profile_id}")
    return embedder


def _scope(pre: str = "", join: str = "") -> str:
    """FROM/WHERE clause restricting spans to one matter and one pinned snapshot."""
    return f"""
  FROM {pre}source_spans s {join}
  JOIN corpus_snapshot_members m
    ON m.extraction_version_id = s.extraction_version_id AND m.matter_id = s.matter_id
 WHERE m.snapshot_id = :snapshot AND s.matter_id = :matter
   AND NOT (s.id = ANY(CAST(:exclude AS uuid[])))
"""


def lexical(db: Session, *, matter_id: UUID, snapshot_id: UUID, query: str, k: int,
            exclude: Sequence[UUID] = ()) -> list[Candidate]:
    terms = query_terms(query)
    if not terms:
        return []
    rows = db.execute(text(f"""
        SELECT s.id, ts_rank_cd(s.search, q) AS score
        {_scope(pre="to_tsquery('english', :tsq) q, ")}
          AND s.search @@ q
        ORDER BY score DESC, s.id
        LIMIT :k"""),
        {"tsq": _or_tsquery(terms), "snapshot": snapshot_id, "matter": matter_id, "k": k,
         "exclude": [str(e) for e in exclude]},
    ).all()
    return [Candidate(r[0], float(r[1]), "lexical", i + 1) for i, r in enumerate(rows)]


def semantic(db: Session, *, matter_id: UUID, snapshot_id: UUID, query: str, k: int,
             profile_id: str, exclude: Sequence[UUID] = ()) -> list[Candidate]:
    vector = _embedder_for(profile_id).embed_texts([query])[0]
    rows = db.execute(text(f"""
        SELECT s.id, 1 - (e.embedding <=> CAST(:qv AS vector)) AS score
        {_scope(join="JOIN source_embeddings e ON e.source_span_id = s.id AND e.matter_id = s.matter_id")}
          AND e.embedding_profile_id = :profile
        ORDER BY e.embedding <=> CAST(:qv AS vector), s.id
        LIMIT :k"""),
        {"qv": "[" + ",".join(f"{v:.7f}" for v in vector) + "]", "profile": profile_id,
         "snapshot": snapshot_id, "matter": matter_id, "k": k,
         "exclude": [str(e) for e in exclude]},
    ).all()
    return [Candidate(r[0], float(r[1]), f"semantic:{profile_id}", i + 1) for i, r in enumerate(rows)]


def challenge(db: Session, *, matter_id: UUID, snapshot_id: UUID, claim: str, k: int,
              exclude: Sequence[UUID] = ()) -> list[Candidate]:
    """Spans sharing the claim's anchors that also contain qualification/reversal language."""
    anchors = anchor_terms(claim)
    if not anchors:
        return []
    rows = db.execute(text(f"""
        SELECT s.id, ts_rank_cd(s.search, q) AS score
        {_scope(pre="to_tsquery('english', :tsq) q, ")}
          AND s.search @@ q
          AND s.text ~* :challenge
        ORDER BY score DESC, s.id
        LIMIT :k"""),
        {"tsq": _or_tsquery(anchors), "challenge": CHALLENGE_REGEX, "snapshot": snapshot_id,
         "matter": matter_id, "k": k, "exclude": [str(e) for e in exclude]},
    ).all()
    return [Candidate(r[0], float(r[1]), "challenge", i + 1) for i, r in enumerate(rows)]


def fuse(*ranked: list[Candidate], k: int) -> list[Candidate]:
    scores: dict[UUID, float] = {}
    retrievers: dict[UUID, list[str]] = {}
    for candidates in ranked:
        for c in candidates:
            scores[c.source_span_id] = scores.get(c.source_span_id, 0.0) + 1.0 / (RRF_K + c.rank)
            retrievers.setdefault(c.source_span_id, []).append(c.retriever)
    ordered = sorted(scores.items(), key=lambda item: (-item[1], str(item[0])))[:k]
    return [Candidate(span_id, score, "+".join(retrievers[span_id]), i + 1)
            for i, (span_id, score) in enumerate(ordered)]


def retrieve(db: Session, *, matter_id: UUID, snapshot_id: UUID, query: str, profile: str,
             k: int = 8, exclude: Sequence[UUID] = ()) -> list[Candidate]:
    config = PROFILES[profile]
    ranked: list[list[Candidate]] = []
    pool = max(k * 3, 20)
    if config["lexical"]:
        ranked.append(lexical(db, matter_id=matter_id, snapshot_id=snapshot_id, query=query,
                              k=pool, exclude=exclude))
    if config["semantic"]:
        ranked.append(semantic(db, matter_id=matter_id, snapshot_id=snapshot_id, query=query,
                               k=pool, profile_id=config["semantic"], exclude=exclude))
    if len(ranked) == 1:
        return ranked[0][:k]
    return fuse(*ranked, k=k)


def counterevidence(db: Session, *, matter_id: UUID, snapshot_id: UUID, claim: str,
                    profile: str, k: int = 6, exclude: Sequence[UUID] = ()) -> list[Candidate]:
    ranked = [challenge(db, matter_id=matter_id, snapshot_id=snapshot_id, claim=claim, k=k * 2,
                        exclude=exclude)]
    semantic_profile = PROFILES[profile]["semantic"]
    if semantic_profile:
        ranked.append(semantic(db, matter_id=matter_id, snapshot_id=snapshot_id, query=claim,
                               k=k * 2, profile_id=semantic_profile, exclude=exclude))
    return fuse(*ranked, k=k) if len(ranked) > 1 else ranked[0][:k]


def snapshot_span_count(db: Session, matter_id: UUID, snapshot_id: UUID) -> int:
    return db.execute(text(f"SELECT count(*) {_scope()}"),
                      {"snapshot": snapshot_id, "matter": matter_id, "exclude": []}).scalar_one()
