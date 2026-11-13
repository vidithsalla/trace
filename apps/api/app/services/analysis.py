"""Investigate a question: retrieve, propose claims, gate sources, search counterevidence, assess.

Trust layers stay separate (PRD section 4): the source gate is deterministic, relation labels
are model *candidates*, and nothing here can set a human review decision.
"""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.claims import AnalysisRun, Claim, ClaimEvidence, ClaimRevision, RetrievalCandidate
from app.models.domain import utcnow
from app.models.evidence import SourceSpan
from app.services import retrieval_v3
from app.services.evidence_versions import create_snapshot
from app.services.llm.client import CallBudget, LLMError, ProviderConfigError
from app.services.llm.contracts import EvidencePack, EvidencePackItem, make_ref
from app.services.llm.engine import ClaimEngine, get_claim_engine, overall_from_relations
from app.services.source_gate import GateResult, check_span, combine

PRIMARY_K = 8
COUNTER_K = 6
MAX_ASSESS_ITEMS = 12
MAX_CLAIMS = 6

RELATION_TO_CANDIDATE = {
    "supported": "SUPPORT_CANDIDATE",
    "contradicted": "CONTRADICTION_CANDIDATE",
    "mixed": "MIXED",
    "not_established": "NOT_ESTABLISHED",
    "uncertain": "UNCERTAIN",
}
RELATION_TO_ROLE = {"supports": "supporting", "contradicts": "opposing", "qualifies": "qualifying"}


def _sha(payload) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def evidence_set_sha256(rows: list[ClaimEvidence], quote_hashes: dict[UUID, str]) -> str:
    return _sha(sorted(
        [str(r.source_span_id), quote_hashes.get(r.source_span_id), r.evidence_role,
         r.relation_candidate, r.cited_by_model] for r in rows
    ))


def start_analysis(db: Session, *, matter_id: UUID, user_id: UUID, question: str,
                   profile: str | None, idempotency_key: str) -> tuple[AnalysisRun, bool]:
    """Create (or return the existing) run for this idempotency key. Returns (run, created)."""
    existing = db.scalar(select(AnalysisRun).where(
        AnalysisRun.matter_id == matter_id, AnalysisRun.requested_by == user_id,
        AnalysisRun.idempotency_key == idempotency_key))
    if existing is not None:
        if existing.question != question:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                {"code": "IDEMPOTENCY_KEY_REUSED", "run_id": str(existing.id)})
        return existing, False
    try:
        profile_name = retrieval_v3.resolve_profile(profile)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            {"code": "INVALID_RETRIEVAL_PROFILE"}) from exc
    try:
        engine = get_claim_engine(settings)
    except ProviderConfigError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            {"code": exc.code, "message": str(exc)}) from exc
    snapshot = create_snapshot(db, matter_id, user_id)
    model_config = engine.describe()
    run = AnalysisRun(
        matter_id=matter_id, corpus_snapshot_id=snapshot.id, requested_by=user_id,
        question=question, retrieval_profile=profile_name,
        retrieval_config_sha256=retrieval_v3.profile_config_sha256(profile_name, PRIMARY_K),
        model_config=model_config, model_config_sha256=_sha(model_config),
        prompt_version=model_config.get("prompt_version", "unknown"),
        code_commit=settings.code_commit, status="QUEUED", idempotency_key=idempotency_key,
    )
    db.add(run)
    db.flush()
    return run, True


def execute_analysis(db: Session, run_id: UUID, engine: ClaimEngine | None = None) -> AnalysisRun:
    run = db.get(AnalysisRun, run_id)
    if run is None:
        raise ValueError("analysis run not found")
    if run.status not in ("QUEUED", "RUNNING"):
        return run  # already finished: a duplicate job message is a no-op
    run.status = "RUNNING"
    run.started_at = utcnow()
    db.commit()

    budget = CallBudget(settings.model_max_calls_per_run)
    try:
        engine = engine or get_claim_engine(settings)
        _run_pipeline(db, run, engine, budget)
        db.commit()
    except (LLMError, httpx.HTTPError) as exc:
        db.rollback()
        run = db.get(AnalysisRun, run_id)
        run.status = "FAILED"
        run.error_code = exc.code if isinstance(exc, LLMError) else "embedding_unavailable"
        run.call_records = [r.as_dict() for r in budget.records]
        run.completed_at = utcnow()
        db.commit()
    except Exception:
        db.rollback()
        run = db.get(AnalysisRun, run_id)
        run.status = "FAILED"
        run.error_code = "internal_error"
        run.completed_at = utcnow()
        db.commit()
        raise
    return run


