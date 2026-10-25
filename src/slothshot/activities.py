"""Everything that touches the outside world: the disk, the OCR model and the local LLM.

The workflow never does any of this itself. Temporal records each activity's result in the
workflow's history, so a finished OCR pass or LLM answer is never paid for twice, even if
the worker dies one second later.
"""

import concurrent.futures
import json
import logging
import os
import random
import re
import shutil
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

import httpx
from temporalio import activity
from temporalio.exceptions import ApplicationError

from slothshot.shared import CATEGORIES, CHAOS_FILE, OLLAMA_URL, MoveRequest, NameRequest, NameResult, Shot, TidyState

SCREENSHOT_NAME = re.compile(r"^(screenshot|screen shot|capture|snip|image|img_|photo)", re.I)
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
GENERIC = {"screenshot", "image", "picture", "text", "unknown", "untitled", "file", "screen", "page", "details", "info", "information", "content", "data"}

log = logging.getLogger("sloth")

_ocr = None
_ocr_lock = threading.Lock()


def chaos_rate() -> float:
    """Fraction of OCR/LLM calls that fail on purpose, to show retries on camera. 0 in normal use.

    Read on every call, so the web page's chaos dial takes effect without restarting the worker.
    """
    try:
        raw = CHAOS_FILE.read_text().strip()
    except OSError:
        raw = os.environ.get("SLOTH_CHAOS", "0")
    try:
        return min(max(float(raw or 0), 0.0), 0.9)
    except ValueError:
        return 0.0


def _chaos(what: str) -> None:
    rate = chaos_rate()
    if rate and random.random() < rate:
        raise RuntimeError(f"chaos: {what} dropped the connection (chaos {rate:g})")


