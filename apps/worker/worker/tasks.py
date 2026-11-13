from uuid import UUID

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from app.db.session import SessionLocal
from app.services.analysis import execute_analysis
from app.services.evidence_versions import refresh_planner_statistics
from app.services.exports import process_export_job
from app.services.ingestion import mark_ingest_failed, process_document
from worker.settings import settings

broker = RedisBroker(url=settings.redis_url)
dramatiq.set_broker(broker)


@dramatiq.actor(queue_name="ingestion")
def ingest_document(document_id: str) -> None:
    parsed_document_id = UUID(document_id)
    with SessionLocal() as db:
        try:
            process_document(db, parsed_document_id)
            db.commit()
            refresh_planner_statistics(db)
            db.commit()
        except Exception as exc:
            db.rollback()
            mark_ingest_failed(db, parsed_document_id, exc)
            db.commit()
            raise


@dramatiq.actor(queue_name="exports")
def export_job(export_id: str) -> None:
    parsed_export_id = UUID(export_id)
    with SessionLocal() as db:
        try:
            process_export_job(db, parsed_export_id)
            db.commit()
        except Exception:
            db.rollback()
            raise


@dramatiq.actor(queue_name="analysis", max_retries=0, time_limit=15 * 60 * 1000)
def run_analysis(run_id: str) -> None:
    # No automatic retries: a model call may already have happened, and re-running silently
    # would multiply cost. execute_analysis marks the run FAILED with a typed error instead.
    with SessionLocal() as db:
        execute_analysis(db, UUID(run_id))
