"""Cost curve v1 — slippage as a function of the bar, not a flat rate.

Flat 2bps silently decides life and death for intraday families (90-day
plan, weeks 7-8): a mean-reversion entry earning 15bps of edge pays a
fixed 4bps round trip regardless of whether it filled in a dead-quiet
or a panic bar. Reality has a shape, and the shape is knowable from the
bar itself:

    slip_bps(bar) = slippage_bps  +  COST_RANGE_COEF * (high - low) / close * 10_000
                    ────────────     ──────────────────────────────────────────────
                    spread+taker     volatility-scaled impact proxy, capped

- The flat term stays: Binance taker is ~4-5bps round trip of fees already
  modeled separately — the flat slippage floor is the half-spread and the
  minimum marketable-order cost, present in every bar however quiet.
- The range term: a bar's (high - low) / close is the only honest liquidity
  stress signal a candle carries. At the desk's sizes (hundreds of dollars
  of notional against Binance depth) participation is negligible and true
  impact is a rounding error — the term therefore proxies SPREAD STRESS,
  not impact: in quiet bars the effective half-spread is a bp or two, in
  a 1% range bar it is several, in a panic it is whatever the panic costs.
  The coefficient is an ASSUMPTION, declared here — no fill data exists
  anywhere in the program to fit it, and none can: paper fills are model
  fills by construction. The value is pessimistic by design because the
  gate's job is killing false edges; an edge that survives pessimistic
  costs is worth believing, and the pessimism is documented rather than
  hidden in a flat rate nobody could see.
- Cap: slippage never exceeds 25bps one way. A cost model that can charge
  more than the edge ever was becomes the strategy, and the measurement
  stops meaning anything.
- Participation vs volume is deliberately ABSENT in v1: sizing is a
  fraction of equity regardless of volume, so a participation term would
  be a constant in disguise pretending to be a measurement. The v2 hook
  is volume-aware sizing, not volume-aware costs on volume-blind sizing.

Every consumer applies the curve per-fill on the bar that filled — entry
cost on the entry bar, exit cost on the exit bar: a panic exit costs what
a panic costs, which is the entire point. Rows measured before this
module carry the flat model; the reconstruction's provenance (engine
version / config hash) already separates the eras, and the sweep ledger's
reasons name the cost model from the first row that uses it.
"""

from __future__ import annotations

# declared assumption, not a fit — see the module docstring
COST_RANGE_COEF = 0.2
SLIPPAGE_CAP_BPS = 25.0


def bar_slippage_bps(high: float, low: float, close: float, flat_bps: float) -> float:
    """One-way slippage in basis points for a fill inside the given bar.

    Degenerate bars (zero close, inverted range, missing values) fall back
    to the flat floor: a cost model never invents data, it degrades to the
    assumption it replaces."""
    try:
        hi, lo, cl = float(high), float(low), float(close)
        flat = float(flat_bps)
    except (TypeError, ValueError):
        return float(flat_bps)
    import math
    if cl <= 0 or math.isnan(hi) or math.isnan(lo) or math.isnan(cl):
        return flat
    rng = max(hi - lo, 0.0) / cl
    return min(flat + COST_RANGE_COEF * rng * 10_000, SLIPPAGE_CAP_BPS)


def apply_slippage(price: float, side: str, is_entry: bool, slip_bps: float) -> float:
    """The directional application — buyer pays up, seller receives down.
    side is the POSITION side; entry pays against it, exit with it."""
    s = slip_bps / 10_000
    adverse = (side == "long") == is_entry
    return price * (1 + s) if adverse else price * (1 - s)
