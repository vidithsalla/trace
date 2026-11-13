from collections.abc import Generator
from io import BytesIO
from uuid import uuid4

import fitz
import pytest
from docx import Document as DocxDocument
from openpyxl import Workbook
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.domain import (
    Document,
    DocumentChunk,
    IngestJob,
    Matter,
    MatterMember,
    Organization,
    User,
)
from app.schemas.search import SearchRequest
from app.services.ingestion import chunk_pages, process_document
from app.services.parsers import ParsedPage, get_parser
from app.services.search import perform_search
from app.services.storage import storage_service


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def phase3_records(db: Session) -> Generator[dict[str, object], None, None]:
    suffix = uuid4().hex
    org = Organization(name=f"Phase 3 Test {suffix}", slug=f"phase-3-{suffix}")
    db.add(org)
    db.flush()

    attorney = User(
        organization_id=org.id,
        email=f"phase3-{suffix}@trace.local",
        name="Phase Three Attorney",
        global_role="member",
        password_hash=hash_password("correct-password"),
    )
    db.add(attorney)
    db.flush()

    matter = Matter(
        organization_id=org.id,
        name=f"Phase 3 Matter {suffix}",
        matter_code=f"P3-{suffix[:8]}",
        created_by=attorney.id,
    )
    other_matter = Matter(
        organization_id=org.id,
        name=f"Phase 3 Other Matter {suffix}",
        matter_code=f"P3O-{suffix[:8]}",
        created_by=attorney.id,
    )
    db.add_all([matter, other_matter])
    db.flush()
    db.add_all(
        [
            MatterMember(matter_id=matter.id, user_id=attorney.id, role="attorney"),
            MatterMember(matter_id=other_matter.id, user_id=attorney.id, role="attorney"),
        ]
    )
    db.commit()

    storage_keys: list[str] = []
    yield {
        "org": org,
        "attorney": attorney,
        "matter": matter,
        "other_matter": other_matter,
        "storage_keys": storage_keys,
    }

    for key in storage_keys:
        storage_service.delete_object(key)
    matter_ids = list(db.scalars(select(Matter.id).where(Matter.organization_id == org.id)))
    if matter_ids:
        db.execute(delete(Document).where(Document.matter_id.in_(matter_ids)))
    db.execute(delete(Organization).where(Organization.id == org.id))
    db.commit()


def test_parser_registry_covers_mvp_file_types() -> None:
    assert get_parser("text/plain", "note.txt").parse(b"plain text", file_name="note.txt").pages
    assert get_parser("text/csv", "rows.csv").parse(b"name,value\nJane,7", file_name="rows.csv").pages

    docx_buffer = BytesIO()
    docx = DocxDocument()
    docx.add_paragraph("Jane Mercer inspected Compressor Unit 7A.")
    docx.save(docx_buffer)
    docx_result = get_parser(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "memo.docx"
    ).parse(docx_buffer.getvalue(), file_name="memo.docx")
    assert "Compressor Unit 7A" in docx_result.pages[0].normalized_text

    xlsx_buffer = BytesIO()
    workbook = Workbook()
    workbook.active.append(["Project", "Falcon"])
    workbook.save(xlsx_buffer)
    xlsx_result = get_parser(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "facts.xlsx"
    ).parse(xlsx_buffer.getvalue(), file_name="facts.xlsx")
    assert "Falcon" in xlsx_result.pages[0].normalized_text

    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "Northshore knew of the compressor defect before shipment.")
    pdf_bytes = pdf.tobytes()
    pdf.close()
    pdf_result = get_parser("application/pdf", "report.pdf").parse(pdf_bytes, file_name="report.pdf")
    assert pdf_result.ocr_status == "not_needed"
    assert "Northshore" in pdf_result.pages[0].normalized_text


def test_image_parser_marks_ocr_unavailable_when_disabled() -> None:
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"minimal"
    result = get_parser("image/png", "scan.png").parse(png_bytes, file_name="scan.png")

    assert result.ocr_status == "unavailable"
    assert result.pages[0].has_text_layer is False
    assert result.pages[0].metadata["ocr"]["provider"] == "disabled"


