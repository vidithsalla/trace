from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import Entity, Matter, Memo, User
from app.schemas.workflow import ChronologyRequest, ContradictionRequest, GroundedQARequest, MemoCreateRequest
from app.services.exports import create_completed_export
from app.services.workflows import (
    run_chronology_builder,
    run_contradiction_finder,
    run_grounded_qa,
    run_issue_memo,
)


def default_truth_path() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "seed_truth" / "acme_truth.json"
        if candidate.exists():
            return candidate
    return Path("/app/seed_truth/acme_truth.json")


DEFAULT_TRUTH_PATH = default_truth_path()
REGRESSION_TRUTH_FILES = [
    "employment_dispute_truth.json",
    "internal_investigation_truth.json",
    "invoice_payment_dispute_truth.json",
]


class EvalRunner:
    def __init__(self, db: Session, truth_path: Path = DEFAULT_TRUTH_PATH) -> None:
        self.db = db
        self.truth = json.loads(truth_path.read_text())

    def run(self) -> dict[str, Any]:
        matter = self._matter()
        user = self._user(matter)
        checks = [
            self._entity_check(matter),
            self._question_check(matter, user),
            self._contradiction_check(matter, user),
            self._chronology_and_export_check(matter, user),
            self._memo_and_export_check(matter, user),
            self._branding_check(),
        ]
        passed = all(check["passed"] for check in checks)
        return {
            "suite": "acme_mvp",
            "matter": matter.name,
            "passed": passed,
            "checks": checks,
        }

    def _matter(self) -> Matter:
        matter = self.db.scalar(select(Matter).where(Matter.name == self.truth["matter_name"]))
        if matter is None:
            raise ValueError(f"Seed matter not found: {self.truth['matter_name']}")
        return matter

    def _user(self, matter: Matter) -> User:
        user = self.db.scalar(select(User).where(User.email == "attorney@trace.local"))
        if user is not None and user.organization_id == matter.organization_id:
            return user
        user = self.db.get(User, matter.created_by)
        if user is None:
            raise ValueError("Seed attorney not found")
        return user

    def _entity_check(self, matter: Matter) -> dict[str, Any]:
        expected = {item["canonical_name"] for item in self.truth.get("entities", [])}
        found = {
            entity.canonical_name
            for entity in self.db.scalars(select(Entity).where(Entity.matter_id == matter.id))
        }
        missing = sorted(expected - found)
        return {
            "name": "canonical_entities",
            "passed": not missing,
            "expected_count": len(expected),
            "found_count": len(found),
            "missing": missing,
        }

    def _question_check(self, matter: Matter, user: User) -> dict[str, Any]:
        results = []
        for item in self.truth.get("golden_questions", []):
            response = run_grounded_qa(
                self.db,
                matter.id,
                user.id,
                GroundedQARequest(question=item["question"], limit=8),
            )
            haystack = " ".join(
                [
                    response.answer,
                    response.short_answer,
                    *[citation.quote for citation in response.citations],
                ]
            ).lower()
            missing_concepts = [
                concept for concept in item.get("must_include", []) if concept.lower() not in haystack
            ]
            results.append(
                {
                    "question": item["question"],
                    "citation_count": len(response.citations),
                    "missing_concepts": missing_concepts,
                    "passed": bool(response.citations) and len(missing_concepts) <= 1,
                }
            )
        return {
            "name": "golden_questions",
            "passed": all(result["passed"] for result in results),
            "results": results,
        }

    def _contradiction_check(self, matter: Matter, user: User) -> dict[str, Any]:
        results = []
        for item in self.truth.get("known_contradictions", []):
            response = run_contradiction_finder(
                self.db,
                matter.id,
                user.id,
                ContradictionRequest(topic=item["topic"], limit=16),
            )
            results.append(
                {
                    "topic": item["topic"],
                    "contradiction_count": len(response.contradictions),
                    "ambiguity_count": len(response.ambiguities),
                    "passed": bool(response.contradictions),
                }
            )
        return {
            "name": "known_contradictions",
            "passed": all(result["passed"] for result in results),
            "results": results,
        }

    def _chronology_and_export_check(self, matter: Matter, user: User) -> dict[str, Any]:
        response = run_chronology_builder(
            self.db,
            matter.id,
            user.id,
            ChronologyRequest(topic="notice payment defect Project Falcon", limit=20),
        )
        csv_export, _ = create_completed_export(
            self.db,
            matter_id=matter.id,
            requested_by=user.id,
            organization_id=user.organization_id,
            export_type="chronology_csv",
            source_object_type="matter",
            source_object_id=matter.id,
            metadata={"eval": "acme_mvp"},
        )
        docx_export, _ = create_completed_export(
            self.db,
            matter_id=matter.id,
            requested_by=user.id,
            organization_id=user.organization_id,
            export_type="chronology_docx",
            source_object_type="matter",
            source_object_id=matter.id,
            metadata={"eval": "acme_mvp"},
        )
        return {
            "name": "chronology_exports",
            "passed": len(response.events) >= 10 and csv_export.status == "completed" and docx_export.status == "completed",
            "event_count": len(response.events),
            "exports": [str(csv_export.id), str(docx_export.id)],
        }

    def _memo_and_export_check(self, matter: Matter, user: User) -> dict[str, Any]:
        memo = run_issue_memo(
            self.db,
            matter.id,
            user.id,
            MemoCreateRequest(issue="Whether Acme gave timely notice of the delivery problem", limit=12),
        )
        self.db.flush()
        markdown_export, _ = create_completed_export(
            self.db,
            matter_id=matter.id,
            requested_by=user.id,
            organization_id=user.organization_id,
            export_type="memo_markdown",
            source_object_type="memo",
            source_object_id=memo.id,
            metadata={"eval": "acme_mvp"},
        )
        docx_export, _ = create_completed_export(
            self.db,
            matter_id=matter.id,
            requested_by=user.id,
            organization_id=user.organization_id,
            export_type="memo_docx",
            source_object_type="memo",
            source_object_id=memo.id,
            metadata={"eval": "acme_mvp"},
        )
        persisted_memo = self.db.get(Memo, memo.id)
        return {
            "name": "memo_exports",
            "passed": persisted_memo is not None
            and markdown_export.status == "completed"
            and docx_export.status == "completed",
            "memo_id": str(memo.id),
            "exports": [str(markdown_export.id), str(docx_export.id)],
        }

    def _branding_check(self) -> dict[str, Any]:
        return {
            "name": "branding",
            "passed": self.truth.get("product_name") == "Trace"
            and self.truth.get("product_full_name") == "Trace - Sovereign Discovery Copilot",
        }


