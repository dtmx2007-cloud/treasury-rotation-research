"""Validation-period robustness review runner under research contract v0.2.3.

This module computes the six frozen metrics for both strategies and both
benchmarks on the VALIDATION PERIOD ONLY: 2016-01-01 through 2020-12-31.
It implements the procedure preregistered in ``validation_procedure.md``
and honors ``VALIDATION_PRECOMMITMENT.md``: the contract permits exactly
ONE robustness review of this period, and these preregistered outputs are
the look.

Both edges of the window are hard-coded on purpose. There is no
parameter, flag, or argument that moves either boundary, because the
moment a window becomes an input, a curious researcher can "just check"
something else. The fences:

- END FENCE (precommitment promise 5): no price or quote observation
  after ``VALIDATION_END`` may reach a signal, a portfolio, or a metric.
  The runner slices first and verifies the slice, so the locked 2021-2025
  test period never produces a number.
- START FENCE: no measured return before ``VALIDATION_START`` may enter
  any metric. Pre-2016 prices are trailing lookback fuel only — on every
  decision date they already existed — mirroring how a live trader
  entering 2016 would have held 2015 data in the lookback.

Initial allocation (procedure, measured-window clause 3): the position
held entering the window is the selection made at the last qualifying
weekly decision date before ``VALIDATION_START`` under the standard
frozen rules. Because the strategies hold exactly one ETF, that one-hot
position carries into the window unchanged. It is installed without cost
and contributes zero turnover: the trade that installed it was decided
and charged before the window, so no cost or turnover lands inside the
measured window — the contract's uncharged-initial-purchase convention.
The benchmarks are installed without cost at the window start and
evaluated over the identical measured-return window.

This module reads local caches only. It never downloads data.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from treasury_rotation.config import (
    CONTRACT_VERSION,
    PRIMARY_COST_BPS,
    SENSITIVITY_COSTS_BPS,
    VALIDATION_END,
    VALIDATION_START,
)
from treasury_rotation.data import DataValidationError, repository_root
from treasury_rotation.metrics import summarize_performance
from treasury_rotation.portfolio import (
    PortfolioSimulation,
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

# The fences. Both edges come from the frozen config, and nothing in this
# module accepts a different date from anywhere.
VALIDATION_WINDOW_START = pd.Timestamp(VALIDATION_START)
VALIDATION_BOUNDARY = pd.Timestamp(VALIDATION_END)

# The only cost assumptions this runner will evaluate: the primary 10 bps
# and the two contract-frozen sensitivities. An arbitrary cost level is a
# tunable parameter, and this project does not have tunable parameters.
ALLOWED_COST_BPS = (PRIMARY_COST_BPS,) + tuple(SENSITIVITY_COSTS_BPS)

PORTFOLIO_LABELS = (
    "phase1_momentum",
    "phase2_risk_adjusted",
    "buy_and_hold_ief",
    "equal_weight_quarterly",
)


class ValidationBoundaryError(DataValidationError):
    """Raised when data crosses either edge of the validation window."""


@dataclass(frozen=True)
class RobustnessReviewResult:
    """The complete review output: one metrics dict per portfolio.

    ``window_start`` and ``window_end`` bound the shared measured-return
    window; ``measured_days`` counts its trading days. ``metrics`` maps
    each portfolio label to its six frozen metrics.
    """

    window_start: pd.Timestamp
    window_end: pd.Timestamp
    measured_days: int
    cost_bps: int
    metrics: dict[str, dict[str, float]]


def validation_slice(prices: pd.DataFrame) -> pd.DataFrame:
    """Return only the price rows on or before the validation boundary.

    The rows that survive include pre-2016 history: signals may read it
    as trailing lookback input. The START fence is applied later, to
    measured returns, not to signal inputs.
    """

    sliced = prices.loc[prices.index <= VALIDATION_BOUNDARY]
    if sliced.empty:
        raise ValidationBoundaryError(
            "No price rows fall on or before the validation boundary."
        )
    # Belt and braces: the slice above makes this impossible, but if a
    # future edit ever breaks the fence, failing here beats reporting a
    # number computed on the locked test period.
    if sliced.index.max() > VALIDATION_BOUNDARY:
        raise ValidationBoundaryError(
            "A post-validation date survived the validation slice."
        )
    if not (sliced.index >= VALIDATION_WINDOW_START).any():
        raise ValidationBoundaryError(
            "No price rows fall inside the validation window."
        )
    return sliced


def _window_slice(daily: pd.DataFrame) -> pd.DataFrame:
    """Restrict a simulation's daily table to the measured-return window."""

    return daily.loc[daily.index >= VALIDATION_WINDOW_START]


