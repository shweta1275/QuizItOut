# DEMO_SCRIPT.md: QuizItOut + IncidentPilot, three presenters

Total about 12 to 13 minutes. No slides. Everything is shown live. Each person owns one part of the story:

| Person | Role | Owns | Time |
|---|---|---|---|
| **P1: The Builder** | Road in | The app, Git, Jenkins pipeline, Trivy, Docker Hub, deploy | ~3.5 min |
| **P2: The Watcher** | Monitoring | Prometheus, Alertmanager, the bad release, the alert | ~3.5 min |
| **P3: The Decider** | Road back | Copilot, evidence, human approval, rollback, honesty | ~5.5 min |

Suggested split: Shweta takes **P3** (it is her idea and the most to explain). Swap freely; the lines are written so any person can read any part.

**Story in one sentence (P1 says it first):** "Most pipelines stop at deploy. We built what happens when a release passes every check and still breaks."

---

## A. Before you walk in (the state must be exactly this)

- [ ] Docker Desktop, Ollama and Jenkins running; `ollama run llama3 "hi"` done once (model warm)
- [ ] Ops stack up (`docker compose -f ops/docker-compose.yml ps` shows prometheus, alertmanager, loadgen, copilot)
- [ ] Last Jenkins build green; the copilot's deploy list shows the current good SHA (call it **SHA-A**)
- [ ] App running SHA-A; Prometheus target UP; error ratio flat near 0
- [ ] No open incidents in the copilot
- [ ] Working tree clean; on branch `incidentpilot` (or `main` after the final merge)
- [ ] Tabs, left to right: **1 QuizItOut app** (`:8000`), **2 Jenkins job** (`:8080`), **3 Prometheus graph** (`:9090`, query already typed, see section F), **4 Alertmanager** (`:9093`), **5 Copilot** (`:8001`)
- [ ] One terminal in the project folder, big font, nothing else in it
- [ ] P3 has the Docker Hub tags page and `docs/` ready only if asked in Q&A
- [ ] Backup: a screen recording of a successful full run, and `scripts/fake_alert.sh`

---

## B. Run sheet (who, where, what)

| Min | Who | Screen | Action |
|---|---|---|---|
| 0:00 | P1 | App tab | Opens QuizItOut, uploads `data/demo/demo_doc.pdf` (generation takes about a minute, runs while P1 talks) |
| 0:30 | P1 | Jenkins tab | Shows the last green build, stage by stage |
| 2:30 | P1 | App tab | Shows the finished quiz and the "live" badge |
| 3:30 | P1 → P2 | , | Handover |
| 3:30 | P2 | Prometheus tab | Targets UP, request graph, error graph flat, alert rule |
| 5:00 | P2 | Terminal | `./scripts/inject_bug.sh` then `git push` |
| 5:30 | P1 | Jenkins tab | Clicks Build Now; narrates the green stages (all green!) |
| 7:00 | P2 | Prometheus tab | Error ratio climbs; Alertmanager tab shows the alert firing |
| 7:00 | P2 → P3 | , | Handover when the incident appears |
| 7:30 | P3 | Copilot tab | Opens the incident, walks the evidence |
| 10:00 | P3 | Copilot tab | Writes a reason, approves |
| 10:30 | P1 | Jenkins tab | Shows the rollback job running and finishing |
| 11:30 | P2 | Prometheus / Alertmanager | Ratio drops, alert resolves |
| 12:00 | P3 | Copilot tab | Audit entry, replay of the "wrong proposal" case, Ollama-off case |
| 13:30 | P3 | , | Limits and close |

If time is short, cut section D-5 (live chaos) and use the replay version only. See section E.

---

## C. The script (spoken lines are in quotes; **bold** = what you do)

### P1: The Builder (about 3.5 min)

**On the QuizItOut tab.**
"Hi, we are group 9. This is QuizItOut: you upload a document and a local LLM writes a multiple choice quiz from it. **Drag the demo PDF into the page.** While it generates, I want to show you how this app reaches production."

