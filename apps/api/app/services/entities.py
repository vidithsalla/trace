from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.domain import AIRun, Document, DocumentChunk, Entity, EntityMention, Event, Matter
from app.schemas.entity import (
    EntityDetailRead,
    EntityKeyDocument,
    EntityListItem,
    EntityMentionRead,
    EntityTimelineItem,
)
from app.schemas.workflow import CitationPayload
from app.services.audit import record_audit_event
from app.services.citations import build_viewer_url
from app.services.model_client import EvidenceItem, ModelClient
from app.services.mock_model_client import MockModelClient
from app.services.openai_compatible_model_client import OpenAICompatibleModelClient


@dataclass(frozen=True, slots=True)
class EntityCandidate:
    canonical_name: str
    entity_type: str
    aliases: tuple[str, ...] = ()
    confidence: float = 0.8
    source: str = "heuristic"


KNOWN_ENTITY_CANDIDATES = [
    EntityCandidate("Jane Mercer", "person", ("J. Mercer",), 0.98, "seed_truth"),
    EntityCandidate("Priya Shah", "person", (), 0.98, "seed_truth"),
    EntityCandidate(
        "Northshore Supply LLC",
        "organization",
        ("Northshore Supply", "Northshore", "NS Supply"),
        0.98,
        "seed_truth",
    ),
    EntityCandidate(
        "Acme Industrial Systems",
        "organization",
        ("Acme Industrial", "Acme"),
        0.98,
        "seed_truth",
    ),
    EntityCandidate("Project Falcon", "project", ("Project Falcon Upgrade",), 0.98, "seed_truth"),
    EntityCandidate(
        "Compressor Unit 7A",
        "equipment",
        ("Unit 7A", "7A", "Compressor 7A"),
        0.98,
        "seed_truth",
    ),
]

CAPITALIZED_PHRASE_RE = re.compile(
    r"\b(?:[A-Z][a-z0-9]+|[A-Z]{2,})(?:\s+(?:[A-Z][a-z0-9]+|[A-Z]{2,})){1,4}\b"
)
SKIP_CANDIDATES = {
    "Seed Document",
    "Trace Demo",
    "March",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
}


def extract_entities_for_matter(
    db: Session,
    matter_id: UUID,
    user_id: UUID | None = None,
    *,
    document_ids: list[UUID] | None = None,
    summarize: bool = True,
) -> list[EntityListItem]:
    matter = db.get(Matter, matter_id)
    if matter is None:
        raise ValueError("Matter not found")

    chunks = _matter_chunks(db, matter_id, document_ids=document_ids)
    candidates = _candidate_catalog(chunks)
    entities_by_key = _load_entity_index(db, matter_id)
    extracted_entities: dict[UUID, Entity] = {}

    if document_ids:
        db.execute(delete(EntityMention).where(EntityMention.document_id.in_(document_ids)))
    else:
        entity_ids = list(db.scalars(select(Entity.id).where(Entity.matter_id == matter_id)))
        if entity_ids:
            db.execute(delete(EntityMention).where(EntityMention.entity_id.in_(entity_ids)))

    for candidate in candidates:
        entity = _ensure_entity(db, matter_id, candidate, entities_by_key)
        extracted_entities[entity.id] = entity
        _extract_mentions_for_candidate(db, entity, candidate, chunks)

    db.flush()
    if summarize:
        for entity in sorted(extracted_entities.values(), key=lambda item: item.canonical_name):
            refresh_entity_summary(db, entity, user_id)

    record_audit_event(
        db,
        organization_id=matter.organization_id,
        user_id=user_id,
        matter_id=matter_id,
        action="extract_entities",
        target_type="matter",
        target_id=matter_id,
        metadata={
            "entity_count": len(extracted_entities),
            "document_scope": [str(document_id) for document_id in document_ids or []],
        },
    )
    return list_entities_for_matter(db, matter_id)


def list_entities_for_matter(db: Session, matter_id: UUID) -> list[EntityListItem]:
    entities = list(
        db.scalars(select(Entity).where(Entity.matter_id == matter_id).order_by(Entity.canonical_name))
    )
    return [entity_to_list_item(db, entity) for entity in entities]


