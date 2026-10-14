"""Locked-test runner (2021-01-01 through 2025-12-31) under contract v0.2.3.

This module implements ``locked_test_procedure.md``. It computes the six
frozen metrics for both strategies and both benchmarks on the LOCKED TEST
PERIOD ONLY, prints three labeled tables (primary 10 bps first, then the
5 and 20 bps labeled sensitivities), and evaluates the four preregistered
hypotheses mechanically on the primary table.

It was added after the freeze commit ``98a9821`` under freeze item 5:
the locked-test session may ADD the procedure, this runner, and its tests,
and may edit nothing that already existed.

Fences, mirroring ``validate.py``:

- Both window edges come from the frozen config and are hard-coded here.
  No flag, parameter, or argument moves either edge.
- END FENCE: prices are sliced on or before ``TEST_END`` first and the
  slice is verified.
- START FENCE: no measured return before ``TEST_START`` enters a metric.
  Pre-2021 prices are trailing lookback input only.
- WINDOW IDENTITY: all four portfolios share one measured-return index.

The frozen portfolio engine and metrics module reject every date on or
after ``TEST_START`` through a module-level constant. Editing them is
forbidden, so ``lifted_engine_guard`` rebinds that constant to the data
end inside a context manager and restores it on exit, including on error.
Every number is produced by the unchanged frozen functions.

On real data, ``main`` refuses to run unless the logged unlock file
exists, refuses to run a second time once the output file exists, and
halts if either cached series does not match the content hash pinned in
the manifest (freeze item 7). It reads local caches only and never
downloads.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from treasury_rotation import metrics as _metrics_module
from treasury_rotation import portfolio as _portfolio_module
from treasury_rotation.config import (
    CONTRACT_VERSION,
    DATA_END_EXCLUSIVE,
    PRIMARY_COST_BPS,
    SENSITIVITY_COSTS_BPS,
    TEST_END,
    TEST_START,
)
from treasury_rotation.data import (
    DataValidationError,
    repository_root,
    validate_adjusted_close,
)
from treasury_rotation.metrics import summarize_performance
from treasury_rotation.portfolio import (
    calculate_returns,
    run_buy_and_hold_ief,
    run_quarterly_equal_weight,
)
from treasury_rotation.riskfree import (
    RISK_FREE_TICKER,
    daily_risk_free_rates,
    validate_and_fill,
)
from treasury_rotation.signals import run_phase1, run_phase2

# The fences. Both edges come from the frozen config.
TEST_WINDOW_START = pd.Timestamp(TEST_START)
TEST_BOUNDARY = pd.Timestamp(TEST_END)

# Where the engine guard is moved while the locked test runs: the first
# date after the research range, so no cached date can trip it.
GUARD_LIFT_DATE = DATA_END_EXCLUSIVE

# The only cost assumptions this runner evaluates.
ALLOWED_COST_BPS = (PRIMARY_COST_BPS,) + tuple(SENSITIVITY_COSTS_BPS)

UNLOCK_LOG_NAME = "LOCKED_TEST_UNLOCK.md"
OUTPUT_RELATIVE_PATH = Path("artifacts") / "locked_test_output.txt"

PORTFOLIO_LABELS = (
    "phase1_momentum",
    "phase2_risk_adjusted",
    "buy_and_hold_ief",
    "equal_weight_quarterly",
)

_GUARDED_MODULES = (_portfolio_module, _metrics_module)


class LockedTestBoundaryError(DataValidationError):
    """Raised when data crosses either edge of the locked test window."""


class LockedTestUnlockError(DataValidationError):
    """Raised when the run is attempted without the logged unlock."""


class LockedTestAlreadyRunError(DataValidationError):
    """Raised when the output file exists: the locked test runs once."""


class PinnedDataMismatchError(DataValidationError):
    """Raised when a cached series does not match its pinned content hash."""


@dataclass(frozen=True)
class LockedTestResult:
    """One cost level's output: the six metrics for each portfolio."""

    window_start: pd.Timestamp
    window_end: pd.Timestamp
    measured_days: int
    cost_bps: int
    metrics: dict[str, dict[str, float]]


@dataclass(frozen=True)
class HypothesisOutcome:
    """One preregistered hypothesis, evaluated on the primary table."""

    number: int
    name: str
    comparison: str
    supported: bool


