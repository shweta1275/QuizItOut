# QuizItOut: Project Explanation (Build Log + Decisions)

This file was written while the project was being built. It follows the build phases from
`docs/PLAN.txt` and records **what** was built, **why**, and **where the plan was changed
(and why)**. The last sections cover the known loopholes and the questions an interviewer or
resume screener is likely to ask, with short answers.

> **What do I still have to do?** Jump to **section 6**: a step-by-step checklist (GitHub →
> Docker Hub → Jenkins → demo), written for someone who has never used these tools.

---

## 0. The project in one paragraph

QuizItOut is a web app: you upload a PDF / DOCX / PPTX / TXT / MD file, the app extracts the
text, cuts it into chunks, asks a **local LLM (Ollama + llama3)** to write one multiple-choice
question per chunk, **validates** every question (schema + "is the evidence really in the
document?"), and shows the quiz in the browser. Around the app is a **Jenkins CI/CD pipeline**:
lint → tests with an 80% coverage gate → retrieval quality gate → build a non-root runtime
image → Trivy vulnerability scan → push to Docker Hub with a git-SHA tag → deploy with
docker compose → smoke test → automatic rollback to the last good SHA on failure.

Two separate "worlds":

```
APP (upload → quiz)                                   PIPELINE (git push → running app)

 browser ──upload──► FastAPI /api/quiz                 GitHub ──poll──► Jenkins
                      │                                                  │
                      ├─ parsers.py   file → text                        ├─ Checkout (TAG = git SHA)
                      ├─ chunker.py   text → chunks                      ├─ Build test image
                      │    └─ topic? retriever.py (BM25+FAISS+RRF+rerank)├─ Lint (ruff)
                      ├─ generator.py chunk → LLM → MCQ (retry)          ├─ Tests + coverage ≥ 80%
                      │    └─ llm.py  (ONLY network call, Ollama)        ├─ Quality gate (hit-rate@3 ≥ 0.8)
                      ├─ validator.py schema + grounding                 ├─ Build runtime image (non-root)
                      └─ fallback.py  SHA-256 keyed demo cache           ├─ Trivy (HIGH/CRITICAL fixable)
                                                                         ├─ Push :sha and :latest
 response: { source: "live" | "cached", questions: [...] }               ├─ Deploy (compose, IMAGE_TAG=sha)
                                                                         ├─ Smoke test (healthy + /api/quiz/demo)
                                                                         └─ post: rollback on failure
```

---

## 1. Phase-by-phase build log

### Phase 0: Preflight
Tools found on the Mac: git, Docker 29 + Compose v5, Python 3.11 (in `.venv`), Ollama 0.21
with `llama3` pulled. Trivy is **not** installed locally on purpose: the pipeline runs it as
the `aquasec/trivy` container, so the laptop doesn't need it.

**Biggest time cost of the whole project: downloads, not code.** torch (~130 MB on Mac, more
inside the Linux image), the two Hugging Face models and the Jenkins base image (~270 MB) on a
slow connection took far longer than writing or testing anything. Lesson: the Dockerfile puts
these heavy steps in early layers so they are downloaded **once** and cached.

### Phase 1: Skeleton (`config.py`, `schemas.py`, requirements, ignore files)
- **One settings object read from env vars** (`app/config.py`). 12-factor idea: the same image
  behaves differently in dev / Docker / Jenkins without code changes. `frozen=True` so nothing
  mutates settings at runtime (tests use `dataclasses.replace` to make a modified copy).
- **Pydantic models are the contract** (`app/schemas.py`). `MCQ` rejects anything that is not
  exactly 4 distinct options with `answer_index` 0–3. The same model validates the LLM's output
  *and* shapes the API response, so the two can never drift apart.
- `QuizResponse.source` = `"live"` or `"cached"`, so the client always knows where a quiz came from.

### Phase 2: Parsers + chunker
- `parsers.py`: a dict maps extension → function (`PARSERS`). Adding a format = one function +
  one entry. Empty text raises a clear error ("scanned PDF?") instead of sending nothing to the LLM.
- `chunker.py`: ~800-char chunks on paragraph boundaries with 100-char overlap, so an idea split
  across a boundary still appears whole in one chunk. Giant paragraphs are hard-cut.
- `pick_spread`: **quiz generation is not retrieval.** There is no question to search for; we
  want coverage of the whole document, so we pick chunks evenly spaced through it.
- DOCX/PPTX test files are created inside the tests, so no binary fixtures are committed. The
  demo PDF is parsed in a test too, which guarantees the demo file always works.

### Phase 3: LLM layer
- `llm.py` is the **only** file that makes a network call. Two failure types are kept separate:
  Ollama unreachable → `LLMUnavailable` (fallback path), model returned bad JSON → `{}` (the
  validator rejects it, generator retries).
- `validator.py`: schema check (Pydantic) + **grounding check**: the LLM must copy an exact
  sentence (`source_snippet`) that proves the answer, and we check it really is in the chunk
  (case/whitespace-insensitive).
- `generator.py` takes the client as an argument (**dependency injection**). That is why tests
  can pass a `FakeLLM` and never touch a real model.

### Phase 4: API + UI + demo cache
- `main.py` is thin wiring: validate upload → (optional cache shortcut) → parse → chunk →
  (optional topic search) → generate → fallback. Status codes: 400 bad type, 413 too large,
  422 no text, 503 LLM down, 502 LLM gave only garbage.
- `fallback.py`: the demo cache is keyed by the **SHA-256 of the uploaded bytes**. It is only
  served for the exact demo file, never for any other document, and every response says
  `source: "cached"`.
- `index.html`: all LLM text goes in via `textContent`, never `innerHTML` (LLM output is
  untrusted → XSS risk). Redesigned after the first version: a dark landing page with
  drag-and-drop upload, then **flashcard mode** with one question per card, a progress bar,
  Previous/Next, the evidence sentence revealed after answering, keyboard shortcuts
  (1–4 / A–D, ← →) and a results screen (score ring, review, retry). Still one static file with
  no framework and no build step, so the Docker image and pipeline didn't change.
- **Demo cache review (done for real):** the first run of `build_demo_cache` produced 8
  questions, the validator kept 4, and on review only **2 of those 4 were actually correct**.
  One had four true statements as options; one was nonsense. Both passed the grounding check.
  This is the plan's "honest limitation" happening live: grounding proves the quote is real,
  not that the answer is right. After the prompt change below, a second run gave 6, of which
  3 were correct. The final `demo_quiz.json` holds **5 hand-reviewed questions**, each
  re-verified against the schema and the PDF text.
- **Demo-day safety net = upload the fixed PDF, not a button.** The first UI had a "demo quiz"
  button, which made no sense in a live demo ("the real thing failed, so here's a canned one").
  It was removed; the fallback now only appears through the normal upload of
  `data/demo/demo_doc.pdf`. Verified with the Docker Hub image and the LLM deliberately pointed
  at a dead address: the demo PDF → 200 `source: cached`, 5 questions; any other file → 503.
  `GET /api/quiz/demo` still exists for Jenkins' smoke test.
- Live check with real Ollama: uploading the demo PDF returned `source: live` with 3 questions
  (2 of 5 chunks rejected by the validator) in about a minute.

### Phase 5: Retriever (topic mode) + quality gate
- Hybrid search: **dense** (MiniLM embeddings in FAISS, catches meaning) + **sparse** (BM25,
  catches exact terms) fused with **RRF** (uses ranks, not scores, because the two score scales
  are incomparable), then a **cross-encoder rerank** of the shortlist (slow but accurate, so
  only run on ~15 candidates).
- Models are lazy-loaded so app startup and non-retrieval tests stay fast.
- Quality gate: 8 golden questions over `tests/golden/notes.txt` (OS + networking notes). The
  gate fails the build if hit-rate@3 < 0.8. **Result: 1.00 (8/8).**

### Phase 6: Docker
- Multi-stage Dockerfile: `base` (deps + baked models) → `test` (adds pytest/ruff/tests, never
  shipped) → `runtime` (non-root `appuser`, HEALTHCHECK).
- CPU-only torch is installed first, otherwise sentence-transformers pulls the multi-GB CUDA build.
- Models are downloaded at build time into `/opt/hf` and made readable, so the non-root user can
  load them and the container starts without network.
- `docker-compose.yml` reads `IMAGE` / `IMAGE_TAG` from env so Jenkins can deploy an exact SHA
  and roll back to an older one. The app talks to the Mac's native Ollama via
  `host.docker.internal` (Ollama in Docker on a Mac is CPU-only and much slower).

### Phase 7: Jenkins
- Jenkins runs in a container with the host Docker socket mounted (**Docker-out-of-Docker**).
  Pipeline containers run as siblings on the host, not inside Jenkins.
- Lint, tests and the quality gate run **inside the test image** rather than mounting the
  workspace, because `$PWD` inside the Jenkins container doesn't exist on the host.
- The Jenkinsfile was written in full (all 10 stages + rollback) rather than added one stage
  per push as the plan suggests, to save time. If a stage fails on the first Jenkins run, that
  stage is the only thing to debug, since every stage was already run locally.
- Rollback: on success the SHA is written to `$JENKINS_HOME/quizitout_last_good`; on failure
  `post { failure }` redeploys that SHA.

### Phase 8: Docs
`README.md` (summary, diagram, run steps, pipeline table, limitations, future work),
`docs/SETUP_AND_DEMO.md` (your GitHub / Docker Hub / Jenkins clicks + demo script) and this file.

---

## 2. Where the build differs from the plan (and why)

| Change | Why |
|---|---|
| Docker Hub user `shwetak1275` (plan had `shweta1275`) | That is the real Docker Hub account. |
| `make_quiz(file: Annotated[UploadFile, File()], ...)` instead of `File(...)` as a default | Ruff rule B008 flagged function calls in defaults. `Annotated` is FastAPI's current recommended style; same behaviour. |
| Dockerfile: `apt-get upgrade -y` in the base stage | Trivy's first scan found a **fixable HIGH CVE in libpcre2** (OS package in `python:3.11-slim`). Upgrading patches it instead of ignoring it. |
| Dockerfile: `pip install --upgrade pip setuptools wheel` first | Trivy found HIGH CVEs in **`wheel` 0.45.1 and `jaraco.context` 5.3.0 vendored inside the old `setuptools`** of the base image. Upgrading the build tooling removes them. No `.trivyignore` was needed. |
| Runtime stage runs `pip uninstall -y pip` | Second Trivy scan flagged setuptools 70.3.0, urllib3 2.7.0 and msgpack 1.1.2, but the image had newer versions installed. Debugging showed Trivy reported them **with no file path**: they came from **`pip/_vendor/bom.cdx.json`, the SBOM of the copies pip vendors inside itself** (already the latest pip, so no upgrade fixes it). I first wrongly tried minimum versions in `requirements.txt` (reverted). Real fix: the app never needs pip at runtime, so the shipped image doesn't have it. Smaller attack surface; the test stage still has pip. |
| BuildKit pip cache mount (`RUN --mount=type=cache,target=/root/.cache/pip`), `PIP_NO_CACHE_DIR` removed | Every requirements change re-downloaded torch (~10 min on a slow link). The cache mount keeps wheels on the build host, **not in the image**, so the image stays small and rebuilds are fast (also for Jenkins, which uses the same host Docker daemon). |
| Uses the existing **Homebrew Jenkins** on the Mac (port 8080) instead of Jenkins-in-Docker; `Jenkinsfile` adds `~/.docker/bin` to `PATH` | It was already installed and set up, which saves the whole setup. Homebrew's launchd service starts Jenkins with `PATH=/usr/bin:/bin:/usr/sbin:/sbin`, so `docker` wasn't found (verified by simulating that environment). Bonus: no Docker socket mount, so the 'socket = root' risk doesn't apply. |
| Push stage uses its own `DOCKER_CONFIG` + `docker logout` | Jenkins now runs as your macOS user, so a plain `docker login` would overwrite Docker Desktop's own login in the keychain. A separate config keeps them apart. First Jenkins run failed at Push: the empty config also dropped Docker's *context*, so the CLI fell back to `/var/run/docker.sock`, which doesn't exist with Docker Desktop on macOS. Fix: export `DOCKER_HOST` from `docker context inspect` before switching config. |
| Stricter generation prompt (one correct option, three clearly false, answer must be supported by the snippet, full sentence) | First real run: 2 of 4 "valid" questions were wrong. The prompt is the cheapest lever; it raised the yield and reduced "all options are true" questions. |
| `build_demo_cache` asks for 12 questions instead of 8 | About half are rejected or wrong, so we need a bigger pool to keep ≥ 5 good ones. |
| `extra_hosts: host.docker.internal:host-gateway` in compose | Docker Desktop resolves it anyway; this makes it also work on Linux hosts. |
| Trivy `--timeout 15m` | Torch makes the image large; the default scan timeout can expire on the first run. |
| Extra tests (413, 422, 502, PREFER_CACHE, demo 404, index page, `test_llm.py`) | Cover every status code and fallback branch → 99% coverage instead of just scraping 80%. |
| Quality gate prints HIT/MISS per query | When the gate fails in Jenkins you can see *which* query broke. |
| `.dockerignore` also excludes `docs/` and `jenkins/` | Smaller build context; neither is needed in the image. |

---

## 3. Verified results (real output, Oct 3 2026)

| Check | Result |
|---|---|
| `ruff check app tests scripts` | All checks passed |
| `pytest --cov=app --cov-fail-under=80` | 38 passed, coverage **99%** |
| `python -m scripts.quality_gate` | hit-rate@3 = **1.00** (8/8) |
| Live API + real Ollama, demo PDF | 200, `source: live`, 3 questions |
| Live API, topic mode | 200, `source: live`, 4 questions |
| Trivy, first scan | 3 HIGH (fixable): libpcre2, `wheel`/`jaraco.context` in old setuptools → fixed (see §2) |
| Trivy, second scan | 4 HIGH: pip's vendored urllib3 ×2, msgpack, setuptools → pip removed from runtime image |
| Trivy, final scan | **exit code 0** (no fixable HIGH/CRITICAL), no `.trivyignore` needed |
| `docker compose up` (runtime image) | container `healthy`, runs as `appuser`, `/health` 200, `/api/quiz/demo` 200 |
| Live quiz from inside the container → host Ollama | 200, `source: live`, 4 questions |
| Jenkins build #1 (Oct 4) | Lint, tests, gate, runtime build, Trivy (0 vulns) green; **failed at Push** (Docker context, see §2) → nothing deployed |
| Jenkins build #2 | **SUCCESS, all 10 stages**, triggered automatically by the push (Poll SCM). Docker Hub has `:b455a1e` + `:latest`; compose deployed `b455a1e`, container healthy; last-good file = `b455a1e` |

---

## 4. Loopholes (be ready to say these yourself)

1. **Grounding ≠ correctness.** The validator proves the evidence sentence exists in the
   document. It does not prove `answer_index` points at the right option. Seen live: 2 of 4
   "valid" questions were wrong. The demo cache is hand-reviewed for exactly this reason. Fix
   idea: a second LLM/NLI pass that checks the snippet entails the chosen option.
2. **Live generation often returns fewer questions than asked** (3 of 5 in the real test),
   because rejected chunks are retried only once and then skipped. There is no "top up from
   other chunks".
3. **Topic mode is weak on short documents.** We retrieve the top `MAX_QUESTIONS` chunks; if
   the document only has ~5 chunks, that is the whole document, so "deadlock" also produced
   DNS questions. There is no relevance threshold.
4. **Quality gate is small and self-written.** 8 queries on a 1-page doc written by us, so
   1.00 is easy. It catches regressions, not real-world retrieval quality.
5. **Coverage ≠ test quality.** 99% means lines ran, not that every behaviour is asserted.
6. **The LLM is never tested in CI** (by design: slow, non-deterministic). A prompt change can
   silently make real output worse and CI will stay green.
7. **Same machine for Jenkins, registry client and "production".** Deploy = `docker compose up`
   on the laptop. No staging, no separate server, no zero-downtime deploy (the container is
   replaced, so there are a few seconds of downtime).
8. **Rollback only covers what the smoke test checks:** health + demo endpoint. A bug in the
   upload path or in Ollama connectivity would pass the smoke test and not roll back.
9. **Rollback state is a text file in `JENKINS_HOME`.** Lose the volume and you lose the last good SHA.
10. **Docker socket mounted + Jenkins as root** = whoever controls Jenkins controls the host.
    Acceptable in a local lab, never in production.
11. **`:latest` tags** for `aquasec/trivy`, `ollama/ollama` and unpinned Python requirements
    mean builds are not fully reproducible. The `apt-get upgrade` also makes the image depend
    on build day.
12. **No auth, no rate limiting, no monitoring.** Anyone who can reach port 8000 can make the
    laptop run LLM calls. Uploads are size-checked but parsers (pypdf, python-docx) still run
    on untrusted files.
13. **Synchronous request.** Generation takes ~1 minute and blocks a worker; no job queue, no
    streaming progress. A timeout from a proxy would kill the request.
14. **Scanned PDFs are rejected** (no OCR). Text extracted from PDFs can contain artifacts
    (e.g. `syste m`), which is why grounding normalises whitespace but can still miss.
15. **Poll SCM every 2 minutes** instead of a webhook (no public URL), so builds start with a delay.

---

## 5. Interview / resume questions you should expect

**Resume line (honest):** *"Built QuizItOut, a document-to-quiz app using a local LLM with
schema + grounding validation, delivered through a Jenkins CI/CD pipeline with automated tests
(99% coverage, 80% gate), a retrieval quality gate, Trivy vulnerability scanning, SHA-tagged
Docker images and automated rollback."* Do **not** write "production-grade".

### DevOps / pipeline
- **Walk me through what happens when you push.** Poll SCM picks it up → test image built →
  ruff → pytest with coverage gate → retrieval gate → runtime image tagged with the git SHA →
  Trivy → push `:sha` and `:latest` → compose deploys that SHA → smoke test → on failure,
  redeploy the last good SHA.
- **Why tag by git SHA, not `latest`?** `latest` moves. A SHA maps an image to an exact commit
  and makes rollback exact.
- **How does rollback work? What doesn't it catch?** Last good SHA stored in a file; failure
  redeploys it. It only catches failures the smoke test can see (health + demo endpoint). See loophole 8.
- **Why a multi-stage Dockerfile?** Test tools stay out of the shipped image, the image is
  smaller, Trivy scans exactly what ships, and tests run on the same base layers.
- **How does layer caching help here?** Requirements are copied and installed before the code,
  so a code change doesn't reinstall torch.
- **What did Trivy actually find and what did you do?** A libpcre2 OS CVE and `wheel` /
  `jaraco.context` inside the base image's old setuptools. Fixed with `apt-get upgrade` and
  upgrading pip/setuptools/wheel, not by ignoring them.
- **You upgraded the package but Trivy still flagged it. Why?** The flagged copies weren't the
  installed packages, they were the copies **vendored inside pip**, which Trivy found through pip's
  embedded SBOM (`bom.cdx.json`). Clue: the findings had no file path. Fix: remove pip from the
  runtime image, since the running app never needs it.
- **Why not just add the CVEs to `.trivyignore`?** Ignoring is for findings you truly can't fix
  (no patch, or not reachable), each with a written reason. All of these had fixes.
- **What is Docker-out-of-Docker and what is the risk?** Jenkins uses the host's Docker daemon
  through the mounted socket. Socket access ≈ root on the host.
- **Why not mount the workspace into test containers?** The path inside Jenkins doesn't exist
  on the host daemon; tests are baked into the test image instead.
- **How are secrets handled?** Docker Hub access token in the Jenkins credentials store,
  injected with `credentials()`, masked in logs, single-quoted shell so Groovy doesn't
  interpolate it. Never in the repo.
- **Is this production-ready? What would you add?** No. Staging + manual approval,
  Prometheus/Grafana, a real server or Kubernetes with readiness probes, IaC (Terraform),
  secrets manager, auth + rate limiting, pinned dependency versions, webhooks.
- **Why Jenkins and not GitHub Actions?** Course requirement + self-hosted (it can reach the
  local Docker daemon and Ollama). Honest trade-off: Actions is simpler to maintain.
- **Difference between CI and CD here?** CI = every push is built, linted, tested and gated.
  CD = a passing build is automatically deployed and smoke-tested.

### App / AI
- **Why not just trust the LLM's JSON?** LLM output is untrusted input: wrong keys, 3 options,
  index 9, hallucinated quotes. Pydantic + grounding catch format and fake evidence.
- **What does grounding prove? What doesn't it prove?** Real quote, yes. Correct answer, no.
  Have the live example ready (2 of 4 valid questions were wrong).
- **Isn't the cache cheating?** No: generated by the real pipeline, hand-reviewed, keyed by the
  file's SHA-256, served only for that file, and labelled `cached` in the API and UI.
- **Why isn't quiz generation RAG?** There is no question to retrieve for; we need coverage, so
  chunks are sampled evenly. Retrieval is only used in topic mode.
- **Why hybrid search + RRF + reranker?** Dense catches meaning, BM25 catches exact terms; RRF
  merges by rank because the scores aren't comparable; the cross-encoder is accurate but slow,
  so it only reranks a shortlist.
- **How do you test code that depends on an LLM?** Dependency injection: the generator takes a
  client, tests pass `FakeLLM` / `DownLLM`. No network in tests.
- **How would you measure quiz quality, not just retrieval?** A labelled set of
  (chunk, good question) pairs, plus an automatic answer check (NLI or a second LLM pass)
  reported as an accuracy number in CI.
- **What happens when Ollama is down?** `LLMUnavailable` → demo cache if the SHA matches → else
  503 with a clear message.
- **XSS?** All model text is rendered with `textContent`.

### Tricky "gotcha" questions
- *"Your coverage is 99%, so your code is bug-free?"* No. Coverage counts executed lines, not
  correct assertions; the LLM's real behaviour isn't covered at all.
- *"Your quality gate scores 1.00. Isn't that suspicious?"* Yes, it's a small, self-written set;
  it's a regression tripwire, not a benchmark.
- *"Why didn't you deploy it to Vercel / the cloud?"* The LLM runs locally in Ollama (5 GB model); Vercel only runs short serverless functions with ~250 MB limits and short timeouts, so neither the model nor the torch image fits. A real cloud deploy would need a VM with enough RAM (or a GPU) and the same Docker image. That's future work, and it would also need auth first.
- *"How does a push become a build if nobody clicks anything?"* Jenkins polls GitHub every 2 minutes (Poll SCM); a new commit on `main` starts the pipeline. A webhook would be instant but needs a public URL.
- *"Did your pipeline work first time?"* No. Build #1 passed lint, tests, gate and Trivy, then failed at Push: isolating the Docker login config also dropped Docker's context, so the CLI looked for the wrong socket. I found it from the console log and pinned `DOCKER_HOST`. Because the pipeline stops at the failed stage, nothing broken got deployed.
- *"What if two builds run at once?"* `disableConcurrentBuilds()` serialises them, so two
  deploys can't race.
- *"What if the very first build fails after deploy?"* There is no last good SHA yet, so
  nothing to roll back to; the pipeline logs that.
- *"Where does the app run in 'production'?"* On the same laptop, via compose. That's the
  honest answer, and why "production-grade" is not on the resume.

---

## 6. YOUR remaining steps (beginner-friendly, do them in order)

Everything inside the code is done and tested. What's left needs **your accounts**
(GitHub, Docker Hub) and **clicking in a browser** (Jenkins). Nobody can do these for you.
Total time: about 1–1.5 hours the first time, mostly waiting.

### 6.0 First, the 5 words you need to know

| Word | What it actually is | In this project |
|---|---|---|
| **Git** | A tool that saves snapshots ("commits") of your code on your laptop. | Already done: 9 commits exist on your laptop. |
| **GitHub** | A website that stores a copy of your Git project online. | You'll upload ("push") the code there. Jenkins downloads it from there. |
| **Docker image** | A sealed box containing the app + Python + all libraries. Runs the same on any machine. | Built from the `Dockerfile`. |
| **Docker Hub** | A website that stores Docker images (like GitHub, but for images). | Jenkins uploads every new image there, tagged with the commit ID. |
| **Jenkins** | A program that watches GitHub and, on every new commit, automatically runs tests → builds → scans → deploys. | Runs on your Mac inside Docker, at http://localhost:8080. The steps it runs are written in `Jenkinsfile`. |

**How to open a terminal:** press `Cmd + Space`, type `Terminal`, press Enter.
Every command below goes into the terminal: paste it and press Enter.
**Before every command block, first go into the project folder:**

```bash
cd "/Users/shwetakarandikar/Documents/cllz stuff/4th year/DevOps/QuizItOut"
```

**Things that must be running the whole time:** Docker Desktop (whale icon in the top menu
bar) and Ollama (llama icon in the menu bar, or run `ollama serve` in a separate terminal).

---

### Step 1: Check the demo quiz answers ✅ DONE (all 5 correct)

Why: this file is shown when the LLM is down. A wrong answer in it would look bad in the demo.

1. Open `data/demo/demo_quiz.json` in VS Code (or any text editor).
2. For each question, look at `options` and `answer_index`. Counting starts at **0**:
   `0` = first option, `1` = second, `2` = third, `3` = fourth.
3. Check that the option at that position is really the correct answer.
4. If one is wrong, tell Claude Code which one, or delete that whole `{ ... }` block (keep at
   least 5 questions).

✅ **Done when:** open http://localhost:8000 → upload `data/demo/demo_doc.pdf` with Ollama quit → every "correct" answer
really is correct.

---

### Step 2: Put the code on GitHub ✅ ALREADY DONE (Oct 4)

The code is at https://github.com/shweta1275/QuizItOut. From now on, uploading new commits is just `git push`.
The steps below are kept for reference only.

**2a. Create an empty repository on the website**
1. Go to https://github.com and log in.
2. Top-right **+** → **New repository**.
3. Repository name: `quizitout`
4. Choose **Public**.
5. Do **NOT** tick "Add a README", ".gitignore" or "license" (the repo must be empty).
6. Click **Create repository**. Leave the page open.

**2b. Install the GitHub login helper (one time)**
```bash
brew install gh
gh auth login
```
`gh auth login` asks questions. Answer with arrow keys + Enter:
- *Where do you use GitHub?* → **GitHub.com**
- *Preferred protocol?* → **HTTPS**
- *Authenticate Git with your GitHub credentials?* → **Yes**
- *How would you like to authenticate?* → **Login with a web browser**
- It shows an 8-character code → press Enter → a browser opens → paste the code → **Authorize**.

**2c. Upload ("push") the code.** Replace `<your-github-username>` with your real GitHub username:
```bash
cd "/Users/shwetakarandikar/Documents/cllz stuff/4th year/DevOps/QuizItOut"
git remote add origin https://github.com/shweta1275/QuizItOut.git
git push -u origin main
```

✅ **Done when:** refresh the GitHub page: you see the folders `app`, `tests`, `docs`… and
the commits ("phase 1 … phase 8") under the commits link.

**2d. (Group project) Add teammates:** repo page → **Settings** → **Collaborators** →
**Add people** → their GitHub usernames.

| If you see | Do this |
|---|---|
| `remote origin already exists` | `git remote set-url origin https://github.com/shweta1275/QuizItOut.git` then push again |
| `Authentication failed` / asks for password | Run `gh auth login` again. GitHub doesn't accept your normal password in the terminal. |
| `rejected … fetch first` | The repo wasn't empty (you ticked README). Delete the repo on GitHub, recreate it empty, push again. |

---

### Step 3: Docker Hub repository + access token ✅ DONE

The token is like a password that only Jenkins uses, so you never give Jenkins your real password.

1. Go to https://hub.docker.com and log in as **shwetak1275**.
2. **Create a repository** → Name: `quizitout` → **Public** → **Create**.
3. Click your profile picture (top-right) → **Account settings** → **Personal access tokens**
   → **Generate new token**.
4. Description: `jenkins` · Access permissions: **Read & Write** → **Generate**.
5. **Copy the token now** (it's shown only once). Paste it into your Notes app or password manager.

⚠️ Never paste this token into the chat, into any project file, or into GitHub.

✅ **Done when:** you have the token saved somewhere and the repo `shwetak1275/quizitout` exists.

---

### Step 4: Start Jenkins (10 min + waiting)

> ✅ **Skip all of Step 4.** This Mac already has Jenkins installed with Homebrew (`jenkins-lts`),
> running at http://localhost:8080 and already set up. We use that one instead of the Docker
> Jenkins below. It runs directly on the Mac, so it uses Docker Desktop directly (no socket
> mounting needed). The only catch, fixed in the `Jenkinsfile`: Homebrew Jenkins starts with a
> minimal PATH that doesn't include Docker (`~/.docker/bin`), so the Jenkinsfile adds it.
> Steps 4a–4e are kept below only as the alternative (Jenkins in Docker).

**4a. Free port 8000.** Claude Code left a test copy of the app running there. Jenkins will deploy
its own copy, so stop this one:
```bash
cd "/Users/shwetakarandikar/Documents/cllz stuff/4th year/DevOps/QuizItOut"
docker compose -p quizitout down
```

**4b. Start the Jenkins container.** The `jenkins-docker` image is already built on your Mac.
```bash
docker run -d --name jenkins -u root -p 8080:8080 \
  -v jenkins_home:/var/jenkins_home \
  -v /var/run/docker.sock:/var/run/docker.sock \
  --restart unless-stopped \
  jenkins-docker
```
What this means: run Jenkins in the background (`-d`), open it on port 8080, keep its data in a
volume called `jenkins_home` (so it survives restarts), and give it access to your Mac's Docker
(`docker.sock`) so it can build images.

**4c. Get the first-time password** (wait ~30 seconds after 4b):
```bash
docker exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword
```
Copy the long string it prints.

**4d. Set up Jenkins in the browser**
1. Open http://localhost:8080
2. Paste the password → **Continue**.
3. Click **Install suggested plugins**. Wait 3–5 minutes until all are green.
4. Create the admin user: pick a username + password you'll remember (this is only for your
   local Jenkins) → **Save and Continue**.
5. Jenkins URL: leave `http://localhost:8080/` → **Save and Finish** → **Start using Jenkins**.

**4e. Check Jenkins can use Docker:**
```bash
docker exec jenkins docker ps
docker exec jenkins docker compose version
```
✅ **Done when:** both print output without "error" (the first shows a table with `jenkins` in it).

| If you see | Do this |
|---|---|
| `permission denied … docker.sock` | `docker rm -f jenkins` and rerun 4b exactly (it needs `-u root`). |
| `Cannot connect to the Docker daemon` inside Jenkins | Docker Desktop → Settings (gear) → **Advanced** → tick **Allow the default Docker socket to be used** → Apply & restart. Then `docker restart jenkins`. |
| `port is already allocated` (8080) | Something else uses 8080. Use `-p 8080:8080` in 4b and open http://localhost:8080 instead. |
| `Conflict. The container name "/jenkins" is already in use` | It's already running. Just open http://localhost:8080 (or `docker start jenkins`). |

---

### Step 5: Give Jenkins your Docker Hub token ✅ DONE

1. In Jenkins: left menu **Manage Jenkins** → **Credentials**.
2. Click **(global)** under "Stores scoped to Jenkins" (or System → Global credentials).
3. **Add Credentials** (top right).
4. Fill in:
   - Kind: **Username with password**
   - Scope: **Global**
   - Username: `shwetak1275`
   - Password: *paste the Docker Hub token from Step 3*
   - ID: `dockerhub` ← exactly this, lowercase. The `Jenkinsfile` looks for this name.
   - Description: `Docker Hub token`
5. **Create**.

✅ **Done when:** the credentials list shows `shwetak1275/****** (Docker Hub token)` with ID `dockerhub`.

---

### Step 6: Create the pipeline job ✅ DONE

1. Jenkins Dashboard → **New Item** (left menu).
2. Name: `quizitout` → select **Pipeline** → **OK**.
3. Scroll to **Triggers** (or "Build Triggers") → tick **Poll SCM** → Schedule: `H/2 * * * *`
   (this means "check GitHub for new commits about every 2 minutes").
4. Scroll to **Pipeline**:
   - Definition: **Pipeline script from SCM**
   - SCM: **Git**
   - Repository URL: `https://github.com/shweta1275/QuizItOut.git`
   - Credentials: leave **- none -** (the repo is public)
   - Branch Specifier: change `*/master` to `*/main` ← important
   - Script Path: `Jenkinsfile`
5. **Save**.

---

### Step 7: First pipeline run ✅ DONE (build #2 green)

1. On the `quizitout` job page click **Build Now** (left menu).
2. A build `#1` appears bottom-left. Click it → **Console Output** to watch the live log.
3. What happens, in order (the "Stages" view shows each box turning green):
   Checkout → Build test image → Lint → Unit + API tests → Quality gate → Build runtime image
   → Trivy scan → Push → Deploy → Smoke test.
4. The first run is slow (the Trivy database download). Later runs take a few minutes because
   Docker reuses cached layers.

✅ **Done when:**
- Every stage is green and the build shows a green tick (**SUCCESS**).
- https://hub.docker.com/r/shwetak1275/quizitout/tags shows two tags: a short code like
  `4bdf48d` (the git commit ID) and `latest`.
- http://localhost:8000 opens the app. **This copy was deployed by Jenkins.**
- `docker ps` shows `quizitout-app-1` running `shwetak1275/quizitout:<commit-id>`.

| Stage that went red | Most likely reason / fix |
|---|---|
| Checkout | Wrong repo URL or branch still `*/master`. Fix in job → **Configure**. |
| any stage: `docker: not found` | Jenkins was started from the plain image. `docker rm -f jenkins`, redo 4b with `jenkins-docker`. |
| Trivy scan | A new CVE was published since Oct 3. Copy the table from the console and give it to Claude Code. |
| Push: `unauthorized` / `denied` | Token wrong, token is read-only, or credential ID isn't exactly `dockerhub`. Redo Step 3/5. |
| Deploy: `port is already allocated` (8000) | Something else uses port 8000. Run Step 4a again, or stop any `uvicorn` you started. |
| Smoke test: `App never became healthy` | Run `docker logs quizitout-app-1` and give the output to Claude Code. |

For anything else: scroll to the **first** red error line in Console Output and give it to Claude Code.

---

### Step 8: Prove the pipeline works automatically ✅ DONE (build #2 was started by a push)

1. Make a tiny change, e.g. in `README.md` add a line at the end, then:
   ```bash
   cd "/Users/shwetakarandikar/Documents/cllz stuff/4th year/DevOps/QuizItOut"
   git add README.md
   git commit -m "docs: test automatic build"
   git push
   ```
2. Within ~2 minutes Jenkins starts build `#2` by itself (because of Poll SCM). Watch it go green.

✅ **Done when:** a build started without you clicking "Build Now".

---

### Step 9: Break things on purpose (for the demo + understanding, 20 min)

Do one at a time. After each one, **undo it** and push again so the pipeline is green again.
(Undo trick: `git revert HEAD --no-edit && git push`.)

| Experiment | What to change | What you should see |
|---|---|---|
| **A failing test** | `tests/test_validator.py`: in `test_rejects_bad_answer_index` change `7` to `0` | Red at **Unit + API tests**. Push/Deploy never run. The old app keeps running. |
| **Coverage gate** | Delete `tests/test_api.py` | Red at tests: "coverage below 80%". |
| **Automatic rollback** | `Dockerfile`, HEALTHCHECK line: change `localhost:8000/health` to `localhost:9999/health` | Green until **Smoke test** → red "App never became healthy" → console says "Rolling back to <old id>". `docker ps` shows the old commit ID running again. |
| **Trivy catches a vulnerable library** | Add the line `jinja2==2.10` to `requirements.txt` | Red at **Trivy scan** with a CVE table. |
| **LLM down safety net** (no push needed) | Quit Ollama (menu bar → Quit) | Upload `data/demo/demo_doc.pdf` → yellow **cached** badge. Upload any other file → "Quiz model unreachable". Restart Ollama after. |

Commit each one with `git add -A && git commit -m "demo: break X" && git push`.

---

### Step 10: Screenshots for the report/README (10 min)

Take these (`Cmd + Shift + 4`, then drag over the area; files go to your Desktop):
1. Jenkins job page: stage view with **all green** boxes.
2. A **red** build from Step 9 (tests red, Deploy skipped).
3. The rollback build's console showing "Rolling back to …".
4. Docker Hub → `quizitout` → **Tags** (commit-ID tag + `latest`).
5. Trivy part of a Jenkins console log.
6. App: a question answered, with the green **generated live** badge + evidence box.
7. App: the yellow **cached** badge (Ollama stopped).
8. App: the results screen with the score ring.
9. GitHub → commits page (everyone's commits).

Put them in a folder `docs/screenshots/`, and ask Claude Code to add them to the README.

---

### Step 11: Final check from a clean copy (10 min, do it before demo day)

This proves the project works for someone who just downloads it:
```bash
rm -rf /tmp/fresh && git clone https://github.com/shweta1275/QuizItOut.git /tmp/fresh
cd /tmp/fresh
docker build --target test -t quizitout:test . && docker run --rm quizitout:test
```
✅ **Done when:** it ends with `passed` and `Required test coverage of 80% reached`.

---

### Demo-day checklist (tick all before you present)

- [ ] Docker Desktop running (whale icon)
- [ ] Ollama running and `ollama list` shows `llama3`
- [ ] `docker ps` shows `jenkins` and `quizitout-app-1`
- [ ] http://localhost:8080 (Jenkins) and http://localhost:8000 (app) both open
- [ ] Last Jenkins build is green
- [ ] Docker Hub token not expired (Docker Hub → Personal access tokens)
- [ ] You've practised the 5-minute demo script in `docs/SETUP_AND_DEMO.md` (section G) once out loud
- [ ] Phone hotspot ready as backup internet
- [ ] You can explain sections 4 (loopholes) and 5 (interview questions) of this file in your own words

**After a laptop restart:** open Docker Desktop and Ollama, then run `docker start jenkins`.
The app container restarts by itself (`restart: unless-stopped`).