def _with_heartbeat(fn, *args):
    """Run a slow call while heartbeating, so Temporal notices within seconds if this worker dies."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(fn, *args)
        while True:
            try:
                return fut.result(timeout=3)
            except concurrent.futures.TimeoutError:
                activity.heartbeat()


@activity.defn
def scan_folder(folder: str, include_all_images: bool) -> List[Shot]:
    root = Path(folder)
    if not root.is_dir():
        raise ApplicationError(f"{folder} is not a folder", non_retryable=True)
    shots = []
    for p in root.iterdir():
        if not p.is_file() or p.suffix.lower() not in IMAGE_TYPES:
            continue
        if not include_all_images and not SCREENSHOT_NAME.match(p.name):
            continue
        taken = datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")
        shots.append(Shot(path=str(p.resolve()), name=p.name, taken=taken))
    shots.sort(key=lambda s: s.taken)
    activity.logger.info("found %d screenshots in %s", len(shots), folder)
    return shots


def _ocr_text(path: str) -> str:
    global _ocr
    with _ocr_lock:
        if _ocr is None:
            from rapidocr_onnxruntime import RapidOCR

            _ocr = RapidOCR()
        result, _ = _ocr(path)
    if not result:
        return ""
    # Each hit is [box, text, score]; keep confident lines in reading order (top to bottom, left to right).
    lines = [(box[0][1] // 12, box[0][0], text) for box, text, score in result if float(score) > 0.5]
    lines.sort()
    return "\n".join(t for _, _, t in lines)


@activity.defn
def read_screenshot(path: str) -> str:
    if not Path(path).exists():
        raise ApplicationError(f"{path} is gone", non_retryable=True, type="Missing")
    log.info("reading   %s (try %d)", Path(path).name, activity.info().attempt)
    _chaos("the OCR model")
    try:
        text = _with_heartbeat(_ocr_text, path)
    except Exception as err:  # a corrupt image will never get better, so don't retry it
        if "chaos" in str(err):
            raise
        raise ApplicationError(f"could not read image: {err}", non_retryable=True, type="Unreadable")
    return text[:1500]


SYSTEM = (
    "You file screenshots. You get the text that OCR read from one screenshot. "
    'Reply with JSON: {"category": ..., "name": ...}.\n'
    "category is one of: code (source code, pull requests), errors (error messages, stack traces, failed commands), "
    "receipts (bills, invoices, payments), chats (message threads), travel (tickets, boarding passes, flights), "
    "articles (articles, blog posts, docs), social (social media posts), shopping (products, carts, deliveries), "
    "notes (notes, lists, passwords, recipes, to-dos), calendar (appointments, events), other.\n"
    "name is 3 to 6 lowercase words joined by hyphens, copied from the most specific words in the text: "
    "names of products, shops, people, places, errors and amounts. "
    'Examples: "flight-del-to-bom-seat-22a", "postgres-connection-refused-port-5432", "dhaba-dinner-bill-1200". '
    "Never use vague words like screenshot, details, info or page."
)

SCHEMA = {
    "type": "object",
    "properties": {"category": {"type": "string", "enum": CATEGORIES}, "name": {"type": "string"}},
    "required": ["category", "name"],
}


def _slug(raw: str) -> str:
    words = re.sub(r"[^a-z0-9]+", " ", raw.lower()).split()
    words = list(dict.fromkeys(w[:20] for w in words if w not in GENERIC))  # drops repeats like "paid-250-paid"
    return "-".join(words[:7])


def _grounded(slug: str, text: str) -> int:
    """How many words of the name really appear on the screenshot."""
    seen = re.sub(r"[^a-z0-9]+", " ", text.lower())
    words = set(seen.split())
    return sum(1 for w in slug.split("-") if w in words or (len(w) > 3 and w in seen))


def _ask_model(req: NameRequest, temperature: float) -> dict:
    body = {
        "model": req.model,
        "stream": False,
        "format": SCHEMA,
        "keep_alive": "30m",
        "options": {"temperature": temperature, "num_ctx": 2048},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Taken {req.taken[:10]}. Text on the screenshot:\n---\n{req.text}\n---"},
        ],
    }
    r = httpx.post(f"{OLLAMA_URL}/api/chat", json=body, timeout=280)
    if r.status_code == 404:
        # Still retried: it starts working the moment the model is pulled.
        raise RuntimeError(f"Ollama doesn't have {req.model} yet. Pull it with: slothshot pull {req.model}")
    r.raise_for_status()
    return json.loads(r.json()["message"]["content"])


@activity.defn
def name_screenshot(req: NameRequest) -> NameResult:
    attempt = activity.info().attempt
    log.info("naming    %s (try %d, %s)", req.name, attempt, req.model)
    _chaos("the local model server")
    # Each retry thinks a little more loosely, so a stuck small model gets unstuck.
    answer = _with_heartbeat(_ask_model, req, min(0.2 + 0.2 * (attempt - 1), 1.0))
    category = answer.get("category") if answer.get("category") in CATEGORIES else "other"
    slug = _slug(str(answer.get("name", "")))
    if len(slug.split("-")) >= 2 and len(slug) <= 70 and _grounded(slug, req.text) >= 2:
        log.info("          -> %s/%s", category, slug)
        return NameResult(category=category, slug=slug, tries=attempt)
    if attempt < 5:
        # A 1B model sometimes answers with a vague name that isn't on the screenshot at all.
        # Raise, and Temporal asks again (a little warmer each time). A weak answer is retried after
        # 1 s; only real outages, like Ollama being closed, get the policy's slow backoff.
        log.info("          !! weak name %r, asking again", answer.get("name"))
        raise ApplicationError(
            f"weak name {answer.get('name')!r}, asking again", type="WeakAnswer", next_retry_delay=timedelta(seconds=1)
        )
    fallback = _slug(" ".join(req.text.split()[:5])) or "unnamed"
    return NameResult(category="other", slug=fallback, tries=attempt, note="model never gave a good name; used the first words")


@activity.defn
def move_file(req: MoveRequest) -> str:
    """Idempotent: if a retry finds the file already moved, it reports the move instead of failing."""
    src = Path(req.src)
    dest_dir = Path(req.folder) / req.category
    dest = dest_dir / req.filename
    if not src.exists():
        if dest.exists():
            return str(dest)
        raise ApplicationError(f"{src.name} disappeared before it could move", non_retryable=True)
    dest_dir.mkdir(exist_ok=True)
    n = 2
    while dest.exists():
        dest = dest_dir / f"{Path(req.filename).stem}-{n}{Path(req.filename).suffix}"
        n += 1
    shutil.move(str(src), str(dest))
    log.info("moved     %s -> %s/%s", src.name, req.category, dest.name)
    return str(dest)


@activity.defn
def put_back(original: str, moved_to: str) -> None:
    """The compensation for move_file. Also idempotent."""
    if Path(original).exists() or not Path(moved_to).exists():
        return
    shutil.move(moved_to, original)
    log.info("put back  %s", Path(original).name)
    try:
        Path(moved_to).parent.rmdir()  # only removes the category folder if it is now empty
    except OSError:
        pass


@activity.defn
def write_report(folder: str, state: TidyState) -> str:
    rows = []
    for it in state.items:
        if it.status in ("moved", "named"):
            new = f"{it.category}/{it.filename}"
        elif it.status == "undone":
            new = f"put back (was {it.category}/{it.filename})"
        else:
            new = f"(left alone: {it.note or it.status})"
        tries = f" ({it.tries} tries)" if it.tries > 1 else ""
        rows.append(f"| {it.name} | {new}{tries} |")
    text = (
        f"# Slothshot report\n\nPhase: **{state.phase}**. {len(state.items)} screenshots looked at "
        f"over {state.runs} workflow run(s).\n\n| Before | After |\n|---|---|\n" + "\n".join(rows) + "\n"
    )
    out = Path(folder) / "slothshot-report.md"
    out.write_text(text, encoding="utf-8")
    return str(out)
