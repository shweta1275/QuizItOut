import os
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.parsers import PARSERS, parse_file
from app.quiz import fallback
from app.quiz.generator import generate_quiz
from app.quiz.llm import LLMUnavailable, OllamaClient
from app.rag.chunker import chunk_text
from app.schemas import QuizResponse

app = FastAPI(title="QuizItOut")
llm_client = OllamaClient()
STATIC = Path(__file__).parent / "static"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/quiz/demo", response_model=QuizResponse)
def demo_quiz():
    cache = fallback.load_cache()
    if not cache:
        raise HTTPException(404, "No demo cache built yet")
    return QuizResponse(
        source="cached",
        filename=cache["filename"],
        questions=cache["questions"][: settings.max_questions],
    )


@app.post("/api/quiz", response_model=QuizResponse)
def make_quiz(file: Annotated[UploadFile, File()], topic: Annotated[str | None, Form()] = None):
    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in PARSERS:
        raise HTTPException(400, f"Unsupported type '{suffix}'. Use: {', '.join(sorted(PARSERS))}")
    data = file.file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, "File too large")

    n = settings.max_questions
    if settings.prefer_cache:
        cached = fallback.cached_quiz_for(data, n)
        if cached:
            return QuizResponse(source="cached", filename=filename, questions=cached)

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
    try:
        text = parse_file(tmp.name)
    except ValueError as e:
        raise HTTPException(422, str(e))
    finally:
        os.unlink(tmp.name)

    chunks = chunk_text(text, settings.chunk_size, settings.chunk_overlap)
    if topic:
        from app.rag.retriever import HybridRetriever  # heavy import, only when needed

        chunks = HybridRetriever(chunks).search(topic, k=n, rerank=True)

    questions, llm_down = [], False
    try:
        questions = generate_quiz(chunks, llm_client, n)
    except LLMUnavailable:
        llm_down = True
    if questions:
        return QuizResponse(source="live", filename=filename, questions=questions)

    cached = fallback.cached_quiz_for(data, n)
    if cached:
        return QuizResponse(source="cached", filename=filename, questions=cached)
    if llm_down:
        raise HTTPException(503, "Quiz model unreachable. Is Ollama running?")
    raise HTTPException(502, "Model returned no valid questions. Try again.")


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