def entity_to_detail(db: Session, entity: Entity) -> EntityDetailRead:
    list_item = entity_to_list_item(db, entity)
    mentions = _entity_mentions(db, entity)
    timeline = _entity_timeline(db, entity)
    return EntityDetailRead(
        **list_item.model_dump(),
        mentions=mentions,
        timeline=timeline,
    )


def entity_to_list_item(db: Session, entity: Entity) -> EntityListItem:
    mention_count = db.scalar(
        select(func.count()).select_from(EntityMention).where(EntityMention.entity_id == entity.id)
    ) or 0
    last_seen_at = db.scalar(
        select(func.max(EntityMention.created_at)).where(EntityMention.entity_id == entity.id)
    )
    return EntityListItem(
        id=entity.id,
        matter_id=entity.matter_id,
        entity_type=entity.entity_type,
        canonical_name=entity.canonical_name,
        aliases_json=list(entity.aliases_json or []),
        summary_json=dict(entity.summary_json or {}),
        confidence=_float_or_none(entity.confidence),
        is_user_curated=entity.is_user_curated,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
        mention_count=mention_count,
        key_documents=_key_documents(db, entity),
        last_seen_at=last_seen_at,
    )


def add_entity_alias(db: Session, entity: Entity, alias: str) -> Entity:
    clean_alias = alias.strip()
    if not clean_alias:
        raise ValueError("Alias is required")
    aliases = list(entity.aliases_json or [])
    if clean_alias.lower() not in {item.lower() for item in aliases} | {entity.canonical_name.lower()}:
        aliases.append(clean_alias)
        entity.aliases_json = aliases
        entity.is_user_curated = True
    return entity


def merge_entities(db: Session, target: Entity, source: Entity) -> Entity:
    if target.matter_id != source.matter_id:
        raise ValueError("Cannot merge entities across matters")
    aliases = list(target.aliases_json or [])
    alias_keys = {alias.lower() for alias in aliases}
    for alias in [source.canonical_name, *(source.aliases_json or [])]:
        if alias.lower() != target.canonical_name.lower() and alias.lower() not in alias_keys:
            aliases.append(alias)
            alias_keys.add(alias.lower())
    target.aliases_json = aliases
    target.is_user_curated = True
    for mention in db.scalars(select(EntityMention).where(EntityMention.entity_id == source.id)):
        mention.entity_id = target.id
    db.delete(source)
    db.flush()
    refresh_entity_summary(db, target, None)
    return target


