"""Lesson curation utilities for the ScalpFX learning loop.

Stdlib only. Every public function never raises: on bad input it returns
a safe fallback (empty list / 0) so the trading loop and prompt injection
path can call it unconditionally.
"""

from __future__ import annotations

import re
from pathlib import Path

_WS_RE = re.compile(r"\s+")
_BULLET_RE = re.compile(r"^(?:[-*+>]\s+|\d+[.)]\s+)")

DEFAULT_MAX_LINES = 200


def _normalize(line: str) -> str:
    """Lower-cased, de-bulleted, whitespace-collapsed key for dedup."""
    s = line.strip()
    s = _BULLET_RE.sub("", s)
    s = _WS_RE.sub(" ", s)
    return s.lower()


def dedup_lessons(lines) -> list:
    """Drop exact/near duplicates, keep first occurrence. Never raises."""
    try:
        if lines is None:
            return []
        seen: set[str] = set()
        out: list[str] = []
        for raw in list(lines):
            try:
                if raw is None:
                    continue
                text = str(raw).strip()
                if not text:
                    continue
                key = _normalize(text)
                if not key or key in seen:
                    continue
                seen.add(key)
                out.append(text)
            except Exception:
                continue
        return out
    except Exception:
        try:
            return [str(l).strip() for l in (lines or []) if str(l).strip()][:0] or []
        except Exception:
            return []


def _specificity(line: str) -> float:
    """Higher = more concrete/actionable. Length + quantitative bonuses."""
    try:
        s = line.strip()
        score = float(min(len(s), 300))
        if any(ch.isdigit() for ch in s):
            score += 25.0
        if "%" in s or "pct" in s.lower():
            score += 15.0
        if "x" in s.lower() and any(ch.isdigit() for ch in s):
            score += 5.0
        lowered = s.lower()
        for kw in ("block", "veto", "stop", "trailing", "funding", "conf", "rr", "size"):
            if kw in lowered:
                score += 3.0
                break
        return score
    except Exception:
        return 0.0


def rank_lessons(lines, max_n: int = 10) -> list:
    """Dedup then keep the newest + most specific lines. Never raises.

    LESSONS.md is append-only, so later index = newer. Score mixes
    recency (newer wins) with specificity (concrete numbers win).
    Returns at most max_n lines, best first.
    """
    try:
        try:
            n = int(max_n)
        except Exception:
            n = 10
        if n <= 0:
            return []
        unique = dedup_lessons(lines)
        if not unique:
            return []
        total = len(unique)
        scored: list[tuple[float, str]] = []
        for i, line in enumerate(unique):
            recency = (i / total) * 100.0  # 0 (oldest) .. ~100 (newest)
            scored.append((_specificity(line) + recency, line))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [line for _, line in scored[:n]]
    except Exception:
        return []


def prune_file(path, max_lines: int = DEFAULT_MAX_LINES) -> int:
    """Trim a lesson/journal file to at most max_lines lines. Never raises.

    Preserves the leading header block (``#`` comments / blanks) and keeps
    the newest body lines. Returns the line count after pruning, or 0 when
    the file is missing/unreadable.
    """
    try:
        try:
            limit = int(max_lines)
        except Exception:
            limit = DEFAULT_MAX_LINES
        if limit <= 0:
            return 0
        p = Path(path)
        if not p.exists() or not p.is_file():
            return 0
        text = p.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        if len(lines) <= limit:
            return len(lines)
        # Split leading header (``#`` / blank lines) from the body.
        header_end = 0
        for line in lines:
            s = line.strip()
            if s == "" or s.startswith("#"):
                header_end += 1
            else:
                break
        header = lines[:header_end]
        body = lines[header_end:]
        keep_body = max(0, limit - len(header))
        if keep_body <= 0:
            # Header alone exceeds the limit: keep the newest lines overall.
            kept = lines[-limit:]
        else:
            kept = header + body[-keep_body:] if body else header[:limit]
        p.write_text("\n".join(kept) + "\n", encoding="utf-8")
        return len(kept)
    except Exception:
        return 0
