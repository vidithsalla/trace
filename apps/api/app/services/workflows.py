from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.domain import AIRun, Citation, Document, DocumentChunk, Matter, Memo
from app.schemas.search import SearchRequest
from app.schemas.workflow import (
    ChronologyEvent,
    ChronologyRequest,
    ChronologyResponse,
    CitationPayload,
    ContradictionItem,
    ContradictionRequest,
    ContradictionResponse,
    GroundedQARequest,
    GroundedQAResponse,
    MemoCreateRequest,
)
from app.services.audit import record_audit_event
from app.services.chronology import collapse_duplicate_events, replace_run_events
from app.services.citations import validate_citations
from app.services.contradictions import build_contradiction_evidence_pack
from app.services.memos import (
    build_issue_memo_evidence_pack,
    fact_to_content,
    render_memo_markdown,
    structured_memo_content,
)
from app.services.mock_model_client import MockModelClient
from app.services.model_client import EvidenceItem, MemoDraft, ModelClient, ModelClientError
from app.services.openai_compatible_model_client import OpenAICompatibleModelClient
from app.services.search import perform_search


def _top_chunks(db: Session, matter_id: UUID, limit: int = 3) -> list[tuple[DocumentChunk, Document]]:
    stmt = (
        select(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunk.matter_id == matter_id)
        .order_by(DocumentChunk.created_at.asc())
        .limit(limit)
    )
    return list(db.execute(stmt).all())


def _build_evidence_pack(
    db: Session, matter_id: UUID, limit: int
) -> list[EvidenceItem]:
    rows = _top_chunks(db, matter_id, limit)
    return [
        EvidenceItem(
            document_id=document.id,
            document_name=document.display_name or document.file_name,
            page=chunk.page_start,
            chunk_id=chunk.id,
            quote=chunk.text[:220],
            text=chunk.text,
        )
        for chunk, document in rows
    ]


def _build_question_evidence_pack(
    db: Session, matter_id: UUID, question: str, limit: int
) -> list[EvidenceItem]:
    search_response = perform_search(db, matter_id, SearchRequest(query=question, limit=limit))
    evidence: list[EvidenceItem] = []
    for result in search_response.results:
        if result.chunk_id is None:
            continue
        chunk = db.get(DocumentChunk, result.chunk_id)
        document = db.get(Document, result.document_id)
        if chunk is None or document is None or chunk.matter_id != matter_id:
            continue
        quote = result.snippet.strip(". ")
        if quote not in chunk.text:
            quote = chunk.text[:360]
        evidence.append(
            EvidenceItem(
                document_id=document.id,
                document_name=document.display_name or document.file_name,
                page=chunk.page_start,
                chunk_id=chunk.id,
                quote=quote,
                text=chunk.text,
            )
        )
    if not evidence:
        return _build_evidence_pack(db, matter_id, limit)
    return evidence


def _build_chronology_evidence_pack(
    db: Session, matter_id: UUID, payload: ChronologyRequest
) -> list[EvidenceItem]:
    query_parts = [
        payload.topic,
        payload.entity_name,
        "notice payment defect inspection shipment approval invoice email letter report date timeline chronology",
    ]
    query = " ".join(part for part in query_parts if part).strip()
    search_response = perform_search(
        db,
        matter_id,
        SearchRequest(
            query=query,
            entity_names=[payload.entity_name] if payload.entity_name else [],
            date_from=payload.start_date,
            date_to=payload.end_date,
            limit=max(payload.limit, 10),
        ),
    )
    evidence: list[EvidenceItem] = []
    seen_chunks: set[UUID] = set()
    for result in search_response.results:
        if result.chunk_id is None or result.chunk_id in seen_chunks:
            continue
        chunk = db.get(DocumentChunk, result.chunk_id)
        document = db.get(Document, result.document_id)
        if chunk is None or document is None or chunk.matter_id != matter_id:
            continue
        quote = result.snippet.strip(". ")
        if quote not in chunk.text:
            quote = chunk.text[:360]
        evidence.append(
            EvidenceItem(
                document_id=document.id,
                document_name=document.display_name or document.file_name,
                page=chunk.page_start,
                chunk_id=chunk.id,
                quote=quote,
                text=chunk.text,
            )
        )
        seen_chunks.add(chunk.id)

    for chunk, document in _top_chunks(db, matter_id, payload.limit):
        if chunk.id in seen_chunks:
            continue
        evidence.append(
            EvidenceItem(
                document_id=document.id,
                document_name=document.display_name or document.file_name,
                page=chunk.page_start,
                chunk_id=chunk.id,
                quote=chunk.text[:360],
                text=chunk.text,
            )
        )
        seen_chunks.add(chunk.id)
        if len(evidence) >= payload.limit:
            break
    return evidence[: payload.limit]


