"""Synthetic tests for extraction, validation, hashing, and manifest privacy.

No historical market prices or strategy performance are used in this module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from treasury_rotation.config import TICKERS
from treasury_rotation.data import (
    DataValidationError,
    build_manifest,
    content_sha256,
    extract_adjusted_close,
    validate_adjusted_close,
)


def make_valid_synthetic_prices() -> pd.DataFrame:
    """Return a fresh artificial price table spanning the contract period."""

    index = pd.bdate_range("2003-01-02", "2025-12-31", name="date")
    steps = pd.Series(range(len(index)), index=index, dtype=float)
    return pd.DataFrame(
        {
            "SHY": 80.0 + steps * 0.001,
            "IEF": 70.0 + steps * 0.002,
            "TLT": 60.0 + steps * 0.003,
        },
        index=index,
    )


def nested_keys(value: Any) -> set[str]:
    """Find nested dictionary/list keys so price rows cannot hide in a manifest."""

    if isinstance(value, dict):
        keys = {str(key).lower() for key in value}
        for child in value.values():
            keys.update(nested_keys(child))
        return keys
    if isinstance(value, list):
        keys: set[str] = set()
        for child in value:
            keys.update(nested_keys(child))
        return keys
    return set()


def test_extracts_close_from_yfinance_multiindex() -> None:
    index = pd.bdate_range("2003-01-02", periods=2)
    columns = pd.MultiIndex.from_product(
        [["Close", "Volume"], list(TICKERS)],
        names=["Price", "Ticker"],
    )
    raw = pd.DataFrame(
        [
            [80.0, 70.0, 60.0, 1_000, 2_000, 3_000],
            [80.1, 70.1, 60.1, 1_100, 2_100, 3_100],
        ],
        index=index,
        columns=columns,
    )

    close = extract_adjusted_close(raw)

    assert list(close.columns) == list(TICKERS)
    assert close.index.name == "date"
    assert close.iloc[0].to_dict() == {"SHY": 80.0, "IEF": 70.0, "TLT": 60.0}


def test_validation_accepts_complete_contract_coverage() -> None:
    complete, report = validate_adjusted_close(make_valid_synthetic_prices())

    assert len(complete) == report.rows
    assert report.first_date == "2003-01-02"
    assert report.last_date == "2025-12-31"
    assert report.missing_by_ticker == {"SHY": 0, "IEF": 0, "TLT": 0}
    assert len(report.content_sha256) == 64


def test_validation_rejects_duplicate_dates() -> None:
    prices = make_valid_synthetic_prices()
    duplicated = pd.concat([prices.iloc[[0]], prices])

    with pytest.raises(DataValidationError, match="duplicate"):
        validate_adjusted_close(duplicated)


def test_validation_rejects_nonpositive_prices() -> None:
    prices = make_valid_synthetic_prices()
    prices.loc[pd.Timestamp("2010-01-04"), "IEF"] = 0

    with pytest.raises(DataValidationError, match="strictly positive"):
        validate_adjusted_close(prices)


def test_validation_rejects_implausible_adjusted_move() -> None:
    prices = make_valid_synthetic_prices()
    prices.loc[pd.Timestamp("2010-01-04"), "TLT"] *= 2

    with pytest.raises(DataValidationError, match="integrity threshold"):
        validate_adjusted_close(prices)


def test_content_hash_changes_with_prices() -> None:
    prices = make_valid_synthetic_prices()
    original = content_sha256(prices)
    prices.iloc[-1, -1] += 0.01

    assert content_sha256(prices) != original


def test_manifest_contains_no_price_rows(tmp_path: Path) -> None:
    contract_path = tmp_path / "research_contract.md"
    contract_path.write_text("locked contract\n", encoding="utf-8")
    _, report = validate_adjusted_close(make_valid_synthetic_prices())

    manifest = build_manifest(report, contract_path)

    assert manifest["contract_version"] == "0.2.3"
    assert manifest["tickers"] == list(TICKERS)
    assert manifest["packages"]["scipy"] == "1.18.0"
    assert {"prices", "price_rows", "observations"}.isdisjoint(nested_keys(manifest))
