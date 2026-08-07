"""BenchCAD loader — the public, CadQuery-native benchmark (B1, docs/BENCH_PLAN.md).

Why this set: `eval/briefs.py` is 15 briefs we wrote ourselves, all L1 prismatic. BenchCAD
(arXiv 2605.10865) is third-party, built from 17,900 execution-verified CadQuery programs across
106 industrial part families drawn from 47 ISO/DIN/EN/ASME/IEC standards. Its `edit-bench` config
grades instruction-guided editing — Ludwig's locked minimal-diff `--edit` thesis (BRIEF §10) — with
no vision required, against a published frontier number (GPT-5.3 thinking, 0.865 normalized accuracy).

Held-out, exactly like `eval/briefs.py`: capabilities may be added because a failure named them;
prompts are NEVER tuned against it.

Dependency posture matches the rest of the core — stdlib `urllib` for the download, and `pyarrow`
imported LAZILY inside the reader, so `--selftest` stays green without it.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

# The parquet conversion HF serves for the `edit-bench` config (one file, ~114 MB).
_EDIT_URL = ("https://huggingface.co/datasets/BenchCAD/BenchCAD/resolve/"
             "refs%2Fconvert%2Fparquet/edit-bench/edit_bench/0000.parquet")

_DATA = Path(__file__).resolve().parent.parent / "data"   # gitignored; pulled on demand

# The columns the harness reads. `orig_step`/`gt_step` are real ISO-10303-21 binaries — the B2
# fixtures — and dominate the file size, so they are opt-in.
_CORE_COLS = ["record_id", "family", "edit_type", "category", "category_label",
              "instruction", "iou", "orig_code", "gt_code"]


class DatasetMissing(RuntimeError):
    """The parquet isn't cached and the caller asked us not to download it."""


def cache_path() -> Path:
    return _DATA / "benchcad_edit.parquet"


def ensure(*, download: bool = True, quiet: bool = False) -> Path:
    """Return the cached parquet path, downloading it once if needed.

    The download is atomic (temp file → rename), so an interrupted pull never leaves a half file
    that later reads as a corrupt dataset.
    """
    path = cache_path()
    if path.exists() and path.stat().st_size > 0:
        return path
    if not download:
        raise DatasetMissing(
            f"BenchCAD edit-bench is not cached at {path}. Run without --no-download to fetch it "
            f"(~114 MB, once) from {_EDIT_URL}")
    import urllib.request

    _DATA.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    if not quiet:
        print(f"› fetching BenchCAD edit-bench (~114 MB, once) → {path}")
    # A timeout is load-bearing on a 114 MB pull: without one, a stalled connection (a captive
    # portal, a half-open socket) hangs the command forever with no output and no way to tell it
    # from a slow link. urlopen's timeout applies per socket operation, so a slow-but-alive
    # download is unaffected — only a genuinely dead one trips it.
    timeout = float(os.environ.get("LUDWIG_FETCH_TIMEOUT_S", "60"))
    try:
        with urllib.request.urlopen(_EDIT_URL, timeout=timeout) as resp, open(tmp, "wb") as fh:  # noqa: S310
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while chunk := resp.read(1 << 20):
                fh.write(chunk)
                done += len(chunk)
                if not quiet and total:
                    print(f"\r  {done / 1e6:6.1f} / {total / 1e6:.1f} MB", end="", flush=True)
        if not quiet:
            print()
        if total and done < total:      # truncated mid-stream: better to fail than to cache a stub
            raise RuntimeError(f"download truncated at {done / 1e6:.1f} of {total / 1e6:.1f} MB")
    except Exception:
        tmp.unlink(missing_ok=True)     # never leave a .part behind to confuse the next run
        raise
    os.replace(tmp, path)               # atomic: an interrupted pull never becomes a corrupt dataset
    return path


def load(*, limit: Optional[int] = None, family: Optional[str] = None, seed: int = 0,
         with_step: bool = False, download: bool = True, quiet: bool = False) -> list[dict[str, Any]]:
    """Load edit-bench rows as plain dicts.

    `limit` takes a DETERMINISTIC stratified sample (see `stratify`) so a partial run still spans
    the part families rather than reporting whatever the first N rows happen to be. `family` filters
    to one family first. `with_step` additionally pulls the `orig_step`/`gt_step` binaries.
    """
    path = ensure(download=download, quiet=quiet)
    try:
        import pyarrow.parquet as pq  # noqa: PLC0415 (lazy by design — core stays dependency-light)
    except ImportError as e:
        raise RuntimeError(
            "the BenchCAD harness needs pyarrow to read the parquet (`pip install pyarrow`); "
            "it is imported lazily so the rest of the spine stays green without it."
        ) from e

    cols = list(_CORE_COLS) + (["orig_step", "gt_step"] if with_step else [])
    rows = pq.read_table(path, columns=cols).to_pylist()
    if family:
        rows = [r for r in rows if r["family"] == family]
    rows.sort(key=lambda r: r["record_id"])          # a stable base order, independent of file layout
    return stratify(rows, limit, seed=seed) if limit else rows


def stratify(rows: list[dict], limit: Optional[int], *, seed: int = 0) -> list[dict]:
    """Deterministically sample `limit` rows spread across `family`.

    Round-robins the families (rotated by `seed`) taking one row at a time, so limit=20 over 106
    families returns 20 DIFFERENT families rather than 20 variants of one part. Pure function —
    no I/O, no kernel — so the selftest exercises it directly.
    """
    if limit is None or limit >= len(rows):
        return rows
    buckets: dict[str, list[dict]] = {}
    for r in rows:
        buckets.setdefault(r["family"], []).append(r)
    names = sorted(buckets)
    if seed:
        seed %= len(names)
        names = names[seed:] + names[:seed]
    out: list[dict] = []
    depth = 0
    while len(out) < limit:
        took = False
        for n in names:
            if depth < len(buckets[n]):
                out.append(buckets[n][depth])
                took = True
                if len(out) == limit:
                    break
        if not took:                                  # every bucket exhausted
            break
        depth += 1
    return out


def families(rows: list[dict]) -> dict[str, int]:
    """Row count per part family — the coverage line a run prints."""
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["family"]] = counts.get(r["family"], 0) + 1
    return counts
