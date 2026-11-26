# Trading agents — the integration architecture, measured against what exists

Date: 2026-11-26. Status: proposal — written the evening the user redirected
toward existing quant tooling, AFTER the data plane, the alpha zoo and the
ML forecaster were already integrated and measured. Nothing here is built.

## What the integration scan found, verbatim

| Tool | License | What it is | What we took |
|---|---|---|---|
| Vibe-Trading factor zoo | MIT | ~290 implemented formulaic alphas (Kakushadze 101, GTJA 191) with metadata, benchmarked on CSI 300 — 8 alive, 15 reversed there | vendored whole into `trading/factors/` + the rank-IC bench measuring them on OUR universes |
| yfinance | Apache-2.0 | Yahoo market data | the multi-asset data plane: 14.5y daily + 2y hourly on SPY/QQQ/IWM/DIA/GLD/SLV, merged |
| statsmodels/scikit-learn | BSD | regression/ML | F9 gradient-boosted forecaster, embargoed walk-forward, OOF corr +0.042 measured before sweeping |
| Freqtrade/Jesse/vectorbt | GPL/Apache/various | full trading frameworks | **rejected**: each replaces the kernel rather than feeding it — the kernel's paper/backtest parity and ledger honesty are the program's one non-negotiable |
| Vibe-Trading agent harness | MIT | a research ecosystem: skills, memory, strategy store | too large to port; its IDEAS are portable (see below) |

## The one design sentence

**Agents propose, the machinery disposes.** An agent's only output is a
declared family — mechanism hypothesis, parameter grid, budget — written
into the program document before the first sweep runs. Everything after
that sentence is the machinery the program already has: kernel validation,
the ledger, permutation tests, out-of-sample gates. No agent ever touches
an order, a key, or a verdict.

This is not caution theater. It is the only architecture in which agent
output can be trusted AT ALL: an LLM that can both propose a strategy and
influence its own evaluation is a selection-bias machine, and selection
bias is exactly what the program exists to destroy.

## The loop

```
ledger + verdicts  ──┐
                     ├─> researcher agent reads, proposes F-family N+1
program document <───┘   (hypothesis, grid, budget — in writing, BEFORE)
                     │
                human/policy gate (cheap: is the grid countable,
                     is the hypothesis falsifiable, is the budget sane)
                     │
                sweep machinery measures, ledger records everything
                     │
                verdict written — loop closes
```

The first three agents, in order of value per hour:

1. **The researcher** — reads ledger + verdicts + research notes, drafts
   family declarations. Input is fully local; output is text reviewable in
   one minute. This is 80% of the value at 5% of the cost.
2. **The auditor** — adversarial pass over every verdict: reruns the
   winner's cell on a virgin slice, checks the accounting (the dev_z bug
   this week was found by exactly this instinct, applied by hand).
3. **The data scout** — watches the ingest planes for gaps, staleness and
   coverage holes; proposes backfills. No opinions about strategies.

What is deliberately NOT here: LLM-in-the-loop trading, news-sentiment
entries, agent-position sizing. Each is a family hypothesis like any other
and enters through the same declaration path if someone writes it down.

## Where the alpha zoo fits

The zoo is not a strategy library — it is a SIGNAL library. The bench
running tonight measures every alpha's rank IC on our universes; survivors
become F10+ families through the normal declaration path, with the alpha
as the entry signal and the kernel's stop/target machinery managing the
trade. A validated alpha is a measurement, not a mandate.

## What this costs

One researcher run is a single LLM call over ~20k tokens of ledger +
verdicts. The honest comparison: the program's day 1 measured seven
families by hand. The agent layer's promise is not more families — it is
never skipping the boring parts (declarations, budgets, verdict updates)
because a human got tired.
