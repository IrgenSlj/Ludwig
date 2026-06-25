"""eval — the frozen held-out brief set + the first-pass geometric pass-rate harness ([H6]).

Only the pure brief data is re-exported here; harness/reference import the kernel lazily, so
`import eval` stays clean before cadquery is installed.
"""
from eval.briefs import BRIEFS

__all__ = ["BRIEFS"]
