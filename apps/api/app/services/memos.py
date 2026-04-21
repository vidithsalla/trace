from __future__ import annotations

from io import BytesIO
from uuid import UUID

from docx import Document as DocxDocument
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import Document, DocumentChunk, Memo
from app.schemas.search import SearchRequest
from app.schemas.workflow import CitationPayload, MemoUpdateRequest
from app.services.contradictions import build_contradiction_evidence_pack
from app.services.model_client import EvidenceItem, MemoDraft
from app.services.search import perform_search


REQUIRED_MEMO_SECTIONS = [
    "issue",
    "answer_in_brief",
    "supporting_facts",
    "contrary_facts",
    "gaps",
    "next_documents_to_review",
]


def build_issue_memo_evidence_pack(
    db: Session,
    matter_id: UUID,
    issue: str,
    *,
    limit: int = 12,
) -> list[EvidenceItem]:
    contradiction_pack = build_contradiction_evidence_pack(db, matter_id, issue, limit=limit)
    evidence: list[EvidenceItem] = []
    seen_chunks: set[UUID] = set()
    for item in contradiction_pack.evidence:
        if item.chunk_id and item.chunk_id not in seen_chunks:
            evidence.append(item)
            seen_chunks.add(item.chunk_id)

    search_response = perform_search(db, matter_id, SearchRequest(query=issue, limit=limit))
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
        if len(evidence) >= limit:
            return evidence

    for chunk, document in _top_chunks(db, matter_id, limit):
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
        if len(evidence) >= limit:
            break
    return evidence


def structured_memo_content(
    *,
    issue: str,
    draft: MemoDraft,
    supporting_facts: list[dict],
    contrary_facts: list[dict],
) -> dict:
    content = {
        "issue": issue,
        "answer_in_brief": draft.answer_in_brief,
        "supporting_facts": supporting_facts,
        "contrary_facts": contrary_facts,
        "gaps": list(draft.gaps),
        "next_documents_to_review": list(draft.next_documents_to_review),
    }
    validate_memo_content(content)
    return content


def fact_to_content(statement: str, citations: list[CitationPayload]) -> dict:
    return {
        "statement": statement,
        "citation_ids": [str(citation.id) for citation in citations if citation.id],
        "citations": [citation.model_dump(mode="json") for citation in citations],
    }


def validate_memo_content(content: dict) -> None:
    missing = [section for section in REQUIRED_MEMO_SECTIONS if section not in content]
    if missing:
        raise ValueError(f"Memo is missing required section(s): {', '.join(missing)}")
    for key in ["supporting_facts", "contrary_facts", "gaps", "next_documents_to_review"]:
        if not isinstance(content[key], list):
            raise ValueError(f"Memo section must be a list: {key}")
    if not str(content["issue"]).strip():
        raise ValueError("Memo issue is required")
    if not str(content["answer_in_brief"]).strip():
        raise ValueError("Memo answer_in_brief is required")
    _validate_fact_citations(content["supporting_facts"], "supporting_facts")
    _validate_fact_citations(content["contrary_facts"], "contrary_facts")


def render_memo_markdown(content: dict) -> str:
    validate_memo_content(content)
    lines = [
        f"# {content['issue']}",
        "",
        "## Answer in Brief",
        str(content["answer_in_brief"]),
        "",
        "## Supporting Facts",
        *_fact_lines(content["supporting_facts"]),
        "",
        "## Contrary Facts",
        *_fact_lines(content["contrary_facts"]),
        "",
        "## Gaps",
        *_simple_lines(content["gaps"]),
        "",
        "## Next Documents to Review",
        *_simple_lines(content["next_documents_to_review"]),
        "",
    ]
    return "\n".join(lines)


def render_memo_docx(content: dict) -> bytes:
    validate_memo_content(content)
    document = DocxDocument()
    document.add_heading(str(content["issue"]), level=1)
    document.add_heading("Answer in Brief", level=2)
    document.add_paragraph(str(content["answer_in_brief"]))
    document.add_heading("Supporting Facts", level=2)
    _add_fact_paragraphs(document, content["supporting_facts"])
    document.add_heading("Contrary Facts", level=2)
    _add_fact_paragraphs(document, content["contrary_facts"])
    document.add_heading("Gaps", level=2)
    for item in content["gaps"]:
        document.add_paragraph(str(item), style="List Bullet")
    document.add_heading("Next Documents to Review", level=2)
    for item in content["next_documents_to_review"]:
        document.add_paragraph(str(item), style="List Bullet")
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def update_memo(db: Session, memo: Memo, payload: MemoUpdateRequest) -> Memo:
    if payload.title is not None:
        memo.title = payload.title
    if payload.status is not None:
        memo.status = payload.status
    if payload.content_json is not None:
        validate_memo_content(payload.content_json)
        memo.content_json = payload.content_json
        memo.content_markdown = render_memo_markdown(payload.content_json)
    elif payload.content_markdown is not None:
        memo.content_markdown = payload.content_markdown
    db.flush()
    return memo


def _top_chunks(db: Session, matter_id: UUID, limit: int) -> list[tuple[DocumentChunk, Document]]:
    return list(
        db.execute(
            select(DocumentChunk, Document)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.matter_id == matter_id)
            .order_by(DocumentChunk.created_at.asc())
            .limit(limit)
        ).all()
    )


def _validate_fact_citations(facts: list, section: str) -> None:
    for index, fact in enumerate(facts, start=1):
        if not isinstance(fact, dict) or not str(fact.get("statement", "")).strip():
            raise ValueError(f"Memo {section} item {index} must include a statement")
        citations = fact.get("citations", [])
        if not isinstance(citations, list) or not citations:
            raise ValueError(f"Memo {section} item {index} must include at least one citation")


def _fact_lines(facts: list[dict]) -> list[str]:
    if not facts:
        return ["- None identified from the current record."]
    lines = []
    for fact in facts:
        citations = fact.get("citations", [])
        labels = [
            f"{citation.get('document_name', 'Source')} p.{citation.get('page') or 1}"
            for citation in citations
        ]
        suffix = f" ({'; '.join(labels)})" if labels else ""
        lines.append(f"- {fact['statement']}{suffix}")
    return lines


def _simple_lines(items: list) -> list[str]:
    if not items:
        return ["- None identified."]
    return [f"- {item}" for item in items]


def _add_fact_paragraphs(document: DocxDocument, facts: list[dict]) -> None:
    if not facts:
        document.add_paragraph("None identified from the current record.", style="List Bullet")
        return
    for fact in facts:
        citations = fact.get("citations", [])
        labels = [
            f"{citation.get('document_name', 'Source')} p.{citation.get('page') or 1}"
            for citation in citations
        ]
        suffix = f" ({'; '.join(labels)})" if labels else ""
        document.add_paragraph(f"{fact['statement']}{suffix}", style="List Bullet")
