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
