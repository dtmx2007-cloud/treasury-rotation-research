"""Fetch, validate, cache, and fingerprint the preregistered price dataset.

This module intentionally contains no strategy or benchmark implementation.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

from treasury_rotation.config import (
    CONTRACT_VERSION,
    DATA_END_EXCLUSIVE,
    DATA_START,
    EARLIEST_ACCEPTABLE_LAST_DATE,
    LATEST_ACCEPTABLE_FIRST_DATE,
    MAX_ABSOLUTE_DAILY_RETURN,
    MAX_MISSING_FRACTION,
    MIN_COMMON_ROWS,
    TICKERS,
)


class DataValidationError(ValueError):
    """Raised when downloaded data violates the frozen integrity contract."""


@dataclass(frozen=True)
class ValidationReport:
    """Non-price metadata safe to record in the public repository."""

    rows: int
    first_date: str
    last_date: str
    missing_by_ticker: dict[str, int]
    maximum_missing_fraction: float
    maximum_absolute_daily_return: float
    content_sha256: str


def fetch_adjusted_close() -> pd.DataFrame:
    """Download adjusted daily closes under the frozen provider parameters.

    ``yfinance`` treats ``end`` as exclusive. ``auto_adjust=True`` makes the
    returned Close field reflect splits and distributions, so price changes
    represent investor returns more faithfully than an unadjusted close.
    """

    # Keep request settings explicit so another researcher can reproduce the
    # provider call rather than inherit changing library defaults.
    raw = yf.download(
        tickers=list(TICKERS),
        start=DATA_START,
        end=DATA_END_EXCLUSIVE,
        interval="1d",
        auto_adjust=True,
        actions=False,
        repair=True,
        group_by="column",
        progress=False,
        threads=False,
        multi_level_index=True,
        timeout=30,
    )
    return extract_adjusted_close(raw)


def extract_adjusted_close(raw: pd.DataFrame) -> pd.DataFrame:
    """Extract ordered adjusted closes from supported yfinance column layouts."""

    if raw.empty:
        raise DataValidationError("The provider returned an empty dataset.")

    if isinstance(raw.columns, pd.MultiIndex):
        level_zero = set(raw.columns.get_level_values(0))
        level_one = set(raw.columns.get_level_values(1))
        if "Close" in level_zero:
            close = raw.xs("Close", axis=1, level=0, drop_level=True)
        elif "Close" in level_one:
            close = raw.xs("Close", axis=1, level=1, drop_level=True)
        else:
            raise DataValidationError("The provider response has no Close field.")
    else:
        if len(TICKERS) != 1 or "Close" not in raw.columns:
            raise DataValidationError(
                "Expected multi-symbol Close columns from the provider."
            )
        close = raw[["Close"]].rename(columns={"Close": TICKERS[0]})

    close.columns = [str(column).upper() for column in close.columns]
    missing_columns = sorted(set(TICKERS) - set(close.columns))
    if missing_columns:
        raise DataValidationError(
            f"Provider response is missing tickers: {', '.join(missing_columns)}."
        )

    close = close.loc[:, list(TICKERS)].copy()
    close.index = pd.to_datetime(close.index, utc=True).tz_convert(None).normalize()
    close.index.name = "date"
    close = close.apply(pd.to_numeric, errors="coerce").sort_index()
    return close


def validate_adjusted_close(
    prices: pd.DataFrame,
) -> tuple[pd.DataFrame, ValidationReport]:
    """Validate integrity and return complete common-date observations.

    Malformed or non-finite values count as missing before any rows are removed.
    The returned table retains only dates on which all three ETFs have valid
    prices. Prices are never forward-filled or otherwise invented.
    """

    expected_columns = list(TICKERS)
    if list(prices.columns) != expected_columns:
        raise DataValidationError(
            f"Expected columns {expected_columns}, received {list(prices.columns)}."
        )
    if not isinstance(prices.index, pd.DatetimeIndex):
        raise DataValidationError("Price index must be a DatetimeIndex.")
    if prices.index.has_duplicates:
        raise DataValidationError("Price index contains duplicate dates.")
    if not prices.index.is_monotonic_increasing:
        raise DataValidationError("Price index is not monotonically increasing.")
    if (prices.index.dayofweek > 4).any():
        raise DataValidationError("Price index contains a weekend observation.")

    # Coerce malformed provider values to missing so they are measured by the
    # same explicit missing-data policy as NaN and infinity.
    numeric = prices.apply(pd.to_numeric, errors="coerce")
    finite_mask = (
        numeric.notna()
        & numeric.ne(float("inf"))
        & numeric.ne(-float("inf"))
    )
    missing_by_ticker = {
        ticker: int((~finite_mask[ticker]).sum()) for ticker in TICKERS
    }
    maximum_missing_fraction = max(missing_by_ticker.values()) / len(numeric)
    if maximum_missing_fraction > MAX_MISSING_FRACTION:
        raise DataValidationError(
            "Missing or non-finite observations exceed the allowed fraction: "
            f"{maximum_missing_fraction:.4%} > {MAX_MISSING_FRACTION:.4%}."
        )

    # Keep only common dates. Forward-filling would quietly create prices that
    # were not actually observed and could alter signals or returns.
    complete = numeric.where(finite_mask).dropna(how="any")
    if len(complete) < MIN_COMMON_ROWS:
        raise DataValidationError(
            f"Only {len(complete)} complete rows; expected at least {MIN_COMMON_ROWS}."
        )
    if (complete <= 0).any(axis=None):
        raise DataValidationError("Prices must all be strictly positive.")

    first_date = complete.index.min()
    last_date = complete.index.max()
    if first_date > pd.Timestamp(LATEST_ACCEPTABLE_FIRST_DATE):
        raise DataValidationError(
            f"Coverage starts too late: {first_date.date().isoformat()}."
        )
    if last_date < pd.Timestamp(EARLIEST_ACCEPTABLE_LAST_DATE):
        raise DataValidationError(
            f"Coverage ends too early: {last_date.date().isoformat()}."
        )

    # This threshold is an alarm, not a winsorization rule: an unusually large
    # adjusted-price move stops the run for investigation instead of being
    # clipped, deleted, or treated as an unfavorable result to hide.
    daily_returns = complete.pct_change(fill_method=None).dropna(how="all")
    maximum_absolute_daily_return = float(daily_returns.abs().max().max())
    if maximum_absolute_daily_return > MAX_ABSOLUTE_DAILY_RETURN:
        raise DataValidationError(
            "A daily adjusted-price move exceeds the integrity threshold: "
            f"{maximum_absolute_daily_return:.2%}."
        )

    report = ValidationReport(
        rows=len(complete),
        first_date=first_date.date().isoformat(),
        last_date=last_date.date().isoformat(),
        missing_by_ticker=missing_by_ticker,
        maximum_missing_fraction=maximum_missing_fraction,
        maximum_absolute_daily_return=maximum_absolute_daily_return,
        content_sha256=content_sha256(complete),
    )
    return complete, report


def content_sha256(prices: pd.DataFrame) -> str:
    """Hash a stable text serialization rather than a provider-specific file."""

    serialized = prices.to_csv(
        date_format="%Y-%m-%d",
        float_format="%.10f",
        lineterminator="\n",
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def file_sha256(path: Path) -> str:
    """Return the SHA-256 digest of a local file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(
    report: ValidationReport,
    contract_path: Path,
    *,
    retrieved_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build provenance metadata without embedding market prices."""

    return {
        "contract_version": CONTRACT_VERSION,
        "contract_sha256": file_sha256(contract_path),
        "retrieved_at_utc": retrieved_at_utc or datetime.now(UTC).isoformat(),
        "provider": "Yahoo Finance via yfinance",
        "provider_usage": "personal educational research; raw prices not distributed",
        "tickers": list(TICKERS),
        "field": "auto-adjusted daily close",
        "request": {
            "start_inclusive": DATA_START,
            "end_exclusive": DATA_END_EXCLUSIVE,
            "interval": "1d",
            "auto_adjust": True,
            "repair": True,
            "threads": False,
        },
        "packages": {
            "pandas": importlib.metadata.version("pandas"),
            "pyarrow": importlib.metadata.version("pyarrow"),
            "scipy": importlib.metadata.version("scipy"),
            "yfinance": importlib.metadata.version("yfinance"),
        },
        "validation": asdict(report),
    }


def prepare_dataset(
    repository_root: Path,
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Validate prices and persist a private cache plus public-safe manifest.

    The cache stores adjusted prices locally, while the manifest stores only
    provenance, validation statistics, package versions, and fingerprints.
    ``force_refresh=True`` bypasses the cache and performs a fresh download.
    """

    cache_path = repository_root / "data" / "cache" / "adjusted_close.parquet"
    manifest_path = repository_root / "artifacts" / "data_manifest.json"
    contract_path = repository_root / "research_contract.md"

    fetched_from_network = force_refresh or not cache_path.exists()
    if not fetched_from_network:
        # A cache avoids unnecessary downloads but is never trusted blindly:
        # every run sends cached prices through the complete validation path.
        prices = pd.read_parquet(cache_path)
        prices.index = pd.to_datetime(prices.index)
        prices.index.name = "date"
    else:
        prices = fetch_adjusted_close()

    complete, report = validate_adjusted_close(prices)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    complete.to_parquet(cache_path, index=True)

    retrieved_at_utc: str | None = None
    if not fetched_from_network and manifest_path.exists():
        # Preserve the actual retrieval time when revalidating an unchanged
        # cache; recording the current run time would misstate data provenance.
        existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        retrieved_at_utc = existing_manifest.get("retrieved_at_utc")
    manifest = build_manifest(
        report,
        contract_path,
        retrieved_at_utc=retrieved_at_utc,
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def repository_root() -> Path:
    """Locate the repository root from the installed source tree."""

    return Path(__file__).resolve().parents[2]


def main() -> None:
    """Run the data-integrity milestone and print metadata only."""

    parser = argparse.ArgumentParser(
        description="Fetch and validate the preregistered price dataset."
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Ignore the local cache and download a fresh copy.",
    )
    args = parser.parse_args()

    manifest = prepare_dataset(
        repository_root(),
        force_refresh=args.force_refresh,
    )
    validation = manifest["validation"]
    print("Data integrity milestone: PASS")
    print(f"Rows: {validation['rows']}")
    print(
        "Coverage: "
        f"{validation['first_date']} through {validation['last_date']}"
    )
    print(f"Content SHA-256: {validation['content_sha256']}")
    print("No strategy or benchmark performance was calculated.")


if __name__ == "__main__":
    main()
