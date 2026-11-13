"""Seed the V3 evidence-review demo matter from evals/datasets/conditional-payment-v1.

    python -m app.scripts.seed_v3_demo                 # four sources, memo at revision 1
    python -m app.scripts.seed_v3_demo --correction    # also publish the corrected memo (r2)
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.domain import Document, Matter, MatterMember
from app.scripts.seed_demo import ensure_seed_shell
from app.services.text_ingest import ingest_text_document

MATTER_NAME = "Halden Freight invoice dispute"
DATASET = "conditional-payment-v1"


def dataset_dir() -> Path:
    here = Path(__file__).resolve()
    candidates = [Path(os.environ.get("TRACE_EVALS_DIR", "/app/evals"))]
    candidates += [parent / "evals" for parent in here.parents]  # repo checkout
    for base in candidates:
        if (base / "datasets" / DATASET / "manifest.json").exists():
            return base / "datasets" / DATASET
    raise SystemExit(f"dataset {DATASET} not found (set TRACE_EVALS_DIR)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--correction", action="store_true", help="publish the corrected memo")
    args = parser.parse_args()
    root = dataset_dir()
    manifest = json.loads((root / "manifest.json").read_text())
    with SessionLocal() as db:
        org, users, _ = ensure_seed_shell(db)
        attorney = users["attorney@trace.local"]
        matter = db.scalar(select(Matter).where(Matter.organization_id == org.id, Matter.name == MATTER_NAME))
        if matter is None:
            matter = Matter(organization_id=org.id, name=MATTER_NAME, matter_code="TRACE-DEMO-002",
                            description="Synthetic invoice-approval dispute for the evidence review demo.",
                            created_by=attorney.id)
            db.add(matter)
            db.flush()
        for email, user in users.items():
            role = "admin" if "admin" in email else ("attorney" if "attorney" in email else "reviewer")
            if db.scalar(select(MatterMember).where(MatterMember.matter_id == matter.id,
                                                    MatterMember.user_id == user.id)) is None:
                db.add(MatterMember(matter_id=matter.id, user_id=user.id, role=role))
        for source in manifest["sources"]:
            title = source["document"].replace("_", " ") + ".txt"
            existing = db.scalar(select(Document).where(Document.matter_id == matter.id,
                                                        Document.file_name == title))
            text = (root / "sources" / source["file"]).read_text()
            if source["revision"] == 1 and existing is None:
                ingest_text_document(db, matter, attorney, title, text)
            elif source["revision"] == 2 and args.correction and existing is not None:
                from app.models.evidence import DocumentVersion

                revs = db.scalars(select(DocumentVersion.revision_no).where(
                    DocumentVersion.document_id == existing.id)).all()
                if 2 not in revs:
                    ingest_text_document(db, matter, attorney, title, text, document=existing,
                                         change_note="Controller's corrected memo of March 19")
        db.commit()
        print(f"seeded matter '{MATTER_NAME}' ({matter.id})")


if __name__ == "__main__":
    main()
