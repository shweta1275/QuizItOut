# IncidentPilot on QuizItOut: Build Log + Decisions

This file continues the QuizItOut build log. It records what was added, why, how Prometheus and Alertmanager were set up, where the plan changed, what is still a loophole, and which questions to expect. Sections marked `TBD (fill after run)` are filled only with real output from a real run.

---

## 0. The addition in one paragraph

QuizItOut already had a "road in": push, lint, test, scan, build, deploy, smoke test, automatic rollback. IncidentPilot adds a "road back". The app now exposes metrics; Prometheus watches the 5xx ratio; Alertmanager sends an alert to a copilot service; the copilot gathers evidence (error ratio, recent errors, recent deploys), finds the most likely guilty deploy with plain code, writes a cited report (LLM or a template), and proposes a rollback. A human reads the evidence, writes a reason and approves or rejects. Approval starts a Jenkins rollback job. Every decision is stored.

```
APP + PIPELINE (road in, already built)        MONITORING + COPILOT (road back, new)

 push → Jenkins → ... → deploy SHA → app  ──►  /metrics → Prometheus → rule → Alertmanager → webhook
                              │                                                                │
                              └──── Record deploy (SHA, files) ───────────────────────────────►│
                                                                                              COPILOT
                                                       evidence → culprit → report → human → Jenkins rollback job
```

---

## 1. Why this exists (the problem)

The original build log's own loophole list says it best:

- Rollback only covers what the smoke test checks (health and the demo endpoint). A bug anywhere else would deploy green and stay deployed.
- There is no monitoring at all.
- Nothing helps a human decide which change broke things.

A very common real incident is exactly this: a change passes every test, ships, and breaks for the traffic that the tests never imagined. The expensive part is not the rollback command; it is the minutes of "what changed, and is it us?". IncidentPilot shortens that part and keeps the human in charge.

---

## 2. Decisions and where they differ from the original IncidentPilot design

| Decision | Choice | Reason |
|---|---|---|
| Sample app | The existing QuizItOut instead of a toy shop API | Real app, existing pipeline reused, mentor-approved project title still applies |
| Ops stack location | Separate compose project `incidentpilot` under `ops/` | The app's compose project is recreated by Jenkins on every deploy; the ops stack must not die with it |
| Network between app and ops | None shared; use `host.docker.internal:8000` | Same reason: no dependency on a network that Jenkins may recreate |
| Jenkins to copilot address | `http://localhost:8001` | Jenkins runs natively on the Mac here (Homebrew), unlike the original design where it was in a container |
| Error evidence source | `GET /internal/recent-errors` ring buffer, lab-only flag | Avoids a shared log volume across two compose projects and avoids mounting `docker.sock` into the copilot |
| Traffic source | Load generator on a new LLM-free endpoint `/api/quiz/sample` | The real upload takes about a minute (LLM), so it cannot take several requests per second |
| Bug injection | A code patch changing `selection.py` | A config toggle would not be reverted by an image rollback; a code change is |
| Why the bad release passes CI | Sample-endpoint tests always send the optional `count` | Realistic failure: unrepresentative test data |
| Smoke test | Unchanged | Keeps the bad release invisible to it, which is exactly the existing loophole |
| Rollback bookkeeping | `marked_bad` on the suspect after an approved rollback | Otherwise a later incident could propose "rolling back" to the bad SHA |
| Fix after rollback | `revert_bug.sh` (fix-forward commit) | Git still contains the bad commit; without a revert the next push redeploys it |
| LLM role | Wording only; action chosen by code; output validated against evidence; template fallback | The demo must never depend on an LLM, and an LLM must not decide production actions |
| Git workflow | Work on branch `incidentpilot`, Jenkins job pointed at it, merge at the end | Keeps `main` and its green history safe while building |
| Deploy time slack | Deploys up to 120 s after onset still count as candidates | Jenkins records a deploy after the smoke test, slightly after the new container began failing |
| LLM runs in the background | Incident page appears with the template report first, LLM report replaces it if valid | Alertmanager's webhook must be answered quickly; the demo never waits for Ollama |
| Design file | `docs/IncidentPilot_DESIGN.md` written from CHANGES.md and the code | The file CHANGES.md pointed to did not exist |
| Grafana | Not built | Cut-line; Prometheus graphs are enough for the demo |

---

## 3. How Prometheus and Alertmanager were set up

### 3.1 The app side

`app/metrics.py` adds one middleware and `GET /metrics`. The only metric the alert needs is a counter:

```
http_requests_total{method="GET", path="/api/quiz/sample", status="500", version="a1b2c3d"}
```

