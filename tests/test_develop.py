"""Tests for the development-period first-look runner.

Synthetic data only. Nothing here downloads data or touches real results.
The synthetic calendar deliberately crosses the development boundary so
the fence itself is what these tests exercise.
"""

from __future__ import annotations

import pandas as pd
import pytest

from treasury_rotation.config import TICKERS
from treasury_rotation.develop import (
    DEVELOPMENT_BOUNDARY,
    DevelopmentBoundaryError,
    development_slice,
    first_look,
)

# A deterministic business-day calendar that starts well before the
# boundary (so the 64-observation warm-up qualifies) and continues past
# it (so the fence has something real to cut off).
FULL_CALENDAR = pd.bdate_range("2014-01-01", "2016-06-30", name="date")


def synthetic_prices(index: pd.DatetimeIndex) -> pd.DataFrame:
    """Strictly positive drifting prices with mild deterministic wiggle.

    The wiggle keeps daily returns from being constant (the Sharpe ratio
    is undefined when excess returns never vary) while staying far below
    every integrity threshold.
    """

    steps = pd.Series(range(len(index)), index=index, dtype=float)
    wiggle = (steps % 5.0 - 2.0) / 1_000.0
    return pd.DataFrame(
        {
            "SHY": 80.0 * (1.0002 + wiggle / 4.0).cumprod(),
            "IEF": 100.0 * (1.0004 + wiggle / 2.0).cumprod(),
            "TLT": 120.0 * (1.0006 + wiggle).cumprod(),
        },
        index=index,
    ).loc[:, list(TICKERS)]


def synthetic_quotes(index: pd.DatetimeIndex) -> pd.Series:
    """A complete, in-bounds ^IRX quote series on the same calendar."""

    return pd.Series(2.0, index=index, name="^IRX")


def test_development_slice_drops_every_later_date() -> None:
    prices = synthetic_prices(FULL_CALENDAR)
    sliced = development_slice(prices)
    assert sliced.index.max() <= DEVELOPMENT_BOUNDARY
    assert (prices.index > DEVELOPMENT_BOUNDARY).any()
    assert len(sliced) == int((prices.index <= DEVELOPMENT_BOUNDARY).sum())


def test_development_slice_refuses_empty_result() -> None:
    late_calendar = pd.bdate_range("2022-01-03", "2022-06-30", name="date")
    prices = synthetic_prices(late_calendar)
    with pytest.raises(DevelopmentBoundaryError):
        development_slice(prices)


def test_first_look_never_reports_past_the_boundary() -> None:
    result = first_look(
        synthetic_prices(FULL_CALENDAR),
        synthetic_quotes(FULL_CALENDAR),
    )
    assert result.window_end <= DEVELOPMENT_BOUNDARY


def test_first_look_uses_one_shared_measured_window() -> None:
    prices = synthetic_prices(FULL_CALENDAR)
    result = first_look(prices, synthetic_quotes(FULL_CALENDAR))

    # The window starts strictly after enough history exists for the
    # 64-observation warm-up, never on the first trading day.
    dev_index = development_slice(prices).index
    assert result.window_start > dev_index[64]
    assert result.measured_days == len(
        dev_index[dev_index > result.window_start]
    ) + 1
    assert set(result.metrics) == {
        "phase1_momentum",
        "phase2_risk_adjusted",
        "buy_and_hold_ief",
        "equal_weight_quarterly",
    }


def test_first_look_reports_all_six_metrics_per_portfolio() -> None:
    result = first_look(
        synthetic_prices(FULL_CALENDAR),
        synthetic_quotes(FULL_CALENDAR),
    )
    expected = {
        "cagr",
        "annualized_volatility",
        "sharpe_ratio",
        "maximum_drawdown",
        "calmar_ratio",
        "annual_turnover",
    }
    for label, metrics in result.metrics.items():
        assert set(metrics) == expected, label
        assert all(isinstance(value, float) for value in metrics.values())


def test_first_look_rejects_non_contract_cost_levels() -> None:
    from treasury_rotation.data import DataValidationError

    with pytest.raises(DataValidationError):
        first_look(
            synthetic_prices(FULL_CALENDAR),
            synthetic_quotes(FULL_CALENDAR),
            cost_bps=7,
        )


def test_first_look_costs_change_tolls_not_trades() -> None:
    prices = synthetic_prices(FULL_CALENDAR)
    quotes = synthetic_quotes(FULL_CALENDAR)
    results = {
        bps: first_look(prices, quotes, cost_bps=bps) for bps in (5, 10, 20)
    }

    for label in (
        "phase1_momentum",
        "phase2_risk_adjusted",
        "buy_and_hold_ief",
        "equal_weight_quarterly",
    ):
        # Decisions never see costs, so turnover is identical at every
        # cost level; only the toll per dollar traded changes.
        turnovers = {
            bps: results[bps].metrics[label]["annual_turnover"]
            for bps in (5, 10, 20)
        }
        assert turnovers[5] == turnovers[10] == turnovers[20], label

    # A trading portfolio keeps more wealth at a lower toll; buy-and-hold
    # IEF never trades after the free initial allocation, so its CAGR is
    # identical at every cost level.
    equal_weight_cagr = {
        bps: results[bps].metrics["equal_weight_quarterly"]["cagr"]
        for bps in (5, 10, 20)
    }
    assert equal_weight_cagr[5] > equal_weight_cagr[20]
    ief_cagr = {
        bps: results[bps].metrics["buy_and_hold_ief"]["cagr"]
        for bps in (5, 10, 20)
    }
    assert ief_cagr[5] == ief_cagr[10] == ief_cagr[20]


def test_first_look_buy_and_hold_never_trades() -> None:
    result = first_look(
        synthetic_prices(FULL_CALENDAR),
        synthetic_quotes(FULL_CALENDAR),
    )
    # Buy-and-hold IEF is installed as the uncharged initial allocation
    # and never rebalances, so its contract turnover is exactly zero.
    assert result.metrics["buy_and_hold_ief"]["annual_turnover"] == 0.0
    # Quarterly equal weight must rebalance drifted weights, so its
    # turnover is strictly positive on this drifting synthetic data.
    assert result.metrics["equal_weight_quarterly"]["annual_turnover"] > 0.0
