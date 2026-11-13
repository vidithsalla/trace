import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.models.domain import Document
from app.models.evidence import DocumentVersion, ExtractionVersion, SourceSpan
from app.services.evidence_versions import (
    PageText,
    create_snapshot,
    parser_profile,
    publish_extraction,
    segment_spans,
)
from app.services.parsers import normalize_text
from app.tests.conftest import current_spans, ingest_text, login

MEMO_V1 = (
    "Re: Invoice 7A.\n\nInvoice 7A is approved for payment subject to verification of delivery "
    "receipts by the\nreceiving dock. Invoice 7B is approved for payment without conditions."
)
MEMO_V2 = "Re: Invoice 7A.\n\nCorrection: invoice 7A is NOT approved. It is on hold."


# --- SRC-03 / SRC-04: offsets ----------------------------------------------------------------
def test_span_offsets_are_exact_and_trimmed():
    page = normalize_text(MEMO_V1)
    spans = segment_spans(page)
    quotes = [page[s:e] for s, e in spans]
    assert any(q.startswith("Invoice 7A is approved") and q.endswith("receiving dock.") for q in quotes)
    assert all(q == q.strip() and q for q in quotes)
    assert all(0 <= s < e <= len(page) for s, e in spans)


def test_unicode_crlf_and_combining_marks_normalize_deterministically():
    decomposed = "Café invoice 😀 approved.\r\nSecond line here is long enough to stand."
    page = normalize_text(decomposed)
    assert "Café" in page and "\r" not in page  # NFC + CRLF handled
    for start, end in segment_spans(page):
        assert len(page[start:end]) == end - start  # code-point offsets
    assert normalize_text(decomposed) == normalize_text(normalize_text(decomposed))


def test_repeated_phrase_gets_distinct_spans():
    page = "The invoice was approved by the controller. The invoice was approved by the controller."
    spans = segment_spans(page)
    assert len(spans) == 2 and spans[0] != spans[1]
    assert page[spans[0][0]:spans[0][1]] == page[spans[1][0]:spans[1][1]]


# --- ING-01: idempotent publication ---------------------------------------------------------
def test_publish_is_idempotent_for_same_version_and_profile(db, world):
    document = ingest_text(db, world.matter, world.attorney, "memo.txt", MEMO_V1)
    version = db.get(DocumentVersion, document.current_version_id)
    before = len(current_spans(db, document))
    again = publish_extraction(db, version, [PageText(1, normalize_text(MEMO_V1))],
                               profile=parser_profile("TextParser"))
    db.commit()
    extractions = db.scalars(select(ExtractionVersion).where(
        ExtractionVersion.document_version_id == version.id)).all()
    assert len(extractions) == 1 and again.id == extractions[0].id
    assert len(current_spans(db, document)) == before


# --- ING-02: crash before commit leaves nothing ----------------------------------------------
def test_uncommitted_publication_is_invisible(db, world):
    document = ingest_text(db, world.matter, world.attorney, "memo.txt", MEMO_V1)
    from app.services.evidence_versions import create_document_version

    version = create_document_version(db, document, storage_key="tests/x.txt", source_sha256="a" * 64,
                                      file_name="memo.txt", mime_type="text/plain",
                                      file_size_bytes=1, created_by=world.attorney.id)
    publish_extraction(db, version, [PageText(1, MEMO_V2)], profile=parser_profile("TextParser"))
    db.rollback()  # simulated worker crash before commit
    assert db.get(DocumentVersion, version.id) is None
    db.refresh(document)
    assert "subject to verification" in " ".join(s.text for s in current_spans(db, document))


# --- SRC-05 / REV-05 basis: new version retires old, old spans survive ----------------------
def test_new_version_retires_old_and_preserves_history(db, world):
    document = ingest_text(db, world.matter, world.attorney, "memo.txt", MEMO_V1)
    old_version_id = document.current_version_id
    old_span_ids = {s.id for s in current_spans(db, document)}
    ingest_text(db, world.matter, world.attorney, "memo.txt", MEMO_V2, document=document)

    db.refresh(document)
    assert document.current_version_id != old_version_id
    assert db.get(DocumentVersion, old_version_id).state == "RETIRED"
    new = db.get(DocumentVersion, document.current_version_id)
    assert new.state == "READY" and new.revision_no == 2
    surviving = db.scalars(select(SourceSpan).where(SourceSpan.id.in_(old_span_ids))).all()
    assert {s.id for s in surviving} == old_span_ids  # historical spans still resolvable
    assert old_span_ids.isdisjoint({s.id for s in current_spans(db, document)})