def _get_model_client() -> ModelClient:
    if settings.model_provider == "openai_compatible":
        return OpenAICompatibleModelClient(
            model_name=settings.model_name,
            base_url=settings.model_base_url,
        )
    return MockModelClient(model_name=settings.model_name)


def _persist_citations(
    db: Session,
    ai_run_id: UUID,
    citations: list[CitationPayload],
) -> list[CitationPayload]:
    persisted: list[CitationPayload] = []
    for citation_payload in citations:
        citation = Citation(
            ai_run_id=ai_run_id,
            document_id=citation_payload.document_id,
            chunk_id=citation_payload.chunk_id,
            page_number=citation_payload.page,
            quote=citation_payload.quote,
        )
        db.add(citation)
        db.flush()
        persisted.append(citation_payload.model_copy(update={"id": citation.id}))
    return persisted


def _record_ai_run_audit(
    db: Session,
    matter_id: UUID,
    user_id: UUID,
    run_id: UUID,
    run_type: str,
    *,
    action: str = "start_ai_run",
    metadata: dict | None = None,
) -> None:
    matter = db.get(Matter, matter_id)
    organization_id = matter.organization_id if matter is not None else user_id
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=user_id,
        matter_id=matter_id,
        action=action,
        target_type="ai_run",
        target_id=run_id,
        metadata={"run_type": run_type, **(metadata or {})},
    )


def run_grounded_qa(
    db: Session, matter_id: UUID, user_id: UUID, payload: GroundedQARequest
) -> GroundedQAResponse:
    evidence = _build_question_evidence_pack(db, matter_id, payload.question, payload.limit)
    client = _get_model_client()
    run = AIRun(
        matter_id=matter_id,
        user_id=user_id,
        run_type="grounded_qa",
        model_name=client.model_name,
        prompt_template_version="grounded_qa_v1",
        status="running",
        input_json={
            **payload.model_dump(mode="json"),
            "evidence": [
                {
                    "document_id": str(item.document_id),
                    "chunk_id": str(item.chunk_id) if item.chunk_id else None,
                    "page": item.page,
                    "quote": item.quote,
                }
                for item in evidence
            ],
        },
        output_json={},
    )
    db.add(run)
    db.flush()
    _record_ai_run_audit(db, matter_id, user_id, run.id, "grounded_qa", action="start_ai_run")

    if not evidence:
        response = _insufficient_evidence_response(
            "No matter-scoped evidence matched the question. Try a broader question or upload more documents."
        )
        run.status = "completed"
        run.output_json = response.model_dump(mode="json", exclude={"ai_run_id"})
        _record_ai_run_audit(
            db,
            matter_id,
            user_id,
            run.id,
            "grounded_qa",
            action="complete_ai_run",
            metadata={"citation_count": 0, "validation": "insufficient_evidence"},
        )
        return response.model_copy(update={"ai_run_id": run.id})

    try:
        response = client.grounded_qa(payload.question, evidence)
    except ModelClientError as exc:
        response = GroundedQAResponse(
            answer="The model provider could not complete this grounded answer safely.",
            short_answer="Model provider failure.",
            confidence="low",
            citations=[],
            open_questions=["Retry later or switch to the local mock model provider."],
            unsupported_claims_detected=True,
        )
        run.status = "failed"
        run.error_message = exc.__class__.__name__
        run.output_json = response.model_dump(mode="json", exclude={"ai_run_id"})
        _record_ai_run_audit(
            db,
            matter_id,
            user_id,
            run.id,
            "grounded_qa",
            action="fail_ai_run",
            metadata={"error_class": exc.__class__.__name__},
        )
        return response.model_copy(update={"ai_run_id": run.id})

    candidate_citation_count = len(response.citations)
    validated_citations = validate_citations(db, matter_id, response.citations)
    if not validated_citations:
        response = _insufficient_evidence_response(
            "Retrieved citations could not be validated against the matter source text."
        )
        run.status = "completed"
        run.output_json = {
            **response.model_dump(mode="json", exclude={"ai_run_id"}),
            "validation": {"workflow": "citation_check_v1", "validated_citation_count": 0},
        }
        _record_ai_run_audit(
            db,
            matter_id,
            user_id,
            run.id,
            "grounded_qa",
            action="citation_validation_failed",
            metadata={"candidate_citation_count": candidate_citation_count},
        )
        return response.model_copy(update={"ai_run_id": run.id})

    confidence = response.confidence
    if len(validated_citations) == 1 and confidence in {"medium", "high"}:
        confidence = "low"
    elif len(validated_citations) < 2 and confidence == "high":
        confidence = "medium"

    persisted_citations = _persist_citations(db, run.id, validated_citations)
    final_response = response.model_copy(
        update={
            "ai_run_id": run.id,
            "citations": persisted_citations,
            "confidence": confidence,
            "unsupported_claims_detected": False,
        }
    )

    run.status = "completed"
    run.output_json = {
        **final_response.model_dump(mode="json", exclude={"ai_run_id"}),
        "validation": {
            "workflow": "citation_check_v1",
            "candidate_citation_count": candidate_citation_count,
            "validated_citation_count": len(validated_citations),
        },
    }
    _record_ai_run_audit(
        db,
        matter_id,
        user_id,
        run.id,
        "grounded_qa",
        action="complete_ai_run",
        metadata={"citation_count": len(persisted_citations), "confidence": confidence},
    )
    return final_response


