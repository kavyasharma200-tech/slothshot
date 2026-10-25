"""The web app's API: start runs, watch them, answer the sloth, and pull the worker's plug on purpose.

  slothshot up                       -> http://localhost:8765/app (runs the worker too)
  uvicorn slothshot.server:app       (the API alone; the worker is then up to you)
"""

import asyncio
import json
import os
import re
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from temporalio.api.enums.v1 import EventType, PendingActivityState
from temporalio.client import Client, WorkflowHandle, WorkflowUpdateFailedError
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from slothshot import __version__, ollama
from slothshot.activities import chaos_rate
from slothshot.cli import start_tidy
from slothshot.demo import make as make_demo
from slothshot.shared import CHAOS_FILE, DEFAULT_MODEL, DEMO_FOLDER, LAST_ID, OLLAMA_URL, SLOTH_HOME, TEMPORAL_ADDRESS

WEB = Path(__file__).parent / "web"


class Runtime:
    """What `slothshot up` tells the API about the processes it looks after."""

    def __init__(self) -> None:
        self.address = TEMPORAL_ADDRESS
        self.ui = f"http://localhost:{int(TEMPORAL_ADDRESS.rpartition(':')[2]) + 1000}"
        self.started_by_us = False
        self.supervisor = None  # a slothshot.up.Supervisor when run by `slothshot up`


runtime = Runtime()
app = FastAPI(title="Slothshot", version=__version__)


