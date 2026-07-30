"""Fetch, validate, forward-fill, and fingerprint the ^IRX risk-free series.

Contract v0.2.3 metric clarifications 3-5 govern this module. The
three-month Treasury rate is the daily ^IRX quote from Yahoo Finance via
yfinance, recorded as a fourth data series in the manifest. The quoted
value is an annualized percentage; the daily rate is (quote / 100) / 252.
A missing observation on a trading day is forward-filled from the most
recent prior trading day. A gap exceeding 10 consecutive trading days, or
a missing value with no prior observation to carry forward, is a
data-validation failure, not an invitation to substitute a new rule.

Forward-fill is the only permitted repair because it uses strictly past
information. Interpolating across a gap would blend in the quote observed
after the gap, which did not exist yet on the missing day.

This module intentionally contains no strategy or benchmark implementation.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

from treasury_rotation.config import (
    DATA_END_EXCLUSIVE,
    DATA_START,
    MAX_RISK_FREE_GAP_TRADING_DAYS,
    MAX_RISK_FREE_QUOTE,
    MIN_RISK_FREE_QUOTE,
    RISK_FREE_TICKER,
)
from treasury_rotation.data import (
    DataValidationError,
    content_sha256,
    repository_root,
)
from treasury_rotation.metrics import TRADING_DAYS_PER_YEAR


@dataclass(frozen=True)
class RiskFreeValidationReport:
    """Non-price metadata safe to record in the public repository."""

    rows: int
    first_date: str
    last_date: str
    missing_before_fill: int
    longest_gap_filled: int
    minimum_quote: float
    maximum_quote: float
    content_sha256: str


def fetch_irx_quotes() -> pd.Series:
    """Download daily ^IRX quotes under explicit, reproducible parameters.

    Unlike the ETF request, ``auto_adjust`` and ``repair`` are off: ^IRX is
    a quoted yield with no splits or distributions to adjust for, and the
    price-repair heuristics are built for tradable prices, not yields. The
    raw Close quote is exactly the contract's named input.
    """

    raw = yf.download(
        tickers=[RISK_FREE_TICKER],
        start=DATA_START,
        end=DATA_END_EXCLUSIVE,
        interval="1d",
        auto_adjust=False,
        actions=False,
        repair=False,
        group_by="column",
        progress=False,
        threads=False,
        multi_level_index=True,
        timeout=30,
    )
    return extract_quote_series(raw)


def extract_quote_series(raw: pd.DataFrame) -> pd.Series:
    """Extract the ordered ^IRX Close quote from supported yfinance layouts."""

    if raw.empty:
        raise DataValidationError("The provider returned an empty ^IRX dataset.")

    if isinstance(raw.columns, pd.MultiIndex):
        level_zero = set(raw.columns.get_level_values(0))
        level_one = set(raw.columns.get_level_values(1))
        if "Close" in level_zero:
            close = raw.xs("Close", axis=1, level=0, drop_level=True)
        elif "Close" in level_one:
            close = raw.xs("Close", axis=1, level=1, drop_level=True)
        else:
            raise DataValidationError("The ^IRX response has no Close field.")
        if close.shape[1] != 1:
            raise DataValidationError(
                f"Expected a single ^IRX column, received {list(close.columns)}."
            )
        quotes = close.iloc[:, 0]
    else:
        if "Close" not in raw.columns:
            raise DataValidationError("The ^IRX response has no Close field.")
        quotes = raw["Close"]

    quotes = pd.to_numeric(quotes, errors="coerce")
    quotes.index = (
        pd.to_datetime(quotes.index, utc=True).tz_convert(None).normalize()
    )
    quotes.index.name = "date"
    quotes.name = RISK_FREE_TICKER
    return quotes.sort_index()


def validate_and_fill(
    quotes: pd.Series,
    trading_days: pd.DatetimeIndex,
) -> tuple[pd.Series, RiskFreeValidationReport]:
    """Align quotes to the ETF trading calendar and apply the clause-5 fill.

    The ETF dataset's common dates define what a trading day is. A quote on
    a day outside that calendar is unused; a trading day with no finite
    quote is a gap. Gaps are forward-filled from the most recent prior
    trading day only, because that is the only repair that uses strictly
    past information. A leading gap has no past to carry forward, and a gap
    longer than the contract limit would turn "the rate did not move" from
    a one-day approximation into a sustained fiction, so both fail closed.
    """

    if not isinstance(quotes.index, pd.DatetimeIndex):
        raise DataValidationError("^IRX quote index must be a DatetimeIndex.")
    if quotes.index.has_duplicates:
        raise DataValidationError("^IRX quote index contains duplicate dates.")
    if not quotes.index.is_monotonic_increasing:
        raise DataValidationError("^IRX quote index is not monotonically increasing.")
    if not isinstance(trading_days, pd.DatetimeIndex) or len(trading_days) == 0:
        raise DataValidationError("The trading calendar is missing or empty.")

    numeric = pd.to_numeric(quotes, errors="coerce")
    finite = numeric[
        numeric.notna()
        & numeric.ne(float("inf"))
        & numeric.ne(-float("inf"))
    ]
    if finite.empty:
        raise DataValidationError("The ^IRX series contains no finite quotes.")

    minimum_quote = float(finite.min())
    maximum_quote = float(finite.max())
    if minimum_quote < MIN_RISK_FREE_QUOTE or maximum_quote > MAX_RISK_FREE_QUOTE:
        raise DataValidationError(
            "A ^IRX quote breaches the plausibility bounds "
            f"[{MIN_RISK_FREE_QUOTE}, {MAX_RISK_FREE_QUOTE}]: observed range "
            f"[{minimum_quote}, {maximum_quote}]. Investigate the data; do not "
            "widen the bounds to make it pass."
        )

    aligned = finite.reindex(trading_days)
    missing_mask = aligned.isna()
    missing_before_fill = int(missing_mask.sum())

    if bool(missing_mask.iloc[0]):
        raise DataValidationError(
            "The first trading day has no ^IRX quote and no prior observation "
            "to carry forward."
        )

    # Consecutive missing runs: each observed day increments the group id, so
    # every gap shares one id and its length is the group's missing count.
    gap_groups = (~missing_mask).cumsum()
    longest_gap = int(missing_mask.groupby(gap_groups).sum().max())
    if longest_gap > MAX_RISK_FREE_GAP_TRADING_DAYS:
        raise DataValidationError(
            f"A ^IRX gap spans {longest_gap} consecutive trading days, "
            f"exceeding the contract limit of "
            f"{MAX_RISK_FREE_GAP_TRADING_DAYS}."
        )

    filled = aligned.ffill()
    filled.name = RISK_FREE_TICKER
    report = RiskFreeValidationReport(
        rows=len(filled),
        first_date=filled.index.min().date().isoformat(),
        last_date=filled.index.max().date().isoformat(),
        missing_before_fill=missing_before_fill,
        longest_gap_filled=longest_gap,
        minimum_quote=minimum_quote,
        maximum_quote=maximum_quote,
        content_sha256=content_sha256(filled.to_frame()),
    )
    return filled, report


def daily_risk_free_rates(filled_quotes: pd.Series) -> pd.Series:
    """Contract clause 4: daily rate = (annualized percent quote / 100) / 252.

    Example with pencil arithmetic: a quote of 5.04 means 5.04% per year,
    so the decimal annual rate is 0.0504 and the daily rate is
    0.0504 / 252 = 0.0002.
    """

    rates = (filled_quotes / 100.0) / TRADING_DAYS_PER_YEAR
    rates.name = "daily_risk_free"
    return rates


def build_risk_free_section(
    report: RiskFreeValidationReport,
    *,
    retrieved_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the manifest's fourth-series entry without embedding quotes."""

    return {
        "ticker": RISK_FREE_TICKER,
        "field": "raw daily Close quote, annualized percent",
        "daily_rate_convention": "(quote / 100) / 252",
        "gap_policy": (
            "forward-fill from the most recent prior trading day; a gap over "
            f"{MAX_RISK_FREE_GAP_TRADING_DAYS} consecutive trading days or a "
            "missing leading value fails validation"
        ),
        "retrieved_at_utc": retrieved_at_utc or datetime.now(UTC).isoformat(),
        "request": {
            "start_inclusive": DATA_START,
            "end_exclusive": DATA_END_EXCLUSIVE,
            "interval": "1d",
            "auto_adjust": False,
            "repair": False,
            "threads": False,
        },
        "validation": asdict(report),
    }