def _run_pipeline(db: Session, run: AnalysisRun, engine: ClaimEngine, budget: CallBudget) -> None:
    matter_id, snapshot_id = run.matter_id, run.corpus_snapshot_id
    total_spans = retrieval_v3.snapshot_span_count(db, matter_id, snapshot_id)
    primary = retrieval_v3.retrieve(db, matter_id=matter_id, snapshot_id=snapshot_id,
                                    query=run.question, profile=run.retrieval_profile, k=PRIMARY_K)
    coverage = {"snapshot_spans": total_spans, "primary_candidates": len(primary), "exhaustive": False}

    refs: dict[UUID, str] = {}
    spans: dict[UUID, SourceSpan] = {}

    def register(candidates, role: str, claim_id: UUID | None = None) -> list[EvidencePackItem]:
        items = []
        for c in candidates:
            if c.source_span_id not in refs:
                refs[c.source_span_id] = make_ref(len(refs))
                db.add(RetrievalCandidate(
                    run_id=run.id, evidence_ref=refs[c.source_span_id], matter_id=matter_id,
                    source_span_id=c.source_span_id, retrieval_role=role, retriever=c.retriever,
                    rank=c.rank, score=c.score, for_claim_id=claim_id))
            span = spans.get(c.source_span_id) or db.get(SourceSpan, c.source_span_id)
            spans[span.id] = span
            items.append(_pack_item(db, refs[span.id], span, role))
        return items

    primary_items = register(primary, "primary")
    if not primary_items:
        _finish(run, "ABSTAINED", {**coverage, "reason": "NO_CANDIDATES"}, budget)
        return

    proposal = engine.propose_claims(run.question, EvidencePack(tuple(primary_items)), budget)
    coverage["model_answer_status"] = proposal.answer_status
    # The model's self-reported status is not trusted either way: claims it wrote are kept (and
    # still gated, assessed and human-reviewed); with no claims the run abstains.
    if proposal.claims and proposal.answer_status != "proposed":
        coverage["model_status_disagreed"] = True
    if not proposal.claims:
        _finish(run, "ABSTAINED", {**coverage, "reason": "MODEL_ABSTAINED",
                                    "abstention_reason": proposal.abstention_reason}, budget)
        return

    primary_by_ref = {item.ref: item for item in primary_items}
    for proposed in proposal.claims[:MAX_CLAIMS]:
        claim = Claim(matter_id=matter_id, run_id=run.id)
        db.add(claim)
        db.flush()
        cited = [primary_by_ref[r] for r in dict.fromkeys(proposed.evidence_refs) if r in primary_by_ref]
        unknown_refs = [r for r in proposed.evidence_refs if r not in primary_by_ref]

        counter = retrieval_v3.counterevidence(
            db, matter_id=matter_id, snapshot_id=snapshot_id, claim=proposed.text,
            profile=run.retrieval_profile, k=COUNTER_K, exclude=[i.source_span_id for i in cited])
        counter_items = register(counter, "counterevidence", claim.id)
        assess_items = _dedupe([*cited, *primary_items[:4], *counter_items])[:MAX_ASSESS_ITEMS]
        assessment = engine.assess_support(proposed.text, EvidencePack(tuple(assess_items)), budget)

        _persist_claim_revision(
            db, claim=claim, revision=1, text=proposed.text, snapshot_id=snapshot_id,
            assess_items=assess_items, cited_refs={i.ref for i in cited}, unknown_refs=unknown_refs,
            relations={r.evidence_ref: r for r in assessment.relations},
            model_overall=assessment.overall, open_questions=proposed.open_questions,
            coverage={"assessed_spans": len(assess_items), "counterevidence_candidates": len(counter_items),
                      "snapshot_spans": total_spans, "exhaustive": False},
            actor_type="model", user_id=None,
        )
    _finish(run, "COMPLETED", coverage, budget)


