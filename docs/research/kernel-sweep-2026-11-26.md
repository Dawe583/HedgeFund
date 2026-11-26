# Kernel revalidation sweep — 2026-11-26 (sizing rails live)

Third sweep of the same matrix, first with the **M3 slice-3 sizing rails active**
in the kernel harness. Same contract as `sweep-2026-11-25.md` and
`kernel-sweep-2026-11-25.md`: 4 bots × 2 symbols × {4h, 1h}, the same 365 days of
Binance klines from `backend/data/research.db` (2025-11-25 → 2026-11-25, seed 42,
1000 permutations, 1000 bootstrap resamples, 5 walk-forward windows). Verdict rows
are in `/tmp/kernel-sweep-2026-11-26.db` (dedicated scratch db — `backend/data.db`
was never touched); every row carries `engine_version nautilus-1.231.0+delayed-close`.

## Why this sweep exists — the re-run decision

The 2026-11-25 kernel baseline (16/16 rejected, verdicts engine-invariant) was
committed at 2026-11-25 21:12. The sizing rails — approved-leverage scaling, hard
exposure caps with vetoed entries, and layer-0 rails (12 % drawdown kill-switch,
daily loss limit, loss-streak cooldown) — landed at 2026-11-26 01:39
(`9c3fb46`, M3 slice 3), **after** that sweep. The caps/rail machinery vetoed entries
into different trade sequences, so the baseline verdicts could not be assumed
invariant — a re-run was required, not verification of existing rows.

## Engine facts this sweep ran under

- Kernel harness, `run_kernel_backtest` exclusively (the ported engine no longer
  feeds validation verdicts).
- `BTConfig` defaults: leverage 1.0, `max_symbol_exposure` 5×, `max_gross_exposure` 8×,
  kill-switch at 12 % drawdown, daily loss limit 5 %, loss-streak cooldown 3.
- Rails are **active in backtest**: entries the caps or rails refuse are vetoed with a
  recorded reason, never resized; sizing uses signal-bar ATR (causal).
- Production parameters only, as registered in the strategy catalog — no optimization.

## Results — 16/16 REJECTED

| bot | symbol | tf | trades (was kernel-baseline) | pf | sharpe | max_dd % | perm_p | ci_lo | wf | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| scalp | BTCUSDT | 4h | 20 (28) | 0.945 | −0.065 | −12.4 | 0.945 | −2.29 | 2/5 | rejected |
| scalp | BTCUSDT | 1h | 44 (164) | 0.978 | 0.027 | −13.7 | 0.426 | −2.00 | 1/5 | rejected |
| scalp | ETHUSDT | 4h | 36 (38) | 1.534 | 1.180 | −11.8 | 0.949 | −0.71 | 3/5 | rejected |
| scalp | ETHUSDT | 1h | 6 (152) | 0.000 | −2.450 | −12.1 | 1.000 | −3.47 | 0/5 | rejected |
| hft | BTCUSDT | 4h | 39 (39) | 1.712 | 1.602 | −10.3 | 0.410 | −0.33 | 4/5 | rejected |
| hft | BTCUSDT | 1h | 6 (145) | 0.000 | −2.449 | −12.6 | 0.993 | −3.32 | 0/5 | rejected |
| hft | ETHUSDT | 4h | 19 (36) | 0.817 | −0.342 | −12.0 | 0.719 | −2.80 | 1/5 | rejected |
| hft | ETHUSDT | 1h | 41 (140) | 1.005 | 0.117 | −12.7 | 0.559 | −1.99 | 1/5 | rejected |
| breakout | BTCUSDT | 4h | 34 (76) | 0.977 | 0.006 | −12.9 | 0.848 | −2.22 | 1/5 | rejected |
| breakout | BTCUSDT | 1h | 15 (298) | 0.664 | −0.760 | −13.8 | 0.945 | −2.70 | 0/5 | rejected |
| breakout | ETHUSDT | 4h | 33 (85) | 0.830 | −0.477 | −13.8 | 0.890 | −2.48 | 1/5 | rejected |
| breakout | ETHUSDT | 1h | 17 (309) | 0.758 | −0.531 | −12.7 | 0.922 | −2.81 | 0/5 | rejected |
| meanrev | BTCUSDT | 4h | 43 (212) | 1.095 | 0.409 | −13.7 | 0.011 | −1.58 | 1/5 | rejected |
| meanrev | BTCUSDT | 1h | 12 (779) | 0.434 | −1.353 | −12.0 | 0.861 | −3.16 | 0/5 | rejected |
| meanrev | ETHUSDT | 4h | 27 (197) | 0.988 | 0.032 | −13.5 | 0.943 | −1.91 | 0/5 | rejected |
| meanrev | ETHUSDT | 1h | 23 (790) | 0.601 | −1.146 | −13.9 | 0.762 | −3.14 | 0/5 | rejected |