**Switch to the Jenkins tab, last green build, Stage View.**
"Every push to GitHub starts this Jenkins pipeline automatically. First it lints the code, then runs the tests, and the build fails if coverage drops below 80 percent. Then a retrieval quality gate checks that our search still finds the right paragraphs. Then Docker builds the image, and Trivy scans it for known vulnerabilities. A fixable high or critical finding stops the build."

"If everything passes, the image is pushed to Docker Hub tagged with the git commit ID, not just 'latest', so every version is traceable. Jenkins deploys exactly that tag and runs a smoke test. And if the deploy itself fails, it rolls back to the last good version automatically."

**Point to the Record deploy stage.**
"One new stage at the end: it tells our incident copilot which version was deployed and which files changed. Remember that, it matters in a minute."

**Back to the app tab.**
"And the quiz is ready. The badge says generated live, and each answer has an evidence sentence from the document. That is the road in: code to running app."

"But a pipeline that stops at deploy has a blind spot. What happens when a release passes every check and still breaks for real users? Over to P2."

### P2: The Watcher (about 3.5 min)

**Prometheus tab, Status → Targets.**
"After deploy, the app exposes its numbers at /metrics. Prometheus visits every five seconds. Here the target is UP."

**Graph tab: `sum(rate(http_requests_total[1m]))`.**
"This is about five requests per second. A small load generator creates them, because without traffic there is nothing to monitor. It calls a lightweight endpoint, since a real quiz upload takes a minute."

**Switch query to the error ratio (section F).**
"This is the share of requests that fail. It is flat at zero. We told Prometheus: if more than five percent of requests fail and that stays true for a full minute, raise an alert. Alertmanager receives it and sends it to our copilot."

**Alertmanager tab (empty).**
"Nothing firing. Now I will do what developers do every day: ship a small change." **Go to the terminal.** "A commit called 'simplify count handling'."

**Run `./scripts/inject_bug.sh`, then `git push`.**
"Pushed. P1, over to you."

*(P1 clicks Build Now and narrates, next block.)*

### P1: during the build (about 1.5 min)

**Jenkins tab, click Build Now, open the running build.**
"New commit, new build. Same stages: lint, tests, gate, build, scan, push, deploy. Look: everything is green. Our tests pass because they always send the optional count parameter. This is a very common real failure: the tests cover what we thought of, not what users do."

**When it reaches Record deploy.**
"And here the pipeline tells the copilot: new version, and these files changed: app slash selection dot py."

### P2: after the build is green

**After the build is green, Prometheus tab.**
"The pipeline is green. Tests passed, Trivy passed, smoke test passed. And yet watch this graph." **Point at the error ratio climbing.** "About forty percent of requests are now failing. The bug only hits callers that leave out an optional parameter, and our tests always send it. Real traffic does not."

**Alertmanager tab, refresh.**
"After a minute, the alert fires. Alertmanager has sent it to the copilot. P3, can you see it?"

### P3: The Decider (about 5.5 min)

**Copilot tab, refresh the list; open the new incident.**
"The copilot received the alert and did four things, with no AI involved. One: it pulled the error ratio from Prometheus. Two: it asked the app for its recent errors. Three: it listed the last five deploys. Four: it matched them."

**Point to the header.**
"Suspect: the version deployed within about a minute of the errors starting. Confidence: high. Why? The errors, KeyError 'count', come from selection.py, and that is exactly the file this deploy changed, and the timing fits. This part is plain code with fixed rules. The language model is not allowed to choose the suspect or the action."

**Point to the report and badge.**
"The report was written by the local LLM, llama3. Every claim cites evidence IDs, E1 to E4. Open this one." **Expand a claim.** "Here is the raw log line. If the model invents a quote, a SHA or an evidence ID, validation rejects the report and the page falls back to a template. The badge tells you which one you are reading."

