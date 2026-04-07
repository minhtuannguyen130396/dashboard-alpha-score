"""Performance metrics for backtest trade lists.

Computes the set called out in `README_score_v2_validation.md`:
- trade count, win rate, avg gain/loss, expectancy
- profit factor, max drawdown, total profit
- Sharpe / Sortino (per-trade, not annualised)
- avg hold days
"""
from dataclasses import dataclass, asdict
from math import sqrt
from typing import Iterable, List

from src.models.trade_record import TradeRecord


@dataclass
class PerformanceStats:
    trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    avg_gain: float = 0.0
    avg_loss: float = 0.0
    expectancy: float = 0.0          # per trade, absolute PnL
    expectancy_pct: float = 0.0      # per trade, % of entry
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    total_profit: float = 0.0
    avg_hold_days: float = 0.0
    sharpe: float = 0.0              # per-trade, not annualised
    sortino: float = 0.0

    def as_dict(self) -> dict:
        return asdict(self)


def _std(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    var = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return sqrt(var)


def compute_stats(trades: Iterable[TradeRecord]) -> PerformanceStats:
    lst = list(trades)
    if not lst:
        return PerformanceStats()

    profits = [t.profit for t in lst]
    pcts = [getattr(t, "profit_pct", 0.0) for t in lst]
    holds = [getattr(t, "hoding_day", 0) for t in lst]

    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p <= 0]

    total = sum(profits)
    win_rate = len(wins) / len(lst) if lst else 0.0
    avg_gain = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0

    gross_win = sum(wins)
    gross_loss = -sum(losses)
    profit_factor = gross_win / gross_loss if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)

    # Running equity drawdown on absolute profit.
    equity = 0.0
    peak = 0.0
    mdd = 0.0
    for p in profits:
        equity += p
        peak = max(peak, equity)
        dd = peak - equity
        if dd > mdd:
            mdd = dd
    mdd_pct = (mdd / peak * 100) if peak > 0 else 0.0

    expectancy = total / len(lst)
    expectancy_pct = sum(pcts) / len(pcts)

    sd = _std(profits)
    sharpe = (expectancy / sd) if sd > 0 else 0.0
    neg = [p for p in profits if p < 0]
    dsd = _std(neg) if len(neg) > 1 else 0.0
    sortino = (expectancy / dsd) if dsd > 0 else 0.0

    return PerformanceStats(
        trades=len(lst),
        wins=len(wins),
        losses=len(losses),
        win_rate=round(win_rate, 4),
        avg_gain=round(avg_gain, 4),
        avg_loss=round(avg_loss, 4),
        expectancy=round(expectancy, 4),
        expectancy_pct=round(expectancy_pct, 4),
        profit_factor=round(profit_factor, 4) if profit_factor != float("inf") else profit_factor,
        max_drawdown=round(mdd, 4),
        max_drawdown_pct=round(mdd_pct, 4),
        total_profit=round(total, 4),
        avg_hold_days=round(sum(holds) / len(holds), 2) if holds else 0.0,
        sharpe=round(sharpe, 4),
        sortino=round(sortino, 4),
    )


def format_stats(stats: PerformanceStats) -> str:
    pf = f"{stats.profit_factor:.2f}" if stats.profit_factor != float("inf") else "inf"
    return (
        f"Trades={stats.trades} Wins={stats.wins} Losses={stats.losses} "
        f"WinRate={stats.win_rate*100:.1f}% Expectancy={stats.expectancy:+.2f} "
        f"({stats.expectancy_pct:+.2f}%) PF={pf} "
        f"MDD={stats.max_drawdown:.2f} ({stats.max_drawdown_pct:.1f}%) "
        f"Total={stats.total_profit:+.2f} AvgHold={stats.avg_hold_days:.1f}d "
        f"Sharpe={stats.sharpe:.2f} Sortino={stats.sortino:.2f}"
    )
