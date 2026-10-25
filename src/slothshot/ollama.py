"""The few things slothshot asks the local Ollama server: what's pulled, and to pull more."""

import json
from typing import Iterator, List, Tuple

import httpx

from slothshot.shared import OLLAMA_URL


def models(timeout: float = 2.0) -> List[str]:
    r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=timeout)
    r.raise_for_status()
    return [m["name"] for m in r.json().get("models", [])]


def has(model: str, pulled: List[str]) -> bool:
    """Ollama lists "llama3" as "llama3:latest", so a name without a tag means :latest."""
    return model in pulled or (":" not in model and f"{model}:latest" in pulled)


def pull(model: str) -> Iterator[Tuple[int, int, str]]:
    """Streams Ollama's pull and yields (bytes done, bytes total, status) across all layers."""
    layers = {}
    timeout = httpx.Timeout(10.0, read=None)  # a big layer can go quiet for a while
    with httpx.stream("POST", f"{OLLAMA_URL}/api/pull", json={"model": model, "stream": True}, timeout=timeout) as r:
        if r.status_code >= 400:
            r.read()
            try:
                raise RuntimeError(r.json().get("error") or r.text)
            except json.JSONDecodeError:
                raise RuntimeError(r.text or f"HTTP {r.status_code}") from None
        for line in r.iter_lines():
            if not line.strip():
                continue
            msg = json.loads(line)
            if msg.get("error"):
                raise RuntimeError(msg["error"])
            if msg.get("digest") and msg.get("total"):
                layers[msg["digest"]] = (msg.get("completed", 0), msg["total"])
            done = sum(c for c, _ in layers.values())
            total = sum(t for _, t in layers.values())
            yield done, total, msg.get("status", "")
