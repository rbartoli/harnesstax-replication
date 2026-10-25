#!/usr/bin/env python3
"""Ledger rows from Harbor trial dirs: one line per trial.

Columns: job trial harness reward first_call_ctx uncached_in cache_read cache_write
out reasoning turns wall_s.  first_call_ctx = uncached + cache-write + cache-read of
the first model call (the HarnessTax definition).  Usage: first_call.py JOBDIR...
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

TURN_CAP = 100  # HarnessTax: "cap each attempt at 100 agent turns"

BANDS = {  # HarnessTax SWE-bench Lite first-call context, mean ± SD
    "claude-code": (27011, 6934),
    "codex": (11308, 2683),
    "pi": (1972, 553),
}


def _jsonl(path: Path):
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def claude(trial: Path) -> dict | None:
    files = sorted((trial / "agent" / "sessions" / "projects").glob("*/*.jsonl"))
    if not files:
        return None
    seen, calls = set(), []
    for ev in _jsonl(files[0]):
        if ev.get("type") != "assistant":
            continue
        msg = ev.get("message") or {}
        if msg.get("id") in seen or not msg.get("usage"):
            continue
        seen.add(msg.get("id"))
        calls.append(msg["usage"])
    if not calls:
        return None
    u0 = calls[0]
    return {
        "first_call_ctx": u0.get("input_tokens", 0)
        + u0.get("cache_creation_input_tokens", 0)
        + u0.get("cache_read_input_tokens", 0),
        "uncached_in": sum(c.get("input_tokens", 0) for c in calls),
        "cache_read": sum(c.get("cache_read_input_tokens", 0) for c in calls),
        "cache_write": sum(c.get("cache_creation_input_tokens", 0) for c in calls),
        "cache_write_1h": sum(
            (c.get("cache_creation") or {}).get("ephemeral_1h_input_tokens", 0) for c in calls
        ),
        "out": sum(c.get("output_tokens", 0) for c in calls),
        "reasoning": sum(
            (c.get("output_tokens_details") or {}).get("thinking_tokens", 0) for c in calls
        ),
        "turns": len(calls),
    }


def codex(trial: Path) -> dict | None:
    files = sorted((trial / "agent" / "sessions").glob("*/*/*/rollout-*.jsonl"))
    if not files:
        return None
    # One token_count event follows each model call, so their count is Codex's turn count.
    counts = [
        ev["payload"]["info"]
        for ev in _jsonl(files[0])
        if ev.get("type") == "event_msg"
        and (ev.get("payload") or {}).get("type") == "token_count"
        and (ev["payload"].get("info") or {}).get("last_token_usage")
    ]
    if not counts:
        return None
    # Codex has no turn cap flag: trials past TURN_CAP are truncated there post hoc
    # (tokens up to that call; the outcome is a failure, see stage4.py).
    capped = len(counts) > TURN_CAP
    last = counts[TURN_CAP - 1] if capped else counts[-1]
    first, total = counts[0]["last_token_usage"], last["total_token_usage"]
    cached = total.get("cached_input_tokens", 0)
    return {
        "first_call_ctx": first.get("input_tokens", 0),  # includes cached
        "uncached_in": total.get("input_tokens", 0) - cached,
        "cache_read": cached,
        "cache_write": total.get("cache_write_input_tokens", 0),
        "cache_write_1h": 0,
        "out": total.get("output_tokens", 0),  # includes reasoning
        "reasoning": total.get("reasoning_output_tokens", 0),
        "turns": len(counts),
        "capped": capped,
    }


def pi(trial: Path) -> dict | None:
    files = sorted((trial / "agent" / "pi" / "sessions").glob("*.jsonl"))
    if not files:
        return None
    calls = [
        ev["message"]["usage"]
        for ev in _jsonl(files[0])
        if ev.get("type") == "message"
        and (ev.get("message") or {}).get("role") == "assistant"
        and ev["message"].get("usage")
        and ev["message"].get("stopReason") != "error"  # overload retries log zero usage
    ]
    if not calls:
        return None
    u0 = calls[0]
    return {
        "first_call_ctx": u0.get("input", 0) + u0.get("cacheRead", 0) + u0.get("cacheWrite", 0),
        "uncached_in": sum(c.get("input", 0) for c in calls),
        "cache_read": sum(c.get("cacheRead", 0) for c in calls),
        "cache_write": sum(c.get("cacheWrite", 0) for c in calls),
        "cache_write_1h": 0,
        "out": sum(c.get("output", 0) for c in calls),
        "reasoning": sum(c.get("reasoning", 0) for c in calls),
        "turns": len(calls),
    }


def harness_of(trial: Path) -> str | None:
    for name, marker in (
        ("claude-code", "claude-code.txt"),
        ("codex", "codex.txt"),
        ("pi", "pi.txt"),
    ):
        if (trial / "agent" / marker).exists():
            return name
    # data/trials keeps transcripts but not the multi-GB agent streams: infer from layout
    if (trial / "agent" / "sessions" / "projects").is_dir():
        return "claude-code"
    if (trial / "agent" / "pi").is_dir():
        return "pi"
    if any((trial / "agent" / "sessions").glob("*/*/*/rollout-*.jsonl")):
        return "codex"
    return None


def wall_seconds(result: dict) -> float | None:
    ex = result.get("agent_execution") or {}
    try:
        s = datetime.fromisoformat(ex["started_at"].replace("Z", "+00:00"))
        f = datetime.fromisoformat(ex["finished_at"].replace("Z", "+00:00"))
        return round((f - s).total_seconds(), 1)
    except (KeyError, ValueError, AttributeError):
        return None


def main(argv: list[str]) -> int:
    cols = [
        "job", "trial", "harness", "reward", "first_call_ctx", "uncached_in",
        "cache_read", "cache_write", "out", "reasoning", "turns", "wall_s", "band",
    ]
    print("\t".join(cols))
    for job in map(Path, argv):
        for trial in sorted(p for p in job.iterdir() if (p / "result.json").exists()):
            harness = harness_of(trial)
            if harness is None:
                continue
            row = {"claude-code": claude, "codex": codex, "pi": pi}[harness](trial)
            if row is None:
                continue
            result = json.loads((trial / "result.json").read_text())
            reward = ((result.get("verifier_result") or {}).get("rewards") or {}).get("reward")
            mean, sd = BANDS[harness]
            band = "in" if mean - sd <= row["first_call_ctx"] <= mean + sd else (
                f"{row['first_call_ctx'] - (mean - sd):+d} vs low" if row["first_call_ctx"] < mean - sd
                else f"{row['first_call_ctx'] - (mean + sd):+d} vs high"
            )
            vals = [job.name, trial.name, harness, reward, *[row[c] for c in cols[4:11]],
                    wall_seconds(result), band]
            print("\t".join("" if v is None else str(v) for v in vals))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
