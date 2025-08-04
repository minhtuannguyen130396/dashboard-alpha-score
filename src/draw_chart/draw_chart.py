import os
import webbrowser
from datetime import datetime
from typing import List, Optional
import pandas as pd
from src.base.load_stock_data import StockRecord
from datetime import datetime
from plotly.subplots import make_subplots
import plotly.graph_objects as go

from src.base.load_stock_data import StockRecord
from src.detect_market_behavior.detect_market_behavior import MartketBehaviorDetector
from src.base.fynance import FynanceRecord
def open_html_in_chrome(path_to_html: str):
    chrome_path = r'"C:\Program Files\Google\Chrome\Application\chrome.exe" %s'
    webbrowser.get(chrome_path).open('file://' + os.path.realpath(path_to_html))


def draw_candlestick_plotly(
    stock_records: List[StockRecord], 
    marketBehavior: MartketBehaviorDetector, 
    actual_sale_point: List[int],
    actual_buy_point: List[int])-> go.Figure:
                             
    """Vẽ biểu đồ nến sử dụng Plotly cho dữ liệu cổ phiếu.  
    Thêm các điểm mua/bán và khối lượng giao dịch.
    Args:
        stock_records (List[StockRecord]): Danh sách các bản ghi cổ phiếu.
        marketBehavior (MartketBehaviorDetector): Đối tượng chứa các điểm mua/bán và thông tin thị trường.
    """
    sale_point = marketBehavior.sale_point
    buy_point = marketBehavior.buy_point
    big_buyer = marketBehavior.big_buyer
    fomo_retail = marketBehavior.fomo_retail
    ema_volume = marketBehavior.ema_volume
    total_volume = marketBehavior.total_volume
    actual_sale_point_converted = [True if actual_sale_point[i] == 1 or actual_sale_point[i] == -1 else False for i in range(len(stock_records))]
    actual_buy_point_converted = [True if actual_buy_point[i] == 1 else False for i in range(len(stock_records))]
  
    if len(stock_records) != len(sale_point):
        raise ValueError("Length sale_point mismatch")
    if len(stock_records) != len(buy_point):
        raise ValueError("Length buy_point mismatch")
    if len(stock_records) != len(big_buyer):
        raise ValueError("Length big_buyer mismatch")
    if len(stock_records) != len(fomo_retail):
        raise ValueError("Length fomo_retail mismatch")
    if len(stock_records) != len(actual_buy_point):
        raise ValueError("Length actual_buy_point mismatch")
    if len(stock_records) != len(actual_sale_point):
        raise ValueError("Length actual_sale_point mismatch")

    df = pd.DataFrame({
        "Date": [r.date for r in stock_records],
        "Open": [r.priceOpen for r in stock_records],
        "High": [r.priceHigh for r in stock_records],
        "Low": [r.priceLow for r in stock_records],
        "Close": [r.priceClose for r in stock_records],
        "AdjRatio": [r.adjRatio for r in stock_records],
        "avgPrice": [r.priceAverage for r in stock_records]
    })

    # Tìm ngày điều chỉnh giá (khi AdjRatio thay đổi so với phiên trước)
    # adjustment_mask = [False]
    # for i in range(1, len(df)):
    #     prev_ratio = df["AdjRatio"].iloc[i - 1]
    #     curr_ratio = df["AdjRatio"].iloc[i]
    #     if prev_ratio == 0:
    #         adjustment_mask.append(False)
    #     else:
    #         change_pct = ((curr_ratio - prev_ratio) / prev_ratio) * 100
    #         if change_pct != 0:
    #             adjustment_mask.append(True)
    #             print(f"Adjustment at {df['Date'].iloc[i]}: {change_pct:+.2f}% (from {prev_ratio} to {curr_ratio})")
    #         else:
    #             adjustment_mask.append(False)
    # adjustment_mask = np.array(adjustment_mask)

    fig = go.Figure()

    # Nến
    fig.add_trace(go.Candlestick(
        x=df["Date"],
        open=df["Open"],
        high=df["High"],
        low=df["Low"],
        close=df["Close"],
        name="Candlestick"
    ))

    # Chấm mua (xanh)
    fig.add_trace(go.Scatter(
        x=df["Date"][buy_point],
        y=df["Low"][buy_point] * 0.995,
        mode='markers',
        marker=dict(color='green', size=10, symbol='triangle-up'),
        name='Mua'
    ))

    # Chấm bán (đỏ)
    fig.add_trace(go.Scatter(
        x=df["Date"][sale_point],
        y=df["High"][sale_point] * 1.005,
        mode='markers',
        marker=dict(color='red', size=10, symbol='triangle-down'),
        name='Ban'
    ))
    # Chấm mua thực tế (xanh lá)
    fig.add_trace(go.Scatter(
        x=df["Date"][actual_buy_point_converted],
        y=df["avgPrice"][actual_buy_point_converted] ,
        mode='markers',
        marker=dict(color='blue', size=10, symbol='circle'),
        name='Mua Thực Tế'
    ))
    # Chấm bán thực tế (đỏ tươi)
    actual_sale_color = []
    for i in range(len(actual_sale_point)):
        if actual_sale_point[i] == -1:
            actual_sale_color.append('red')
            #print(f"Actual sale at {df['Date'][i]}: {df['Close'][i]} (loss)")
        else:
            actual_sale_color.append('crimson')
            #print(f"Actual sale at {df['Date'][i]}: {df['Close'][i]} (profit)")
            
    fig.add_trace(go.Scatter(
        x=df["Date"][actual_sale_point_converted],
        y=df["avgPrice"][actual_sale_point_converted],
        mode='markers',
        marker=dict(color="#FF9900", size=10, symbol='circle'),
        name='Bán Thực Tế'
    ))
    
    
    # # Chấm vàng cho ngày điều chỉnh
    # fig.add_trace(go.Scatter(
    #     x=df["Date"][adjustment_mask],
    #     y=df["Close"][adjustment_mask],
    #     mode='markers',
    #     marker=dict(color='gold', size=8, symbol='circle'),
    #     name='Adjusted Price Day'
    # ))
    # Thêm cột khối lượng bên dưới chart
    # Tạo màu cho từng cột volume theo điều kiện big_buyer và fomo_retail
    volume_colors = []
    for i in range(len(stock_records)):
        if big_buyer[i] and not fomo_retail[i]:
            volume_colors.append('green')
        elif not big_buyer[i] and fomo_retail[i]:
            volume_colors.append('red')
        elif big_buyer[i] and fomo_retail[i]:
            volume_colors.append('blue')
        else:
            volume_colors.append('purple')

    fig.add_trace(go.Bar(
        x=df["Date"],
        y=total_volume,
        marker_color=volume_colors,
        name='Volume',
        yaxis='y2',
    ))

    # Thiết lập trục phụ cho khối lượng
    fig.update_layout(
        yaxis2=dict(
            #family="Arial",
            title='Khối lượng(Tím None Big & Fomo)',
            overlaying='y',
            side='right',
            showgrid=False,
            position=1.0,
            range=[0, max(total_volume) * 4],
        ),
        legend=dict(orientation="h"),
    )
    # Đường trung bình khối lượng (EMA 5 phiên)
    #volume_series = df["Volume"] if "Volume" in df.columns else pd.Series([r.totalVolume for r in stock_records])
    #ema_volume = volume_series.ewm(span=14, adjust=False).mean()

    fig.add_trace(go.Scatter(
        x=df["Date"],
        y=ema_volume,
        mode='lines',
        line=dict(color='magenta', width=2, dash='dash'),
        name='EMA Volume (14 days)',
        yaxis='y2'
    ))
    symbol = stock_records[-1].symbol
    
    fig.update_layout(title=f"[{symbol}] Từ {stock_records[0].date.strftime('%Y-%m-%d')} đến {stock_records[-1].date.strftime('%Y-%m-%d')}",
                      xaxis_title='Date', yaxis_title='Price',
                      xaxis_rangeslider_visible=False
                      )
    fig.update_xaxes(
        rangeslider_visible=True,  # bật range slider
        type="date"                # đảm bảo trục X là ngày tháng
    )
    return fig


