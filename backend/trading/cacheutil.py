"""Content-keyed cache discipline — one home for digest and eviction.

The honesty failure this module exists to close (F-8, whole-system analysis
2026-11-27): caches keyed by POSITION (len, first/last row) or by config
alone serve stale truth forever — a repaired hole of equal length produces
an artifact hit computed on pre-fix data. The fix is structural: every
cache filename carries a digest of the exact frame content the computation
consumed, so new data produces a new key rather than a stale hit, and
writing the new artifact evicts its stale predecessors.

Determinism across processes: pd.util.hash_pandas_object uses a fixed-seed
hasher (not PYTHONHASHSEED-dependent), verified empirically across seeds.
Cost measured: ~3ms for a 30k-row frame — tens of thousands of rows is the
program ceiling, so full-content hashing is cheap; no sampling shortcuts.
"""

from __future__ import annotations

import hashlib
import re

import pandas as pd

# 16 hex chars of sha256 = 64 bits; collision risk across the program's
# artifact counts is negligible and the glob eviction stays legible
DIGEST_LEN = 16


def frame_digest(df: pd.DataFrame) -> str:
    """Content digest of a dataframe: row count, index, column names,
    dtypes, and every value — everything a computation consuming the frame
    can possibly be a function of. Column names enter explicitly because
    hash_pandas_object covers values/index/dtypes but not names."""
    h = hashlib.sha256()
    h.update(str(len(df)).encode())
    h.update("|".join(str(c) for c in df.columns).encode())
    h.update(str(df.index.dtype).encode())
    h.update(pd.util.hash_pandas_object(df, index=True).to_numpy().tobytes())
    return h.hexdigest()[:DIGEST_LEN]


def panel_digest(panel: dict[str, pd.DataFrame]) -> str:
    """Digest of a dict-of-frames panel (the alpha bench's wide OHLCV
    contract): every frame's content digest plus its key, key order
    canonicalized so dict iteration order never matters."""
    h = hashlib.sha256()
    for name in sorted(panel):
        h.update(name.encode())
        h.update(frame_digest(panel[name]).encode())
    return h.hexdigest()[:DIGEST_LEN]


def artifact_file(cache_dir, stem: str, digest: str, ext: str = ".pkl"):
    """Canonical artifact path: the stem is everything EXCEPT the digest
    (function/params component), the digest is the data-content component.
    Readers hit only same-content artifacts; writers evict predecessors."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{stem}-{digest}{ext}"


# strict shape: stem + "-" + exactly DIGEST_LEN lowercase hex + ext — so
# `evict_stale` never swallows an artifact whose stem merely happens to be
# a prefix of the evicted stem (e.g. h6 vs h60 params both starting "-h6")
_STALE_RE = re.compile(r"^(?P<stem>.+)-(?P<digest>[0-9a-f]{%d})(?P<ext>\.[A-Za-z0-9]+)$" % DIGEST_LEN)


def evict_stale(cache_dir, stem: str, keep_digest: str) -> None:
    """Delete same-family artifacts whose key matches everything except
    the digest — the stale predecessors of the computation now being
    written. The artifact being written (keep_digest) survives. Simple
    glob-and-delete by design: no daemon, no timers, eviction happens
    exactly where fresh truth is written."""
    for path in cache_dir.iterdir():
        m = _STALE_RE.match(path.name)
        if m and m["stem"] == stem and m["digest"] != keep_digest:
            path.unlink(missing_ok=True)


def write_artifact(cache_dir, stem: str, digest: str, obj, ext: str = ".pkl"):
    """Pickle obj to its content-keyed path, evicting stale predecessors
    first. Evict-before-write keeps the freshest write alive even in the
    pathological multiprocess interleaving — a concurrent same-stem writer
    never deletes the file matching its own digest."""
    import pickle

    evict_stale(cache_dir, stem, digest)
    path = artifact_file(cache_dir, stem, digest, ext)
    with open(path, "wb") as fh:
        pickle.dump(obj, fh)
    return path
