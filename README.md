# QuizItOut + IncidentPilot

**QuizItOut** turns a document (PDF, DOCX, PPTX, TXT, MD) into a multiple-choice quiz using a **local LLM** (Ollama + llama3), and ships through a full Jenkins CI/CD pipeline.
**IncidentPilot** is the second half of the project: when a release passes every check and still breaks in production, an evidence-grounded copilot finds the likely guilty deploy and proposes a rollback that a human approves.

> One line: *Jenkins CI/CD with Trivy scanning for an LLM quiz app, extended with Prometheus/Alertmanager monitoring and an evidence-grounded, human-approved rollback copilot (local Ollama LLM).*

> **Status note:** items marked `TBD (fill after run)` are filled only after they have been run on the real stack (Docker, Jenkins). See `docs/EXPLANATION_INCIDENTPILOT.md` for the build log.

---

## 1. What is in the repo

| Part | What it is |
|---|---|
| **QuizItOut app** | Upload a file, get a quiz. Local LLM (Ollama, llama3), schema + grounding validation, hybrid retrieval for topic mode, SHA-256-keyed demo cache. Every answer shows an evidence sentence from your document. |
| **Pipeline (road in)** | GitHub, Jenkins, lint, tests with an 80% gate, retrieval quality gate, Docker multi-stage build, Trivy, Docker Hub with git-SHA tags, compose deploy, smoke test, automatic rollback on a failed deploy. |
| **Monitoring (new)** | The app exposes `/metrics`. Prometheus scrapes it. An alert rule watches the 5xx ratio. Alertmanager sends the alert to the copilot. |
| **IncidentPilot copilot (new)** | Collects evidence, finds the suspect deploy with deterministic code, writes a cited report (LLM or template), and asks a human to approve or reject a rollback. Approval triggers a Jenkins rollback job. Everything is audited. |

## 2. Architecture

```
browser ──► FastAPI ──► parse ──► chunk ──► [topic? hybrid search + rerank]
                                              │
                                              ▼
                         Ollama (llama3) ◄── generator ──► validator (schema + grounding)
                                              │
                         no valid questions / LLM down?
                                              ▼
                         SHA-256 keyed demo cache (only for the exact demo file)
```

Quiz responses always carry `source: "live"` or `source: "cached"`, and the UI shows a badge.

The delivery and incident loop around it:

```
 GitHub ──poll──► Jenkins (native, :8080)
                    │ lint → tests(≥80%) → quality gate → copilot tests → build → Trivy → push → deploy → smoke test
                    │                                                                         │
                    │                                              Record deploy ─────────────┼──► POST /deploys
                    ▼                                                                         ▼
        docker compose (quizitout) ──► app :8000 ──/metrics──► Prometheus :9090 ──alert──► Alertmanager :9093
                                         ▲   │                                                  │ webhook
                              loadgen ───┘   └─/internal/recent-errors──────┐                   ▼
                                                                            └────────────► COPILOT :8001
                                                  Ollama (host) ◄── narrative only ──────────────┤ evidence → culprit → report
                                                                                                  ▼
                                                                                          Approval page (human)
                                                                                                  │ approve + reason
                                            Jenkins job quizitout-rollback ◄── buildWithParameters┘
                                                   │ deploy old SHA → smoke test → callback
```

## 3. Tech stack

| Layer | Tools |
|---|---|
| API / UI | FastAPI, Pydantic v2, one static HTML page (no build step) |
| Parsing | pypdf, python-docx, python-pptx |
| Retrieval (topic mode) | sentence-transformers (all-MiniLM-L6-v2), FAISS, BM25, RRF, cross-encoder reranker |
| LLM | Ollama (llama3) over HTTP |
| Monitoring | prometheus_client, Prometheus, Alertmanager |
| Copilot | FastAPI, Jinja2, SQLite, httpx |
| Tests | pytest, pytest-cov, ruff |
| Delivery | Docker (multi-stage), Docker Compose, Jenkins, Trivy, Docker Hub |

## 4. Pipeline stages (road in)

