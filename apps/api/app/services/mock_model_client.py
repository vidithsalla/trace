from __future__ import annotations

import re
from datetime import date

from app.schemas.workflow import (
    ChronologyEvent,
    ChronologyRequest,
    ChronologyResponse,
    CitationPayload,
    ContradictionItem,
    ContradictionRequest,
    ContradictionResponse,
    GroundedQAResponse,
)
from app.services.contradictions import cluster_evidence_for_topic
from app.services.model_client import EvidenceItem, MemoDraft, MemoFact, ModelClient


class MockModelClient(ModelClient):
    def __init__(self, model_name: str = "trace-mock-local") -> None:
        super().__init__(provider_name="mock", model_name=model_name)

    def grounded_qa(self, question: str, evidence: list[EvidenceItem]) -> GroundedQAResponse:
        citations = self._citations(evidence[:2])
        if not citations:
            return GroundedQAResponse(
                answer="Insufficient evidence available in the current matter corpus.",
                short_answer="Insufficient evidence.",
                confidence="low",
                citations=[],
                open_questions=["Upload more documents or complete ingestion to strengthen the answer."],
                unsupported_claims_detected=False,
            )

        answer = " ".join(f"{item.document_name} states: {item.quote}" for item in evidence[:2])
        return GroundedQAResponse(
            answer=answer,
            short_answer=f"Retrieved {len(citations)} grounded evidence item(s) for: {question}",
            confidence="medium" if len(citations) > 1 else "low",
            citations=citations,
            open_questions=[],
            unsupported_claims_detected=False,
        )

    def chronology(self, request: ChronologyRequest, evidence: list[EvidenceItem]) -> ChronologyResponse:
        events: list[ChronologyEvent] = []
        for index, item in enumerate(evidence[:10], start=1):
            event_date, date_text, date_confidence = _extract_date(item.text, index)
            title = _event_title(item.text, index)
            events.append(
                ChronologyEvent(
                    date=event_date,
                    date_text=date_text,
                    date_confidence=date_confidence,
                    title=title,
                    description=item.quote,
                    entity_names=_extract_entities(item.text),
                    citations=self._citations([item]),
                    conflict_flag="dispute" in item.text.lower() or "contradict" in item.text.lower(),
                    confidence="medium",
                )
            )
        ambiguities = []
        if any(event.date_confidence == "low" for event in events):
            ambiguities.append("Some events only provided relative or inferred dates.")
        return ChronologyResponse(events=events, unresolved_ambiguities=ambiguities)

    def contradictions(
        self, request: ContradictionRequest, evidence: list[EvidenceItem]
    ) -> ContradictionResponse:
        profile, side_a, side_b, ambiguities = cluster_evidence_for_topic(request.topic, evidence)
        if not side_a or not side_b:
            return ContradictionResponse(
                topic=request.topic,
                contradictions=[],
                ambiguities=ambiguities or [
                    "Not enough evidence was retrieved to form both sides of a contradiction pair."
                ],
                evidence_count=len(evidence),
            )

        return ContradictionResponse(
            topic=request.topic,
            contradictions=[
                ContradictionItem(
                    claim_a=profile.side_a_claim,
                    claim_b=profile.side_b_claim,
                    why_conflict=profile.why_conflict,
                    severity=profile.severity,
                    citations_a=self._citations(side_a[:2]),
                    citations_b=self._citations(side_b[:2]),
                    side_a_label=profile.side_a_label,
                    side_b_label=profile.side_b_label,
                    confidence="medium",
                )
            ],
            ambiguities=[],
            evidence_count=len(evidence),
        )

    def issue_memo(self, issue: str, evidence: list[EvidenceItem]) -> MemoDraft:
        qa = self.grounded_qa(issue, evidence)
        supporting_evidence = evidence[:2]
        contrary_evidence = [
            item
            for item in evidence
            if any(
                term in item.text.lower()
                for term in ["conditional", "disputed", "withheld", "late", "incomplete", "after shipment"]
            )
        ][:2]
        if not contrary_evidence and len(evidence) > 2:
            contrary_evidence = evidence[2:3]
        supporting = [
            MemoFact(statement=item.quote, citations=self._citations([item])) for item in supporting_evidence
        ]
        contrary = [
            MemoFact(statement=item.quote, citations=self._citations([item])) for item in contrary_evidence
        ]
        markdown = "\n".join(
            [
                f"# {issue}",
                "",
                "## Answer in Brief",
                qa.answer,
                "",
                "## Supporting Facts",
                *[f"- {fact.statement}" for fact in supporting],
            ]
        )
        return MemoDraft(
            answer_in_brief=qa.short_answer,
            supporting_facts=supporting,
            contrary_facts=contrary,
            gaps=qa.open_questions or ["Confirm governing notice and payment provisions in the contract."],
            next_documents_to_review=[
                "Formal notice letter",
                "Payment approval email thread",
                "Inspection and shipment records",
            ],
            content_markdown=markdown,
        )

    def entity_summary(self, entity_name: str, evidence: list[EvidenceItem]) -> dict:
        key_actions = [item.quote for item in evidence[:5]]
        documents = sorted({item.document_name for item in evidence})
        overview = (
            f"{entity_name} appears in {len(evidence)} validated matter mention(s)"
            if evidence
            else f"{entity_name} has no validated mentions yet."
        )
        return {
            "overview": overview,
            "role_in_matter": _entity_role(entity_name),
            "key_actions": key_actions,
            "key_documents": documents,
            "key_dates": _summary_dates(evidence),
            "open_questions": [] if evidence else ["Upload or ingest documents that mention this entity."],
        }

    def _citations(self, evidence: list[EvidenceItem]) -> list[CitationPayload]:
        return [
            CitationPayload(
                document_id=item.document_id,
                document_name=item.document_name,
                page=item.page,
                chunk_id=item.chunk_id,
                quote=item.quote,
            )
            for item in evidence
        ]


