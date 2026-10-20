# IncidentPilot: design of the copilot

`docs/CHANGES.md` refers to this file for the copilot specification. It was not in the repo when the work started, so this version was written from `CHANGES.md`, the README and the explanation doc, and then checked against the code in `ops/copilot/`. Where code and an older description differ, the code wins and this file says so.

Principles (from CHANGES 1.1): the LLM is not in the decision path; nothing without evidence; approval must resist rubber-stamping; logs and commit messages are untrusted input; claims are honest (correlation, simulated incidents).

---

## 1. Data model (SQLite, `ops/copilot/app/db.py`)

| Table | Columns that matter |
|---|---|
| `deploys` | `sha`, `image`, `commit_message`, `files_changed` (comma-joined repo paths), `status` (`succeeded`/`failed`), `kind` (`deploy`/`rollback`), `deployed_at` (epoch), `marked_bad` |
| `incidents` | `alert_name`, `alert_start`, `alert_resolved_at`, `status`, `suspect_sha`, `confidence`, `action`, `previous_good_sha`, frozen `analysis_json` / `evidence_json` / `report_json`, `report_source` (`template`/`llm`), `report_note`, `is_replay`, `first_viewed_at`, `rollback_detail` |
| `decisions` | `incident_id`, `decision`, `reason`, `seconds_to_decide`, `confirmed_fast`, `decided_at` (the audit trail) |

Incident status flow: `awaiting_decision` → `rejected` | `rollback_requested` → `rollback_ok` | `rollback_failed`; replay incidents end in `rollback_skipped_replay`.

## 2. HTTP API (`ops/copilot/app/main.py`)

| Route | Purpose |
|---|---|
| `POST /deploys` (form) | Jenkins "Record deploy". `sha` must be 7-40 hex, `kind` in {deploy, rollback}. |
| `GET /deploys` | JSON list, for checks with curl. |
| `POST /alert` (JSON) | Alertmanager webhook. `firing` creates an incident (one per alert name until it resolves); `resolved` stamps `alert_resolved_at`. |
| `POST /dev/replay/{name}` | Only with `ENABLE_REPLAY=true`. Builds an incident from `tests/incidents/{name}.json` through the same analysis code. |
| `GET /`, `GET /incidents/{id}` | Incident list, deploy list, detail and approval page. Opening the detail page stamps `first_viewed_at`. |
| `POST /incidents/{id}/approve`, `/reject` | Form: `reason`, optional `confirm=yes`. |
| `POST /incidents/{id}/rollback-result` | Callback from the rollback job: `status=ok|failed`, `sha`. |
| `GET /incidents/{id}/json`, `GET /health` | Inspection and health check. |

## 3. Evidence bundle

| ID | Content | Source |
|---|---|---|
| E1 | 5xx ratio: baseline, current, peak, onset | Prometheus `query_range`, same expression as the alert rule |
| E2 | Request rate before and after onset | Prometheus |
| E3 | Last (up to 20) error records: exception, file, line, path, truncated message | App `GET /internal/recent-errors`, fetched when the alert arrives and stored (frozen). Unreachable app: E3 empty with a note, analysis continues. |
| E4 | Last five deploys with files changed | Copilot's own `deploys` table |

## 4. Deterministic analysis (`culprit.py`, no I/O, no LLM)

1. **Onset.** Baseline = median of ratio samples older than `alert_start - 60 s - 30 s`. Onset = first sample of the first run of three consecutive samples above baseline + 0.05. No baseline window or no such run: `alert_start - 60 s` (method `fallback`).
2. **Candidates.** Successful deploys with `onset - 3600 s <= deployed_at <= onset + 120 s`. The 120 s slack exists because Jenkins records a deploy after the smoke test, a little after the new container started serving (and failing).
3. **Overlap.** Basenames of `files_changed` intersected with basenames in E3 (records inside the window, `unknown` ignored).
4. **Suspect.** Newest candidate with overlap; else newest candidate; else none.
5. **Confidence.** `high`: overlap and gap <= 900 s. `medium`: no overlap and gap <= 300 s. Otherwise `low`. Gap = `max(0, onset - deployed_at)`.
6. **previous_good.** Newest successful deploy strictly earlier than the suspect, with a different SHA, not `marked_bad`.
7. **Action** (allowlist `rollback_previous`, `no_action`): `rollback_previous` iff confidence is high or medium and `previous_good` exists.
8. **Alternatives** (rules): no deploy in the hour; errors in files the release did not touch; no error records; other deploys in the window; "what would change my mind".

## 5. Report

The incident page is stored immediately with a **template report** (deterministic text built from E1-E4). A background task then asks Ollama (`/api/generate`, JSON mode, `LLM_TIMEOUT` 60 s) for a narrative. The prompt marks the evidence as untrusted data and gives the analysis result as fixed fact. The answer is accepted only if `report.validate_report` finds no problem:

- `summary` and at least one claim; every claim lists evidence IDs that exist (E1-E4);
- a `quote`, if present, appears verbatim in the E3 text;
- every hex token of 7-40 characters containing a digit is a SHA from E4;
- no mention of an evidence ID that does not exist.

One retry; then the template stays and `report_note` says why (Ollama down, or the first rejection reasons). Extra fields from the model (for example an `action`) are discarded by `clean_report`. The action is never read from the model.

## 6. Approval (`actions.py`)

- Reason of at least 15 characters for approve and for reject.
- If `seconds_to_decide` (now minus first page view; never viewed counts as 0) is under 10 s, the first submit is answered with a challenge and nothing is stored; resubmitting with `confirm=yes` records the decision with `confirmed_fast = 1`.
- `approve` only when the proposed action is `rollback_previous`; an incident without a proposal can only be rejected (closed).
- Approve: record decision, then call Jenkins `POST /job/<job>/buildWithParameters?ROLLBACK_TO=<previous_good_sha>&INCIDENT_ID=<id>` with basic auth (user + API token). The SHA comes from the stored incident, never from the request, and is regex-checked again. On success the suspect deploy gets `marked_bad = 1`. If Jenkins refuses, the decision stays in the audit table and the incident becomes `rollback_failed` with the reason.
- Replay incidents record the decision and never call Jenkins.

## 7. Recorded incidents and the replay gate

`ops/copilot/tests/incidents/*.json` (8 files): `bad_release`, `chaos_after_docs_deploy`, `no_recent_deploy`, `two_deploys`, `no_baseline`, `old_deploy_with_overlap`, `log_injection`, `marked_bad_excluded`. Each holds a synthetic ratio series, request rate, error records and deploys (times in seconds relative to the alert start) plus the expected suspect, confidence, action and previous good SHA. `tests/test_replay_gate.py` requires a 100% match, and also that the template report of every case passes the validator and that the injection case changes nothing. The gate is a regression test for the deterministic analyzer, not a measure of LLM quality.

## 8. Security notes

- Untrusted text (log messages, commit messages) is rendered through Jinja autoescape (tested with a `<script>` payload) and placed inside a data block in the LLM prompt.
- No Docker socket and no shared volume with the app; the only app interface is `/internal/recent-errors` (lab only, no authentication).
- The Jenkins token lives in `ops/.env` (gitignored) and is sent only to Jenkins.
- The copilot UI has no login and no CSRF protection: lab only.