@app.middleware("http")
async def only_from_here(request, call_next):
    """Writes must come from this app, not from another website the browser happens to have open.

    A custom header forces a CORS preflight, which other origins can't pass, so a page elsewhere
    can't start a night on your folder or pull the plug on your worker.
    """
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin", "")
        local = re.match(r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$", origin) if origin else True
        if request.headers.get("x-slothshot") != "1" or not local:
            return JSONResponse({"detail": "Writes are only accepted from the Slothshot app itself."}, status_code=403)
    return await call_next(request)

_client: Optional[Client] = None
_last_state: Dict[str, Any] = {}  # the last answer to each run's status query, for when no worker is up
_pulls: Dict[str, dict] = {}


async def temporal() -> Client:
    global _client
    if _client is None:
        try:
            _client = await asyncio.wait_for(Client.connect(runtime.address), 3)
        except Exception:
            raise HTTPException(503, f"Can't reach Temporal at {runtime.address}. Start everything with: slothshot up")
    return _client


def _id(wf: Optional[str]) -> str:
    if wf:
        return wf
    if LAST_ID.exists():
        return LAST_ID.read_text().strip()
    raise HTTPException(404, "No sloth started yet. Start one from the page, or run: slothshot tidy <folder>")


def _iso(ts) -> Optional[str]:
    """A protobuf Timestamp as ISO text, or None when it was never set."""
    if not ts.seconds and not ts.nanos:
        return None
    return datetime.fromtimestamp(ts.seconds + ts.nanos / 1e9, timezone.utc).isoformat()


def _rpc_fail(err: RPCError, wf_id: str):
    if err.status == RPCStatusCode.NOT_FOUND:
        raise HTTPException(404, f"No run called {wf_id}.")
    raise HTTPException(503, f"Temporal says: {err.message}")


async def _state(handle: WorkflowHandle):
    """Asks the workflow for its state. Queries need a live worker, so while the worker is down
    (say, right after the Lab pulled its plug) the last answer is returned and marked stale."""
    sup = runtime.supervisor
    if sup is not None and not sup.alive and handle.id in _last_state:
        return _last_state[handle.id], True
    try:
        state = await handle.query("status", rpc_timeout=timedelta(seconds=3))
    except (RPCError, asyncio.TimeoutError) as err:
        if handle.id in _last_state:
            return _last_state[handle.id], True
        if isinstance(err, RPCError) and err.status == RPCStatusCode.NOT_FOUND:
            raise HTTPException(404, f"No run called {handle.id}.")
        raise HTTPException(503, "The sloth's worker isn't answering yet. Is `slothshot up` running?")
    _last_state[handle.id] = state
    return state, False


# ---- health ----


def suggested_folders() -> List[str]:
    """The usual places screenshots pile up, if they exist on this machine."""
    home = Path.home()
    places = [home / "Pictures" / "Screenshots"]
    if os.name == "nt":
        roots = [os.environ.get(k) for k in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial")]
        roots += [str(p) for p in home.glob("OneDrive*")]
        places += [Path(r) / "Pictures" / "Screenshots" for r in dict.fromkeys(roots) if r]
    if sys.platform == "darwin":
        places += [home / "Desktop", home / "Documents" / "Screenshots"]
    seen, out = set(), []
    for p in places:
        try:
            key = str(p.resolve()).lower()
            if p.is_dir() and key not in seen:
                seen.add(key)
                out.append(str(p))
        except OSError:
            pass
    return out


async def _temporal_ok() -> bool:
    try:
        client = await temporal()
        return await client.service_client.check_health(timeout=timedelta(seconds=2))
    except Exception:
        return False


async def _ollama_models() -> Optional[List[str]]:
    try:
        async with httpx.AsyncClient(timeout=2) as http:
            r = await http.get(f"{OLLAMA_URL}/api/tags")
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return None


@app.get("/api/health")
async def health():
    temporal_ok, models = await asyncio.gather(_temporal_ok(), _ollama_models())
    sup = runtime.supervisor
    worker = sup.info() if sup else {"alive": False, "pid": None, "restarts": 0, "since": None, "last_exit": None, "managed": False}
    return {
        "version": __version__,
        "temporal": {"ok": temporal_ok, "address": runtime.address, "ui": runtime.ui, "started_by_us": runtime.started_by_us},
        "worker": worker,
        "ollama": {"ok": models is not None, "url": OLLAMA_URL, "models": models or []},
        "model": {"name": DEFAULT_MODEL, "present": ollama.has(DEFAULT_MODEL, models or [])},
        "chaos": chaos_rate(),
        "home": str(SLOTH_HOME),
        "demo_folder": str(DEMO_FOLDER),
        "suggested_folders": suggested_folders(),
    }


# ---- runs ----


@app.get("/api/runs")
async def runs():
    client = await temporal()
    newest: Dict[str, dict] = {}
    try:
        async for wf in client.list_workflows("WorkflowType = 'TidyScreenshots'", limit=200, rpc_timeout=timedelta(seconds=5)):
            row = newest.get(wf.id)
            if row and row["start"] >= wf.start_time.isoformat():
                continue  # continue-as-new leaves one execution per run; show only the newest
            memo = await wf.memo()
            newest[wf.id] = {
                "id": wf.id,
                "run_id": wf.run_id,
                "status": wf.status.name if wf.status else "UNKNOWN",
                "start": wf.start_time.isoformat(),
                "close": wf.close_time.isoformat() if wf.close_time else None,
                "folder": memo.get("folder"),
            }
    except RPCError as err:
        raise HTTPException(503, f"Temporal says: {err.message}")
    return {"runs": sorted(newest.values(), key=lambda r: r["start"], reverse=True)[:20]}


class NewRun(BaseModel):
    folder: str
    apply_after_minutes: float = Field(480.0, ge=0)
    undo_window_minutes: float = Field(1440.0, ge=0)
    night: Optional[str] = None
    include_all_images: bool = False
    model: Optional[str] = None


@app.post("/api/runs")
async def new_run(body: NewRun):
    folder = Path(body.folder).expanduser()
    if not body.folder.strip() or not folder.is_dir():
        raise HTTPException(400, f"{body.folder} isn't a folder on this computer.")
    if body.night and not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", body.night):
        raise HTTPException(400, "night must look like 01:30")
    client = await temporal()
    try:
        wf_id = await start_tidy(
            client,
            str(folder),
            apply_after_minutes=body.apply_after_minutes,
            undo_window_minutes=body.undo_window_minutes,
            night=body.night,
            include_all_images=body.include_all_images,
            model=(body.model or "").strip() or None,
        )
    except WorkflowAlreadyStartedError:
        raise HTTPException(409, "A run for this folder started this very second. Give it a moment.")
    except RPCError as err:
        raise HTTPException(503, f"Temporal says: {err.message}")
    return {"id": wf_id}


@app.post("/api/demo-folder")
async def demo_folder():
    try:
        count = await asyncio.to_thread(make_demo, DEMO_FOLDER)
    except OSError as err:
        raise HTTPException(409, f"Couldn't redraw the sample folder: {err}")
    return {"folder": str(DEMO_FOLDER.resolve()), "count": count}


# ---- one run ----


@app.get("/api/status")
async def status(id: Optional[str] = None):
    client = await temporal()
    handle = client.get_workflow_handle(_id(id))
    try:
        desc = await handle.describe()
    except RPCError as err:
        _rpc_fail(err, handle.id)
    state, stale = await _state(handle)
    result = None
    if desc.status and desc.status.name == "COMPLETED":
        result = await handle.result()
    memo = await desc.memo()
    pending = [
        {
            "activity": p.activity_type.name,
            "attempt": p.attempt,
            "state": PendingActivityState.Name(p.state).replace("PENDING_ACTIVITY_STATE_", ""),
            "last_failure": p.last_failure.message if p.HasField("last_failure") else None,
            "last_heartbeat": _iso(p.last_heartbeat_time),
            "last_started": _iso(p.last_started_time),
            "scheduled": _iso(p.scheduled_time),
        }
        for p in desc.raw_description.pending_activities
    ]
    return {
        "id": handle.id,
        "run": desc.run_id,
        "running": desc.status.name,
        "result": result,
        "model": memo.get("model") or DEFAULT_MODEL,
        "state": state,
        "stale": stale,
        "pending": pending,
        "temporal_ui": f"{runtime.ui}/namespaces/default/workflows/{quote(handle.id, safe='')}/{desc.run_id}/history",
    }


def _pascal(event_type: int) -> str:
    name = EventType.Name(event_type).replace("EVENT_TYPE_", "")
    return "".join(w.capitalize() for w in name.split("_"))


def _span(d) -> str:
    sec = d.seconds + d.nanos / 1e9
    if sec >= 3600:
        return f"{round(sec / 3600, 2):g}h"
    if sec >= 60:
        return f"{round(sec / 60, 2):g}m"
    return f"{round(sec, 1):g}s"


def _payload_text(payloads) -> Optional[str]:
    try:
        value = json.loads(payloads.payloads[0].data)
        return value if isinstance(value, str) else json.dumps(value)[:200]
    except Exception:
        return None


@app.get("/api/history")
async def history(id: Optional[str] = None, after: int = 0):
    client = await temporal()
    handle = client.get_workflow_handle(_id(id))
    try:
        desc = await handle.describe()
        events = [e async for e in client.get_workflow_handle(handle.id, run_id=desc.run_id).fetch_history_events()]
    except RPCError as err:
        _rpc_fail(err, handle.id)
    activity_of: Dict[int, str] = {}  # scheduled event id -> activity type
    attempt_of: Dict[int, int] = {}  # started event id -> attempt
    update_of: Dict[str, str] = {}  # update id -> update name
    out = []
    for e in events:
        activity = attempt = detail = None
        kind = e.WhichOneof("attributes")
        a = getattr(e, kind) if kind else None
        if kind == "activity_task_scheduled_event_attributes":
            activity = activity_of[e.event_id] = a.activity_type.name
        elif kind == "activity_task_started_event_attributes":
            activity = activity_of.get(a.scheduled_event_id)
            attempt = attempt_of[e.event_id] = a.attempt
            if a.HasField("last_failure"):
                detail = a.last_failure.message  # why the attempt before this one failed
        elif kind in (
            "activity_task_completed_event_attributes",
            "activity_task_failed_event_attributes",
            "activity_task_timed_out_event_attributes",
            "activity_task_canceled_event_attributes",
        ):
            activity = activity_of.get(a.scheduled_event_id)
            attempt = attempt_of.get(a.started_event_id)
            if hasattr(a, "failure") and a.HasField("failure"):
                detail = a.failure.message
        elif kind == "timer_started_event_attributes":
            detail = f"timer {_span(a.start_to_fire_timeout)}"
        elif kind == "workflow_execution_signaled_event_attributes":
            detail = a.signal_name
        elif kind == "workflow_execution_update_accepted_event_attributes":
            detail = update_of[a.protocol_instance_id] = a.accepted_request.input.name
        elif kind == "workflow_execution_update_admitted_event_attributes":
            detail = a.request.input.name
        elif kind == "workflow_execution_update_completed_event_attributes":
            detail = update_of.get(a.meta.update_id)
        elif kind == "workflow_execution_continued_as_new_event_attributes":
            detail = "continue-as-new"
        elif kind == "workflow_execution_started_event_attributes" and a.continued_execution_run_id:
            detail = "continued from the run before (continue-as-new)"
        elif kind == "workflow_execution_completed_event_attributes":
            detail = _payload_text(a.result)
        elif kind in ("workflow_execution_failed_event_attributes", "workflow_task_failed_event_attributes"):
            detail = a.failure.message
        elif kind == "workflow_execution_terminated_event_attributes":
            detail = a.reason
        if e.event_id > after:
            out.append({
                "id": e.event_id,
                "time": _iso(e.event_time),
                "type": _pascal(e.event_type),
                "activity": activity,
                "attempt": attempt,
                "detail": detail,
            })
    return {"run_id": desc.run_id, "events": out, "last": events[-1].event_id if events else 0}


class Act(BaseModel):
    action: str
    id: Optional[str] = None
    index: Optional[int] = None


@app.post("/api/act")
async def act(body: Act):
    client = await temporal()
    handle = client.get_workflow_handle(_id(body.id))
    try:
        if body.action in ("nap", "wake"):
            await handle.signal(body.action)
            return {"message": "Napping." if body.action == "nap" else "Awake."}
        if body.action == "skip":
            await handle.signal("skip", body.index)
            return {"message": "Skipped."}
        if body.action in ("approve", "veto", "undo"):
            return {"message": await handle.execute_update(body.action)}
    except WorkflowUpdateFailedError as err:
        raise HTTPException(409, err.cause.message if err.cause else str(err))
    except RPCError as err:
        _rpc_fail(err, handle.id)
    raise HTTPException(400, "unknown action")


@app.get("/api/shot")
async def shot(i: int, id: Optional[str] = None):
    client = await temporal()
    state, _ = await _state(client.get_workflow_handle(_id(id)))
    if not 0 <= i < len(state["items"]):
        raise HTTPException(404)
    item = state["items"][i]
    root = Path(state["folder"]).resolve()
    for candidate in (item.get("final_path"), item["path"]):
        if candidate:
            p = Path(candidate).resolve()
            if root in p.parents and p.exists():
                return FileResponse(p, headers={"Cache-Control": "max-age=3600"})
    raise HTTPException(404)


# ---- the Lab: break things on purpose ----


@app.post("/api/lab/kill")
async def lab_kill():
    sup = runtime.supervisor
    if sup is None:
        raise HTTPException(409, "The worker isn't run by slothshot up, so it can't be pulled from here.")
    pid = sup.kill()
    if pid is None:
        raise HTTPException(409, "The worker is already down. A new one starts in a few seconds.")
    from slothshot.up import RESTART_DELAY

    return {"killed": pid, "restart_in": RESTART_DELAY}


class Chaos(BaseModel):
    rate: float = Field(ge=0, le=0.9)


@app.post("/api/lab/chaos")
async def lab_chaos(body: Chaos):
    SLOTH_HOME.mkdir(parents=True, exist_ok=True)
    CHAOS_FILE.write_text(f"{body.rate:g}")
    return {"rate": body.rate}


# ---- Ollama models ----


class Pull(BaseModel):
    model: str = DEFAULT_MODEL


def _pull(job: dict) -> None:
    try:
        for done, total, _ in ollama.pull(job["model"]):
            job["completed"], job["total"] = done, total
        job["status"] = "done"
    except Exception as err:
        job["status"], job["error"] = "error", str(err) or type(err).__name__


@app.post("/api/ollama/pull")
async def ollama_pull(body: Pull):
    model = body.model.strip()
    if not model:
        raise HTTPException(400, "Which model? For example gemma3:1b")
    job = _pulls.get(model)
    if job is None or job["status"] != "pulling":
        job = _pulls[model] = {"model": model, "status": "pulling", "completed": 0, "total": 0, "error": None}
        threading.Thread(target=_pull, args=(job,), name=f"pull-{model}", daemon=True).start()
    return job


@app.get("/api/ollama/pull")
async def ollama_pull_status(model: str = DEFAULT_MODEL):
    return _pulls.get(model) or {"model": model, "status": "idle", "completed": 0, "total": 0, "error": None}


# ---- pages ----


@app.get("/", include_in_schema=False)
async def index():
    page = WEB / "index.html"
    if page.exists():
        return FileResponse(page)
    return RedirectResponse("/app")


@app.get("/app", include_in_schema=False)
async def app_page():
    return FileResponse(WEB / "app.html")


if (WEB / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")