**Point to the alternative explanation.**
"We also show the alternative explanation: what else could cause this, and what would change my mind. Correlation is not causation, so a human decides."

**Try to click Approve without a reason.**
"I cannot approve without a written reason. A decision made in under ten seconds even asks me to confirm that I read the evidence. We designed it this way because people stop reading when they just click yes."

**Type the reason, for example "KeyError in selection.py changed by this release, matches onset", click Approve.**
"Approved. The copilot starts a Jenkins job. P1?"

### P1 (about 1 min)

**Jenkins tab, quizitout-rollback job.**
"A separate rollback job started with the old version's tag. It validates the tag, deploys that exact image, and runs the smoke test."

**When green.**
"Done. And it reports back to the copilot."

### P2 (about 30 s)

**Prometheus tab.**
"The error ratio is falling. In about a minute the alert will resolve." **Alertmanager tab.** "Resolved. Back to P3."

### P3 (continued, about 2.5 min)

**Copilot tab, incident page.**
"The incident is closed and the decision is in the audit log: who, when, why, and how many seconds it took to decide. Rollback is the quick fix. The proper fix is a normal commit that reverts the bad one." **Mention (P1 can run `./scripts/revert_bug.sh` and push in the background).**

**Show the wrong proposal (live if time and the build is done; otherwise replay, see section E).**
"Now the interesting case. Suppose a harmless docs-only release is deployed, and then something else breaks, for example the model service. The copilot sees a recent deploy and proposes a rollback with medium confidence. But look at the evidence: the errors come from chaos.py, which this release never touched. A good human rejects this." **Reject with the reason "errors come from a file this release did not modify".** "The human in the loop is real, not a button."

**Resilience.**
"One more thing. Local models fail. I stop Ollama." **Quit Ollama, run `./scripts/fake_alert.sh`.** "The incident still appears, with the badge 'Template report'. The demo does not depend on the LLM."

**Close.**
"What is simulated: the traffic, the bug and the failure are generated for this demo. What is real: the pipeline, the metrics, the alert, the evidence, the validation and the rollback. What is missing: authentication, more than one service, and tuning on real incidents. We built both roads: shipping the code, and finding out what to do when shipping goes wrong. Thank you."

---

## D. Scenario details

### D-1. Happy path (P1)
The last green build is shown, not re-run. The quiz generation runs while P1 talks. If the quiz takes more than about 90 seconds, say "it takes about a minute on a laptop with a local model" and move on; come back to it at the end of the part.

### D-2. Bad release (P2 and P1)
- `./scripts/inject_bug.sh` applies `scripts/bad_release.patch` (changes `app/selection.py`), commits, prints `Now run: git push`.
- P1 clicks **Build Now** instead of waiting for Poll SCM (up to 2 minutes).
- Expected: all stages green; deploy succeeds; smoke test passes.

### D-3. Alert (P2)
- Error ratio crosses 5% within about 20 seconds of deploy; the alert fires after the one-minute `for` window, so about 70 to 90 seconds after the deploy.
- P3 refreshes the copilot tab when P2 says the alert is firing.

### D-4. Approve and rollback (P3, P1, P2)
- The Approve form needs a reason (15+ characters).
- The rollback job takes about 1 to 2 minutes. Prometheus needs another minute for the one-minute rate window to drain before the alert resolves.

### D-5. Wrong proposal (P3)
Plan A (live, only if you have the time):
1. P1 runs `./scripts/revert_bug.sh` and `git push`, clicks Build Now. This is the fix-forward and also a normal "harmless" release.
2. When it is deployed, run `./scripts/chaos_on.sh` (30% of sample requests fail with a simulated upstream error from `chaos.py`).
3. After the alert, the copilot proposes a rollback with medium confidence; the evidence shows `chaos.py`, not a changed file.
4. Reject with a reason. Run `./scripts/chaos_off.sh`.