def table_fynance(list_fynance: List[FynanceRecord]) -> go.Figure:
    """
    Vẽ bảng từ DataFrame table_df (mỗi cột là 1 trường, mỗi dòng 1 record)
    Trả về fig chứa 1 trace Table
    """
    header = dict(
        values=["Date", "Profit", "Cash", "Stock Value", "Stock Volume", "Symbol", "Price"],
        fill_color="paleturquoise",
        align="left"
    )
    # Chuyển đổi từng trường trong list thành một list song song
    dates = [rec.date.strftime("%Y-%m-%d") for rec in list_fynance]
    profits = [rec.profit for rec in list_fynance]
    cashes = [rec.cash for rec in list_fynance]
    stock_values = [rec.stock_value for rec in list_fynance]
    stock_volumes = [rec.stock_volume for rec in list_fynance]
    symbols = [rec.stock_symbol for rec in list_fynance]
    prices = [rec.stock_price for rec in list_fynance]

    cells = dict(
        values=[dates, profits, cashes, stock_values, stock_volumes, symbols, prices],
        fill_color="lavender",
        align="left"
    )

    # Tạo figure dạng Table
    fig = go.Figure(data=[go.Table(header=header, cells=cells)])
    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        height=400 + 30 * len(list_fynance)  # tự điều chỉnh chiều cao theo số dòng
    )
    return fig

def draw_chart(
    stock_records: List[StockRecord], 
    marketBehavior: MartketBehaviorDetector, 
    actual_sale_point: List[int],
    actual_buy_point: List[int],
    list_fynance:List[FynanceRecord])    -> None:
    """ Hàm vẽ biểu đồ tổng quan"""
    
    # Tạo layout 2 hàng, 1 cột

    fig_candlestick = draw_candlestick_plotly(
        stock_records,
        marketBehavior,
        actual_sale_point,
        actual_buy_point,
    )
    
    
    current_date_str = datetime.now().strftime('%Y-%m-%d')
    output_dir = os.path.join('chart', current_date_str)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    #fig.update_layout(height=3000)
    
    file_name = f"{stock_records[-1].symbol}_{stock_records[0].date.strftime('%Y-%m-%d')}_{stock_records[-1].date.strftime('%Y-%m-%d')}.html"
    fig_candlestick.write_html(
        os.path.join(output_dir, file_name),  
        auto_open=False
    )
    open_html_in_chrome(os.path.join(output_dir, file_name))