@contextmanager
def lifted_engine_guard() -> Iterator[None]:
    """Temporarily move the frozen engine's locked-period guard.

    The guard reads a module-level ``TEST_START`` at call time. Rebinding
    it here lifts the guard for the duration of the block without editing
    a frozen file. The original value is always restored.
    """

    saved = {module: module.TEST_START for module in _GUARDED_MODULES}
    try:
        for module in _GUARDED_MODULES:
            module.TEST_START = GUARD_LIFT_DATE
        yield
    finally:
        for module, value in saved.items():
            module.TEST_START = value


def locked_test_slice(prices: pd.DataFrame) -> pd.DataFrame:
    """Return only the price rows on or before the locked-test boundary."""

    sliced = prices.loc[prices.index <= TEST_BOUNDARY]
    if sliced.empty:
        raise LockedTestBoundaryError(
            "No price rows fall on or before the locked-test boundary."
        )
    if sliced.index.max() > TEST_BOUNDARY:
        raise LockedTestBoundaryError(
            "A post-boundary date survived the locked-test slice."
        )
    if not (sliced.index >= TEST_WINDOW_START).any():
        raise LockedTestBoundaryError(
            "No price rows fall inside the locked-test window."
        )
    return sliced


def locked_test_review(
    prices: pd.DataFrame,
    quotes: pd.Series,
    *,
    cost_bps: int = PRIMARY_COST_BPS,
) -> LockedTestResult:
    """Compute all six metrics for all four portfolios, locked test only.

    Mirrors ``validate.robustness_review`` with the locked-test edges. The
    strategies are simulated over the full pre-boundary history so the
    position entering 2021 is the one selected at the last qualifying
    decision of 2020; because costs are proportional, in-window net
    returns equal those of a trader who installed that position free at
    the window start.
    """

    if cost_bps not in ALLOWED_COST_BPS:
        raise DataValidationError(
            f"{cost_bps} bps is not a contract cost assumption. The "
            f"permitted levels are {sorted(ALLOWED_COST_BPS)}."
        )

    fenced_prices = locked_test_slice(prices)

    with lifted_engine_guard():
        phase1_decisions, phase1_sim = run_phase1(
            fenced_prices, cost_bps=cost_bps
        )
        _phase2_decisions, phase2_sim = run_phase2(
            fenced_prices, cost_bps=cost_bps
        )

        if not (phase1_decisions.targets.index < TEST_WINDOW_START).any():
            raise LockedTestBoundaryError(
                "No qualifying decision date precedes the locked-test "
                "window; the pre-2021 trailing history is missing."
            )

        asset_returns = calculate_returns(fenced_prices)
        measured_returns = asset_returns.loc[
            asset_returns.index >= TEST_WINDOW_START
        ]
        if measured_returns.empty:
            raise LockedTestBoundaryError(
                "No measured returns exist inside the locked-test window."
            )

        ief_sim = run_buy_and_hold_ief(measured_returns, cost_bps=cost_bps)
        equal_weight_sim = run_quarterly_equal_weight(
            measured_returns, cost_bps=cost_bps
        )

        window_tables: dict[str, pd.DataFrame] = {
            "phase1_momentum": phase1_sim.daily.loc[
                phase1_sim.daily.index >= TEST_WINDOW_START
            ],
            "phase2_risk_adjusted": phase2_sim.daily.loc[
                phase2_sim.daily.index >= TEST_WINDOW_START
            ],
            "buy_and_hold_ief": ief_sim.daily,
            "equal_weight_quarterly": equal_weight_sim.daily,
        }

        expected_index = measured_returns.index
        for label, table in window_tables.items():
            if not table.index.equals(expected_index):
                raise LockedTestBoundaryError(
                    f"The {label} window differs from the shared "
                    "measured-return window."
                )
        if expected_index[-1] > TEST_BOUNDARY:
            raise LockedTestBoundaryError(
                "The measured-return window ends past the boundary."
            )

        trading_days = pd.DatetimeIndex(fenced_prices.index, name="date")
        filled_quotes, _report = validate_and_fill(quotes, trading_days)
        measured_risk_free = daily_risk_free_rates(filled_quotes).loc[
            expected_index
        ]

        results = {
            label: summarize_performance(table, measured_risk_free)
            for label, table in window_tables.items()
        }

    return LockedTestResult(
        window_start=expected_index[0],
        window_end=expected_index[-1],
        measured_days=len(expected_index),
        cost_bps=cost_bps,
        metrics=results,
    )


