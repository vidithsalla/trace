"""OpenAI-compatible chat client for local (Ollama/llama.cpp/vLLM) and hosted providers.

Design rules (PRD sections 6.2 T2, 8.3):
- The model is an untrusted proposer. Output is parsed into a Pydantic model and rejected if it
  does not validate. Nothing here "repairs" a bad answer.
- No fallback: a configured real provider that fails raises a typed error. The mock is only used
  when explicitly configured.
- Only sanitized metadata is logged (provider kind, model, status, latency, token counts). Prompts,
  evidence text and completions are never logged.
"""

from __future__ import annotations

import ipaddress
import json
import socket
import time
from dataclasses import dataclass, field
from typing import Any, Literal, TypeVar
from urllib.parse import urlparse

import httpx
import structlog
from pydantic import BaseModel, ValidationError

from app.core.config import Settings

logger = structlog.get_logger("trace.llm")

ProviderKind = Literal["mock", "local", "hosted"]
T = TypeVar("T", bound=BaseModel)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


# ---------------------------------------------------------------------------------------------
# Error taxonomy. Each maps to a distinct, user-visible run status; none is ever scored as success.
# ---------------------------------------------------------------------------------------------
class LLMError(RuntimeError):
    code = "provider_error"
    retryable = False


class ProviderConfigError(LLMError):
    code = "provider_config_error"


class ProviderAuthError(LLMError):
    code = "provider_auth_error"


class ProviderRateLimitedError(LLMError):
    code = "provider_rate_limited"
    retryable = True


class ProviderUnavailableError(LLMError):
    code = "provider_unavailable"
    retryable = True


class ProviderTimeoutError(LLMError):
    code = "provider_timeout"
    retryable = True


class ProviderContentFilteredError(LLMError):
    code = "provider_content_filtered"


class ProviderResponseTooLargeError(LLMError):
    code = "provider_response_too_large"


class ProviderSchemaError(LLMError):
    code = "schema_error"


class CallBudgetExceededError(LLMError):
    code = "call_budget_exceeded"


@dataclass(slots=True)
class ProviderConfig:
    kind: ProviderKind
    model: str
    base_url: str | None = None
    api_key: str | None = None
    timeout_seconds: float = 120.0
    max_output_tokens: int = 1500
    max_retries: int = 2
    temperature: float = 0.0
    structured_output: Literal["json_schema", "json_object"] = "json_schema"
    max_response_bytes: int = 256 * 1024
    hosted_egress_acknowledged: bool = False

    @classmethod
    def from_settings(cls, settings: Settings) -> ProviderConfig:
        kind = settings.model_provider
        if kind == "openai_compatible":  # pre-V3 name; it always meant a self-hosted endpoint
            kind = "local"
        if kind not in ("mock", "local", "hosted"):
            raise ProviderConfigError(f"unknown TRACE_MODEL_PROVIDER={kind!r}")
        return cls(
            kind=kind,
            model=settings.model_name,
            base_url=settings.model_base_url,
            api_key=settings.model_api_key,
            timeout_seconds=float(settings.model_timeout_seconds),
            max_output_tokens=settings.model_max_output_tokens,
            max_retries=settings.model_max_retries,
            structured_output=settings.model_structured_output,
            hosted_egress_acknowledged=settings.hosted_egress_acknowledged,
        )

    def describe(self) -> dict[str, Any]:
        """Safe, persistable description. Never includes credentials or full URLs."""
        host = urlparse(self.base_url).hostname if self.base_url else None
        return {
            "provider_kind": self.kind,
            "model": self.model,
            "endpoint_class": _endpoint_class(host) if host else None,
            "structured_output": self.structured_output,
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
        }


def _endpoint_class(host: str) -> str:
    if host in {"localhost", "host.docker.internal"} or host.endswith(".local"):
        return "loopback"
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        try:
            ip = ipaddress.ip_address(socket.gethostbyname(host))
        except (OSError, ValueError):
            return "unresolved"
    if ip.is_loopback:
        return "loopback"
    if ip.is_private or ip.is_link_local:
        return "private_network"
    return "public_internet"


def validate_provider_config(config: ProviderConfig) -> None:
    """Enforce the data-boundary rules before any request is sent."""
    if config.kind == "mock":
        return
    if not config.base_url:
        raise ProviderConfigError("TRACE_MODEL_BASE_URL is required for a real provider")
    parsed = urlparse(config.base_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ProviderConfigError("TRACE_MODEL_BASE_URL must be an http(s) URL")
    endpoint = _endpoint_class(parsed.hostname)
    if config.kind == "local" and endpoint == "public_internet":
        raise ProviderConfigError(
            "provider 'local' points at a public internet host; use 'hosted' and acknowledge egress"
        )
    if config.kind == "hosted":
        if not config.hosted_egress_acknowledged:
            raise ProviderConfigError(
                "hosted provider requires TRACE_HOSTED_EGRESS_ACKNOWLEDGED=true: selected evidence "
                "passages and questions will leave this machine"
            )
        if parsed.scheme != "https" and endpoint == "public_internet":
            raise ProviderConfigError("hosted provider must use https")


@dataclass(slots=True)
class CallRecord:
    """Sanitized per-call metadata, persisted with runs. No prompt or completion text."""

    purpose: str
    status: str
    latency_ms: int
    attempts: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    provider_request_id: str | None = None
    error_code: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__slots__}