def prepare_risk_free(
    repo_root: Path,
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Validate the ^IRX series and extend the manifest with the fourth series.

    The ETF dataset must already exist: its common dates are the trading
    calendar the risk-free series is aligned to. Raw quotes are cached
    locally and, like the ETF cache, are revalidated end to end on every
    run rather than trusted blindly.
    """

    price_cache_path = repo_root / "data" / "cache" / "adjusted_close.parquet"
    quote_cache_path = repo_root / "data" / "cache" / "irx_quotes.parquet"
    manifest_path = repo_root / "artifacts" / "data_manifest.json"

    if not price_cache_path.exists():
        raise DataValidationError(
            "The ETF price cache does not exist yet. Run the data module "
            "first; the risk-free series aligns to its trading calendar."
        )
    if not manifest_path.exists():
        raise DataValidationError(
            "artifacts/data_manifest.json does not exist yet. Run the data "
            "module first so the risk-free entry extends a real manifest."
        )

    prices = pd.read_parquet(price_cache_path)
    trading_days = pd.DatetimeIndex(pd.to_datetime(prices.index), name="date")

    fetched_from_network = force_refresh or not quote_cache_path.exists()
    if not fetched_from_network:
        cached = pd.read_parquet(quote_cache_path)
        quotes = cached.iloc[:, 0]
        quotes.index = pd.to_datetime(cached.index)
        quotes.index.name = "date"
        quotes.name = RISK_FREE_TICKER
    else:
        quotes = fetch_irx_quotes()

    filled, report = validate_and_fill(quotes, trading_days)

    quote_cache_path.parent.mkdir(parents=True, exist_ok=True)
    quotes.to_frame().to_parquet(quote_cache_path, index=True)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    retrieved_at_utc: str | None = None
    if not fetched_from_network:
        # Preserve the actual retrieval time when revalidating an unchanged
        # cache; recording the run time would misstate data provenance.
        retrieved_at_utc = manifest.get("risk_free", {}).get("retrieved_at_utc")
    manifest["risk_free"] = build_risk_free_section(
        report,
        retrieved_at_utc=retrieved_at_utc,
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    """Run the risk-free data milestone and print metadata only."""

    parser = argparse.ArgumentParser(
        description="Fetch and validate the preregistered ^IRX risk-free series."
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Ignore the local cache and download a fresh copy.",
    )
    args = parser.parse_args()

    manifest = prepare_risk_free(
        repository_root(),
        force_refresh=args.force_refresh,
    )
    validation = manifest["risk_free"]["validation"]
    print("Risk-free data milestone: PASS")
    print(f"Rows: {validation['rows']}")
    print(
        "Coverage: "
        f"{validation['first_date']} through {validation['last_date']}"
    )
    print(f"Trading days forward-filled: {validation['missing_before_fill']}")
    print(f"Longest gap filled: {validation['longest_gap_filled']}")
    print(f"Content SHA-256: {validation['content_sha256']}")
    print("No strategy or benchmark performance was calculated.")


if __name__ == "__main__":
    main()