def robustness_review(
    prices: pd.DataFrame,
    quotes: pd.Series,
    *,
    cost_bps: int = PRIMARY_COST_BPS,
) -> RobustnessReviewResult:
    """Compute all six metrics for all four portfolios, validation only.

    ``prices`` is the validated adjusted-close table (any range; it is
    fenced here) and ``quotes`` is the raw ^IRX quote series. Everything
    downstream shares one measured-return window, enforced by an explicit
    index-equality check rather than by trust.

    The strategies are simulated over the full pre-boundary history so
    that the position entering the window is exactly the one selected at
    the last qualifying decision before ``VALIDATION_START``. Because
    per-dollar costs are proportional, the daily net returns inside the
    window are identical to those of a trader who installed that same
    position cost-free at the window start; the pre-window simulation
    contributes no measured return, no in-window cost, and no in-window
    turnover.
    """

    if cost_bps not in ALLOWED_COST_BPS:
        raise DataValidationError(
            f"{cost_bps} bps is not a contract cost assumption. The "
            f"permitted levels are {sorted(ALLOWED_COST_BPS)}; costs are "
            "frozen, not tunable."
        )

    fenced_prices = validation_slice(prices)

    phase1_decisions, phase1_sim = run_phase1(fenced_prices, cost_bps=cost_bps)
    _phase2_decisions, phase2_sim = run_phase2(fenced_prices, cost_bps=cost_bps)

    # Procedure clause 3: the initial allocation must come from a decision
    # made BEFORE the window on data that already existed. If no decision
    # predates the window, the trailing history is missing and the review
    # cannot mirror a live trader entering 2016.
    if not (phase1_decisions.targets.index < VALIDATION_WINDOW_START).any():
        raise ValidationBoundaryError(
            "No qualifying decision date precedes the validation window; "
            "the pre-2016 trailing history is missing."
        )

    # START fence: measured returns begin on the first trading day of the
    # window. Pre-window returns exist in the simulations but are never
    # measured; they are discarded here, before any metric sees them.
    asset_returns = calculate_returns(fenced_prices)
    measured_returns = asset_returns.loc[
        asset_returns.index >= VALIDATION_WINDOW_START
    ]
    if measured_returns.empty:
        raise ValidationBoundaryError(
            "No measured returns exist inside the validation window."
        )

    ief_sim = run_buy_and_hold_ief(measured_returns, cost_bps=cost_bps)
    equal_weight_sim = run_quarterly_equal_weight(
        measured_returns, cost_bps=cost_bps
    )

    window_tables: dict[str, pd.DataFrame] = {
        "phase1_momentum": _window_slice(phase1_sim.daily),
        "phase2_risk_adjusted": _window_slice(phase2_sim.daily),
        "buy_and_hold_ief": ief_sim.daily,
        "equal_weight_quarterly": equal_weight_sim.daily,
    }

    # Window identity: all four portfolios share the exact same
    # measured-return index. Metrics on mismatched windows are not
    # comparable, so a mismatch raises instead of printing a table.
    expected_index = measured_returns.index
    for label, table in window_tables.items():
        if not table.index.equals(expected_index):
            raise ValidationBoundaryError(
                f"The {label} window differs from the shared measured-return "
                "window; metrics on mismatched windows are not comparable."
            )
    if expected_index[-1] > VALIDATION_BOUNDARY:
        raise ValidationBoundaryError(
            "The measured-return window ends past the validation boundary."
        )

    # The risk-free series aligns to the fenced trading calendar only, so
    # this call never touches a post-validation quote. The clause-5
    # forward-fill uses strictly prior days, so pre-window quotes may
    # legitimately fill an early-window gap.
    trading_days = pd.DatetimeIndex(fenced_prices.index, name="date")
    filled_quotes, _report = validate_and_fill(quotes, trading_days)
    measured_risk_free = daily_risk_free_rates(filled_quotes).loc[expected_index]

    metrics = {
        label: summarize_performance(table, measured_risk_free)
        for label, table in window_tables.items()
    }
    return RobustnessReviewResult(
        window_start=expected_index[0],
        window_end=expected_index[-1],
        measured_days=len(expected_index),
        cost_bps=cost_bps,
        metrics=metrics,
    )