def test_chunking_preserves_page_boundaries_and_overlap() -> None:
    page = ParsedPage(
        page_number=3,
        raw_text=" ".join(f"token{i}" for i in range(20)),
        normalized_text=" ".join(f"token{i}" for i in range(20)),
        has_text_layer=True,
    )

    chunks = chunk_pages([page], target_tokens=10, overlap_tokens=3)

    assert [chunk.page_start for chunk in chunks] == [3, 3, 3]
    assert chunks[0].text.split()[-3:] == chunks[1].text.split()[:3]
    assert chunks[1].text.split()[-3:] == chunks[2].text.split()[:3]


def test_process_document_persists_pages_chunks_embeddings_and_search(
    db: Session, phase3_records: dict[str, object]
) -> None:
    matter = phase3_records["matter"]
    attorney = phase3_records["attorney"]
    storage_keys = phase3_records["storage_keys"]
    assert isinstance(matter, Matter)
    assert isinstance(attorney, User)
    assert isinstance(storage_keys, list)

    storage_key = f"tests/{matter.id}/{uuid4()}-notice.txt"
    storage_keys.append(storage_key)
    storage_service.upload_fileobj(
        storage_key,
        BytesIO(b"Northshore knew about the Compressor Unit 7A defect before shipment."),
        "text/plain",
    )
    document = Document(
        matter_id=matter.id,
        uploaded_by=attorney.id,
        file_name="notice.txt",
        display_name="Notice Memo",
        mime_type="text/plain",
        file_size_bytes=64,
        storage_key=storage_key,
        sha256="phase3",
        parse_status="uploaded",
        ocr_status="not_needed",
        ingest_status="queued",
    )
    db.add(document)
    db.flush()
    db.add(IngestJob(document_id=document.id, matter_id=matter.id, status="queued"))
    db.commit()

    process_document(db, document.id)
    db.commit()

    db.refresh(document)
    chunk = db.scalar(select(DocumentChunk).where(DocumentChunk.document_id == document.id))
    assert document.ingest_status == "completed"
    assert document.parse_status == "completed"
    assert document.page_count == 1
    assert chunk is not None
    assert chunk.embedding is not None

    response = perform_search(
        db,
        matter.id,
        SearchRequest(query="Compressor Unit 7A defect", limit=5),
    )
    assert response.total == 1
    assert response.results[0].document_id == document.id
    assert "Compressor Unit 7A" in response.results[0].snippet
    assert response.results[0].metadata["lexical_rank"] == 1
    assert response.results[0].metadata["vector_rank"] == 1

    filtered = perform_search(
        db,
        matter.id,
        SearchRequest(query="Compressor Unit 7A defect", file_types=["application/pdf"], limit=5),
    )
    assert filtered.total == 0


def test_search_is_matter_scoped(db: Session, phase3_records: dict[str, object]) -> None:
    matter = phase3_records["matter"]
    other_matter = phase3_records["other_matter"]
    attorney = phase3_records["attorney"]
    assert isinstance(matter, Matter)
    assert isinstance(other_matter, Matter)
    assert isinstance(attorney, User)

    document = Document(
        matter_id=other_matter.id,
        uploaded_by=attorney.id,
        file_name="other.txt",
        display_name="Other Matter",
        mime_type="text/plain",
        file_size_bytes=20,
        storage_key="not-needed",
        sha256="other",
        parse_status="completed",
        ocr_status="not_needed",
        ingest_status="completed",
    )
    db.add(document)
    db.flush()
    db.add(
        DocumentChunk(
            document_id=document.id,
            matter_id=other_matter.id,
            page_start=1,
            page_end=1,
            chunk_index=0,
            text="Northshore defect evidence belongs to a different matter.",
            token_count=8,
            embedding=[0.0] * 384,
        )
    )
    db.commit()

    response = perform_search(db, matter.id, SearchRequest(query="Northshore defect", limit=5))

    assert response.total == 0
