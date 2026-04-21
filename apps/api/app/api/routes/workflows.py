from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.domain import AIRun, Entity, Event, Memo
from app.schemas.audit import AIRunRead
from app.schemas.entity import (
    EntityAliasCreate,
    EntityDetailRead,
    EntityListItem,
    EntityMergeRequest,
)
from app.schemas.search import SearchRequest, SearchResponse
from app.schemas.workflow import (
    ChronologyRequest,
    ChronologyResponse,
    ChronologyEvent,
    ChronologyEventUpdate,
    ContradictionRequest,
    ContradictionResponse,
    GroundedQARequest,
    GroundedQAResponse,
    MemoCreateRequest,
    MemoRead,
    MemoUpdateRequest,
)
from app.services.audit import record_audit_event
from app.services.chronology import event_to_payload, list_chronology_events, update_chronology_event
from app.services.entities import (
    add_entity_alias,
    entity_to_detail,
    extract_entities_for_matter,
    list_entities_for_matter,
    merge_entities,
    refresh_entity_summary,
)
from app.services.exports import create_completed_export
from app.services.matter import ensure_matter_access
from app.services.memos import update_memo
from app.services.search import perform_search
from app.services.workflows import (
    run_chronology_builder,
    run_contradiction_finder,
    run_grounded_qa,
    run_issue_memo,
)

router = APIRouter()


