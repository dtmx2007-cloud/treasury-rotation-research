"""Hand-computed tests of the six frozen metrics, never of profitability.

All returns are synthetic decimals: 0.01 means 1%, not 0.01%. Every expected
value below is derived by pencil arithmetic in the accompanying comment, so a
silent change to any metric convention breaks a visible number.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from treasury_rotation.metrics import (
    LockedTestPeriodError,
    MetricsValidationError,
    annual_turnover,
    annualized_volatility,
    calmar_ratio,
    compound_growth_rate,
    maximum_drawdown,
    sharpe_ratio,
    summarize_performance,
    years_elapsed,
)


def dated_series(values: list[float], *, start: str = "2010-01-04") -> pd.Series:
    return pd.Series(
        values,
        index=pd.bdate_range(start, periods=len(values), name="date"),
        dtype=float,
    )


def test_years_elapsed_counts_returns_not_calendar_days() -> None:
    # Contract v0.2.3 clause 1: 504 measured daily returns are exactly two
    # contract years regardless of the calendar dates they span.
    returns = dated_series([0.0] * 504)

    assert years_elapsed(returns) == pytest.approx(2.0)


def test_cagr_of_constant_daily_return() -> None:
    # 504 days of 0.1% daily growth is two contract years. Ending wealth is
    # 1.001 ** 504, and the steady annual rate matching it is 1.001 ** 252 - 1,
    # because (1.001 ** 504) ** (1 / 2) = 1.001 ** 252.
    returns = dated_series([0.001] * 504)

    assert compound_growth_rate(returns) == pytest.approx(1.001**252 - 1.0)


def test_cagr_matches_hand_compounded_wealth() -> None:
    # One contract year built from 252 zero returns plus a single +10% day.
    # Ending wealth is exactly 1.10 over 253 / 252 years, so CAGR is
    # 1.10 ** (252 / 253) - 1: slightly under 10% because the stretch is
    # slightly longer than one year.
    returns = dated_series([0.0] * 252 + [0.10])

    assert compound_growth_rate(returns) == pytest.approx(
        1.10 ** (252.0 / 253.0) - 1.0
    )


def test_volatility_uses_sample_standard_deviation_and_sqrt_252() -> None:
    # Returns +1% then -1%: mean 0, squared deviations 0.0001 each, sample
    # variance (n - 1 = 1 denominator) 0.0002, daily std sqrt(0.0002).
    returns = dated_series([0.01, -0.01])

    expected_daily_std = math.sqrt(0.0002)
    assert annualized_volatility(returns) == pytest.approx(
        expected_daily_std * math.sqrt(252.0)
    )


def test_volatility_of_constant_returns_is_zero() -> None:
    returns = dated_series([0.005] * 10)

    assert annualized_volatility(returns) == pytest.approx(0.0)


def test_sharpe_ratio_hand_computed_with_constant_risk_free() -> None:
    # Net returns 2% then 0% against a constant 0.5% daily risk-free rate.
    # Excess returns: 1.5% and -0.5%. Mean excess 0.5%; deviations +1% and
    # -1%, so sample std is sqrt(0.0002). Sharpe is then
    # (0.005 * 252) / (sqrt(0.0002) * sqrt(252)).
    returns = dated_series([0.02, 0.00])
    risk_free = dated_series([0.005, 0.005])

    expected = (0.005 * 252.0) / (math.sqrt(0.0002) * math.sqrt(252.0))
    assert sharpe_ratio(returns, risk_free) == pytest.approx(expected)


def test_sharpe_subtracts_risk_free_before_averaging() -> None:
    # With a zero risk-free rate the same returns produce a different Sharpe:
    # mean 1%, same std, so (0.01 * 252) / (sqrt(0.0002) * sqrt(252)). A
    # mutation that ignores the risk-free series fails one of these two tests.
    returns = dated_series([0.02, 0.00])
    zero_risk_free = dated_series([0.0, 0.0])

    expected = (0.01 * 252.0) / (math.sqrt(0.0002) * math.sqrt(252.0))
    assert sharpe_ratio(returns, zero_risk_free) == pytest.approx(expected)


def test_sharpe_requires_identical_dates() -> None:
    returns = dated_series([0.01, 0.02])
    shifted = dated_series([0.001, 0.001], start="2010-01-05")

    with pytest.raises(MetricsValidationError, match="identical dates"):
        sharpe_ratio(returns, shifted)


def test_sharpe_undefined_for_constant_excess_returns() -> None:
    returns = dated_series([0.01, 0.01])
    risk_free = dated_series([0.001, 0.001])

    with pytest.raises(MetricsValidationError, match="never vary"):
        sharpe_ratio(returns, risk_free)


def test_maximum_drawdown_of_constructed_peak_and_trough() -> None:
    # Wealth path: 1.10, 0.88, 0.924, 0.8316, then recovery. The peak is 1.10
    # and the trough is 0.8316, so the drawdown is 0.8316 / 1.10 - 1 = -0.244.
    returns = dated_series([0.10, -0.20, 0.05, -0.10, 0.30])

    assert maximum_drawdown(returns) == pytest.approx(0.8316 / 1.10 - 1.0)


def test_maximum_drawdown_measures_first_day_loss_from_starting_wealth() -> None:
    # The wealth index begins at 1.0, so an immediate -5% day is a -5%
    # drawdown even though every later value is a new running maximum.
    returns = dated_series([-0.05, 0.01, 0.01, 0.01, 0.01, 0.01])

    assert maximum_drawdown(returns) == pytest.approx(-0.05)


def test_maximum_drawdown_is_zero_when_wealth_never_falls() -> None:
    returns = dated_series([0.01, 0.02, 0.00, 0.03])

    assert maximum_drawdown(returns) == pytest.approx(0.0)


def test_calmar_ratio_hand_computed() -> None:
    # Two days: +10% then -10%. Wealth ends at 0.99 over 2 / 252 years, so
    # CAGR is 0.99 ** 126 - 1. The only decline is 0.99 / 1.10 - 1 = -0.1
    # exactly, so Calmar is (0.99 ** 126 - 1) / 0.1: a large negative number.
    returns = dated_series([0.10, -0.10])

    expected_cagr = 0.99**126 - 1.0
    assert calmar_ratio(returns) == pytest.approx(expected_cagr / 0.1)


def test_calmar_undefined_when_drawdown_is_zero() -> None:
    returns = dated_series([0.01, 0.01])

    with pytest.raises(MetricsValidationError, match="undefined"):
        calmar_ratio(returns)


def test_annual_turnover_averages_over_contract_years() -> None:
    # Two full one-way switches inside 504 days (two contract years) average
    # to one switch per year.
    turnover = dated_series([0.0] * 504)
    turnover.iloc[100] = 1.0
    turnover.iloc[400] = 1.0

    assert annual_turnover(turnover) == pytest.approx(1.0)


def test_annual_turnover_rejects_negative_values() -> None:
    turnover = dated_series([0.0, -0.5, 0.0])

    with pytest.raises(MetricsValidationError, match="negative"):
        annual_turnover(turnover)


def test_summarize_performance_returns_all_six_frozen_metrics() -> None:
    daily = pd.DataFrame(
        {
            "net_return": [0.02, 0.00, -0.01],
            "turnover": [0.0, 1.0, 0.0],
        },
        index=pd.bdate_range("2010-01-04", periods=3, name="date"),
    )
    risk_free = dated_series([0.0001, 0.0001, 0.0001])

    summary = summarize_performance(daily, risk_free)

    assert set(summary) == {
        "cagr",
        "annualized_volatility",
        "sharpe_ratio",
        "maximum_drawdown",
        "calmar_ratio",
        "annual_turnover",
    }
    assert summary["maximum_drawdown"] == pytest.approx(-0.01)
    assert summary["annual_turnover"] == pytest.approx(1.0 / (3.0 / 252.0))


def test_metrics_reject_the_locked_test_period() -> None:
    returns = dated_series([0.01] * 5, start="2020-12-28")

    assert returns.index.max() >= pd.Timestamp("2021-01-01")
    with pytest.raises(LockedTestPeriodError, match="test period is locked"):
        compound_growth_rate(returns)


def test_metrics_reject_missing_values() -> None:
    returns = dated_series([0.01, float("nan"), 0.02])

    with pytest.raises(MetricsValidationError, match="missing values"):
        annualized_volatility(returns)
