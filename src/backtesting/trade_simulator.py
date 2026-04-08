"""Trade simulator V4.

Single-position long-only simulator with realistic VN market frictions:
  - Buy fee: 0.15%
  - Sell fee + tax: 0.25%
  - T+2.5 settlement (rounded up to T+3)
  - Next-bar open execution (no look-ahead)

Risk management:
  - Initial stop:  entry - k_stop * ATR
  - Dynamic trail: ATR multiple shrinks as the trade banks more R-multiples,
    so winners are given more breathing room early and protected hard late.
  - Partial take-profit at 1.5R (sells half, locks breakeven on the runner)
  - Time stop after max_hold_days
  - Sell-signal exit (the analyzer suppresses these in bull regimes)
"""
from dataclasses import dataclass
from typing import List, Tuple

from src.models.trade_record import TradeRecord
from src.data.stock_data_loader import StockRecord
from src.analysis.technical_indicators import IndicatorGroup3


FEE_BUY = 0.0015
FEE_SELL = 0.0025  # 0.15% broker + 0.10% tax
T_PLUS = 3         # T+2.5 rounded up


@dataclass
class TradeConfigV4:
    k_stop: float = 2.5          # initial stop in ATR units (gives T+3 room)
    tp_r: float = 1.5            # first take-profit at 1.5R
    tp_fraction: float = 0.5     # partial exit fraction
    use_trailing: bool = True
    use_take_profit: bool = True
    atr_period: int = 14
    respect_t_plus: bool = True
    max_hold_days: int = 60      # hard time-stop

    # Dynamic trailing — k_trail (in ATR units) by R-multiple of unrealized PnL.
    # Tighter as the trade banks profit so we give back less of a winner.
    trail_loose:  float = 2.8    # < 1R unrealized
    trail_mid:    float = 2.0    # 1R..2R
    trail_tight:  float = 1.4    # > 2R


def _trail_k(r_multiple: float, cfg: TradeConfigV4) -> float:
    if r_multiple < 1.0:
        return cfg.trail_loose
    if r_multiple < 2.0:
        return cfg.trail_mid
    return cfg.trail_tight


def _build_trade_record(
    date_buy, date_sale, hold_days: int,
    entry_px: float, exit_px: float, cash_running: float,
    fraction: float = 1.0,
) -> TradeRecord:
    """Emit a TradeRecord for ``fraction`` of a unit position.

    ``profit`` is scaled so the sum of multiple partial records equals the
    full-position PnL. ``profit_pct`` stays at the full return-on-entry
    rate (not scaled) so per-trade percentage reporting is unaffected by
    tp_fraction tuning.
    """
    net = (exit_px * (1 - FEE_SELL) - entry_px * (1 + FEE_BUY)) * fraction
    full_pct = ((exit_px * (1 - FEE_SELL) - entry_px * (1 + FEE_BUY)) / entry_px) * 100 if entry_px else 0
    return TradeRecord(
        date_buy=date_buy,
        date_sale=date_sale,
        hoding_day=hold_days,
        profit=net,
        profit_pct=full_pct,
        cash=cash_running,
        buy_value=entry_px,
        buy_volume=fraction,
        sale_value=exit_px,
        sale_volume=fraction,
    )


def run_trade_simulation(
    records: List[StockRecord],
    sale_point: List[bool],
    buy_point: List[bool],
    cfg: TradeConfigV4 = None,
) -> Tuple[List[TradeRecord], List[int], List[int]]:
    """Single-position simulator. Returns trades, sale-marker list, buy-marker list."""
    if cfg is None:
        cfg = TradeConfigV4()

    signals = [0] * len(records)
    for index in range(len(records)):
        if sale_point[index]:
            signals[index] = -1
        elif buy_point[index]:
            signals[index] = 1

    atr = IndicatorGroup3.atr(records, cfg.atr_period)

    cash = 0.0
    buy_list = [0] * len(records)
    sale_list = [0] * len(records)
    trades: List[TradeRecord] = []

    i = 0
    while i < len(records) - 1:
        if signals[i] != 1:
            i += 1
            continue

        entry_idx = i + 1  # next-bar execution
        if entry_idx >= len(records):
            break
        entry_px = records[entry_idx].priceOpen or records[entry_idx].priceAverage
        entry_date = records[entry_idx].date
        buy_list[entry_idx] = 1

        entry_atr = atr[entry_idx] if entry_idx < len(atr) and atr[entry_idx] else entry_px * 0.02
        stop = entry_px - cfg.k_stop * entry_atr
        risk = entry_px - stop
        tp1 = entry_px + cfg.tp_r * risk

        remaining = 1.0
        tp_frac = max(0.0, min(1.0, cfg.tp_fraction))

        j = entry_idx + 1
        exit_px = None
        exit_idx = None
        while j < len(records):
            r = records[j]
            can_sell = (j - entry_idx) >= T_PLUS if cfg.respect_t_plus else True

            # Stop hit (intraday low)
            if can_sell and r.priceLow <= stop:
                exit_px = stop
                exit_idx = j
                break

            # Partial take-profit at 1.5R
            if (
                cfg.use_take_profit
                and can_sell
                and remaining > tp_frac
                and tp_frac > 0
                and r.priceHigh >= tp1
            ):
                partial_profit = (tp1 * (1 - FEE_SELL) - entry_px * (1 + FEE_BUY)) * tp_frac
                cash += partial_profit
                sale_list[j] = 1 if partial_profit >= 0 else -1
                trades.append(_build_trade_record(
                    entry_date, r.date,
                    j - entry_idx, entry_px, tp1, cash,
                    fraction=tp_frac,
                ))
                remaining -= tp_frac
                # Lock breakeven for the runner
                stop = max(stop, entry_px)
                if remaining <= 1e-9:
                    exit_px = tp1
                    exit_idx = j
                    remaining = 0.0
                    break

            # Dynamic trailing — tighten as R-multiple grows
            if cfg.use_trailing and risk > 0:
                r_mult = (r.priceClose - entry_px) / risk
                cur_atr = atr[j] if atr[j] else entry_atr
                k = _trail_k(r_mult, cfg)
                new_stop = r.priceClose - k * cur_atr
                if new_stop > stop:
                    stop = new_stop

            # Sell signal
            if can_sell and signals[j] == -1:
                exit_px = r.priceAverage
                exit_idx = j
                break

            # Max hold
            if (j - entry_idx) >= cfg.max_hold_days:
                exit_px = r.priceAverage
                exit_idx = j
                break

            j += 1

        # End-of-data: close whatever remains at last bar's average
        if remaining > 1e-9:
            if exit_px is None:
                exit_idx = len(records) - 1
                exit_px = records[exit_idx].priceAverage

            tail_profit = (exit_px * (1 - FEE_SELL) - entry_px * (1 + FEE_BUY)) * remaining
            cash += tail_profit
            sale_list[exit_idx] = 1 if tail_profit >= 0 else -1
            trades.append(_build_trade_record(
                entry_date, records[exit_idx].date,
                exit_idx - entry_idx, entry_px, exit_px, cash,
                fraction=remaining,
            ))
            remaining = 0.0

        i = (exit_idx if exit_idx is not None else entry_idx) + 1

    return trades, sale_list, buy_list


trade_controller = run_trade_simulation