Plan B (replay, about 30 seconds): `./scripts/fake_alert.sh chaos_after_docs_deploy`. The page shows a banner "Replay of a recorded incident"; approving it only records the decision and never calls Jenkins. Say it is a replay.

### D-6. Resilience (P3)
Quit Ollama (menu bar → Quit). Run `./scripts/fake_alert.sh`. The new incident shows the badge **Template report** (with the reason "LLM unavailable"). The LLM narrative is attempted in the background, so with Ollama running the badge can flip to "LLM report (validated)" after a refresh. Start Ollama again afterwards.

---

## E. If something breaks live

| What breaks | What to do | What to say |
|---|---|---|
| Alert does not fire after 2 minutes | P3 runs `./scripts/fake_alert.sh` (replay of `bad_release`) | "To save time, here is a recorded incident that went through the same analysis code." |
| Jenkins build is slow or red | Show the last green build; run `fake_alert.sh` | "This build is still running, the previous one shows the stages." |
| Copilot page empty | `docker compose -f ops/docker-compose.yml ps`; restart copilot; replay | "Let me show the recorded case." |
| Rollback job fails | Show the console output; explain the SHA / Docker Hub reason | "That is why every step is logged and the human sees the result." |
| Ollama slow | Say "template report is the fallback by design" | , |
| No internet | Phone hotspot; otherwise the screen recording | , |
| Quiz generation fails | Upload the demo PDF with Ollama off to show the cached badge | "This is the demo-cache fallback; it is labelled `cached`." |

Rule: never apologise for 20 seconds. Say what the system does, then do the safe path.

---

## F. Copy-paste queries and commands

Prometheus queries:

```
sum(rate(http_requests_total[1m]))
```
```
(sum(rate(http_requests_total{status=~"5.."}[1m])) or vector(0)) / sum(rate(http_requests_total[1m]))
```
```
sum by (version) (rate(http_requests_total{status=~"5.."}[1m]))
```
(the last one shows which version is producing the errors)

Terminal:

```bash
./scripts/inject_bug.sh      # then: git push
./scripts/revert_bug.sh      # then: git push
./scripts/chaos_on.sh
./scripts/chaos_off.sh
./scripts/fake_alert.sh                       # replay: bad_release
./scripts/fake_alert.sh chaos_after_docs_deploy
```

---

## G. Questions the examiner may ask, and who answers

| Question | Answer by | Short answer |
|---|---|---|
| Why Jenkins? | P1 | Course requirement, runs on the same machine as Docker and Ollama, parameterised jobs and a REST API for the rollback. |
| What does Trivy do here? | P1 | Scans the image for known CVEs; fixable HIGH/CRITICAL fails the build. We fixed real findings (libpcre2, vendored packages inside pip) instead of ignoring them. |
| Why tag by git SHA? | P1 | `latest` moves; a SHA identifies the exact commit and makes rollback exact. |
| Why does the bad release pass CI? | P2 | The tests always send the optional parameter. It models unrepresentative test data. |
| Why not just use Grafana alerts? | P2 | An alert only says something is wrong. The copilot adds evidence, a ranked suspect, a recorded decision and an action path. |
| What does the alert rule mean? | P2 | More than 5% of requests failed for a full minute. |
| Is the LLM in charge? | P3 | No. Code picks the suspect and the action; the LLM only phrases the explanation, validated against evidence, with a template fallback. |
| What if the log contains malicious text? | P3 | Logs are treated as data; the action never comes from the model; there is a test for a prompt-injection line. |
| Is this production-ready? | P3 | No: simulated traffic, no authentication, one machine, hand-set thresholds. |
| What would you do next? | P3 | Webhooks, authentication, staging environment, canary releases, tuning on real incidents. |

---

## H. Rehearsal checklist

