from src.base.load_stock_data import load_stock_data
from datetime import datetime, date, timedelta

def main1():
    import streamlit as st
    import pandas as pd
    import ta

    st.title("Dự báo xu hướng cổ phiếu")

    symbol = st.text_input("Nhập mã cổ phiếu:")
    uploaded_file = st.file_uploader("Upload file dữ liệu (.csv)", type="csv")

    if uploaded_file and symbol:
        df = pd.read_csv(uploaded_file)
        df['RSI'] = ta.momentum.RSIIndicator(close=df['close']).rsi()
        df['MACD'] = ta.trend.MACD(close=df['close']).macd_diff()
        st.line_chart(df[['close', 'RSI', 'MACD']])
        st.write(">> Dự đoán: **Tăng**")


def main():
    from pathlib import Path
    root = Path(__file__).resolve().parent

    # Lấy từ 2021-01-01 đến hết
    recs_from_jan = load_stock_data(root, '2021-01-01')
    print(f'From 2021-01-01 đến nay: {len(recs_from_jan)} records')
    print(recs_from_jan[:5])
            
if __name__ == '__main__':
    main1()
