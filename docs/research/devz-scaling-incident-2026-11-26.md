# dev_z scaling incident — F5/F7/F8 measured 100x off, verdicts invalid

Date: 2026-11-26, late evening. Found during F8 phase-B analysis: the two
`entry_dev` variants produced byte-identical results, which is impossible
for a parameter that gates entries.

## The bug

`atr_pct` in the feature frame is a **fraction of price** (`atr/close`,
measured mean 0.0067 on BTCUSDT 1h — i.e. 0.67% per bar). Three bots —
`continuation_bot` (F7), `meanrev_regime_bot` (F5), `regime_continuation_bot`
(F8) — divided it by 100 again in their dev_z computation:

    atr_abs = atr_pct * close / 100    # wrong: 100x too small

Every ATR was 100x too small, every dev_z 100x too large, so the families'
declared thresholds (dev 1.5-2.5 ATR) actually fired at 0.015-0.025 honest
ATRs — noise-level entries on ~99% of bars (measured directly on the ETH
out-of-sample tape before the fix: |dev_z| >= 1.5 on 99.1% of bars; after
the fix: 34.6%, with p50|z| = 1.01, the sane signature of an ATR-normalized
deviation).

## What this invalidates

- **F5's 48/48-negative verdict** measured fade-the-noise, not
  fade-the-extension. The family verdict is void.
- **F7's validation cluster and phase-B death** measured ride-the-noise.
  Both the in-sample +1.92 and the OOS -0.31 are void. (The edge-decay
  measurement stands structurally but measured the same wrong signal.)
- **F8's 16/16-positive-but-permutation-flat** measured gate-the-noise.
  Void.
- The test fixture for MeanRevRegime carried the same 100x error in the
  opposite direction (atr_pct=0.5 instead of the honest 0.005), which is
  why the tests passed against the bug — fixture and bug were written
  together. Both fixed in the same commit.

## What survives

The kernel, gates, statistics and ledger machinery are untouched — the bug
lived in three strategy files' parameter interpretation, never in the
measurement harness. Ledger rows written under the bug stay in the ledger
(the ledger is the count of everything tried, and these were honestly
tried); re-measured families land as new rows beside them, marked in their
verdict docs.

## The correction

All re-measurement uses the fixed scaling. dev_z distribution after the
fix: p50|z| 1.01, p90 2.80, p99 4.86 — the declared entry thresholds now
mean what the program documents say they mean.
