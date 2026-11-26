# Program verdict — day 2: the integration day

Date: 2026-11-26 late night. The day the user's redirect landed: stop
building, integrate what exists. Four integrations shipped and measured,
three families declared and closed, one architecture documented.

## Integrations, each measured on our tape

| Integration | What it is | Verdict |
|---|---|---|
| Yahoo data plane | 24 equities + indexes + metals: 14.5y daily, 2y hourly | **kept** — the data plane under everything below |
| Alpha zoo (Vibe, MIT) | ~290 formulaic alphas + bench machinery | **kept as feature library** — as entry signals: dead (below) |
| sklearn ML forecaster | embargoed walk-forward, artifact cache, predict CLI | **kept as machinery** — as a strategy: dead (below) |
| Researcher agent | reads ledger/verdicts, drafts family declarations | **ready, unpowered** — owner chose manual declarations; agent waits for an OpenRouter key |

## Families closed

- **F9 ML forecaster**: genuine in-sample skill (random-entries null
  p = 0.0, the strongest entry-quality measurement the program has),
  dead out-of-sample (+0.1 Sharpe). Overfit-or-decay, honestly measured
  end to end. Full verdict in f9-ledger-2026-11-26.md.
- **F10 alpha-per-symbol**: 0/20, mean Sharpe -0.23 — the control that
  proved cross-sectional ranks do not project into time series.
- **F11 alpha basket**: in-sample edge real (gtja191_093 Sharpe +1.26,
  wf 3/5), out-of-sample collapse (-2.4). The alpha directional program
  is closed; the zoo remains as a FEATURE library for future ML.

## Measurements that outlive the families

1. **Market efficiency ordering**, measured three independent ways in one
   day: large-cap US equities are information-thinnest (alpha IC a quarter
   of crypto's, ML skill +0.02), crypto majors intermediate (BTC +0.042),
   gold strongest (GLD +0.083). Same ordering in the alpha bench and the
   ML screen — the instruments agree, which is what instruments are for.
2. **Regime decay is the program's one unresolved question.** F7, F9, F11
   all died at exactly the in-sample/out-of-sample boundary. Nothing else
   explains three independent families failing at the same wall.
3. **The random-entries null is now the decisive instrument** wherever the
   permutation test reads insensitive — it caught what the permutation
   could not, twice.

## Day 3 candidates, in honest order

1. **F12 regime-conditional ML** — rolling retraining; the only hypothesis
   directly motivated by three measured deaths. Declare before sweeping.
2. Alpha-zoo features INTO the ML frame — the zoo's second life, cheap
   because both halves already exist.
3. Agent power-up — one OpenRouter key and the researcher starts drafting;
   the architecture is already written.
