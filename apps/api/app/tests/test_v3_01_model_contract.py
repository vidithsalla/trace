import json
import os
import uuid

import httpx
import pytest
from structlog.testing import capture_logs

from app.core.config import Settings
from app.services.llm.client import (
    CallBudget,
    CallBudgetExceededError,
    ChatClient,
    ProviderAuthError,
    ProviderConfig,
    ProviderConfigError,
    ProviderContentFilteredError,
    ProviderRateLimitedError,
    ProviderResponseTooLargeError,
    ProviderSchemaError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.services.llm.contracts import ClaimProposal, EvidencePack, EvidencePackItem
from app.services.llm.engine import MockClaimEngine, RealClaimEngine, get_claim_engine

SECRET_TEXT = "CONFIDENTIAL-PASSAGE-7731"


def _pack() -> EvidencePack:
    return EvidencePack(items=(
        EvidencePackItem(ref="ev_01", source_span_id=None, chunk_id=uuid.uuid4(),
                         document_id=uuid.uuid4(), document_title="memo.txt", page=1,
                         text=f"Invoice 7A is approved subject to verification. {SECRET_TEXT}"),
    ))


def _completion(content, finish_reason="stop"):
    return {"choices": [{"message": {"content": content}, "finish_reason": finish_reason}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 20}}


VALID = json.dumps({"answer_status": "proposed", "abstention_reason": None, "claims": [
    {"client_claim_id": "c1", "text": "Invoice 7A was approved subject to verification.",
     "evidence_refs": ["ev_01"], "open_questions": []}]})


def _client(handler, **overrides) -> ChatClient:
    config = ProviderConfig(kind="local", model="test-model",
                            base_url="http://127.0.0.1:11434/v1", **overrides)
    return ChatClient(config, transport=httpx.MockTransport(handler), sleep=lambda _s: None)


def _call(client):
    return RealClaimEngine(client).propose_claims("Was 7A approved?", _pack(), CallBudget(5))


def test_success_returns_typed_claims_and_sends_schema():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_completion(VALID))

    result = _call(_client(handler))
    assert isinstance(result, ClaimProposal)
    assert result.claims[0].evidence_refs == ["ev_01"]
    assert seen["body"]["response_format"]["type"] == "json_schema"
    assert seen["body"]["temperature"] == 0.0
    assert "untrusted" in seen["body"]["messages"][0]["content"]


def test_code_fenced_json_is_accepted():
    result = _call(_client(lambda r: httpx.Response(200, json=_completion(f"```json\n{VALID}\n```"))))
    assert result.answer_status == "proposed"


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(200, json=_completion("not json at all")), ProviderSchemaError),
        (httpx.Response(200, json=_completion('{"answer_status": "proposed"}')), ProviderSchemaError),
        (httpx.Response(200, json=_completion(VALID[:-1] + ', "extra": 1}')), ProviderSchemaError),
        (httpx.Response(200, json=_completion(VALID, finish_reason="length")), ProviderSchemaError),
        (httpx.Response(200, json=_completion("", finish_reason="content_filter")),
         ProviderContentFilteredError),
        (httpx.Response(200, json={"unexpected": True}), ProviderSchemaError),
        (httpx.Response(200, content=b"<html>"), ProviderSchemaError),
        (httpx.Response(401), ProviderAuthError),
        (httpx.Response(302, headers={"location": "http://evil.example"}), ProviderConfigError),
    ],
)
def test_bad_responses_raise_typed_errors_without_retry(response, error):
    calls = []

    def handler(request):
        calls.append(1)
        return response

    with pytest.raises(error):
        _call(_client(handler))
    assert len(calls) == 1


def test_rate_limit_retries_then_succeeds():
    responses = [httpx.Response(429), httpx.Response(200, json=_completion(VALID))]
    budget = CallBudget(5)
    client = _client(lambda r: responses.pop(0))
    RealClaimEngine(client).propose_claims("q", _pack(), budget)
    assert budget.records[0].attempts == 2 and budget.records[0].status == "ok"


@pytest.mark.parametrize(("status", "error"), [(429, ProviderRateLimitedError),
                                               (503, ProviderUnavailableError)])
def test_retries_are_capped(status, error):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(status)

    with pytest.raises(error):
        _call(_client(handler, max_retries=2))
    assert len(calls) == 3