**VALIDATED: 0 — REJECTED: 16.**

## What the comparison says

- **The verdict is unchanged for all sixteen cells: nothing validates, on any engine,
  with or without rails.** The answer "nothing goes to paper" has now survived the
  ported engine, the kernel migration, and the sizing-rails landing. That is the M3
  acceptance line's "honest verdicts" — the empty roster is the correct answer, not a
  pipeline failure.
- **The rails dominate trade counts.** Every losing cell hits ~12–14 % max drawdown and
  then stops trading: the 12 % drawdown kill-switch trips and subsequent entries are
  vetoed. High-frequency cells collapse most (meanrev 1h: 779→12, 790→23 trades;
  scalp ETHUSDT 1h: 152→6). This is the rails doing exactly what design §6 says they
  do — an account that bleeds to the kill-switch stops bleeding. In the pre-rails
  baseline those cells instead ground on to 67–100 % drawdowns.
- **The rails change outcomes, not verdicts.** meanrev BTCUSDT 4h flipped its headline
  from catastrophic (PF 0.70, Sharpe −2.95 pre-rails) to mildly positive (PF 1.10,
  Sharpe 0.41, permutation p 0.011 — the only sub-0.05 cell ever measured) purely by
  having its worst tails cut off. It still fails the bootstrap CI (−1.58 ≤ 0) and
  walk-forward (1/5). Reading: permutation significance on 43 trades with a negative
  CI lower bound is not a strategy; the gate's redundancy is doing its job.
- **hft BTCUSDT 4h remains the nearest miss, by the same shape as before**: PF 1.71,
  Sharpe 1.60, wf 4/5, permutation p 0.41 — random reshufflings of the same trades do
  as well 41 % of the time. No fill model, no rail configuration changes that.
- Rows now fail on *more* independent checks than before (sub-30 trade counts in 9/16
  cells vs 0/16 pre-rails), because kill-switch truncation reduces n. Rejection
  margins widened; nothing moved toward the gate.

## Registration-path demonstration (registry migration evidence)

`research.py register` exercised against validation row 6 (hft BTCUSDT 4h, the best
row of the sweep) in the scratch db:

```json
{
  "registered": true,
  "version_id": 1,
  "bot": "hft-v1",
  "state": "research",
  "roster_size": 0,
  "promotion_refused": "validation row 6 says 'rejected', not 'validated'"
}
```

The registration path itself works end to end — the version lands in the lifecycle
registry in `research` state — and the guard correctly refuses the validated → paper
transition because the verdict is rejected. `roster()` is empty: **the honest-empty
end state is confirmed on kernel-produced rows**, which is exactly what design §M3
(migrated through the gate with honest verdicts) requires. No strategy is eligible
for paper; none pretend to be.

## Reproduction

```bash
cd backend
for bot in scalp hft breakout meanrev; do
  for sym in BTCUSDT ETHUSDT; do
    for tf in 4h 1h; do
      uv run python -m trading.research validate --bot $bot --symbol $sym \
        --timeframe $tf --app-db sqlite:////tmp/kernel-sweep-2026-11-26.db
    done
  done
done
uv run python -m trading.research register --bot hft --validation-id 6 \
  --app-db sqlite:////tmp/kernel-sweep-2026-11-26.db
```

Full sweep runtime: ~30 s wall on this machine (kernel harness, cached candles).
Tests green: `uv run pytest tests_trading/test_research.py -q` → 9 passed.