DATE_RE = re.compile(r"\b(2024)-(\d{2})-(\d{2})\b")
MONTH_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(2024)\b",
    re.IGNORECASE,
)
MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
ENTITY_CANDIDATES = [
    "Acme Industrial",
    "Northshore Supply",
    "Jane Mercer",
    "Priya Shah",
    "Project Falcon",
    "Compressor Unit 7A",
]


def _extract_date(text: str, index: int) -> tuple[date | None, str, str]:
    iso_match = DATE_RE.search(text)
    if iso_match:
        year, month, day = (int(part) for part in iso_match.groups())
        return date(year, month, day), iso_match.group(0), "high"
    month_match = MONTH_RE.search(text)
    if month_match:
        month_name, day, year = month_match.groups()
        return date(int(year), MONTHS[month_name.lower()], int(day)), month_match.group(0), "high"
    return date(2024, 3, min(index, 28)), f"inferred March {min(index, 28)}, 2024", "low"


def _event_title(text: str, index: int) -> str:
    first_sentence = text.split(".")[0].strip()
    if not first_sentence:
        return f"Retrieved matter event {index}"
    words = first_sentence.split()
    title = " ".join(words[:12])
    return title if len(words) <= 12 else f"{title}..."


def _extract_entities(text: str) -> list[str]:
    lower_text = text.lower()
    return [entity for entity in ENTITY_CANDIDATES if entity.lower() in lower_text]


def _entity_role(entity_name: str) -> str:
    lower = entity_name.lower()
    if "jane" in lower:
        return "Witness or participant associated with Project Falcon and defect history evidence."
    if "priya" in lower:
        return "Participant associated with payment approval and notice review evidence."
    if "northshore" in lower:
        return "Counterparty organization tied to shipment, notice, and defect knowledge evidence."
    if "acme" in lower:
        return "Matter party receiving the equipment and asserting notice or payment positions."
    if "project falcon" in lower:
        return "Project context connecting equipment readiness, inspection, and payment disputes."
    if "compressor" in lower or "7a" in lower:
        return "Equipment or product at the center of the defect and shipment dispute."
    return "Matter entity derived from parsed source mentions."


def _summary_dates(evidence: list[EvidenceItem]) -> list[str]:
    dates: list[str] = []
    for item in evidence:
        for match in DATE_RE.finditer(item.text):
            if match.group(0) not in dates:
                dates.append(match.group(0))
        for match in MONTH_RE.finditer(item.text):
            if match.group(0) not in dates:
                dates.append(match.group(0))
    return dates[:5]
