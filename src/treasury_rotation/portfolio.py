"""Portfolio accounting and transparent benchmark simulations.

This module rejects the locked 2021-2025 test period. Unlocking it requires a
deliberate future code change after both strategies and their tests are frozen.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from treasury_rotation.config import (
    PRIMARY_COST_BPS,
    TEST_START,
    TICKERS,
)


class PortfolioValidationError(ValueError):
    """Raised when returns, weights, or portfolio arithmetic are invalid."""


class LockedTestPeriodError(PortfolioValidationError):
    """Raised when this milestone is asked to evaluate the locked test period."""


@dataclass(frozen=True)
class PortfolioSimulation:
    """Auditable daily accounting and two distinct views of portfolio weights.

    ``daily`` records gross return, turnover, transaction-cost drag, net return,
    and cumulative portfolio value. ``held_weights`` earned that row's return;
    ``ending_weights`` reflect market drift and any close-date rebalance and
    therefore become the next row's held weights.
    """

    daily: pd.DataFrame
    held_weights: pd.DataFrame
    ending_weights: pd.DataFrame


def calculate_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Convert a complete adjusted-price table into close-to-close returns."""

    validate_labeled_frame(prices, frame_name="prices")
    if (prices <= 0).any(axis=None):
        raise PortfolioValidationError("Prices must be strictly positive.")

    # A return needs two prices, so the first price row has no return and is
    # deliberately removed. Values are decimals: 0.01 means a 1% return.
    returns = prices.pct_change(fill_method=None).iloc[1:]
    if returns.isna().any(axis=None):
        raise PortfolioValidationError(
            "Returns contain missing values after percentage-change calculation."
        )
    if (returns <= -1).any(axis=None):
        raise PortfolioValidationError("An asset return cannot be -100% or lower.")
    return returns


def run_buy_and_hold_ief(
    asset_returns: pd.DataFrame,
    *,
    cost_bps: int = PRIMARY_COST_BPS,
) -> PortfolioSimulation:
    """Simulate a portfolio that begins in IEF and never intentionally trades."""

    initial_weights = pd.Series(
        {"SHY": 0.0, "IEF": 1.0, "TLT": 0.0},
        dtype=float,
    )
    return simulate_portfolio(
        asset_returns,
        initial_weights=initial_weights,
        targets=_empty_targets(),
        cost_bps=cost_bps,
    )


def run_quarterly_equal_weight(
    asset_returns: pd.DataFrame,
    *,
    cost_bps: int = PRIMARY_COST_BPS,
) -> PortfolioSimulation:
    """Simulate one-third allocations rebalanced at each completed quarter."""

    equal_weights = pd.Series(
        {ticker: 1.0 / len(TICKERS) for ticker in TICKERS},
        dtype=float,
    )
    targets = quarterly_equal_weight_targets(asset_returns.index)
    return simulate_portfolio(
        asset_returns,
        initial_weights=equal_weights,
        targets=targets,
        cost_bps=cost_bps,
    )


def quarterly_equal_weight_targets(index: pd.DatetimeIndex) -> pd.DataFrame:
    """Return equal-weight targets on completed quarter-end observations.

    The final observation is excluded because paying to rebalance after the
    evaluation has ended cannot affect a later return.
    """

    dates = pd.DatetimeIndex(index)
    if dates.empty:
        return _empty_targets()
    if dates.has_duplicates or not dates.is_monotonic_increasing:
        raise PortfolioValidationError(
            "Target dates must be unique and monotonically increasing."
        )

    # Grouping by calendar quarter and taking ``last`` finds the final available
    # trading observation even when the literal quarter-end is not a market day.
    date_series = pd.Series(dates, index=dates)
    quarter_ends = list(date_series.groupby(dates.to_period("Q")).last())
    if quarter_ends and quarter_ends[-1] == dates[-1]:
        quarter_ends = quarter_ends[:-1]

    equal_row = [1.0 / len(TICKERS)] * len(TICKERS)
    return pd.DataFrame(
        [equal_row] * len(quarter_ends),
        index=pd.DatetimeIndex(quarter_ends, name=dates.name),
        columns=list(TICKERS),
        dtype=float,
    )


