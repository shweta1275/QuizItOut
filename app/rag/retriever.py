import faiss
import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder, SentenceTransformer

_embedder = None
_reranker = None


def _get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedder


def _get_reranker():
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _reranker


def rrf(rankings: list[list[int]], k: int = 60) -> list[int]:
    """Reciprocal Rank Fusion: merge several ranked id lists."""
    score: dict[int, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking):
            score[int(doc_id)] = score.get(int(doc_id), 0.0) + 1.0 / (k + rank + 1)
    return sorted(score, key=score.get, reverse=True)


class HybridRetriever:
    def __init__(self, chunks: list[str]):
        self.chunks = chunks
        vecs = _get_embedder().encode(chunks, normalize_embeddings=True)
        self.index = faiss.IndexFlatIP(vecs.shape[1])  # inner product = cosine (normalized)
        self.index.add(np.asarray(vecs, dtype="float32"))
        self.bm25 = BM25Okapi([c.lower().split() for c in chunks])

    def search(self, query: str, k: int = 5, rerank: bool = False) -> list[str]:
        pool = min(max(k * 3, 10), len(self.chunks))
        qv = _get_embedder().encode([query], normalize_embeddings=True)
        _, dense_ids = self.index.search(np.asarray(qv, dtype="float32"), pool)
        sparse_ids = np.argsort(self.bm25.get_scores(query.lower().split()))[::-1][:pool]
        fused = rrf([list(dense_ids[0]), list(sparse_ids)])
        if not rerank:
            return [self.chunks[i] for i in fused[:k]]
        shortlist = fused[:pool]
        scores = _get_reranker().predict([(query, self.chunks[i]) for i in shortlist])
        order = np.argsort(scores)[::-1][:k]
        return [self.chunks[shortlist[i]] for i in order]
