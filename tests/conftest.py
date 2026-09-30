import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class FakeEmbeddingFunction:
    """Deterministic, dependency-free stand-in for SentenceTransformerEmbeddingFunction.

    Produces a small fixed-dimension vector from a hash of the text so tests never
    download a real embedding model or make network calls.
    """

    def __init__(self, model_name: str = "fake", **kwargs):
        self.model_name = model_name

    def __call__(self, input):  # noqa: A002 - chromadb's expected signature
        import hashlib

        vectors = []
        for text in input:
            h = hashlib.sha256(text.encode("utf-8")).digest()
            vectors.append([b / 255.0 for b in h[:16]])
        return vectors

    def embed_query(self, input):  # noqa: A002 - chromadb >= 1.x query-side hook
        return self(input)

    def name(self):
        return "fake-embedding-function"


@pytest.fixture
def tmp_home(tmp_path, monkeypatch):
    home = tmp_path / "paper-rag-home"
    home.mkdir()
    monkeypatch.setenv("PAPER_RAG_HOME", str(home))
    monkeypatch.delenv("PAPER_RAG_EMBEDDING_MODEL", raising=False)
    return home


@pytest.fixture
def fake_embeddings(monkeypatch):
    from lib import store as store_lib

    monkeypatch.setattr(store_lib, "SentenceTransformerEmbeddingFunction", FakeEmbeddingFunction)
    return FakeEmbeddingFunction
