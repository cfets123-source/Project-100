"""
Centralized configuration. ALL risk parameters live here.
Any change to a risk-affecting field must be logged by the caller via audit.log_config_change().
"""
from enum import Enum
from pydantic_settings import BaseSettings
from pydantic import Field, model_validator


class ConfigConsistencyError(ValueError):
    """Raised when TRADING_MODE / AUTONOMY_LEVEL / AUTO_EXECUTION form an unsafe
    or contradictory combination. Fails startup rather than silently picking
    a behavior."""


class TradingMode(str, Enum):
    PAPER = "paper"
    SHADOW = "shadow"
    LIVE = "live"


class AutonomyLevel(int, Enum):
    LEVEL_0_RESEARCH_ONLY = 0
    LEVEL_1_CANDIDATES_ONLY = 1
    LEVEL_2_PAPER_AUTO = 2
    LEVEL_3_LIVE_NEEDS_APPROVAL = 3
    LEVEL_4_LIVE_AUTONOMOUS = 4
    LEVEL_5_LIVE_AUTONOMOUS_EXPANDED = 5


class SystemState(str, Enum):
    OFF = "off"
    RESEARCH = "research"
    PAPER = "paper"
    SHADOW = "shadow"
    LIVE = "live"
    SAFE = "safe"
    HALTED = "halted"


class Settings(BaseSettings):
    # --- Core ---
    APP_ENV: str = "development"
    DATABASE_URL: str = "sqlite:///./project100.db"  # Postgres in prod, sqlite for local/test
    # Deployment scopes identify one broker/account/mode. Legacy local databases
    # retain 'current'; deployed workers must use separate explicit scopes.
    STATE_SCOPE: str = Field(default="current", min_length=1)
    ALPACA_LIVE_STATE_SCOPE: str = "alpaca:live"
    LIVE_POSITION_MANAGEMENT_ENABLED: bool = False
    SECRET_KEY: str = Field(default="dev-only-change-me")

    # --- Trading mode / autonomy (defaults are the SAFE defaults) ---
    TRADING_MODE: TradingMode = TradingMode.PAPER
    AUTONOMY_LEVEL: AutonomyLevel = AutonomyLevel.LEVEL_0_RESEARCH_ONLY
    AUTO_EXECUTION: bool = False
    # A separate, default-off gate for an external broker's simulated account.
    # It is never equivalent to LIVE_TRADING_ENABLED.
    ALPACA_PAPER_EXECUTION_ENABLED: bool = False
    # Broker-specific live gates. Building a transport never enables a worker.
    ROBINHOOD_EQUITY_EXECUTION_ENABLED: bool = False
    ROBINHOOD_CRYPTO_EXECUTION_ENABLED: bool = False
    ROBINHOOD_OPTIONS_EXECUTION_ENABLED: bool = False

    # --- Capital ---
    STARTING_CAPITAL: float = 100.0
    FIRST_MILESTONE: float = Field(default=200.0, ge=200.0, le=500.0)

    # --- Risk Engine defaults (per spec) ---
    MAX_RISK_PER_TRADE: float = 0.01          # 1% of equity
    MAX_DAILY_LOSS: float = 0.03              # 3% -> halt new trades for session
    MAX_WEEKLY_DRAWDOWN: float = 0.06         # 6% -> disable live trading, require review
    MAX_TOTAL_DRAWDOWN: float = 0.12          # 12% -> automatic shutdown (10-15% band)
    MAX_POSITIONS: int = 2
    MAX_POSITION_PCT: float = 0.50            # max % of equity in one position
    MAX_SECTOR_CONCENTRATION: float = 0.60

    # --- Hard prohibitions (must stay False until explicit future gate) ---
    ALLOW_MARGIN: bool = False
    ALLOW_OPTIONS: bool = False
    ALLOW_SHORTS: bool = False
    ALLOW_LEVERAGE: bool = False

    # --- Liquidity floors ---
    MIN_AVG_DOLLAR_VOLUME: float = 1_000_000.0
    MAX_SPREAD_PCT: float = 0.01              # reject if bid-ask spread > 1% of mid
    MIN_PRICE: float = 1.0

    # --- Data freshness ---
    MAX_QUOTE_AGE_SECONDS: int = 5

    # --- Hard kill switch on real-money execution, independent of AUTONOMY_LEVEL ---
    # Must remain False for the entirety of this development task. Flipping this
    # requires an explicit, separate, out-of-band change — never set via strategy
    # code, AI output, or milestone logic.
    LIVE_TRADING_ENABLED: bool = False

    # --- Broker OAuth: deployment-only. Keep empty in local development. ---
    BROKER_OAUTH_REDIRECT_URL: str = ""
    BROKER_TOKEN_ENCRYPTION_KEY: str = ""
    DASHBOARD_USERNAME: str = "operator"
    DASHBOARD_PASSWORD: str = ""

    class Config:
        env_file = ".env"

    @model_validator(mode="after")
    def _reconcile_authorization_policy(self) -> "Settings":
        """Single source of truth reconciling mode/level/execution-flag. Any
        combination not explicitly whitelisted is rejected at startup."""
        mode, level, auto = self.TRADING_MODE, self.AUTONOMY_LEVEL, self.AUTO_EXECUTION

        if mode in (TradingMode.PAPER, TradingMode.SHADOW) and level >= AutonomyLevel.LEVEL_3_LIVE_NEEDS_APPROVAL:
            raise ConfigConsistencyError(
                f"TRADING_MODE={mode} cannot be combined with AUTONOMY_LEVEL={level} "
                "(live-order autonomy levels require TRADING_MODE=live)"
            )

        if mode == TradingMode.LIVE and level < AutonomyLevel.LEVEL_3_LIVE_NEEDS_APPROVAL:
            raise ConfigConsistencyError(
                f"TRADING_MODE=live requires AUTONOMY_LEVEL>=3 (got {level})"
            )

        if auto and mode == TradingMode.LIVE and level == AutonomyLevel.LEVEL_3_LIVE_NEEDS_APPROVAL:
            raise ConfigConsistencyError(
                "AUTO_EXECUTION=true is incompatible with AUTONOMY_LEVEL_3 "
                "(LEVEL_3 is human-approval-required by definition)"
            )

        if auto and mode == TradingMode.LIVE and level < AutonomyLevel.LEVEL_4_LIVE_AUTONOMOUS:
            raise ConfigConsistencyError(
                "AUTO_EXECUTION=true with TRADING_MODE=live requires AUTONOMY_LEVEL>=4"
            )

        if mode != TradingMode.LIVE and (self.ALLOW_MARGIN or self.ALLOW_OPTIONS or
                                          self.ALLOW_SHORTS or self.ALLOW_LEVERAGE):
            # Not unsafe by itself (paper can simulate anything), but flagged so it is
            # never mistaken for a live-safe default. Left as a no-op guard point for
            # future stricter policy; explicit ALLOW_* still all default False.
            pass

        if self.APP_ENV.lower() in {"production", "prod"} and not self.DASHBOARD_PASSWORD:
            raise ConfigConsistencyError("DASHBOARD_PASSWORD is required when APP_ENV is production")

        return self


settings = Settings()
