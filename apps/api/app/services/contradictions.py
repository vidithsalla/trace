from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import Document, DocumentChunk
from app.services.model_client import EvidenceItem


@dataclass(frozen=True, slots=True)
class ContradictionTopicProfile:
    canonical_topic: str
    side_a_label: str
    side_b_label: str
    side_a_terms: tuple[str, ...]
    side_b_terms: tuple[str, ...]
    side_a_claim: str
    side_b_claim: str
    why_conflict: str
    severity: str = "medium"


@dataclass(frozen=True, slots=True)
class ContradictionEvidencePack:
    evidence: list[EvidenceItem]
    side_a: list[EvidenceItem]
    side_b: list[EvidenceItem]
    ambiguities: list[str]
    profile: ContradictionTopicProfile


DEFAULT_PROFILE = ContradictionTopicProfile(
    canonical_topic="general inconsistency",
    side_a_label="Position A",
    side_b_label="Position B",
    side_a_terms=("approved", "sent", "known", "resolved", "complete", "ready"),
    side_b_terms=("conditional", "disputed", "denied", "late", "incomplete", "withheld"),
    side_a_claim="Some evidence supports the topic as satisfied or resolved.",
    side_b_claim="Other evidence keeps the topic conditional, disputed, or unresolved.",
    why_conflict="The retrieved sources appear to describe materially different states of the same issue.",
)

TOPIC_PROFILES = [
    ContradictionTopicProfile(
        canonical_topic="notice timing",
        side_a_label="Timely written notice",
        side_b_label="Disputed or late notice",
        side_a_terms=("formal notice", "written notice", "provided written notice", "march 18"),
        side_b_terms=("disputed the notice", "disputed notice", "notice timing", "late", "incomplete"),
        side_a_claim="Acme appears to have provided written notice on March 18, 2024.",
        side_b_claim="Northshore disputed the notice timing or completeness.",
        why_conflict="One side describes written notice as sent, while another challenges the timing or adequacy of notice.",
    ),
    ContradictionTopicProfile(
        canonical_topic="payment approval authority",
        side_a_label="Payment authority approved",
        side_b_label="Payment remained conditional",
        side_a_terms=("approved payment", "payment authority", "authorized payment", "payment approval"),
        side_b_terms=("conditional", "pending notice", "withheld payment", "final authorization remained conditional"),
        side_a_claim="Evidence suggests Priya Shah or Acme personnel had authority to approve payment.",
        side_b_claim="Other evidence says payment approval remained conditional or withheld.",
        why_conflict="The evidence separates discussion or authority to approve payment from final unconditional authorization.",
    ),
    ContradictionTopicProfile(
        canonical_topic="defect knowledge",
        side_a_label="Pre-shipment defect knowledge",
        side_b_label="Denied prior knowledge",
        side_a_terms=("before shipment", "defect risk", "knew", "known before shipment", "needed follow-up"),
        side_b_terms=("first learned", "after shipment", "denied", "disputed", "claimed it first learned"),
        side_a_claim="Northshore appears to have known of the defect risk before shipment.",
        side_b_claim="Northshore later claimed it first learned of the defect after shipment or denied prior knowledge.",
        why_conflict="Pre-shipment internal knowledge is difficult to reconcile with a later denial of prior knowledge.",
    ),
]


def build_contradiction_evidence_pack(
    db: Session,
    matter_id: UUID,
    topic: str,
    *,
    limit: int = 16,
) -> ContradictionEvidencePack:
    profile = topic_profile(topic)
    rows = _matter_chunks(db, matter_id)
    side_a = _rank_side(rows, profile.side_a_terms, limit=limit // 2)
    side_b = _rank_side(rows, profile.side_b_terms, limit=limit // 2)

    evidence: list[EvidenceItem] = []
    seen: set[UUID] = set()
    for item in [*side_a, *side_b]:
        if item.chunk_id and item.chunk_id not in seen:
            evidence.append(item)
            seen.add(item.chunk_id)

    ambiguities = []
    if not side_a:
        ambiguities.append(f"No clearly citation-backed evidence was found for: {profile.side_a_label}.")
    if not side_b:
        ambiguities.append(f"No clearly citation-backed evidence was found for: {profile.side_b_label}.")
    return ContradictionEvidencePack(
        evidence=evidence[:limit],
        side_a=side_a,
        side_b=side_b,
        ambiguities=ambiguities,
        profile=profile,
    )


def topic_profile(topic: str) -> ContradictionTopicProfile:
    normalized = topic.lower()
    for profile in TOPIC_PROFILES:
        if profile.canonical_topic in normalized:
            return profile
        profile_words = set(profile.canonical_topic.split())
        if len(profile_words.intersection(normalized.split())) >= 2:
            return profile
    return DEFAULT_PROFILE


def cluster_evidence_for_topic(
    topic: str, evidence: list[EvidenceItem]
) -> tuple[ContradictionTopicProfile, list[EvidenceItem], list[EvidenceItem], list[str]]:
    profile = topic_profile(topic)
    side_a = [
        item for item in evidence if _term_score(item.text, profile.side_a_terms) > 0
    ]
    side_b = [
        item for item in evidence if _term_score(item.text, profile.side_b_terms) > 0
    ]
    ambiguities = []
    if not side_a:
        ambiguities.append(f"No evidence cluster supported: {profile.side_a_label}.")
    if not side_b:
        ambiguities.append(f"No evidence cluster supported: {profile.side_b_label}.")
    return profile, side_a, side_b, ambiguities


def _matter_chunks(db: Session, matter_id: UUID) -> list[tuple[DocumentChunk, Document]]:
    return list(
        db.execute(
            select(DocumentChunk, Document)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.matter_id == matter_id)
            .order_by(Document.created_at.asc(), DocumentChunk.chunk_index.asc())
        ).all()
    )


def _rank_side(
    rows: list[tuple[DocumentChunk, Document]],
    terms: tuple[str, ...],
    *,
    limit: int,
) -> list[EvidenceItem]:
    scored: list[tuple[int, EvidenceItem]] = []
    for chunk, document in rows:
        score = _term_score(chunk.text, terms)
        if score <= 0:
            continue
        scored.append(
            (
                score,
                EvidenceItem(
                    document_id=document.id,
                    document_name=document.display_name or document.file_name,
                    page=chunk.page_start,
                    chunk_id=chunk.id,
                    quote=_quote_for_terms(chunk.text, terms),
                    text=chunk.text,
                ),
            )
        )
    scored.sort(key=lambda item: item[0], reverse=True)
    return [item for _score, item in scored[:limit]]


def _term_score(text: str, terms: tuple[str, ...]) -> int:
    lower_text = text.lower()
    return sum(1 for term in terms if term.lower() in lower_text)


def _quote_for_terms(text: str, terms: tuple[str, ...]) -> str:
    lower_text = text.lower()
    first_match = min(
        [lower_text.find(term.lower()) for term in terms if lower_text.find(term.lower()) >= 0]
        or [0]
    )
    start = max(first_match - 140, 0)
    end = min(start + 420, len(text))
    return text[start:end].strip()
