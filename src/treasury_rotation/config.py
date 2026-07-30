"""Contract-locked research inputs and explicit data-integrity guardrails."""

from __future__ import annotations

# These research choices are frozen before strategy results are viewed. Changing
# them later would require a documented contract revision rather than an
# informal code tweak.
CONTRACT_VERSION = "0.2.3"

TICKERS = ("SHY", "IEF", "TLT")
DATA_START = "2003-01-01"
DATA_END_EXCLUSIVE = "2026-01-01"

DEVELOPMENT_END = "2015-12-31"
VALIDATION_START = "2016-01-01"
VALIDATION_END = "2020-12-31"
TEST_START = "2021-01-01"
TEST_END = "2025-12-31"

LOOKBACK_TRADING_DAYS = 63
RISK_ADJUSTED_VOLATILITY_DAYS = 21
PRIMARY_COST_BPS = 10
SENSITIVITY_COSTS_BPS = (5, 20)

# These are fail-closed data-quality gates, not strategy parameters to optimize.
# Fractions use decimal units: 0.005 means 0.5%, and 0.20 means 20%. A breach
# raises an error for investigation; the pipeline never clips a market move or
# fills in a price merely to make the dataset pass.
MIN_COMMON_ROWS = 5_500
MAX_MISSING_FRACTION = 0.005
MAX_ABSOLUTE_DAILY_RETURN = 0.20
LATEST_ACCEPTABLE_FIRST_DATE = "2003-01-10"
EARLIEST_ACCEPTABLE_LAST_DATE = "2025-12-20"
