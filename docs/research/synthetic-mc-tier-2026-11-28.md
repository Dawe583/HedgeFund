# Synthetic-path Monte Carlo — the generalization tier, built 2026-11-28

Owner request, same day: build Monte Carlo stress testing into the validation
plane. What existed replayed one tape three ways; what this adds replays the
strategy on price paths that never happened.

## 1. Why the existing trio could not answer the question

| tier | what it resamples | what it cannot see |
|---|---|---|
| permutation MC | trade ordering | entry quality, path-dependence |
| block bootstrap | trade PnL | feedback between signals and tape |
| walk-forward | time windows | regimes that never occurred |
| entries-null | entry timing on the same tape | the tape itself |

Every tier shares the same blind spot: the price path is fixed. The F12
autopsy made that blind spot load-bearing — skill exists in early segments
and decays to zero (persistence, 8 tapes), so the program's central question
became "how regime-fragile is any measured edge?". Only fresh price paths
answer that, because path-dependence is the phenomenon: stops reshape
exposure to vol clustering, entries cluster inside the regimes that birthed
them, and a trade permutation is structurally incapable of seeing either.

## 2. The instrument

`trading/validation/synthetic_paths.py`:

- **Resample**: Politis-Romano stationary bootstrap over bar positions
  (mean block 20), exposed as indices so price ratios, volume and funding
  are drawn from the SAME source bar — the joint within-bar structure
  survives intact.
- **Chaining**: close-to-close multiplication through the resampled blocks,
  gaps and intra-bar ranges transplanted proportionally. The synthetic tape
  is continuous by construction and the OHLC envelope is forced consistent
  (contract tests: 12/12).
- **Execution**: the strategy runs the FULL kernel backtest on each synthetic
  feature frame — features rebuilt per path, injected alpha recomputed
  causally through the family hook. Nothing is approximated at trade level.
- **Funding**: `_funding_rate` travels with its source bar — a time-coherent
  hybrid, documented limitation; the honest alternative (no funding) would
  silently defund the families whose edge IS funding.

## 3. Cost honesty, measured before declaration

One simulation = one full kernel backtest. Measured 2026-11-28: **5.9 s per
3000-bar backtest** (BTCUSDT 1h, TrendMomentum, rails on). A 64-path
ensemble on one cell costs ~6 minutes; on an ML family whose predictions
retrain per path it costs hours. n_simulations is therefore a budget
decision the caller makes explicitly:

- survivor tier inside `validate_core`: **16 paths** — a distribution floor,
  same non-voiding discipline as entries-null. Pays only on validated cells,
  which the program's history says are rare.
- deep ensembles: `backend/scripts/synthetic_mc_probe.py` — owner-invoked,
  writes nothing to the ledger.

## 4. Cost, remeasured honestly

The first cost estimate (5.9 s/sim) priced the baseline backtest into the
average. The deep probe measured 0.53 s per incremental path at 2000 bars —
deep ensembles are cheap for non-ML families and remain the overnight-shaped
compute only where predictions retrain per path. The 16-path survivor
default is therefore conservative, not strained.

## 5. The first measurement, completed

TrendMomentum / BTCUSDT 1h in-sample, 2000 bars, 24 synthetic paths,
0.53 s per simulation end-to-end (the earlier 5.9 s figure priced the
baseline run in; the kernel itself is far cheaper per path once warm):

| metric | value |
|---|---|
| observed Sharpe (real tape) | −4.19 |
| synthetic ensemble mean | −0.74 |
| synthetic p05 … p95 | −5.06 … +2.61 |
| fraction of paths positive | 0.50 |
| generalization p-value | 0.88 |

Reading: 88% of the paths-that-never-happened treat this strategy better
than the tape-that-did. The loss is not a property of the market ensemble —
it is a property of the interaction between this signal logic and the
specific realized path, in the direction the F12 counterfactual established
independently (anti-predictive entries harvesting mean reversion as
momentum). The tier discriminates: a noise strategy would sit near the
middle of its own ensemble; this one sits at its 12th percentile from below.

## 6. What this tier is not

Not a veto. The verdict still stands on the same-tape gates; the
generalization p-value is evidence about fragility, reported in reasons.
The doctrine for ever vetoing on it — like entries-null before it — must be
declared before use, in the program document, with its own budget.