def format_report(result: RobustnessReviewResult) -> str:
    """Render the review result as a fixed-width text table.

    These tables, plus the metadata lines, are the preregistered outputs:
    per ``VALIDATION_PRECOMMITMENT.md`` they ARE the one look.
    """

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
        "PRIMARY"
        if result.cost_bps == PRIMARY_COST_BPS
        else "LABELED SENSITIVITY"
    )
    lines = [
        "Validation-period robustness review: PASS",
        f"Contract version: {CONTRACT_VERSION}",
        (
            "Validation period: "
            f"{VALIDATION_WINDOW_START.date().isoformat()} through "
            f"{VALIDATION_BOUNDARY.date().isoformat()}"
        ),
        (
            "Measured-return window: "
            f"{result.window_start.date().isoformat()} through "
            f"{result.window_end.date().isoformat()} "
            f"({result.measured_days} trading days, identical for all four "
            "portfolios)"
        ),
        (
            f"Transaction costs: {result.cost_bps} bps per dollar traded "
            f"[{cost_label}]"
        ),
        f"Risk-free series: {RISK_FREE_TICKER}",
        (
            "Pre-2016 prices entered as trailing lookback input only; no "
            "pre-2016 return was measured."
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
            if key in percent_metrics:
                cells.append(f"{value:>12.2%}")
            else:
                cells.append(f"{value:>12.3f}")
        lines.append(f"{display:<22}" + "".join(cells))

    lines.append("")
    lines.append(
        "The locked test period (2021-2025) was not evaluated and remains "
        "sealed."
    )
    return "\n".join(lines)


def main() -> None:
    """Load local caches, run the one robustness review, print the tables."""

    repo_root = repository_root()
    price_cache_path = repo_root / "data" / "cache" / "adjusted_close.parquet"
    quote_cache_path = repo_root / "data" / "cache" / "irx_quotes.parquet"

    if not price_cache_path.exists():
        raise DataValidationError(
            "The ETF price cache does not exist. Run the data module first."
        )
    if not quote_cache_path.exists():
        raise DataValidationError(
            "The ^IRX quote cache does not exist. Run the riskfree module "
            "first."
        )

    prices = pd.read_parquet(price_cache_path)
    prices.index = pd.to_datetime(prices.index)
    prices.index.name = "date"

    cached_quotes = pd.read_parquet(quote_cache_path)
    quotes = cached_quotes.iloc[:, 0]
    quotes.index = pd.to_datetime(cached_quotes.index)
    quotes.index.name = "date"
    quotes.name = RISK_FREE_TICKER

    # Primary assumption first, then the two frozen sensitivities, clearly
    # labeled. Contract sensitivity policy: these cannot replace the
    # primary results or change the conclusion.
    for cost_bps in (PRIMARY_COST_BPS, *SENSITIVITY_COSTS_BPS):
        result = robustness_review(prices, quotes, cost_bps=cost_bps)
        print(format_report(result))
        print()
    print(
        "Sensitivity policy: the 5 and 20 bps tables are labeled "
        "sensitivities and cannot replace the primary 10 bps results."
    )
    print(
        "This was the contract's one robustness review of 2016-2020. It "
        "does not repeat."
    )


if __name__ == "__main__":
    main()
