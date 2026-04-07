import os
import webbrowser
from datetime import datetime
from typing import List

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.models.trade_record import TradeRecord
from src.data.stock_data_loader import StockRecord
from src.analysis.market_behavior_analyzer import MarketBehaviorSnapshot


def open_html_in_chrome(path_to_html: str):
    chrome_path = r'"C:\Program Files\Google\Chrome\Application\chrome.exe" %s'
    webbrowser.get(chrome_path).open("file://" + os.path.realpath(path_to_html))


def draw_candlestick_plotly(
    stock_records: List[StockRecord],
    market_behavior: MarketBehaviorSnapshot,
    actual_sale_point: List[int],
    actual_buy_point: List[int],
) -> go.Figure:
    sale_point = market_behavior.sale_point
    buy_point = market_behavior.buy_point
    big_buyer = market_behavior.big_buyer
    fomo_retail = market_behavior.fomo_retail
    ema_volume = market_behavior.ema_volume
    total_volume = market_behavior.total_volume
    ema20 = market_behavior.ema20
    ema50 = market_behavior.ema50
    signal_reasons = market_behavior.signal_reasons
    signal_scores = market_behavior.signal_scores

    actual_sale_point_converted = [
        actual_sale_point[i] in (1, -1) for i in range(len(stock_records))
    ]
    actual_buy_point_converted = [
        actual_buy_point[i] == 1 for i in range(len(stock_records))
    ]

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

    df = pd.DataFrame(
        {
            "Date": [record.date for record in stock_records],
            "Open": [record.priceOpen for record in stock_records],
            "High": [record.priceHigh for record in stock_records],
            "Low": [record.priceLow for record in stock_records],
            "Close": [record.priceClose for record in stock_records],
            "AvgPrice": [record.priceAverage for record in stock_records],
        }
    )

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.7, 0.3],
        vertical_spacing=0.03,
    )

    fig.add_trace(
        go.Candlestick(
            x=df["Date"],
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name="Candlestick",
        ),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=df["Date"],
            y=ema20,
            mode="lines",
            line=dict(color="#1f77b4", width=1.5),
            name="EMA20",
        ),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=df["Date"],
            y=ema50,
            mode="lines",
            line=dict(color="#ff7f0e", width=1.5),
            name="EMA50",
        ),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=df["Date"][buy_point],
            y=df["Low"][buy_point] * 0.995,
            mode="markers",
            marker=dict(color="green", size=10, symbol="triangle-up"),
            text=[
                f"Score {signal_scores[i]:.2f}<br>{signal_reasons[i]}"
                for i, flag in enumerate(buy_point)
                if flag
            ],
            hovertemplate="%{text}<extra>Mua</extra>",
            name="Mua",
        ),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=df["Date"][sale_point],
            y=df["High"][sale_point] * 1.005,
            mode="markers",
            marker=dict(color="red", size=10, symbol="triangle-down"),
            text=[
                f"Score {signal_scores[i]:.2f}<br>{signal_reasons[i]}"
                for i, flag in enumerate(sale_point)
                if flag
            ],
            hovertemplate="%{text}<extra>Bán</extra>",
            name="Bán",
        ),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=df["Date"][actual_buy_point_converted],
            y=df["AvgPrice"][actual_buy_point_converted],
            mode="markers",
            marker=dict(color="blue", size=10, symbol="circle"),
            name="Mua Thực Tế",
        ),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=df["Date"][actual_sale_point_converted],
            y=df["AvgPrice"][actual_sale_point_converted],
            mode="markers",
            marker=dict(color="#FF9900", size=10, symbol="circle"),
            name="Bán Thực Tế",
        ),
        row=1, col=1,
    )

    volume_colors = []
    for index in range(len(stock_records)):
        if big_buyer[index] and not fomo_retail[index]:
            volume_colors.append("green")
        elif not big_buyer[index] and fomo_retail[index]:
            volume_colors.append("red")
        elif big_buyer[index] and fomo_retail[index]:
            volume_colors.append("blue")
        else:
            volume_colors.append("purple")

    fig.add_trace(
        go.Bar(
            x=df["Date"],
            y=total_volume,
            marker_color=volume_colors,
            name="Volume",
        ),
        row=2, col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=df["Date"],
            y=ema_volume,
            mode="lines",
            line=dict(color="magenta", width=2, dash="dash"),
            name="EMA Volume (14 days)",
        ),
        row=2, col=1,
    )

    symbol = stock_records[-1].symbol
    padding_days = max(5, len(stock_records) // 20)
    x_start = df["Date"].iloc[0]
    x_end = df["Date"].iloc[-1] + pd.Timedelta(days=padding_days)

    fig.update_layout(
        title=f"[{symbol}] Từ {stock_records[0].date.strftime('%Y-%m-%d')} đến {stock_records[-1].date.strftime('%Y-%m-%d')}",
        yaxis_title="Price",
        yaxis2_title="Khối lượng",
        legend=dict(orientation="h"),
        xaxis=dict(type="date", range=[x_start, x_end]),
        xaxis2=dict(type="date", range=[x_start, x_end]),
    )
    fig.update_xaxes(rangeslider_visible=False)
    return fig


def table_fynance(list_fynance: List[TradeRecord]) -> go.Figure:
    header = dict(
        values=["Buy Date", "Sale Date", "Profit", "Cash", "Buy Value", "Buy Volume", "Sale Value"],
        fill_color="paleturquoise",
        align="left",
    )
    buy_dates = [record.date_buy.strftime("%Y-%m-%d") for record in list_fynance]
    sale_dates = [record.date_sale.strftime("%Y-%m-%d") for record in list_fynance]
    profits = [record.profit for record in list_fynance]
    cashes = [record.cash for record in list_fynance]
    buy_values = [record.buy_value for record in list_fynance]
    buy_volumes = [record.buy_volume for record in list_fynance]
    sale_values = [record.sale_value for record in list_fynance]

    cells = dict(
        values=[buy_dates, sale_dates, profits, cashes, buy_values, buy_volumes, sale_values],
        fill_color="lavender",
        align="left",
    )

    fig = go.Figure(data=[go.Table(header=header, cells=cells)])
    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        height=400 + 30 * len(list_fynance),
    )
    return fig


def render_backtest_chart(
    stock_records: List[StockRecord],
    market_behavior: MarketBehaviorSnapshot,
    actual_sale_point: List[int],
    actual_buy_point: List[int],
    list_fynance: List[TradeRecord],
) -> None:
    fig_candlestick = draw_candlestick_plotly(
        stock_records,
        market_behavior,
        actual_sale_point,
        actual_buy_point,
    )
    total_profit = sum(record.profit for record in list_fynance)
    fig_candlestick.add_annotation(
        text=f"Realized PnL: {total_profit:.2f}",
        xref="paper",
        yref="paper",
        x=0.99,
        y=1.08,
        showarrow=False,
        bgcolor="rgba(255,255,255,0.8)",
    )

    current_date_str = datetime.now().strftime("%Y-%m-%d")
    output_dir = os.path.join("chart", current_date_str)
    os.makedirs(output_dir, exist_ok=True)

    file_name = (
        f"{stock_records[-1].symbol}_"
        f"{stock_records[0].date.strftime('%Y-%m-%d')}_"
        f"{stock_records[-1].date.strftime('%Y-%m-%d')}.html"
    )
    output_path = os.path.join(output_dir, file_name)
    fig_candlestick.write_html(output_path, auto_open=False)
    open_html_in_chrome(output_path)


draw_chart = render_backtest_chart
