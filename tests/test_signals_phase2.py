"""Synthetic, hand-checkable tests of the Phase 2 risk-adjusted rule.

Expected volatilities are computed independently with ``statistics.stdev``
so a pandas mistake cannot silently agree with itself. No real market data
and no strategy performance measurement appear in this module.
"""

from __future__ import annotations

import math
import statistics

import pandas as pd
import pytest

from treasury_rotation.portfolio import LockedTestPeriodError
from treasury_rotation.signals import (
    SignalValidationError,
    generate_phase2_decisions,
    run_phase2,
    select_ticker,
    select_ticker_risk_adjusted,
    trailing_volatility,
)
from tests.test_signals import flat_prices, price_frame, scores


def labeled(shy: float, ief: float, tlt: float) -> pd.Series:
    return pd.Series({"SHY": shy, "IEF": ief, "TLT": tlt}, dtype=float)


def test_volatility_uses_exactly_21_returns_ending_before_decision() -> None:
    # Decision at position 65: the window is the 21 daily returns at
    # positions 44 through 64, built from prices 43 through 64. Position 43
    # is the base of the window's first return, so a bump there changes
    # exactly ONE in-window return (at 44); the +10% move at position 43
    # itself belongs to the return at 43, which is outside the window.
    prices = flat_prices(70)
    prices.iloc[43, prices.columns.get_loc("IEF")] = 110.0

    result = trailing_volatility(prices, prices.index[65])

    window_returns = [100.0 / 110.0 - 1.0] + [0.0] * 20
    expected = statistics.stdev(window_returns) * math.sqrt(252.0)
    assert result["IEF"] == pytest.approx(expected)
    assert result["SHY"] == pytest.approx(0.0)


def test_prices_outside_volatility_window_do_not_matter() -> None:
    prices = flat_prices(70)
    prices.iloc[42, prices.columns.get_loc("SHY")] = 90.0   # too old
    prices.iloc[65, prices.columns.get_loc("TLT")] = 500.0  # decision date

    result = trailing_volatility(prices, prices.index[65])

    assert result["SHY"] == pytest.approx(0.0)
    assert result["TLT"] == pytest.approx(0.0)


def test_annualization_multiplies_by_square_root_of_252() -> None:
    # Alternate +1% and -1% daily moves so the daily standard deviation is
    # known and nonzero, then check the annualization factor explicitly.
    values = [100.0]
    for step in range(69):
        change = 0.01 if step % 2 == 0 else -0.01
        values.append(values[-1] * (1.0 + change))
    prices = price_frame([100.0] * 70, values, [100.0] * 70)

    result = trailing_volatility(prices, prices.index[65])

    window_prices = values[43:65]
    window_returns = [
        window_prices[i + 1] / window_prices[i] - 1.0
        for i in range(len(window_prices) - 1)
    ]
    daily_std = statistics.stdev(window_returns)
    assert result["IEF"] == pytest.approx(daily_std * math.sqrt(252.0))


def test_risk_adjustment_can_overturn_raw_momentum() -> None:
    # TLT has the higher raw return but four times the volatility, so its
    # return per unit of risk is lower. Phase 1 picks TLT; Phase 2 must
    # pick IEF from identical inputs.
    raw = labeled(0.0, 0.06, 0.08)
    volatility = labeled(0.01, 0.04, 0.16)

    assert select_ticker(raw) == "TLT"
    assert select_ticker_risk_adjusted(raw, volatility) == "IEF"  # 1.5 > 0.5


def test_negative_raw_returns_are_never_scored() -> None:
    # TLT's hypothetical ratio would dominate, but its raw return is
    # negative, so it is not a candidate. Its volatility is zero, which
    # must NOT raise, because a non-candidate's volatility is never used.
    raw = labeled(-0.02, 0.01, -0.04)
    volatility = labeled(0.05, 0.20, 0.0)

    assert select_ticker_risk_adjusted(raw, volatility) == "IEF"


def test_no_strictly_positive_return_selects_shy() -> None:
    # v0.2.2 fallback: a highest return of exactly zero is not positive,
    # so nothing is scored and SHY is selected.
    assert select_ticker_risk_adjusted(
        labeled(0.0, -0.01, -0.03), labeled(0.05, 0.05, 0.05)
    ) == "SHY"
    assert select_ticker_risk_adjusted(
        labeled(-0.04, -0.01, -0.03), labeled(0.05, 0.05, 0.05)
    ) == "SHY"


def test_zero_volatility_for_a_candidate_is_a_validation_failure() -> None:
    raw = labeled(0.0, 0.05, 0.0)

    with pytest.raises(SignalValidationError, match="zero or missing"):
        select_ticker_risk_adjusted(raw, labeled(0.05, 0.0, 0.05))


def test_exact_score_tie_breaks_to_shortest_duration() -> None:
    # IEF and TLT tie exactly at a ratio of 0.5; IEF is earlier in the
    # duration ordering and must win.
    raw = labeled(-0.01, 0.02, 0.04)
    volatility = labeled(0.05, 0.04, 0.08)

    assert select_ticker_risk_adjusted(raw, volatility) == "IEF"


def make_phase2_prices() -> pd.DataFrame:
    """Prices in which Phase 2 must overturn Phase 1's ranking.

    IEF climbs smoothly; TLT ends higher over any 63-day window but gets
    there through violent alternating swings, so its risk-adjusted score is
    far lower. SHY stays flat and is never a candidate.
    """

    ief = [100.0 * 1.002**i for i in range(75)]
    tlt = [100.0]
    for step in range(74):
        change = 0.05 if step % 2 == 0 else -0.04
        tlt.append(tlt[-1] * (1.0 + change))
    shy = [100.0] * 75
    return price_frame(shy, ief, tlt)


def test_generated_decisions_are_one_hot_and_auditable() -> None:
    decisions = generate_phase2_decisions(make_phase2_prices())

    for _, row in decisions.targets.iterrows():
        assert row.sum() == pytest.approx(1.0)
        assert set(row) <= {0.0, 1.0}
    # SHY's raw return is never strictly positive, so it is never scored.
    assert decisions.risk_scores["SHY"].isna().all()
    # Raw momentum would pick TLT; the risk adjustment must pick IEF.
    first = decisions.raw_scores.index[0]
    assert decisions.raw_scores.loc[first, "TLT"] > decisions.raw_scores.loc[
        first, "IEF"
    ]
    assert (decisions.selections == "IEF").all()


def test_phase2_flows_through_portfolio_engine() -> None:
    decisions, simulation = run_phase2(make_phase2_prices(), cost_bps=10)

    first_decision = decisions.targets.index[0]
    # Measurement begins the next trading day after the first decision.
    assert simulation.daily.index[0] > first_decision
    assert simulation.held_weights.iloc[0]["IEF"] == pytest.approx(1.0)
    # The initial allocation is free, and IEF is held throughout, so no
    # turnover or trading cost ever occurs in this construction.
    assert simulation.daily["turnover"].eq(0.0).all()
    assert simulation.daily["trading_cost"].eq(0.0).all()


def test_locked_test_period_guard_remains_effective() -> None:
    prices = flat_prices(80, start="2020-09-15")
    assert prices.index[-1] >= pd.Timestamp("2021-01-01")

    with pytest.raises(LockedTestPeriodError, match="test period is locked"):
        run_phase2(prices, cost_bps=10)
