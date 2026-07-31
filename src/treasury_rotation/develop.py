"""Development-period first-look runner under research contract v0.2.3.

This module computes the six frozen metrics for both strategies and both
benchmarks on the DEVELOPMENT PERIOD ONLY: 2003-01-01 through 2015-12-31.

The boundary is hard-coded on purpose. There is no parameter, flag, or
argument that widens the window, because the moment a window becomes an
input, a disappointed researcher can "just check" a later period. The
validation period (2016-2020) is reserved for one robustness review, and
the locked test period (2021-2025) may not be evaluated until everything
is frozen. This runner slices first and verifies the slice, so post-2015
data never reaches a signal, a portfolio, or a metric.

Contract obligations implemented here:

1. (v0.2.1 clause 3) Benchmarks are evaluated over the identical
   measured-return window as the strategies: measurement begins the
   trading day AFTER the first qualifying decision close. If any of the
   four portfolios ends up with a different window, this runner raises
   instead of reporting numbers whose differences could be caused by the
   calendar rather than the rules.
2. (v0.2.3 clauses 3-5) The Sharpe ratio uses the ^IRX daily risk-free
   series, aligned to the same measured-return window.
3. Costs use the primary 10 bps assumption for this first look.

This module reads local caches only. It never downloads data.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from treasury_rotation.config import (
    CONTRACT_VERSION,
    DEVELOPMENT_END,
    PRIMARY_COST_BPS,
    SENSITIVITY_COSTS_BPS,
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

# The fence. DEVELOPMENT_END comes from the frozen config, and nothing in
# this module accepts a different date from anywhere.
DEVELOPMENT_BOUNDARY = pd.Timestamp(DEVELOPMENT_END)

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


class DevelopmentBoundaryError(DataValidationError):
    """Raised when data outside the development period reaches this runner."""


@dataclass(frozen=True)
class FirstLookResult:
    """The complete first-look output: one metrics dict per portfolio.

    ``window_start`` and ``window_end`` bound the shared measured-return
    window; ``measured_days`` counts its trading days. ``metrics`` maps
    each portfolio label to its six frozen metrics.
    """

    window_start: pd.Timestamp
    window_end: pd.Timestamp
    measured_days: int
    cost_bps: int
    metrics: dict[str, dict[str, float]]


def development_slice(prices: pd.DataFrame) -> pd.DataFrame:
    """Return only the price rows on or before the development boundary."""

    sliced = prices.loc[prices.index <= DEVELOPMENT_BOUNDARY]
    if sliced.empty:
        raise DevelopmentBoundaryError(
            "No price rows fall inside the development period."
        )
    # Belt and braces: the slice above makes this impossible, but if a
    # future edit ever breaks the fence, failing here beats reporting a
    # number computed on reserved data.
    if sliced.index.max() > DEVELOPMENT_BOUNDARY:
        raise DevelopmentBoundaryError(
            "A post-development date survived the development slice."
        )
    return sliced


def first_look(
    prices: pd.DataFrame,
    quotes: pd.Series,
    *,
    cost_bps: int = PRIMARY_COST_BPS,
) -> FirstLookResult:
    """Compute all six metrics for all four portfolios, development only.

    ``prices`` is the validated adjusted-close table (any range; it is
    fenced here) and ``quotes`` is the raw ^IRX quote series. Everything
    downstream shares one measured-return window, enforced by an explicit
    index-equality check rather than by trust.

    ``cost_bps`` may only be the primary assumption or one of the two
    contract-frozen sensitivities. Decisions never see costs, so every
    cost level produces identical trades on identical dates; only the
    toll per dollar traded changes.
    """

    if cost_bps not in ALLOWED_COST_BPS:
        raise DataValidationError(
            f"{cost_bps} bps is not a contract cost assumption. The "
            f"permitted levels are {sorted(ALLOWED_COST_BPS)}; costs are "
            "frozen, not tunable."
        )

    dev_prices = development_slice(prices)

    phase1_decisions, phase1_sim = run_phase1(dev_prices, cost_bps=cost_bps)
    _phase2_decisions, phase2_sim = run_phase2(dev_prices, cost_bps=cost_bps)

    # Contract v0.2.1 clause 3: the measured-return window starts the
    # trading day after the first qualifying decision close, and the
    # benchmarks are evaluated over that identical window. Handing the
    # benchmarks the full asset-return history would let them earn the
    # strategy's warm-up months, and any later difference in metrics
    # could then be caused by the calendar instead of the rules.
    asset_returns = calculate_returns(dev_prices)
    first_decision = phase1_decisions.targets.index[0]
    measured_returns = asset_returns.loc[asset_returns.index > first_decision]

    ief_sim = run_buy_and_hold_ief(measured_returns, cost_bps=cost_bps)
    equal_weight_sim = run_quarterly_equal_weight(
        measured_returns, cost_bps=cost_bps
    )

    simulations: dict[str, PortfolioSimulation] = {
        "phase1_momentum": phase1_sim,
        "phase2_risk_adjusted": phase2_sim,
        "buy_and_hold_ief": ief_sim,
        "equal_weight_quarterly": equal_weight_sim,
    }

    expected_index = measured_returns.index
    for label, simulation in simulations.items():
        if not simulation.daily.index.equals(expected_index):
            raise DevelopmentBoundaryError(
                f"The {label} window differs from the shared measured-return "
                "window; metrics on mismatched windows are not comparable."
            )

    # The risk-free series aligns to the development trading calendar only,
    # so this call never touches a post-development quote. The clause-5
    # forward-fill uses strictly prior days, so restricting the calendar
    # cannot change any filled value inside the window.
    trading_days = pd.DatetimeIndex(dev_prices.index, name="date")
    filled_quotes, _report = validate_and_fill(quotes, trading_days)
    measured_risk_free = daily_risk_free_rates(filled_quotes).loc[expected_index]

    metrics = {
        label: summarize_performance(simulation.daily, measured_risk_free)
        for label, simulation in simulations.items()
    }
    return FirstLookResult(
        window_start=expected_index[0],
        window_end=expected_index[-1],
        measured_days=len(expected_index),
        cost_bps=cost_bps,
        metrics=metrics,
    )


def format_report(result: FirstLookResult) -> str:
    """Render the first-look result as a fixed-width text table."""

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
        "Development-period first look: PASS",
        f"Contract version: {CONTRACT_VERSION}",
        f"Development period ends: {DEVELOPMENT_BOUNDARY.date().isoformat()}",
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
        "The validation period (2016-2020) and locked test period "
        "(2021-2025) were not evaluated."
    )
    return "\n".join(lines)


def main() -> None:
    """Load local caches, run the development first look, print the table."""

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
        result = first_look(prices, quotes, cost_bps=cost_bps)
        print(format_report(result))
        print()
    print(
        "Sensitivity policy: the 5 and 20 bps tables are labeled "
        "sensitivities and cannot replace the primary 10 bps results."
    )


if __name__ == "__main__":
    main()