def evaluate_hypotheses(primary: LockedTestResult) -> list[HypothesisOutcome]:
    """Score the four contract hypotheses on the primary table.

    Strict inequalities, as preregistered: a tie is not supported.
    """

    if primary.cost_bps != PRIMARY_COST_BPS:
        raise DataValidationError(
            "Hypotheses are evaluated on the primary cost table only."
        )
    m = primary.metrics
    p1_calmar = m["phase1_momentum"]["calmar_ratio"]
    p2_calmar = m["phase2_risk_adjusted"]["calmar_ratio"]
    ief_calmar = m["buy_and_hold_ief"]["calmar_ratio"]
    ew_calmar = m["equal_weight_quarterly"]["calmar_ratio"]
    p1_mdd = m["phase1_momentum"]["maximum_drawdown"]
    p2_mdd = m["phase2_risk_adjusted"]["maximum_drawdown"]
    ief_mdd = m["buy_and_hold_ief"]["maximum_drawdown"]

    return [
        HypothesisOutcome(
            1,
            "Phase 1 primary",
            (
                f"Phase 1 Calmar {p1_calmar:.3f} > Hold IEF {ief_calmar:.3f} "
                f"and > Eq weight {ew_calmar:.3f}"
            ),
            p1_calmar > ief_calmar and p1_calmar > ew_calmar,
        ),
        HypothesisOutcome(
            2,
            "Phase 1 secondary",
            (
                f"|Phase 1 max drawdown| {abs(p1_mdd):.2%} < "
                f"|Hold IEF max drawdown| {abs(ief_mdd):.2%}"
            ),
            abs(p1_mdd) < abs(ief_mdd),
        ),
        HypothesisOutcome(
            3,
            "Phase 2 incremental",
            f"Phase 2 Calmar {p2_calmar:.3f} > Phase 1 Calmar {p1_calmar:.3f}",
            p2_calmar > p1_calmar,
        ),
        HypothesisOutcome(
            4,
            "Phase 2 secondary",
            (
                f"|Phase 2 max drawdown| {abs(p2_mdd):.2%} < "
                f"|Phase 1 max drawdown| {abs(p1_mdd):.2%}"
            ),
            abs(p2_mdd) < abs(p1_mdd),
        ),
    ]


def format_report(result: LockedTestResult) -> str:
    """Render one cost level as a fixed-width table plus window metadata."""

    percent_metrics = {"cagr", "annualized_volatility", "maximum_drawdown"}
    metric_rows = (
        ("cagr", "CAGR"),
        ("annualized_volatility", "Annualized volatility"),
        ("sharpe_ratio", "Sharpe ratio"),
        ("maximum_drawdown", "Maximum drawdown"),
        ("calmar_ratio", "Calmar ratio"),
        ("annual_turnover", "Annual turnover"),
    )
    column_labels = {
        "phase1_momentum": "Phase 1",
        "phase2_risk_adjusted": "Phase 2",
        "buy_and_hold_ief": "Hold IEF",
        "equal_weight_quarterly": "Eq weight",
    }
    cost_label = (
        "PRIMARY" if result.cost_bps == PRIMARY_COST_BPS else "LABELED SENSITIVITY"
    )
    lines = [
        "Locked-test evaluation: PASS",
        f"Contract version: {CONTRACT_VERSION}",
        (
            "Locked test period: "
            f"{TEST_WINDOW_START.date().isoformat()} through "
            f"{TEST_BOUNDARY.date().isoformat()}"
        ),
        (
            "Measured-return window: "
            f"{result.window_start.date().isoformat()} through "
            f"{result.window_end.date().isoformat()} "
            f"({result.measured_days} trading days, identical for all four "
            "portfolios)"
        ),
        f"Transaction costs: {result.cost_bps} bps per dollar traded [{cost_label}]",
        f"Risk-free series: {RISK_FREE_TICKER}",
        (
            "Pre-2021 prices entered as trailing lookback input only; no "
            "pre-2021 return was measured."
        ),
        "",
    ]
    header = f"{'Metric':<22}" + "".join(
        f"{column_labels[label]:>12}" for label in PORTFOLIO_LABELS
    )
    lines.append(header)
    lines.append("-" * len(header))
    for key, display in metric_rows:
        cells = []
        for label in PORTFOLIO_LABELS:
            value = result.metrics[label][key]
            cells.append(
                f"{value:>12.2%}" if key in percent_metrics else f"{value:>12.3f}"
            )
        lines.append(f"{display:<22}" + "".join(cells))
    return "\n".join(lines)


