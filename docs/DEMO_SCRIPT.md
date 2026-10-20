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
