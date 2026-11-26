# OpenBB evaluation — time-boxed experiment (M1)

**Date:** 2026-11-26. **Verdict: REJECT** — no demonstrable coverage advantage for what this
system reads. Every data type the system consumes through free OpenBB providers either comes
from the same Yahoo backend we already use (zero coverage gain), is blocked or broken in
practice (Cboe 403s, ECB SSL failure), or does not exist for our universe (no UCITS ETF
holdings, no crypto pairs beyond what Binance already covers, no exotic FX).

The design's adoption bar (docs/design/hedge-fund-os.md line 719): *"adopt only if it
demonstrably covers something we read that yfinance does not."* Nothing measured below clears it.

---

## 1. What the system actually reads (inventory from code, not memory)

Established from `backend/app/` and the live databases (read-only copies; `backend/data/*`
never opened for write):

| Data type | Symbols / scope | Source today | Evidence |
|---|---|---|---|
| Daily closes (latest + dated windows) | **User-typed open universe** — any Yahoo symbol: UCITS ETFs, international equities, crypto pairs. Concrete instances: BTC-USD, XAUT-USD (production `holdings`/`price_cache`), EUNL.DE, IS3N.DE, SAP.DE (demo portfolio), AAPL/MSFT (reachability canaries), SPY/QQQ (M1 acceptance backfill) | yfinance `history()` | `backend/app/prices.py` |
| Dividends **with currency** | every held listing | yfinance `get_dividends` (the only call that keeps the currency) | `prices.py:509-516`, `test_every_dividend_in_its_own_currency.py` |
| FX daily closes for currencies the ECB does not publish | `USD{code}=X` pairs, e.g. VND, PKR, BOB | yfinance via `prices._fetch_close_window` | `yahoo_rates.py` |
| ECB FX rates | EUR×30+ currencies | ECB feed direct (not Yahoo) | `fx.py` — 841 rows in `fx_rates` |
| ETF composition (countries/sectors/holdings) | issuer files → justETF → trackinsight → yfinance `funds_data` (last resort, degraded: no geography) | 4-source waterfall, all free | `composition.py:1-26` |
| Instrument search + names | open universe | Yahoo lookup (`yfinance.Lookup`) | `tools.py:516` |
| Crypto intraday candles (1m–4h) | BTCUSDT, ETHUSDT (21,904 rows in research.db: 1h/4h) | **Binance** (`binance_history.py`) — explicitly not an OpenBB question | `backend/data/research.db` |

**What the system does NOT read:** no fundamentals (income/balance/earnings), no macro series
(GDP/CPI/FRED), no options chains. Grep of `backend/app/*.py` and `backend/trading/*.py`:
zero ingestion of any of these. The design places macro/fundamentals in §3.3 as OpenBB's
*potential* layer but M1 explicitly scopes it out: *"Out of scope: realtime streaming to the
UI, macro/fundamentals beyond the experiment."* The experiment itself is the only mandate to
look, and the bar is coverage of what we read.

## 2. yfinance coverage of the exact universe — measured 2026-11-26

Script `/tmp/yf_coverage_test.py`, backend venv, yfinance 1.7.0. Result: **15/15 symbols
resolve, 3/3 exotic FX pairs resolve, zero coverage failures.**

| Symbol | Close | Dated window | Dividends | Name/currency | funds_data |
|---|---|---|---|---|---|
| BTC-USD, XAUT-USD, BTC-EUR | ✅ today (24/7 markets) | ✅ 14/14 rows | n/a (0) | ✅ | raises "No Fund data" — correct, they are not funds |
| EUNL.DE, IS3N.DE, VWCE.MI, CSPX.L | ✅ (latest closed session) | ✅ 10 rows | 0 (accumulating UCITS — correct) | ✅ full names | ✅ 11 sectors + top-10 holdings |
| SAP.DE, ENI.MI, ASML.AS | ✅ | ✅ | ✅ 28/57/– dividends | ✅ | raises — correct for equities |
| AAPL, MSFT, SPY, QQQ, VOO | ✅ | ✅ | ✅ 93/92/136/90/64 | ✅ | ✅ ETFs 11 sectors + top-10 |
| USDVND=X, USDPKR=X, USDBOB=X | ✅ 4 rows each | — | — | — | — |

The one systematic artifact — `nan_close_rows: 1` on the most recent row for exchange-hours
instruments — is **not a coverage gap**: it is the in-progress session's row, and the app's
`keepna=True` + close-waiting discipline (`prices._close_on`, defended by 123 tests) exists
precisely for it. yfinance 1.7.0's float-typed columns already fixed the 1.4.1 None-object trap.

Empty-row traps documented in `how-aurelio-reasons.md` are Yahoo data behaviors; no client
library changes what Yahoo publishes.

## 3. OpenBB measured (scratch venv `/tmp/openbb-venv`, never touched the backend venv)

### Dependency cost — itself a finding

- `uv pip install openbb` → **openbb 5.0.0, 219 packages, 719 MB** installed in 17.6 s.
  Adding the routers needed for prices (`openbb-yfinance openbb-equity openbb-etf
  openbb-currency`) → **780 MB**. For comparison the entire backend venv carries this whole
  application in a fraction of that.
- First `from openbb import obb` after any extension change: **27.7 s** (it rebuilds the
  generated package in-process); subsequent imports in a fresh process still pay extension
  discovery (~9-10 s measured across probes). Every wealth-plane revaluation process would
  carry this or need a warm daemon.
