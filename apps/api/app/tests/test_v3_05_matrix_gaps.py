"""PRD test-matrix cases not covered elsewhere: ING-03, SRC-06, SEC-01 (packets), EVAL-01, EVAL-02."""

import copy
import json
import uuid

import pytest
from sqlalchemy import select

from app.models.evidence import DocumentVersion, ExtractionVersion
from app.scripts.seed_v3_demo import dataset_dir
from app.services import retrieval_v3
from app.services.eval_validation import validate_dataset, validate_profiles
from app.services.evidence_versions import (
    PageText,
    create_document_version,
    create_snapshot,
    parser_profile,
    publish_extraction,
)
from app.services.parsers import get_parser
from app.tests.conftest import current_spans, ingest_text, login
from app.tests.test_v3_02_review_pipeline import (  # noqa: F401
    MEMO_V1,
    MEMO_V2,
    H,
    _accepted_claim,
    corpus,
    engine,
)


def _span_ids(db, matter_id, snapshot_id, query):
    return {c.source_span_id for c in retrieval_v3.lexical(
        db, matter_id=matter_id, snapshot_id=snapshot_id, query=query, k=50)}


# --- ING-03: a run stays bound to the snapshot it pinned ---------------------------------------
def test_publication_during_a_run_does_not_change_its_snapshot(db, world):
    memo = ingest_text(db, world.matter, world.attorney, "memo.txt", MEMO_V1)
    pinned = create_snapshot(db, world.matter.id, world.attorney.id)
    db.commit()
    before = _span_ids(db, world.matter.id, pinned.id, "invoice 7A approved hold")
    old_memo_spans = {s.id for s in current_spans(db, memo)}

    # While the "run" is in progress: a correction and a brand-new document are published.
    ingest_text(db, world.matter, world.attorney, "memo.txt", MEMO_V2, document=memo)
    ingest_text(db, world.matter, world.attorney, "dock.txt", "Please hold payment on invoice 7A.")

    assert _span_ids(db, world.matter.id, pinned.id, "invoice 7A approved hold") == before
    assert before & old_memo_spans  # still answered from revision 1
    fresh = create_snapshot(db, world.matter.id, world.attorney.id)
    after = _span_ids(db, world.matter.id, fresh.id, "invoice 7A approved hold")
    assert fresh.id != pinned.id and after.isdisjoint(old_memo_spans) and len(after) > len(before) - 1


# --- SRC-06: no text layer is surfaced, never read as "the document says nothing" -------------
def test_scanned_pdf_without_text_is_flagged_not_silently_empty(db, world, client, engine):  # noqa: F811
    import fitz

    pdf = fitz.open()
    pdf.new_page()  # an image-only scan looks like this to a text parser
    content = pdf.tobytes()
    parsed = get_parser("application/pdf", "scan.pdf").parse(content, file_name="scan.pdf")
    from app.models.domain import Document

    document = Document(matter_id=world.matter.id, uploaded_by=world.attorney.id, file_name="scan.pdf",
                        mime_type="application/pdf", file_size_bytes=len(content),
                        storage_key=f"tests/{uuid.uuid4().hex}.pdf", sha256="0" * 64)
    db.add(document)
    db.flush()
    version = create_document_version(db, document, storage_key=document.storage_key,
                                      source_sha256="a" * 64, file_name="scan.pdf",
                                      mime_type="application/pdf", file_size_bytes=len(content),
                                      created_by=world.attorney.id)
    extraction = publish_extraction(db, version, [PageText(p.page_number, p.normalized_text) for p in parsed.pages],
                                    profile=parser_profile("PdfParser"))
    db.commit()
    assert extraction.span_count == 0 and "NO_TEXT_EXTRACTED" in extraction.warnings
    assert db.get(DocumentVersion, version.id).state == "READY"

    login(client, world.reviewer)
    sources = client.get(f"/matters/{world.matter.id}/sources").json()
    scan = next(s for s in sources if s["title"] == "scan.pdf")
    assert "NO_TEXT_EXTRACTED" in scan["versions"][0]["warnings"]
    run = client.post(f"/matters/{world.matter.id}/analyses", json={"question": "What does the scan say about invoice 7A?"},
                      headers={**H, "Idempotency-Key": uuid.uuid4().hex}).json()
    assert run["status"] == "ABSTAINED" and run["claims"] == []
    assert run["coverage"]["reason"] == "NO_CANDIDATES"


# --- SEC-01 (packets): another matter's packet is unreachable ---------------------------------
def test_other_matter_cannot_list_or_download_packets(client, world, corpus, engine):  # noqa: F811
    claim = _accepted_claim(client, world, engine)
    packet = client.post(f"/matters/{world.matter.id}/packets", headers=H,
                         json={"claim_ids": [claim["id"]]}).json()
    client.cookies.clear()
    login(client, world.outsider)
    assert client.get(f"/matters/{world.matter.id}/packets").status_code == 403
    assert client.get(f"/matters/{world.matter.id}/packets/{packet['id']}/files/manifest.json").status_code == 403
    assert client.get(f"/matters/{world.other_matter.id}/packets/{packet['id']}/files/manifest.json").status_code == 404
    leak = client.post(f"/matters/{world.other_matter.id}/packets", headers=H, json={"claim_ids": [claim["id"]]})
    assert leak.status_code == 422 and leak.json()["detail"]["code"] == "CLAIM_NOT_IN_MATTER"


# --- EVAL-01 ---------------------------------------------------------------------------------
@pytest.fixture()
def dataset():
    root = dataset_dir()
    return json.loads((root / "manifest.json").read_text()), root / "sources"


def test_published_dataset_validates(dataset):
    manifest, sources = dataset
    assert validate_dataset(manifest, sources) == []


def test_split_leak_and_bad_gold_are_rejected(dataset):
    manifest, sources = dataset
    leaky = copy.deepcopy(manifest)
    leaky["splits"] = {"tune": ["CP-01"], "holdout": ["CP-04"]}  # both cite the approval memo
    assert any("leak: document approval_memo" in p for p in validate_dataset(leaky, sources))

    paraphrase = copy.deepcopy(manifest)
    paraphrase["splits"] = {"tune": ["RP-02"], "holdout": ["CP-04"]}  # same claim, different id
    assert any("leak: claim text" in p for p in validate_dataset(paraphrase, sources))

    broken = copy.deepcopy(manifest)
    broken["relation_pairs"][0]["quote"] = "a sentence that is not in the memo"
    assert any("gold quote not found" in p for p in validate_dataset(broken, sources))


# --- EVAL-02 ---------------------------------------------------------------------------------
def test_hash_vectors_cannot_be_reported_as_semantic(db):
    assert validate_profiles(db, retrieval_v3.PROFILES) == []
    mislabeled = {**retrieval_v3.PROFILES, "semantic_cheap": {"lexical": True, "semantic": "hash-v1"}}
    assert validate_profiles(db, mislabeled) == [
        "semantic_cheap: named semantic but uses non-semantic embeddings (hash-v1)"]


def test_extraction_versions_are_unique_per_profile(db, world):
    memo = ingest_text(db, world.matter, world.attorney, "memo.txt", MEMO_V1)
    count = db.scalars(select(ExtractionVersion).where(
        ExtractionVersion.document_version_id == memo.current_version_id)).all()
    assert len(count) == 1
