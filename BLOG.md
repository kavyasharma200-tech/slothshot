---
title: "Slothshot: a tiny model on a slow laptop names my screenshots overnight, and Temporal makes sure it finishes"
published: false
tags: devchallenge, hf26challenge, temporal, opensource
cover_image: https://raw.githubusercontent.com/kavyasharma200-tech/slothshot/main/docs/cover.jpg
---

*This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 3: Slow and Steady](https://dev.to/challenges/hacktoberfest-week3-2026-10-19)*

## What I Built

**Slothshot is a sloth that names my screenshots while I sleep, on my own laptop, and doesn't stop until the job is done, even when the laptop dies halfway through.**

![The Slothshot story page: "Your screenshots, named by morning." A sloth hangs from a branch with screenshots dangling from it like leaves.](https://raw.githubusercontent.com/kavyasharma200-tech/slothshot/main/docs/story-hero.jpg)

My Screenshots folder is where useful things go to be forgotten, because every boarding pass and Wi-Fi password I have ever needed lands there under a name like `Screenshot 2026-10-19 105126.png`, and on the day I need one again I spend five minutes squinting at thumbnails that all look the same. Slothshot does the tidying for me overnight, slowly and steadily, with open models that never leave my machine.

- **It reads every screenshot.** RapidOCR, an open OCR model running in ONNX Runtime, pulls the text off each image.
- **It names and files them.** Gemma 3 1B, running in Ollama on my laptop, turns that text into a short name and a folder, so `Screenshot 2026-10-19 211740.png` becomes `notes/2026-10-19-banana-bread-recipe.png`.
- **It waits for a yes, or for nothing.** The plan waits for me in the morning, and if I'm still asleep when the timer runs out, it takes my silence as a yes, since the whole point is that I don't lift a finger.
- **It can take it all back.** For a whole day after the files move, one click puts every one of them back where it was.
- **It naps when I need the laptop.** It works on one screenshot at a time, and I can tell it to nap, wake up, or leave a single screenshot alone.
- **It runs every night if I want it to.** One command sets up a schedule, and after that I never think about it again.
- **It survives anything.** I can kill the worker, close the lid or quit Ollama in the middle of a night, and it carries on from the screenshot it was on without redoing a single finished step.

**Who it's for:** anyone with a Screenshots folder they're scared to open.

**How lazy it lets you be:** one command before bed, and one click in the morning, or none at all.

## Demo

- **The story of one real night:** https://kavyasharma200-tech.github.io/slothshot/
- **Install on Windows:** `irm https://raw.githubusercontent.com/kavyasharma200-tech/slothshot/main/install.ps1 | iex`
- **Install on macOS or Linux:** `curl -fsSL https://raw.githubusercontent.com/kavyasharma200-tech/slothshot/main/install.sh | sh`
- **Or from a clone:** `git clone https://github.com/kavyasharma200-tech/slothshot`, then `cd slothshot` and `uv run slothshot up`

The story page isn't a mock-up. It replays a run I did this evening straight from its recorded Temporal history, so every name, every bad answer from the model, the heartbeat timeout after I killed the worker, and the approve and undo at the end are what actually happened. Scroll slowly and the sloth crawls along a branch whose notches are the events Temporal wrote down, until halfway through the branch snaps, the sloth falls, and a new one climbs back to the very same notch.

![The story page at the moment of the crash: "Halfway through, I pulled the plug." The branch has cracked and the real worker log shows the kill.](https://raw.githubusercontent.com/kavyasharma200-tech/slothshot/main/docs/story-pulled-the-plug.jpg)

## Code

{% embed https://github.com/kavyasharma200-tech/slothshot %}

## How I Built It

### Four open pieces and one rule

RapidOCR reads the text off each screenshot, Gemma 3 1B in Ollama turns that text into a name and a folder, the Temporal Python SDK runs the whole night as a workflow, and a small FastAPI server shows it all as a story page and an app. The rule that holds them together is Temporal's own: the workflow only makes decisions, and anything slow or flaky, like reading an image, asking the model or moving a file, happens in an activity, whose result Temporal writes into the workflow's history the moment it finishes.

```
slothshot up ─▶ Temporal dev server (reused if one is running, or downloaded and started, history kept on disk)
             ─▶ a supervised worker (restarted 4 s after it dies, for any reason)
             ─▶ FastAPI: the story at /, the app at /app

TidyScreenshots (the workflow: decides, never touches the world)
  scan_folder
  ─▶ for each screenshot: read_screenshot (RapidOCR) ─▶ name_screenshot (Gemma 3 1B)
  ─▶ wait for a yes        (durable timer: silence means yes)
  ─▶ move_file × 19        (saga: put_back everything if one fails)
  ─▶ undo window           (durable timer: one day)
```

```python
# Slow and steady: never give up on a flaky local model, just wait longer between tries.
STEADY = RetryPolicy(initial_interval=timedelta(seconds=2), backoff_coefficient=2.0,
                     maximum_interval=timedelta(seconds=30))

while s.cursor < len(s.items):
    await workflow.wait_condition(lambda: not s.napping)   # "nap" and "wake" are signals
    item = s.items[s.cursor]
    if item.status == "waiting":
        await self._read_and_name(item)                    # two activities: OCR, then the model
    s.cursor += 1
```

### Pulling the plug, for real

That history is what makes crashing boring in the best way. During the night on the story page I killed the worker three times with `Stop-Process -Force`, and the second time it was in the middle of asking the model to name a page of meeting notes:

```
20:19:01  naming    Screenshot 2026-10-20 225701.png (try 1)
          (worker killed at 20:19:08)
20:19:19  sloth worker up on task queue 'slothshot', model gemma3:1b
20:19:26  naming    Screenshot 2026-10-20 225701.png (try 2)
20:19:36            -> notes/q4-planning-offline-mode-action-items-sync
```

The new worker didn't look at the eight finished screenshots again, and it didn't run OCR on the meeting notes again either, because all of those results were already sitting in the history. It also came back after 18 seconds rather than after the five-minute activity timeout, because the slow model call runs in a thread while the activity heartbeats every three seconds, so with a 20-second heartbeat timeout Temporal notices quickly that nobody is home and hands the call to the next worker.

You don't have to take my word for it, because the app has a **Pull the plug on the worker** button that hard-kills the real worker process. This is the app just after I pressed it: the new worker has been up for 18 seconds, and the call that died is back as attempt 2, with "activity Heartbeat timeout" as the reason.

![The Slothshot app after pulling the plug: "name_screenshot · attempt 2 · started, last try: activity Heartbeat timeout" and "Worker 28132 is up, since 18 s ago, restarted 1 time."](https://raw.githubusercontent.com/kavyasharma200-tech/slothshot/main/docs/app-pulled-the-plug.jpg)

### The flakiest tool is the model

Running a 1B model on a laptop with no graphics card is honest about one thing: it is slow, and it is often wrong. After every answer, `name_screenshot` checks that at least two words of the name really appear on the screenshot, and when they don't, it raises an error with `next_retry_delay` set to one second, so Temporal asks again straight away with the temperature turned up a little, while a real outage like Ollama being closed still gets the slow backoff and the sloth simply waits for it to come back.

```python
raise ApplicationError(f"weak name {answer.get('name')!r}, asking again",
                       type="WeakAnswer", next_retry_delay=timedelta(seconds=1))
```

The real answers from that night are the best argument for it. For a bakery receipt the model said "order", "order", "food", "Order Details" and "shopping", so after five tries Slothshot kept the first words on the screen instead, `kettle-crumb-bakery-order`; for a boarding pass it said "flight" five times in a row; and once it answered with `taken-2026-10-23`, which turned out to be the date I had put in its own prompt. Across 20 screenshots it took 66 model calls to name 19 of them, and the fallback that keeps the first words on the screen turned out to be a surprisingly decent namer, because most screens put their title at the top.

![The story page replaying the model's real answers: order, order, food, Order Details and shopping, each crossed out as "not on the screen".](https://raw.githubusercontent.com/kavyasharma200-tech/slothshot/main/docs/story-slow-and-wrong.jpg)

### Everything a lazy person needs, built from Temporal

The rest of Temporal is there because a lazy person needs it, not to tick boxes:

| What I want as a lazy person | What does it |
|---|---|
| Start at 01:30, not now | `--night 01:30` is a durable timer, so a reboot at midnight doesn't cancel it |
| "If I say nothing, go ahead" | the approval wait is a `wait_condition` with an 8-hour timeout |
| Approve, veto or undo, and be told when it's too late | workflow updates with validators, so a veto after the move answers "too late, try undo" |
| Pause while I'm on a call | `nap` and `wake` signals, checked between screenshots |
| Never a half-tidied folder | a saga: if a move fails, every file already moved is put back |
| A corrupt file | a non-retryable error, so one bad image is skipped instead of retried forever |
| Thousands of screenshots | continue-as-new every 25 screenshots keeps each run's history small |
| Set it up once | `slothshot schedule` creates a Temporal Schedule that runs every night |

Every activity is idempotent too, so if a move is retried after the file has already landed, it reports the move instead of failing.

### Tests that replay real nights

Because I kept the histories of my test runs, they became tests as well. `tests/test_replay.py` feeds two recorded nights, the one with three kills and an undo and one that continued-as-new and was vetoed, back through today's workflow code with Temporal's `Replayer`, so any change that would trip up a night already in flight fails before it ships. `tests/test_workflow.py` runs the whole night on Temporal's time-skipping test server, where the eight-hour "say nothing and it goes ahead" wait passes in a blink. All 13 tests pass.

### One command, and a lab for breaking it

`slothshot up` is a tiny supervisor that reuses a Temporal server if one is running, or downloads and starts its own with a database that survives reboots, then runs the worker as a child process that comes back four seconds after it dies, and serves the app. The app is night while the sloth works and morning once there is a plan, and its **Under the hood** panel shows what Temporal sees: the activity in flight with its attempt number and last failure, the event history as it grows, the **Pull the plug** button, and a slider that makes a share of real OCR and model calls fail so you can watch Temporal retry each one. The local server only accepts changes from the app itself, so no other website open in your browser can start a night on your folder or kill your worker.

![The Slothshot app at night: "Reading 4 of 20." with the sloth on its branch, the named screenshots, and the Under the hood panel.](https://raw.githubusercontent.com/kavyasharma200-tech/slothshot/main/docs/app-night.jpg)

### Design

The story page is one night on one branch, told by your scroll with GSAP, ScrollTrigger and Lenis, and the palette comes from the sloth itself: moss for the algae that grows in its fur, bark for the fur and the tree, and hibiscus, the flower sloths eat, only for the moment that matters. Further down, a graph replays all 499 events of the real night, and each way the night can go wrong lights up the part of the graph that catches it, with the real line of code beside it.

![The history graph: the workflow in the middle, its six activities around it, and the history, the folder and gemma3:1b outside, replaying the real run's events.](https://raw.githubusercontent.com/kavyasharma200-tech/slothshot/main/docs/story-history-graph.jpg)

## Why Does Open Innovation Matter?

Because screenshots are the most private files on my laptop.

I take most of them because I didn't want to type the thing anywhere, so my folder is full of Wi-Fi passwords, delivery OTPs, payment references and chats with friends. Sending all of that to a cloud vision API every night just to get tidier filenames would be a strange trade, and with Gemma, RapidOCR and a local Temporal server nothing leaves the laptop at all, which also means it works on a train with no signal just as well as it does at my desk.

Running everything locally also changed how I designed the agent:

- **Retries are free, so the sloth can be stubborn.** With a paid API every weak answer and every retry costs money, which quietly pushes you to retry less, but here a retry costs a few seconds of a CPU that would otherwise sit idle at two in the morning.
- **The model is a setting, not a contract.** It's one environment variable, and the app lets you pick per night. When I tried Qwen 2.5 1.5B on the six screenshots Gemma struggled with most, it answered in about four and a half seconds instead of nine and filed the boarding pass under travel, but it also copied the example name from my prompt, `flight-del-to-bom-seat-22a`, word for word on two screenshots that had nothing to do with flights, and the same grounding check caught that too.
- **It costs nothing to run, forever.** No key, no quota and no bill, however many screenshots I take.

There is one place where a closed model would still beat mine, and it's pictures without words: OCR has nothing to read on a drawing, so the sloth leaves those files alone and marks them "no words on it" rather than guessing. Swapping in an open vision model from Ollama is the obvious next step, and because it would just be another activity, the workflow wouldn't change at all.

## The Lazy Payoff

On the night the story page replays, the sloth worked through 20 screenshots in about ten and a half minutes on a Ryzen 5 7520U with no graphics card, while I killed its worker three times, and it never redid a single OCR pass or model answer that had already finished. My part of the job was one command before the run and one click after it, and on a night when I can't even manage the click, it goes ahead without me.

## Prize Categories

- **Best Use of Gemma**: Gemma 3 1B, running locally in Ollama on a laptop with no graphics card, names and files every screenshot through structured JSON output, and a grounding check makes it prove each name with words that are really on the screenshot before the name is kept.
- **Best Use of Temporal**: the whole agent is a durable Temporal workflow that survives hard worker kills mid-model-call (heartbeats), retries a flaky local model (retry policies and `next_retry_delay`), and gives a lazy person signals, validated updates, durable timers, a saga undo, continue-as-new and a nightly Schedule, with replay tests built from real recorded histories.
