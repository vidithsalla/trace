from __future__ import annotations

import csv
import re
from io import BytesIO
from io import StringIO
from uuid import UUID

from docx import Document as DocxDocument
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.domain import Document, Event, EventCitation
from app.schemas.workflow import ChronologyEvent, ChronologyEventUpdate


SPACE_RE = re.compile(r"\s+")


def event_to_payload(db: Session, matter_id: UUID, event: Event) -> ChronologyEvent:
    citations: list = []
    rows = db.execute(
        select(EventCitation, Document)
        .join(Document, Document.id == EventCitation.document_id)
        .where(EventCitation.event_id == event.id, Document.matter_id == matter_id)
        .order_by(EventCitation.created_at.asc())
    ).all()
    from app.schemas.workflow import CitationPayload
    from app.services.citations import build_viewer_url

    for citation, document in rows:
        payload = CitationPayload(
            id=citation.id,
            document_id=citation.document_id,
            document_name=document.display_name or document.file_name,
            page=citation.page_number,
            chunk_id=citation.chunk_id,
            quote=citation.quote,
            validation_status="validated",
        )
        citations.append(payload.model_copy(update={"viewer_url": build_viewer_url(matter_id, payload)}))

    return ChronologyEvent(
        id=event.id,
        date=event.event_date,
        date_text=event.event_date_text,
        date_confidence=event.event_date_confidence,
        title=event.title,
        description=event.description,
        entity_names=list(event.entities_json or []),
        citations=citations,
        conflict_flag=event.conflict_flag,
        confidence=event.confidence,
        source_type=event.source_type,
    )


def list_chronology_events(
    db: Session,
    matter_id: UUID,
    *,
    entity_name: str | None = None,
    conflict_only: bool = False,
) -> list[ChronologyEvent]:
    stmt = select(Event).where(Event.matter_id == matter_id).order_by(
        Event.event_date.asc().nullslast(), Event.event_date_text.asc().nullslast(), Event.created_at.asc()
    )
    if conflict_only:
        stmt = stmt.where(Event.conflict_flag.is_(True))
    rows = list(db.scalars(stmt))
    payloads = [event_to_payload(db, matter_id, event) for event in rows]
    if entity_name:
        needle = entity_name.lower()
        payloads = [
            event
            for event in payloads
            if any(needle in entity.lower() for entity in event.entity_names)
            or needle in event.title.lower()
            or needle in event.description.lower()
        ]
    return payloads


def update_chronology_event(db: Session, event: Event, payload: ChronologyEventUpdate) -> Event:
    update = payload.model_dump(exclude_unset=True)
    if "date" in update:
        event.event_date = update["date"]
    if "date_text" in update:
        event.event_date_text = update["date_text"]
    if "date_confidence" in update and update["date_confidence"] is not None:
        event.event_date_confidence = update["date_confidence"]
    if "title" in update and update["title"] is not None:
        event.title = update["title"]
    if "description" in update and update["description"] is not None:
        event.description = update["description"]
    if "entity_names" in update and update["entity_names"] is not None:
        event.entities_json = update["entity_names"]
    if "conflict_flag" in update and update["conflict_flag"] is not None:
        event.conflict_flag = update["conflict_flag"]
    if "confidence" in update and update["confidence"] is not None:
        event.confidence = update["confidence"]
    event.source_type = "user_edited"
    return event


def collapse_duplicate_events(events: list[ChronologyEvent]) -> list[ChronologyEvent]:
    collapsed: dict[str, ChronologyEvent] = {}
    for event in events:
        key = _event_key(event)
        existing = collapsed.get(key)
        if existing is None:
            collapsed[key] = event
            continue
        citation_keys = {
            (
                citation.document_id,
                citation.chunk_id,
                citation.page,
                _normalize(citation.quote).lower(),
            )
            for citation in existing.citations
        }
        citations = list(existing.citations)
        for citation in event.citations:
            citation_key = (
                citation.document_id,
                citation.chunk_id,
                citation.page,
                _normalize(citation.quote).lower(),
            )
            if citation_key not in citation_keys:
                citations.append(citation)
                citation_keys.add(citation_key)
        entities = sorted({*existing.entity_names, *event.entity_names})
        collapsed[key] = existing.model_copy(update={"citations": citations, "entity_names": entities})
    return list(collapsed.values())


