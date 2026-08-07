"""The repair corpus (S-MEM / A5) — remembered (critic-failure → successful fix) pairs.

HARNESS_BRIEF §3.3: the R-series proved the critic's *exact* error signal is what closes the
60%→100% gap; this store gives repair *remembered* fixes so the loop converges faster (fewer rounds,
fewer tokens) and — the bet — more reliably. It is MEASURED, never assumed (principle #12): it ships
default-on only if a frozen-set eval shows it moves post-repair rate or repair rounds. Until then it is
off (`memory.repair_corpus` in standards.yaml, or `LUDWIG_REPAIR_CORPUS=on|off`).

Design choices:
- **Retrieval key is a controlled vocabulary** — the set of *base* critic check-names (`min_wall`,
  `dimensional`, `hole_count`, …) or a build-error class. So a plain table + Python token-overlap
  ranking is cleaner and more robust than FTS5, which is reserved for A6's free-text brief retrieval.
- **No leakage by construction.** The corpus is mined from a SEPARATE pool of briefs (`eval/pool.py`),
  never the frozen held-out set (`eval/briefs.py`). `source` tags every row so a grading run can also
  exclude a source defensively. The frozen eval only ever *reads* the corpus, never writes it.
"""
from __future__ import annotations

import difflib
import os
import sqlite3
import time
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parent
DEFAULT_PATH = _ROOT / "repairs.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS repair (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    signature  TEXT NOT NULL,      -- space-joined base check-names / build-error class (the retrieval key)
    detail     TEXT NOT NULL,      -- the concrete failure messages (context for the few-shot)
    broken     TEXT NOT NULL,      -- the program that failed the critic
    fixed      TEXT NOT NULL,      -- the program that then passed
    source     TEXT NOT NULL,      -- provenance (a pool brief id) — the leakage guard
    created    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS repair_sig ON repair(signature);   -- serves the record() dedup probe

