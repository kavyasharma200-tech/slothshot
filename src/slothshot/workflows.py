"""The sloth itself: one durable workflow that reads, names, waits for you, moves, and can undo.

Workflow code must be deterministic, so it only decides. Every slow or flaky thing (OCR, the
local LLM, the disk) happens in an activity, and Temporal keeps each result in history.
Kill the worker at screenshot 7 of 20 and the next worker replays the history, skips the six
finished screenshots without calling the model again, and carries on at 7.
"""

import asyncio
import dataclasses
from datetime import datetime, timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from slothshot import activities as acts
    from slothshot.shared import Item, MoveRequest, NameRequest, TidyInput, TidyState

# Slow and steady: never give up on a flaky local model, just wait longer between tries (max 30 s).
# Errors that can never succeed (a missing or corrupt file) are raised as non-retryable instead.
STEADY = RetryPolicy(initial_interval=timedelta(seconds=2), backoff_coefficient=2.0, maximum_interval=timedelta(seconds=30))
# Heartbeats every 3 s from the activity; if a worker dies mid-call, Temporal retries elsewhere after 20 s.
HEARTBEAT = timedelta(seconds=20)


def _why(err: ActivityError) -> str:
    cause = err.cause
    return str(getattr(cause, "message", None) or cause or err)[:140]