def test_timeout_and_unreachable_are_distinct():
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    def refused(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ProviderTimeoutError):
        _call(_client(timeout, max_retries=0))
    with pytest.raises(ProviderUnavailableError):
        _call(_client(refused, max_retries=0))


def test_oversized_response_rejected():
    big = _completion(VALID)
    big["padding"] = "x" * 2000
    with pytest.raises(ProviderResponseTooLargeError):
        _call(_client(lambda r: httpx.Response(200, json=big), max_response_bytes=1000))


def test_call_budget_enforced():
    client = _client(lambda r: httpx.Response(200, json=_completion(VALID)))
    budget = CallBudget(1)
    engine = RealClaimEngine(client)
    engine.propose_claims("q", _pack(), budget)
    with pytest.raises(CallBudgetExceededError):
        engine.propose_claims("q", _pack(), budget)


def test_logs_contain_metadata_but_never_evidence_text():
    with capture_logs() as logs:
        _call(_client(lambda r: httpx.Response(200, json=_completion(VALID))))
    assert logs and logs[0]["event"] == "llm_call"
    assert logs[0]["prompt_tokens"] == 50
    assert SECRET_TEXT not in repr(logs)


def test_real_provider_failure_never_falls_back_to_mock():
    settings = Settings(model_provider="local", model_base_url="http://127.0.0.1:9/v1",
                        model_max_retries=0, model_timeout_seconds=2)
    engine = get_claim_engine(settings)
    assert isinstance(engine, RealClaimEngine)
    with pytest.raises(ProviderUnavailableError):
        engine.propose_claims("q", _pack(), CallBudget(2))


def test_mock_only_when_explicitly_configured():
    assert isinstance(get_claim_engine(Settings(model_provider="mock")), MockClaimEngine)
    with pytest.raises(ProviderConfigError):
        get_claim_engine(Settings(model_provider="gpt-please"))


def test_hosted_requires_egress_acknowledgement_and_https():
    with pytest.raises(ProviderConfigError, match="EGRESS"):
        get_claim_engine(Settings(model_provider="hosted", model_base_url="https://8.8.8.8/v1"))
    with pytest.raises(ProviderConfigError, match="https"):
        get_claim_engine(Settings(model_provider="hosted", model_base_url="http://8.8.8.8/v1",
                                  hosted_egress_acknowledged=True))
    engine = get_claim_engine(Settings(model_provider="hosted", model_base_url="https://8.8.8.8/v1",
                                       hosted_egress_acknowledged=True, model_api_key="sk-test-SECRET123"))
    assert engine.describe()["endpoint_class"] == "public_internet"
    assert "SECRET123" not in json.dumps(engine.describe())


def test_local_provider_cannot_point_at_public_internet():
    with pytest.raises(ProviderConfigError, match="public internet"):
        get_claim_engine(Settings(model_provider="local", model_base_url="http://8.8.8.8/v1"))


def test_legacy_provider_name_maps_to_local():
    config = ProviderConfig.from_settings(Settings(model_provider="openai_compatible"))
    assert config.kind == "local"


def test_mock_engine_abstains_without_overlap_and_flags_conditions():
    engine = MockClaimEngine()
    budget = CallBudget(5)
    assert engine.propose_claims("interest rate penalty", _pack(), budget).answer_status == \
        "insufficient_context"
    assessment = engine.assess_support("Invoice 7A was approved without conditions.", _pack(), budget)
    assert assessment.relations[0].relation == "qualifies"
    assert assessment.overall == "contradicted"


@pytest.mark.real_model
@pytest.mark.skipif(os.environ.get("TRACE_REAL_MODEL_TESTS") != "1",
                    reason="opt-in: set TRACE_REAL_MODEL_TESTS=1 with a local model running")
def test_real_local_model_smoke():
    settings = Settings(model_provider=os.environ.get("TRACE_MODEL_PROVIDER_FOR_SMOKE", "local"))
    engine = get_claim_engine(settings)
    assert isinstance(engine, RealClaimEngine)
    budget = CallBudget(3)
    proposal = engine.propose_claims("Was invoice 7A approved, and on what condition?", _pack(), budget)
    assert proposal.answer_status in {"proposed", "insufficient_context", "abstained"}
    for claim in proposal.claims:
        assert set(claim.evidence_refs) <= _pack().refs or claim.evidence_refs
    assert budget.records[0].status == "ok"
    assert budget.records[0].prompt_tokens
