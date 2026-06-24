"""Parse the orchestrator's stdout progress lines into structured SSE events.

Strangler-fig: ``ludwig.py`` already prints human progress as it runs the loop; we
capture that stream and turn the recognizable lines into typed events instead of
modifying the loop to emit callbacks (that comes with the M4 contracts refactor).
Unrecognized lines pass through as ``log`` events so nothing is lost.
"""
from __future__ import annotations

import re

_ROUND = re.compile(r"=== Round (\d+)/(\d+)\s+\(panel of (\d+)\)")
_CANDIDATE = re.compile(r"candidate (.+?): score ([\d.]+)")
_BEST = re.compile(r"best so far: ([\d.]+)/10\s+→\s+(.+)")
_HERO_START = re.compile(r"rendering hero shot")
_HERO_OK = re.compile(r"✓ hero: (.+)")
_WINNER = re.compile(r"Winner: (.+?)\s+\(score ([\d.]+)/10\)")
_CLEARED = re.compile(r"cleared the quality bar")


def parse_line(line: str) -> dict | None:
    """Map one stdout line to a structured event, or None to drop it."""
    s = line.strip()
    if not s:
        return None
    if m := _ROUND.search(s):
        return {"type": "round", "round": int(m.group(1)),
                "rounds": int(m.group(2)), "candidates": int(m.group(3))}
    if m := _CANDIDATE.search(s):
        return {"type": "candidate", "label": m.group(1), "score": float(m.group(2))}
    if m := _BEST.search(s):
        return {"type": "best", "score": float(m.group(1)), "path": m.group(2)}
    if _HERO_START.search(s):
        return {"type": "hero_start"}
    if m := _HERO_OK.search(s):
        return {"type": "hero", "path": m.group(1)}
    if m := _WINNER.search(s):
        return {"type": "winner", "path": m.group(1), "score": float(m.group(2))}
    if _CLEARED.search(s):
        return {"type": "cleared"}
    return {"type": "log", "message": s}
