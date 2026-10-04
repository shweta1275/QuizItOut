"""Generate data/demo/demo_quiz.json once, from the real pipeline.

Run with Ollama up:  python -m scripts.build_demo_cache
Then REVIEW the JSON by hand (is answer_index on the right option?) and delete bad questions.
"""
import json
from pathlib import Path

from app.config import settings
from app.parsers import parse_file
from app.quiz.fallback import sha256_bytes
from app.quiz.generator import generate_quiz
from app.quiz.llm import OllamaClient
from app.rag.chunker import chunk_text

PDF = Path("data/demo/demo_doc.pdf")


def main() -> None:
    chunks = chunk_text(parse_file(str(PDF)), settings.chunk_size, settings.chunk_overlap)
    questions = generate_quiz(chunks, OllamaClient(), n=12)
    out = {
        "sha256": sha256_bytes(PDF.read_bytes()),
        "filename": PDF.name,
        "questions": [q.model_dump() for q in questions],
    }
    Path(settings.demo_quiz_path).write_text(json.dumps(out, indent=2))
    print(f"Saved {len(questions)} questions. Now REVIEW them by hand before committing.")


if __name__ == "__main__":
    main()
