"""Turns a real workflow history into the data the story page replays.

  temporal workflow show -w <id> --output json > tests/histories/run1-kills-and-undo.json
  python scripts/export_night.py tests/histories/run1-kills-and-undo.json src/slothshot/web/assets/night

Everything on the page's "night" comes from this file: the screenshots, what OCR read, every
weak answer the model gave, the heartbeat timeout after the worker was killed, the approve and
the undo. Folder paths are dropped, only file names are kept.
"""

import base64
import json
import sys
from datetime import datetime
from pathlib import Path


def payload(p):
    items = (p or {}).get("payloads") or []
    out = []
    for it in items:
        raw = base64.b64decode(it.get("data", "") or b"")
        out.append(json.loads(raw) if raw else None)
    return out


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")[:26] + "+00:00" if "." in s else s.replace("Z", "+00:00"))


def short(t):
    return "".join(w.capitalize() for w in t.replace("EVENT_TYPE_", "").split("_"))


def main(history_path, out_dir):
    events = json.loads(Path(history_path).read_text(encoding="utf-8"))["events"]
    t0 = ts(events[0]["eventTime"])
    scheduled = {}  # scheduled event id -> (activity, input)
    shots = {}  # file name -> dict
    order = []
    marks = []
    moments = []

    def at(e):
        return round((ts(e["eventTime"]) - t0).total_seconds(), 2)

    for e in events:
        kind = short(e["eventType"])
        act = None
        if kind == "ActivityTaskScheduled":
            a = e["activityTaskScheduledEventAttributes"]
            act = a["activityType"]["name"]
            scheduled[e["eventId"]] = (act, payload(a.get("input")))
        elif kind in ("ActivityTaskStarted", "ActivityTaskCompleted", "ActivityTaskFailed", "ActivityTaskTimedOut"):
            key = {"ActivityTaskStarted": "activityTaskStartedEventAttributes",
                   "ActivityTaskCompleted": "activityTaskCompletedEventAttributes",
                   "ActivityTaskFailed": "activityTaskFailedEventAttributes",
                   "ActivityTaskTimedOut": "activityTaskTimedOutEventAttributes"}[kind]
            a = e[key]
            act, args = scheduled[a["scheduledEventId"]]
            if kind == "ActivityTaskStarted":
                attempt = int(a.get("attempt", 1))
                failure = a.get("lastFailure") or {}
                if attempt > 1:
                    timeout = (failure.get("timeoutFailureInfo") or {}).get("timeoutType", "")
                    why = "heartbeat" if "HEARTBEAT" in timeout else failure.get("message", "")
                    if act == "name_screenshot":
                        shots[args[0]["name"]]["last_failure"] = why
                    if why == "heartbeat":
                        moments.append({"t": at(e), "kind": "heartbeat-timeout", "activity": act, "attempt": attempt,
                                        "shot": args[0]["name"] if act == "name_screenshot" else None})
            if kind == "ActivityTaskCompleted":
                result = payload(a.get("result"))
                result = result[0] if result else None
                if act == "scan_folder":
                    for s in result:
                        shots[s["name"]] = {"name": s["name"], "taken": s["taken"]}
                        order.append(s["name"])
                elif act == "read_screenshot":
                    name = Path(args[0]).name
                    shots[name]["ocr"] = " ".join((result or "").split())[:240]
                    shots[name]["read_at"] = at(e)
                elif act == "name_screenshot":
                    s = shots[args[0]["name"]]
                    s.update(category=result["category"], slug=result["slug"], tries=result["tries"],
                             fallback=bool(result.get("note")), named_at=at(e))
                elif act == "move_file":
                    shots[Path(args[0]["src"]).name]["moved_to"] = f"{args[0]['category']}/{Path(result).name}"
        elif kind == "WorkflowExecutionUpdateAccepted":
            name = e["workflowExecutionUpdateAcceptedEventAttributes"]["acceptedRequest"]["input"]["name"]
            moments.append({"t": at(e), "kind": f"update-{name}"})
        elif kind == "WorkflowExecutionCompleted":
            result = payload(e["workflowExecutionCompletedEventAttributes"].get("result"))
            moments.append({"t": at(e), "kind": "completed", "result": result[0] if result else None})
        marks.append([at(e), kind, act])

    started_input = payload(events[0]["workflowExecutionStartedEventAttributes"]["input"])[0]
    night = {
        "workflow": "TidyScreenshots",
        "started": events[0]["eventTime"],
        "events": len(events),
        "apply_after_minutes": started_input.get("apply_after_minutes"),
        "shots": [shots[n] for n in order],
        "moments": moments,
        "marks": marks,
    }
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "night.json").write_text(json.dumps(night, separators=(",", ":")), encoding="utf-8")
    named = [s for s in night["shots"] if s.get("slug")]
    print(f"{len(events)} events, {len(named)} named, {sum(s['tries'] for s in named)} model calls, "
          f"{sum(1 for s in named if s['fallback'])} fallbacks, {len(moments)} moments")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
