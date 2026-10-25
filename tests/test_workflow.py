"""The sloth's promises, checked on a time-skipping Temporal with fake activities.

The fakes are registered under the real activity names, so the real workflow code runs unchanged.
"""

import asyncio
import uuid
from typing import List

import pytest
from temporalio import activity
from temporalio.client import WorkflowHandle, WorkflowUpdateFailedError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from slothshot.shared import MoveRequest, NameRequest, NameResult, Shot, TidyInput, TidyState
from slothshot.workflows import TidyScreenshots

SHOTS = 5


class FakeDisk:
    """Stands in for the disk, OCR and the model, and remembers what it was asked to do."""

    def __init__(self, hold_from: int | None = None) -> None:
        self.read: List[str] = []
        self.models: List[str] = []
        self.moved: List[str] = []
        self.put_back: List[str] = []
        self.hold_from = hold_from  # reading this screenshot waits until the gate opens
        self.holding = asyncio.Event()
        self.gate = asyncio.Event()

    def activities(self):
        @activity.defn(name="scan_folder")
        async def scan_folder(folder: str, include_all_images: bool) -> List[Shot]:
            return [Shot(path=f"{folder}/Screenshot {n}.png", name=f"Screenshot {n}.png", taken=f"2026-10-1{n}T10:00:00") for n in range(SHOTS)]

        @activity.defn(name="read_screenshot")
        async def read_screenshot(path: str) -> str:
            if self.hold_from is not None and len(self.read) == self.hold_from:
                self.holding.set()
                await self.gate.wait()
            self.read.append(path)
            return f"Invoice {len(self.read)} from Fernleaf Studio, due 5 Nov"

        @activity.defn(name="name_screenshot")
        async def name_screenshot(req: NameRequest) -> NameResult:
            self.models.append(req.model)
            return NameResult(category="receipts", slug=f"fernleaf-invoice-{len(self.models)}")

        @activity.defn(name="move_file")
        async def move_file(req: MoveRequest) -> str:
            self.moved.append(req.src)
            return f"{req.folder}/{req.category}/{req.filename}"

        @activity.defn(name="put_back")
        async def put_back(original: str, moved_to: str) -> None:
            self.put_back.append(original)

        @activity.defn(name="write_report")
        async def write_report(folder: str, state: TidyState) -> str:
            return f"{folder}/slothshot-report.md"

        return [scan_folder, read_screenshot, name_screenshot, move_file, put_back, write_report]


@pytest.fixture
async def env():
    async with await WorkflowEnvironment.start_time_skipping() as env:
        yield env


def worker(env: WorkflowEnvironment, disk: FakeDisk, queue: str) -> Worker:
    return Worker(env.client, task_queue=queue, workflows=[TidyScreenshots], activities=disk.activities())


async def start(env: WorkflowEnvironment, queue: str, **inp) -> WorkflowHandle:
    return await env.client.start_workflow(
        TidyScreenshots.run, TidyInput(folder="/shots", **inp), id=f"tidy-{uuid.uuid4()}", task_queue=queue
    )


async def phase_is(handle: WorkflowHandle, phase: str) -> TidyState:
    for _ in range(200):
        state = await handle.query(TidyScreenshots.status)
        if state.phase == phase:
            return state
        await asyncio.sleep(0.05)
    raise AssertionError(f"never reached {phase}; stuck at {state.phase}")


async def test_plan_applies_itself_when_nobody_answers(env):
    disk, queue = FakeDisk(), str(uuid.uuid4())
    async with worker(env, disk, queue):
        handle = await start(env, queue, apply_after_minutes=480, undo_window_minutes=1440, model="qwen2.5:1.5b")
        # Nobody approves or vetoes: the 8 h timer and the 1 day undo window both pass (time skips).
        assert await handle.result() == f"Tidied {SHOTS} screenshots."
        state = await handle.query(TidyScreenshots.status)
    assert state.phase == "done" and state.decision == "approve"
    assert len(disk.moved) == SHOTS
    assert disk.models == ["qwen2.5:1.5b"] * SHOTS  # the run's model reaches every naming call


async def test_veto_while_reading_stops_early_and_moves_nothing(env):
    disk, queue = FakeDisk(hold_from=2), str(uuid.uuid4())
    async with worker(env, disk, queue):
        handle = await start(env, queue)
        await asyncio.wait_for(disk.holding.wait(), 20)  # reading screenshot 3 of 5
        assert await handle.execute_update(TidyScreenshots.veto) == "Vetoed. Nothing will move."
        disk.gate.set()
        assert await handle.result() == "Vetoed. Nothing moved."
        state = await handle.query(TidyScreenshots.status)
    assert state.phase == "vetoed"
    assert len(disk.read) == 3  # finished the one in hand, then stopped
    assert disk.moved == []


async def test_undo_puts_everything_back(env):
    disk, queue = FakeDisk(), str(uuid.uuid4())
    async with worker(env, disk, queue):
        handle = await start(env, queue)
        await handle.execute_update(TidyScreenshots.approve)
        await phase_is(handle, "done")
        assert len(disk.moved) == SHOTS
        assert await handle.execute_update(TidyScreenshots.undo) == "Putting every file back."
        assert await handle.result() == f"Undid {SHOTS} moves."
        state = await handle.query(TidyScreenshots.status)
    assert state.phase == "undone"
    assert disk.put_back == list(reversed(disk.moved))  # last moved, first back
    assert all(item.status == "undone" for item in state.items)


async def test_undo_is_refused_before_anything_moved(env):
    disk, queue = FakeDisk(), str(uuid.uuid4())
    async with worker(env, disk, queue):
        handle = await start(env, queue)
        await phase_is(handle, "waiting")
        with pytest.raises(WorkflowUpdateFailedError) as refused:
            await handle.execute_update(TidyScreenshots.undo)
        assert "Nothing to undo yet" in refused.value.cause.message
        # A rejected update leaves no trace in history, and the run carries on as if nothing happened.
        await handle.execute_update(TidyScreenshots.veto)
        assert await handle.result() == "Vetoed. Nothing moved."
    assert disk.moved == [] and disk.put_back == []