@dataclass(slots=True)
class CallBudget:
    max_calls: int
    used: int = 0
    records: list[CallRecord] = field(default_factory=list)

    def take(self) -> None:
        if self.used >= self.max_calls:
            raise CallBudgetExceededError(f"run exceeded its budget of {self.max_calls} model calls")
        self.used += 1


class ChatClient:
    """Sends one chat request and returns a validated Pydantic object."""

    def __init__(
        self,
        config: ProviderConfig,
        transport: httpx.BaseTransport | None = None,
        sleep: Any = time.sleep,
    ) -> None:
        validate_provider_config(config)
        if config.kind == "mock":
            raise ProviderConfigError("use MockChatClient for provider 'mock'")
        self.config = config
        self._sleep = sleep
        headers = {"Content-Type": "application/json"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        self._http = httpx.Client(
            base_url=config.base_url.rstrip("/"),
            headers=headers,
            timeout=httpx.Timeout(config.timeout_seconds, connect=10.0),
            transport=transport,
            follow_redirects=False,
        )

    @property
    def is_mock(self) -> bool:
        return False

    def close(self) -> None:
        self._http.close()

    def complete_json(
        self,
        *,
        purpose: str,
        system: str,
        user: str,
        schema: type[T],
        budget: CallBudget,
    ) -> T:
        budget.take()
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_output_tokens,
            "stream": False,
        }
        if self.config.structured_output == "json_schema":
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": schema.model_json_schema(),
                    "strict": True,
                },
            }
        else:
            payload["response_format"] = {"type": "json_object"}

        started = time.monotonic()
        record = CallRecord(purpose=purpose, status="error", latency_ms=0, attempts=0)
        try:
            body = self._send_with_retries(payload, record)
            result = self._parse(body, schema, record)
            record.status = "ok"
            return result
        except LLMError as exc:
            record.error_code = exc.code
            raise
        finally:
            record.latency_ms = int((time.monotonic() - started) * 1000)
            budget.records.append(record)
            logger.info(
                "llm_call",
                provider_kind=self.config.kind,
                model=self.config.model,
                **record.as_dict(),
            )

    def _send_with_retries(self, payload: dict[str, Any], record: CallRecord) -> dict[str, Any]:
        last_error: LLMError | None = None
        for attempt in range(self.config.max_retries + 1):
            record.attempts = attempt + 1
            try:
                return self._send_once(payload, record)
            except LLMError as exc:
                last_error = exc
                if not exc.retryable or attempt == self.config.max_retries:
                    raise
                self._sleep(min(2**attempt, 8))
        raise last_error or ProviderUnavailableError("no attempt made")  # pragma: no cover

    def _send_once(self, payload: dict[str, Any], record: CallRecord) -> dict[str, Any]:
        try:
            response = self._http.post("/chat/completions", json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("model request timed out") from exc
        except httpx.TransportError as exc:
            raise ProviderUnavailableError("model endpoint unreachable") from exc

        record.provider_request_id = response.headers.get("x-request-id")
        status = response.status_code
        if status in (401, 403):
            raise ProviderAuthError(f"provider rejected credentials (HTTP {status})")
        if status == 429:
            raise ProviderRateLimitedError("provider rate limit")
        if status in _RETRYABLE_STATUS:
            raise ProviderUnavailableError(f"provider error (HTTP {status})")
        if 300 <= status < 400:
            raise ProviderConfigError(f"provider redirected (HTTP {status}); redirects are refused")
        if status >= 400:
            raise LLMError(f"provider returned HTTP {status}")
        if len(response.content) > self.config.max_response_bytes:
            raise ProviderResponseTooLargeError("provider response exceeded size limit")
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderSchemaError("provider response was not JSON") from exc

    def _parse(self, body: dict[str, Any], schema: type[T], record: CallRecord) -> T:
        usage = body.get("usage") or {}
        record.prompt_tokens = usage.get("prompt_tokens")
        record.completion_tokens = usage.get("completion_tokens")
        try:
            choice = body["choices"][0]
            finish_reason = choice.get("finish_reason")
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderSchemaError("provider response missing choices[0].message.content") from exc
        if finish_reason == "content_filter":
            raise ProviderContentFilteredError("provider filtered the response")
        if finish_reason == "length":
            raise ProviderSchemaError("model output truncated at max_output_tokens")
        if not isinstance(content, str) or not content.strip():
            raise ProviderSchemaError("model returned empty content")
        try:
            data = json.loads(_strip_code_fence(content))
        except ValueError as exc:
            raise ProviderSchemaError("model output was not valid JSON") from exc
        try:
            return schema.model_validate(data)
        except ValidationError as exc:
            raise ProviderSchemaError(
                f"model output failed schema validation ({exc.error_count()} errors)"
            ) from exc


def _strip_code_fence(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text