class StaticTruthPackRunner:
    def __init__(self, truth_path: Path) -> None:
        self.truth_path = truth_path
        self.truth = json.loads(truth_path.read_text())
        self.documents = self.truth.get("documents", [])

    def run(self) -> dict[str, Any]:
        checks = [
            self._schema_check(),
            self._entity_check(),
            self._question_check(),
            self._contradiction_check(),
            self._chronology_check(),
            self._memo_section_check(),
            self._ambiguity_check(),
            self._branding_check(),
        ]
        return {
            "suite": self.truth.get("corpus_id", self.truth_path.stem),
            "matter": self.truth.get("matter_name"),
            "corpus_type": self.truth.get("corpus_type", "static_regression"),
            "passed": all(check["passed"] for check in checks),
            "checks": checks,
        }

    def _schema_check(self) -> dict[str, Any]:
        required = [
            "product_name",
            "product_full_name",
            "corpus_id",
            "corpus_type",
            "matter_name",
            "documents",
            "entities",
            "key_events",
            "known_contradictions",
            "golden_questions",
        ]
        missing = [key for key in required if key not in self.truth]
        return {"name": "truth_pack_schema", "passed": not missing, "missing": missing}

    def _entity_check(self) -> dict[str, Any]:
        corpus_text = self._corpus_text()
        missing = [
            entity["canonical_name"]
            for entity in self.truth.get("entities", [])
            if entity["canonical_name"].lower() not in corpus_text
            and not any(alias.lower() in corpus_text for alias in entity.get("aliases", []))
        ]
        return {
            "name": "entity_mentions",
            "passed": not missing,
            "expected_count": len(self.truth.get("entities", [])),
            "missing": missing,
        }

    def _question_check(self) -> dict[str, Any]:
        results = []
        for question in self.truth.get("golden_questions", []):
            docs = self._documents_by_name(question.get("expected_document_names", []))
            evidence_text = " ".join(doc.get("text", "") for doc in docs).lower()
            missing_concepts = [
                concept
                for concept in question.get("must_include", [])
                if concept.lower() not in evidence_text
            ]
            results.append(
                {
                    "question": question["question"],
                    "expected_document_count": len(question.get("expected_document_names", [])),
                    "citation_count": len(docs),
                    "missing_concepts": missing_concepts,
                    "passed": bool(docs) and not missing_concepts,
                }
            )
        return {
            "name": "golden_questions",
            "passed": all(result["passed"] for result in results),
            "results": results,
        }

    def _contradiction_check(self) -> dict[str, Any]:
        corpus_text = self._corpus_text()
        results = []
        for contradiction in self.truth.get("known_contradictions", []):
            claim_a_hits = _claim_hits(contradiction.get("claim_a", ""), corpus_text)
            claim_b_hits = _claim_hits(contradiction.get("claim_b", ""), corpus_text)
            results.append(
                {
                    "topic": contradiction.get("topic"),
                    "claim_a_hits": claim_a_hits,
                    "claim_b_hits": claim_b_hits,
                    "passed": claim_a_hits >= 2 and claim_b_hits >= 2,
                }
            )
        return {
            "name": "known_contradictions",
            "passed": all(result["passed"] for result in results),
            "results": results,
        }

    def _chronology_check(self) -> dict[str, Any]:
        dated_events = [
            event
            for event in self.truth.get("key_events", [])
            if str(event.get("date", "")).count("-") == 2 and event.get("title")
        ]
        return {
            "name": "chronology_coverage",
            "passed": len(dated_events) >= 3,
            "event_count": len(dated_events),
        }

    def _memo_section_check(self) -> dict[str, Any]:
        required = {
            "issue",
            "answer_in_brief",
            "supporting_facts",
            "contrary_facts",
            "gaps",
            "next_documents_to_review",
        }
        results = []
        for topic in self.truth.get("memo_topics", []):
            sections = set(topic.get("required_sections", []))
            missing = sorted(required - sections)
            results.append(
                {
                    "issue": topic.get("issue"),
                    "missing_sections": missing,
                    "passed": not missing,
                }
            )
        return {
            "name": "memo_section_coverage",
            "passed": bool(results) and all(result["passed"] for result in results),
            "results": results,
        }

    def _ambiguity_check(self) -> dict[str, Any]:
        ambiguities = self.truth.get("ambiguities", [])
        return {
            "name": "ambiguity_handling",
            "passed": bool(ambiguities),
            "ambiguity_count": len(ambiguities),
        }

    def _branding_check(self) -> dict[str, Any]:
        return {
            "name": "branding",
            "passed": self.truth.get("product_name") == "Trace"
            and self.truth.get("product_full_name") == "Trace - Sovereign Discovery Copilot",
        }

    def _documents_by_name(self, names: list[str]) -> list[dict]:
        wanted = set(names)
        return [document for document in self.documents if document.get("name") in wanted]

    def _corpus_text(self) -> str:
        return " ".join(document.get("text", "") for document in self.documents).lower()


