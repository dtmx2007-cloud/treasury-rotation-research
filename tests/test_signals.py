"""Synthetic, hand-checkable tests of the Phase 1 raw-momentum rule.

Every price table here is artificial with a known correct answer. No real
market data and no strategy performance measurement appear in this module.
"""

from __future__ import annotations

import pandas as pd
import pytest

from treasury_rotation.portfolio import LockedTestPeriodError
from treasury_rotation.signals import (
    MINIMUM_PRIOR_OBSERVATIONS,
    SignalValidationError,
    generate_phase1_decisions,
    run_phase1,
    select_ticker,
    trailing_returns,
    weekly_decision_dates,
)


def price_frame(
    shy: list[float],
    ief: list[float],
    tlt: list[float],
    *,
    start: str = "2020-01-02",
) -> pd.DataFrame:
    """Build a dated price table whose column order is always SHY, IEF, TLT."""

    index = pd.bdate_range(start, periods=len(shy), name="date")
    return pd.DataFrame(
        {"SHY": shy, "IEF": ief, "TLT": tlt},
        index=index,
        dtype=float,
    )


def flat_prices(periods: int, *, start: str = "2020-01-02") -> pd.DataFrame:
    level = [100.0] * periods
    return price_frame(level, list(level), list(level), start=start)


def scores(shy: float, ief: float, tlt: float) -> pd.Series:
    return pd.Series({"SHY": shy, "IEF": ief, "TLT": tlt}, dtype=float)


def test_weekly_decision_dates_ordinary_and_holiday_weeks() -> None:
    # Two full weeks, but the second Friday (2020-01-17) does not trade.
    dates = pd.bdate_range("2020-01-06", "2020-01-17", name="date")
    dates = dates.drop(pd.Timestamp("2020-01-17"))

    decisions = weekly_decision_dates(dates)

    assert list(decisions) == [
        pd.Timestamp("2020-01-10"),  # ordinary week ends Friday
        pd.Timestamp("2020-01-16"),  # holiday-shortened week ends Thursday
    ]


def test_trailing_return_uses_exactly_63_prior_trading_days() -> None:
    # Decision at position 65 must use positions 1 through 64 and nothing
    # else. Position 1 is halved (inside the window); position 0 is doubled
    # (just outside), so an off-by-one window start changes the answer.
    prices = flat_prices(70)
    prices.iloc[1, prices.columns.get_loc("IEF")] = 50.0
    prices.iloc[0, prices.columns.get_loc("IEF")] = 200.0

    result = trailing_returns(prices, prices.index[65])

    assert result["IEF"] == pytest.approx(1.0)  # 100 / 50 - 1
    assert result["SHY"] == pytest.approx(0.0)
    assert result["TLT"] == pytest.approx(0.0)


def test_decision_date_price_cannot_influence_selection() -> None:
    # SHY explodes on the decision date itself. The window ends one trading
    # day earlier, so SHY's score must remain zero and IEF must still win.
    prices = flat_prices(70)
    prices.iloc[1, prices.columns.get_loc("IEF")] = 50.0
    prices.iloc[65, prices.columns.get_loc("SHY")] = 1000.0

    result = trailing_returns(prices, prices.index[65])

    assert result["SHY"] == pytest.approx(0.0)
    assert select_ticker(result) == "IEF"


def test_insufficient_history_is_rejected() -> None:
    prices = flat_prices(70)

    with pytest.raises(SignalValidationError, match="prior observations"):
        trailing_returns(prices, prices.index[MINIMUM_PRIOR_OBSERVATIONS - 1])


def test_highest_positive_momentum_wins() -> None:
    assert select_ticker(scores(0.01, 0.05, 0.03)) == "IEF"
    assert select_ticker(scores(0.06, 0.05, 0.03)) == "SHY"
    assert select_ticker(scores(-0.01, -0.05, 0.03)) == "TLT"


def test_all_negative_momentum_selects_shy() -> None:
    assert select_ticker(scores(-0.04, -0.01, -0.03)) == "SHY"


def test_exact_tie_breaks_to_shortest_duration() -> None:
    # v0.2.1 clarification: the tied ticker earliest in (SHY, IEF, TLT) wins.
    assert select_ticker(scores(-0.02, 0.05, 0.05)) == "IEF"
    assert select_ticker(scores(0.05, 0.05, 0.01)) == "SHY"
    # All exactly zero: zero is not negative, so the fallback does not fire,
    # and the three-way tie resolves to SHY by duration.
    assert select_ticker(scores(0.0, 0.0, 0.0)) == "SHY"


