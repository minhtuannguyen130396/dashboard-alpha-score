from dataclasses import dataclass
from typing import List, Tuple

from src.models.trade_record import TradeRecord
from src.data.stock_data_loader import StockRecord
from src.analysis.technical_indicators import IndicatorGroup3


# =============================================================================
# Trade simulator V2
# =============================================================================
# Realistic VN market fees:
#   - Buy:  0.15% broker fee
#   - Sell: 0.15% broker fee + 0.10% income tax
# T+2.5 settlement: shares bought today are sellable 2.5 sessions later (use 3).
#
# Execution model:
#   - Entry fills on next-bar open (no look-ahead).
#   - Initial stop at entry - k_stop * ATR.
#   - Trailing stop: raised to max(previous stop, close - k_trail * ATR).
#   - Partial take-profit at entry + tp_r * risk, sell tp_fraction of position.
#   - Final exit: stop hit, sell signal, or end of data.

FEE_BUY = 0.0015
FEE_SELL = 0.0025  # 0.15% broker + 0.10% tax
T_PLUS = 3         # T+2.5 rounded up


@dataclass
class TradeConfigV2:
    k_stop: float = 2.0        # initial stop in ATR units
    k_trail: float = 3.0       # trailing stop in ATR units
    tp_r: float = 1.5          # first take-profit at 1.5R
    tp_fraction: float = 0.5   # partial exit fraction
    use_trailing: bool = True
    use_take_profit: bool = True
    atr_period: int = 14
    respect_t_plus: bool = True
    max_hold_days: int = 60    # hard time-stop


