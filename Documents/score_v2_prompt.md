# Prompt Xay Dung Score V2

Ban la mot senior quantitative developer dang nang cap he thong cham diem tin hieu giao dich co phieu trong repo nay.

Bo canh:
- Du lieu dau vao la `List[StockRecord]`.
- He thong hien tai tinh `SignalScore` trong `src/analysis/signal_scoring.py`.
- Luong su dung hien tai:
  - `src/backtesting/backtest_runner.py` build score theo tung ngay
  - `src/analysis/market_behavior_analyzer.py` doi score thanh `buy_point` va `sale_point`
  - `src/backtesting/trade_simulator.py` dung cac diem nay de mo phong giao dich
- Score v1 hien tai gom:
  - `candle_score`
  - `volume_score`
  - `context_score`
  - `pivot_score`
  - `final_score`

Muc tieu cua ban:
- Thiet ke `score v2` chat che hon, giam nhieu, va de backtest.
- Khong pha vo interface chinh neu khong can thiet.
- Uu tien giai thich ro logic, cong thuc, va cac ly do thuc chien.

Yeu cau bat buoc:
1. Tao score cho tung ngay dua tren lich su toi ngay do, khong duoc nhin du lieu tuong lai.
2. Tach ro `setup_score` va `trigger_score`.
3. Ho tro ca hai huong:
   - bullish reversal / bullish continuation
   - bearish reversal / bearish continuation
4. Bo sung cac nhom xac nhan:
   - trend strength
   - momentum
   - volume quality
   - support/resistance or swing structure
   - follow-through / breakout confirmation
5. Cac thanh phan moi phai co:
   - ten
   - cong thuc
   - mien gia tri
   - cach chuan hoa ve 0..1 hoac -1..1
6. Trong so phai dua vao file config, khong hard-code trong ham chinh.
7. Tra ve giai thich cho moi score:
   - label
   - final_score
   - sub_scores
   - reasons
   - blockers
8. Cho phep bat/tat tung bo loc.
9. De xuat cach backtest, do hit-rate, expectancy, max drawdown, va profit factor.
10. Neu mot phan khong du du lieu thi phai co co che fallback ro rang.

Chi bao uu tien can xem xet:
- EMA20, EMA50, EMA100
- ATR14
- RSI14
- MACD line / signal / histogram
- ADX14
- OBV hoac CMF hoac MFI
- Relative volume
- Swing high / swing low 10, 20 phien
- Breakout close, retest, follow-through 1-2 phien

Nguyen tac thiet ke:
- Don gian truoc, on dinh truoc, toi uu sau.
- Moi score thanh phan phai giai thich duoc theo ngon ngu giao dich.
- Tranh overfit vao 1 ma co phieu.
- Uu tien scale theo lich su rieng tung ma bang percentile, z-score, hoac threshold mem.
- Phan biet setup dep va trigger vao lenh.
- Khong duoc dua ra chi bao de co cho du.

Dau ra mong muon:
1. De xuat cau truc du lieu moi cho `SignalScoreV2`.
2. Liet ke cac ham can them/sua trong:
   - `src/analysis/technical_indicators.py`
   - `src/analysis/signal_scoring.py`
   - `src/analysis/market_behavior_analyzer.py`
   - `src/backtesting/backtest_runner.py`
3. Dua ra cong thuc `final_score`.
4. Dua ra cong thuc `setup_score` va `trigger_score`.
5. De xuat default thresholds.
6. De xuat bo test va backtest toi thieu.
7. Neu thay can, de xuat file config moi vi du:
   - `src/analysis/score_config.py`

Rang buoc coding:
- Python ro rang, tach ham nho.
- Comment ngan gon, dung o cho logic khong tu nhien.
- Ten bien nhat quan voi codebase hien tai.
- Khong doi format `StockRecord`.
- Han che thay doi API cong khai neu khong can.

Hay tra loi theo cau truc:
1. Tong quan score v2
2. Thanh phan va cong thuc
3. Kien truc file can sua
4. Pseudocode
5. Ke hoach backtest va tuning