- [ ] Run the whole script once with a stopwatch; the target is 12 to 13 minutes
- [ ] Practise the handovers ("over to P2") until they are silent and smooth
- [ ] Run the live rollback at least twice and the replay once
- [ ] Practise one failure on purpose (stop the copilot) and recover in under 30 seconds
- [ ] Every person says their own part aloud, standing, once
- [ ] Decide who answers which question (section G) and who stays quiet
- [ ] Reset between rehearsals: see `docs/SETUP_INCIDENTPILOT.md` section 6

---

## I. Full runbook: from a broken build to a live rollback (copy and paste)

This section is the exact order of work for this machine (Jenkins on port 8081, branch `main`). Every command can be pasted into a terminal. Run them from the project folder:

```bash
cd "/Users/shwetakarandikar/Documents/cllz stuff/4th year/DevOps/QuizItOut"
```

### I.0 What was wrong, in plain words

1. **Jenkins build #18 failed in stage 6 (Copilot: lint + tests).** The test `test_replay_creates_incident_page_with_banner_and_badge` expects the "Template report" badge. Inside Docker, `host.docker.internal` resolves to the Mac, so the test reached the real Ollama, got a valid LLM report and the badge said "LLM report (validated)". The fix is in `ops/copilot/tests/conftest.py`: tests now point Ollama at a dead address. The failing build triggered the automatic rollback, which is why the copilot shows a `rollback` deploy of `0c15511`.
2. **Incident #14 was a replay**, created by `fake_alert.sh`. Approving a replay never calls Jenkins, by design. That is why no `quizitout-rollback` build appeared.
3. **The bad release was never pushed.** The commit `b99d7f2` named "perf: faster question selection" contains only the report `.docx`; `app/selection.py` is still the good version.
4. **`ops/.env` is not ready for a real approval:** `JENKINS_USER` and `JENKINS_TOKEN` are empty and `JENKINS_URL` points to port 8080, but this Jenkins runs on **8081**.

### I.1 Fix `ops/.env` (once)

1. Open Jenkins at http://localhost:8081, click your user name (top right), **Security**, **API Token**, **Add new Token**, name it `copilot`, **Generate**, copy the token (it is shown once).
2. Open the file and set these three lines (`JENKINS_URL` changes from 8080 to 8081):

```bash
open -e ops/.env
```
```
JENKINS_URL=http://host.docker.internal:8081
JENKINS_USER=<your Jenkins user name>
JENKINS_TOKEN=<the token you just copied>
```

3. Restart the copilot so it reads the file, then test the credentials (expect `200`):

```bash
docker compose -f ops/docker-compose.yml --env-file ops/.env up -d copilot
curl -s -o /dev/null -w '%{http_code}\n' -u 'YOUR_USER:YOUR_TOKEN' http://localhost:8081/api/json
```

`ops/.env` is git-ignored, so the token is never pushed.

### I.2 Jenkins settings to check (once)

| Job | Where | Must be |
|---|---|---|
| `quizitout` | Configure, Pipeline | Branch Specifier `*/main` (not `*/incidentpilot`, because the work is merged), Script Path `Jenkinsfile`, Poll SCM `H/2 * * * *` |
| `quizitout-rollback` | http://localhost:8081/job/quizitout-rollback/ | Exists, Branch Specifier `*/main`, Script Path `Jenkinsfile.rollback`, and the left menu says **Build with Parameters**. If the job is missing or only shows "Build Now", follow `docs/SETUP_INCIDENTPILOT.md` section 5. |

### I.3 Push the repo fix (you commit and push)

The test fix and this runbook are already edited in your working tree. Check, commit and push it:

```bash
git status --short
git add ops/copilot/tests/conftest.py docs/DEMO_SCRIPT.md
git commit -m "fix: copilot tests must not reach a real Ollama; add demo runbook"
git push
```

Optional local proof before you push (the second line pretends Ollama is reachable, like inside Docker):

```bash
(cd ops/copilot && ../../.venv/bin/python -m pytest -q)
(cd ops/copilot && OLLAMA_BASE_URL=http://localhost:11434 ../../.venv/bin/python -m pytest -q)
```