def _insufficient_evidence_response(reason: str) -> GroundedQAResponse:
    return GroundedQAResponse(
        answer="Insufficient evidence in the current matter record to answer this question.",
        short_answer="Insufficient evidence.",
        confidence="low",
        citations=[],
        open_questions=[reason],
        unsupported_claims_detected=False,
    )


def run_chronology_builder(
    db: Session, matter_id: UUID, user_id: UUID, payload: ChronologyRequest
) -> ChronologyResponse:
    evidence = _build_chronology_evidence_pack(db, matter_id, payload)
    client = _get_model_client()
    run = AIRun(
        matter_id=matter_id,
        user_id=user_id,
        run_type="chronology_builder",
        model_name=client.model_name,
        prompt_template_version="chronology_builder_v1",
        status="running",
        input_json={
            **payload.model_dump(mode="json"),
            "evidence": [
                {
                    "document_id": str(item.document_id),
                    "chunk_id": str(item.chunk_id) if item.chunk_id else None,
                    "page": item.page,
                    "quote": item.quote,
                }
                for item in evidence
            ],
        },
        output_json={},
    )
    db.add(run)
    db.flush()
    _record_ai_run_audit(db, matter_id, user_id, run.id, "chronology_builder", action="start_ai_run")

    if not evidence:
        response = ChronologyResponse(
            events=[],
            unresolved_ambiguities=[
                "No matter-scoped evidence was available for chronology generation."
            ],
        )
        run.status = "completed"
        run.output_json = response.model_dump(mode="json", exclude={"ai_run_id"})
        _record_ai_run_audit(
            db,
            matter_id,
            user_id,
            run.id,
            "chronology_builder",
            action="complete_ai_run",
            metadata={"event_count": 0, "validation": "insufficient_evidence"},
        )
        return response.model_copy(update={"ai_run_id": run.id})

    try:
        model_response = client.chronology(payload, evidence)
    except ModelClientError as exc:
        response = ChronologyResponse(
            events=[],
            unresolved_ambiguities=["The model provider could not safely build the chronology."],
        )
        run.status = "failed"
        run.error_message = exc.__class__.__name__
        run.output_json = response.model_dump(mode="json", exclude={"ai_run_id"})
        _record_ai_run_audit(
            db,
            matter_id,
            user_id,
            run.id,
            "chronology_builder",
            action="fail_ai_run",
            metadata={"error_class": exc.__class__.__name__},
        )
        return response.model_copy(update={"ai_run_id": run.id})

    validated_events: list[ChronologyEvent] = []
    rejected_event_count = 0
    for event_payload in model_response.events:
        if payload.start_date and event_payload.date and event_payload.date < payload.start_date:
            continue
        if payload.end_date and event_payload.date and event_payload.date > payload.end_date:
            continue
        validated_citations = validate_citations(db, matter_id, event_payload.citations)
        if not validated_citations:
            rejected_event_count += 1
            continue
        validated_events.append(
            event_payload.model_copy(
                update={
                    "citations": validated_citations,
                    "source_type": event_payload.source_type or "ai_extracted",
                }
            )
        )

    deduped_events = collapse_duplicate_events(validated_events)
    persisted_events = replace_run_events(db, matter_id, run.id, deduped_events)
    unresolved = list(model_response.unresolved_ambiguities)
    if rejected_event_count:
        unresolved.append(
            f"{rejected_event_count} proposed event(s) were excluded because their citations did not validate."
        )

    response = model_response.model_copy(
        update={"events": persisted_events, "unresolved_ambiguities": unresolved, "ai_run_id": run.id}
    )
    run.status = "completed"
    run.output_json = {
        **response.model_dump(mode="json", exclude={"ai_run_id"}),
        "validation": {
            "workflow": "citation_check_v1",
            "candidate_event_count": len(model_response.events),
            "persisted_event_count": len(persisted_events),
            "rejected_event_count": rejected_event_count,
        },
    }
    _record_ai_run_audit(
        db,
        matter_id,
        user_id,
        run.id,
        "chronology_builder",
        action="complete_ai_run",
        metadata={"event_count": len(persisted_events), "rejected_event_count": rejected_event_count},
    )
    return response


