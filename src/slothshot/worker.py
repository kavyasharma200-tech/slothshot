"""Runs the sloth. Kill it whenever you like; start it again and it carries on.

  slothshot worker              (or: python -m slothshot.worker)
"""

import asyncio
import concurrent.futures
import logging

from temporalio.client import Client
from temporalio.worker import Worker

from slothshot import activities as acts
from slothshot.shared import DEFAULT_MODEL, TASK_QUEUE, TEMPORAL_ADDRESS
from slothshot.workflows import TidyScreenshots

ACTIVITIES = [
    acts.scan_folder,
    acts.read_screenshot,
    acts.name_screenshot,
    acts.move_file,
    acts.put_back,
    acts.write_report,
]


async def main(address: str = TEMPORAL_ADDRESS) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("temporalio").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    # Failed attempts are expected (Temporal retries them); the sloth logs its own one-line note instead.
    logging.getLogger("temporalio.worker._activity").setLevel(logging.ERROR)
    logging.getLogger("temporalio.activity").setLevel(logging.ERROR)
    client = await Client.connect(address)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        worker = Worker(
            client,
            task_queue=TASK_QUEUE,
            workflows=[TidyScreenshots],
            activities=ACTIVITIES,
            activity_executor=pool,
            # One screenshot at a time, so the laptop stays usable while the sloth works.
            max_concurrent_activities=1,
        )
        logging.info(
            "sloth worker up on %s, task queue %r (default model %s, chaos %g)",
            address, TASK_QUEUE, DEFAULT_MODEL, acts.chaos_rate(),
        )
        await worker.run()


def run(address: str = TEMPORAL_ADDRESS) -> None:
    try:
        asyncio.run(main(address))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
