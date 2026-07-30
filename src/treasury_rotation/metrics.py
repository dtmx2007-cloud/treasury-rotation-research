"""Frozen performance metrics defined by research contract v0.2.3.

Every metric uses the single 252-trading-day year convention, and every
metric is computed on net-of-cost quantities produced by the portfolio
engine. This module rejects the locked 2021-2025 test period exactly as the
portfolio engine does: metrics on that period require a deliberate future
code change after everything is frozen.

All returns are decimals: 0.01 means a 1% return. The daily risk-free rate
is also a decimal per-day return, produced upstream by the contract's
(quote / 100) / 252 conversion.
"""

from __future__ import annotations

import math

import pandas as pd

from treasury_rotation.config import TEST_START
from treasury_rotation.portfolio import (
    LockedTestPeriodError,
    PortfolioValidationError,
)

# Contract v0.2.3: 252 trading days is the single definition of one year for
# every metric. Years elapsed is a count of measured daily returns, not a
# calendar difference, so CAGR, Sharpe, and turnover all share one clock.
TRADING_DAYS_PER_YEAR = 252


class MetricsValidationError(PortfolioValidationError):
    """Raised when a metric input is structurally invalid or undefined."""


def years_elapsed(net_returns: pd.Series) -> float:
    """Convert a measured daily-return series into contract years."""

    _validate_return_series(net_returns, series_name="net returns")
    return len(net_returns) / TRADING_DAYS_PER_YEAR


def compound_growth_rate(net_returns: pd.Series) -> float:
    """Contract CAGR: the steady annual rate matching total net growth.

    Ending wealth divided by starting wealth is the product of all daily
    (1 + return) factors, so the wealth index itself never needs to be
    passed in separately.
    """

    _validate_return_series(net_returns, series_name="net returns")
    ending_wealth = float((1.0 + net_returns).prod())
    return ending_wealth ** (1.0 / years_elapsed(net_returns)) - 1.0


def annualized_volatility(net_returns: pd.Series) -> float:
    """Sample standard deviation of daily net returns times sqrt(252)."""

    _validate_return_series(net_returns, series_name="net returns")
    if len(net_returns) < 2:
        raise MetricsValidationError(
            "Annualized volatility requires at least two daily returns."
        )
    daily_std = float(net_returns.std(ddof=1))
    return daily_std * math.sqrt(TRADING_DAYS_PER_YEAR)


def sharpe_ratio(
    net_returns: pd.Series,
    daily_risk_free: pd.Series,
) -> float:
    """Annualized mean excess net return over annualized excess volatility."""

    _validate_return_series(net_returns, series_name="net returns")
    _validate_return_series(
        daily_risk_free,
        series_name="daily risk-free rates",
    )
    if not net_returns.index.equals(daily_risk_free.index):
        raise MetricsValidationError(
            "Net returns and daily risk-free rates must share identical dates."
        )
    if len(net_returns) < 2:
        raise MetricsValidationError(
            "The Sharpe ratio requires at least two daily returns."
        )

    excess = net_returns - daily_risk_free
    excess_std = float(excess.std(ddof=1))
    if excess_std == 0.0:
        raise MetricsValidationError(
            "The Sharpe ratio is undefined when excess returns never vary."
        )
    annualized_mean = float(excess.mean()) * TRADING_DAYS_PER_YEAR
    annualized_std = excess_std * math.sqrt(TRADING_DAYS_PER_YEAR)
    return annualized_mean / annualized_std


def maximum_drawdown(net_returns: pd.Series) -> float:
    """Largest peak-to-trough decline of the net wealth index, as a negative.

    The wealth index begins at 1.0 before the first measured return, exactly
    as in the portfolio engine, so a loss on the very first day is already a
    drawdown from that starting point.
    """

    _validate_return_series(net_returns, series_name="net returns")
    wealth = (1.0 + net_returns).cumprod()
    # Including the starting value keeps an immediate first-day loss from
    # being invisible to a running maximum taken over later values only.
    running_peak = wealth.cummax().clip(lower=1.0)
    drawdowns = wealth / running_peak - 1.0
    return float(drawdowns.min())


def calmar_ratio(net_returns: pd.Series) -> float:
    """CAGR divided by the magnitude of maximum drawdown."""

    drawdown = maximum_drawdown(net_returns)
    if drawdown == 0.0:
        raise MetricsValidationError(
            "The Calmar ratio is undefined when maximum drawdown is zero."
        )
    return compound_growth_rate(net_returns) / abs(drawdown)


def annual_turnover(daily_turnover: pd.Series) -> float:
    """Total one-way turnover divided by contract years elapsed.

    The uncharged initial allocation never appears in the engine's daily
    turnover column, so it contributes zero here, mirroring the cost model.
    """

    _validate_return_series(daily_turnover, series_name="daily turnover")
    if (daily_turnover < 0).any():
        raise MetricsValidationError("Daily turnover cannot be negative.")
    return float(daily_turnover.sum()) / years_elapsed(daily_turnover)


def summarize_performance(
    daily: pd.DataFrame,
    daily_risk_free: pd.Series,
) -> dict[str, float]:
    """Compute all six frozen metrics from an engine ``daily`` table."""

    for column in ("net_return", "turnover"):
        if column not in daily.columns:
            raise MetricsValidationError(
                f"The daily table is missing the '{column}' column."
            )
    net_returns = daily["net_return"]
    return {
        "cagr": compound_growth_rate(net_returns),
        "annualized_volatility": annualized_volatility(net_returns),
        "sharpe_ratio": sharpe_ratio(net_returns, daily_risk_free),
        "maximum_drawdown": maximum_drawdown(net_returns),
        "calmar_ratio": calmar_ratio(net_returns),
        "annual_turnover": annual_turnover(daily["turnover"]),
    }


def _validate_return_series(series: pd.Series, *, series_name: str) -> None:
    if not isinstance(series.index, pd.DatetimeIndex):
        raise MetricsValidationError(
            f"{series_name.title()} must use a DatetimeIndex."
        )
    if series.empty:
        raise MetricsValidationError(f"{series_name.title()} cannot be empty.")
    if series.index.has_duplicates:
        raise MetricsValidationError(
            f"{series_name.title()} contain duplicate dates."
        )
    if not series.index.is_monotonic_increasing:
        raise MetricsValidationError(
            f"{series_name.title()} dates are not increasing."
        )
    if not pd.api.types.is_numeric_dtype(series):
        raise MetricsValidationError(
            f"{series_name.title()} must contain only numeric values."
        )
    if series.isna().any():
        raise MetricsValidationError(
            f"{series_name.title()} contain missing values."
        )
    if series.isin([float("inf"), -float("inf")]).any():
        raise MetricsValidationError(
            f"{series_name.title()} contain infinite values."
        )
    if (series <= -1).any():
        raise MetricsValidationError(
            f"{series_name.title()} cannot be -100% or lower."
        )
    if (series.index >= pd.Timestamp(TEST_START)).any():
        raise LockedTestPeriodError(
            "The 2021-2025 test period is locked. Metrics may be computed on "
            "development and validation dates only."
        )
