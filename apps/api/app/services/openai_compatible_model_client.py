from __future__ import annotations

from app.schemas.workflow import (
    ChronologyRequest,
    ChronologyResponse,
    ContradictionRequest,
    ContradictionResponse,
    GroundedQAResponse,
)
from app.services.mock_model_client import MockModelClient
from app.services.model_client import EvidenceItem, MemoDraft, ModelClient


class OpenAICompatibleModelClient(ModelClient):
    def __init__(self, model_name: str, base_url: str) -> None:
        super().__init__(provider_name="openai_compatible", model_name=model_name)
        self.base_url = base_url
        self._fallback = MockModelClient(model_name=model_name)

    def grounded_qa(self, question: str, evidence: list[EvidenceItem]) -> GroundedQAResponse:
        return self._fallback.grounded_qa(question, evidence)

    def chronology(self, request: ChronologyRequest, evidence: list[EvidenceItem]) -> ChronologyResponse:
        return self._fallback.chronology(request, evidence)

    def contradictions(
        self, request: ContradictionRequest, evidence: list[EvidenceItem]
    ) -> ContradictionResponse:
        return self._fallback.contradictions(request, evidence)

    def issue_memo(self, issue: str, evidence: list[EvidenceItem]) -> MemoDraft:
        return self._fallback.issue_memo(issue, evidence)
