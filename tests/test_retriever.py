from app.rag.retriever import HybridRetriever, rrf

CHUNKS = [
    "Photosynthesis happens in chloroplasts.",
    "The French Revolution began in 1789.",
    "Water boils at 100 degrees Celsius.",
]


def test_rrf_prefers_items_ranked_high_in_both_lists():
    assert rrf([[1, 2, 3], [1, 3, 2]])[0] == 1


def test_hybrid_search_finds_relevant_chunk():
    r = HybridRetriever(CHUNKS)
    assert "chloroplasts" in r.search("where does photosynthesis occur", k=1)[0]


def test_rerank_path_runs():
    r = HybridRetriever(CHUNKS)
    assert "1789" in r.search("when did the French Revolution start", k=1, rerank=True)[0]