@workflow.defn
class TidyScreenshots:
    def __init__(self) -> None:
        self.s = TidyState()
        self.woken = False
        self.undo_asked = False

    @workflow.run
    async def run(self, inp: TidyInput) -> str:
        if inp.state:
            self.s = inp.state
            self.s.runs += 1
        s = self.s
        s.folder = inp.folder

        if s.phase in ("starting", "sleeping"):
            await self._sleep_until(inp.not_before)
            shots = await workflow.execute_activity(
                acts.scan_folder,
                args=[inp.folder, inp.include_all_images],
                start_to_close_timeout=timedelta(minutes=1),
            )
            s.items = [Item(path=x.path, name=x.name, taken=x.taken) for x in shots]
            s.phase = "reading"

        if s.phase == "reading":
            done_this_run = 0
            while s.cursor < len(s.items):
                await workflow.wait_condition(lambda: not s.napping)
                if s.decision == "veto":
                    break  # nothing will move, so don't keep the laptop busy naming things
                item = s.items[s.cursor]
                if item.status == "waiting":
                    await self._read_and_name(item, inp.model)
                    done_this_run += 1
                s.cursor += 1
                if s.cursor < len(s.items) and (
                    done_this_run >= inp.items_per_run or workflow.info().is_continue_as_new_suggested()
                ):
                    await workflow.wait_condition(workflow.all_handlers_finished)
                    workflow.continue_as_new(dataclasses.replace(inp, state=s))
            self._dedupe_names()
            s.phase = "waiting"

        if s.phase == "waiting":
            await self._wait_for_a_yes(inp.apply_after_minutes)
            if s.decision == "veto":
                s.phase = "vetoed"
                await self._report()
                return "Vetoed. Nothing moved."
            s.phase = "moving"

        if s.phase == "moving":
            try:
                for item in s.items:
                    if item.status != "named":
                        continue
                    item.final_path = await workflow.execute_activity(
                        acts.move_file,
                        MoveRequest(src=item.path, folder=inp.folder, category=item.category, filename=item.filename),
                        start_to_close_timeout=timedelta(seconds=30),
                        retry_policy=RetryPolicy(maximum_attempts=5),
                    )
                    item.status = "moved"
            except ActivityError as err:
                # Saga: a half-tidied folder is worse than an untidy one, so put back what already moved.
                await self._put_everything_back()
                s.phase = "rolled-back"
                await self._report()
                return f"Rolled back after a failed move: {_why(err)}"
            s.phase = "done"
            await self._report()

        moved = sum(1 for i in s.items if i.status == "moved")
        undo_window = timedelta(minutes=inp.undo_window_minutes)
        s.undo_until = (workflow.now() + undo_window).isoformat()
        try:
            await workflow.wait_condition(lambda: self.undo_asked, timeout=undo_window)
        except asyncio.TimeoutError:
            return f"Tidied {moved} screenshots."
        s.phase = "undoing"
        await self._put_everything_back()
        s.phase = "undone"
        await self._report()
        return f"Undid {moved} moves."

    async def _sleep_until(self, not_before):
        if not not_before:
            return
        delay = datetime.fromisoformat(not_before) - workflow.now()
        if delay.total_seconds() <= 0:
            return
        self.s.phase = "sleeping"
        try:
            # A durable timer: survives worker restarts and reboots. "wake" ends it early.
            await workflow.wait_condition(lambda: self.woken, timeout=delay)
        except asyncio.TimeoutError:
            pass

    async def _read_and_name(self, item: Item, model: str) -> None:
        item.status = "reading"
        try:
            text = await workflow.execute_activity(
                acts.read_screenshot,
                item.path,
                start_to_close_timeout=timedelta(minutes=3),
                heartbeat_timeout=HEARTBEAT,
                retry_policy=STEADY,
            )
        except ActivityError as err:
            item.status, item.note = "failed", _why(err)
            return
        item.text = " ".join(text.split())[:180]
        if len(text.strip()) < 8:
            item.status, item.note = "no-text", "no words on it, so it stays where it is"
            return
        item.status = "naming"
        try:
            named = await workflow.execute_activity(
                acts.name_screenshot,
                NameRequest(path=item.path, name=item.name, taken=item.taken, text=text, model=model),
                start_to_close_timeout=timedelta(minutes=5),
                heartbeat_timeout=HEARTBEAT,
                retry_policy=STEADY,
            )
        except ActivityError as err:
            item.status, item.note = "failed", _why(err)
            return
        ext = "." + item.name.rsplit(".", 1)[-1].lower() if "." in item.name else ".png"
        item.category = named.category
        item.filename = f"{item.taken[:10]}-{named.slug}{ext}"
        item.tries = named.tries
        item.note = named.note
        item.status = "named"

    def _dedupe_names(self) -> None:
        seen = {}
        for item in self.s.items:
            if item.status != "named":
                continue
            key = f"{item.category}/{item.filename}"
            if key in seen:
                seen[key] += 1
                stem, ext = item.filename.rsplit(".", 1)
                item.filename = f"{stem}-{seen[key]}.{ext}"
            else:
                seen[key] = 1

    async def _wait_for_a_yes(self, minutes: float) -> None:
        s = self.s
        if s.decision:  # approved or vetoed while it was still reading
            return
        s.apply_at = (workflow.now() + timedelta(minutes=minutes)).isoformat()
        try:
            await workflow.wait_condition(lambda: s.decision is not None, timeout=timedelta(minutes=minutes))
        except asyncio.TimeoutError:
            s.decision = "approve"  # the lazy default: you said nothing, so it goes ahead

    async def _put_everything_back(self) -> None:
        for item in reversed(self.s.items):
            if item.status != "moved":
                continue
            await workflow.execute_activity(
                acts.put_back,
                args=[item.path, item.final_path],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=STEADY,
            )
            item.status = "undone"

    async def _report(self) -> None:
        self.s.report = await workflow.execute_activity(
            acts.write_report,
            args=[self.s.folder, self.s],
            start_to_close_timeout=timedelta(seconds=30),
        )

    # ---- talking to the sloth ----

    @workflow.query
    def status(self) -> TidyState:
        return self.s

    @workflow.signal
    def nap(self) -> None:
        self.s.napping = True

    @workflow.signal
    def wake(self) -> None:
        self.s.napping = False
        self.woken = True

    @workflow.signal
    def skip(self, index: int) -> None:
        if 0 <= index < len(self.s.items) and self.s.items[index].status in ("waiting", "named"):
            self.s.items[index].status = "skipped"
            self.s.items[index].note = "you skipped it"

    @workflow.update
    def approve(self) -> str:
        self.s.decision = "approve"
        return "Approved. It moves as soon as every screenshot has a name." if self.s.phase != "waiting" else "Approved."

    @approve.validator
    def _approve_ok(self) -> None:
        if self.s.phase not in ("starting", "sleeping", "reading", "waiting"):
            raise ValueError(f"Too late to approve: the sloth is {self.s.phase}.")

    @workflow.update
    def veto(self) -> str:
        self.s.decision = "veto"
        return "Vetoed. Nothing will move."

    @veto.validator
    def _veto_ok(self) -> None:
        if self.s.phase not in ("starting", "sleeping", "reading", "waiting"):
            raise ValueError(f"Too late to veto: the sloth is {self.s.phase}. Try undo.")

    @workflow.update
    def undo(self) -> str:
        self.undo_asked = True
        return "Putting every file back."

    @undo.validator
    def _undo_ok(self) -> None:
        if self.s.phase != "done":
            raise ValueError(f"Nothing to undo yet: the sloth is {self.s.phase}.")
