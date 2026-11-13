"""Typed contracts between Trace and a model.

The model only ever sees server-issued evidence references (``ev_01`` ...). It never sees or
returns database IDs, so it cannot cite something it was not given or reach outside the matter.
All fields are required (nullable where optional) so the schemas work with strict structured
output on hosted providers as well as with local runtimes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

EVIDENCE_REF_PATTERN = re.compile(r"^ev_\d{2,3}$")

RelationLabel = Literal["supports", "qualifies", "contradicts", "irrelevant", "uncertain"]
OverallLabel = Literal["supported", "contradicted", "mixed", "not_established", "uncertain"]
ReasonCode = Literal[
    "DIRECT_STATEMENT",
    "CONDITIONAL",
    "SUBSEQUENT_CHANGE",
    "DIFFERENT_ENTITY",
    "DIFFERENT_TIME",
    "NEGATION",
    "MISSING_DETAIL",
    "NOT_RELEVANT",
    "AMBIGUOUS",
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProposedClaim(_Strict):
    client_claim_id: str = Field(max_length=16)
    text: str = Field(min_length=3, max_length=400)
    evidence_refs: list[str] = Field(min_length=1, max_length=6)
    open_questions: list[str] = Field(max_length=4)


class ClaimProposal(_Strict):
    answer_status: Literal["proposed", "abstained", "insufficient_context"]
    claims: list[ProposedClaim] = Field(max_length=8)
    abstention_reason: str | None = Field(max_length=400)


class EvidenceRelation(_Strict):
    evidence_ref: str
    relation: RelationLabel
    reason_code: ReasonCode


class SupportAssessment(_Strict):
    relations: list[EvidenceRelation] = Field(max_length=24)
    overall: OverallLabel


@dataclass(frozen=True, slots=True)
class EvidencePackItem:
    """One passage offered to the model. ``ref`` is the only identifier the model sees."""

    ref: str
    source_span_id: UUID | None
    chunk_id: UUID | None
    document_id: UUID
    document_title: str
    page: int | None
    text: str
    retrieval_role: Literal["primary", "counterevidence"] = "primary"


@dataclass(frozen=True, slots=True)
class EvidencePack:
    items: tuple[EvidencePackItem, ...]

    @property
    def refs(self) -> frozenset[str]:
        return frozenset(item.ref for item in self.items)

    def get(self, ref: str) -> EvidencePackItem | None:
        for item in self.items:
            if item.ref == ref:
                return item
        return None


def make_ref(index: int) -> str:
    return f"ev_{index + 1:02d}"
