import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    ollama_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model: str = os.getenv("OLLAMA_MODEL", "llama3")
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "800"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "100"))
    max_questions: int = int(os.getenv("MAX_QUESTIONS", "5"))
    llm_timeout: int = int(os.getenv("LLM_TIMEOUT", "120"))
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "10"))
    demo_quiz_path: str = os.getenv("DEMO_QUIZ_PATH", "data/demo/demo_quiz.json")
    prefer_cache: bool = os.getenv("PREFER_CACHE", "false").lower() == "true"


settings = Settings()
