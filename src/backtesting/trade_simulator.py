from typing import List, Tuple

from src.models.trade_record import TradeRecord
from src.data.stock_data_loader import StockRecord


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

    raise ValueError(f"Unsupported script_num: {script_num}")


scenario_1_buy_sale_once = run_single_position_strategy
trade_controller = run_trade_simulation