def run_contradiction_finder(
    db: Session, matter_id: UUID, user_id: UUID, payload: ContradictionRequest
) -> ContradictionResponse:
    evidence_pack = build_contradiction_evidence_pack(
        db, matter_id, payload.topic, limit=payload.limit
    )
    client = _get_model_client()
    run = AIRun(
        matter_id=matter_id,
        user_id=user_id,
        run_type="contradiction_finder",
        model_name=client.model_name,
        prompt_template_version="contradiction_finder_v1",
        status="running",
        input_json={
            **payload.model_dump(mode="json"),
            "profile": {
                "canonical_topic": evidence_pack.profile.canonical_topic,
                "side_a_label": evidence_pack.profile.side_a_label,
                "side_b_label": evidence_pack.profile.side_b_label,
            },
            "evidence": [
                {
                    "document_id": str(item.document_id),
                    "chunk_id": str(item.chunk_id) if item.chunk_id else None,
                    "page": item.page,
                    "quote": item.quote,
                }
                for item in evidence_pack.evidence
            ],
            "clusters": {
                "side_a_count": len(evidence_pack.side_a),
                "side_b_count": len(evidence_pack.side_b),
            },
        },
        output_json={},
    )
    db.add(run)
    db.flush()
    _record_ai_run_audit(db, matter_id, user_id, run.id, "contradiction_finder", action="start_ai_run")

    if not evidence_pack.side_a or not evidence_pack.side_b:
        response = ContradictionResponse(
            topic=payload.topic,
            contradictions=[],
            ambiguities=evidence_pack.ambiguities
            or ["Trace did not find citation-backed evidence on both sides of this topic."],
            evidence_count=len(evidence_pack.evidence),
        )
        run.status = "completed"
        run.output_json = {
            **response.model_dump(mode="json", exclude={"ai_run_id"}),
            "validation": {
                "workflow": "citation_check_v1",
                "candidate_contradiction_count": 0,
                "persisted_contradiction_count": 0,
                "rejected_contradiction_count": 0,
            },
        }
        _record_ai_run_audit(
            db,
            matter_id,
            user_id,
            run.id,
            "contradiction_finder",
            action="complete_ai_run",
            metadata={"contradiction_count": 0, "ambiguity_count": len(response.ambiguities)},
        )
        return response.model_copy(update={"ai_run_id": run.id})

    try:
        response = client.contradictions(payload, evidence_pack.evidence)
    except ModelClientError as exc:
        response = ContradictionResponse(
            topic=payload.topic,
            contradictions=[],
            ambiguities=["The model provider could not safely complete contradiction analysis."],
            evidence_count=len(evidence_pack.evidence),
        )
        run.status = "failed"
        run.error_message = exc.__class__.__name__
        run.output_json = response.model_dump(mode="json", exclude={"ai_run_id"})
        _record_ai_run_audit(
            db,
            matter_id,
            user_id,
            run.id,
            "contradiction_finder",
            action="fail_ai_run",
            metadata={"error_class": exc.__class__.__name__},
        )
        return response.model_copy(update={"ai_run_id": run.id})

    contradictions: list[ContradictionItem] = []
    rejected_contradiction_count = 0
    for item in response.contradictions:
        validated_a = validate_citations(db, matter_id, item.citations_a)
        validated_b = validate_citations(db, matter_id, item.citations_b)
        if not validated_a or not validated_b:
            rejected_contradiction_count += 1
            continue
        citations_a = _persist_citations(db, run.id, validated_a)
        citations_b = _persist_citations(db, run.id, validated_b)
        contradictions.append(
            item.model_copy(update={"citations_a": citations_a, "citations_b": citations_b})
        )

    ambiguities = list(response.ambiguities)
    if rejected_contradiction_count:
        ambiguities.append(
            f"{rejected_contradiction_count} proposed contradiction(s) were excluded because both sides did not validate."
        )
    if not contradictions and not ambiguities:
        ambiguities.append("Trace found evidence but could not validate a citation-backed contradiction.")

    final_response = response.model_copy(
        update={
            "contradictions": contradictions,
            "ambiguities": ambiguities,
            "evidence_count": len(evidence_pack.evidence),
            "ai_run_id": run.id,
        }
    )
    run.status = "completed"
    run.output_json = {
        **final_response.model_dump(mode="json", exclude={"ai_run_id"}),
        "validation": {
            "workflow": "citation_check_v1",
            "candidate_contradiction_count": len(response.contradictions),
            "persisted_contradiction_count": len(contradictions),
            "rejected_contradiction_count": rejected_contradiction_count,
        },
    }
    _record_ai_run_audit(
        db,
        matter_id,
        user_id,
        run.id,
        "contradiction_finder",
        action="complete_ai_run",
        metadata={
            "contradiction_count": len(contradictions),
            "ambiguity_count": len(ambiguities),
            "rejected_contradiction_count": rejected_contradiction_count,
        },
    )
    return final_response