def refresh_entity_summary(db: Session, entity: Entity, user_id: UUID | None) -> Entity:
    evidence = _entity_evidence(db, entity, limit=8)
    client = _get_model_client()
    summary = client.entity_summary(entity.canonical_name, evidence)
    run = AIRun(
        matter_id=entity.matter_id,
        user_id=user_id or _fallback_user_id(db, entity.matter_id),
        run_type="entity_summary",
        model_name=client.model_name,
        prompt_template_version="entity_summary_v1",
        status="completed",
        input_json={
            "entity_id": str(entity.id),
            "canonical_name": entity.canonical_name,
            "aliases": list(entity.aliases_json or []),
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
        output_json=summary,
    )
    db.add(run)
    db.flush()
    entity.summary_json = {
        **summary,
        "ai_run_id": str(run.id),
        "workflow": "entity_summary_v1",
        "mention_count": len(evidence),
    }
    return entity


def _matter_chunks(
    db: Session, matter_id: UUID, *, document_ids: list[UUID] | None
) -> list[tuple[DocumentChunk, Document]]:
    stmt = (
        select(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunk.matter_id == matter_id)
        .order_by(Document.created_at.asc(), DocumentChunk.chunk_index.asc())
    )
    if document_ids:
        stmt = stmt.where(DocumentChunk.document_id.in_(document_ids))
    return list(db.execute(stmt).all())


def _candidate_catalog(chunks: list[tuple[DocumentChunk, Document]]) -> list[EntityCandidate]:
    candidates = {candidate.canonical_name.lower(): candidate for candidate in KNOWN_ENTITY_CANDIDATES}
    for chunk, document in chunks:
        for phrase in CAPITALIZED_PHRASE_RE.findall(f"{document.file_name} {chunk.text}"):
            candidate = _candidate_from_phrase(phrase)
            if candidate is not None and candidate.canonical_name.lower() not in candidates:
                candidates[candidate.canonical_name.lower()] = candidate
    return list(candidates.values())


def _candidate_from_phrase(phrase: str) -> EntityCandidate | None:
    clean = " ".join(phrase.split()).strip(" .,:;")
    if clean in SKIP_CANDIDATES or len(clean) < 5:
        return None
    if any(skip in clean for skip in SKIP_CANDIDATES):
        return None
    entity_type = "organization" if any(term in clean for term in ["LLC", "Supply", "Industrial"]) else "person"
    if "Project" in clean:
        entity_type = "project"
    if "Unit" in clean or "Compressor" in clean:
        entity_type = "equipment"
    return EntityCandidate(clean, entity_type, (), 0.72, "capitalized_phrase")


def _ensure_entity(
    db: Session,
    matter_id: UUID,
    candidate: EntityCandidate,
    entities_by_key: dict[str, Entity],
) -> Entity:
    for name in [candidate.canonical_name, *candidate.aliases]:
        existing = entities_by_key.get(_entity_key(name))
        if existing is not None:
            aliases = list(existing.aliases_json or [])
            alias_keys = {_entity_key(alias) for alias in aliases}
            for alias in candidate.aliases:
                if _entity_key(alias) != _entity_key(existing.canonical_name) and _entity_key(alias) not in alias_keys:
                    aliases.append(alias)
                    alias_keys.add(_entity_key(alias))
            existing.aliases_json = aliases
            if existing.confidence is None or float(existing.confidence) < candidate.confidence:
                existing.confidence = candidate.confidence
            _index_entity(entities_by_key, existing)
            return existing

    entity = Entity(
        matter_id=matter_id,
        entity_type=candidate.entity_type,
        canonical_name=candidate.canonical_name,
        aliases_json=list(candidate.aliases),
        confidence=candidate.confidence,
        summary_json={},
    )
    db.add(entity)
    db.flush()
    _index_entity(entities_by_key, entity)
    return entity


def _extract_mentions_for_candidate(
    db: Session,
    entity: Entity,
    candidate: EntityCandidate,
    chunks: list[tuple[DocumentChunk, Document]],
) -> None:
    aliases = [entity.canonical_name, *(entity.aliases_json or []), *candidate.aliases]
    seen_aliases: set[str] = set()
    unique_aliases = []
    for alias in aliases:
        key = _entity_key(alias)
        if key and key not in seen_aliases:
            unique_aliases.append(alias)
            seen_aliases.add(key)

    for chunk, document in chunks:
        for alias in unique_aliases:
            match = _find_alias(alias, chunk.text)
            if match is None:
                continue
            context = _context_window(chunk.text, match.start(), match.end())
            db.add(
                EntityMention(
                    entity_id=entity.id,
                    document_id=document.id,
                    chunk_id=chunk.id,
                    page_number=chunk.page_start,
                    mention_text=match.group(0),
                    context_text=context,
                    confidence=candidate.confidence,
                    metadata_json={
                        "canonical_name": entity.canonical_name,
                        "matched_alias": alias,
                        "source": candidate.source,
                    },
                )
            )


def _find_alias(alias: str, text: str) -> re.Match[str] | None:
    if len(alias.strip()) < 2:
        return None
    pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])", re.IGNORECASE)
    return pattern.search(text)


def _context_window(text: str, start: int, end: int, radius: int = 180) -> str:
    context_start = max(start - radius, 0)
    context_end = min(end + radius, len(text))
    return text[context_start:context_end].strip()


