"""Evidence packet export (PRD section 9.5).

Built only from immutable stored records (claim revisions, evidence rows, spans, review events),
never by re-running a model. Files are written once; later source changes cannot alter them.
The manifest digest is an integrity/reproducibility aid, not a digital signature.
"""

from __future__ import annotations

import hashlib
import json
from io import BytesIO
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.claims import Claim, ClaimEvidence, ClaimRevision, PacketExport, ReviewEvent
from app.models.domain import Document, Matter, User, utcnow
from app.models.evidence import DocumentVersion, ExtractionVersion, SourceSpan
from app.services.storage import storage_service

SCHEMA_VERSION = "trace-packet-v1"
POLICIES = {"accepted_current_only", "include_all_labeled"}
MEDIA = {"manifest.json": "application/json", "findings.json": "application/json",
         "packet.md": "text/markdown; charset=utf-8", "checksums.sha256": "text/plain; charset=utf-8"}
LIMITATIONS = [
    "Accepted means an authorized reviewer accepted the finding for this evidence packet. "
    "It is not a legal conclusion.",
    "Support labels are model candidates. Source verification only shows that a quoted span "
    "exists unchanged in the stated document version.",
    "Counterevidence search is not exhaustive; absence of an opposing passage is not proof that "
    "none exists.",
    "The manifest SHA-256 is an integrity aid, not a digital signature.",
]


def _canonical(obj) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _exclusion_reason(claim: Claim, revision: ClaimRevision) -> str | None:
    if claim.review_state != "ACCEPTED":
        return f"review_state={claim.review_state}"
    if claim.basis_state != "CURRENT":
        return "basis_state=STALE_SOURCE"
    if claim.coverage_state != "CURRENT":
        return "coverage_state=POTENTIAL_NEW_EVIDENCE"
    if revision.source_gate_state != "VERIFIED":
        return f"source_gate_state={revision.source_gate_state}"
    return None


