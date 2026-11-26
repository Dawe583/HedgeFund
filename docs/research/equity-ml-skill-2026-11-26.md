# Equity ML skill map — the honest answer to "can we predict stock prices"

Date: 2026-11-26 late night. Method: the F9 forecaster's leakage-first
screen — embargoed walk-forward out-of-fold correlation between predicted
and realized 6-hour forward returns, per symbol, in-sample window only.
No sweeps ran and none are implied; this is the measurement that decides
whether a sweep is worth declaring at all.

## The measured map (17 symbols, 3110 hourly rows each)

| symbol | OOF corr | reading |
|---|---|---|
| GLD | +0.083 | strongest — gold remains the least efficient tape here |
| AAPL | +0.058 | real but small |
| NFLX | +0.039 | real but small |
| XLE | +0.038 | real but small |
| SLV | +0.027 | weak |
| SPY | +0.025 | weak |
| NVDA | +0.019 | noise-adjacent |
| QQQ | +0.017 | noise-adjacent |
| MSFT | -0.063 | negative — model anti-predicts |
| IWM | -0.059 | negative |
| AMD | -0.038 | negative |
| JPM | -0.024 | negative |

For scale: BTCUSDT measures +0.042 on the same instrument. The ordering is
the same one the alpha bench found independently — gold and crypto carry
more exploitable structure than large-cap equities, and mega-cap tech is
close to efficiently random at the hourly horizon.

## What this means, stated plainly

Stock price prediction with these features is possible in the statistical
sense — correlations are real, embargoed, out-of-fold — and useless in the
economic sense at this magnitude: a +0.02 correlation does not survive
spread, fees and the regime decay that killed F9 in crypto. The honest
answer to the user's question is: yes, the machinery predicts, the CLI
prints it, and the measurement says how much to trust it — which for most
large caps is "barely". GLD, AAPL and NFLX are the only equity names where
a future family declaration would not start from a null prior.
