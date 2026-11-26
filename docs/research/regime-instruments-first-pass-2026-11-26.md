# Regime instruments — first pass measurement (day 2 item 1, started early)

Date: 2026-11-26, just before midnight. Declared in program-day2-plan as
pure measurement of the existing ledger cells' trades — no new candidates,
no budget spent. All numbers recomputed deterministically: the F8 leader
(regcont-m2-r36-e2.0, ETH 1h, out-of-sample 13 months, rails on), 91 trades.

## The measurements

| instrument | split | mean pnl difference | permutation p (n=2000) |
|---|---|---|---|
| funding crowding | positive funding vs negative | +5.0 USD/trade | 0.332 |
| volatility (atr_pct) | top-30% hot vs bottom-70% | −7.0 USD/trade (hot is worse) | 0.162 |

Direction detail (funding split):

| bucket | n | mean pnl | win rate | long | short |
|---|---|---|---|---|---|
| positive funding (longs pay) | 64 | +3.6 | 44% | −0.2 | **+7.0** |
| negative funding | 27 | −1.3 | 19% | −4.1 | +0.3 |

Volatility detail: low-rvol trades mean +3.9/43% win vs high-rvol +0.4/29%;
atr top-30% mean −2.8 vs bottom-70% +4.2 — the same direction twice.

## The honest verdict

Both instruments point the SAME direction — continuation edge concentrates
in quiet tapes with crowded longs, and fades (or inverts) in hot, short-
crowded ones — but neither split is significant at n=91: the sample is the
limit, not the instruments. Direction consistency across two independent
instruments is weak positive evidence; permutation p 0.33/0.16 is the
honest significance statement: unproven.

## What power would need

The cell's 91 OOS trades split 64/27 already; significance at these effect
sizes needs several hundred trades. Paths: the data-plane expansion (BTCUSDT
1h backfills reach 2025-01 only — deeper history extends every window),
or the F9 family (declared before sweeping, regime-gated continuation with
the winning instrument as the gate) generating its own dense sample. Both
are day-2 decisions, none taken tonight.

Recorded because the ledger cannot say it: this measurement used ONE cell
on ONE symbol — even a significant split here would be a lead, not a gate.