def build_packet(db: Session, *, matter_id: UUID, user: User, claim_ids: list[UUID],
                 inclusion_policy: str) -> PacketExport:
    if inclusion_policy not in POLICIES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"code": "INVALID_POLICY"})
    unique_ids = list(dict.fromkeys(claim_ids))
    claims = db.scalars(select(Claim).where(Claim.id.in_(unique_ids), Claim.matter_id == matter_id)).all()
    if len(claims) != len(unique_ids):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"code": "CLAIM_NOT_IN_MATTER"})
    matter = db.get(Matter, matter_id)

    included, excluded, sources = [], [], {}
    for claim in sorted(claims, key=lambda c: str(c.id)):
        revision = db.get(ClaimRevision, (claim.id, claim.current_revision))
        reason = _exclusion_reason(claim, revision)
        if reason and inclusion_policy == "accepted_current_only":
            excluded.append({"claim_id": str(claim.id), "revision": claim.current_revision, "reason": reason})
            continue
        included.append(_claim_record(db, claim, revision, reason, sources))

    if not included:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            {"code": "NOTHING_TO_EXPORT", "excluded": excluded})

    packet_id = uuid4()
    generated_at = utcnow().isoformat()
    manifest = {
        "schema_version": SCHEMA_VERSION, "packet_id": str(packet_id), "matter_id": str(matter_id),
        "matter_name": matter.name if matter else None, "generated_at": generated_at,
        "generated_by_user_id": str(user.id), "code_commit": settings.code_commit,
        "inclusion_policy": inclusion_policy,
        "claims": [{"claim_id": c["claim_id"], "revision": c["revision"],
                    "evidence_set_sha256": c["evidence_set_sha256"], "review_state": c["review_state"],
                    "label": c["label"], "review_event_ids": [e["id"] for e in c["review_events"]]}
                   for c in included],
        "excluded": excluded,
        "sources": sorted(sources.values(), key=lambda s: (s["document_id"], s["revision_no"])),
        "limitations": LIMITATIONS,
    }
    findings = {"schema_version": SCHEMA_VERSION, "packet_id": str(packet_id), "claims": included}
    files = {"manifest.json": _canonical(manifest), "findings.json": _canonical(findings),
             "packet.md": _markdown(manifest, included).encode("utf-8")}
    checksums = "".join(f"{hashlib.sha256(body).hexdigest()}  {name}\n"
                        for name, body in sorted(files.items()))
    files["checksums.sha256"] = checksums.encode("utf-8")

    prefix = f"packets/{matter_id}/{packet_id}"
    for name, body in files.items():
        storage_service.upload_fileobj(f"{prefix}/{name}", BytesIO(body), MEDIA[name])
    packet = PacketExport(
        id=packet_id, matter_id=matter_id, requested_by=user.id, inclusion_policy=inclusion_policy,
        claim_count=len(included), manifest_sha256=hashlib.sha256(files["manifest.json"]).hexdigest(),
        storage_prefix=prefix,
        files={name: {"sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}
               for name, body in files.items()},
    )
    db.add(packet)
    db.flush()
    return packet


def _claim_record(db: Session, claim: Claim, revision: ClaimRevision, reason: str | None,
                  sources: dict) -> dict:
    evidence = []
    for row in db.scalars(select(ClaimEvidence).where(
            ClaimEvidence.claim_id == claim.id, ClaimEvidence.claim_revision == revision.revision)
            .order_by(ClaimEvidence.evidence_role, ClaimEvidence.evidence_ref)):
        span = db.get(SourceSpan, row.source_span_id)
        extraction = db.get(ExtractionVersion, span.extraction_version_id)
        version = db.get(DocumentVersion, extraction.document_version_id)
        document = db.get(Document, span.document_id)
        sources[str(version.id)] = {
            "document_id": str(document.id), "title": document.display_name or document.file_name,
            "document_version_id": str(version.id), "revision_no": version.revision_no,
            "source_sha256": version.source_sha256, "provenance": version.provenance,
            "extraction_version_id": str(extraction.id),
            "normalized_text_sha256": extraction.normalized_text_sha256,
        }
        evidence.append({
            "role": row.evidence_role, "relation_candidate": row.relation_candidate,
            "reason_code": row.reason_code, "cited_by_model": row.cited_by_model,
            "quote_integrity": row.quote_integrity, "source_span_id": str(span.id),
            "document_version_id": str(version.id), "revision_no": version.revision_no,
            "page": span.page_no, "start": span.normalized_start, "end": span.normalized_end,
            "quote": span.text, "quote_sha256": span.quote_sha256, "document_title": sources[str(version.id)]["title"],
        })
    events = db.scalars(select(ReviewEvent).where(ReviewEvent.claim_id == claim.id)
                        .order_by(ReviewEvent.event_seq)).all()
    return {
        "claim_id": str(claim.id), "revision": revision.revision, "text": revision.text,
        "label": reason or "accepted_current", "review_state": claim.review_state,
        "basis_state": claim.basis_state, "coverage_state": claim.coverage_state,
        "source_gate_state": revision.source_gate_state, "relation_candidate": revision.relation_candidate,
        "evidence_set_sha256": revision.evidence_set_sha256,
        "corpus_snapshot_id": str(revision.corpus_snapshot_id), "coverage": revision.coverage,
        "evidence": evidence,
        "review_events": [{"id": str(e.id), "seq": e.event_seq, "action": e.action,
                           "revision": e.claim_revision, "reason_code": e.reason_code, "note": e.note,
                           "actor_user_id": str(e.actor_user_id),
                           "evidence_set_sha256": e.evidence_set_sha256,
                           "created_at": e.created_at.isoformat()} for e in events],
    }


def _md_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("<", "&lt;").replace(">", "&gt;").replace("`", "\\`")


def _markdown(manifest: dict, claims: list[dict]) -> str:
    lines = [f"# Evidence packet: {_md_escape(manifest['matter_name'] or manifest['matter_id'])}", "",
             f"Generated {manifest['generated_at']} · policy `{manifest['inclusion_policy']}` · "
             f"{len(claims)} finding(s)", ""]
    for claim in claims:
        lines += [f"## {_md_escape(claim['text'])}", "",
                  f"- Status: **{claim['label']}** (review: {claim['review_state']}, "
                  f"sources: {claim['source_gate_state']}, support candidate: {claim['relation_candidate']})",
                  f"- Claim revision {claim['revision']} · evidence digest `{claim['evidence_set_sha256'][:16]}`", ""]
        for ev in claim["evidence"]:
            lines.append(f"> {_md_escape(ev['quote'])}")
            lines.append(f">\n> — {_md_escape(ev['document_title'])}, revision {ev['revision_no']}, "
                         f"page {ev['page']} · {ev['role']} ({ev['relation_candidate']})")
            lines.append("")
        for event in claim["review_events"]:
            note = f": {_md_escape(event['note'])}" if event["note"] else ""
            lines.append(f"- {event['created_at']} {event['action']} (revision {event['revision']}){note}")
        lines.append("")
    if manifest["excluded"]:
        lines += ["## Not included", ""]
        lines += [f"- `{e['claim_id']}` revision {e['revision']}: {e['reason']}" for e in manifest["excluded"]]
        lines.append("")
    lines += ["## Limitations", ""] + [f"- {item}" for item in manifest["limitations"]]
    return "\n".join(lines) + "\n"


def packet_view(packet: PacketExport) -> dict:
    return {"id": str(packet.id), "inclusion_policy": packet.inclusion_policy,
            "claim_count": packet.claim_count, "manifest_sha256": packet.manifest_sha256,
            "files": packet.files, "created_at": packet.created_at.isoformat() if packet.created_at else None}


def read_file(packet: PacketExport, name: str) -> tuple[bytes, str]:
    body = storage_service.get_object_bytes(f"{packet.storage_prefix}/{name}")
    if hashlib.sha256(body).hexdigest() != packet.files[name]["sha256"]:
        raise HTTPException(status.HTTP_409_CONFLICT, {"code": "PACKET_FILE_INTEGRITY_FAILED"})
    return body, MEDIA[name]
