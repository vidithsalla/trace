"""Human review ledger, claim revisions, and evidence-drift detection (PRD sections 5.3, 7.4, 9).

- Review events are append-only. ``claims`` holds a projection guarded by optimistic
  concurrency: expected revision + evidence digest + review sequence must all match.
- A new version of a cited document makes the claim's basis ``STALE_SOURCE`` (deterministic).
- A new or revised document that *might* matter raises ``POTENTIAL_NEW_EVIDENCE`` (a lexical
  candidate detector; it can miss things and never asserts that a finding is false).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.claims import Claim, ClaimEvidence, ClaimRevision, CoverageAlert, ReviewEvent
from app.models.domain import utcnow
from app.models.evidence import DocumentVersion, SourceSpan
from app.services import retrieval_v3
from app.services.llm.client import CallBudget, LLMError
from app.services.llm.engine import ClaimEngine, get_claim_engine

DETECTOR_VERSION = "overlap-v1"
ACTION_TO_STATE = {"accept": "ACCEPTED", "reject": "REJECTED", "unresolved": "UNRESOLVED"}
REASON_CODES = {
    "SOURCE_REVIEWED", "CONDITION_OMITTED", "CONTRADICTED_BY_LATER_SOURCE", "WRONG_ENTITY",
    "INSUFFICIENT_EVIDENCE", "NEEDS_MORE_DOCUMENTS", "OTHER",
}


def _conflict(code: str, **extra) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, {"code": code, **extra})


def lock_claim(db: Session, matter_id: UUID, claim_id: UUID) -> Claim:
    claim = db.scalar(select(Claim).where(Claim.id == claim_id, Claim.matter_id == matter_id)
                      .with_for_update())
    if claim is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, {"code": "CLAIM_NOT_FOUND"})
    return claim


def current_revision(db: Session, claim: Claim) -> ClaimRevision:
    return db.get(ClaimRevision, (claim.id, claim.current_revision))


def _snapshot_state(claim: Claim, revision: ClaimRevision) -> dict:
    return {"claim_revision": claim.current_revision, "review_seq": claim.review_seq,
            "evidence_sha256": revision.evidence_set_sha256, "review_state": claim.review_state,
            "basis_state": claim.basis_state, "coverage_state": claim.coverage_state}


# ---------------------------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------------------------
@dataclass(slots=True)
class ReviewRequest:
    decision: str
    expected_claim_revision: int
    expected_evidence_sha256: str
    expected_review_seq: int
    reason_code: str | None
    note: str | None


def submit_review(db: Session, *, matter_id: UUID, claim_id: UUID, actor_id: UUID,
                  request: ReviewRequest, idempotency_key: str) -> tuple[ReviewEvent, Claim]:
    if request.decision not in ACTION_TO_STATE:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"code": "INVALID_DECISION"})
    if request.reason_code is not None and request.reason_code not in REASON_CODES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"code": "INVALID_REASON_CODE"})
    request_sha = hashlib.sha256(json.dumps(
        {"claim": str(claim_id), **asdict(request)}, sort_keys=True).encode()).hexdigest()

    claim = lock_claim(db, matter_id, claim_id)
    prior = db.scalar(select(ReviewEvent).where(
        ReviewEvent.matter_id == matter_id, ReviewEvent.actor_user_id == actor_id,
        ReviewEvent.idempotency_key == idempotency_key))
    if prior is not None:
        if prior.request_sha256 != request_sha or prior.claim_id != claim_id:
            raise _conflict("IDEMPOTENCY_KEY_REUSED")
        return prior, claim  # duplicate submission of the same logical action

    revision = current_revision(db, claim)
    state = _snapshot_state(claim, revision)
    if (request.expected_claim_revision != claim.current_revision
            or request.expected_evidence_sha256 != revision.evidence_set_sha256):
        raise _conflict("CLAIM_OR_EVIDENCE_CHANGED", current=state)
    if request.expected_review_seq != claim.review_seq:
        raise _conflict("REVIEW_STATE_CHANGED", current=state)
    if request.decision == "accept":
        if revision.source_gate_state != "VERIFIED":
            raise _conflict("SOURCE_NOT_VERIFIED", current=state)
        if claim.basis_state != "CURRENT":
            raise _conflict("STALE_BASIS", current=state)
        if claim.coverage_state != "CURRENT":
            raise _conflict("COVERAGE_OUTDATED", current=state)

    event = ReviewEvent(
        matter_id=matter_id, claim_id=claim.id, claim_revision=claim.current_revision,
        evidence_set_sha256=revision.evidence_set_sha256, actor_user_id=actor_id,
        action=request.decision.upper(), reason_code=request.reason_code, note=request.note,
        event_seq=claim.review_seq + 1, idempotency_key=idempotency_key, request_sha256=request_sha,
    )
    db.add(event)
    claim.review_seq += 1
    claim.review_state = ACTION_TO_STATE[request.decision]
    claim.updated_at = utcnow()
    db.flush()
    return event, claim


# ---------------------------------------------------------------------------------------------
# New revisions (human edit, or system re-check against the current corpus)
# ---------------------------------------------------------------------------------------------
def revise_claim(db: Session, *, matter_id: UUID, claim_id: UUID, actor_id: UUID,
                 expected_revision: int, new_text: str | None, idempotency_key: str,
                 engine: ClaimEngine | None = None) -> Claim:
    """Create revision n+1. Edits keep the evidence set; re-checks re-retrieve against the
    current corpus. Either way relations are re-assessed and the review decision resets."""
    from app.services.analysis import _pack_item, _persist_claim_revision
    from app.services.evidence_versions import create_snapshot

    claim = lock_claim(db, matter_id, claim_id)
    if expected_revision != claim.current_revision:
        raise _conflict("CLAIM_OR_EVIDENCE_CHANGED", current_revision=claim.current_revision)
    previous = current_revision(db, claim)
    claim_text = (new_text or previous.text).strip()
    if not 3 <= len(claim_text) <= 600:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"code": "INVALID_CLAIM_TEXT"})
    action = "EDIT" if new_text else "RECHECK"
    snapshot = create_snapshot(db, matter_id, actor_id)
    profile = retrieval_v3.resolve_profile(None)

    if action == "EDIT":
        rows = db.scalars(select(ClaimEvidence).where(
            ClaimEvidence.claim_id == claim.id, ClaimEvidence.claim_revision == previous.revision)).all()
        span_ids = [r.source_span_id for r in rows]
        cited_ids = {r.source_span_id for r in rows if r.cited_by_model}
        snapshot_id = previous.corpus_snapshot_id if claim.basis_state == "CURRENT" else snapshot.id
    else:
        primary = retrieval_v3.retrieve(db, matter_id=matter_id, snapshot_id=snapshot.id,
                                        query=claim_text, profile=profile, k=6)
        counter = retrieval_v3.counterevidence(db, matter_id=matter_id, snapshot_id=snapshot.id,
                                               claim=claim_text, profile=profile, k=6,
                                               exclude=[c.source_span_id for c in primary])
        span_ids = list(dict.fromkeys([c.source_span_id for c in primary + counter]))
        cited_ids = {c.source_span_id for c in primary[:2]}
        snapshot_id = snapshot.id

    items = []
    for index, span_id in enumerate(span_ids[:12]):
        span = db.get(SourceSpan, span_id)
        items.append(_pack_item(db, f"ev_{index + 1:02d}", span,
                                "primary" if span_id in cited_ids else "counterevidence"))
    engine = engine or get_claim_engine(settings)
    budget = CallBudget(2)
    try:
        from app.services.llm.contracts import EvidencePack

        assessment = engine.assess_support(claim_text, EvidencePack(tuple(items)), budget)
    except LLMError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, {"code": exc.code}) from exc

    new_number = claim.current_revision + 1
    _persist_claim_revision(
        db, claim=claim, revision=new_number, text=claim_text, snapshot_id=snapshot_id,
        assess_items=items, cited_refs={i.ref for i in items if i.source_span_id in cited_ids},
        unknown_refs=[], relations={r.evidence_ref: r for r in assessment.relations},
        model_overall=assessment.overall, open_questions=previous.open_questions,
        coverage={"assessed_spans": len(items), "exhaustive": False, "trigger": action.lower()},
        actor_type="human" if action == "EDIT" else "system", user_id=actor_id,
        change_reason="edited by reviewer" if action == "EDIT" else "re-checked against current sources",
    )
    db.add(ReviewEvent(
        matter_id=matter_id, claim_id=claim.id, claim_revision=new_number,
        evidence_set_sha256=db.get(ClaimRevision, (claim.id, new_number)).evidence_set_sha256,
        actor_user_id=actor_id, action=action, reason_code=None, note=None,
        event_seq=claim.review_seq + 1, idempotency_key=idempotency_key,
        request_sha256=hashlib.sha256(f"{claim.id}:{action}:{claim_text}".encode()).hexdigest(),
    ))
    was_reviewed = claim.review_state != "UNREVIEWED"
    claim.current_revision = new_number
    claim.review_seq += 1
    claim.review_state = "UNREVIEWED"  # a decision never carries over to a different revision
    if action == "RECHECK" or snapshot_id == snapshot.id:
        claim.basis_state = "CURRENT"
        claim.coverage_state = "CURRENT"
        _resolve_alerts(db, claim, actor_id, kinds=("STALE_SOURCE", "POTENTIAL_NEW_EVIDENCE"))
    if was_reviewed and action == "EDIT":
        db.add(CoverageAlert(matter_id=matter_id, claim_id=claim.id, claim_revision=new_number,
                             kind="STALE_CLAIM", detail={"previous_revision": previous.revision},
                             detector_version=DETECTOR_VERSION))
    claim.updated_at = utcnow()
    db.flush()
    return claim


def _resolve_alerts(db: Session, claim: Claim, actor_id: UUID | None, kinds: tuple[str, ...]) -> None:
    for alert in db.scalars(select(CoverageAlert).where(
            CoverageAlert.claim_id == claim.id, CoverageAlert.status == "OPEN",
            CoverageAlert.kind.in_(kinds))):
        alert.status = "RESOLVED"
        alert.resolved_at = utcnow()
        alert.resolved_by = actor_id


def dismiss_alert(db: Session, *, matter_id: UUID, alert_id: UUID, actor_id: UUID) -> CoverageAlert:
    alert = db.scalar(select(CoverageAlert).where(CoverageAlert.id == alert_id,
                                                  CoverageAlert.matter_id == matter_id))
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, {"code": "ALERT_NOT_FOUND"})
    if alert.kind == "STALE_SOURCE":
        raise _conflict("STALE_SOURCE_REQUIRES_RECHECK")
    claim = lock_claim(db, matter_id, alert.claim_id)
    alert.status = "DISMISSED"
    alert.resolved_at = utcnow()
    alert.resolved_by = actor_id
    db.flush()
    still_open = db.scalar(select(CoverageAlert.id).where(
        CoverageAlert.claim_id == claim.id, CoverageAlert.status == "OPEN",
        CoverageAlert.kind == "POTENTIAL_NEW_EVIDENCE").limit(1))
    if still_open is None:
        claim.coverage_state = "CURRENT"
    db.flush()
    return alert


# ---------------------------------------------------------------------------------------------
# Drift detection, called when a document version is published
# ---------------------------------------------------------------------------------------------
def on_version_published(db: Session, version: DocumentVersion, extraction_id: UUID) -> list[CoverageAlert]:
    alerts: list[CoverageAlert] = []
    stale_claim_ids: set[UUID] = set()
    # 1) Direct invalidation: current claim revisions citing spans of an older version.
    rows = db.execute(text("""
        SELECT DISTINCT c.id, c.current_revision, dv.revision_no
          FROM claims c
          JOIN claim_evidence ce ON ce.claim_id = c.id AND ce.claim_revision = c.current_revision
          JOIN source_spans s ON s.id = ce.source_span_id AND s.matter_id = c.matter_id
          JOIN extraction_versions ev ON ev.id = s.extraction_version_id
          JOIN document_versions dv ON dv.id = ev.document_version_id
         WHERE c.matter_id = :matter AND dv.document_id = :document
           AND dv.revision_no < :revision
    """), {"matter": version.matter_id, "document": version.document_id,
           "revision": version.revision_no}).all()
    for claim_id, claim_revision, old_revision in rows:
        claim = db.get(Claim, claim_id)
        stale_claim_ids.add(claim_id)
        if claim.basis_state == "STALE_SOURCE":
            continue
        claim.basis_state = "STALE_SOURCE"
        claim.updated_at = utcnow()
        alerts.append(_alert(db, claim, claim_revision, "STALE_SOURCE", version, {
            "document_id": str(version.document_id), "superseded_revision": old_revision,
            "new_revision": version.revision_no, "review_state_at_change": claim.review_state,
        }))

    # 2) Coverage candidates: reviewed claims whose terms overlap the new extraction.
    new_spans = db.scalars(select(SourceSpan).where(SourceSpan.extraction_version_id == extraction_id)).all()
    if new_spans:
        span_terms = [(s.id, set(retrieval_v3.query_terms(s.text))) for s in new_spans]
        reviewed = db.execute(select(Claim, ClaimRevision).join(
            ClaimRevision, (ClaimRevision.claim_id == Claim.id)
            & (ClaimRevision.revision == Claim.current_revision)).where(
            Claim.matter_id == version.matter_id, Claim.review_state != "UNREVIEWED")).all()
        for claim, revision in reviewed:
            if claim.id in stale_claim_ids:
                continue
            terms = set(retrieval_v3.query_terms(revision.text))
            anchors = set(retrieval_v3.anchor_terms(revision.text))
            matches = [str(sid) for sid, st in span_terms
                       if len(terms & st) >= 2 and len(terms & st) / max(len(terms), 1) >= 0.4
                       and (not anchors or anchors & st)]
            if matches:
                claim.coverage_state = "POTENTIAL_NEW_EVIDENCE"
                alerts.append(_alert(db, claim, claim.current_revision, "POTENTIAL_NEW_EVIDENCE",
                                     version, {"document_id": str(version.document_id),
                                               "revision": version.revision_no,
                                               "matched_span_ids": matches[:5]}))
    db.flush()
    return [a for a in alerts if a is not None]


def _alert(db: Session, claim: Claim, revision: int, kind: str, version: DocumentVersion,
           detail: dict) -> CoverageAlert | None:
    existing = db.scalar(select(CoverageAlert).where(
        CoverageAlert.claim_id == claim.id, CoverageAlert.kind == kind,
        CoverageAlert.triggering_document_version_id == version.id, CoverageAlert.status == "OPEN"))
    if existing is not None:
        return existing
    alert = CoverageAlert(matter_id=claim.matter_id, claim_id=claim.id, claim_revision=revision,
                          kind=kind, triggering_document_version_id=version.id, detail=detail,
                          detector_version=DETECTOR_VERSION)
    db.add(alert)
    return alert