| # | Stage | Fails the build when |
|---|---|---|
| 1 | Checkout (tag = short git SHA) | repo or branch wrong |
| 2 | Build test image | build error |
| 3 | Lint (ruff) | any lint error |
| 4 | Unit + API tests | a test fails or coverage < 80% |
| 5 | Retrieval quality gate | hit-rate@3 < 0.8 |
| 6 | Copilot lint + tests (new) | lint, test, coverage or replay-gate failure |
| 7 | Build runtime image (non-root, `GIT_SHA` build arg) | build error |
| 8 | Trivy scan (app) | fixable HIGH/CRITICAL CVE |
| 9 | Copilot Trivy (new) | fixable HIGH/CRITICAL CVE (image is scanned, never pushed) |
| 10 | Push `:sha` and `:latest` to Docker Hub | bad credentials |
| 11 | Deploy with compose at that exact SHA | compose error |
| 12 | Smoke test (container healthy + `/api/quiz/demo`) | unhealthy or non-200 |
| 13 | Record deploy in the copilot (new) | never fails the build, prints a warning |

On failure after deploy, the pipeline redeploys the last good SHA automatically (`$JENKINS_HOME/quizitout_last_good`) and tells the copilot. A separate job, `quizitout-rollback` (`Jenkinsfile.rollback`), performs rollbacks approved by a human.

## 5. Start the project

### What you need installed (one time)
- **Docker Desktop**: running (whale icon in the menu bar)
- **Ollama** with the model: `ollama pull llama3` (~5 GB, one time)
- **Git**

Every time, first make sure **Docker Desktop** and **Ollama** are running
(the Ollama app open, or `ollama serve` in a terminal).

### Option A: run the image Jenkins already built (fastest, ~1 min)
```bash
git clone https://github.com/shweta1275/QuizItOut.git
cd QuizItOut
docker compose -p quizitout up -d          # pulls shwetak1275/quizitout:latest from Docker Hub
```
Open **http://localhost:8000**. Check: `curl localhost:8000/health` → `{"status":"ok","version":"<git sha>"}`.
Stop it with `docker compose -p quizitout down`.

To run one exact version (any git short SHA listed on Docker Hub):
```bash
IMAGE_TAG=<sha> docker compose -p quizitout up -d
```

### Option B: build the image yourself (first build ~15–30 min, then cached)
```bash
docker build --target test -t quizitout:test .
docker run --rm quizitout:test                        # tests + coverage gate
docker run --rm quizitout:test python -m scripts.quality_gate
docker build --target runtime --build-arg GIT_SHA=dev -t quizitout:dev .
IMAGE=quizitout IMAGE_TAG=dev docker compose -p quizitout up -d
```

### Option C: without Docker (for editing code)
```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
uvicorn app.main:app --reload            # http://localhost:8000
ruff check app tests scripts             # lint
pytest --cov=app --cov-fail-under=80     # tests
python -m scripts.quality_gate           # retrieval gate
```
Stop any Docker copy first (`docker compose -p quizitout down`); both use port 8000.
The copilot's tests run separately: `cd ops/copilot && pytest --cov=app --cov-fail-under=80`.

### Ops stack (monitoring + copilot)
```bash
cp ops/.env.example ops/.env        # then fill JENKINS_USER and JENKINS_TOKEN (see docs/SETUP_INCIDENTPILOT.md)
docker compose -f ops/docker-compose.yml --env-file ops/.env up -d --build
```
Run it from the **host** terminal (it uses relative bind mounts), never from a Jenkins step.

| URL | What |
|---|---|
| http://localhost:8000 | QuizItOut app |
| http://localhost:8080 | Jenkins |
| http://localhost:9090 | Prometheus (Status → Targets, Alerts, Graph) |
| http://localhost:9093 | Alertmanager |
| http://localhost:8001 | Copilot (incident list and approval page) |

Full click-by-click setup (Jenkins branch, API token, rollback job) is in `docs/SETUP_INCIDENTPILOT.md`. The demo is in `docs/DEMO_SCRIPT.md`.

