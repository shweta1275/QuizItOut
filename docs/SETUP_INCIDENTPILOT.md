# SETUP_INCIDENTPILOT.md: your click-by-click steps

The coding agent writes the code. This file is for **you**: the things only you can do (pushes, Jenkins clicks) and how to check that every part works.

Terminal: `Cmd + Space`, type Terminal, Enter. Always start from the project folder:

```bash
cd "/Users/shwetakarandikar/Documents/cllz stuff/4th year/DevOps/QuizItOut"
```

**The golden rule of this change:** the coding agent never pushes. When it says "YOUR TURN: PUSH", you run the `git push` it shows. Everything is on the branch `incidentpilot`, so your working `main` pipeline stays untouched until the very end.

Things that must be running: Docker Desktop (whale icon), Ollama (llama icon, or `ollama serve`), Jenkins (`http://localhost:8080` opens).

---

## 0. Quick sanity check (2 min)

```bash
docker ps --format '{{.Names}}\t{{.Status}}'
ollama list
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/login
curl -s http://localhost:8000/health
```

Success: `quizitout-app-1` is listed and healthy, `llama3` appears in `ollama list`, Jenkins returns `200`, the app health prints JSON.

If Jenkins returns nothing: `brew services list` and `brew services start jenkins-lts`.

---

## 1. Push the branch (every time the agent asks)

```bash
git push -u origin incidentpilot      # first time
git push                              # afterwards
```

If asked for a password: run `gh auth login` again (GitHub does not accept your account password in the terminal).

---

## 2. Point the Jenkins job at the new branch (Phase 1, 2 min)

Why: the job currently builds `main`. Until the work is finished you build the branch instead, so `main` keeps its green history.

1. Open `http://localhost:8080`, click the job **quizitout**.
2. Left menu → **Configure**.
3. Scroll to **Pipeline** → **Branch Specifier** → change `*/main` to `*/incidentpilot`.
4. **Save**.
5. Click **Build Now**.

Success: every stage turns green; Docker Hub → `shwetak1275/quizitout` → Tags shows a new short SHA tag and `latest`.

At the very end (after the demo is ready): merge `incidentpilot` into `main` on GitHub (a Pull Request is fine), then set the Branch Specifier back to `*/main`.

| Problem | Fix |
|---|---|
| "No such branch" in Checkout | You have not pushed the branch yet. Run the push in section 1. |
| Build does not start by itself | Poll SCM runs every ~2 min. Click **Build Now** to skip the wait. |

---

## 3. Start the ops stack (Phase 2 onwards)

```bash
cp ops/.env.example ops/.env
docker compose -f ops/docker-compose.yml --env-file ops/.env up -d --build
docker compose -f ops/docker-compose.yml ps
```

(The agent normally runs this for you; you run it after a laptop restart.)

### Verify each part

| Part | Open | Success looks like |
|---|---|---|
| App metrics | http://localhost:8000/metrics | Text lines starting with `http_requests_total{...}` |
| Prometheus targets | http://localhost:9090/targets | Target `quizitout` is **UP** (green) |
| Prometheus rules | http://localhost:9090/alerts | Rule `HighErrorRate` listed, state **inactive** |
| Alertmanager | http://localhost:9093 | Page opens, no alerts |
| Copilot | http://localhost:8001 | Incident list page (empty) |
| Loadgen | `docker logs -f incidentpilot-loadgen-1` | A summary line every 10 s, mostly ok |

Check recorded deploys: `curl -s localhost:8001/deploys`.

Quick graph check: Prometheus → Graph tab → enter `sum(rate(http_requests_total[1m]))` → Execute. About 5 requests per second.

| Problem | Fix |
|---|---|
| Target `quizitout` is DOWN | App not running or not on 8000: `curl localhost:8000/health`. From a container: `docker run --rm curlimages/curl -s http://host.docker.internal:8000/health` |
| Port already allocated | Another process uses 9090/9093/8001: `lsof -i :9090` |
| Loadgen logs show connection errors | Normal for a few seconds during every redeploy. If constant, the app is down. |

Stop the ops stack (data kept): `docker compose -f ops/docker-compose.yml down`.

---

## 4. Jenkins API token for the copilot (Phase 4, 3 min)

Why: the copilot needs to start the rollback job. It uses a token, never your password.

1. Jenkins (top-right) → click **your username** → **Security**.
2. Section **API Token** → **Add new Token** → name `copilot` → **Generate**.
3. **Copy the token now** (shown once). Paste it into `ops/.env`:
   ```
   JENKINS_USER=<your Jenkins username>
   JENKINS_TOKEN=<the token>
   ```
4. Never paste the token into chat, into any committed file, or into GitHub. `ops/.env` is gitignored.
5. Restart the copilot so it reads the file:
   ```bash
   docker compose -f ops/docker-compose.yml --env-file ops/.env up -d copilot
   ```
6. Verify the token works:
   ```bash
   curl -s -o /dev/null -w '%{http_code}\n' -u 'YOUR_USER:YOUR_TOKEN' http://localhost:8080/api/json
   ```
   Success: `200`. A `401` means wrong user or token.

---

## 5. Create the rollback job (Phase 4, 5 min)

