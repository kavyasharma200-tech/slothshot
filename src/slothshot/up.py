"""`slothshot up`: Temporal, the worker and the web app from one command. Ctrl+C stops all three.

If no Temporal server answers, it starts a local dev server (the Temporal CLI is downloaded once
into ~/.slothshot/bin) with its history kept in ~/.slothshot/temporal.db, so runs survive restarts.
The worker runs as a child process that is started again whenever it dies, which is what lets
the web page pull its plug on purpose.
"""

import asyncio
import os
import signal
import socket
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import uvicorn
from temporalio.testing import WorkflowEnvironment

from slothshot import server
from slothshot.cli import _reachable
from slothshot.shared import SLOTH_HOME

RESTART_DELAY = 4  # seconds between a worker dying and the next one starting
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def say(text: str) -> None:
    print(f"{datetime.now():%H:%M:%S}  {text}", flush=True)


class Supervisor:
    """Keeps one worker process running. When it exits, for any reason, another starts 4 s later."""

    def __init__(self, address: str, log_path: Path) -> None:
        self.address = address
        self.log_path = log_path
        self.proc: Optional[subprocess.Popen] = None
        self.restarts = 0
        self.since: Optional[str] = None
        self.last_exit: Optional[str] = None
        self._stopping = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="worker-supervisor", daemon=True)

    @property
    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def info(self) -> dict:
        return {
            "alive": self.alive,
            "pid": self.proc.pid if self.alive else None,
            "restarts": self.restarts,
            "since": self.since if self.alive else None,
            "last_exit": self.last_exit,
            "managed": True,
        }

    def start(self) -> None:
        self._thread.start()

    def kill(self) -> Optional[int]:
        """Pulls the plug: TerminateProcess on Windows, SIGKILL elsewhere. No chance to say goodbye."""
        proc = self.proc
        if proc is None or proc.poll() is not None:
            return None
        proc.kill()
        return proc.pid

    def stop(self) -> None:
        self._stopping.set()
        proc = self.proc
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        self._thread.join(timeout=5)

    def _spawn(self) -> subprocess.Popen:
        env = dict(
            os.environ,
            SLOTHSHOT_TEMPORAL=self.address,
            SLOTHSHOT_HOME=str(SLOTH_HOME),
            PYTHONUNBUFFERED="1",
            PYTHONIOENCODING="utf-8",
        )
        # Its own process group, so Ctrl+C reaches only us and we decide when the worker stops.
        extra = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
        return subprocess.Popen(
            [sys.executable, "-m", "slothshot.worker"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            **extra,
        )

    def _loop(self) -> None:
        with open(self.log_path, "a", encoding="utf-8") as log:

            def note(text: str) -> None:
                say(text)
                log.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {text}\n")
                log.flush()

            while not self._stopping.is_set():
                try:
                    proc = self._spawn()
                except OSError as err:
                    note(f"couldn't start the worker: {err}")
                    if self._stopping.wait(RESTART_DELAY):
                        break
                    continue
                self.proc, self.since = proc, _now()
                note(f"worker started (pid {proc.pid})")
                for raw in proc.stdout:
                    line = raw.decode("utf-8", "replace").rstrip()
                    print(f"  worker | {line}", flush=True)
                    log.write(line + "\n")
                    log.flush()
                code = proc.wait()
                self.last_exit = _now()
                if self._stopping.is_set():
                    note("worker stopped")
                    break
                note(f"worker exited (code {code}); starting a new one in {RESTART_DELAY} s")
                if self._stopping.wait(RESTART_DELAY):
                    break
                self.restarts += 1


def _port_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _interrupt(signum, frame) -> None:
    raise KeyboardInterrupt


async def serve(port: int = 8765, open_browser: bool = True, address: str = "localhost:7233") -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # a worker line with ₹ in it must not crash a cp1252 console
    SLOTH_HOME.mkdir(parents=True, exist_ok=True)
    if _port_busy(port):
        sys.exit(f"Port {port} is already in use. Is slothshot already running? Or try: slothshot up --port {port + 1}")

    # uvicorn re-raises the signal that stopped it once it has shut down; turning that into a plain
    # KeyboardInterrupt lets the cleanup below run instead of asyncio cancelling it halfway.
    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), _interrupt)

    host, _, temporal_port = address.rpartition(":")
    ui = f"http://localhost:{int(temporal_port) + 1000}"
    env = None
    if await _reachable(address):
        say(f"Temporal is already running at {address}.")
    elif host not in LOCAL_HOSTS:
        sys.exit(f"Can't reach Temporal at {address}, and it isn't on this machine, so slothshot can't start it.")
    else:
        say(f"No Temporal at {address}, so starting a local one (the first time downloads the Temporal CLI into {SLOTH_HOME / 'bin'}).")
        (SLOTH_HOME / "bin").mkdir(exist_ok=True)
        try:
            env = await WorkflowEnvironment.start_local(
                ip="127.0.0.1",
                port=int(temporal_port),
                ui=True,
                ui_port=int(temporal_port) + 1000,
                dev_server_database_filename=str(SLOTH_HOME / "temporal.db"),
                download_dest_dir=str(SLOTH_HOME / "bin"),
            )
        except Exception as err:
            sys.exit(f"Couldn't start Temporal: {err}\nRun one yourself (temporal server start-dev) and pass --temporal HOST:PORT.")
        say(f"Temporal started at {address} (history in {SLOTH_HOME / 'temporal.db'}).")

    server.runtime.address = address
    server.runtime.ui = ui
    server.runtime.started_by_us = env is not None
    supervisor = Supervisor(address, SLOTH_HOME / "worker.log")
    server.runtime.supervisor = supervisor
    supervisor.start()

    web = uvicorn.Server(uvicorn.Config(server.app, host="127.0.0.1", port=port, log_level="warning"))
    url = f"http://localhost:{port}/app"

    async def announce() -> None:
        while not web.started:
            await asyncio.sleep(0.1)
        say(f"Slothshot is up: {url}")
        say(f"Temporal UI:      {ui}")
        say("Ctrl+C stops everything.")
        if open_browser:
            webbrowser.open(url)

    announcing = asyncio.create_task(announce())
    try:
        await web.serve()
    except KeyboardInterrupt:
        pass
    finally:
        announcing.cancel()
        say("Stopping the worker...")
        await asyncio.to_thread(supervisor.stop)
        if env is not None:
            say("Stopping Temporal...")
            try:
                await env.shutdown()
            except Exception:
                pass  # Ctrl+C in the same console may have stopped it already
        say("Bye. Every run is kept in Temporal; `slothshot up` picks them up again.")