-- A signature is a SET of base check-names, and retrieval ranks by set overlap. Storing the set
-- exploded one-token-per-row is what lets that ranking be an indexed JOIN instead of "read the whole
-- table, then rank in Python" — which is what `retrieve` used to do, on the A5 measurement's hot path.
CREATE TABLE IF NOT EXISTS repair_token (
    repair_id  INTEGER NOT NULL REFERENCES repair(id) ON DELETE CASCADE,
    token      TEXT NOT NULL,
    PRIMARY KEY (repair_id, token)
);
CREATE INDEX IF NOT EXISTS repair_token_tok ON repair_token(token);
"""


# --------------------------------------------------------------------------- #
# flag
# --------------------------------------------------------------------------- #

def enabled() -> bool:
    """Is the repair corpus switched on? Env `LUDWIG_REPAIR_CORPUS` wins; else `memory.repair_corpus`
    in standards.yaml; else OFF (measure-don't-assert default until it earns its bytes)."""
    env = os.environ.get("LUDWIG_REPAIR_CORPUS")
    if env is not None:
        return env.strip().lower() in ("1", "on", "true", "yes")
    try:
        from toolkit.standards import load
        return bool((load().get("memory", {}) or {}).get("repair_corpus", False))
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# signature — a Critique's failures (or a build error) → a normalized retrieval key
# --------------------------------------------------------------------------- #

def signature_of(failures=None, err: Optional[str] = None) -> str:
    """A compact, generalizable key: the sorted unique BASE check-names that failed, or the build-error
    class. `cover:anchor_1` and `cover:anchor_2` both fold to `cover`; a GeometryBuildError on a hole
    folds to `build:hole`. This is what makes a remembered fix generalize across parts."""
    if err:
        low = err.lower()
        cls = err.split(":", 1)[0].strip() or "error"
        for op in ("hole", "fillet", "chamfer", "boolean", "cut", "fuse", "sketch", "extrude"):
            if op in low:
                return f"build:{op}"
        return f"build:{cls}"
    names = set()
    for c in (failures or []):
        raw = getattr(c, "check", None) or (c.get("check") if isinstance(c, dict) else None) or ""
        base = str(raw).split(":", 1)[0].strip()
        if base:
            names.add(base)
    return " ".join(sorted(names)) if names else "unspecified"


def _detail_of(failures=None, err: Optional[str] = None) -> str:
    if err:
        return err
    parts = []
    for c in (failures or []):
        chk = getattr(c, "check", None) or (c.get("check") if isinstance(c, dict) else "")
        msg = getattr(c, "message", None) or (c.get("message") if isinstance(c, dict) else "")
        parts.append(f"{chk}: {msg}".strip().rstrip(":").strip())
    return "; ".join(p for p in parts if p) or "unspecified"


# --------------------------------------------------------------------------- #
# persistence
# --------------------------------------------------------------------------- #

def connect(path: Path = DEFAULT_PATH) -> sqlite3.Connection:
    """Open (creating/upgrading) the corpus. Idempotent, and safe on a corpus mined before the token
    table existed — `_backfill_tokens` reindexes any pre-existing rows in place, so an old
    `store/repairs.sqlite` keeps working without a migration step or a re-mine."""
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    _backfill_tokens(conn)
    return conn


def _index_tokens(conn: sqlite3.Connection, repair_id: int, signature: str) -> None:
    conn.executemany("INSERT OR IGNORE INTO repair_token (repair_id, token) VALUES (?,?)",
                     [(repair_id, t) for t in set(signature.split()) if t])


def _backfill_tokens(conn: sqlite3.Connection) -> int:
    """Index any repair row that has no tokens yet. Returns how many rows were backfilled."""
    rows = conn.execute(
        "SELECT id, signature FROM repair WHERE id NOT IN (SELECT repair_id FROM repair_token)"
    ).fetchall()
    for r in rows:
        _index_tokens(conn, r["id"], r["signature"])
    if rows:
        conn.commit()
    return len(rows)


def record(conn: sqlite3.Connection, *, broken: str, fixed: str, source: str,
           failures=None, err: Optional[str] = None) -> str:
    """Store one (failure → fix) pair. Returns the signature it was filed under. A no-op-safe upsert:
    an identical (signature, broken, fixed) triple is not duplicated."""
    sig = signature_of(failures, err)
    detail = _detail_of(failures, err)
    dup = conn.execute(
        "SELECT 1 FROM repair WHERE signature=? AND broken=? AND fixed=? LIMIT 1",
        (sig, broken, fixed)).fetchone()
    if not dup:
        cur = conn.execute(
            "INSERT INTO repair (signature, detail, broken, fixed, source, created) VALUES (?,?,?,?,?,?)",
            (sig, detail, broken, fixed, source, time.time()))
        _index_tokens(conn, cur.lastrowid, sig)   # keep the retrieval index in step with the row
        conn.commit()
    return sig


def _overlap(a: str, b: str) -> int:
    """Token overlap between two signatures — the ranking score (controlled vocab, so exact overlap)."""
    return len(set(a.split()) & set(b.split()))


def retrieve(conn: sqlite3.Connection, failures=None, err: Optional[str] = None, *,
             k: int = 2, exclude_source: Optional[str] = None) -> list[dict]:
    """Top-k past fixes whose failure signature overlaps this one, best overlap first (ties: newest).

    The overlap ranking runs as an indexed JOIN over `repair_token` and returns only the k rows it
    needs. It previously did `SELECT * FROM repair` and ranked in Python — which read every stored
    `broken`/`fixed` PROGRAM into memory just to score the signatures, on the path the repair loop
    hits on every round. The ordering is unchanged (overlap desc, then newest).

    `exclude_source` drops rows from a given provenance — a belt-and-braces leakage guard on top of
    the mine-from-pool-only rule — and is applied in SQL so an excluded row never leaves the DB.
    """
    tokens = [t for t in set(signature_of(failures, err).split()) if t]
    if not tokens:
        return []
    sql = (
        "SELECT r.*, COUNT(*) AS overlap FROM repair r "
        "JOIN repair_token t ON t.repair_id = r.id "
        f"WHERE t.token IN ({','.join('?' * len(tokens))})"
        + (" AND r.source <> ?" if exclude_source is not None else "") +
        " GROUP BY r.id ORDER BY overlap DESC, r.created DESC LIMIT ?"
    )
    params = [*tokens] + ([exclude_source] if exclude_source is not None else []) + [int(k)]
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


# --------------------------------------------------------------------------- #
# few-shot rendering — a remembered fix as a MINIMAL diff (the whole thesis: small change)
# --------------------------------------------------------------------------- #

def _min_diff(broken: str, fixed: str, max_lines: int = 14) -> str:
    diff = list(difflib.unified_diff(
        broken.splitlines(), fixed.splitlines(), lineterm="", n=1))
    body = [ln for ln in diff if ln and ln[0] in "+-" and not ln.startswith(("+++", "---"))]
    return "\n".join(body[:max_lines]) if body else "(no textual diff)"


def as_prompt(entries: list[dict]) -> str:
    """Render retrieved fixes as a repair-prompt section — signature + the concrete failure + the minimal
    diff that fixed it. Empty string when there's nothing to add (so the prompt is unchanged when off)."""
    if not entries:
        return ""
    blocks = []
    for e in entries:
        blocks.append(
            f"- when [{e['signature']}] failed ({e['detail']}), this minimal change fixed it:\n"
            f"```diff\n{_min_diff(e['broken'], e['fixed'])}\n```")
    return ("## Remembered fixes — how a similar failure was repaired before (apply the analogous "
            "minimal change; do NOT copy verbatim if the geometry differs)\n" + "\n".join(blocks) + "\n")