class EvalSuiteRunner:
    def __init__(self, db: Session, truth_dir: Path | None = None) -> None:
        self.db = db
        self.truth_dir = truth_dir or DEFAULT_TRUTH_PATH.parent

    def run_acme(self) -> dict[str, Any]:
        return EvalRunner(self.db, self.truth_dir / "acme_truth.json").run()

    def run_regression(self, corpus_id: str) -> dict[str, Any]:
        truth_path = self._regression_path(corpus_id)
        return StaticTruthPackRunner(truth_path).run()

    def run_all(self, *, include_acme: bool = True) -> dict[str, Any]:
        reports = []
        if include_acme:
            reports.append(self.run_acme())
        for truth_path in regression_truth_paths(self.truth_dir):
            reports.append(StaticTruthPackRunner(truth_path).run())
        return {
            "suite": "all",
            "passed": all(report["passed"] for report in reports),
            "reports": reports,
            "summary": {
                "total": len(reports),
                "passed": sum(1 for report in reports if report["passed"]),
                "failed": sum(1 for report in reports if not report["passed"]),
            },
        }

    def _regression_path(self, corpus_id: str) -> Path:
        for truth_path in regression_truth_paths(self.truth_dir):
            truth = json.loads(truth_path.read_text())
            if truth.get("corpus_id") == corpus_id or truth_path.stem == corpus_id:
                return truth_path
        raise ValueError(f"Unknown regression corpus: {corpus_id}")


def regression_truth_paths(truth_dir: Path | None = None) -> list[Path]:
    root = truth_dir or DEFAULT_TRUTH_PATH.parent
    return [root / file_name for file_name in REGRESSION_TRUTH_FILES]


def _claim_hits(claim: str, corpus_text: str) -> int:
    stopwords = {
        "a",
        "an",
        "and",
        "for",
        "of",
        "or",
        "the",
        "to",
        "was",
        "were",
    }
    terms = {
        term.lower().strip(".,:;()")
        for term in claim.split()
        if len(term.strip(".,:;()")) > 3 and term.lower().strip(".,:;()") not in stopwords
    }
    return sum(1 for term in terms if term in corpus_text)
