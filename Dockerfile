# ---------- base: runtime deps + baked models ----------
FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HOME=/opt/hf
WORKDIR /srv

# patch OS packages (Trivy flagged a fixable libpcre2 CVE in the stock slim image)
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

# requirements first: changing code reuses this (heavy) layer from cache.
# The cache mount keeps downloaded wheels on the build host (not in the image), so changing
# requirements.txt doesn't re-download torch.
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip pip install --upgrade pip setuptools wheel \
 && pip install torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install -r requirements.txt

# bake models into the image so the container starts without network
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; SentenceTransformer('all-MiniLM-L6-v2'); CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')" \
 && chmod -R a+rX /opt/hf

COPY app ./app
COPY data ./data

# ---------- test: never shipped ----------
FROM base AS test
COPY requirements-dev.txt pytest.ini ./
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements-dev.txt
COPY scripts ./scripts
COPY tests ./tests
CMD ["pytest", "--cov=app", "--cov-fail-under=80", "-q"]

# ---------- runtime: this is what ships ----------
FROM base AS runtime
# pip isn't needed to run the app, and its vendored urllib3/msgpack/setuptools carry
# fixable HIGH CVEs (Trivy reads pip/_vendor/bom.cdx.json). Fewer tools = smaller attack surface.
RUN python -m pip uninstall -y pip && useradd -m appuser
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
