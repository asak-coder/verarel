from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Any

from pinecone import Pinecone

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "dating-app-users")
PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "default")
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "1536"))


@dataclass(frozen=True)
class VectorRecord:
    id: str
    values: list[float]
    metadata: dict[str, Any]


def get_pinecone_index():
    if not PINECONE_API_KEY:
        raise RuntimeError("PINECONE_API_KEY is not configured")
    client = Pinecone(api_key=PINECONE_API_KEY)
    return client.Index(PINECONE_INDEX_NAME)


def text_to_embedding(text: str, dimensions: int = EMBEDDING_DIMENSION) -> list[float]:
    """
    Deterministic local fallback embedding for asynchronous indexing.
    Replace with a true embedding model when the embedding provider is finalized.
    """
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values: list[float] = []
    while len(values) < dimensions:
        for byte in digest:
            values.append((byte / 255.0) * 2.0 - 1.0)
            if len(values) >= dimensions:
                break
        digest = hashlib.sha256(digest).digest()
    return values[:dimensions]


def build_user_vector_payload(
    user_id: int,
    text: str,
    kind: str,
    extra_metadata: dict[str, Any] | None = None,
) -> VectorRecord:
    metadata: dict[str, Any] = {
        "user_id": user_id,
        "kind": kind,
        "text": text[:1000],
    }
    if extra_metadata:
        metadata.update(extra_metadata)
    return VectorRecord(
        id=f"user:{user_id}:{kind}",
        values=text_to_embedding(text),
        metadata=metadata,
    )


def upsert_user_vector(user_id: int, text: str, kind: str, extra_metadata: dict[str, Any] | None = None) -> None:
    record = build_user_vector_payload(user_id=user_id, text=text, kind=kind, extra_metadata=extra_metadata)
    index = get_pinecone_index()
    index.upsert(
        vectors=[
            {
                "id": record.id,
                "values": record.values,
                "metadata": record.metadata,
            }
        ],
        namespace=PINECONE_NAMESPACE,
    )