@router.post("/matters/{matter_id}/search", response_model=SearchResponse)
def search_matter(
    matter_id: UUID,
    payload: SearchRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> SearchResponse:
    ensure_matter_access(db, matter_id, current_user)
    response = perform_search(db, matter_id, payload)
    record_audit_event(
        db,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        matter_id=matter_id,
        action="search_matter",
        target_type="matter",
        target_id=matter_id,
        metadata={"query": payload.query, "result_count": len(response.results)},
    )
    db.commit()
    return response


@router.post("/matters/{matter_id}/ask", response_model=GroundedQAResponse)
def ask_matter(
    matter_id: UUID,
    payload: GroundedQARequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> GroundedQAResponse:
    ensure_matter_access(db, matter_id, current_user)
    response = run_grounded_qa(db, matter_id, current_user.id, payload)
    db.commit()
    return response


@router.post("/matters/{matter_id}/chronology", response_model=ChronologyResponse)
def build_chronology(
    matter_id: UUID,
    payload: ChronologyRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> ChronologyResponse:
    ensure_matter_access(db, matter_id, current_user)
    response = run_chronology_builder(db, matter_id, current_user.id, payload)
    db.commit()
    return response


@router.get("/matters/{matter_id}/chronology/events", response_model=list[ChronologyEvent])
def get_chronology_events(
    matter_id: UUID,
    entity_name: str | None = None,
    conflict_only: bool = False,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[ChronologyEvent]:
    ensure_matter_access(db, matter_id, current_user)
    return list_chronology_events(db, matter_id, entity_name=entity_name, conflict_only=conflict_only)


@router.patch("/events/{event_id}", response_model=ChronologyEvent)
def patch_chronology_event(
    event_id: UUID,
    payload: ChronologyEventUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> ChronologyEvent:
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    ensure_matter_access(db, event.matter_id, current_user)
    update_chronology_event(db, event, payload)
    record_audit_event(
        db,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        matter_id=event.matter_id,
        action="update_chronology_event",
        target_type="event",
        target_id=event.id,
        metadata={"fields": sorted(payload.model_dump(exclude_unset=True).keys())},
    )
    db.commit()
    db.refresh(event)
    return event_to_payload(db, event.matter_id, event)


@router.get("/matters/{matter_id}/chronology/export.csv")
def export_chronology_csv(
    matter_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> Response:
    ensure_matter_access(db, matter_id, current_user)
    events = list_chronology_events(db, matter_id)
    export_job, artifact = create_completed_export(
        db,
        organization_id=current_user.organization_id,
        matter_id=matter_id,
        requested_by=current_user.id,
        export_type="chronology_csv",
        source_object_type="matter",
        source_object_id=matter_id,
        metadata={"event_count": len(events)},
    )
    record_audit_event(
        db,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        matter_id=matter_id,
        action="export_chronology_csv",
        target_type="export_job",
        target_id=export_job.id,
        metadata={"event_count": len(events)},
    )
    db.commit()
    return Response(
        content=artifact.content,
        media_type=artifact.content_type,
        headers={
            "content-disposition": f'attachment; filename="{artifact.file_name}"',
            "x-trace-export-id": str(export_job.id),
        },
    )


@router.get("/matters/{matter_id}/chronology/export.docx")
def export_chronology_docx(
    matter_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> Response:
    ensure_matter_access(db, matter_id, current_user)
    events = list_chronology_events(db, matter_id)
    export_job, artifact = create_completed_export(
        db,
        organization_id=current_user.organization_id,
        matter_id=matter_id,
        requested_by=current_user.id,
        export_type="chronology_docx",
        source_object_type="matter",
        source_object_id=matter_id,
        metadata={"event_count": len(events)},
    )
    record_audit_event(
        db,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        matter_id=matter_id,
        action="export_chronology_docx",
        target_type="export_job",
        target_id=export_job.id,
        metadata={"event_count": len(events)},
    )
    db.commit()
    return Response(
        content=artifact.content,
        media_type=artifact.content_type,
        headers={
            "content-disposition": f'attachment; filename="{artifact.file_name}"',
            "x-trace-export-id": str(export_job.id),
        },
    )


@router.post("/matters/{matter_id}/entities/extract", response_model=list[EntityListItem])
def extract_entities(
    matter_id: UUID, db: Session = Depends(get_db), current_user=Depends(get_current_user)
) -> list[EntityListItem]:
    ensure_matter_access(db, matter_id, current_user)
    entities = extract_entities_for_matter(db, matter_id, current_user.id)
    db.commit()
    return entities


@router.get("/matters/{matter_id}/entities", response_model=list[EntityListItem])
def list_entities(
    matter_id: UUID, db: Session = Depends(get_db), current_user=Depends(get_current_user)
) -> list[EntityListItem]:
    ensure_matter_access(db, matter_id, current_user)
    return list_entities_for_matter(db, matter_id)


@router.get("/entities/{entity_id}", response_model=EntityDetailRead)
def get_entity(
    entity_id: UUID, db: Session = Depends(get_db), current_user=Depends(get_current_user)
) -> EntityDetailRead:
    entity = db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
    ensure_matter_access(db, entity.matter_id, current_user)
    return entity_to_detail(db, entity)


@router.post("/entities/{entity_id}/aliases", response_model=EntityDetailRead)
def create_entity_alias(
    entity_id: UUID,
    payload: EntityAliasCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> EntityDetailRead:
    entity = db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
    ensure_matter_access(db, entity.matter_id, current_user)
    try:
        add_entity_alias(db, entity, payload.alias)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    refresh_entity_summary(db, entity, current_user.id)
    record_audit_event(
        db,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        matter_id=entity.matter_id,
        action="add_entity_alias",
        target_type="entity",
        target_id=entity.id,
        metadata={"alias": payload.alias},
    )
    db.commit()
    db.refresh(entity)
    return entity_to_detail(db, entity)


@router.post("/entities/{target_entity_id}/merge", response_model=EntityDetailRead)
def merge_entity_aliases(
    target_entity_id: UUID,
    payload: EntityMergeRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> EntityDetailRead:
    target = db.get(Entity, target_entity_id)
    source = db.get(Entity, payload.source_entity_id)
    if target is None or source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
    ensure_matter_access(db, target.matter_id, current_user)
    ensure_matter_access(db, source.matter_id, current_user)
    try:
        merge_entities(db, target, source)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    record_audit_event(
        db,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        matter_id=target.matter_id,
        action="merge_entity_alias",
        target_type="entity",
        target_id=target.id,
        metadata={"source_entity_id": str(payload.source_entity_id)},
    )
    db.commit()
    db.refresh(target)
    return entity_to_detail(db, target)


@router.post("/matters/{matter_id}/contradictions", response_model=ContradictionResponse)
def contradictions(
    matter_id: UUID,
    payload: ContradictionRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> ContradictionResponse:
    ensure_matter_access(db, matter_id, current_user)
    response = run_contradiction_finder(db, matter_id, current_user.id, payload)
    db.commit()
    return response


@router.post("/matters/{matter_id}/memos", response_model=MemoRead, status_code=status.HTTP_201_CREATED)
def create_memo(
    matter_id: UUID,
    payload: MemoCreateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> Memo:
    ensure_matter_access(db, matter_id, current_user)
    memo = run_issue_memo(db, matter_id, current_user.id, payload)
    db.commit()
    db.refresh(memo)
    return memo


@router.get("/memos/{memo_id}", response_model=MemoRead)
def get_memo(memo_id: UUID, db: Session = Depends(get_db), current_user=Depends(get_current_user)) -> Memo:
    memo = db.get(Memo, memo_id)
    if memo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memo not found")
    ensure_matter_access(db, memo.matter_id, current_user)
    return memo


@router.patch("/memos/{memo_id}", response_model=MemoRead)
def patch_memo(
    memo_id: UUID,
    payload: MemoUpdateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> Memo:
    memo = db.get(Memo, memo_id)
    if memo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memo not found")
    ensure_matter_access(db, memo.matter_id, current_user)
    try:
        update_memo(db, memo, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    record_audit_event(
        db,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        matter_id=memo.matter_id,
        action="update_memo",
        target_type="memo",
        target_id=memo.id,
        metadata={"fields": sorted(payload.model_dump(exclude_unset=True).keys())},
    )
    db.commit()
    db.refresh(memo)
    return memo


@router.get("/memos/{memo_id}/export.md")
def export_memo_markdown(
    memo_id: UUID, db: Session = Depends(get_db), current_user=Depends(get_current_user)
) -> Response:
    memo = db.get(Memo, memo_id)
    if memo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memo not found")
    ensure_matter_access(db, memo.matter_id, current_user)
    export_job, artifact = create_completed_export(
        db,
        organization_id=current_user.organization_id,
        matter_id=memo.matter_id,
        requested_by=current_user.id,
        export_type="memo_markdown",
        source_object_type="memo",
        source_object_id=memo.id,
        metadata={"memo_type": memo.memo_type},
    )
    record_audit_event(
        db,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        matter_id=memo.matter_id,
        action="export_memo_markdown",
        target_type="export_job",
        target_id=export_job.id,
        metadata={"memo_type": memo.memo_type},
    )
    db.commit()
    return Response(
        content=artifact.content,
        media_type=artifact.content_type,
        headers={
            "content-disposition": f'attachment; filename="{artifact.file_name}"',
            "x-trace-export-id": str(export_job.id),
        },
    )


@router.get("/memos/{memo_id}/export.docx")
def export_memo_docx(
    memo_id: UUID, db: Session = Depends(get_db), current_user=Depends(get_current_user)
) -> Response:
    memo = db.get(Memo, memo_id)
    if memo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memo not found")
    ensure_matter_access(db, memo.matter_id, current_user)
    export_job, artifact = create_completed_export(
        db,
        organization_id=current_user.organization_id,
        matter_id=memo.matter_id,
        requested_by=current_user.id,
        export_type="memo_docx",
        source_object_type="memo",
        source_object_id=memo.id,
        metadata={"memo_type": memo.memo_type},
    )
    record_audit_event(
        db,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        matter_id=memo.matter_id,
        action="export_memo_docx",
        target_type="export_job",
        target_id=export_job.id,
        metadata={"memo_type": memo.memo_type},
    )
    db.commit()
    return Response(
        content=artifact.content,
        media_type=artifact.content_type,
        headers={
            "content-disposition": f'attachment; filename="{artifact.file_name}"',
            "x-trace-export-id": str(export_job.id),
        },
    )


@router.get("/ai-runs/{run_id}", response_model=AIRunRead)
def get_ai_run(run_id: UUID, db: Session = Depends(get_db), current_user=Depends(get_current_user)) -> AIRun:
    run = db.get(AIRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI run not found")
    ensure_matter_access(db, run.matter_id, current_user)
    return run