1. Jenkins Dashboard → **New Item**.
2. Name: `quizitout-rollback` → **Pipeline** → **OK**.
3. Scroll to **Pipeline**:
   - Definition: **Pipeline script from SCM**
   - SCM: **Git**
   - Repository URL: `https://github.com/shweta1275/QuizItOut.git`
   - Branch Specifier: `*/incidentpilot` (change to `*/main` at the end, like section 2)
   - Script Path: `Jenkinsfile.rollback`
4. **Save**.
5. **Important quirk:** a parameterised pipeline only learns its parameters after it has run once. Click **Build Now** once. It will fail or stop at validation, that is fine. Refresh the job page: the menu now says **Build with Parameters**.
6. Test by hand: **Build with Parameters** → `ROLLBACK_TO` = a SHA that exists on Docker Hub and that you want running (use the previous good tag), `INCIDENT_ID` = `0` → **Build**.

Success: stages Validate, Deploy, Smoke test green, `docker ps` shows `quizitout-app-1` running the SHA you gave.

| Problem | Fix |
|---|---|
| Only "Build Now", no parameters | Run it once first (step 5). |
| Validate stage fails | `ROLLBACK_TO` must be 7 to 40 hex characters, `INCIDENT_ID` digits only. |
| Deploy stage cannot pull | The tag does not exist on Docker Hub. Check the Tags page. |

---

## 6. Dry run of the whole story (Phase 6, 20 min)

Follow `docs/DEMO_SCRIPT.md` once, alone, with the stopwatch off. The first time it is normal for something to need a fix.

State you need before the bad release:
1. A green build recorded by the copilot: click **Build Now** on `quizitout` after the ops stack is up, then open `http://localhost:8001` and check the deploy list shows the SHA.
2. Loadgen running, error ratio flat near 0.

Reset between rehearsals:
```bash
./scripts/revert_bug.sh      # then: git push   (fix-forward the bad commit)
docker compose -f ops/docker-compose.yml down -v   # clears copilot data (incidents and deploys)
docker compose -f ops/docker-compose.yml --env-file ops/.env up -d
# then Build Now once so the copilot learns the current good SHA again
```

---

## 7. How each monitoring piece was set up (summary; the long version is in `EXPLANATION_INCIDENTPILOT.md`)

| Piece | Image / source | Config file | One-line purpose |
|---|---|---|---|
| Prometheus | `prom/prometheus` | `ops/prometheus/prometheus.yml`, `alert_rules.yml` | Scrapes `/metrics`, evaluates the alert rule |
| Alertmanager | `prom/alertmanager` | `ops/alertmanager/alertmanager.yml` | Receives alerts, forwards them as a webhook to the copilot |
| Loadgen | built from `ops/loadgen` | env vars in compose | Creates steady traffic so graphs are not empty |
| Copilot | built from `ops/copilot` | `ops/.env` | Collects evidence, proposes rollback, asks you |
| Ollama | already installed | model `llama3` | Writes the explanation text only |

---

## 8. Troubleshooting table

| Symptom | Likely cause | Fix |
|---|---|---|
| Alert never fires after the bad release | Loadgen not running, or `/api/quiz/sample` not hit | `docker logs incidentpilot-loadgen-1`; check the 5xx count in Prometheus: `sum(rate(http_requests_total{status=~"5.."}[1m]))` |
| Alert fires but no incident | Alertmanager cannot reach the copilot | `docker logs incidentpilot-alertmanager-1`; copilot must be up on 8001 |
| Incident says "no suspect" | Copilot has no recorded deploys | Click Build Now once after the copilot is up; check the Record deploy stage output |
| Deploy not recorded | Jenkins used the wrong address | Jenkins is native: it must call `http://localhost:8001`, not `host.docker.internal` |
| Approve does nothing | `JENKINS_USER`/`JENKINS_TOKEN` empty or wrong | Redo section 4, restart the copilot |
| Rollback job runs but the app is not rolled back | Wrong SHA, or tag missing on Docker Hub | Read the Deploy stage in the rollback job's Console Output |
| Report badge says "Template report" with Ollama running | Model not loaded or timeout | Warm it up: `ollama run llama3 "hi"`; the first call can take a while |
| Push stage `unauthorized` | Docker Hub token expired | Docker Hub → Personal access tokens → regenerate → update Jenkins credential `dockerhub` |
| After rollback the next push brings the error back | Git still contains the bad commit | `./scripts/revert_bug.sh`, then push |

---

## 9. Demo-day checklist (tick before presenting)

- [ ] Docker Desktop, Ollama and Jenkins running
- [ ] `ollama run llama3 "hi"` done once (model warm)
- [ ] `docker ps` shows `quizitout-app-1`, the four ops containers
- [ ] Prometheus target UP, error ratio flat near 0
- [ ] Copilot deploy list shows the current good SHA (and at least one earlier one if possible)
- [ ] Last Jenkins build green; Jenkins job branch matches what you pushed
- [ ] Browser tabs open in this order: Jenkins, Prometheus graph, Alertmanager, Copilot, QuizItOut app
- [ ] Terminal open in the project folder, large font
- [ ] Docker Hub token not expired
- [ ] Phone hotspot ready as backup
- [ ] Screen recording of a successful full run saved (last-resort fallback)
- [ ] Every presenter has read their part of `docs/DEMO_SCRIPT.md` aloud once
