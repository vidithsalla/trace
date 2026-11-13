"""V3 evidence-review API: investigations, claims, reviews, changes, sources, packets.

Identity and matter scope always come from the session and membership table; IDs in the
request are selectors, never grants. Every query is filtered by ``matter_id``.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.models.claims import (
    AnalysisRun,
    Claim,
    ClaimEvidence,
    ClaimRevision,
    CoverageAlert,
    PacketExport,
    ReviewEvent,
)
from app.models.domain import Document, User
from app.models.evidence import DocumentVersion, ExtractionPage, ExtractionVersion, SourceSpan
from app.services import analysis, change_control, packets
from app.services.audit import record_audit_event
from app.services.matter import ensure_matter_access, ensure_matter_role

router = APIRouter()

REVIEW_ROLES = frozenset({"admin", "attorney", "reviewer"})
EXPORT_ROLES = frozenset({"admin", "attorney", "reviewer"})


def require_trace_header(x_trace_request: str | None = Header(default=None)) -> None:
    """CSRF defence for mutations: a custom header cannot be sent cross-site without CORS."""
    if x_trace_request != "1":
        raise HTTPException(status.HTTP_403_FORBIDDEN, {"code": "MISSING_CSRF_HEADER"})


def _key(idempotency_key: str | None) -> str:
    if not idempotency_key or not 8 <= len(idempotency_key) <= 128:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, {"code": "IDEMPOTENCY_KEY_REQUIRED"})
    return idempotency_key


def _audit(db, user: User, matter_id: UUID, action: str, target_type: str, target_id, meta=None):
    record_audit_event(db, organization_id=user.organization_id, user_id=user.id, matter_id=matter_id,
                       action=action, target_type=target_type, target_id=target_id, metadata=meta or {})


# --------------------------------------------------------------------------------------------
# Serialization
# --------------------------------------------------------------------------------------------
def _span_view(db: Session, span: SourceSpan, context_chars: int = 240) -> dict:
    extraction = db.get(ExtractionVersion, span.extraction_version_id)
    version = db.get(DocumentVersion, extraction.document_version_id)
    document = db.get(Document, span.document_id)
    page = db.get(ExtractionPage, (span.extraction_version_id, span.page_no))
    before = after = ""
    if page is not None:
        before = page.text[max(0, span.normalized_start - context_chars):span.normalized_start]
        after = page.text[span.normalized_end:span.normalized_end + context_chars]
    return {
        "source_span_id": str(span.id), "text": span.text, "context_before": before,
        "context_after": after, "page": span.page_no, "start": span.normalized_start,
        "end": span.normalized_end, "quote_sha256": span.quote_sha256,
        "document_id": str(span.document_id),
        "document_title": (document.display_name or document.file_name) if document else None,
        "document_version_id": str(version.id), "revision_no": version.revision_no,
        "version_state": version.state, "is_current_version": document is not None
        and document.current_version_id == version.id,
        "extraction_version_id": str(extraction.id), "provenance": version.provenance,
    }


def _claim_summary(db: Session, claim: Claim) -> dict:
    revision = db.get(ClaimRevision, (claim.id, claim.current_revision))
    return {
        "id": str(claim.id), "run_id": str(claim.run_id), "text": revision.text,
        "revision": claim.current_revision, "review_seq": claim.review_seq,
        "review_state": claim.review_state, "basis_state": claim.basis_state,
        "coverage_state": claim.coverage_state, "source_gate_state": revision.source_gate_state,
        "source_gate_reasons": revision.source_gate_reasons,
        "relation_candidate": revision.relation_candidate,
        "evidence_sha256": revision.evidence_set_sha256, "updated_at": claim.updated_at.isoformat(),
    }


def _run_view(db: Session, run: AnalysisRun, with_claims: bool = True) -> dict:
    view = {
        "id": str(run.id), "question": run.question, "status": run.status,
        "error_code": run.error_code, "retrieval_profile": run.retrieval_profile,
        "model": run.model_config, "corpus_snapshot_id": str(run.corpus_snapshot_id),
        "coverage": run.coverage, "calls": run.call_records, "created_at": run.created_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }
    if with_claims:
        claims = db.scalars(select(Claim).where(Claim.run_id == run.id, Claim.matter_id == run.matter_id)
                            .order_by(Claim.created_at)).all()
        view["claims"] = [_claim_summary(db, c) for c in claims]
    return view


# --------------------------------------------------------------------------------------------
# Investigations
# --------------------------------------------------------------------------------------------
class AnalyzeRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    retrieval_profile: str | None = None


@router.post("/matters/{matter_id}/analyses", status_code=202,
             dependencies=[Depends(require_trace_header)])
def create_analysis(matter_id: UUID, payload: AnalyzeRequest,
                    idempotency_key: str | None = Header(default=None),
                    db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    ensure_matter_role(db, matter_id, user, REVIEW_ROLES)
    run, created = analysis.start_analysis(
        db, matter_id=matter_id, user_id=user.id, question=payload.question.strip(),
        profile=payload.retrieval_profile, idempotency_key=_key(idempotency_key))
    if created:
        _audit(db, user, matter_id, "analysis_requested", "analysis_run", run.id,
               {"retrieval_profile": run.retrieval_profile, "provider": run.model_config.get("provider_kind")})
    db.commit()
    if created:
        if settings.analysis_inline:
            analysis.execute_analysis(db, run.id)
        else:
            from app.services.document import enqueue_analysis

            enqueue_analysis(run.id)
    db.refresh(run)
    return _run_view(db, run)


@router.get("/matters/{matter_id}/analyses")
def list_analyses(matter_id: UUID, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> list[dict]:
    ensure_matter_access(db, matter_id, user)
    runs = db.scalars(select(AnalysisRun).where(AnalysisRun.matter_id == matter_id)
                      .order_by(AnalysisRun.created_at.desc()).limit(50)).all()
    return [_run_view(db, r, with_claims=False) for r in runs]


@router.get("/matters/{matter_id}/analyses/{run_id}")
def get_analysis(matter_id: UUID, run_id: UUID, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> dict:
    ensure_matter_access(db, matter_id, user)
    run = db.scalar(select(AnalysisRun).where(AnalysisRun.id == run_id, AnalysisRun.matter_id == matter_id))
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, {"code": "RUN_NOT_FOUND"})
    return _run_view(db, run)


# --------------------------------------------------------------------------------------------
# Claims
# --------------------------------------------------------------------------------------------
@router.get("/matters/{matter_id}/claims")
def list_claims(matter_id: UUID, review_state: str | None = None, needs_attention: bool = False,
                db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    ensure_matter_access(db, matter_id, user)
    query = select(Claim).where(Claim.matter_id == matter_id)
    if review_state:
        query = query.where(Claim.review_state == review_state.upper())
    if needs_attention:
        query = query.where((Claim.basis_state != "CURRENT") | (Claim.coverage_state != "CURRENT"))
    claims = db.scalars(query.order_by(Claim.updated_at.desc()).limit(200)).all()
    return [_claim_summary(db, c) for c in claims]


def _get_claim(db: Session, matter_id: UUID, claim_id: UUID) -> Claim:
    claim = db.scalar(select(Claim).where(Claim.id == claim_id, Claim.matter_id == matter_id))
    if claim is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, {"code": "CLAIM_NOT_FOUND"})
    return claim


@router.get("/matters/{matter_id}/claims/{claim_id}")
def get_claim(matter_id: UUID, claim_id: UUID, revision: int | None = None,
              db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    ensure_matter_access(db, matter_id, user)
    claim = _get_claim(db, matter_id, claim_id)
    number = revision or claim.current_revision
    rev = db.get(ClaimRevision, (claim.id, number))
    if rev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, {"code": "REVISION_NOT_FOUND"})
    evidence = db.scalars(select(ClaimEvidence).where(
        ClaimEvidence.claim_id == claim.id, ClaimEvidence.claim_revision == number,
        ClaimEvidence.matter_id == matter_id)).all()
    order = {"supporting": 0, "qualifying": 1, "opposing": 2, "other": 3}
    evidence_views = []
    for row in sorted(evidence, key=lambda r: (order[r.evidence_role], r.evidence_ref)):
        span = db.get(SourceSpan, row.source_span_id)
        evidence_views.append({
            "evidence_ref": row.evidence_ref, "role": row.evidence_role,
            "cited_by_model": row.cited_by_model, "relation_candidate": row.relation_candidate,
            "reason_code": row.reason_code, "quote_integrity": row.quote_integrity,
            "integrity_reason": row.integrity_reason, "retrieval_role": row.retrieval_role,
            "source": _span_view(db, span),
        })
    revisions = db.scalars(select(ClaimRevision).where(ClaimRevision.claim_id == claim.id)
                           .order_by(ClaimRevision.revision)).all()
    events = db.scalars(select(ReviewEvent).where(ReviewEvent.claim_id == claim.id,
                                                  ReviewEvent.matter_id == matter_id)
                        .order_by(ReviewEvent.event_seq)).all()
    alerts = db.scalars(select(CoverageAlert).where(CoverageAlert.claim_id == claim.id,
                                                    CoverageAlert.matter_id == matter_id)
                        .order_by(CoverageAlert.created_at.desc())).all()
    actors = {u.id: u.name for u in db.scalars(select(User).where(
        User.id.in_({e.actor_user_id for e in events}))).all()} if events else {}
    run = db.get(AnalysisRun, claim.run_id)
    return {
        **_claim_summary(db, claim),
        "viewing_revision": number, "viewing_text": rev.text,
        "viewing_source_gate_state": rev.source_gate_state,
        "viewing_relation_candidate": rev.relation_candidate,
        "coverage": rev.coverage, "open_questions": rev.open_questions,
        "corpus_snapshot_id": str(rev.corpus_snapshot_id),
        "question": run.question if run else None, "model": run.model_config if run else None,
        "evidence": evidence_views,
        "revisions": [{"revision": r.revision, "text": r.text, "actor_type": r.created_by_actor_type,
                       "change_reason": r.change_reason, "source_gate_state": r.source_gate_state,
                       "relation_candidate": r.relation_candidate,
                       "created_at": r.created_at.isoformat()} for r in revisions],
        "events": [{"id": str(e.id), "seq": e.event_seq, "action": e.action,
                    "revision": e.claim_revision, "reason_code": e.reason_code, "note": e.note,
                    "actor": actors.get(e.actor_user_id), "evidence_sha256": e.evidence_set_sha256,
                    "created_at": e.created_at.isoformat()} for e in events],
        "alerts": [_alert_view(a) for a in alerts],
    }


class ReviewPayload(BaseModel):
    decision: str
    expected_claim_revision: int
    expected_evidence_sha256: str = Field(min_length=64, max_length=64)
    expected_review_seq: int
    reason_code: str | None = None
    note: str | None = Field(default=None, max_length=2000)


@router.post("/matters/{matter_id}/claims/{claim_id}/reviews",
             dependencies=[Depends(require_trace_header)])
def review_claim(matter_id: UUID, claim_id: UUID, payload: ReviewPayload,
                 idempotency_key: str | None = Header(default=None),
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        ensure_matter_role(db, matter_id, user, REVIEW_ROLES)
    except HTTPException as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, {"code": "REVIEW_NOT_AUTHORIZED"}) from exc
    event, claim = change_control.submit_review(
        db, matter_id=matter_id, claim_id=claim_id, actor_id=user.id, idempotency_key=_key(idempotency_key),
        request=change_control.ReviewRequest(**payload.model_dump()))
    _audit(db, user, matter_id, "claim_reviewed", "claim", claim.id,
           {"decision": payload.decision, "revision": event.claim_revision, "event_id": str(event.id)})
    db.commit()
    return {"review_event_id": str(event.id), "active_state": claim.review_state,
            "claim_revision": claim.current_revision, "review_seq": claim.review_seq}


class RevisePayload(BaseModel):
    expected_claim_revision: int
    text: str | None = Field(default=None, min_length=3, max_length=600)


@router.post("/matters/{matter_id}/claims/{claim_id}/revisions",
             dependencies=[Depends(require_trace_header)])
def revise_claim(matter_id: UUID, claim_id: UUID, payload: RevisePayload,
                 idempotency_key: str | None = Header(default=None),
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    """With ``text``: reviewer edit (new revision). Without: re-check against current sources."""
    ensure_matter_role(db, matter_id, user, REVIEW_ROLES)
    claim = change_control.revise_claim(
        db, matter_id=matter_id, claim_id=claim_id, actor_id=user.id,
        expected_revision=payload.expected_claim_revision, new_text=payload.text,
        idempotency_key=_key(idempotency_key))
    _audit(db, user, matter_id, "claim_revised", "claim", claim.id,
           {"revision": claim.current_revision, "kind": "edit" if payload.text else "recheck"})
    db.commit()
    return _claim_summary(db, claim)


# --------------------------------------------------------------------------------------------
# Changes requiring review
# --------------------------------------------------------------------------------------------
def _alert_view(alert: CoverageAlert) -> dict:
    return {"id": str(alert.id), "claim_id": str(alert.claim_id), "claim_revision": alert.claim_revision,
            "kind": alert.kind, "status": alert.status, "detail": alert.detail,
            "detector_version": alert.detector_version, "created_at": alert.created_at.isoformat(),
            "triggering_document_version_id": str(alert.triggering_document_version_id)
            if alert.triggering_document_version_id else None}


@router.get("/matters/{matter_id}/changes")
def list_changes(matter_id: UUID, include_closed: bool = False, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> list[dict]:
    ensure_matter_access(db, matter_id, user)
    query = select(CoverageAlert).where(CoverageAlert.matter_id == matter_id)
    if not include_closed:
        query = query.where(CoverageAlert.status == "OPEN")
    alerts = db.scalars(query.order_by(CoverageAlert.created_at.desc()).limit(200)).all()
    out = []
    for alert in alerts:
        claim = db.get(Claim, alert.claim_id)
        out.append({**_alert_view(alert), "claim": _claim_summary(db, claim)})
    return out


@router.post("/matters/{matter_id}/changes/{alert_id}/dismiss",
             dependencies=[Depends(require_trace_header)])
def dismiss_change(matter_id: UUID, alert_id: UUID, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> dict:
    ensure_matter_role(db, matter_id, user, REVIEW_ROLES)
    alert = change_control.dismiss_alert(db, matter_id=matter_id, alert_id=alert_id, actor_id=user.id)
    _audit(db, user, matter_id, "coverage_alert_dismissed", "coverage_alert", alert.id)
    db.commit()
    return _alert_view(alert)


# --------------------------------------------------------------------------------------------
# Sources and versions
# --------------------------------------------------------------------------------------------
@router.get("/matters/{matter_id}/spans/{span_id}")
def get_span(matter_id: UUID, span_id: UUID, context: int = Query(default=400, ge=0, le=4000),
             db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    ensure_matter_access(db, matter_id, user)
    span = db.scalar(select(SourceSpan).where(SourceSpan.id == span_id, SourceSpan.matter_id == matter_id))
    if span is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, {"code": "SPAN_NOT_FOUND"})
    return _span_view(db, span, context)


@router.get("/matters/{matter_id}/sources")
def list_sources(matter_id: UUID, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> list[dict]:
    ensure_matter_access(db, matter_id, user)
    documents = db.scalars(select(Document).where(Document.matter_id == matter_id)
                           .order_by(Document.created_at.desc())).all()
    out = []
    for document in documents:
        versions = db.scalars(select(DocumentVersion).where(
            DocumentVersion.document_id == document.id, DocumentVersion.matter_id == matter_id)
            .order_by(DocumentVersion.revision_no.desc())).all()
        version_views = []
        for v in versions:
            extraction = db.scalar(select(ExtractionVersion).where(
                ExtractionVersion.document_version_id == v.id).order_by(ExtractionVersion.created_at.desc()))
            version_views.append({
                "id": str(v.id), "revision_no": v.revision_no, "state": v.state,
                "source_sha256": v.source_sha256, "provenance": v.provenance,
                "file_name": v.file_name, "change_note": v.change_note,
                "created_at": v.created_at.isoformat(),
                "span_count": extraction.span_count if extraction else 0,
                "warnings": extraction.warnings if extraction else [],
            })
        out.append({"id": str(document.id), "title": document.display_name or document.file_name,
                    "mime_type": document.mime_type, "ingest_status": document.ingest_status,
                    "current_version_id": str(document.current_version_id) if document.current_version_id else None,
                    "versions": version_views})
    return out


# --------------------------------------------------------------------------------------------
# Evidence packets
# --------------------------------------------------------------------------------------------
class PacketRequest(BaseModel):
    claim_ids: list[UUID] = Field(min_length=1, max_length=200)
    inclusion_policy: str = "accepted_current_only"


@router.post("/matters/{matter_id}/packets", status_code=201,
             dependencies=[Depends(require_trace_header)])
def create_packet(matter_id: UUID, payload: PacketRequest, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> dict:
    ensure_matter_role(db, matter_id, user, EXPORT_ROLES)
    packet = packets.build_packet(db, matter_id=matter_id, user=user, claim_ids=payload.claim_ids,
                                  inclusion_policy=payload.inclusion_policy)
    _audit(db, user, matter_id, "packet_exported", "packet", packet.id,
           {"claim_count": packet.claim_count, "manifest_sha256": packet.manifest_sha256})
    db.commit()
    return packets.packet_view(packet)


@router.get("/matters/{matter_id}/packets")
def list_packets(matter_id: UUID, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> list[dict]:
    ensure_matter_access(db, matter_id, user)
    rows = db.scalars(select(PacketExport).where(PacketExport.matter_id == matter_id)
                      .order_by(PacketExport.created_at.desc()).limit(50)).all()
    return [packets.packet_view(p) for p in rows]


@router.get("/matters/{matter_id}/packets/{packet_id}/files/{file_name}")
def download_packet_file(matter_id: UUID, packet_id: UUID, file_name: str,
                         db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Response:
    ensure_matter_access(db, matter_id, user)  # re-checked at download time, every time
    packet = db.scalar(select(PacketExport).where(PacketExport.id == packet_id,
                                                  PacketExport.matter_id == matter_id))
    if packet is None or file_name not in packet.files:
        raise HTTPException(status.HTTP_404_NOT_FOUND, {"code": "PACKET_FILE_NOT_FOUND"})
    content, media_type = packets.read_file(packet, file_name)
    return Response(content=content, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="{file_name}"',
                             "X-Content-Type-Options": "nosniff"})
