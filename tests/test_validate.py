"""Tests for the validation-period robustness review runner.

Synthetic data only. Nothing here downloads data or touches real results.
The synthetic calendar deliberately crosses BOTH validation edges — it
starts before 2016 and continues past 2020 — so the two fences themselves
are what these tests exercise.
"""

from __future__ import annotations

import pandas as pd
import pytest

from treasury_rotation.config import TICKERS
from treasury_rotation.validate import (
    VALIDATION_BOUNDARY,
    VALIDATION_WINDOW_START,
    RobustnessReviewResult,
    ValidationBoundaryError,
    robustness_review,
    validation_slice,
)

# A deterministic business-day calendar that starts well before the window
# (so pre-window trailing history and a pre-window decision exist) and
# continues past the boundary (so the end fence has something real to cut
# off). The post-2020 tail stays below 2021 dates' locked-period guard
# only because the fence removes it first — which is the point.
FULL_CALENDAR = pd.bdate_range("2014-01-01", "2021-06-30", name="date")


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


def test_validation_slice_drops_every_post_boundary_date() -> None:
    prices = synthetic_prices(FULL_CALENDAR)
    sliced = validation_slice(prices)
    assert sliced.index.max() <= VALIDATION_BOUNDARY
    assert (prices.index > VALIDATION_BOUNDARY).any()
    assert len(sliced) == int((prices.index <= VALIDATION_BOUNDARY).sum())


def test_validation_slice_keeps_pre_window_lookback_history() -> None:
    prices = synthetic_prices(FULL_CALENDAR)
    sliced = validation_slice(prices)
    # Pre-2016 rows survive the slice: they are legitimate lookback fuel.
    assert (sliced.index < VALIDATION_WINDOW_START).any()


def test_validation_slice_refuses_empty_result() -> None:
    late_calendar = pd.bdate_range("2021-01-04", "2021-06-30", name="date")
    prices = synthetic_prices(late_calendar)
    with pytest.raises(ValidationBoundaryError):
        validation_slice(prices)


def test_validation_slice_refuses_data_ending_before_window() -> None:
    early_calendar = pd.bdate_range("2014-01-01", "2015-06-30", name="date")
    prices = synthetic_prices(early_calendar)
    with pytest.raises(ValidationBoundaryError):
        validation_slice(prices)


def test_review_never_reports_outside_the_window() -> None:
    result = robustness_review(
        synthetic_prices(FULL_CALENDAR),
        synthetic_quotes(FULL_CALENDAR),
    )
    assert result.window_start >= VALIDATION_WINDOW_START
    assert result.window_end <= VALIDATION_BOUNDARY


def test_review_measures_from_the_first_window_trading_day() -> None:
    prices = synthetic_prices(FULL_CALENDAR)
    result = robustness_review(prices, synthetic_quotes(FULL_CALENDAR))
    fenced_index = validation_slice(prices).index
    in_window = fenced_index[fenced_index >= VALIDATION_WINDOW_START]
    # Measurement begins on the FIRST trading day inside the window: the
    # warm-up happened before 2016, so no window day is sacrificed to it.
    assert result.window_start == in_window[0]
    assert result.measured_days == len(in_window)


def test_review_requires_pre_window_trailing_history() -> None:
    # A calendar that starts inside the window has no pre-window decision
    # to supply the initial allocation, so the review must refuse to
    # silently warm up inside its own measured period.
    window_only = pd.bdate_range("2016-01-04", "2020-12-31", name="date")
    with pytest.raises(ValidationBoundaryError):
        robustness_review(
            synthetic_prices(window_only),
            synthetic_quotes(window_only),
        )


def test_review_uses_one_shared_measured_window() -> None:
    result = robustness_review(
        synthetic_prices(FULL_CALENDAR),
        synthetic_quotes(FULL_CALENDAR),
    )
    assert isinstance(result, RobustnessReviewResult)
    assert set(result.metrics) == {
        "phase1_momentum",
        "phase2_risk_adjusted",
        "buy_and_hold_ief",
        "equal_weight_quarterly",
    }


def test_review_reports_all_six_metrics_per_portfolio() -> None:
    result = robustness_review(
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


def test_review_rejects_non_contract_cost_levels() -> None:
    from treasury_rotation.data import DataValidationError

    with pytest.raises(DataValidationError):
        robustness_review(
            synthetic_prices(FULL_CALENDAR),
            synthetic_quotes(FULL_CALENDAR),
            cost_bps=7,
        )


def test_review_costs_change_tolls_not_trades() -> None:
    prices = synthetic_prices(FULL_CALENDAR)
    quotes = synthetic_quotes(FULL_CALENDAR)
    results = {
        bps: robustness_review(prices, quotes, cost_bps=bps)
        for bps in (5, 10, 20)
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

    # Buy-and-hold IEF never trades inside the window, so its CAGR is
    # identical at every cost level.
    ief_cagr = {
        bps: results[bps].metrics["buy_and_hold_ief"]["cagr"]
        for bps in (5, 10, 20)
    }
    assert ief_cagr[5] == ief_cagr[10] == ief_cagr[20]


def test_review_buy_and_hold_never_trades() -> None:
    result = robustness_review(
        synthetic_prices(FULL_CALENDAR),
        synthetic_quotes(FULL_CALENDAR),
    )
    # Buy-and-hold IEF is installed as the uncharged initial allocation
    # at the window start and never rebalances: exactly zero turnover.
    assert result.metrics["buy_and_hold_ief"]["annual_turnover"] == 0.0
    # Quarterly equal weight must rebalance drifted weights, so its
    # turnover is strictly positive on this drifting synthetic data.
    assert result.metrics["equal_weight_quarterly"]["annual_turnover"] > 0.0
