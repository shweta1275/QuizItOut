import json
import sys
from pathlib import Path

from app.rag.chunker import chunk_text
from app.rag.retriever import HybridRetriever


def main(threshold: float = 0.8) -> int:
    golden = json.loads(Path("tests/golden/golden.json").read_text())
    text = Path(golden["doc"]).read_text()
    retriever = HybridRetriever(chunk_text(text, 400, 50))
    hits = 0
    for case in golden["cases"]:
        top = retriever.search(case["query"], k=3)
        hit = any(case["must_contain"].lower() in chunk.lower() for chunk in top)
        hits += hit
        print(f"  [{'HIT ' if hit else 'MISS'}] {case['query']}")
    rate = hits / len(golden["cases"])
    print(f"retrieval hit-rate@3 = {rate:.2f} (threshold {threshold})")
    return 0 if rate >= threshold else 1


if __name__ == "__main__":
    sys.exit(main())