# --- Immutability triggers --------------------------------------------------------------------
def test_published_spans_and_version_identity_are_immutable(db, world):
    document = ingest_text(db, world.matter, world.attorney, "memo.txt", MEMO_V1)
    span = current_spans(db, document)[0]
    with pytest.raises(DBAPIError, match="immutable"):
        db.execute(text("UPDATE source_spans SET text = 'tampered' WHERE id = :id"), {"id": span.id})
    db.rollback()
    with pytest.raises(DBAPIError, match="immutable"):
        db.execute(text("UPDATE document_versions SET source_sha256 = :h WHERE id = :id"),
                   {"h": "b" * 64, "id": document.current_version_id})
    db.rollback()
    with pytest.raises(DBAPIError, match="immutable"):
        db.execute(text("UPDATE extraction_versions SET span_count = 0 WHERE id = :id"),
                   {"id": span.extraction_version_id})
    db.rollback()


# --- SRC-02 at the database layer: cross-matter references are impossible -------------------
def test_cross_matter_span_reference_rejected_by_foreign_key(db, world):
    document = ingest_text(db, world.matter, world.attorney, "memo.txt", MEMO_V1)
    span = current_spans(db, document)[0]
    with pytest.raises(IntegrityError):
        db.execute(text(
            "INSERT INTO source_spans (id, matter_id, extraction_version_id, document_id, page_no, "
            "span_index, normalized_start, normalized_end, text, quote_sha256) VALUES "
            "(gen_random_uuid(), :other, :ev, :doc, 1, 999, 0, 4, 'evil', 'x')"),
            {"other": world.other_matter.id, "ev": span.extraction_version_id, "doc": document.id})
    db.rollback()


# --- Snapshots ---------------------------------------------------------------------------------
def test_snapshots_are_content_addressed_and_track_versions(db, world):
    document = ingest_text(db, world.matter, world.attorney, "memo.txt", MEMO_V1)
    ingest_text(db, world.matter, world.attorney, "terms.txt", "Payment terms require written notice.")
    first = create_snapshot(db, world.matter.id, world.attorney.id)
    same = create_snapshot(db, world.matter.id, world.attorney.id)
    assert first.id == same.id and first.member_count == 2
    ingest_text(db, world.matter, world.attorney, "memo.txt", MEMO_V2, document=document)
    second = create_snapshot(db, world.matter.id, world.attorney.id)
    db.commit()
    assert second.id != first.id and second.member_count == 2
    other = create_snapshot(db, world.other_matter.id, world.outsider.id)
    assert other.member_count == 0


# --- Upload API for new versions ---------------------------------------------------------------
def _upload(client, matter_id, document_id, content, expected):
    return client.post(
        f"/matters/{matter_id}/documents/{document_id}/versions",
        files={"file": ("memo.txt", content, "text/plain")},
        data={"expected_revision": str(expected), "change_note": "corrected"},
    )


def test_version_upload_api_guards(db, world, client, monkeypatch):
    monkeypatch.setattr("app.api.routes.documents.enqueue_ingest_job", lambda _id: None)
    document = ingest_text(db, world.matter, world.attorney, "memo.txt", MEMO_V1)

    login(client, world.attorney)
    assert _upload(client, world.matter.id, document.id, MEMO_V2.encode(), 5).status_code == 409
    identical = _upload(client, world.matter.id, document.id, MEMO_V1.encode(), 1)
    assert identical.status_code == 409 and identical.json()["detail"]["code"] == "IDENTICAL_CONTENT"
    ok = _upload(client, world.matter.id, document.id, MEMO_V2.encode(), 1)
    assert ok.status_code == 202 and ok.json()["revision_no"] == 2 and ok.json()["state"] == "STAGING"
    # Staged version is not current until the worker publishes it.
    db.expire_all()
    assert db.get(Document, document.id).current_version_id != ok.json()["version_id"]

    client.cookies.clear()
    login(client, world.viewer)
    assert _upload(client, world.matter.id, document.id, b"x", 2).status_code == 403
    client.cookies.clear()
    login(client, world.outsider)
    assert _upload(client, world.matter.id, document.id, b"x", 2).status_code == 403
    assert _upload(client, world.other_matter.id, document.id, b"x", 2).status_code == 404


def test_worker_processes_staged_version(db, world, client, monkeypatch):
    from app.services.ingestion import process_document

    monkeypatch.setattr("app.api.routes.documents.enqueue_ingest_job", lambda _id: None)
    document = ingest_text(db, world.matter, world.attorney, "memo.txt", MEMO_V1)
    login(client, world.attorney)
    assert _upload(client, world.matter.id, document.id, MEMO_V2.encode(), 1).status_code == 202
    db.expire_all()
    process_document(db, document.id)
    db.commit()
    process_document(db, document.id)  # duplicate message: no new extraction
    db.commit()
    db.expire_all()
    current = db.get(DocumentVersion, db.get(Document, document.id).current_version_id)
    assert current.revision_no == 2 and current.state == "READY"
    assert db.scalar(select(text("count(*)")).select_from(ExtractionVersion).where(
        ExtractionVersion.document_version_id == current.id)) == 1
    assert "on hold" in " ".join(s.text for s in current_spans(db, db.get(Document, document.id)))
