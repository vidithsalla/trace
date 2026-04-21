from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.schemas.workflow import (
    ChronologyRequest,
    ChronologyResponse,
    CitationPayload,
    ContradictionRequest,
    ContradictionResponse,
    GroundedQAResponse,
)


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    document_id: UUID
    document_name: str
    page: int | None
    chunk_id: UUID | None
    quote: str
    text: str


@dataclass(frozen=True, slots=True)
class MemoFact:
    statement: str
    citations: list[CitationPayload]


@dataclass(frozen=True, slots=True)
class MemoDraft:
    answer_in_brief: str
    supporting_facts: list[MemoFact]
    contrary_facts: list[MemoFact]
    gaps: list[str]
    next_documents_to_review: list[str]
    content_markdown: str


class ModelClientError(RuntimeError):
    pass


class ModelClient(ABC):
    def __init__(self, provider_name: str, model_name: str) -> None:
        self.provider_name = provider_name
        self.model_name = model_name

    @abstractmethod
    def grounded_qa(self, question: str, evidence: list[EvidenceItem]) -> GroundedQAResponse:
        raise NotImplementedError

    @abstractmethod
    def chronology(self, request: ChronologyRequest, evidence: list[EvidenceItem]) -> ChronologyResponse:
        raise NotImplementedError

    @abstractmethod
    def contradictions(
        self, request: ContradictionRequest, evidence: list[EvidenceItem]
    ) -> ContradictionResponse:
        raise NotImplementedError

    @abstractmethod
    def issue_memo(self, issue: str, evidence: list[EvidenceItem]) -> MemoDraft:
        raise NotImplementedError

    def entity_summary(self, entity_name: str, evidence: list[EvidenceItem]) -> dict[str, Any]:
        return {
            "overview": f"{entity_name} appears in {len(evidence)} retrieved evidence items.",
            "role_in_matter": "Pending extraction refinement.",
            "key_actions": [item.quote for item in evidence[:3]],
            "key_dates": [],
            "open_questions": [],
        }