def run_issue_memo(
    db: Session, matter_id: UUID, user_id: UUID, payload: MemoCreateRequest
) -> Memo:
    evidence = build_issue_memo_evidence_pack(db, matter_id, payload.issue, limit=payload.limit)
    client = _get_model_client()
    run = AIRun(
        matter_id=matter_id,
        user_id=user_id,
        run_type="issue_memo",
        model_name=client.model_name,
        prompt_template_version="issue_memo_v1",
        status="running",
        input_json={
            **payload.model_dump(mode="json"),
            "evidence": [
                {
                    "document_id": str(item.document_id),
                    "chunk_id": str(item.chunk_id) if item.chunk_id else None,
                    "page": item.page,
                    "quote": item.quote,
                }
                for item in evidence
            ],
        },
        output_json={},
    )
    db.add(run)
    db.flush()
    _record_ai_run_audit(db, matter_id, user_id, run.id, "issue_memo", action="start_ai_run")

    try:
        draft: MemoDraft = client.issue_memo(payload.issue, evidence)
    except ModelClientError as exc:
        run.status = "failed"
        run.error_message = exc.__class__.__name__
        run.output_json = {"error": "The model provider could not safely draft this memo."}
        _record_ai_run_audit(
            db,
            matter_id,
            user_id,
            run.id,
            "issue_memo",
            action="fail_ai_run",
            metadata={"error_class": exc.__class__.__name__},
        )
        raise

    supporting_facts = []
    for fact in draft.supporting_facts:
        validated_citations = validate_citations(db, matter_id, fact.citations)
        if validated_citations:
            citations = _persist_citations(db, run.id, validated_citations)
            supporting_facts.append(fact_to_content(fact.statement, citations))

    contrary_facts = []
    for fact in draft.contrary_facts:
        validated_citations = validate_citations(db, matter_id, fact.citations)
        if validated_citations:
            citations = _persist_citations(db, run.id, validated_citations)
            contrary_facts.append(fact_to_content(fact.statement, citations))

    content_json = structured_memo_content(
        issue=payload.issue,
        draft=draft,
        supporting_facts=supporting_facts,
        contrary_facts=contrary_facts,
    )
    content_markdown = render_memo_markdown(content_json)
    run.status = "completed"
    run.output_json = {
        **content_json,
        "validation": {
            "workflow": "citation_check_v1",
            "supporting_fact_count": len(supporting_facts),
            "contrary_fact_count": len(contrary_facts),
            "required_sections": [
                "issue",
                "answer_in_brief",
                "supporting_facts",
                "contrary_facts",
                "gaps",
                "next_documents_to_review",
            ],
        },
    }
    _record_ai_run_audit(
        db,
        matter_id,
        user_id,
        run.id,
        "issue_memo",
        action="complete_ai_run",
        metadata={
            "supporting_fact_count": len(supporting_facts),
            "contrary_fact_count": len(contrary_facts),
        },
    )
    memo = Memo(
        matter_id=matter_id,
        created_by=user_id,
        title=payload.issue,
        source_run_id=run.id,
        content_json=content_json,
        content_markdown=content_markdown,
    )
    db.add(memo)
    return memo
