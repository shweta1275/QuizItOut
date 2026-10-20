# ---------- base: runtime deps + app code ----------
FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

# patch OS packages (same reason as the QuizItOut image: Trivy flags fixable CVEs in the stock slim image)
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && pip install --no-cache-dir -r requirements.txt
COPY app ./app

# ---------- test: never shipped ----------
FROM base AS test
COPY requirements-dev.txt pytest.ini ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY tests ./tests
CMD ["pytest", "--cov=app", "--cov-fail-under=80", "-q"]

# ---------- runtime: this is what runs in the ops stack ----------
FROM base AS runtime
# recorded incidents are needed by the replay endpoint (demo safety net)
COPY tests/incidents ./tests/incidents
# pip is not needed at runtime and its vendored packages carry CVEs Trivy would flag
RUN python -m pip uninstall -y pip && useradd -m appuser && mkdir /data && chown appuser /data
USER appuser
EXPOSE 8001
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
