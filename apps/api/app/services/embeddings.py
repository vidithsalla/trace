from __future__ import annotations

import hashlib
import importlib
import math
import re
from collections.abc import Iterable
from typing import Any


EMBEDDING_DIMENSION = 384
TOKEN_RE = re.compile(r"[a-z0-9]+")


class EmbeddingClient:
    dimension = EMBEDDING_DIMENSION

    def embed_texts(self, texts: Iterable[str]) -> list[list[float]]:
        raise NotImplementedError


class LocalHashEmbeddingClient(EmbeddingClient):
    """Tiny deterministic embedding client for local development.

    It is not a semantic model, but it gives us stable pgvector-shaped vectors,
    cosine-style ranking, and no heavy model process on an 8 GB laptop.
    """

    def embed_texts(self, texts: Iterable[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = TOKEN_RE.findall(text.lower())
        features = tokens + [f"{left}_{right}" for left, right in zip(tokens, tokens[1:])]

        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


class SentenceTransformerEmbeddingClient(EmbeddingClient):
    """Semantic embedding provider backed by sentence-transformers.

    The dependency and model are loaded lazily so the default lightweight
    development path never imports torch or downloads model weights.
    """

    def __init__(self, model_name: str, model: Any | None = None) -> None:
        self.model_name = model_name
        self._model = model

    def embed_texts(self, texts: Iterable[str]) -> list[list[float]]:
        text_values = list(texts)
        if not text_values:
            return []

        model = self._load_model()
        encoded = model.encode(
            text_values,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [self._normalize(vector) for vector in self._coerce_vectors(encoded, len(text_values))]

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model

        try:
            sentence_transformers = importlib.import_module("sentence_transformers")
        except ImportError as exc:
            raise RuntimeError(
                "TRACE_EMBEDDING_PROVIDER=sentence_transformer requires the optional "
                "semantic embedding dependency. Install the semantic extra before enabling it."
            ) from exc

        self._model = sentence_transformers.SentenceTransformer(self.model_name)
        return self._model

    def _coerce_vectors(self, encoded: Any, expected_count: int) -> list[list[float]]:
        if hasattr(encoded, "tolist"):
            encoded = encoded.tolist()

        if expected_count == 1 and encoded and isinstance(encoded[0], int | float):
            encoded = [encoded]

        vectors = [[float(value) for value in vector] for vector in encoded]
        if len(vectors) != expected_count:
            raise RuntimeError(
                f"Embedding model returned {len(vectors)} vectors for {expected_count} texts."
            )
        return vectors

    def _normalize(self, vector: list[float]) -> list[float]:
        if len(vector) != self.dimension:
            raise RuntimeError(
                f"Embedding model '{self.model_name}' returned {len(vector)} dimensions; "
                f"Trace requires {self.dimension}."
            )

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


def cosine_similarity(left, right) -> float:
    if left is None or right is None:
        return 0.0
    left_values = list(left)
    right_values = list(right)
    if not left_values or not right_values:
        return 0.0
    return sum(a * b for a, b in zip(left_values, right_values))


def get_embedding_client(
    provider: str | None = None,
    model_name: str | None = None,
) -> EmbeddingClient:
    from app.core.config import settings

    selected_provider = (provider or settings.embedding_provider).strip().lower()
    selected_model = model_name or settings.embedding_model

    if selected_provider in {"hash", "local_hash"}:
        return LocalHashEmbeddingClient()
    if selected_provider in {"sentence_transformer", "sentence-transformer", "semantic"}:
        return SentenceTransformerEmbeddingClient(selected_model)

    raise RuntimeError(
        "Unknown TRACE_EMBEDDING_PROVIDER "
        f"'{selected_provider}'. Expected 'hash' or 'sentence_transformer'."
    )