def _entity_mentions(db: Session, entity: Entity, limit: int = 50) -> list[EntityMentionRead]:
    rows = db.execute(
        select(EntityMention, Document)
        .join(Document, Document.id == EntityMention.document_id)
        .where(EntityMention.entity_id == entity.id)
        .order_by(EntityMention.created_at.asc())
        .limit(limit)
    ).all()
    mentions = []
    for mention, document in rows:
        citation = CitationPayload(
            document_id=document.id,
            document_name=document.display_name or document.file_name,
            page=mention.page_number,
            chunk_id=mention.chunk_id,
            quote=mention.context_text or mention.mention_text,
            validation_status="validated",
        )
        mentions.append(
            EntityMentionRead(
                id=mention.id,
                entity_id=mention.entity_id,
                document_id=mention.document_id,
                document_name=document.display_name or document.file_name,
                chunk_id=mention.chunk_id,
                page_number=mention.page_number,
                mention_text=mention.mention_text,
                context_text=mention.context_text,
                viewer_url=build_viewer_url(entity.matter_id, citation),
                confidence=_float_or_none(mention.confidence),
                metadata_json=dict(mention.metadata_json or {}),
                created_at=mention.created_at,
            )
        )
    return mentions


def _key_documents(db: Session, entity: Entity) -> list[EntityKeyDocument]:
    rows = db.execute(
        select(Document.id, Document.display_name, Document.file_name, func.count(EntityMention.id).label("count"))
        .join(EntityMention, EntityMention.document_id == Document.id)
        .where(EntityMention.entity_id == entity.id)
        .group_by(Document.id, Document.display_name, Document.file_name)
        .order_by(func.count(EntityMention.id).desc(), Document.created_at.asc())
        .limit(5)
    ).all()
    return [
        EntityKeyDocument(
            document_id=document_id,
            document_name=display_name or file_name,
            mention_count=count,
        )
        for document_id, display_name, file_name, count in rows
    ]


def _entity_timeline(db: Session, entity: Entity) -> list[EntityTimelineItem]:
    names = [entity.canonical_name, *(entity.aliases_json or [])]
    events = list(db.scalars(select(Event).where(Event.matter_id == entity.matter_id)))
    matched = []
    for event in events:
        haystack = " ".join([event.title, event.description, " ".join(event.entities_json or [])]).lower()
        if any(name.lower() in haystack for name in names):
            matched.append(event)
    matched.sort(key=lambda event: (event.event_date is None, event.event_date, event.created_at))
    return [
        EntityTimelineItem(
            event_id=event.id,
            date=event.event_date,
            date_text=event.event_date_text,
            title=event.title,
            description=event.description,
            conflict_flag=event.conflict_flag,
        )
        for event in matched[:20]
    ]


def _entity_evidence(db: Session, entity: Entity, limit: int) -> list[EvidenceItem]:
    rows = db.execute(
        select(EntityMention, Document, DocumentChunk)
        .join(Document, Document.id == EntityMention.document_id)
        .join(DocumentChunk, DocumentChunk.id == EntityMention.chunk_id)
        .where(EntityMention.entity_id == entity.id)
        .order_by(EntityMention.created_at.asc())
        .limit(limit)
    ).all()
    return [
        EvidenceItem(
            document_id=document.id,
            document_name=document.display_name or document.file_name,
            page=mention.page_number,
            chunk_id=mention.chunk_id,
            quote=mention.context_text or mention.mention_text,
            text=chunk.text,
        )
        for mention, document, chunk in rows
    ]


def _load_entity_index(db: Session, matter_id: UUID) -> dict[str, Entity]:
    entities_by_key: dict[str, Entity] = {}
    for entity in db.scalars(select(Entity).where(Entity.matter_id == matter_id)):
        _index_entity(entities_by_key, entity)
    return entities_by_key


def _index_entity(entities_by_key: dict[str, Entity], entity: Entity) -> None:
    entities_by_key[_entity_key(entity.canonical_name)] = entity
    for alias in entity.aliases_json or []:
        entities_by_key[_entity_key(alias)] = entity


def _entity_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _float_or_none(value: float | Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _get_model_client() -> ModelClient:
    if settings.model_provider == "openai_compatible":
        return OpenAICompatibleModelClient(
            model_name=settings.model_name,
            base_url=settings.model_base_url,
        )
    return MockModelClient(model_name=settings.model_name)


def _fallback_user_id(db: Session, matter_id: UUID) -> UUID:
    matter = db.get(Matter, matter_id)
    if matter is None:
        raise ValueError("Matter not found")
    return matter.created_by