### Using the app
1. Drop a PDF / DOCX / PPTX / TXT / MD file, optionally type a topic, click **Make quiz**
   (a local LLM takes about a minute).
2. Answer one card at a time (keys 1–4 / A–D, ← →). After each answer you see the evidence
   sentence from your document. At the end, you get a score with review and retry.
3. Badge: **generated live** = made by the LLM just now. **cached** = the pre-generated,
   hand-reviewed quiz for `data/demo/demo_doc.pdf`. If the LLM is down or returns no valid
   questions, **uploading that exact PDF** still gives a quiz (matched by its SHA-256 fingerprint).
   Any other file gets a clear error instead. **For a live demo, always upload `demo_doc.pdf`.**

### The CI/CD pipeline (Jenkins)
This project uses a Jenkins at **http://localhost:8080** (installed with Homebrew:
`brew services start jenkins-lts`). Job `quizitout` → *Pipeline script from SCM* → this repo,
branch `*/main` (`*/incidentpilot` while that branch is being built), Poll SCM `H/2 * * * *`,
credential `dockerhub` (Docker Hub access token).
After that, **every `git push` to that branch builds, tests, scans and deploys automatically.**
Full click-by-click setup: `docs/PROJECT_EXPLANATION.md`, section 6, and `docs/SETUP_INCIDENTPILOT.md`.

### After a laptop restart
Open Docker Desktop and Ollama. Jenkins (Homebrew service) and the app container
(`restart: unless-stopped`) come back by themselves. The ops containers also restart on their own;
if not, rerun the `docker compose -f ops/docker-compose.yml ...` command above.

### Optional: a temporary public link for a demo
The app runs on your laptop (the LLM needs it), so it isn't hosted anywhere. To show it to
someone remotely for a while:
```bash
brew install cloudflared
cloudflared tunnel --url http://localhost:8000     # prints a https://….trycloudflare.com link
```
The link works only while this command and your laptop are running. There is no login on the
app, so share it only briefly. **Why not Vercel?** Vercel runs short serverless functions:
it can't run Ollama, its Python functions are limited to ~250 MB (our image is several GB
with torch and the models) and requests time out long before a one-minute quiz generation
finishes. It would also bypass the Jenkins → Docker deploy that this project is about.

## 6. Configuration (environment variables)

### The app

| Variable | Default | Meaning |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` (compose: `http://host.docker.internal:11434`) | Where Ollama runs |
| `OLLAMA_MODEL` | `llama3` | Model name |
| `MAX_QUESTIONS` | `5` | Questions per quiz |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `800` / `100` | Chunking, in characters |
| `LLM_TIMEOUT` | `120` | Seconds per LLM call |
| `MAX_UPLOAD_MB` | `10` | Upload size limit |
| `PREFER_CACHE` | `false` | Serve the demo cache first for the demo file |
| `APP_VERSION` | `dev` | Release identity (set from the `GIT_SHA` build arg); shown in `/health` and the `version` metric label |
| `ENABLE_DIAG` | `false` (compose: `true`) | Turns on `GET /internal/recent-errors` (lab only, **no authentication**) |
| `ENABLE_CHAOS` | `false` (compose: `true`) | Turns on `POST /admin/chaos` (lab only, **no authentication**) |

### The copilot (`ops/.env`, template in `ops/.env.example`)

`PROMETHEUS_URL`, `APP_URL`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `LLM_TIMEOUT` (60), `JENKINS_URL`, `JENKINS_USER`, `JENKINS_TOKEN`, `JENKINS_ROLLBACK_JOB`, `DB_PATH`, `ENABLE_REPLAY`. `ops/.env` is gitignored.

## 7. Monitoring, explained

**How the app is monitored.** The app counts every request in `http_requests_total{method,path,status,version}`. `path` is the route template (`/api/quiz/sample`), not the raw URL, so the number of label combinations stays small; unmatched URLs are labelled `other`. `version` is the git SHA the image was built from, so a graph can show which release produced the errors. Requests to `/metrics` are not counted.

