"""Tests for the locked-test runner.

Synthetic data only. Nothing here reads the real caches or produces a real
locked-test number. The short synthetic calendar starts before 2021 (so a
2020 decision and trailing history exist) and runs past 2025 (so the end
fence has something real to cut).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from treasury_rotation import metrics as metrics_module
from treasury_rotation import portfolio as portfolio_module
from treasury_rotation.config import TEST_START, TICKERS
from treasury_rotation.data import DataValidationError, validate_adjusted_close
from treasury_rotation.locked_test import (
    OUTPUT_RELATIVE_PATH,
    TEST_BOUNDARY,
    TEST_WINDOW_START,
    UNLOCK_LOG_NAME,
    LockedTestAlreadyRunError,
    LockedTestBoundaryError,
    LockedTestResult,
    LockedTestUnlockError,
    PinnedDataMismatchError,
    evaluate_hypotheses,
    lifted_engine_guard,
    locked_test_review,
    locked_test_slice,
    main,
    verify_pinned_data,
)
from treasury_rotation.portfolio import LockedTestPeriodError, run_buy_and_hold_ief
from treasury_rotation.riskfree import validate_and_fill

FULL_CALENDAR = pd.bdate_range("2019-01-01", "2026-06-30", name="date")
PORTFOLIOS = (
    "phase1_momentum",
    "phase2_risk_adjusted",
    "buy_and_hold_ief",
    "equal_weight_quarterly",
)


def synthetic_prices(index: pd.DatetimeIndex) -> pd.DataFrame:
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
    return pd.Series(2.0, index=index, name="^IRX")


def hand_built_result(values: dict[str, tuple[float, float]], cost_bps: int = 10):
    """values maps portfolio -> (calmar, max drawdown); other metrics fixed."""

    metrics = {
        label: {
            "cagr": 0.01,
            "annualized_volatility": 0.05,
            "sharpe_ratio": 0.1,
            "maximum_drawdown": mdd,
            "calmar_ratio": calmar,
            "annual_turnover": 1.0,
        }
        for label, (calmar, mdd) in values.items()
    }
    return LockedTestResult(
        window_start=pd.Timestamp("2021-01-04"),
        window_end=pd.Timestamp("2025-12-31"),
        measured_days=1255,
        cost_bps=cost_bps,
        metrics=metrics,
    )


def test_slice_drops_every_post_boundary_date() -> None:
    prices = synthetic_prices(FULL_CALENDAR)
    sliced = locked_test_slice(prices)
    assert (prices.index > TEST_BOUNDARY).any()
    assert sliced.index.max() <= TEST_BOUNDARY


def test_slice_keeps_pre_window_lookback_history() -> None:
    sliced = locked_test_slice(synthetic_prices(FULL_CALENDAR))
    assert (sliced.index < TEST_WINDOW_START).any()


def test_slice_refuses_data_ending_before_window() -> None:
    early = pd.bdate_range("2019-01-01", "2020-06-30", name="date")
    with pytest.raises(LockedTestBoundaryError):
        locked_test_slice(synthetic_prices(early))


def test_review_never_reports_outside_the_window() -> None:
    result = locked_test_review(
        synthetic_prices(FULL_CALENDAR), synthetic_quotes(FULL_CALENDAR)
    )
    assert result.window_start >= TEST_WINDOW_START
    assert result.window_end <= TEST_BOUNDARY


def test_review_measures_from_the_first_window_trading_day() -> None:
    prices = synthetic_prices(FULL_CALENDAR)
    result = locked_test_review(prices, synthetic_quotes(FULL_CALENDAR))
    fenced = locked_test_slice(prices).index
    in_window = fenced[fenced >= TEST_WINDOW_START]
    assert result.window_start == in_window[0]
    assert result.measured_days == len(in_window)


def test_review_requires_pre_window_trailing_history() -> None:
    window_only = pd.bdate_range("2021-01-04", "2025-12-31", name="date")
    with pytest.raises(LockedTestBoundaryError):
        locked_test_review(
            synthetic_prices(window_only), synthetic_quotes(window_only)
        )


def test_review_reports_six_metrics_for_four_portfolios() -> None:
    result = locked_test_review(
        synthetic_prices(FULL_CALENDAR), synthetic_quotes(FULL_CALENDAR)
    )
    assert set(result.metrics) == set(PORTFOLIOS)
    for label, values in result.metrics.items():
        assert set(values) == {
            "cagr",
            "annualized_volatility",
            "sharpe_ratio",
            "maximum_drawdown",
            "calmar_ratio",
            "annual_turnover",
        }, label


def test_review_rejects_non_contract_cost_levels() -> None:
    with pytest.raises(DataValidationError):
        locked_test_review(
            synthetic_prices(FULL_CALENDAR),
            synthetic_quotes(FULL_CALENDAR),
            cost_bps=7,
        )


def test_costs_change_tolls_not_trades() -> None:
    prices = synthetic_prices(FULL_CALENDAR)
    quotes = synthetic_quotes(FULL_CALENDAR)
    results = {
        bps: locked_test_review(prices, quotes, cost_bps=bps) for bps in (5, 10, 20)
    }
    for label in PORTFOLIOS:
        turnovers = {
            bps: results[bps].metrics[label]["annual_turnover"] for bps in (5, 10, 20)
        }
        assert turnovers[5] == turnovers[10] == turnovers[20], label
    assert results[10].metrics["buy_and_hold_ief"]["annual_turnover"] == 0.0


def test_guard_is_restored_after_the_review() -> None:
    locked_test_review(
        synthetic_prices(FULL_CALENDAR), synthetic_quotes(FULL_CALENDAR)
    )
    assert portfolio_module.TEST_START == TEST_START
    assert metrics_module.TEST_START == TEST_START
    # Outside the lifted block the frozen engine still refuses 2021 dates.
    window_only = pd.bdate_range("2021-01-04", "2021-06-30", name="date")
    returns = synthetic_prices(window_only).pct_change().dropna()
    with pytest.raises(LockedTestPeriodError):
        run_buy_and_hold_ief(returns, cost_bps=10)


def test_guard_is_restored_when_the_block_raises() -> None:
    with pytest.raises(RuntimeError):
        with lifted_engine_guard():
            assert portfolio_module.TEST_START != TEST_START
            raise RuntimeError("boom")
    assert portfolio_module.TEST_START == TEST_START
    assert metrics_module.TEST_START == TEST_START


def test_hypotheses_pencil_arithmetic() -> None:
    # Phase 1 Calmar 0.40 beats IEF 0.30 and EW 0.35; Phase 1 drawdown
    # -8% is smaller than IEF's -10%; Phase 2 Calmar 0.20 loses to 0.40;
    # Phase 2 drawdown -12% is deeper than Phase 1's -8%.
    result = hand_built_result(
        {
            "phase1_momentum": (0.40, -0.08),
            "phase2_risk_adjusted": (0.20, -0.12),
            "buy_and_hold_ief": (0.30, -0.10),
            "equal_weight_quarterly": (0.35, -0.09),
        }
    )
    outcomes = evaluate_hypotheses(result)
    assert [o.supported for o in outcomes] == [True, True, False, False]


def test_hypotheses_treat_a_tie_as_not_supported() -> None:
    result = hand_built_result(
        {
            "phase1_momentum": (0.30, -0.10),
            "phase2_risk_adjusted": (0.30, -0.10),
            "buy_and_hold_ief": (0.30, -0.10),
            "equal_weight_quarterly": (0.10, -0.20),
        }
    )
    assert not any(o.supported for o in evaluate_hypotheses(result))


def test_hypotheses_need_the_primary_table() -> None:
    result = hand_built_result(
        {label: (0.3, -0.1) for label in PORTFOLIOS}, cost_bps=20
    )
    with pytest.raises(DataValidationError):
        evaluate_hypotheses(result)


def test_main_refuses_without_the_logged_unlock(tmp_path: Path) -> None:
    with pytest.raises(LockedTestUnlockError):
        main(repo_root=tmp_path)


def test_main_refuses_a_second_run(tmp_path: Path) -> None:
    (tmp_path / UNLOCK_LOG_NAME).write_text("unlock", encoding="utf-8")
    output = tmp_path / OUTPUT_RELATIVE_PATH
    output.parent.mkdir(parents=True)
    output.write_text("already ran", encoding="utf-8")
    with pytest.raises(LockedTestAlreadyRunError):
        main(repo_root=tmp_path)


def _full_range_inputs() -> tuple[pd.DataFrame, pd.Series, dict]:
    index = pd.bdate_range("2003-01-02", "2025-12-31", name="date")
    prices = synthetic_prices(index)
    quotes = synthetic_quotes(index)
    _complete, price_report = validate_adjusted_close(prices)
    _filled, quote_report = validate_and_fill(quotes, index)
    manifest = {
        "validation": {"content_sha256": price_report.content_sha256},
        "risk_free": {"validation": {"content_sha256": quote_report.content_sha256}},
    }
    return prices, quotes, manifest


def test_pinned_data_check_passes_on_matching_hashes() -> None:
    prices, quotes, manifest = _full_range_inputs()
    verified_prices, _ = verify_pinned_data(prices, quotes, manifest)
    assert len(verified_prices) == len(prices)


def test_pinned_data_check_halts_on_price_mismatch() -> None:
    prices, quotes, manifest = _full_range_inputs()
    manifest["validation"]["content_sha256"] = "0" * 64
    with pytest.raises(PinnedDataMismatchError):
        verify_pinned_data(prices, quotes, manifest)


def test_pinned_data_check_halts_on_quote_mismatch() -> None:
    prices, quotes, manifest = _full_range_inputs()
    manifest["risk_free"]["validation"]["content_sha256"] = "0" * 64
    with pytest.raises(PinnedDataMismatchError):
        verify_pinned_data(prices, quotes, manifest)
