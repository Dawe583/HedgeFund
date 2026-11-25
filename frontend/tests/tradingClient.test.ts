/* The trading API client against its contract — the canonical backend shapes
   of backend/app/routers/trading.py, verbatim.

   The transport is mocked at the axios adapter — the one seam axios itself
   offers — so what these tests pin is the client's side of the bargain: the
   exact paths it calls (relative, because the proxy and the same-origin
   production deployment are the whole point of api/client.ts) and the payload
   passing through UNALTERED. There is no mapping layer: the backend's shapes
   are canonical and the client is a transcription, so a test that finds the
   client transforming anything is a bug report, not a test failure to fix by
   editing the expectation. */

import assert from "node:assert/strict";
import { test } from "node:test";
import type { InternalAxiosRequestConfig } from "axios";
import { api } from "../src/api/client.ts";
import {
  getBacktestRun,
  getBacktestRuns,
  getTradingStatus,
  getTradingStrategies,
} from "../src/api/trading.ts";

type Handler = (config: InternalAxiosRequestConfig) => unknown;

/** Answer every request through the handler, returning `{data}` as axios
    would. Returns the list of paths actually called. */
function mockAdapter(handler: Handler): string[] {
  const called: string[] = [];
  const adapter = async (config: InternalAxiosRequestConfig) => {
    called.push(config.url ?? "");
    return {
      data: handler(config),
      status: 200,
      statusText: "OK",
      headers: {},
      config,
    };
  };
  api.defaults.adapter = adapter;
  return called;
}

const STATUS = {
  engine_state: "offline",
  last_tick_at: null,
  db_ok: true,
  strategies_registered: 0,
  validations_total: 0,
};

test("the status endpoint is the contract's path, and the payload passes through unaltered", async () => {
  const called = mockAdapter(() => STATUS);
  const got = await getTradingStatus();
  assert.deepEqual(called, ["/api/trading/status"]);
  assert.deepEqual(got, STATUS);
});

test("the strategies endpoint maps to /api/trading/strategies", async () => {
  const strategies = [
    {
      key: "scalp",
      name: "ScalpTrend",
      timeframe: "4h",
      symbols: ["BTCUSDT"],
      description: "Higher-timeframe trend strategy.",
      registered: false,
    },
  ];
  const called = mockAdapter(() => strategies);
  const got = await getTradingStrategies();
  assert.deepEqual(called, ["/api/trading/strategies"]);
  assert.deepEqual(got, strategies);
});

test("runs pass through unaltered: lowercase verdict, null validation, the metrics bag as given", async () => {
  const runs = [
    {
      id: 7,
      bot: "scalp",
      symbol: "BTCUSDT",
      timeframe: "4h",
      started_at: "2026-11-20T08:00:00",
      trades_count: 42,
      metrics: {
        win_rate: 0.41,
        profit_factor: 1.3,
        sharpe: 1.4,
        max_dd_pct: -12.1,
        total_return_pct: 8.5,
      },
      verdict: null,
      validation: null,
      created_at: "2026-11-20T08:00:00",
    },
    {
      id: 9,
      bot: "scalp",
      symbol: "BTCUSDT",
      timeframe: "4h",
      started_at: "2026-11-24T08:00:00",
      trades_count: 51,
      metrics: {
        win_rate: 0.55,
        profit_factor: 1.9,
        sharpe: 1.9,
        max_dd_pct: -8.2,
        total_return_pct: 14.1,
      },
      verdict: "validated",
      validation: {
        permutation_p: 0.01,
        sharpe_ci_lo: 0.42,
        sharpe_ci_hi: 1.87,
        wf_positive_folds: 3,
        wf_total_folds: 4,
      },
      created_at: "2026-11-24T08:00:00",
    },
  ];
  const called = mockAdapter(() => runs);
  const got = await getBacktestRuns();
  assert.deepEqual(called, ["/api/trading/backtest-runs"]);
  assert.deepEqual(got, runs);
  assert.equal(got[0].verdict, null);
  assert.equal(got[1].verdict, "validated");
});

test("the detail endpoint interpolates the run id; nested provenance, reasons and gate statistics pass through unaltered", async () => {
  const detail = {
    id: 1,
    bot: "scalp",
    symbol: "BTCUSDT",
    timeframe: "4h",
    started_at: "2026-11-25T01:17:54",
    trades_count: 17,
    metrics: {
      win_rate: 0.1765,
      profit_factor: 0.366,
      sharpe: -2.41,
      max_dd_pct: -21.115,
      total_return_pct: -16.522,
    },
    verdict: "rejected",
    validation: {
      permutation_p: 0.05,
      sharpe_ci_lo: -5.702,
      sharpe_ci_hi: 0.3793,
      wf_positive_folds: 1,
      wf_total_folds: 5,
    },
    created_at: "2026-11-25T01:17:54",
    params: { regime_min: 1.5, rsi_long_max: 70.0, stop_atr: 2.2, tp_rr: 2.0 },
    provenance: {
      seed: 42,
      data_source: "binance",
      data_rows: 1080,
      data_start: "2026-05-29 04:00:00",
      data_end: "2026-11-25 00:00:00",
    },
    reasons: ["trades 17 < minimum 30", "bootstrap Sharpe CI lower -5.702 <= 0"],
    prob_positive: 0.049,
    sharpe_actual: -21.0358,
    min_trades_required: 30,
  };
  const called = mockAdapter(() => detail);
  const got = await getBacktestRun(1);
  assert.deepEqual(called, ["/api/trading/backtest-runs/1"]);
  assert.deepEqual(got, detail);
  assert.equal(got.verdict, "rejected");
  assert.equal(got.provenance?.seed, 42);
  assert.equal(got.reasons.length, 2);
  assert.equal(got.prob_positive, 0.049);
});

test("a run the gate never ran carries no verdict and no provenance — nulls, not inventions", async () => {
  const detail = {
    id: 3,
    bot: "hft",
    symbol: "BTCUSDT",
    timeframe: "1m",
    started_at: "2026-11-25T01:00:00",
    trades_count: 0,
    metrics: {
      win_rate: 0,
      profit_factor: 0,
      sharpe: 0,
      max_dd_pct: 0,
      total_return_pct: 0,
    },
    verdict: null,
    validation: null,
    created_at: "2026-11-25T01:00:00",
    params: {},
    provenance: null,
    reasons: [],
  };
  mockAdapter(() => detail);
  const got = await getBacktestRun(3);
  assert.equal(got.verdict, null);
  assert.equal(got.provenance, null);
  assert.deepEqual(got.reasons, []);
  assert.equal(got.metrics.sharpe, 0);
});