**Prometheus** (`ops/prometheus/prometheus.yml`) scrapes `host.docker.internal:8000/metrics` every 5 seconds and evaluates rules every 5 seconds. It runs in Docker and the app is published on the host's port 8000, so it reaches the app through `host.docker.internal`.

**The alert rule** (`ops/prometheus/alert_rules.yml`) is:

```
(sum(rate(http_requests_total{status=~"5.."}[1m])) or vector(0))
  / sum(rate(http_requests_total[1m])) > 0.05      for 1m
```

Read it as: "over the last minute, more than 5% of requests returned 5xx, and it stayed true for a full minute". `rate(...[1m])` turns the ever-growing counter into requests per second. `or vector(0)` makes the numerator 0 when no 5xx series exists yet, so the baseline reads 0 and not "no data". `for: 1m` stops a single bad second from paging anyone. Note that 502/503 (for example an Ollama outage) are 5xx too and count, which is correct: that is an incident.

**Alertmanager** (`ops/alertmanager/alertmanager.yml`) receives firing and resolved alerts from Prometheus, groups them by alert name (`group_wait: 5s` so the copilot hears quickly), and sends them as a webhook to `http://copilot:8001/alert`. In a real team this receiver would be Slack or PagerDuty. Here the receiver is the copilot.

**Load generator.** A small container sends 5 requests per second to `GET /api/quiz/sample`, and 40% of those omit the optional `count` parameter. The real upload endpoint takes about a minute per request because it calls the LLM, so it cannot be load-tested this way. The sample endpoint is a cheap, LLM-free stand-in.

## 8. How the copilot decides

1. **Evidence bundle.** E1 error ratio, E2 request rate before and after onset (Prometheus). E3 recent error records (exception type, file, line) from the app. E4 the last five deploys (SHA, time, commit message, files changed).
2. **Onset.** First time the error ratio stays clearly above its quiet baseline (+5 percentage points for three samples in a row). If there is no quiet baseline, `alert_start - 60 s`.
3. **Suspect.** The newest deploy before onset (within the last hour) that changed a file named in the errors. If none overlaps, the newest deploy. If there is no deploy, no suspect.
4. **Confidence.** High: file overlap and the deploy was within 15 minutes of onset. Medium: no overlap but within 5 minutes. Otherwise low.
5. **Action.** `rollback_previous` only when confidence is high or medium and a previous good deploy exists (not failed, not marked bad). Otherwise `no_action`. This is plain code. **The LLM never chooses the action.**
6. **Report.** The incident page is created immediately with a deterministic template report. In the background an LLM (llama3 via Ollama) may phrase a better one. Every claim must cite evidence IDs, quoted log text must appear verbatim in E3, and any SHA must exist in E4. If validation fails twice, or Ollama is down, the template stays and the page says which one you are reading.
7. **Human decision.** The page shows the suspect, confidence, proposed action, evidence behind each claim, and an alternative explanation. Approving or rejecting needs a written reason of at least 15 characters. A decision made less than 10 seconds after first opening the page must be confirmed. Everything lands in the audit table.

## 9. Limitations (read before trusting anything here)

- **Traffic and failures are simulated.** A load generator creates traffic, a patch injects the bad release, and a chaos switch creates a second failure.
- **The bad release passes CI on purpose.** The tests for the sample endpoint always send the optional `count` parameter, so the tests never see the missing-parameter case. This reproduces a real failure type (unrepresentative test data); it is not a claim that the test suite is poor in general.
- **The suspect is a guess based on timing and file overlap.** Correlation is not causation, which is exactly why a human approves.
- **The replay gate tests the deterministic analyzer and the report validator.** It does not measure LLM quality. Numbers written in LLM prose are not machine-checked.
- **`/internal/recent-errors` and `/admin/chaos` have no authentication.** They are lab-only switches enabled in compose. The copilot UI also has no login.
- **Single machine.** Jenkins, the app, monitoring and "production" all run on one laptop. No staging, no zero-downtime deploy.
- **The upload path is not load-tested** (LLM-bound).
- **A rollback job and a main build can run at the same time.** Each job serialises itself, but they do not lock each other.
- Not production-grade. Missing: multi-environment promotion, secrets manager, high availability, long-term metrics storage, authentication.
- **Scanned PDFs** (images) have no text layer; they are rejected with a clear error. No OCR.
- **LLM accuracy:** the grounding check proves the evidence sentence exists in the document, not that `answer_index` points at the right option. The demo cache is therefore reviewed by hand.
- Jenkins uses the host Docker socket (lab-only trade-off). The local LLM is slow: about 10–30 s per question on a laptop.