def _persist_claim_revision(db: Session, *, claim: Claim, revision: int, text: str,
                            snapshot_id: UUID, assess_items: list[EvidencePackItem],
                            cited_refs: set[str], unknown_refs: list[str], relations: dict,
                            model_overall: str | None, open_questions: list[str], coverage: dict,
                            actor_type: str, user_id: UUID | None,
                            change_reason: str | None = None) -> ClaimRevision:
    matter_id = claim.matter_id
    allowed = frozenset(i.source_span_id for i in assess_items)
    rows: list[ClaimEvidence] = []
    quote_hashes: dict[UUID, str] = {}
    cited_results: list[GateResult] = [GateResult("INVALID", "UNKNOWN_EVIDENCE_REF") for _ in unknown_refs]
    kept_relations = []
    for item in assess_items:
        gate = check_span(db, matter_id=matter_id, snapshot_id=snapshot_id,
                          span_id=item.source_span_id, allowed_span_ids=allowed)
        relation = relations.get(item.ref)
        label = relation.relation if relation else "unassessed"
        is_cited = item.ref in cited_refs
        if is_cited:
            cited_results.append(gate)
        if not is_cited and label in ("irrelevant", "unassessed"):
            continue  # do not clutter the packet with passages the assessor set aside
        span = db.get(SourceSpan, item.source_span_id)
        quote_hashes[span.id] = span.quote_sha256
        if relation is not None:
            kept_relations.append(relation)
        rows.append(ClaimEvidence(
            claim_id=claim.id, claim_revision=revision, matter_id=matter_id,
            source_span_id=item.source_span_id, evidence_ref=item.ref, cited_by_model=is_cited,
            evidence_role=RELATION_TO_ROLE.get(label, "other"), quote_integrity=gate.state,
            integrity_reason=gate.reason, relation_candidate=label,
            reason_code=relation.reason_code if relation else None,
            retrieval_role=item.retrieval_role,
        ))
    gate_state, gate_reasons = combine(cited_results)
    overall = overall_from_relations(kept_relations)
    if model_overall and model_overall != overall:
        coverage = {**coverage, "model_overall_disagreed": model_overall}
    claim_revision = ClaimRevision(
        claim_id=claim.id, revision=revision, matter_id=matter_id, text=text,
        evidence_set_sha256=evidence_set_sha256(rows, quote_hashes),
        corpus_snapshot_id=snapshot_id, source_gate_state=gate_state,
        source_gate_reasons=gate_reasons, relation_candidate=RELATION_TO_CANDIDATE[overall],
        coverage=coverage, open_questions=list(open_questions), created_by_actor_type=actor_type,
        created_by_user_id=user_id, change_reason=change_reason,
    )
    db.add(claim_revision)
    db.flush()
    db.add_all(rows)
    db.flush()
    return claim_revision


def _pack_item(db: Session, ref: str, span: SourceSpan, role: str) -> EvidencePackItem:
    from app.models.domain import Document

    document = db.get(Document, span.document_id)
    return EvidencePackItem(ref=ref, source_span_id=span.id, chunk_id=None, document_id=span.document_id,
                            document_title=(document.display_name or document.file_name) if document else "document",
                            page=span.page_no, text=span.text, retrieval_role=role)


def _dedupe(items: list[EvidencePackItem]) -> list[EvidencePackItem]:
    seen: set[str] = set()
    out = []
    for item in items:
        if item.ref not in seen:
            seen.add(item.ref)
            out.append(item)
    return out


def _finish(run: AnalysisRun, status_value: str, coverage: dict, budget: CallBudget) -> None:
    run.status = status_value
    run.coverage = coverage
    run.call_records = [r.as_dict() for r in budget.records]
    run.completed_at = utcnow()