def simulate_portfolio(
    asset_returns: pd.DataFrame,
    *,
    initial_weights: pd.Series,
    targets: pd.DataFrame,
    cost_bps: int,
) -> PortfolioSimulation:
    """Apply held weights, drift, close-date targets, costs, and compounding.

    Asset returns and weights use decimal units, while ``cost_bps`` is basis
    points charged per dollar of one-way turnover. A target dated today is
    applied only after today's return and can first earn tomorrow's return.
    ``initial_weights`` are already held when measurement begins, so the common
    initial allocation is not charged.

    The returned ``daily`` table expresses trading cost as a fraction of the
    portfolio's opening value, making ``net_return = gross_return -
    trading_cost``. Portfolio value is a wealth index that begins at 1.0.
    """

    _validate_asset_returns(asset_returns)
    current_weights = _validate_weight_row(
        initial_weights,
        row_name="initial weights",
    )
    clean_targets = _validate_targets(targets, asset_returns.index)
    if cost_bps < 0:
        raise PortfolioValidationError("Transaction costs cannot be negative.")

    cost_rate = cost_bps / 10_000.0
    portfolio_value = 1.0
    daily_records: list[dict[str, float]] = []
    held_records: list[pd.Series] = []
    ending_records: list[pd.Series] = []

    for date, return_row in asset_returns.iterrows():
        # Start-of-day weights are the only weights allowed to earn today's
        # return. Recording them separately makes the timing auditable.
        held_records.append(current_weights.rename(date))

        gross_return = float(current_weights.dot(return_row))
        gross_multiplier = 1.0 + gross_return
        if gross_multiplier <= 0:
            raise PortfolioValidationError(
                f"Portfolio value became nonpositive before costs on {date.date()}."
            )

        # Grow each asset independently, then divide by total portfolio growth.
        # This renormalizes the drifted weights so they continue to sum to one.
        post_return_weights = (
            current_weights * (1.0 + return_row) / gross_multiplier
        )

        turnover = 0.0
        if date in clean_targets.index:
            target = clean_targets.loc[date]
            # Purchases and sales describe the same reallocation. Dividing the
            # absolute changes by two prevents counting both sides separately.
            turnover = float((target - post_return_weights).abs().sum() / 2.0)
            # The close-date target is installed only after today's return.
            current_weights = target.copy()
        else:
            current_weights = post_return_weights

        # Turnover is measured after today's market move, so dollar trading
        # costs are based on post-return wealth. Multiplying by gross_multiplier
        # expresses that cost as a fraction of the day's opening portfolio.
        trading_cost = gross_multiplier * turnover * cost_rate
        net_return = gross_return - trading_cost
        if 1.0 + net_return <= 0:
            raise PortfolioValidationError(
                f"Portfolio value became nonpositive after costs on {date.date()}."
            )
        portfolio_value *= 1.0 + net_return

        daily_records.append(
            {
                "gross_return": gross_return,
                "turnover": turnover,
                "trading_cost": trading_cost,
                "net_return": net_return,
                "portfolio_value": portfolio_value,
            }
        )
        # These weights carry forward and become the next row's held weights.
        ending_records.append(current_weights.rename(date))

    daily = pd.DataFrame(daily_records, index=asset_returns.index)
    daily.index.name = asset_returns.index.name
    held_weights = pd.DataFrame(held_records).loc[:, list(TICKERS)]
    ending_weights = pd.DataFrame(ending_records).loc[:, list(TICKERS)]
    held_weights.index.name = asset_returns.index.name
    ending_weights.index.name = asset_returns.index.name

    return PortfolioSimulation(
        daily=daily,
        held_weights=held_weights,
        ending_weights=ending_weights,
    )


def _validate_asset_returns(asset_returns: pd.DataFrame) -> None:
    validate_labeled_frame(asset_returns, frame_name="asset returns")
    if asset_returns.empty:
        raise PortfolioValidationError("Asset returns cannot be empty.")
    if asset_returns.index.min() >= pd.Timestamp(TEST_START) or (
        asset_returns.index >= pd.Timestamp(TEST_START)
    ).any():
        raise LockedTestPeriodError(
            "The 2021-2025 test period is locked. This benchmark milestone may "
            "evaluate development and validation dates only."
        )
    if (asset_returns <= -1).any(axis=None):
        raise PortfolioValidationError("An asset return cannot be -100% or lower.")


def validate_labeled_frame(frame: pd.DataFrame, *, frame_name: str) -> None:
    if list(frame.columns) != list(TICKERS):
        raise PortfolioValidationError(
            f"{frame_name.title()} must have columns {list(TICKERS)} in order."
        )
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise PortfolioValidationError(
            f"{frame_name.title()} must use a DatetimeIndex."
        )
    if frame.index.has_duplicates:
        raise PortfolioValidationError(
            f"{frame_name.title()} contains duplicate dates."
        )
    if not frame.index.is_monotonic_increasing:
        raise PortfolioValidationError(
            f"{frame_name.title()} dates are not increasing."
        )
    if not all(pd.api.types.is_numeric_dtype(dtype) for dtype in frame.dtypes):
        raise PortfolioValidationError(
            f"{frame_name.title()} must contain only numeric values."
        )
    if frame.isna().any(axis=None):
        raise PortfolioValidationError(
            f"{frame_name.title()} contains missing values."
        )
    if frame.isin([float("inf"), -float("inf")]).any(axis=None):
        raise PortfolioValidationError(
            f"{frame_name.title()} contains infinite values."
        )


def _validate_targets(
    targets: pd.DataFrame,
    return_index: pd.DatetimeIndex,
) -> pd.DataFrame:
    if list(targets.columns) != list(TICKERS):
        raise PortfolioValidationError(
            f"Targets must have columns {list(TICKERS)} in order."
        )
    if not isinstance(targets.index, pd.DatetimeIndex):
        raise PortfolioValidationError("Targets must use a DatetimeIndex.")
    if targets.index.has_duplicates:
        raise PortfolioValidationError("Targets contain duplicate dates.")
    if not targets.index.is_monotonic_increasing:
        raise PortfolioValidationError("Target dates are not increasing.")
    if not targets.index.isin(return_index).all():
        raise PortfolioValidationError(
            "Every target date must exist in the asset-return index."
        )

    clean = targets.astype(float)
    for date, row in clean.iterrows():
        _validate_weight_row(row, row_name=f"target weights on {date.date()}")
    return clean


def _validate_weight_row(weights: pd.Series, *, row_name: str) -> pd.Series:
    if list(weights.index) != list(TICKERS):
        raise PortfolioValidationError(
            f"{row_name.title()} must have labels {list(TICKERS)} in order."
        )
    clean = weights.astype(float)
    if clean.isna().any():
        raise PortfolioValidationError(f"{row_name.title()} contains missing values.")
    if ((clean < 0) | (clean > 1)).any():
        raise PortfolioValidationError(
            f"{row_name.title()} must be long-only weights between zero and one."
        )
    if abs(float(clean.sum()) - 1.0) > 1e-10:
        raise PortfolioValidationError(f"{row_name.title()} must sum to one.")
    return clean


def _empty_targets() -> pd.DataFrame:
    return pd.DataFrame(
        index=pd.DatetimeIndex([], name="date"),
        columns=list(TICKERS),
        dtype=float,
    )
