"""Today's workflow code must replay yesterday's real runs event for event.

run1: three hard worker kills mid-run, then approve, 19 moves and an undo.
run2: the second run after a continue-as-new, then a veto.
"""

from pathlib import Path

import pytest
from temporalio.client import WorkflowHistory
from temporalio.worker import Replayer

from slothshot.workflows import TidyScreenshots

HISTORIES = Path(__file__).parent / "histories"


@pytest.mark.parametrize("name", ["run1-kills-and-undo.json", "run2-veto-after-continue.json"])
async def test_replays_recorded_history(name):
    history = WorkflowHistory.from_json(name, (HISTORIES / name).read_text(encoding="utf-8"))
    result = await Replayer(workflows=[TidyScreenshots]).replay_workflow(history)
    assert result.replay_failure is None
