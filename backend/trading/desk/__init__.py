"""The kernel paper desk — M3 slice 1.

A TradingNode whose execution venue is the kernel's own sandbox (the same
SimulatedExchange the backtest uses) and whose strategies are the same
harness-wrapped classes `trading.kernel` runs in backtests. Parity is
structural: one strategy implementation, one matching engine, one economics
reconstruction — the only difference is where bars come from (a replayed or
live feed instead of a dataframe).
"""
