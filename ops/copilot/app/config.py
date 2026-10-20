import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    prometheus_url: str = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
    app_url: str = os.getenv("APP_URL", "http://host.docker.internal:8000")
    ollama_url: str = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3")
    llm_timeout: int = int(os.getenv("LLM_TIMEOUT", "60"))
    jenkins_url: str = os.getenv("JENKINS_URL", "http://host.docker.internal:8080")
    jenkins_user: str = os.getenv("JENKINS_USER", "")
    jenkins_token: str = os.getenv("JENKINS_TOKEN", "")
    jenkins_job: str = os.getenv("JENKINS_ROLLBACK_JOB", "quizitout-rollback")
    db_path: str = os.getenv("DB_PATH", "/data/copilot.db")
    enable_replay: bool = os.getenv("ENABLE_REPLAY", "false").lower() == "true"
    alert_for_seconds: int = int(os.getenv("ALERT_FOR_SECONDS", "60"))
    lookback_seconds: int = int(os.getenv("LOOKBACK_SECONDS", "1200"))
    min_reason_chars: int = 15
    fast_decision_seconds: int = 10


settings = Settings()
