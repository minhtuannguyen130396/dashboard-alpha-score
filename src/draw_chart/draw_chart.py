import plotly.graph_objects as go
from datetime import datetime
from typing import List, Optional
import pandas as pd
import mplfinance as mpf
from src.base.load_stock_data import StockRecord
import numpy as np
from datetime import datetime, timedelta
from src.base.load_stock_data import StockRecord
import webbrowser
import os


def open_html_in_chrome(path_to_html: str):
    chrome_path = r'"C:\Program Files\Google\Chrome\Application\chrome.exe" %s'
    webbrowser.get(chrome_path).open('file://' + os.path.realpath(path_to_html))

def draw_chart_with_signals(
    stock_records: List[StockRecord],
    list_point: List[float],
    buy_threshold: float = 5,
    sell_threshold: float = -5,
    buy_offset: float = 0.995,   # vẽ chấm xanh hơi dưới đáy nến
    sell_offset: float = 1.005   # vẽ chấm đỏ hơi trên đỉnh nến
):
    if len(stock_records) != len(list_point):
        raise ValueError("list_point length does not match stock_records.")

    df = pd.DataFrame({
        "Date": [r.date for r in stock_records],
        "Open": [r.priceOpen for r in stock_records],
        "High": [r.priceHigh for r in stock_records],
        "Low":  [r.priceLow  for r in stock_records],
        "Close":[r.priceClose for r in stock_records],
        "Volume":[r.totalVolume for r in stock_records],
    }).set_index("Date")

    points = np.asarray(list_point)

    # dùng np.where và np.nan để đảm bảo numeric array
    buy_vals  = np.where(points >= buy_threshold, df["Low"].values  * buy_offset,  np.nan)
    sell_vals = np.where(points <= sell_threshold, df["High"].values * sell_offset, np.nan)

    buy_series  = pd.Series(buy_vals,  index=df.index)
    sell_series = pd.Series(sell_vals, index=df.index)

    apds = [
        mpf.make_addplot(buy_series,  type='scatter', marker='^', markersize=80, color='green'),
        mpf.make_addplot(sell_series, type='scatter', marker='v', markersize=80, color='red'),
    ]

    mpf.plot(
        df,
        type='candle',
        volume=True,
        style='charles',
        addplot=apds,
        title='Candlestick Chart with Buy/Sell Signals'
    )
    
def draw_candlestick_plotly1(stock_records: List[StockRecord], list_point: List[float]):
    if len(stock_records) != len(list_point):
        raise ValueError("Length mismatch")

    df = pd.DataFrame({
        "Date": [r.date for r in stock_records],
        "Open": [r.priceOpen for r in stock_records],
        "High": [r.priceHigh for r in stock_records],
        "Low": [r.priceLow for r in stock_records],
        "Close": [r.priceClose for r in stock_records],
    })

    # Tìm điểm mua / bán
    buy_mask = np.array(list_point) >= 4
    sell_mask = np.array(list_point) <= -4

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

    # Chấm mua (màu xanh)
    fig.add_trace(go.Scatter(
        x=df["Date"][buy_mask],
        y=df["Low"][buy_mask] * 0.995,
        mode='markers',
        marker=dict(color='green', size=10, symbol='triangle-up'),
        name='Buy Signal'
    ))

    # Chấm bán (màu đỏ)
    fig.add_trace(go.Scatter(
        x=df["Date"][sell_mask],
        y=df["High"][sell_mask] * 1.005,
        mode='markers',
        marker=dict(color='red', size=10, symbol='triangle-down'),
        name='Sell Signal'
    ))

    fig.update_layout(title='Candlestick Chart with Buy/Sell Signals (Plotly)',
                      xaxis_title='Date', yaxis_title='Price',
                      xaxis_rangeslider_visible=False)

    fig.write_html("candlestick_chart.html", auto_open=False)
    open_html_in_chrome("candlestick_chart.html")
    
def draw_candlestick_plotly(stock_records: List[StockRecord], list_point: List[float]): 
    if len(stock_records) != len(list_point):
        raise ValueError("Length mismatch")

    df = pd.DataFrame({
        "Date": [r.date for r in stock_records],
        "Open": [r.priceOpen for r in stock_records],
        "High": [r.priceHigh for r in stock_records],
        "Low": [r.priceLow for r in stock_records],
        "Close": [r.priceClose for r in stock_records],
        "AdjRatio": [r.adjRatio for r in stock_records],
    })

    # Tìm điểm mua / bán
    lower_therious = np.min(list_point)
    higher_therious = np.max(list_point)
    print(f"Lower threshold: {lower_therious}, \nHigher threshold: {higher_therious}")
    buy_mask = np.array(list_point) == 6
    sell_mask = np.array(list_point) <= lower_therious

    # Tìm ngày điều chỉnh giá (khi AdjRatio thay đổi so với phiên trước)
    adjustment_mask = [False]
    for i in range(1, len(df)):
        prev_ratio = df["AdjRatio"].iloc[i - 1]
        curr_ratio = df["AdjRatio"].iloc[i]
        
        if prev_ratio == 0:
            adjustment_mask.append(False)
        else:
            change_pct = ((curr_ratio - prev_ratio) / prev_ratio) * 100
            if change_pct != 0:
                adjustment_mask.append(True)
                print(f"Adjustment at {df['Date'].iloc[i]}: {change_pct:+.2f}% (from {prev_ratio} to {curr_ratio})")
            else:
                adjustment_mask.append(False)

    adjustment_mask = np.array(adjustment_mask)

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
        x=df["Date"][buy_mask],
        y=df["Low"][buy_mask] * 0.995,
        mode='markers',
        marker=dict(color='green', size=10, symbol='triangle-up'),
        name='Mua'
    ))

    # Chấm bán (đỏ)
    fig.add_trace(go.Scatter(
        x=df["Date"][sell_mask],
        y=df["High"][sell_mask] * 1.005,
        mode='markers',
        marker=dict(color='red', size=10, symbol='triangle-down'),
        name='Ban'
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
    fig.add_trace(go.Bar(
        x=df["Date"],
        y=df["Volume"] if "Volume" in df.columns else [r.totalVolume for r in stock_records],
        marker_color='blue',
        name='Volume',
        yaxis='y2',
    ))

    # Thiết lập trục phụ cho khối lượng
    fig.update_layout(
        yaxis2=dict(
            title='Volume',
            overlaying='y',
            side='right',
            showgrid=False,
            position=1.0,
            range=[0, max(df["Volume"] if "Volume" in df.columns else [r.totalVolume for r in stock_records]) * 4],
        ),
        legend=dict(orientation="h"),
    )
    # Đường trung bình khối lượng (EMA 5 phiên)
    volume_series = df["Volume"] if "Volume" in df.columns else pd.Series([r.totalVolume for r in stock_records])
    ema_volume = volume_series.ewm(span=14, adjust=False).mean()

    fig.add_trace(go.Scatter(
        x=df["Date"],
        y=ema_volume,
        mode='lines',
        line=dict(color='magenta', width=2, dash='dash'),
        name='EMA Volume (5 days)',
        yaxis='y2'
    ))
    
    fig.update_layout(title='Candlestick Chart with Buy/Sell/Adjustment Signals (Plotly)',
                      xaxis_title='Date', yaxis_title='Price',
                      xaxis_rangeslider_visible=False)

    fig.write_html("candlestick_chart.html", auto_open=False)
    open_html_in_chrome("candlestick_chart.html")

  