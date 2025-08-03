from src.base.load_stock_data import StockRecord
from typing import List, Tuple
from src.base.fynance import FynanceRecord


def scenario_1_buy_sale_once(
    records: List[StockRecord],
    signals: List[int],
    max_buy_times: int,
    cut_loss_pct: float, # Tỷ lệ cắt lỗ ex: 5.0 (5%)
    times_appear_buy_point: int,
    max_between_two_buy_points: int,
    times_appear_sale_point: int,
    max_between_two_sale_points: int
) -> Tuple[List[FynanceRecord], List[int], List[int]]:
    """
    Kịch bản 1: mua-bán 1 lần
    - Force sell khi giá < holding_price * (1 - cut_loss_pct/100)
    - Mua khi có times_appear_buy_point tín hiệu mua trong max_between_two_buy_points phiên
    - Mua ngay khi đạt đủ tín hiệu mua >= times_appear_buy_point
    - Bán khi có times_appear_sale_point tín hiệu bán trong max_between_two_sale_points phiên
    - Bán ngay khi đạt đủ tín hiệu bán >= times_appear_sale_point
    - Nếu còn giữ đến cuối, sẽ bán ở phiên cuối
    Trả về: (final_cash, sale_list, buy_list)
    """
    cash = 0.0
    holding_price = 0.0
    holding = False
    buy_times = 0
    buy_list = [0] * len(records)
    sale_list = [0] * len(records)
    max_between_sale_points = max_between_two_sale_points*times_appear_sale_point
    max_between_buy_points = max_between_two_buy_points*times_appear_buy_point
    list_profit = []
    # Chuyển đổi tín hiệu mua/bán thành danh sách
    
    i = 0
    while i < len(records):
        # 1) Force sell nếu giá giảm quá mức cut-loss
        if holding and records[i].priceAverage < holding_price * (1 - cut_loss_pct / 100):
            print(f"Force selling at {records[i].date}: {records[i].priceAverage} (cut loss)")
            
            # Nếu cắt lỗ, bán luôn ở giá hiện tại
            sale_list[i] = -1  # Đánh dấu cắt lỗ
            sell_price = records[i].priceAverage
            profit = sell_price - holding_price - 0.005 * sell_price
            
            print(f"Profit from cut loss: {profit}")
            # Cập nhật tiền mặt và đánh dấu bán
            cash += profit
            list_profit.append(FynanceRecord(
                date=records[i].date,
                profit=profit,
                cash=cash,
                stock_value=0.0,  # Không còn giữ cổ phiếu
                stock_volume=0.0,  # Không còn giữ cổ phiếu
                stock_symbol=records[i].symbol,
                stock_price=sell_price
            ))
            
            holding = False
            buy_times = 0  # Reset buy times after selling
            i += 1
            continue

        # 2) Mua nếu chưa holding và chưa vượt max_buy_times
        if not holding and buy_times < max_buy_times:
            count = 0
            for j in range(i, min(i + max_between_buy_points, len(records))):
                if signals[j] == 1:
                    count += 1
                if count >= times_appear_buy_point:
                    holding = True
                    holding_price = records[j].priceAverage
                    buy_list[j] = 1
                    buy_times += 1
                    i = j + 1
                    print(f"Bought at: {records[j].date}: {holding_price}")
                    break
            else:
                i += 1
            continue

        # 3) Bán khi holding và có đủ tín hiệu bán
        if holding:
            count = 0
            for j in range(i, min(i + max_between_sale_points, len(records))):
                if signals[j] == -1:
                    count += 1
                if count >= times_appear_sale_point:
                    sell_price = records[j].priceAverage
                    profit = sell_price - holding_price - 0.005 * sell_price
                    cash += profit
                    sale_list[j] = 1 if profit >= 0 else -1
                    holding = False
                    buy_times = 0  # Reset buy times after selling
                    i = j + 1
                    print(f"Sold at:   {records[j].date}: {sell_price} (profit: {profit})")
                    list_profit.append(FynanceRecord(
                        date=records[j].date,
                        profit=profit,
                        cash=cash,
                        stock_value=0.0,  # Không còn giữ cổ phiếu
                        stock_volume=0.0,  # Không còn giữ cổ phiếu
                        stock_symbol=records[j].symbol,
                        stock_price=sell_price
                    ))
                    
                    break
                    
                    # cash += records[j].priceAverage
                    # holding = False
                    # sale_list[j] = True
                    # i = j + 1
                    # break
            else:
                i += 1
            continue

        i += 1

    # 4) Nếu còn giữ đến cuối, bán luôn ở phiên cuối
    if holding:
        sell_price = records[-1].priceAverage
        profit = sell_price - holding_price - 0.005 * sell_price
        
        cash += profit
        sale_list[-1] = 1 if profit >= 0 else -1
        print(f"Sold at last: {records[-1].date}: {sell_price} (profit: {profit})")
        list_profit.append(FynanceRecord(
            date=records[-1].date,
            profit=profit,
            cash=cash,
            stock_value=0.0,  # Không còn giữ cổ phiếu
            stock_volume=0.0,  # Không còn giữ cổ phiếu
            stock_symbol=records[-1].symbol,
            stock_price=sell_price
        ))
        # cash += records[-1].priceAverage
        # sale_list[-1] = True
    else:
        print(f"Not holding at last: {records[-1].date}")
    return list_profit, sale_list, buy_list


def trade_controller(
    records: List[StockRecord],
    sale_point: List[bool],
    buy_point: List[bool],
    script_num: int,
    max_buy_times: int = 1,
    cut_loss_pct: float = 5.0
) -> Tuple[List[FynanceRecord], List[bool], List[bool]]:
    """
    Điều phối các kịch bản dựa vào script_num.
    - script_num=1: gọi scenario_1
    - script_num=2: gọi scenario_2
    - ...
    """
    signals = [0] * len(records)
    for _i in range(len(records)):
        if sale_point[_i]:
            signals[_i] = -1
        elif buy_point[_i]:
            signals[_i] = 1
        else:
            signals[_i] = 0
        
    if script_num == 1:
        # times_appear_buy_point, max_between_two_buy_points, times_appear_sale_point, max_between_two_sale_points có thể rút thành tham số đầu vào nếu muốn tuỳ biến dễ dàng
        return scenario_1_buy_sale_once(
            records, signals,
            max_buy_times=max_buy_times,
            cut_loss_pct=cut_loss_pct,
            times_appear_buy_point=3, max_between_two_buy_points=3,
            times_appear_sale_point=3, max_between_two_sale_points=3
        )
    # elif script_num == 2:
    #     return scenario_2(/* tương tự */)
    # elif script_num == 3:
    #     return scenario_3(/* tương tự */)
    else:
        raise ValueError(f"Unsupported script_num: {script_num}")
