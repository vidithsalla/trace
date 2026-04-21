from uuid import UUID

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from app.db.session import SessionLocal
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
