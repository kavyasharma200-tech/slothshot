"""Types shared by the workflow, the activities, the CLI and the web page."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

TASK_QUEUE = "slothshot"
TEMPORAL_ADDRESS = os.environ.get("SLOTHSHOT_TEMPORAL", "localhost:7233")
# 127.0.0.1, not localhost: Windows tries ::1 first, and Ollama only listens on IPv4 (costs ~2 s a call).
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.environ.get("SLOTH_MODEL", "gemma3:1b")

# Everything slothshot keeps on disk: the last run's id, the chaos dial, logs, the Temporal db.
SLOTH_HOME = Path(os.environ.get("SLOTHSHOT_HOME", Path.home() / ".slothshot"))
LAST_ID = SLOTH_HOME / "last-id"
CHAOS_FILE = SLOTH_HOME / "chaos"
DEMO_FOLDER = SLOTH_HOME / "demo-screenshots"

CATEGORIES = [
    "code",
    "errors",
    "receipts",
    "chats",
    "travel",
    "articles",
    "social",
    "shopping",
    "notes",
    "calendar",
    "other",
]


@dataclass
class Shot:
    """One screenshot found on disk."""

    path: str
    name: str
    taken: str  # ISO date-time from the file's modified time


@dataclass
class NameRequest:
    path: str
    name: str
    taken: str
    text: str
    model: str = "gemma3:1b"


@dataclass
class NameResult:
    category: str
    slug: str  # "stripe-invoice-failed-payment"
    tries: int = 1
    note: str = ""


@dataclass
class MoveRequest:
    src: str
    folder: str
    category: str
    filename: str


@dataclass
class Item:
    path: str
    name: str
    taken: str
    status: str = "waiting"  # waiting, reading, naming, named, no-text, failed, skipped, moved, undone
    text: str = ""  # a short preview of what OCR read
    category: str = ""
    filename: str = ""  # the new name, decided before anything moves
    final_path: str = ""
    tries: int = 0
    note: str = ""


@dataclass
class TidyState:
    folder: str = ""
    items: List[Item] = field(default_factory=list)
    cursor: int = 0
    phase: str = "starting"  # starting, sleeping, reading, waiting, moving, done, vetoed, undone, rolled-back
    napping: bool = False
    decision: Optional[str] = None  # "approve" or "veto"
    apply_at: Optional[str] = None
    undo_until: Optional[str] = None
    report: str = ""
    runs: int = 1  # how many times the workflow has continued-as-new


@dataclass
class TidyInput:
    folder: str
    apply_after_minutes: float = 480.0  # say nothing and it applies the plan after this long
    undo_window_minutes: float = 24 * 60.0
    not_before: Optional[str] = None  # ISO time in UTC; the sloth sleeps until then
    include_all_images: bool = False
    model: str = "gemma3:1b"  # the Ollama model that names this run's screenshots
    items_per_run: int = 25  # continue-as-new after this many, so history stays small
    state: Optional[TidyState] = None  # carried across continue-as-new
