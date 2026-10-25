---
title: Slothshot: a tiny model on a slow laptop finally named my screenshots, and Temporal made sure it finished
published: false
tags: devchallenge, hf26challenge, temporal, ollama
---

*This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 3: Slow and Steady](https://dev.to/challenges/hacktoberfest-week3-2026-10-19)*

## What I Built

My Screenshots folder is where useful things go to be forgotten, because every boarding pass and Wi-Fi password I have ever needed lands there under a name like `Screenshot 2026-10-19 105126.png`, and on the day I need one again I spend five minutes squinting at thumbnails that all look the same.

Slothshot is a small agent that does the tidying for me while I sleep. It reads each screenshot with an open OCR model, asks Gemma 3 1B, running in Ollama on my own laptop, for a short name and a folder, and then waits for me to say yes, although if I am still asleep when the timer runs out it takes my silence as a yes, since the whole point is that I don't lift a finger. By morning `Screenshot 2026-10-19 211740.png` has become `notes/2026-10-19-banana-bread-recipe.png`, and if I hate what it did, one click puts every file back where it was for the next 24 hours.

The trouble is that my laptop is a Ryzen 5 7520U with no graphics card, so the model takes somewhere between 3 and 16 seconds to think of each name, it often answers with one useless word like "recipe" or "cart", and a real folder of a few hundred screenshots is a job that runs longer than my laptop stays awake. A plain Python script would die at screenshot 214 and start again from zero, which is why the whole agent lives inside a Temporal workflow that remembers every answer the model has already given, retries the bad ones, and, when I kill the worker in the middle of a model call, carries on from the same screenshot as if nothing had happened.

## Demo

The story of one real night lives at **[kavyasharma200-tech.github.io/slothshot](https://kavyasharma200-tech.github.io/slothshot/)**, and it isn't a mock-up: the page replays a run I did this evening straight from its recorded Temporal history, so every name, every weak answer, the heartbeat timeout after I killed the worker, and the approve and undo at the end are what actually happened. Scroll slowly and the sloth crawls along a branch whose notches are the events Temporal wrote down; halfway through, the branch snaps, the sloth falls, and a new one climbs back to the very same notch.

<!-- Upload the video (YouTube or similar) and replace this line with: {% embed https://youtu.be/YOUR_VIDEO %} -->

In the video I run `slothshot up`, point the app at twenty made-up screenshots, and press **Pull the plug on the worker** halfway through. The app's "Under the hood" panel shows a new worker up about four seconds later and, once the old heartbeat has been quiet for 20 seconds, the call that died coming back as its next attempt with "activity Heartbeat timeout" as the last failure, while the history keeps growing on the new worker; then I turn the **Make the model flaky** slider up and watch Temporal retry every failed call. At the end I press **Move them now**, the files land in their folders, and **Put them back** undoes all of it.

<!-- Upload docs/story-hero.jpg, docs/story-pulled-the-plug.jpg, docs/story-history-graph.jpg and docs/app-night.jpg here. -->

## Code

{% github kavyasharma200-tech/slothshot %}

Installing it is one line on Windows (`irm https://raw.githubusercontent.com/kavyasharma200-tech/slothshot/main/install.ps1 | iex`) or macOS and Linux (`curl -fsSL https://raw.githubusercontent.com/kavyasharma200-tech/slothshot/main/install.sh | sh`), and then `slothshot up` starts Temporal, a supervised worker and the app together, downloading a Temporal dev server on first run if you don't already have one.

## How I Built It

The stack is four open pieces held together by one rule. RapidOCR (PaddleOCR's models running in ONNX Runtime) reads the text off each screenshot, Gemma 3 1B in Ollama turns that text into a name and a folder, the Temporal Python SDK runs the agent as a workflow against a local Temporal dev server, and a FastAPI app serves both the story page and the app you actually use. The rule is Temporal's own: the workflow only makes decisions, and anything slow or flaky, like reading an image, calling the model or moving a file, happens in an activity, whose result Temporal writes into the workflow's history the moment it finishes.

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

That history is what makes crashing boring in the best possible way. This evening I killed the worker three times with `Stop-Process -Force`, and the second time it was in the middle of asking the model to name a page of meeting notes:

```
20:19:01  naming    Screenshot 2026-10-20 225701.png (try 1)
          (worker killed at 20:19:08)
20:19:19  sloth worker up on task queue 'slothshot', model gemma3:1b
20:19:26  naming    Screenshot 2026-10-20 225701.png (try 2)
20:19:36            -> notes/q4-planning-offline-mode-action-items-sync
```

The new worker didn't look at the eight finished screenshots again, and it didn't run OCR on the meeting notes again either, because all of those results were already sitting in the history. It also came back after 18 seconds rather than after the five-minute activity timeout, because the slow model call runs in a thread while the activity heartbeats every three seconds, so with a 20-second heartbeat timeout Temporal notices quickly that nobody is home and hands the call to whichever worker turns up next.

The flakiest tool in this agent is the model itself, which is the honest problem with running a 1B model on a laptop. After every answer, `name_screenshot` checks that at least two words of the name really appear on the screenshot, and when they don't it raises an error with `next_retry_delay` set to one second, so Temporal asks again straight away with the temperature turned up a little, while a real outage like Ollama being closed still gets the slow backoff and the sloth simply waits for it to come back. Today the model said "recipe" for the banana bread screenshot and got it right on the second try, and for one social post it said "chat" and then "social" before settling on `hot-take` on the fifth. Across the 20 demo screenshots it took 66 model calls to name 19 of them, and 7 never got a good answer at all, so they fell back to the first few words on the screen, which turned out to be a surprisingly decent namer of its own, because most screens put their title at the top: `boarding-pass-blr-goi` and `your-cart-oakline-standing-desk` both came from the fallback.

The rest of Temporal is there because a lazy person needs it, not to tick boxes:

| What I want as a lazy person | What does it |
|---|---|
| Start at 01:30, not now | `--night 01:30` is a durable timer, so a reboot at midnight doesn't cancel it |
| "If I say nothing, go ahead" | the approval wait is a `wait_condition` with an 8-hour timeout |
| Approve, veto or undo, and be told when it's too late | workflow updates with validators, so a veto after the move answers "too late, try undo" |
| Pause while I'm on a call | `nap` and `wake` signals, checked between screenshots |
| Never a half-tidied folder | a saga: if a move fails, every file already moved is put back |
| Thousands of screenshots | continue-as-new every 25 screenshots keeps each run's history small |
| Set it up once | `sloth.py schedule` creates a Temporal Schedule that runs every night |

Every activity is idempotent, too, so if a move is retried after the file has already landed, it reports the move instead of failing.

Because I kept the histories of those runs, they became tests as well. `tests/test_replay.py` feeds both recorded nights, the one with three kills and an undo and the one that continued-as-new and was vetoed, back through today's workflow code with Temporal's `Replayer`, so any change that would trip up a night already in flight fails before it ships, and `tests/test_workflow.py` runs the whole night on Temporal's time-skipping test server, where an eight-hour "say nothing and it goes ahead" wait passes in a blink.

The last piece is the one that makes it usable by someone who isn't me. `slothshot up` is a tiny supervisor: it reuses a Temporal server if one is running or starts its own with a database that survives reboots, runs the worker as a child process and restarts it four seconds after it dies, and serves the app, which is also why the **Pull the plug** button can exist at all, since it hard-kills a real process that the supervisor then brings back.

## Why Does Open Innovation Matter?

Screenshots are the most private files on my laptop, since I only take most of them because I didn't want to type the thing anywhere, so my folder is full of Wi-Fi passwords, delivery OTPs, payment references and chats with friends. Sending all of that to a cloud vision API every night just to get tidier filenames would be a strange trade, and with Gemma, RapidOCR and a local Temporal server nothing leaves the laptop at all, which also means it works on a train with no signal just as well as it does at my desk.

Running everything locally also changed how I designed the agent. With a paid API every weak answer and every retry costs money, which quietly pushes you to retry less, but here a retry costs a few seconds of a CPU that would otherwise sit idle at two in the morning, so I could make the sloth as stubborn as I liked. The model is one environment variable, `SLOTH_MODEL`, so swapping Gemma for another open model takes no code at all, and when I tried Qwen 2.5 1.5B on the six screenshots Gemma struggled with most, it answered in about four and a half seconds instead of nine and filed the boarding pass under travel, but it also copied the example name from my prompt, `flight-del-to-bom-seat-22a`, word for word on two screenshots that had nothing to do with flights, and the same grounding check caught that too.

There is one place where a closed model would still beat mine, and it's pictures without words: OCR has nothing to read on a drawing, so the sloth leaves those files alone and marks them "no words on it" rather than guessing. Swapping the OCR step for an open vision model in Ollama is the obvious next step, and because it's just another activity, the workflow wouldn't change at all.

## The Lazy Payoff

On the demo folder of 20 screenshots the sloth finished on its own in about ten minutes, even though I killed its worker three times along the way, and it never redid a single OCR pass or model answer that had already finished. My part of the job was one command before the run and one click after it, and on a night when I can't even manage the click, it goes ahead without me.

## Prize Categories

Best Use of Temporal
