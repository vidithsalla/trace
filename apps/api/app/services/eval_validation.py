"""Guards that run before an evaluation is scored (PRD test matrix EVAL-01 / EVAL-02).

- ``validate_dataset``: every gold quote exists verbatim in its stated source revision, ids are
  unique, and when the manifest declares splits, no document, source file or (near-)identical
  claim text appears in more than one split.
- ``validate_profiles``: a retrieval profile whose name says "semantic" must use an embedding
  profile registered as semantic. The pre-V3 hash vectors can never be reported as semantic.
"""

from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.evidence import EmbeddingProfile


class DatasetValidationError(ValueError):
    pass


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def validate_dataset(manifest: dict, sources_dir: Path) -> list[str]:
    problems: list[str] = []
    texts = {}
    for source in manifest.get("sources", []):
        path = sources_dir / source["file"]
        if not path.exists():
            problems.append(f"missing source file {source['file']}")
            continue
        texts[(source["document"], source["revision"])] = path.read_text()

    def check_quote(owner: str, gold: dict) -> None:
        body = texts.get((gold["document"], gold["revision"]))
        if body is None:
            problems.append(f"{owner}: unknown source {gold['document']} r{gold['revision']}")
        elif gold["quote"] not in body:
            problems.append(f"{owner}: gold quote not found in {gold['document']} r{gold['revision']}")

    ids: list[str] = []
    for case in manifest.get("cases", []):
        ids.append(case["case_id"])
        for gold in case.get("gold_supporting", []) + case.get("gold_opposing", []):
            check_quote(case["case_id"], gold)
    for pair in manifest.get("relation_pairs", []):
        ids.append(pair["pair_id"])
        check_quote(pair["pair_id"], pair)
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        problems.append(f"duplicate ids: {', '.join(duplicates)}")

    splits = manifest.get("splits") or {}
    owners: dict[str, dict[str, str]] = {"document": {}, "claim": {}}
    by_id = {c["case_id"]: c for c in manifest.get("cases", [])}
    by_id.update({p["pair_id"]: p for p in manifest.get("relation_pairs", [])})
    for split, members in splits.items():
        for item_id in members:
            item = by_id.get(item_id)
            if item is None:
                problems.append(f"split {split}: unknown id {item_id}")
                continue
            documents = {g["document"] for g in item.get("gold_supporting", []) + item.get("gold_opposing", [])}
            if "document" in item:
                documents.add(item["document"])
            for document in documents:
                other = owners["document"].setdefault(document, split)
                if other != split:
                    problems.append(f"leak: document {document} in splits {other} and {split}")
            claim = _norm(item.get("claim", ""))
            if claim:
                other = owners["claim"].setdefault(claim, split)
                if other != split:
                    problems.append(f"leak: claim text '{item['claim'][:40]}' in splits {other} and {split}")
    return problems


def assert_valid_dataset(manifest: dict, sources_dir: Path) -> None:
    problems = validate_dataset(manifest, sources_dir)
    if problems:
        raise DatasetValidationError("; ".join(problems))


def validate_profiles(db: Session, profiles: dict[str, dict]) -> list[str]:
    semantic_ids = set(db.scalars(select(EmbeddingProfile.id).where(EmbeddingProfile.is_semantic)))
    known = set(db.scalars(select(EmbeddingProfile.id)))
    problems = []
    for name, config in profiles.items():
        embedding = config.get("semantic")
        if embedding and embedding not in known:
            problems.append(f"{name}: unknown embedding profile {embedding}")
        if "semantic" in name and embedding not in semantic_ids:
            problems.append(f"{name}: named semantic but uses non-semantic embeddings ({embedding})")
    return problems