def _build_trade_record(
    date_buy, date_sale, hold_days: int,
    entry_px: float, exit_px: float, cash_running: float,
    fraction: float = 1.0,
) -> TradeRecord:
    """Emit a TradeRecord for ``fraction`` of a unit position.

    ``profit`` / ``profit_pct`` are scaled so that the sum of multiple partial
    records equals the full-position PnL. ``profit_pct`` intentionally stays
    at the full return-on-entry rate (not scaled) so tuning tp_fraction does
    not distort the per-trade percentage reporting.
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


def run_single_position_strategy_v2(
    records: List[StockRecord],
    signals: List[int],
    cfg: TradeConfigV2 = None,
) -> Tuple[List[TradeRecord], List[int], List[int]]:
    """V2 strategy: ATR stop, trailing stop, partial TP, realistic fees, T+2.5."""
    if cfg is None:
        cfg = TradeConfigV2()

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

        # Fraction of the unit position still held. Shrinks after a TP1 fill.
        remaining = 1.0
        tp_frac = max(0.0, min(1.0, cfg.tp_fraction))

        j = entry_idx + 1
        exit_px = None
        exit_idx = None
        while j < len(records):
            r = records[j]
            # T+ constraint
            can_sell = (j - entry_idx) >= T_PLUS if cfg.respect_t_plus else True

            # Check stop (intraday low) — full exit of whatever remains
            if can_sell and r.priceLow <= stop:
                exit_px = stop
                exit_idx = j
                break

            # Partial TP — realize a real sell of ``tp_frac`` of the unit
            if (
                cfg.use_take_profit
                and can_sell
                and remaining > tp_frac  # TP1 not yet executed
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
                # If fraction was 1.0 (effectively full exit), we're done
                if remaining <= 1e-9:
                    exit_px = tp1
                    exit_idx = j
                    # The record was already emitted above; skip the tail emit.
                    remaining = 0.0
                    break

            # Trailing stop for the runner
            if cfg.use_trailing:
                cur_atr = atr[j] if atr[j] else entry_atr
                new_stop = r.priceClose - cfg.k_trail * cur_atr
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

        # Advance past the final exit bar (or past TP1 if full_exit-via-TP1)
        i = (exit_idx if exit_idx is not None else entry_idx) + 1

    return trades, sale_list, buy_list


def run_single_position_strategy(
    records: List[StockRecord],
    signals: List[int],
    max_buy_times: int,
    cut_loss_pct: float,
    times_appear_buy_point: int,
    max_between_two_buy_points: int,
    times_appear_sale_point: int,
    max_between_two_sale_points: int,
) -> Tuple[List[TradeRecord], List[int], List[int]]:
    cash = 0.0
    holding_price = 0.0
    holding_position = 0
    date_buy = None
    holding = False
    buy_list = [0] * len(records)
    sale_list = [0] * len(records)
    list_profit: List[TradeRecord] = []
    count_sale_signal = 0

    i = 0
    while i < len(records):
        count_buy_signal = 0
        while not holding:
            if i >= len(records):
                break
            if signals[i] == 1:
                count_buy_signal += 1
            else:
                count_buy_signal = 0

            if count_buy_signal >= times_appear_buy_point:
                holding = True
                holding_price = records[i].priceAverage
                date_buy = records[i].date
                holding_position = i
                buy_list[i] = 1
                i += 1
                break

            i += 1

        while holding:
            if i >= len(records):
                break

            if records[i].priceAverage < holding_price * (1 - cut_loss_pct / 100):
                sell_price = records[i].priceAverage
                profit = sell_price - holding_price - 0.005 * sell_price
                sale_list[i] = -1
                cash += profit
                list_profit.append(
                    TradeRecord(
                        date_buy=date_buy,
                        date_sale=records[i].date,
                        hoding_day=i - holding_position,
                        profit=profit,
                        profit_pct=(profit / holding_price) * 100 if holding_price else 0,
                        cash=cash,
                        buy_value=holding_price,
                        buy_volume=1,
                        sale_value=sell_price,
                        sale_volume=1,
                    )
                )
                holding = False
                count_sale_signal = 0
                i += 1
                continue

            if signals[i] == -1:
                count_sale_signal += 1
            elif signals[i] == 1:
                count_sale_signal = 0

            if count_sale_signal < times_appear_sale_point:
                i += 1
                continue

            sell_price = records[i].priceAverage
            profit = sell_price - holding_price - 0.005 * sell_price
            cash += profit
            sale_list[i] = 1 if profit >= 0 else -1
            holding = False
            count_sale_signal = 0
            list_profit.append(
                TradeRecord(
                    date_buy=date_buy,
                    date_sale=records[i].date,
                    hoding_day=i - holding_position,
                    profit=profit,
                    profit_pct=(profit / holding_price) * 100 if holding_price else 0,
                    cash=cash,
                    buy_value=holding_price,
                    buy_volume=1,
                    sale_value=sell_price,
                    sale_volume=1,
                )
            )
            i += 1
            continue

        if not holding:
            continue

    if holding:
        sell_price = records[-1].priceAverage
        profit = sell_price - holding_price - 0.005 * sell_price
        cash += profit
        sale_list[-1] = 1 if profit >= 0 else -1
        list_profit.append(
            TradeRecord(
                date_buy=date_buy,
                date_sale=records[-1].date,
                hoding_day=len(records) - 1 - holding_position,
                profit=profit,
                profit_pct=(profit / holding_price) * 100 if holding_price else 0,
                cash=cash,
                buy_value=holding_price,
                buy_volume=1,
                sale_value=sell_price,
                sale_volume=1,
            )
        )

    return list_profit, sale_list, buy_list


def run_trade_simulation(
    records: List[StockRecord],
    sale_point: List[bool],
    buy_point: List[bool],
    script_num: int,
    max_buy_times: int = 1,
    cut_loss_pct: float = 5.0,
) -> Tuple[List[TradeRecord], List[bool], List[bool]]:
    signals = [0] * len(records)
    for index in range(len(records)):
        if sale_point[index]:
            signals[index] = -1
        elif buy_point[index]:
            signals[index] = 1

    if script_num == 1:
        return run_single_position_strategy(
            records,
            signals,
            max_buy_times=max_buy_times,
            cut_loss_pct=cut_loss_pct,
            times_appear_buy_point=3,
            max_between_two_buy_points=3,
            times_appear_sale_point=3,
            max_between_two_sale_points=3,
        )

    if script_num == 2:
        return run_single_position_strategy_v2(records, signals, TradeConfigV2())

    raise ValueError(f"Unsupported script_num: {script_num}")


scenario_1_buy_sale_once = run_single_position_strategy
trade_controller = run_trade_simulation