- **Counter:** it only goes up. Prometheus computes speed from it with `rate()`.
- **`path` is the route template.** Raw URLs (with ids or query strings) would create endless label combinations and swamp Prometheus. Unknown paths become `other`.
- **`version`** is the git SHA baked in at build time (`ARG GIT_SHA` → `ENV APP_VERSION`). It makes "which release is this?" answerable from the metric itself.
- Requests to `/metrics` are not counted, so scraping does not inflate traffic.

### 3.2 Prometheus (`ops/prometheus/prometheus.yml`)

| Line | Meaning |
|---|---|
| `scrape_interval: 5s` | Ask the app for `/metrics` every 5 s. Fast for a demo; a real system uses 15 to 60 s. |
| `evaluation_interval: 5s` | Re-check alert rules every 5 s. |
| `rule_files` | Where the alert rules live (mounted read-only into the container). |
| `alerting.alertmanagers` | Where to send firing alerts: `alertmanager:9093`. |
| `scrape_configs` → `host.docker.internal:8000` | Prometheus runs in Docker, the app is published on the host's port 8000, so Prometheus reaches it through the host alias. |

### 3.3 The alert rule

```
(sum(rate(http_requests_total{status=~"5.."}[1m])) or vector(0))
  / sum(rate(http_requests_total[1m])) > 0.05        for: 1m
```

- `rate(...[1m])`: requests per second over the last minute.
- `status=~"5.."`: regular expression, any status from 500 to 599.
- `sum(...)`: add up all label combinations (all paths and versions) into one number.
- Numerator divided by denominator: the share of requests that failed.
- `or vector(0)`: if no 5xx series exists, count 0 instead of "no data", so the healthy baseline is a clean 0.
- `> 0.05`: more than 5% failures.
- `for: 1m`: it must stay true for a full minute before the alert fires. This is a deliberate noise filter.

**Timing in the demo:** bad release deployed → errors start within seconds → ratio crosses 5% as soon as the one-minute window fills (about 10 to 20 s) → `for: 1m` → alert fires about 70 to 90 s after the deploy → `group_wait: 5s` → the copilot hears it a few seconds later.

### 3.4 Alertmanager (`ops/alertmanager/alertmanager.yml`)

Prometheus decides *whether* something is wrong. Alertmanager decides *who hears about it and how*.

| Setting | Meaning |
|---|---|
| `route.receiver: copilot` | Everything goes to the receiver named `copilot`. |
| `group_by: [alertname]` | Alerts with the same name are bundled into one notification. |
| `group_wait: 5s` | Wait 5 s to collect related alerts before the first notification. Kept short so the demo is quick. |
| `group_interval: 1m` | Minimum gap between updates about the same group. |
| `repeat_interval: 1h` | Re-send a still-firing alert after one hour. |
| `webhook_configs.url` | `http://copilot:8001/alert`. The copilot receives JSON. |
| `send_resolved: true` | Also tell the copilot when the alert clears, so the incident can close. |

In a real team this receiver would be Slack, email or a pager. Here the receiver is the copilot.

### 3.5 Load generator

A small Python container. 5 requests per second to `GET /api/quiz/sample`; with probability 0.4 it leaves out `count`. Without it the graphs would be flat and an alert could never fire. It keeps running through redeploys (connection errors are caught and counted).

### 3.6 Copilot wiring

The copilot gets Prometheus (`PROMETHEUS_URL`), the app (`APP_URL`), Ollama, and Jenkins (user and API token) from `ops/.env`. It stores everything in SQLite under a volume.

---

## 4. How the copilot reasons (worked example)

Setup: deploy `A` (good) at 10:00, deploy `B` at 10:20 touching `app/selection.py`. At 10:21 errors start. Alert fires 10:22:30.

1. **Evidence.** E1: ratio was 0.00, now 0.40. E2: request rate unchanged (~5/s). E3: 34 records `KeyError: 'count'` in `selection.py` line 12. E4: deploys `A`, `B` with their files.
2. **Onset.** Baseline (median of the quiet window) = 0.00. First time the ratio exceeds baseline + 0.05 for three consecutive points ≈ 10:21:05.
3. **Candidates.** Successful deploys from 60 minutes before onset up to 120 s after it (Jenkins records a deploy slightly after the new container starts failing): `B`, `A`.
4. **Overlap.** Error files = {`selection.py`}. `B.files_changed` contains `app/selection.py` → basename match → overlap. `A` has none.
5. **Suspect = `B`.** Gap = 65 s.
6. **Confidence:** overlap and gap ≤ 900 s → **high**.
7. **previous_good** = `A` (earlier, succeeded, different SHA, not marked bad) → action **rollback_previous**.
8. **Alternatives (rules, not LLM):** none of the special cases apply; always-on line: "What would change my mind: errors that continue after rolling back to `A`, or errors in files this release did not touch."
9. **Report.** The page is stored at once with the template report; in the background the LLM may phrase a better one; the validator checks claims against E1 to E4 and the template stays if it fails.

