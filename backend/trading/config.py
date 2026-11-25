from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_DIR = _REPO_ROOT / "backend"
_DEFAULT_DB = _BACKEND_DIR / "data.db"


class Settings(BaseSettings):
    """Central configuration. All secrets come from env — nothing hard-coded."""

    app_name: str = "Trading"
    debug: bool = True

    # Storage: the engine shares the platform SQLite database (design D3).
    database_url: str = f"sqlite:///{_DEFAULT_DB}"
    data_dir: str = str(_BACKEND_DIR / "data")  # scratch dir for budget counters, worker lock, etc.

    # Market data venues (public endpoints — no keys needed for data)
    binance_rest: str = "https://api2.binance.com"
    binance_ws: str = "wss://stream.binance.com:9443/ws"
    hyperliquid_rest: str = "https://api.hyperliquid.xyz"

    # Paper account
    paper_equity_start: float = 1_000.0
    default_leverage: float = 5.0  # perp margin math: margin = notional / leverage

    # Risk rails (hard limits) — turbo-tuned: more trades, wider rails.
    # Paper money: daily loss 5%, kill-switch 12% DD, 2% risk/trade,
    # up to 60% equity per position, full Kelly.
    risk_max_daily_loss_pct: float = 0.05
    risk_killswitch_dd_pct: float = 0.12
    risk_per_trade_risk_pct: float = 0.02
    risk_max_exposure_pct: float = 0.60
    kelly_fraction_cap: float = 1.0

    # Turbo execution: dynamic leverage + multi-position
    leverage_min: float = 2.0
    leverage_max: float = 25.0
    max_positions_per_bot: int = 3
    max_total_positions: int = 8
    confidence_min_hft: float = 0.45
    confidence_min_scalp: float = 0.52
    target_trades_per_day: int = 5
    trailing_stop_atr_mult: float = 1.0  # move SL to breakeven+ when profit exceeds this × ATR
    time_stop_bars: int = 60  # force-close HFT positions after N bars without TP
    turbo_mode: bool = True  # master switch: loose gates + aggressive sizing

    # AI agents (OpenRouter) — free-tier models only, zero token cost.
    # agent_model is tried first; agent_model_fallbacks (comma-separated) are
    # handed to OpenRouter's routing so a rate-limited or down free model
    # transparently rolls over to the next one instead of dropping the call.
    openrouter_api_key: str | None = None
    agent_model: str = "nvidia/nemotron-3-super-120b-a12b:free"
    agent_model_fallbacks: str = "z-ai/glm-5.2:free,dots-studio/dots-3-note-preview:free"

    # Free-tier request budget. OpenRouter caps free models per ACCOUNT at
    # 20 req/min and 50/day (until $10 of credit has ever been bought; then
    # 1000/day) — no model choice changes that, so the desk rations requests
    # and falls back to heuristics rather than earning a 429 mid-trade.
    agent_daily_budget: int = 45  # margin under the 50/day free-tier ceiling
    agent_rpm_budget: int = 15  # margin under the 20/min ceiling
    agent_timeout_s: float = 30.0
    agents_enabled: bool = True
    analyst_interval_s: int = 300  # market analyst cadence
    engine_token: str | None = None  # bearer auth for /api/agents/tick (cron)
    cors_origins: str = ""  # comma-separated extra origins (Vercel domain)
    ml_gate_threshold: float = 0.55  # champion-model entry gate

    # Execution model for paper fills
    taker_fee_pct: float = 0.045
    maker_fee_pct: float = 0.015
    slippage_bps: float = 2.0

    # Hyperliquid live trading (agent wallet — trades, never withdraws)
    hl_private_key: str | None = None  # AGENT wallet key, never the main wallet key
    hl_account: str | None = None  # main wallet address (0x…)
    hl_testnet: bool = True  # testnet sandbox first — always
    live_trading: bool = False  # HARD GATE: no live order until explicitly true
    hl_max_order_usd: float = 25.0  # small-capital guardrail per order
    hl_max_exposure_usd: float = 100.0  # total open notional cap

    # Root .env first (repo checkout), optional cwd .env as override —
    # makes TRADING_* vars work regardless of where the engine is launched.
    model_config = {"env_file": [_REPO_ROOT / ".env", ".env"], "env_prefix": "TRADING_"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
