import importlib
import math
import sys
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.services.embeddings import (
    EMBEDDING_DIMENSION,
    LocalHashEmbeddingClient,
    SentenceTransformerEmbeddingClient,
    get_embedding_client,
)


class FakeSentenceTransformer:
    def __init__(self, model_name: str = "fake-model") -> None:
        self.model_name = model_name

    def encode(
        self,
        texts: list[str],
        *,
        normalize_embeddings: bool,
        show_progress_bar: bool,
    ) -> list[list[float]]:
        assert normalize_embeddings is True
        assert show_progress_bar is False
        return [[3.0, 4.0, *([0.0] * (EMBEDDING_DIMENSION - 2))] for _text in texts]


def vector_norm(vector: list[float]) -> float:
    return math.sqrt(sum(value * value for value in vector))


def test_hash_embedding_client_is_deterministic_and_384_dimensional() -> None:
    client = LocalHashEmbeddingClient()

    first = client.embed_texts(["Northshore compressor defect"])[0]
    second = client.embed_texts(["Northshore compressor defect"])[0]

    assert first == second
    assert len(first) == EMBEDDING_DIMENSION
    assert vector_norm(first) == pytest.approx(1.0)


def test_get_embedding_client_defaults_to_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "embedding_provider", "hash")

    client = get_embedding_client()

    assert isinstance(client, LocalHashEmbeddingClient)


def test_get_embedding_client_rejects_unknown_provider() -> None:
    with pytest.raises(RuntimeError, match="Unknown TRACE_EMBEDDING_PROVIDER"):
        get_embedding_client(provider="mystery")


def test_sentence_transformer_provider_loads_lazily_from_optional_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_module = SimpleNamespace(SentenceTransformer=FakeSentenceTransformer)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    client = get_embedding_client(provider="sentence_transformer", model_name="fake-model")

    assert isinstance(client, SentenceTransformerEmbeddingClient)
    vector = client.embed_texts(["product flaw known before delivery"])[0]
    assert len(vector) == EMBEDDING_DIMENSION
    assert vector_norm(vector) == pytest.approx(1.0)


def test_sentence_transformer_provider_has_clear_missing_dependency_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import_module = importlib.import_module

    def fake_import_module(name: str, package: str | None = None):
        if name == "sentence_transformers":
            raise ImportError("missing optional dependency")
        return real_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)
    client = SentenceTransformerEmbeddingClient("fake-model")

    with pytest.raises(RuntimeError, match="requires the optional semantic embedding dependency"):
        client.embed_texts(["defect knowledge"])


def test_sentence_transformer_provider_rejects_wrong_dimension_vectors() -> None:
    class WrongDimensionModel:
        def encode(
            self,
            texts: list[str],
            *,
            normalize_embeddings: bool,
            show_progress_bar: bool,
        ) -> list[list[float]]:
            return [[1.0, 0.0] for _text in texts]

    client = SentenceTransformerEmbeddingClient("wrong-dim-model", model=WrongDimensionModel())

    with pytest.raises(RuntimeError, match="requires 384"):
        client.embed_texts(["defect knowledge"])
