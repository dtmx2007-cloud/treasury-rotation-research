"""Synthetic tests for the ^IRX risk-free pipeline: fill rule and validation.

Expected values are pencil arithmetic on tiny artificial series. No
historical market data or strategy performance is used in this module.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from treasury_rotation.config import RISK_FREE_TICKER, TICKERS
from treasury_rotation.data import (
    DataValidationError,
    prepare_dataset,
    preserve_risk_free_section,
)
from treasury_rotation.riskfree import (
    daily_risk_free_rates,
    extract_quote_series,
    validate_and_fill,
)


def make_calendar(days: int) -> pd.DatetimeIndex:
    """Return a small artificial trading calendar of business days."""

    return pd.bdate_range("2003-01-02", periods=days, name="date")


def make_quotes(calendar: pd.DatetimeIndex, values: list[float | None]) -> pd.Series:
    """Build a quote series holding only the calendar days with a value."""

    observed = {
        date: value
        for date, value in zip(calendar, values)
        if value is not None
    }
    return pd.Series(observed, name=RISK_FREE_TICKER)


def test_daily_rate_conversion_matches_pencil_arithmetic() -> None:
    # Quote 5.04 means 5.04% per year: 5.04 / 100 = 0.0504 as a decimal,
    # and 0.0504 / 252 = 0.0002 per trading day. Quote 2.52 halves it.
    calendar = make_calendar(2)
    filled, _ = validate_and_fill(make_quotes(calendar, [5.04, 2.52]), calendar)

    rates = daily_risk_free_rates(filled)

    assert rates.iloc[0] == pytest.approx(0.0002)
    assert rates.iloc[1] == pytest.approx(0.0001)


def test_forward_fill_uses_most_recent_prior_quote() -> None:
    # Days: 4.0, 3.0, gap, gap, 2.0, 1.0. Both gap days must carry 3.0,
    # the most recent PRIOR quote; 2.0 arrives later and may not leak back.
    calendar = make_calendar(6)
    quotes = make_quotes(calendar, [4.0, 3.0, None, None, 2.0, 1.0])

    filled, report = validate_and_fill(quotes, calendar)

    assert list(filled) == [4.0, 3.0, 3.0, 3.0, 2.0, 1.0]
    assert report.rows == 6
    assert report.missing_before_fill == 2
    assert report.longest_gap_filled == 2


def test_gap_of_exactly_ten_trading_days_is_filled() -> None:
    # One quote of 5.0, then 10 missing trading days, then 4.0. Ten equals
    # the contract limit, so all ten days fill with 5.0 and validation passes.
    calendar = make_calendar(12)
    quotes = make_quotes(calendar, [5.0] + [None] * 10 + [4.0])

    filled, report = validate_and_fill(quotes, calendar)

    assert list(filled) == [5.0] * 11 + [4.0]
    assert report.longest_gap_filled == 10


def test_two_short_gaps_do_not_sum_into_a_violation() -> None:
    # Two separate 6-day gaps total 12 missing days, above the 10-day
    # limit, but the contract limits CONSECUTIVE days: the longest single
    # gap is 6, so validation must pass. This distinguishes a correct
    # longest-run count from an incorrect total-missing count.
    calendar = make_calendar(15)
    quotes = make_quotes(
        calendar,
        [5.0] + [None] * 6 + [4.0] + [None] * 6 + [3.0],
    )

    filled, report = validate_and_fill(quotes, calendar)

    assert report.missing_before_fill == 12
    assert report.longest_gap_filled == 6
    assert list(filled) == [5.0] * 7 + [4.0] * 7 + [3.0]


def test_gap_of_eleven_trading_days_fails() -> None:
    # Eleven consecutive missing trading days exceeds the 10-day limit.
    calendar = make_calendar(13)
    quotes = make_quotes(calendar, [5.0] + [None] * 11 + [4.0])

    with pytest.raises(DataValidationError, match="gap"):
        validate_and_fill(quotes, calendar)


def test_missing_leading_value_fails() -> None:
    # The first trading day has no quote and nothing earlier to carry
    # forward, so the fill rule cannot start.
    calendar = make_calendar(4)
    quotes = make_quotes(calendar, [None, 5.0, 5.0, 5.0])

    with pytest.raises(DataValidationError, match="prior observation"):
        validate_and_fill(quotes, calendar)


def test_quote_outside_plausibility_bounds_fails() -> None:
    # 26.0 means a 26% annualized three-month Treasury rate, above the
    # 25.0 alarm bound: stop and investigate rather than convert it.
    calendar = make_calendar(3)
    quotes = make_quotes(calendar, [5.0, 26.0, 5.0])

    with pytest.raises(DataValidationError, match="plausibility"):
        validate_and_fill(quotes, calendar)


def test_extracts_close_from_single_ticker_multiindex() -> None:
    index = pd.bdate_range("2003-01-02", periods=2)
    columns = pd.MultiIndex.from_product(
        [["Close", "Volume"], [RISK_FREE_TICKER]],
        names=["Price", "Ticker"],
    )
    raw = pd.DataFrame(
        [[5.04, 0], [2.52, 0]],
        index=index,
        columns=columns,
    )

    quotes = extract_quote_series(raw)

    assert quotes.name == RISK_FREE_TICKER
    assert quotes.index.name == "date"
    assert list(quotes) == [5.04, 2.52]


def test_risk_free_section_survives_price_manifest_rebuild() -> None:
    # A later ETF price refresh rebuilds the manifest from scratch; the
    # recorded fourth series must ride through instead of being erased.
    rebuilt = {"contract_version": "0.2.3"}
    existing = {"risk_free": {"ticker": RISK_FREE_TICKER}}

    merged = preserve_risk_free_section(rebuilt, existing)

    assert merged["risk_free"] == {"ticker": RISK_FREE_TICKER}
    assert preserve_risk_free_section({"a": 1}, {}) == {"a": 1}


def test_prepare_dataset_carries_risk_free_through_rebuild(
    tmp_path: Path,
) -> None:
    # End-to-end guard: a cached ETF revalidation rewrites the whole
    # manifest file, and the previously recorded risk-free entry must
    # still be present in the rewritten file.
    index = pd.bdate_range("2003-01-02", "2025-12-31", name="date")
    steps = pd.Series(range(len(index)), index=index, dtype=float)
    prices = pd.DataFrame(
        {
            "SHY": 80.0 + steps * 0.001,
            "IEF": 70.0 + steps * 0.002,
            "TLT": 60.0 + steps * 0.003,
        },
        index=index,
    ).loc[:, list(TICKERS)]

    cache_path = tmp_path / "data" / "cache" / "adjusted_close.parquet"
    cache_path.parent.mkdir(parents=True)
    prices.to_parquet(cache_path, index=True)
    (tmp_path / "research_contract.md").write_text(
        "locked contract\n", encoding="utf-8"
    )
    manifest_path = tmp_path / "artifacts" / "data_manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps({"risk_free": {"ticker": RISK_FREE_TICKER}}) + "\n",
        encoding="utf-8",
    )

    manifest = prepare_dataset(tmp_path)

    assert manifest["risk_free"] == {"ticker": RISK_FREE_TICKER}
    rewritten = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert rewritten["risk_free"] == {"ticker": RISK_FREE_TICKER}