The original QuizItOut loopholes are listed in `docs/PROJECT_EXPLANATION.md`, section 4; the new ones in `docs/EXPLANATION_INCIDENTPILOT.md`, section 8.

## 10. Repository layout

```
app/                    QuizItOut FastAPI app (metrics.py, diag.py, selection.py, chaos.py are new)
tests/                  app tests
data/demo/              demo PDF and the hand-reviewed demo quiz
ops/
  docker-compose.yml    monitoring + copilot (project name: incidentpilot)
  prometheus/ alertmanager/ loadgen/ copilot/
scripts/                inject_bug / revert_bug / harmless_change / chaos_on / chaos_off / fake_alert / verify_patch
Jenkinsfile             main pipeline
Jenkinsfile.rollback    human-approved rollback job
docs/                   setup, explanation, demo script, design
```

## 11. Test and gate results

Run on the dev machine (Python 3.11 venv). Docker, Jenkins and Ollama were not running during these runs, so the image-based checks are still open.

| Check | Result |
|---|---|
| App lint (`ruff check app tests scripts`) | All checks passed |
| App tests + coverage | 59 passed, coverage 99.41% (baseline before the change: 38 passed, 99.19%) |
| Retrieval quality gate | hit-rate@3 = 1.00 (threshold 0.8) |
| Copilot lint, tests, coverage (`ops/copilot`) | ruff clean; 81 passed, coverage 99.11% |
| Replay gate (8 recorded incidents) | 8/8 match the expected suspect, confidence and action |
| `scripts/verify_patch.sh` (bad release passes CI, fails at runtime) | all checks PASS (A to G) |
| Compose files (`docker compose config`) | both valid |
| Docker image builds, Trivy (app and copilot) | TBD (fill after run) |
| Jenkins build on the new stages | TBD (fill after run) |
| Prometheus rule loads, alert fires and resolves | TBD (fill after run) |
| End-to-end demo run | TBD (fill after run) |

## 12. Future work

Webhook instead of Poll SCM, authentication on the copilot and diagnostics endpoints, staging environment with promotion, canary releases with automatic judging, pinned dependency versions, a Grafana dashboard, OCR for scanned PDFs, a second LLM or NLI pass to check quiz answer correctness, Kubernetes with readiness probes, and a real chat/pager receiver in Alertmanager.

## 13. Docs

- `docs/PLAN.txt` – the original mentor plan
- `docs/PROJECT_EXPLANATION.md` – QuizItOut build log, design decisions, loopholes and interview Q&A
- `docs/EXPLANATION_INCIDENTPILOT.md` – the IncidentPilot build log: decisions, monitoring setup, results, loopholes, viva questions
- `docs/IncidentPilot_DESIGN.md` – the copilot specification
- `docs/SETUP_INCIDENTPILOT.md` – click-by-click setup for the new parts (branch, API token, rollback job, ops stack)
- `docs/SETUP_AND_DEMO.md` – the original human-side setup checklist (GitHub, Docker Hub, Jenkins)
- `docs/DEMO_SCRIPT.md` – the three-person demo script
- `docs/CHANGES.md` – the change specification this work followed

## 14. Resume line

*Built QuizItOut, a document-to-quiz app on a local LLM, delivered through a Jenkins CI/CD pipeline (80% coverage gate, retrieval quality gate, Trivy scanning, SHA-tagged Docker images), and extended it with an evidence-grounded incident copilot: Prometheus and Alertmanager alerting, deterministic deploy correlation, LLM reports validated against source evidence, and human-approved rollback with an audit trail.*

Use this line only after the demo has run end to end on the real stack.
