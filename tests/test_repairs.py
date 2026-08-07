"""Repair-corpus tests (store/repairs.py, A5) — pure Python, no kernel, no tokens.

Retrieval sits on the repair loop's hot path (every round consults it), so these pin both the
ranking contract and the fact that it is served by an index rather than by reading the table.
"""
import sqlite3
import time

import pytest

from store import repairs


@pytest.fixture()
def corpus(tmp_path):
    conn = repairs.connect(tmp_path / "r.sqlite")
    yield conn
    conn.close()


def _seed(conn):
    """Four rows: two single-token, one two-token, one disjoint. Distinct `created` for tie-breaks."""
    for broken, source, failures in [
        ("b1", "p1", [{"check": "min_wall"}]),
        ("b2", "p2", [{"check": "min_wall"}, {"check": "cover"}]),
        ("b3", "p3", [{"check": "min_wall"}]),
        ("b4", "p4", [{"check": "hole_count"}]),
    ]:
        repairs.record(conn, broken=broken, fixed=f"fixed_{broken}", source=source, failures=failures)
        time.sleep(0.01)


def test_ranking_is_overlap_first_then_newest(corpus):
    _seed(corpus)
    hits = repairs.retrieve(corpus, [{"check": "min_wall"}, {"check": "cover"}], k=3)
    assert [h["broken"] for h in hits] == ["b2", "b3", "b1"]   # overlap 2, then the two overlap-1 newest-first
    assert hits[0]["overlap"] == 2 and hits[1]["overlap"] == 1


def test_a_disjoint_signature_retrieves_nothing(corpus):
    _seed(corpus)
    assert repairs.retrieve(corpus, [{"check": "nothing_matches"}]) == []
    assert repairs.retrieve(corpus, []) == []                  # no tokens at all → no query, no rows


def test_exclude_source_is_the_leakage_guard(corpus):
    _seed(corpus)
    hits = repairs.retrieve(corpus, [{"check": "min_wall"}, {"check": "cover"}], k=5,
                            exclude_source="p2")
    assert [h["broken"] for h in hits] == ["b3", "b1"]         # the best-overlap row is dropped
    assert all(h["source"] != "p2" for h in hits)


def test_k_bounds_the_result(corpus):
    _seed(corpus)
    assert len(repairs.retrieve(corpus, [{"check": "min_wall"}], k=1)) == 1
    assert len(repairs.retrieve(corpus, [{"check": "min_wall"}], k=99)) == 3


def test_retrieval_is_served_by_an_index_not_a_table_scan(corpus):
    _seed(corpus)
    plan = corpus.execute(
        "EXPLAIN QUERY PLAN "
        "SELECT r.*, COUNT(*) AS overlap FROM repair r JOIN repair_token t ON t.repair_id = r.id "
        "WHERE t.token IN (?,?) GROUP BY r.id ORDER BY overlap DESC, r.created DESC LIMIT ?",
        ("min_wall", "cover", 2)).fetchall()
    detail = " ".join(row[-1] for row in plan)
    assert "repair_token_tok" in detail                        # the token index carries the lookup
    assert "SCAN repair " not in detail                        # and we never read the whole table


def test_dedup_still_holds_and_keeps_the_token_index_consistent(corpus):
    f = [{"check": "min_wall"}]
    repairs.record(corpus, broken="b", fixed="f", source="p", failures=f)
    repairs.record(corpus, broken="b", fixed="f", source="p", failures=f)   # identical triple
    assert corpus.execute("SELECT COUNT(*) FROM repair").fetchone()[0] == 1
    assert corpus.execute("SELECT COUNT(*) FROM repair_token").fetchone()[0] == 1
    assert len(repairs.retrieve(corpus, f)) == 1


def test_a_build_error_signature_round_trips(corpus):
    repairs.record(corpus, broken="b", fixed="f", source="p",
                   err="GeometryBuildError: hole is off the part (op=hole)")
    hits = repairs.retrieve(corpus, err="GeometryBuildError: something about a hole")
    assert len(hits) == 1 and hits[0]["signature"] == "build:hole"


def test_a_corpus_mined_before_the_token_table_still_works(tmp_path):
    # An existing store/repairs.sqlite must keep working with no migration step and no re-mine.
    path = tmp_path / "legacy.sqlite"
    old = sqlite3.connect(str(path))
    old.executescript(
        "CREATE TABLE repair (id INTEGER PRIMARY KEY AUTOINCREMENT, signature TEXT NOT NULL, "
        "detail TEXT NOT NULL, broken TEXT NOT NULL, fixed TEXT NOT NULL, source TEXT NOT NULL, "
        "created REAL NOT NULL);")
    old.execute("INSERT INTO repair VALUES (1,'cover min_wall','0.5<1.5','old_b','old_f','pool_x',1.0)")
    old.commit()
    old.close()

    conn = repairs.connect(path)                               # backfills on open
    hits = repairs.retrieve(conn, [{"check": "min_wall"}])
    assert [h["broken"] for h in hits] == ["old_b"]
    assert repairs._backfill_tokens(conn) == 0                 # idempotent — nothing left to do
    conn.close()


def test_as_prompt_renders_a_minimal_diff(corpus):
    repairs.record(corpus, broken="hole(e,(35,0))", fixed="hole(e,(28,0))", source="p",
                   failures=[{"check": "min_wall", "message": "0.5 < 1.5"}])
    text = repairs.as_prompt(repairs.retrieve(corpus, [{"check": "min_wall"}]))
    assert "min_wall" in text and "```diff" in text and "28" in text
    assert repairs.as_prompt([]) == ""                          # off → the prompt is unchanged