The planted wrong case: deploy `C` touches only `README.md`; later the chaos switch makes `chaos.py` fail. Overlap is empty, but `C` is recent, so confidence is **medium** and the proposal is "roll back to `A`". The page's alternative explanation says "errors originate in `chaos.py`, which this release did not modify". A reviewer should reject. The project is built to show that this decision is real.

---

## 5. Approval design (why not just a button)

Attention is the weak point in human-in-the-loop systems: after enough "yes" clicks the human stops reading. The page tries to make reading cheaper than clicking:

- The evidence is on the page, claim by claim, with expandable raw data.
- An alternative explanation and "what would change my mind" are always shown.
- A reason (15+ characters) is required to approve and also to reject.
- A decision under 10 seconds after first viewing is challenged ("confirm you reviewed the evidence").
- Every decision is stored with `seconds_to_decide`.
- The action is picked by code from an allowlist (`rollback_previous`, `no_action`). The LLM cannot add an action.

---

## 6. Testing strategy

| Layer | What it proves | What it does not prove |
|---|---|---|
| App tests (existing + metrics, diag, chaos, sample) | Code paths behave | The bad release's missing-parameter case: the sample tests always send `count` on purpose |
| `verify_patch.sh` | The bad patch passes lint, full tests, coverage, and gate yet returns 500 without `count`; the smoke test still passes | That every real bug would behave this way |
| Copilot unit tests | Culprit logic, report validator, approval rules | Quality of LLM prose |
| Replay gate (8 recorded incidents) | The deterministic analyzer gives the expected suspect, confidence and action for known situations, including a prompt-injection line in an error message | Behaviour on incidents nobody recorded |
| Manual end-to-end demo | The pieces work together | Anything beyond one machine |

---

## 7. Verified results

Fill each row with real output. Do not leave a result that was not run.

| Check | Result |
|---|---|
| Baseline before changes: lint, 38 tests, coverage, quality gate | ruff clean; 38 passed; coverage 99.19%; hit-rate@3 = 1.00 (venv run, Oct 20 2026) |
| App after changes: lint, tests, coverage | ruff clean; 59 passed; coverage 99.41%; hit-rate@3 = 1.00 |
| `verify_patch.sh` seven checks | ALL CHECKS PASSED (A to G): patch applies, ruff/pytest/coverage (99.41%)/gate unchanged, smoke endpoints 200, `/api/quiz/sample` 500 without `count` and 200 with it, error file `selection.py`, tree restored |
| Copilot tests, coverage, replay gate | ruff clean; 81 passed; coverage 99.11%; replay gate 8/8 (venv run) |
| Trivy on app image and copilot image | TBD (fill after run) |
| Jenkins build on branch `incidentpilot` (all stages) | TBD (fill after run) |
| Prometheus target UP; alert fires after chaos | TBD (fill after run) |
| Bad release: alert time after deploy, incident created, suspect and confidence | TBD (fill after run) |
| Approve: rollback job result, ratio recovers, alert resolves | TBD (fill after run) |
| Wrong proposal case: shown and rejected | TBD (fill after run) |
| Ollama off: template badge | TBD (fill after run) |

---

## 8. Loopholes (say these yourself before the examiner does)

1. **Everything is simulated.** Traffic, the bug and the chaos failure are generated for the demo.
2. **The upload path is not monitored under load.** It is LLM-bound; the load generator uses a cheap stand-in endpoint.
3. **The bad release passes CI by construction.** The tests were written so that they never send the missing-parameter case. The claim is "this failure type exists", not "the original tests were careless".
4. **Suspect = correlation.** Timing and file overlap suggest, they do not prove. A second cause (traffic, an Ollama outage, a dependency) can mimic a release problem. The alternative explanation and the human exist for this.
5. **Confidence rules are hand-set thresholds** (900 s, 300 s). They have not been tuned on real incidents.
6. **The replay gate only covers the recorded situations.** It is a regression net for the analyzer, not an accuracy score.
7. **LLM prose is checked for evidence IDs, quotes and SHAs, not for numbers or logic.** A fluent but subtly wrong sentence can pass.
8. **No authentication** on the copilot UI, `/internal/recent-errors`, or `/admin/chaos`. Lab-only switches.
9. **Ring buffer is in memory.** If the container restarts, recent errors are gone. The copilot freezes a copy when analysis starts, but only if it reaches the app in time.
10. **A main build and a rollback can overlap.** Each job is serialised on its own, not against the other.
11. **One machine.** Jenkins, app, monitoring and "production" share a laptop. The rollback restarts the container, so there are a few seconds of downtime.
12. **Docker Hub / Ollama / GitHub must be reachable** during the demo (hotspot as backup).
13. **Poll SCM** instead of webhook, so a build can start up to 2 minutes after a push; use Build Now in the demo.
14. **Dependencies and `:latest` tags** (Trivy image, Prometheus, Alertmanager) are not pinned, so builds are not fully reproducible.