Both must print `81 passed`.

### I.4 Start from a clean copilot, then get the green build

Reset the copilot database (it holds 14 old incidents, 12 of them still "awaiting decision") and start everything:

```bash
docker compose -f ops/docker-compose.yml down -v
docker compose -f ops/docker-compose.yml --env-file ops/.env up -d --build
docker compose -f ops/docker-compose.yml ps
```

Warm up the model so the first LLM report is quick:

```bash
ollama run llama3 "hi"
```

Now in Jenkins click **quizitout**, **Build Now**. Expect **all 13 stages green** (about 2 to 5 minutes). Then confirm:

```bash
curl -s localhost:8000/health
curl -s localhost:8001/deploys
git rev-parse --short HEAD
```

The `version` in `/health` must equal the short SHA from `git rev-parse`, and `/deploys` must list that SHA with `"kind":"deploy"`. Call this SHA **SHA-A**: it is the version the rollback will return to. If `/deploys` is empty, the Record deploy stage did not reach the copilot; check the stage output in Jenkins.

### I.5 Pre-flight checklist (2 minutes before the demo)

```bash
git status --short                                   # must print nothing (inject_bug.sh refuses a dirty tree)
curl -s localhost:8000/health                        # version = SHA-A
curl -s localhost:9090/api/v1/targets | python3 -c "import json,sys; print([(t['scrapeUrl'], t['health']) for t in json.load(sys.stdin)['data']['activeTargets']])"   # health: up
curl -s localhost:8001/deploys | head -c 300; echo   # SHA-A listed
docker logs --tail 3 incidentpilot-loadgen-1         # traffic flowing, 5xx = 0
open http://localhost:8000 http://localhost:8081 http://localhost:9090 http://localhost:9093 http://localhost:8001
```

The copilot home page must show **no open incident** (an empty list after the reset in I.4).

### I.5b Optional: the error ratio as one number

```bash
curl -s localhost:9090/api/v1/query --data-urlencode 'query=(sum(rate(http_requests_total{status=~"5.."}[1m])) or vector(0)) / sum(rate(http_requests_total[1m]))' | python3 -c "import json,sys; print(json.load(sys.stdin)['data']['result'][0]['value'][1])"
```

Healthy is `0`. During the bad release it climbs towards `0.4`.

### I.6 The demo run, step by step

**Step 1: ship the bad release.** This applies `scripts/bad_release.patch` (one line in `app/selection.py`), commits it as "fix: simplify count handling" and stops. You push.

```bash
./scripts/inject_bug.sh
git push
```

Say: "A small, harmless-looking change."

**Step 2: run the pipeline.** In Jenkins click **quizitout**, **Build Now** (do not wait for Poll SCM, it can take up to 2 minutes). **Show that every stage goes green**, including Trivy and the smoke test. This is the point of the demo: the checks cannot see this bug because the tests always send `count` and the smoke test only calls `/health` and `/api/quiz/demo`.

**Step 3: confirm the bad version is live.**

```bash
curl -s localhost:8000/health
curl -s -o /dev/null -w 'no count: %{http_code}\n' localhost:8000/api/quiz/sample
curl -s -o /dev/null -w 'count=3 : %{http_code}\n' "localhost:8000/api/quiz/sample?count=3"
```

Expect a new version, `no count: 500` and `count=3 : 200`.

**Step 4: show the error. This is the moment to show it, not in Jenkins.** Within 20 to 30 seconds:

- Prometheus graph (http://localhost:9090/graph), paste the query from I.5b, the ratio climbs towards 0.4.
- After about 1 to 1.5 minutes: http://localhost:9090/alerts shows **HighErrorRate FIRING**, then http://localhost:9093 shows the alert.
- Optional proof of the cause: `curl -s localhost:8000/internal/recent-errors | python3 -m json.tool | head -20` shows `KeyError: 'count'` in `selection.py`.

**Step 5: open the incident.** Go to http://localhost:8001 and open the newest incident. It must have **no yellow "Replay" banner**. Check: suspect = the SHA you just pushed, confidence high, action `rollback_previous` to SHA-A, and the evidence (E3) shows `selection.py`. Click an "evidence" link to show the raw log line.

**Step 6: approve.** Type a reason of at least 15 characters, for example `KeyError in selection.py changed by this release, matches onset`, and click **Approve rollback**. If you click within 10 seconds of opening the page it asks you to confirm: this is the rubber-stamp guard, click the confirm button.

**Step 7: watch the rollback.** Open http://localhost:8081/job/quizitout-rollback/ . A new build starts within seconds (Validate, Checkout, Deploy, Smoke test, Record deploy). Then:

```bash
curl -s localhost:8000/health
curl -s -o /dev/null -w 'no count: %{http_code}\n' localhost:8000/api/quiz/sample
```

`version` must be SHA-A again and the request without `count` returns `200`. The incident status becomes `rollback_ok`; the suspect is marked bad in the deploy list.

**Step 8: errors stop, alert resolves.** The ratio falls to 0 within about a minute and the alert resolves about one minute after that (the one-minute rate window must drain). The audit table on the incident page shows your reason and the seconds you took to decide.

**Step 9: fix forward.** The rollback is only a mitigation; git still contains the bad commit. Revert it, push, and build once so the repository and the running app agree:

```bash
./scripts/revert_bug.sh
git push
```

Then **Build Now** on `quizitout` (wait until the rollback job has finished before you do this: the two jobs do not lock each other).

### I.7 Optional extras (after the main run)

**Wrong proposal (a human should reject).** Needs a docs-only release first so the copilot sees a recent, unrelated deploy:

```bash
./scripts/harmless_change.sh
git push
```

Build Now, wait until it is deployed and healthy, then:

```bash
./scripts/chaos_on.sh
```

After the alert the copilot proposes a rollback with medium confidence, but the errors come from `chaos.py`, which this release did not touch. Open the incident, read the alternative explanation, **Reject** with a reason such as `errors come from chaos.py, a file this release did not modify`, then:

```bash
./scripts/chaos_off.sh
```

**Safety net (replay, no Jenkins needed).** Say out loud that it is a replay; approving it never calls Jenkins:

```bash
./scripts/fake_alert.sh
./scripts/fake_alert.sh chaos_after_docs_deploy
```

**Ollama off, template report.** Quit Ollama from the menu bar, then run `./scripts/fake_alert.sh`. The new incident shows the "Template report" badge. Start Ollama again afterwards (`open -a Ollama`).

### I.8 If something goes wrong

| Symptom | Fix |
|---|---|
| A Jenkins stage is red | Click it and read the console; run the failing command from section I.3 locally. Jenkins rolls back automatically to the last good SHA. |
| Build does not start after a push | Poll SCM is every 2 minutes, or the job still builds another branch. Click **Build Now** and check I.2. |
| Approve says "Jenkins needs credentials" or shows `rollback_failed` | `JENKINS_USER` or `JENKINS_TOKEN` empty, or `JENKINS_URL` still on 8080. Redo I.1. |
| Approve works but no `quizitout-rollback` build appears | The incident is a replay (yellow banner), or the job does not exist yet. Check I.2. |
| Alert does not fire after 2 minutes | `docker logs incidentpilot-loadgen-1`, then `curl -s localhost:8000/api/quiz/sample` must return 500. Otherwise use the replay as a safety net and say so. |
| Incident says "no suspect" | The copilot has no recorded deploy. Run a Build Now with the ops stack up (I.4). |
| Next build brings the error back | The bad commit is still in git. Run `./scripts/revert_bug.sh` and push (step 9). |
| `inject_bug.sh` says the working tree is not clean | Commit or stash your changes first. |