def replace_run_events(
    db: Session,
    matter_id: UUID,
    run_id: UUID,
    events: list[ChronologyEvent],
) -> list[ChronologyEvent]:
    db.execute(
        delete(Event).where(
            Event.matter_id == matter_id,
            Event.source_type == "ai_extracted",
        )
    )
    persisted: list[ChronologyEvent] = []
    for event_payload in events:
        if not event_payload.citations:
            continue
        event = Event(
            matter_id=matter_id,
            event_date=event_payload.date,
            event_date_text=event_payload.date_text,
            event_date_confidence=event_payload.date_confidence,
            title=event_payload.title,
            description=event_payload.description,
            entities_json=event_payload.entity_names,
            source_type=event_payload.source_type,
            confidence=event_payload.confidence,
            conflict_flag=event_payload.conflict_flag,
            created_by_run_id=run_id,
        )
        db.add(event)
        db.flush()
        persisted_citations = []
        for citation_payload in event_payload.citations:
            citation = EventCitation(
                event_id=event.id,
                document_id=citation_payload.document_id,
                chunk_id=citation_payload.chunk_id,
                page_number=citation_payload.page,
                quote=citation_payload.quote,
            )
            db.add(citation)
            db.flush()
            persisted_citations.append(citation_payload.model_copy(update={"id": citation.id}))
        persisted.append(event_payload.model_copy(update={"id": event.id, "citations": persisted_citations}))
    return persisted


def render_chronology_csv(events: list[ChronologyEvent]) -> str:
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "date",
            "date_text",
            "date_confidence",
            "title",
            "description",
            "entities",
            "conflict_flag",
            "confidence",
            "citations",
        ]
    )
    for event in events:
        writer.writerow(
            [
                event.date.isoformat() if event.date else "",
                event.date_text or "",
                event.date_confidence,
                event.title,
                event.description,
                "; ".join(event.entity_names),
                "true" if event.conflict_flag else "false",
                event.confidence,
                " | ".join(
                    f"{citation.document_name} p.{citation.page or 1}: {citation.quote}"
                    for citation in event.citations
                ),
            ]
        )
    return output.getvalue()


def render_chronology_docx(events: list[ChronologyEvent]) -> bytes:
    document = DocxDocument()
    document.add_heading("Trace Chronology", level=1)
    if not events:
        document.add_paragraph("No chronology events are currently saved for this matter.")
    for event in events:
        date_label = event.date.isoformat() if event.date else event.date_text or "Undated"
        document.add_heading(f"{date_label}: {event.title}", level=2)
        document.add_paragraph(event.description)
        details = [
            f"Date confidence: {event.date_confidence}",
            f"Confidence: {event.confidence}",
            f"Disputed: {'yes' if event.conflict_flag else 'no'}",
        ]
        if event.entity_names:
            details.append(f"Entities: {', '.join(event.entity_names)}")
        for detail in details:
            document.add_paragraph(detail, style="List Bullet")
        if event.citations:
            document.add_paragraph("Citations:")
            for citation in event.citations:
                document.add_paragraph(
                    f"{citation.document_name} p.{citation.page or 1}: {citation.quote}",
                    style="List Bullet",
                )
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def _event_key(event: ChronologyEvent) -> str:
    title = _normalize(event.title).lower()
    description = _normalize(event.description).lower()
    return f"{event.date or event.date_text}|{title[:80]}|{description[:120]}"


def _normalize(value: str) -> str:
    return SPACE_RE.sub(" ", value).strip()
