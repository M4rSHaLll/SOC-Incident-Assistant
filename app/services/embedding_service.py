"""Sentence Transformer lifecycle and non-blocking text encoding."""

from __future__ import annotations

import asyncio
import math
from typing import TYPE_CHECKING

from app.core.config import EMBEDDING_DIMENSION

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer


class EmbeddingService:
    def __init__(self, model_name: str, dimension: int) -> None:
        if dimension != EMBEDDING_DIMENSION:
            raise ValueError(
                f"Database schema requires dimension {EMBEDDING_DIMENSION}"
            )
        self.model_name = model_name
        self.dimension = dimension
        self._model: SentenceTransformer | None = None

    def _load_model(self) -> SentenceTransformer:
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(self.model_name, device="cpu")

    async def load_model(self) -> None:
        """Load once at application startup, outside the event loop thread."""
        if self._model is None:
            model = await asyncio.to_thread(self._load_model)
            if model.get_embedding_dimension() != self.dimension:
                raise ValueError("Model dimension does not match the database schema")
            self._model = model

    def _encode(self, text: str) -> list[float]:
        if self._model is None:
            raise RuntimeError("Call load_model() before embed_text()")
        values = self._model.encode(
            text,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [float(value) for value in values]

    async def embed_text(self, text: str) -> list[float]:
        embedding = await asyncio.to_thread(self._encode, text)
        if len(embedding) != self.dimension:
            raise ValueError(f"Expected {self.dimension} embedding values")
        if not all(math.isfinite(value) for value in embedding) or not any(embedding):
            raise ValueError("Embedding must be finite and nonzero for cosine distance")
        return embedding