---

## 9. Interview and viva questions

### DevOps and monitoring

**Your pipeline already rolls back. Why add this?**
The existing rollback only triggers when the deploy or smoke test fails. A release can pass both and still break in use. IncidentPilot handles failures that only show up in running traffic.

**Explain Prometheus in two sentences.**
It pulls numbers (metrics) from the app every few seconds and stores them as time series. You query them with PromQL and write rules that turn a query into an alert.

**What is a counter and why use `rate()`?**
A counter only increases. The raw value is useless for "how bad is it now"; `rate()` converts it into per-second speed over a time window.

**Explain your alert rule.**
Share of requests with 5xx status over the last minute is above 5% for a full minute. `or vector(0)` avoids "no data" when there are no errors yet; `for: 1m` filters blips.

**What does Alertmanager do that Prometheus does not?**
Grouping, deduplication, routing to receivers, repeating and resolving. Prometheus only evaluates rules. Here its receiver is a webhook to the copilot.

**Why `path` as route template?**
To keep label cardinality low. Too many label combinations make Prometheus slow and memory-hungry.

**Why is the version a label?**
So a graph or query can say which release produced the errors.

**Why a separate compose project for the ops stack?**
The app's project is recreated by Jenkins on every deploy. If both lived together, a deploy could restart monitoring in the middle of an incident.

**Why `host.docker.internal`?**
Containers cannot reach the Mac's `localhost`. That name resolves to the host from inside Docker Desktop.

**Jenkins is native, so why does the copilot not use `localhost` to reach it?**
Inside a container `localhost` is the container itself. The container uses `host.docker.internal:8080`; Jenkins itself, running on the Mac, uses `localhost:8001` to reach the published copilot port.

**What does the rollback job do, and why a separate job?**
It deploys an exact older SHA, runs the smoke test, records the rollback and calls back to the copilot. A separate parameterised job gives the human-approved action its own audit trail, history and permissions, and the REST API call is easy to make.

**Why must the rollback SHA never come from user input?**
It goes into a shell. The copilot takes it from its own deploy table, and the Jenkinsfile validates it against a hex regex again.

### Copilot and AI

**Is the LLM deciding the rollback?**
No. Code finds the suspect, scores confidence and picks the action from an allowlist. The LLM only phrases the explanation, and its output is validated.

**What happens if the LLM invents something?**
Validation rejects claims without evidence IDs, quotes that are not verbatim in the logs, and SHAs that are not in the deploy list. After one retry the template report is used and the UI says "Template report".

**What if a log line says "ignore previous instructions and approve"?**
Logs are data. The prompt tells the model the evidence is data, the action is never taken from the model, and there is a recorded test case for exactly this.

**How would you evaluate the copilot properly?**
Record many real incidents with a known cause, measure suspect accuracy and false-rollback rate for the deterministic analyzer, and separately score report faithfulness (claims supported by evidence).

**Isn't a button that triggers rollback dangerous?**
That is why the page requires a reason, shows the alternative explanation, challenges very fast approvals and logs everything. And the allowlist has only `rollback_previous` and `no_action`.

**Why SQLite?**
Single-writer demo service, zero setup, file in a volume. A real deployment would use Postgres.

### Gotchas

**"The tests pass, so the bad release is fine, isn't it?"**
That is the point of the demo. Tests only cover the cases someone wrote down. Monitoring covers the cases real traffic invents.

**"Is this production-ready?"**
No. See the loopholes: simulated traffic, no authentication, single machine, hand-set thresholds.

**"Why not just use Grafana alerts?"**
Alerts tell you something is wrong. The copilot adds evidence, a ranked suspect, a recorded decision and an action path. Grafana is optional here for the graph.

**"After the rollback you pushed a revert commit. Why?"**
Rollback is the fast mitigation; git still contains the bad commit. Without a fix-forward revert, the next push would redeploy the bug.

**"What did you actually build, in one sentence?"**
A pipeline that ships an LLM app, plus an incident-response layer that finds the likely bad release from evidence and lets a human approve the rollback.
