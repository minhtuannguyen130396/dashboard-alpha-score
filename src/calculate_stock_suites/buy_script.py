from src.base.load_stock_data import StockRecord
from typing import List, Tuple
from src.base.fynance import FynanceRecord
from datetime import datetime

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
    holding_position = 0
    date_buy = None
    holding = False
    buy_times = 0
    buy_list = [0] * len(records)
    sale_list = [0] * len(records)
    max_between_sale_points = max_between_two_sale_points*times_appear_sale_point
    max_between_buy_points = max_between_two_buy_points*times_appear_buy_point
    list_profit = []
    count_sale_singnal = 0
    
    # Chuyển đổi tín hiệu mua/bán thành danh sách
    
    i = 0
    while i < len(records):
        # 2) Xác định vị trí để bắt đầu mua mới
        
        count_buy_signal = 0
        while (not holding):
            if signals[i] == 1:
                count_buy_signal += 1
            if count_buy_signal >= times_appear_buy_point:
                count_buy_signal = 0
                holding = True
                holding_price = records[i].priceAverage
                date_buy = records[i].date
                holding_position = i
                buy_list[i] = 1
                buy_times += 1
                i = i + 1
                break
            else:
                i += 1
            if i >= len(records):
                break
            
        # 3) Bán khi holding và có đủ tín hiệu bán
        while holding:
            if i >= len(records):
                break
            if records[i].priceAverage < holding_price * (1 - cut_loss_pct / 100):
                print(f"Force selling at {records[i].date}: {records[i].priceAverage} (cut loss)")
                # Nếu cắt lỗ, bán luôn ở giá hiện tại
                sale_list[i] = -1  # Đánh dấu cắt lỗ
                sell_price = records[i].priceAverage
                profit = sell_price - holding_price - 0.005 * sell_price
                print(f"Profit from cut loss: {profit}")
                # Cập nhật tiền mặt và đánh dấu bán
                cash += profit
                list_profit.append(FynanceRecord(
                    date_buy=date_buy,
                    date_sale=records[i].date,
                    hoding_day=i - holding_position,
                    profit=profit,
                    profit_pct=(profit / holding_price) * 100 if holding_price else 0,
                    cash=cash,
                    buy_value=holding_price,
                    buy_volume=1,  # Giả sử mua 1 cổ phiếu
                    sale_value=sell_price,
                    sale_volume=1,  # Giả sử bán 1 cổ phiếu
                ))
                
                holding = False
                buy_times = 0  # Reset buy times after selling
                i += 1
                continue
            
            #if i < (holding_position + max_between_sale_points):    
            if signals[i] == -1:
                #add confition max_between_sale_points
                count_sale_singnal += 1
            elif signals[i] == 1:
                count_sale_singnal = 0
                
            if count_sale_singnal < times_appear_sale_point:
                i+= 1
                continue
           
            sell_price = records[i].priceAverage
            profit = sell_price - holding_price - 0.005 * sell_price
            cash += profit
            sale_list[i] = 1 if profit >= 0 else -1
            holding = False
            buy_times = 0  # Reset buy times after selling
            count_sale_singnal = 0
            print(f"Sold at:   {records[i].date.strftime('%d-%m-%Y')}: {sell_price} (profit: {profit})")
            list_profit.append(FynanceRecord(
                date_sale=records[i].date,
                date_buy=date_buy,
                hoding_day=i - holding_position,
                profit=profit,
                profit_pct=(profit / holding_price) * 100 if holding_price else 0,
                cash=cash,
                buy_value=holding_price,
                buy_volume=1,  # Giả sử mua 1 cổ phiếu
                sale_value=sell_price,
                sale_volume=1,  # Giả sử bán 1 cổ phiếu
            ))
            i +=1
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
            date_buy=records[-1].date,
            date_sale=records[-1].date,
            hoding_day=i - holding_position,
            profit=profit,
            profit_pct=(profit / holding_price) * 100 if holding_price else 0,
            cash=cash,
            buy_value=holding_price,
            buy_volume=1,  # Giả sử mua 1 cổ phiếu
            sale_value=sell_price,
            sale_volume=1,  # Giả sử bán 1 cổ phiếu
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
