import json

import requests

from app.config import settings


class LLMUnavailable(Exception):
    pass


class OllamaClient:
    def generate_json(self, prompt: str) -> dict:
        try:
            r = requests.post(
                f"{settings.ollama_url}/api/generate",
                json={
                    "model": settings.model,
                    "prompt": prompt,
                    "format": "json",
                    "stream": False,
                    "options": {"temperature": 0.3},
                },
                timeout=settings.llm_timeout,
            )
            r.raise_for_status()
            return json.loads(r.json()["response"])
        except (requests.RequestException, KeyError) as e:
            raise LLMUnavailable(str(e)) from e
        except ValueError:  # bad JSON from the model
            return {}
