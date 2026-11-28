"""Statistical validation spine — vendored from Vibe-Trading (MIT, see LICENSE).

monte_carlo_test answers "is this ordering of trades luck", bootstrap_sharpe_ci
answers "how stable is the risk-adjusted return", walk_forward_analysis answers
"is performance consistent across time windows".
"""

from trading.validation.validation import (
    bootstrap_sharpe_ci,
    monte_carlo_test,
    run_validation,
    walk_forward_analysis,
)

__all__ = [
    "bootstrap_sharpe_ci",
    "monte_carlo_test",
    "run_validation",
    "walk_forward_analysis",
]


def __getattr__(name):
    # synthetic_path_mc is importable from the package but loaded lazily:
    # it pulls the kernel in transitively, and validation/__init__ is on the
    # import path of code that must stay kernel-free (the ledger writer).
    if name in ("synthetic_path_mc", "make_synthetic_ohlcv", "stationary_bootstrap_indices"):
        from trading.validation import synthetic_paths
        return getattr(synthetic_paths, name)
    raise AttributeError(name)