- The metapackage drags in the CLI, the FastAPI REST server, the MCP server, **devtools
  (linters, pytest plugins)**, charting, and jupyter-adjacent packages (ipykernel, nbformat)
  — nothing a data-plane loader needs.
- pandas constraint is loose (`>=1.5.3`); no hard conflict with backend pandas 3.0.3, but
  OpenBB pinned pandas 3.1.1 in its own resolve — a second pandas version line in one venv
  is a testing burden even when it resolves.

### Coverage: does it cover anything yfinance failed on?

Nothing failed under yfinance (§2), so the question reduces to: could OpenBB cover the two
**known degraded areas** — and does it add any data type with a concrete need?

**a) Keyless free price providers — measured broken or absent for our universe:**

| Provider | Result 2026-11-26 |
|---|---|
| Cboe equity historical | **403 from cdn-api.cboe.com for every symbol** (SPY, AAPL included — HTML block page, not JSON). Non-functional as installed. |
| Nasdaq equity historical | AAPL ✅ but **SPY → EmptyDataError** ("No historical prices"); SAP.DE, EUNL.DE → EmptyDataError. US equities only, and even there ETFs absent. |
| ECB exchange_rates | **SSLCertVerificationError to data-api.ecb.europa.eu** as installed; and irrelevant — the app reads the ECB feed directly already, with exotic-currency coverage the ECB never publishes. |
| TMX | Canadian listings; `Results not found` for every test symbol. |

**b) `obb.equity.price.historical(provider="yfinance")` does work for every symbol** —
because it *is* yfinance (openbb-yfinance 2.1.0 wraps yfinance 1.8.0). Same Yahoo backend,
same data, strictly an added abstraction layer over what we already call directly. Coverage
gain: zero.

**c) ETF holdings — the one real degradation in our system** (yfinance fallback has no
country geography): `obb.etf.holdings` accepts only providers `nasdaq` or `tmx`. Measured:
**EUNL.DE and VWCE.MI → "Symbol not exists"; even SPY/nasdaq → EmptyDataError.** The free
tier of ETF composition in OpenBB does not cover UCITS at all and failed on the US flagship
ETF. OpenBB does not even match the waterfall we already run (issuer files → justETF →
trackinsight), which covers UCITS with countries through three sources before Yahoo is ever
asked.

**d) Dividends**: `obb.equity.fundamental.dividends(SAP.DE, provider="yfinance")` returns
`(ex_dividend_date, amount)` — **the currency is dropped**, the exact data the app reads
`get_dividends` for and the reason `prices.py:509-516` documents the choice. OpenBB's
normalized schema is a *regression* for this read.

**e) Macro/fundamentals**: keyless macro exists (FRED with free key, IMF, OECD, Fed,
Treasury, BLS) and is genuinely OpenBB-shaped value — but nothing in the system reads it,
M1 declares it out of scope, and the adoption bar is coverage of what we read. File under:
*revisit if the design adds a macro reader.*

### OpenBB versions note

`openbb` 5.0.0 (Nov 2026 line) installs a different shape than v4 documentation describes:
the metapackage bundles US-government-heavy providers but **no equity/etf/currency routers
and no yfinance provider** — those are separate installs. The `obb.equity` surface most
examples show requires explicitly adding `openbb-equity openbb-yfinance` (+60 MB here).
Documentation drift of this size in the project's own README is an integration-cost signal.

## 4. Verdict

**REJECT adoption.** Evidence summary:

1. yfinance covers 100% of the concrete universe today (15/15 symbols, 3/3 exotic FX).
   There is no failure for OpenBB to cover.
2. OpenBB's keyless non-Yahoo price providers are broken (Cboe 403), US-only-and-partial
   (Nasdaq: no ETFs!), or redundant (ECB — already read directly).
3. The one degraded read in the system — UCITS ETF composition — is **not covered** by
   OpenBB's free tier at all; even US ETF holdings came back empty.
4. Where OpenBB does cover our universe (`provider="yfinance"`), it is the same Yahoo
   backend we already call — pure indirection — and its normalized schemas **lose data we
   need** (dividend currency).
5. Cost: ~780 MB, 220+ packages, 10-28 s import/build penalty, devtools/CLI/MCP server in
   the dependency tree, plus Yahoo remains a dependency underneath it all — so nothing is
   even removed by adopting.

**Trigger to re-evaluate** (write it into M1's notes): the day the design adds a macro or
fundamentals reader, `openbb` becomes the obvious candidate layer — its keyless IMF/OECD/
Fed/Treasury/SEC providers are real. Equally, if Yahoo ever degrades coverage of UCITS or
exotic FX, re-run this experiment against the concrete failing symbols. Until then the bars
store in M1 should be built as designed — loader registry with fallback chains — with
yfinance and Binance as the first loaders, and OpenBB left out.

## 5. Experiment hygiene

- All OpenBB work in `/tmp/openbb-venv` (scratch); the backend venv was never installed into:
  `uv pip list | grep openbb` → 0 packages. Nothing to uninstall.
- `uv run pytest tests_trading/test_kernel.py -q` → **7 passed** after the experiment.
- `backend/data/*` accessed only read-only through SQLite backup copies in /tmp.
- Test scripts: `/tmp/yf_coverage_test.py`; database copies `/tmp/hedgefund_copy.db`,
  `/tmp/research_copy.db`.
