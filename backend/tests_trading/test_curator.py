"""Tests for trading.agents.curator (stdlib-only lesson curation)."""

import ast
from pathlib import Path

from trading.agents.curator import dedup_lessons, prune_file, rank_lessons


def test_dedup_removes_duplicates_and_blanks():
    lines = [
        "- Trailing stop locks winners",
        "- trailing  stop  locks winners",  # same after normalize
        "  ",
        "- Funding >0.001 blocks longs",
        "- Funding >0.001 blocks longs",
    ]
    out = dedup_lessons(lines)
    assert out == ["- Trailing stop locks winners", "- Funding >0.001 blocks longs"]


def test_dedup_never_raises():
    assert dedup_lessons(None) == []
    assert dedup_lessons([None, 123, "  ok  "]) == ["123", "ok"]
    assert isinstance(dedup_lessons("not-a-list"), list)


def test_rank_keeps_newest_and_most_specific():
    lines = ["- old vague note"] + ["- filler note %d" % i for i in range(5)]
    newest_specific = "- Funding >0.001 blocks longs, OI shocks >8% block everything"
    lines.append(newest_specific)
    ranked = rank_lessons(lines, max_n=3)
    assert len(ranked) == 3
    # newest + most specific line must survive the cut
    assert newest_specific in ranked
    assert ranked[0] == newest_specific


def test_rank_respects_max_n_and_never_raises():
    lines = [f"- lesson {i} with 1.5% detail" for i in range(20)]
    assert len(rank_lessons(lines, max_n=5)) == 5
    assert rank_lessons(lines, max_n=0) == []
    assert rank_lessons(None, max_n=5) == []
    assert rank_lessons(lines, max_n=-1) == []


def test_prune_file_trims_to_limit_and_keeps_header(tmp_path):
    p = tmp_path / "LESSONS.md"
    header = ["# LESSONS", "", "intro line"]
    body = [f"- lesson {i}" for i in range(10)]
    p.write_text("\n".join(header + body) + "\n")
    n = prune_file(p, max_lines=5)
    assert n == 5
    kept = p.read_text().splitlines()
    assert len(kept) == 5
    assert kept[0] == "# LESSONS"
    assert kept[-1] == "- lesson 9"  # newest kept


def test_prune_file_noop_when_short_and_graceful_when_missing(tmp_path):
    p = tmp_path / "L.md"
    p.write_text("- a\n- b\n")
    assert prune_file(p, max_lines=10) == 2
    assert prune_file(tmp_path / "missing.md", max_lines=10) == 0
    assert prune_file(None) == 0


def test_curator_is_stdlib_only():
    src = Path(__file__).resolve().parents[1] / "trading" / "agents" / "curator.py"
    tree = ast.parse(src.read_text())
    allowed = {
        "__future__", "re", "pathlib", "os", "sys", "datetime",
        "collections", "itertools", "functools", "typing", "dataclasses",
        "json", "math", "statistics", "textwrap",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                assert a.name.split(".")[0] in allowed, a.name
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] in allowed, node.module
