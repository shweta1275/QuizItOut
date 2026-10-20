import json
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import actions, config, db, deploys, incidents
from app.evidence import LiveSource, ReplaySource
from app.report import fmt_ts
from app.schemas import AlertPayload

BASE = Path(__file__).parent
INCIDENT_DIR = BASE.parent / "tests" / "incidents"



@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="IncidentPilot copilot", lifespan=lifespan)
templates = Jinja2Templates(directory=BASE / "templates")
templates.env.filters["ts"] = fmt_ts
templates.env.filters["pct"] = lambda v: "n/a" if v is None else f"{v * 100:.1f}%"


def _parse_starts_at(value: str | None) -> float:
    if not value:
        return time.time()
    trimmed = re.sub(r"(\.\d{6})\d+", r"\1", value)
    try:
        return datetime.fromisoformat(trimmed).timestamp()
    except ValueError:
        return time.time()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request,
        "list.html",
        {"incidents": incidents.list_incidents(), "deploys": deploys.list_deploys(10)},
    )


@app.post("/deploys")
def add_deploy(
    sha: str = Form(...),
    image: str = Form(""),
    commit_message: str = Form(""),
    files_changed: str = Form(""),
    status: str = Form("succeeded"),
    kind: str = Form("deploy"),
):
    try:
        new_id = deploys.record_deploy(sha, image, commit_message, files_changed, status, kind)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return {"id": new_id}


@app.get("/deploys")
def list_deploys_json():
    return deploys.list_deploys()


@app.post("/alert")
def alert(payload: AlertPayload, background: BackgroundTasks):
    created = []
    for a in payload.alerts:
        name = a.labels.get("alertname", "unknown")
        if a.status == "resolved":
            incidents.mark_alert_resolved(name)
        elif incidents.find_open_for_alert(name) is None:
            new_id = incidents.create_incident(name, _parse_starts_at(a.startsAt), LiveSource())
            background.add_task(incidents.upgrade_report, new_id)
            created.append(new_id)
    return {"created": created}


@app.post("/dev/replay/{name}")
def replay(name: str, background: BackgroundTasks):
    if not config.settings.enable_replay:
        raise HTTPException(404, "Not found")
    path = INCIDENT_DIR / f"{name}.json"
    if not re.fullmatch(r"[a-z0-9_]+", name) or not path.exists():
        raise HTTPException(404, f"No recorded incident '{name}'")
    source = ReplaySource(json.loads(path.read_text()))
    new_id = incidents.create_incident(
        "HighErrorRate", source.alert_start, source, is_replay=True, replay_name=name
    )
    background.add_task(incidents.upgrade_report, new_id)
    return JSONResponse({"id": new_id, "url": f"/incidents/{new_id}", "replay": name})


def _detail(request: Request, incident_id: int, **extra):
    inc = incidents.get_incident(incident_id)
    if inc is None:
        raise HTTPException(404, "Incident not found")
    ctx = {"inc": inc, "decisions": incidents.decisions_for(incident_id), "challenge": None, "error": ""}
    return templates.TemplateResponse(request, "detail.html", {**ctx, **extra})


@app.get("/incidents/{incident_id}", response_class=HTMLResponse)
def detail(request: Request, incident_id: int):
    incidents.mark_viewed(incident_id)
    return _detail(request, incident_id)


@app.get("/incidents/{incident_id}/json")
def detail_json(incident_id: int):
    inc = incidents.get_incident(incident_id)
    if inc is None:
        raise HTTPException(404, "Incident not found")
    return inc


@app.post("/incidents/{incident_id}/rollback-result")
def rollback_result(incident_id: int, status: str = Form(...), sha: str = Form("")):
    if not actions.record_rollback_result(incident_id, status, sha):
        raise HTTPException(404, "No rollback pending for this incident")
    return {"ok": True}


@app.post("/incidents/{incident_id}/{decision}", response_class=HTMLResponse)
def decide(request: Request, incident_id: int, decision: str, reason: str = Form(""), confirm: str = Form("")):
    if decision not in ("approve", "reject"):
        raise HTTPException(404, "Not found")
    out = actions.decide(incident_id, decision, reason, confirmed=confirm == "yes")
    if out.challenge:
        return _detail(request, incident_id, challenge={"decision": decision, "reason": reason})
    if not out.ok:
        return _detail(request, incident_id, error=out.error)
    return RedirectResponse(f"/incidents/{incident_id}", status_code=303)