def format_hypotheses(outcomes: list[HypothesisOutcome]) -> str:
    """Render the four hypothesis outcomes, one line each."""

    lines = ["Preregistered hypotheses, primary 10 bps table:"]
    for outcome in outcomes:
        verdict = "SUPPORTED" if outcome.supported else "NOT SUPPORTED"
        lines.append(
            f"  H{outcome.number} {outcome.name}: {outcome.comparison} -> "
            f"{verdict}"
        )
    return "\n".join(lines)


def verify_pinned_data(
    raw_prices: pd.DataFrame,
    raw_quotes: pd.Series,
    manifest: dict,
) -> tuple[pd.DataFrame, pd.Series]:
    """Recompute both content hashes and halt on any mismatch (freeze item 7).

    Uses the existing validation functions, so the hash is computed exactly
    the way the manifest's hash was.
    """

    prices, price_report = validate_adjusted_close(raw_prices)
    pinned_prices = manifest["validation"]["content_sha256"]
    if price_report.content_sha256 != pinned_prices:
        raise PinnedDataMismatchError(
            "The ETF price cache does not match the pinned content hash "
            f"{pinned_prices[:8]}... This halts the session as a reportable "
            "blocker. Do not re-fetch."
        )

    trading_days = pd.DatetimeIndex(prices.index, name="date")
    _filled, quote_report = validate_and_fill(raw_quotes, trading_days)
    pinned_quotes = manifest["risk_free"]["validation"]["content_sha256"]
    if quote_report.content_sha256 != pinned_quotes:
        raise PinnedDataMismatchError(
            "The ^IRX cache does not match the pinned content hash "
            f"{pinned_quotes[:8]}... This halts the session as a reportable "
            "blocker. Do not re-fetch."
        )
    return prices, raw_quotes


def _load_caches(repo_root: Path) -> tuple[pd.DataFrame, pd.Series, dict]:
    price_cache_path = repo_root / "data" / "cache" / "adjusted_close.parquet"
    quote_cache_path = repo_root / "data" / "cache" / "irx_quotes.parquet"
    manifest_path = repo_root / "artifacts" / "data_manifest.json"
    for path in (price_cache_path, quote_cache_path, manifest_path):
        if not path.exists():
            raise DataValidationError(f"Required local file is missing: {path}")

    prices = pd.read_parquet(price_cache_path)
    prices.index = pd.to_datetime(prices.index)
    prices.index.name = "date"

    cached_quotes = pd.read_parquet(quote_cache_path)
    quotes = cached_quotes.iloc[:, 0]
    quotes.index = pd.to_datetime(cached_quotes.index)
    quotes.index.name = "date"
    quotes.name = RISK_FREE_TICKER

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return prices, quotes, manifest


def run_locked_test(prices: pd.DataFrame, quotes: pd.Series) -> str:
    """Produce the complete preregistered output text."""

    sections = []
    primary: LockedTestResult | None = None
    for cost_bps in (PRIMARY_COST_BPS, *SENSITIVITY_COSTS_BPS):
        result = locked_test_review(prices, quotes, cost_bps=cost_bps)
        if cost_bps == PRIMARY_COST_BPS:
            primary = result
        sections.append(format_report(result))
    assert primary is not None
    sections.append(format_hypotheses(evaluate_hypotheses(primary)))
    sections.append(
        "Sensitivity policy: the 5 and 20 bps tables are labeled "
        "sensitivities and cannot replace the primary 10 bps results.\n"
        "This was the contract's one evaluation of 2021-2025. It does not "
        "repeat."
    )
    return "\n\n".join(sections) + "\n"


def main(repo_root: Path | None = None) -> None:
    """Gate on the logged unlock, verify pinned data, run once, record."""

    root = repo_root if repo_root is not None else repository_root()
    if not (root / UNLOCK_LOG_NAME).exists():
        raise LockedTestUnlockError(
            f"{UNLOCK_LOG_NAME} does not exist. Opening 2021-2025 is a "
            "one-way event and must be logged before the run."
        )
    output_path = root / OUTPUT_RELATIVE_PATH
    if output_path.exists():
        raise LockedTestAlreadyRunError(
            f"{OUTPUT_RELATIVE_PATH.as_posix()} already exists. The locked "
            "test runs once."
        )

    raw_prices, raw_quotes, manifest = _load_caches(root)
    prices, quotes = verify_pinned_data(raw_prices, raw_quotes, manifest)

    text = run_locked_test(prices, quotes)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print(text, end="")


if __name__ == "__main__":
    main()