def test_warm_up_first_decision_and_one_hot_targets() -> None:
    # With 70 business days from 2020-01-02, weekly decision dates with at
    # least 64 prior observations are 2020-04-03 (position 66) and
    # 2020-04-08 (position 69, the final observation).
    decisions = generate_phase1_decisions(flat_prices(70))

    assert list(decisions.targets.index) == [
        pd.Timestamp("2020-04-03"),
        pd.Timestamp("2020-04-08"),
    ]
    for _, row in decisions.targets.iterrows():
        assert row.sum() == pytest.approx(1.0)
        assert set(row) <= {0.0, 1.0}
        assert (row >= 0).all()
    # Flat prices tie every score at zero, so every selection is SHY.
    assert list(decisions.selections) == ["SHY", "SHY"]


def test_no_qualifying_decision_date_is_rejected() -> None:
    with pytest.raises(SignalValidationError, match="enough history"):
        generate_phase1_decisions(flat_prices(30))


def make_switch_prices() -> pd.DataFrame:
    """Prices whose first decision picks TLT and second decision picks IEF.

    TLT rises one point per day through position 65, then falls ten points
    per day. IEF compounds steadily at 0.2% per day. SHY stays flat. At the
    2020-04-03 decision TLT's trailing return (about 62%) beats IEF (about
    13%); by 2020-04-10 TLT's trailing return (about 7%) loses to IEF.
    """

    tlt = [
        100.0 + i if i <= 65 else 165.0 - 10.0 * (i - 65)
        for i in range(75)
    ]
    ief = [100.0 * 1.002**i for i in range(75)]
    shy = [100.0] * 75
    return price_frame(shy, ief, tlt)


def test_first_selection_seeds_free_initial_allocation() -> None:
    decisions, simulation = run_phase1(make_switch_prices(), cost_bps=10)

    assert decisions.selections.loc[pd.Timestamp("2020-04-03")] == "TLT"
    # Measurement begins the next trading day after the first decision close.
    assert simulation.daily.index[0] == pd.Timestamp("2020-04-06")
    assert simulation.held_weights.iloc[0]["TLT"] == pytest.approx(1.0)
    # The initial allocation is installed without cost.
    assert simulation.daily.iloc[0]["turnover"] == pytest.approx(0.0)
    assert simulation.daily.iloc[0]["trading_cost"] == pytest.approx(0.0)


def test_switch_decision_affects_only_later_returns() -> None:
    prices = make_switch_prices()
    decisions, simulation = run_phase1(prices, cost_bps=10)

    assert decisions.selections.loc[pd.Timestamp("2020-04-10")] == "IEF"
    # On the decision day itself the portfolio still earned TLT's return.
    decision_day = pd.Timestamp("2020-04-10")
    tlt_return = (
        prices.loc[decision_day, "TLT"]
        / prices.loc[pd.Timestamp("2020-04-09"), "TLT"]
        - 1.0
    )
    assert simulation.daily.loc[decision_day, "gross_return"] == pytest.approx(
        tlt_return
    )
    assert simulation.held_weights.loc[decision_day, "TLT"] == pytest.approx(1.0)
    # IEF is first held on the next trading day.
    assert simulation.held_weights.loc[
        pd.Timestamp("2020-04-13"), "IEF"
    ] == pytest.approx(1.0)


def test_switch_turnover_and_costs_flow_through_engine() -> None:
    prices = make_switch_prices()
    _, simulation = run_phase1(prices, cost_bps=10)

    decision_day = pd.Timestamp("2020-04-10")
    tlt_return = (
        prices.loc[decision_day, "TLT"]
        / prices.loc[pd.Timestamp("2020-04-09"), "TLT"]
        - 1.0
    )
    # A complete one-asset switch is 100% one-way turnover, and ten basis
    # points are charged on the post-return portfolio value.
    assert simulation.daily.loc[decision_day, "turnover"] == pytest.approx(1.0)
    assert simulation.daily.loc[decision_day, "trading_cost"] == pytest.approx(
        (1.0 + tlt_return) * 0.001
    )
    # No other day trades.
    other_days = simulation.daily.drop(index=decision_day)
    assert other_days["turnover"].eq(0.0).all()


def test_final_observation_decision_is_not_traded() -> None:
    # 2020-04-15 is both a weekly decision date and the final observation.
    # It appears in the decision record but must not create a trade.
    decisions, simulation = run_phase1(make_switch_prices(), cost_bps=10)

    final_day = pd.Timestamp("2020-04-15")
    assert final_day in decisions.targets.index
    assert simulation.daily.loc[final_day, "turnover"] == pytest.approx(0.0)


def test_locked_test_period_guard_remains_effective() -> None:
    prices = flat_prices(80, start="2020-09-15")
    assert prices.index[-1] >= pd.Timestamp("2021-01-01")

    with pytest.raises(LockedTestPeriodError, match="test period is locked"):
        run_phase1(prices, cost_bps=10)
