import os
from typing import List

import httpx
import numpy as np


EMBEDDING_BASE_URL = os.environ.get("QWEN_EMBEDDING_BASE_URL", "http://127.0.0.1:8001/v1")
EMBEDDING_MODEL = os.environ.get("QWEN_EMBEDDING_MODEL", "qwen3-embedding-8b")
EMBEDDING_TIMEOUT = float(os.environ.get("QWEN_EMBEDDING_TIMEOUT", "120"))


def embed_texts(texts: List[str]) -> List[np.ndarray]:
    if not texts:
        return []

    payload = {"model": EMBEDDING_MODEL, "input": texts}
    with httpx.Client(trust_env=False, timeout=EMBEDDING_TIMEOUT) as client:
        resp = client.post(f"{EMBEDDING_BASE_URL.rstrip('/')}/embeddings", json=payload)
        resp.raise_for_status()
        data = resp.json()["data"]

    data.sort(key=lambda item: int(item.get("index", 0)))
    return [np.asarray(item["embedding"], dtype=np.float32) for item in data]


def embed_text(text: str) -> np.ndarray:
    vectors = embed_texts([text])
    if not vectors:
        raise RuntimeError("embedding service returned no vectors")
    return vectors[0]
