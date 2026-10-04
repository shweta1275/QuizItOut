from app.rag.chunker import chunk_text, pick_spread


def test_chunks_respect_size():
    text = "\n\n".join(["word " * 50] * 20)
    chunks = chunk_text(text, size=300, overlap=30)
    assert len(chunks) > 1
    assert all(len(c) <= 300 for c in chunks)


def test_huge_paragraph_is_split():
    assert len(chunk_text("a" * 2000, size=500, overlap=50)) >= 4


def test_pick_spread_covers_whole_document():
    picked = pick_spread([str(i) for i in range(100)], 5)
    assert picked[0] == "0" and int(picked[-1]) >= 70


def test_pick_spread_returns_all_when_few_chunks():
    assert pick_spread(["a", "b"], 5) == ["a", "b"]
