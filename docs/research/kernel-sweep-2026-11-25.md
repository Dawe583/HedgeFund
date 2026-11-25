# Kernel baseline sweep — 2026-11-25

The first validation sweep produced entirely by the nautilus kernel harness
(engine_version `nautilus-1.231.0+delayed-close`). Same matrix, data, seed and
gate as `sweep-2026-11-25.md` — 4 bots × 2 symbols × {4h, 1h}, 365 days of
Binance klines, seed 42 — so the two tables read as the engine migration's
effect on verdicts, apples to apples. Rows are written to `backend/data.db`
(the dashboard reads them there); every row carries its engine version, so
pre-kernel and kernel rows never read as the same experiment.

## Results — 16/16 REJECTED on the kernel, as on the ported engine

| bot | symbol | tf | kernel trades | ported trades | kernel perm_p | verdict (both engines) |
|---|---|---|---|---|---|---|
| scalp | BTCUSDT | 4h | 28 | 36 | 0.382 | rejected |
| scalp | BTCUSDT | 1h | 164 | 167 | 0.891 | rejected |
| scalp | ETHUSDT | 4h | 38 | 44 | 0.966 | rejected |
| scalp | ETHUSDT | 1h | 152 | 165 | 0.221 | rejected |
| hft | BTCUSDT | 4h | 39 | 40 | 0.410 | rejected |
| hft | BTCUSDT | 1h | 145 | 151 | 0.760 | rejected |
| hft | ETHUSDT | 4h | 36 | 36 | 0.696 | rejected |
| hft | ETHUSDT | 1h | 140 | 136 | 0.665 | rejected |
| breakout | BTCUSDT | 4h | 76 | 79 | 0.299 | rejected |
| breakout | BTCUSDT | 1h | 298 | 317 | 0.634 | rejected |
| breakout | ETHUSDT | 4h | 85 | 87 | 0.645 | rejected |
| breakout | ETHUSDT | 1h | 309 | 325 | 0.763 | rejected |
| meanrev | BTCUSDT | 4h | 212 | 271 | 0.710 | rejected |
| meanrev | BTCUSDT | 1h | 779 | 962 | n/a† | rejected |
| meanrev | ETHUSDT | 4h | 197 | 254 | 0.791 | rejected |
| meanrev | ETHUSDT | 1h | 790 | 989 | n/a† | rejected |

† permutation test inconclusive for the same reason as in the ported sweep:
shuffled orderings hit zero equity — catastrophic loss-making either way.

**VALIDATED: 0 — REJECTED: 16, on both engines.**

## What the comparison says

- **The verdict is engine-invariant for all sixteen cells.** No strategy sits
  anywhere near the gate boundary on either engine — the closest to passing
  in either sweep (hft BTCUSDT 4h) fails the permutation test at p 0.41–0.54
  regardless of fill model. The migration changed no investment-relevant
  answer, which is the strongest available evidence the kernel harness is not
  silently broken in a direction that matters.
- **Kernel trade counts run 5–20 % below ported counts.** Expected, not
  alarming: the kernel's gap-through fills are worse for the trader (fills at
  the open, not the stop price), its intrabar path is O→H→L→C rather than
  stop-first, and its entries fill at close rather than open — three small
  execution differences that compound through trade survival, exactly as the
  reference diff (`kernel-diff-2026-11-25.md`) analyzed. The kernel model is
  the more honest of the two wherever they differ (gap fills and causal ATR
  sizing especially).
- **meanrev trade counts dropped the most** (962→779, 989→790 on 1h): the
  highest-frequency strategies are the most sensitive to fill timing, and
  they remain catastrophic on any engine — bleeding accounts dry either way.
- Nothing in these numbers says any of the four strategies should trade.
  That conclusion was true before the migration and survives it unchanged.

## Note on what this sweep is not

It is not a re-validation decision input — the ported sweep already answered
"nothing goes to paper". It is the kernel migration's regression baseline:
future validation rows are kernel-produced, and this table is what honest
kernel output looks like on known data.
