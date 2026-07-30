"""Hand-checkable tests of portfolio accounting rather than profitability.

All returns are synthetic decimals: 0.01 means 1%, not 0.01%.
"""

from __future__ import annotations

import pandas as pd
import pytest

from treasury_rotation.portfolio import (
    LockedTestPeriodError,
    PortfolioValidationError,
    calculate_returns,
    quarterly_equal_weight_targets,
    run_buy_and_hold_ief,
    run_quarterly_equal_weight,
    simulate_portfolio,
)


def return_frame(
    rows: list[tuple[float, float, float]],
    *,
    start: str = "2020-01-02",
) -> pd.DataFrame:
    """Build dated returns whose tuple order is always SHY, IEF, then TLT."""

    return pd.DataFrame(
        rows,
        index=pd.bdate_range(start, periods=len(rows), name="date"),
        columns=["SHY", "IEF", "TLT"],
        dtype=float,
    )


def test_calculate_returns_from_adjusted_prices() -> None:
    prices = pd.DataFrame(
        {
            "SHY": [50.0, 55.0],
            "IEF": [100.0, 99.0],
            "TLT": [80.0, 80.0],
        },
        index=pd.to_datetime(["2020-01-02", "2020-01-03"]),
    )
    prices.index.name = "date"

    returns = calculate_returns(prices)

    assert returns.loc[pd.Timestamp("2020-01-03"), "SHY"] == pytest.approx(0.10)
    assert returns.loc[pd.Timestamp("2020-01-03"), "IEF"] == pytest.approx(-0.01)
    assert returns.loc[pd.Timestamp("2020-01-03"), "TLT"] == pytest.approx(0.0)


def test_buy_and_hold_ief_exactly_matches_ief_returns() -> None:
    asset_returns = return_frame(
        [
            (0.01, 0.02, 0.03),
            (-0.01, -0.02, 0.00),
            (0.00, 0.01, -0.01),
        ]
    )

    result = run_buy_and_hold_ief(asset_returns)

    pd.testing.assert_series_equal(
        result.daily["gross_return"],
        asset_returns["IEF"].rename("gross_return"),
    )
    pd.testing.assert_series_equal(
        result.daily["net_return"],
        asset_returns["IEF"].rename("net_return"),
    )
    assert result.daily["turnover"].eq(0.0).all()
    assert result.daily["trading_cost"].eq(0.0).all()
    assert result.held_weights["IEF"].eq(1.0).all()


def test_equal_weight_first_return_is_simple_average() -> None:
    asset_returns = return_frame([(0.03, 0.00, -0.03)])

    result = run_quarterly_equal_weight(asset_returns)

    assert result.daily.iloc[0]["gross_return"] == pytest.approx(0.0)
    assert result.daily.iloc[0]["portfolio_value"] == pytest.approx(1.0)


def test_weights_drift_when_no_rebalance_occurs() -> None:
    asset_returns = return_frame([(0.00, 0.00, 0.10)])

    result = run_quarterly_equal_weight(asset_returns)

    # TLT's post-return value divided by the post-return portfolio total.
    expected_tlt_weight = (1.0 / 3.0 * 1.10) / (1.0 + 0.10 / 3.0)
    assert result.ending_weights.iloc[0]["TLT"] == pytest.approx(
        expected_tlt_weight
    )
    assert result.daily.iloc[0]["turnover"] == pytest.approx(0.0)


def test_complete_switch_creates_full_turnover_and_earns_next_day() -> None:
    asset_returns = return_frame(
        [
            (0.00, 0.00, 0.00),
            (0.00, 0.00, 0.02),
        ]
    )
    initial_weights = pd.Series({"SHY": 0.0, "IEF": 1.0, "TLT": 0.0})
    targets = pd.DataFrame(
        [[0.0, 0.0, 1.0]],
        index=asset_returns.index[[0]],
        columns=asset_returns.columns,
    )

    result = simulate_portfolio(
        asset_returns,
        initial_weights=initial_weights,
        targets=targets,
        cost_bps=10,
    )

    assert result.daily.iloc[0]["turnover"] == pytest.approx(1.0)
    assert result.daily.iloc[0]["trading_cost"] == pytest.approx(0.001)
    assert result.daily.iloc[0]["net_return"] == pytest.approx(-0.001)
    assert result.held_weights.iloc[1]["TLT"] == pytest.approx(1.0)
    assert result.daily.iloc[1]["gross_return"] == pytest.approx(0.02)


def test_trading_cost_uses_post_return_portfolio_value() -> None:
    asset_returns = return_frame(
        [
            (0.00, 0.10, 0.00),
            (0.00, 0.00, 0.00),
        ]
    )
    initial_weights = pd.Series({"SHY": 0.0, "IEF": 1.0, "TLT": 0.0})
    targets = pd.DataFrame(
        [[0.0, 0.0, 1.0]],
        index=asset_returns.index[[0]],
        columns=asset_returns.columns,
    )

    result = simulate_portfolio(
        asset_returns,
        initial_weights=initial_weights,
        targets=targets,
        cost_bps=10,
    )

    # IEF grows $1.00 to $1.10 before the complete switch. Ten basis points
    # charged on $1.10 is $0.0011, leaving a net return of 9.89%.
    assert result.daily.iloc[0]["gross_return"] == pytest.approx(0.10)
    assert result.daily.iloc[0]["turnover"] == pytest.approx(1.0)
    assert result.daily.iloc[0]["trading_cost"] == pytest.approx(0.0011)
    assert result.daily.iloc[0]["net_return"] == pytest.approx(0.0989)
    assert result.daily.iloc[0]["portfolio_value"] == pytest.approx(1.0989)
    assert result.held_weights.iloc[1]["TLT"] == pytest.approx(1.0)


def test_quarterly_targets_exclude_final_observation() -> None:
    # June 30 is omitted because a final-date trade would pay a cost without
    # leaving any later return period in which the new allocation could matter.
    dates = pd.bdate_range("2020-01-02", "2020-06-30", name="date")

    targets = quarterly_equal_weight_targets(dates)

    assert list(targets.index) == [pd.Timestamp("2020-03-31")]
    assert targets.iloc[0].sum() == pytest.approx(1.0)


def test_locked_test_period_is_rejected() -> None:
    asset_returns = return_frame([(0.01, 0.01, 0.01)], start="2021-01-04")

    with pytest.raises(LockedTestPeriodError, match="test period is locked"):
        run_buy_and_hold_ief(asset_returns)


def test_infinite_asset_return_is_rejected() -> None:
    asset_returns = return_frame([(0.01, float("inf"), 0.01)])

    with pytest.raises(PortfolioValidationError, match="infinite values"):
        run_buy_and_hold_ief(asset_returns)
