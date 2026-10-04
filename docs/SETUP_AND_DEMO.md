# QuizItOut: Your Checklist (things only you can do)

Everything inside the repo (code, tests, Docker images, local commits) is already done.
What's left needs **your accounts and passwords**, so it can't be automated from here.
Do the steps in order. Each step ends with a **check** command so you know it worked.

---

## A. Before anything: confirm your Docker Hub username

The image name is written as `shwetak1275/quizitout` in **two places**. If your Docker Hub
username is different, change both:

1. `Jenkinsfile` → `IMAGE = 'shwetak1275/quizitout'`
2. `docker-compose.yml` → `image: ${IMAGE:-shwetak1275/quizitout}:...`

Then `git commit -am "use my docker hub username"`.

---

## B. GitHub (5 min)

1. github.com → **New repository** → name `quizitout`, **Public**, do **not** tick README /
   .gitignore / license.
2. In this folder:
   ```bash
   git remote add origin https://github.com/shweta1275/QuizItOut.git
   gh auth login            # easiest way to authenticate (or use an SSH key)
   git push -u origin main
   ```
3. Repo → Settings → Collaborators → add your teammates.

**Check:** `git log origin/main --oneline | head -3` shows the phase commits.

| Error | Fix |
|---|---|
| `Authentication failed` | HTTPS needs a Personal Access Token, not your password. Use `gh auth login`. |
| `remote origin already exists` | `git remote set-url origin <url>` |

---

## C. Docker Hub (5 min)

1. hub.docker.com → **Create repository** → `quizitout`, Public.
2. Account settings → **Personal access tokens** → Generate. Name `jenkins`, permission
   **Read & Write**. Copy it into your password manager (you only see it once).
3. **Never paste this token into chat or into any file in the repo.**

---

## D. Jenkins (20–30 min, first time)

1. Build and start Jenkins (the image already has the docker CLI + compose plugin):
   ```bash
   docker build -t jenkins-docker ./jenkins
   docker run -d --name jenkins -u root -p 8080:8080 \
     -v jenkins_home:/var/jenkins_home \
     -v /var/run/docker.sock:/var/run/docker.sock \
     jenkins-docker
   docker logs jenkins 2>&1 | grep -A2 "initialAdminPassword"   # first-time password
   ```
2. Open http://localhost:8080 → paste the password → **Install suggested plugins** →
   create your admin user.
3. **Check Docker access from inside Jenkins:**
   ```bash
   docker exec jenkins docker ps
   docker exec jenkins docker compose version
   ```
   Both must print output without errors.
4. **Credentials:** Manage Jenkins → Credentials → System → Global credentials →
   **Add Credentials** → Kind *Username with password*:
   - Username: your Docker Hub username
   - Password: the access token from step C
   - ID: `dockerhub` (exact spelling, the Jenkinsfile looks for this ID)
5. **Job:** Dashboard → **New Item** → name `quizitout` → **Pipeline** → OK.
   - Build Triggers: tick **Poll SCM**, schedule `H/2 * * * *`
   - Pipeline → Definition: **Pipeline script from SCM** → SCM: **Git**
   - Repository URL: `https://github.com/shweta1275/QuizItOut.git`
   - Branch: `*/main` → Script Path: `Jenkinsfile` → Save.
6. **Build Now.** Open the build → **Console Output**.
   The first run is slow (torch + models + the Trivy database download, ~15–25 min).
   Later runs reuse the Docker layer cache.
7. **Before the first Deploy stage:** stop anything already using port 8000 on your Mac
   (e.g. a local `uvicorn` or a manual `docker compose up`), because the deployed container needs it:
   `docker compose -p quizitout down` and stop any `uvicorn` you started by hand.

| Error | Fix |
|---|---|
| `permission denied ... docker.sock` | Container wasn't started with `-u root`. `docker rm -f jenkins` and re-run step 1. |
| `docker: command not found` inside Jenkins | You ran the plain `jenkins/jenkins` image. Build `./jenkins` first. |
| `docker compose` not found | `docker-compose-plugin` missing from `jenkins/Dockerfile`. |
| `unauthorized` on push | Wrong token / username, or credential ID isn't exactly `dockerhub`. |
| Port 8080 in use | Use `-p 8080:8080` and open localhost:8080. |
| `Bind for 0.0.0.0:8000 failed` in Deploy | Something else is on port 8000; see step 7. |

**Check:** Docker Hub → `quizitout` → Tags shows the short git SHA and `latest`.
http://localhost:8000 opens the app deployed by Jenkins.

---

## E. Things to try on purpose (great for the demo and for understanding)

1. **Failing test:** in `tests/test_validator.py` change `answer_index": 7` to `0`. Push.
   Jenkins goes red at *Unit + API tests*, Push/Deploy are skipped, and the old version keeps
   running. Revert and push.
2. **Coverage gate:** delete `tests/test_api.py`, push → red at tests (coverage < 80%).
3. **Rollback:** break something that only exists in the *runtime* stage, so tests still
   pass. In the Dockerfile's runtime `HEALTHCHECK`, change `localhost:8000/health` to
   `localhost:9999/health`. Push → everything green up to Deploy → Smoke test says
   "App never became healthy" → `post { failure }` redeploys the last good SHA.
   (Check with `docker ps`: the running image tag is the old SHA.) Revert and push.
4. **Trivy:** add `jinja2==2.10` to `requirements.txt` → Trivy stage goes red with CVEs.
5. **LLM down:** quit Ollama, upload `data/demo/demo_doc.pdf` → yellow "cached" badge. Upload
   any other file → error 503 "Quiz model unreachable".

---

## F. Screenshots to take for the report / README

1. Jenkins Stage View, every stage green.
2. Jenkins run that you broke on purpose (red stage, Deploy skipped).
3. Docker Hub tags page (`:<sha>` and `:latest`).
4. Trivy console output from the Jenkins log.
5. App with the green **generated live** badge, with the evidence snippet visible.
6. App with the yellow **cached** badge (Ollama stopped).
7. GitHub commits page (everyone's commits).

---

## G. Demo script (5 minutes)

1. **(30 s)** Architecture diagram from the README: "upload → quiz, and behind it CI/CD."
2. **(90 s)** Browser: upload `data/demo/demo_doc.pdf`, let it generate live. Point at the
   "generated live" badge, answer one question, show the evidence sentence from the document.
3. **(60 s)** Make a tiny code change, `git push`, show Jenkins stages turning green one by one.
4. **(60 s)** Show a run you broke on purpose: the pipeline stopped and nothing was deployed.
5. **(30 s)** Docker Hub SHA tags + Trivy output.
6. **(30 s)** Safety net: "If the LLM is down, the known demo file gets a reviewed cache and the
   UI says so." Quit Ollama and show it.

**Demo-day checklist:** Ollama running + `llama3` pulled · Docker Desktop up · Jenkins container
up · Docker Hub token valid · fresh clone tested (`git clone <repo> /tmp/fresh` and run compose
from there) · phone hotspot as a backup network.
