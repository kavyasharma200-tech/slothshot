"""Talk to the sloth from a terminal.

  slothshot up                      Temporal, the worker and the web app, in one go
  slothshot doctor                  checks Python, Temporal, Ollama and the model
  slothshot demo                    draws 20 sample screenshots to tidy
  slothshot tidy ~/Pictures/Screenshots --apply-after 10m
  slothshot tidy ~/Pictures/Screenshots --night 01:30 --model qwen2.5:1.5b
  slothshot status | nap | wake | approve | veto | undo
  slothshot skip 3
  slothshot schedule ~/Pictures/Screenshots --at 01:30
"""

import argparse
import asyncio
import platform
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleCalendarSpec,
    ScheduleRange,
    ScheduleSpec,
    WorkflowUpdateFailedError,
)
from temporalio.service import RPCError

from slothshot import __version__
from slothshot.shared import DEFAULT_MODEL, LAST_ID, OLLAMA_URL, SLOTH_HOME, TASK_QUEUE, TEMPORAL_ADDRESS, TidyInput
from slothshot.workflows import TidyScreenshots


def minutes(text: str) -> float:
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([smhd])", text.strip())
    if not m:
        raise argparse.ArgumentTypeError("use a number and a unit, like 30s, 10m, 8h or 1d")
    return float(m.group(1)) * {"s": 1 / 60, "m": 1, "h": 60, "d": 1440}[m.group(2)]


def next_local(hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    now = datetime.now().astimezone()
    at = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return at if at > now else at + timedelta(days=1)


def workflow_id(args) -> str:
    if getattr(args, "id", None):
        return args.id
    if not LAST_ID.exists():
        sys.exit("No sloth has been started yet. Run: slothshot tidy <folder>")
    return LAST_ID.read_text().strip()


async def start_tidy(
    client: Client,
    folder: str,
    *,
    apply_after_minutes: float = 480.0,
    undo_window_minutes: float = 1440.0,
    night: Optional[str] = None,
    include_all_images: bool = False,
    model: Optional[str] = None,
    items_per_run: int = 25,
) -> str:
    """Starts one tidy run and remembers it as the last one. Used by the CLI and the web API."""
    folder = str(Path(folder).expanduser().resolve())
    model = model or DEFAULT_MODEL
    not_before = next_local(night).astimezone(timezone.utc).isoformat() if night else None
    wf_id = f"slothshot-{Path(folder).name.lower().replace(' ', '-')}-{datetime.now():%Y%m%d-%H%M%S}"
    await client.start_workflow(
        TidyScreenshots.run,
        TidyInput(
            folder=folder,
            apply_after_minutes=apply_after_minutes,
            undo_window_minutes=undo_window_minutes,
            not_before=not_before,
            include_all_images=include_all_images,
            model=model,
            items_per_run=items_per_run,
        ),
        id=wf_id,
        task_queue=TASK_QUEUE,
        memo={"folder": folder, "model": model},
    )
    LAST_ID.parent.mkdir(parents=True, exist_ok=True)
    LAST_ID.write_text(wf_id)
    return wf_id


async def talk(args) -> None:
    """Every command that only needs a Temporal client."""
    try:
        client = await Client.connect(args.temporal)
    except Exception as err:
        sys.exit(f"Can't reach Temporal at {args.temporal} ({err}). Start everything with: slothshot up")

    if args.cmd == "tidy":
        if not Path(args.folder).expanduser().is_dir():
            sys.exit(f"{args.folder} isn't a folder.")
        wf_id = await start_tidy(
            client,
            args.folder,
            apply_after_minutes=args.apply_after,
            undo_window_minutes=args.undo_window,
            night=args.night,
            include_all_images=args.all,
            model=args.model,
            items_per_run=args.per_run,
        )
        print(f"Started {wf_id}")
        print("  watch it:     http://localhost:8765/app")
        print(f"  its history:  http://localhost:8233/namespaces/default/workflows/{wf_id}")
        return

    if args.cmd == "schedule":
        folder = str(Path(args.folder).expanduser().resolve())
        at_utc = next_local(args.at).astimezone(timezone.utc)
        await client.create_schedule(
            "slothshot-nightly",
            Schedule(
                action=ScheduleActionStartWorkflow(
                    TidyScreenshots.run,
                    TidyInput(folder=folder, apply_after_minutes=args.apply_after, model=args.model),
                    id="slothshot-nightly",
                    task_queue=TASK_QUEUE,
                    memo={"folder": folder, "model": args.model},
                ),
                spec=ScheduleSpec(
                    calendars=[ScheduleCalendarSpec(hour=[ScheduleRange(at_utc.hour)], minute=[ScheduleRange(at_utc.minute)])]
                ),
            ),
        )
        print(f"Every night at {args.at} the sloth tidies {folder}. Set it once, forget it.")
        return

    handle = client.get_workflow_handle(workflow_id(args))
    try:
        if args.cmd == "status":
            st = await handle.query(TidyScreenshots.status)
            done = sum(1 for i in st.items if i.status not in ("waiting", "reading", "naming"))
            print(f"{handle.id}: {st.phase}{' (napping)' if st.napping else ''}, {done}/{len(st.items)} looked at, run {st.runs}")
            if st.apply_at and st.phase == "waiting":
                print(f"  moves at {datetime.fromisoformat(st.apply_at).astimezone():%H:%M} unless you veto")
            for n, it in enumerate(st.items):
                after = f"{it.category}/{it.filename}" if it.filename else it.note
                print(f"  {n:>3} {it.status:<8} {it.name}  ->  {after}")
        elif args.cmd in ("nap", "wake"):
            await handle.signal(args.cmd)
            print("Napping." if args.cmd == "nap" else "Awake.")
        elif args.cmd == "skip":
            await handle.signal(TidyScreenshots.skip, args.index)
            print(f"Skipping {args.index}.")
        else:
            print(await handle.execute_update(args.cmd))
    except WorkflowUpdateFailedError as err:
        print(f"No: {err.cause.message if err.cause else err}")
    except RPCError as err:  # e.g. the run has already finished, or there's no run with that id
        sys.exit(f"No: {err.message}")


async def _reachable(address: str) -> bool:
    try:
        await asyncio.wait_for(Client.connect(address), 3)
        return True
    except Exception:
        return False


def doctor(address: str) -> int:
    """Plain checks, each with a one-line fix. Returns the exit code."""
    from slothshot import ollama

    failed = 0

    def check(good: bool, what: str, fix: str = "", soft: bool = False) -> None:
        nonlocal failed
        print(f"  {'ok' if good else ('--' if soft else '!!')}  {what}")
        if not good:
            print(f"      fix: {fix}")
            failed += 0 if soft else 1

    print(f"slothshot {__version__} doctor (home: {SLOTH_HOME})")
    good = (3, 10) <= sys.version_info[:2] < (3, 13)
    check(good, f"Python {platform.python_version()}", "use Python 3.10 to 3.12: uv tool install --python 3.12 git+https://github.com/kavyasharma200-tech/slothshot")
    try:
        import rapidocr_onnxruntime  # noqa: F401  (loads onnxruntime's DLLs, the usual thing to break)

        check(True, "OCR engine (RapidOCR) loads")
    except Exception as err:
        check(False, f"OCR engine (RapidOCR) won't load: {err}", "reinstall: uv tool install --force --python 3.12 git+https://github.com/kavyasharma200-tech/slothshot")
    if asyncio.run(_reachable(address)):
        check(True, f"Temporal is running at {address}")
    else:
        check(False, f"Temporal isn't running at {address}", "nothing to do: `slothshot up` starts a local one for you", soft=True)
    try:
        pulled = ollama.models()
        check(True, f"Ollama is running at {OLLAMA_URL} ({len(pulled)} models)")
    except Exception:
        pulled = None
        check(False, f"Ollama isn't answering at {OLLAMA_URL}", "install it from https://ollama.com/download (Windows: winget install Ollama.Ollama) and open it")
    if pulled is not None:
        good = ollama.has(DEFAULT_MODEL, pulled)
        check(good, f"model {DEFAULT_MODEL} is {'pulled' if good else 'not pulled yet'}", f"slothshot pull {DEFAULT_MODEL}")
    print("All good. Start it with: slothshot up" if not failed else f"{failed} thing(s) to fix.")
    return 1 if failed else 0


def pull(model: str) -> int:
    from slothshot import ollama

    print(f"Pulling {model} into Ollama...")
    shown = None
    try:
        for done, total, status in ollama.pull(model):
            line = f"  {status[:44]:<44} {int(done * 100 / total) if total else 0:>3}%"
            if line != shown:
                print(f"\r{line}", end="", flush=True)
                shown = line
    except Exception as err:
        print()
        print(f"Couldn't pull {model}: {err}")
        return 1
    print(f"\n{model} is ready.")
    return 0


def main(argv=None) -> None:
    conn = argparse.ArgumentParser(add_help=False)
    conn.add_argument("--temporal", default=TEMPORAL_ADDRESS, metavar="HOST:PORT", help=f"Temporal server (default {TEMPORAL_ADDRESS})")

    p = argparse.ArgumentParser(prog="slothshot", description="A slow, steady screenshot tidier: a local model inside a durable Temporal workflow.")
    p.add_argument("--version", action="version", version=f"slothshot {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="command")

    u = sub.add_parser("up", parents=[conn], help="run everything: Temporal, the worker and the web app")
    u.add_argument("--port", type=int, default=8765, help="web app port (default 8765)")
    u.add_argument("--no-browser", action="store_true", help="don't open the browser")
    sub.add_parser("worker", parents=[conn], help="run only the worker, in the foreground")
    d = sub.add_parser("demo", help="draw 20 sample screenshots to tidy")
    d.add_argument("folder", nargs="?", help=f"where (default {SLOTH_HOME / 'demo-screenshots'})")
    sub.add_parser("doctor", parents=[conn], help="check that everything slothshot needs is in place")
    pl = sub.add_parser("pull", help="download a model into Ollama")
    pl.add_argument("model", nargs="?", default=DEFAULT_MODEL)

    t = sub.add_parser("tidy", parents=[conn], help="start tidying a folder")
    t.add_argument("folder")
    t.add_argument("--apply-after", type=minutes, default=480.0, help="move files after this long unless you veto (default 8h)")
    t.add_argument("--undo-window", type=minutes, default=1440.0, help="how long you can undo (default 1d)")
    t.add_argument("--night", metavar="HH:MM", help="sleep until this local time before starting")
    t.add_argument("--all", action="store_true", help="every image, not only ones named like screenshots")
    t.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model that names the screenshots (default {DEFAULT_MODEL})")
    t.add_argument("--per-run", type=int, default=25, help="continue-as-new after this many screenshots (default 25)")
    for name, what in (
        ("status", "where the sloth is and its rename plan"),
        ("nap", "pause after the screenshot in hand"),
        ("wake", "carry on, or start now instead of at --night"),
        ("approve", "move the files as soon as every screenshot has a name"),
        ("veto", "move nothing"),
        ("undo", "put every moved file back"),
    ):
        sub.add_parser(name, parents=[conn], help=what).add_argument("--id", help="run id (default: the last one)")
    s = sub.add_parser("skip", parents=[conn], help="leave one screenshot alone")
    s.add_argument("index", type=int)
    s.add_argument("--id")
    sc = sub.add_parser("schedule", parents=[conn], help="tidy a folder every night")
    sc.add_argument("folder")
    sc.add_argument("--at", default="01:30", metavar="HH:MM")
    sc.add_argument("--apply-after", type=minutes, default=360.0)
    sc.add_argument("--model", default=DEFAULT_MODEL)
    args = p.parse_args(argv)

    if args.cmd == "up":
        from slothshot import up

        try:
            asyncio.run(up.serve(port=args.port, open_browser=not args.no_browser, address=args.temporal))
        except KeyboardInterrupt:
            pass
    elif args.cmd == "worker":
        from slothshot import worker

        worker.run(args.temporal)
    elif args.cmd == "demo":
        from slothshot import demo

        demo.main(args.folder)
    elif args.cmd == "doctor":
        sys.exit(doctor(args.temporal))
    elif args.cmd == "pull":
        sys.exit(pull(args.model))
    else:
        asyncio.run(talk(args))


if __name__ == "__main__":
    main()
