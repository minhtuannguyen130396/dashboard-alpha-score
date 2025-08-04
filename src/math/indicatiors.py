from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass
from datetime import datetime
import math
import statistics
from src.base.load_stock_data import StockRecord

# Helper to extract list of floats
def _extract(records: List[StockRecord], attr: str) -> List[float]:
    return [getattr(r, attr) for r in records]
def average_volume(records: List[StockRecord], period: int = 10) -> float:
    """Tính trung bình khối lượng trong n phiên gần nhất"""
    volumes = [r.totalVolume for r in records[-period:] if r.totalVolume is not None]
    if not volumes:
        return 0.0
    return sum(volumes) / len(volumes)

# =========================
# Nhóm 1: Trung bình động
# =========================
class IndicatorGroup1:
    @staticmethod
    def sma(records: List[StockRecord], period: int) -> List[Optional[float]]:
        """Tính Simple Moving Average"""
        closes = _extract(records, 'priceClose')
        result: List[Optional[float]] = []
        for i in range(len(closes)):
            if i + 1 < period:
                result.append(None)
            else:
                result.append(sum(closes[i+1-period:i+1]) / period)
        #print(f"[MATH][SMA] Last point: {result[-1]}")
        return result

    @staticmethod
    def ema(records: List[StockRecord], period: int) -> List[Optional[float]]:
        """Tính Exponential Moving Average"""
        closes = _extract(records, 'priceClose')
        k = 2 / (period + 1)
        ema_prev = None
        result: List[Optional[float]] = []
        for i, price in enumerate(closes):
            if i + 1 < period:
                result.append(None)
            elif i + 1 == period:
                ema_prev = sum(closes[:period]) / period
                result.append(ema_prev)
            else:
                ema_prev = price * k + ema_prev * (1 - k)  # type: ignore
                result.append(ema_prev)
        #print(f"[MATH][EMA] Last point: {result[-1]}")
        return result

    @staticmethod
    def wma(records: List[StockRecord], period: int) -> List[Optional[float]]:
        """Tính Weighted Moving Average"""
        closes = _extract(records, 'priceClose')
        result: List[Optional[float]] = []
        weights = list(range(1, period+1))
        wsum = sum(weights)
        for i in range(len(closes)):
            if i + 1 < period:
                result.append(None)
            else:
                window = closes[i+1-period:i+1]
                result.append(sum(v * w for v, w in zip(window, weights)) / wsum)
        #print(f"[MATH][WMA] Last point: {result[-1]}")
        return result

    @staticmethod
    def vwma(records: List[StockRecord], period: int) -> List[Optional[float]]:
        """Tính Volume Weighted Moving Average"""
        closes = _extract(records, 'priceClose')
        volumes = _extract(records, 'totalVolume')
        result: List[Optional[float]] = []
        for i in range(len(closes)):
            if i + 1 < period:
                result.append(None)
            else:
                c = closes[i+1-period:i+1]
                v = volumes[i+1-period:i+1]
                num = sum(ci * vi for ci, vi in zip(c, v))
                den = sum(v)
                result.append(num/den if den != 0 else None)
        #print(f"[MATH][VWMA] Last point: {result[-1]}")
        return result

    @staticmethod
    def hma(records: List[StockRecord], period: int) -> List[Optional[float]]:
        """Tính Hull Moving Average"""
        half = IndicatorGroup1.ema(records, period // 2)
        full = IndicatorGroup1.ema(records, period)
        diff = []
        for h, f in zip(half, full):
            diff.append((2*h - f) if h is not None and f is not None else None)
        # wrap dummy records
        class D: priceClose = 0
        diff_recs = [D() for _ in diff]
        for d, rec in zip(diff, diff_recs): rec.priceClose = d or 0
        result = IndicatorGroup1.ema(diff_recs, int(math.sqrt(period)))
        #print(f"[MATH][HMA] Last point: {result[-1]}")
        return result

    @staticmethod
    def kama(records: List[StockRecord], period: int, fast: int = 2, slow: int = 30) -> List[Optional[float]]:
        """Tính Kaufman Adaptive Moving Average"""
        closes = _extract(records, 'priceClose')
        result: List[Optional[float]] = []
        ama = closes[0]
        result.append(ama)
        for i in range(1, len(closes)):
            change = abs(closes[i] - closes[i-period]) if i>=period else 0
            volatility = sum(abs(closes[j] - closes[j-1]) for j in range(max(1, i-period), i+1))
            er = change/volatility if volatility else 0
            sc = (er*(2/(fast+1)-2/(slow+1))+2/(slow+1))**2
            ama = ama + sc*(closes[i] - ama)
            result.append(ama)
        #print(f"[MATH][KAMA] Last point: {result[-1]}")
        return result

# =========================
# Nhóm 2: Đà (Momentum)
# =========================
class IndicatorGroup2:
    @staticmethod
    def momentum(records: List[StockRecord], period: int) -> List[Optional[float]]:
        closes = _extract(records, 'priceClose')
        result: List[Optional[float]] = []
        for i in range(len(closes)):
            if i < period:
                result.append(None)
            else:
                result.append(closes[i] - closes[i-period])
        #print(f"[MATH][Momentum] Last point: {result[-1]}")
        return result

    @staticmethod
    def roc(records: List[StockRecord], period: int) -> List[Optional[float]]:
        closes = _extract(records, 'priceClose')
        result: List[Optional[float]] = []
        for i in range(len(closes)):
            if i < period or closes[i-period]==0:
                result.append(None)
            else:
                result.append((closes[i]-closes[i-period])/closes[i-period]*100)
        #print(f"[MATH][ROC] Last point: {result[-1]}")
        return result

    @staticmethod
    def cci(records: List[StockRecord], period: int) -> List[Optional[float]]:
        tp = [(r.priceHigh+r.priceLow+r.priceClose)/3 for r in records]
        result: List[Optional[float]] = []
        for i in range(len(tp)):
            if i+1<period:
                result.append(None)
            else:
                window=tp[i+1-period:i+1]
                ma=sum(window)/period
                md=sum(abs(x-ma) for x in window)/period
                result.append((tp[i]-ma)/(0.015*md) if md else None)
        #print(f"[MATH][CCI] Last point: {result[-1]}")
        return result

    @staticmethod
    def stochastic_k(records: List[StockRecord], period: int) -> List[Optional[float]]:
        result: List[Optional[float]] = []
        for i in range(len(records)):
            if i+1<period:
                result.append(None)
            else:
                high=max(r.priceHigh for r in records[i+1-period:i+1])
                low=min(r.priceLow for r in records[i+1-period:i+1])
                close=records[i].priceClose
                result.append((close-low)/(high-low)*100 if high!=low else None)
        #print(f"[MATH][Stoch%K] Last point: {result[-1]}")
        return result

    @staticmethod
    def stochastic_d(records: List[StockRecord], period_k: int, period_d: int) -> List[Optional[float]]:
        k=IndicatorGroup2.stochastic_k(records, period_k)
        result: List[Optional[float]] = []
        for i in range(len(k)):
            if k[i] is None or i+1<period_d:
                result.append(None)
            else:
                window=[x for x in k[i+1-period_d:i+1] if x is not None]
                result.append(sum(window)/len(window) if window else None)
        #print(f"[MATH][Stoch%D] Last point: {result[-1]}")
        return result

    @staticmethod
    def williams_r(records: List[StockRecord], period: int) -> List[Optional[float]]:
        result: List[Optional[float]] = []
        for i in range(len(records)):
            if i+1<period:
                result.append(None)
            else:
                high=max(r.priceHigh for r in records[i+1-period:i+1])
                low=min(r.priceLow for r in records[i+1-period:i+1])
                result.append((high-records[i].priceClose)/(high-low)*-100 if high!=low else None)
        #print(f"[MATH][Williams%R] Last point: {result[-1]}")
        return result

    @staticmethod
    def ult_osc(records: List[StockRecord], p1: int=7, p2: int=14, p3: int=28) -> List[Optional[float]]:
        bp=[]; tr=[]; result: List[Optional[float]] = []
        for i in range(len(records)):
            if i==0: bp.append(0); tr.append(records[i].priceHigh-records[i].priceLow)
            else:
                bp.append(records[i].priceClose-min(records[i].priceLow,records[i-1].priceClose))
                tr.append(max(records[i].priceHigh-records[i].priceLow,
                              abs(records[i].priceHigh-records[i-1].priceClose),
                              abs(records[i].priceLow-records[i-1].priceClose)))
        for i in range(len(bp)):
            if i+1< p3: result.append(None)
            else:
                avg1=sum(bp[i+1-p1:i+1])/sum(tr[i+1-p1:i+1]) if sum(tr[i+1-p1:i+1]) else 0
                avg2=sum(bp[i+1-p2:i+1])/sum(tr[i+1-p2:i+1]) if sum(tr[i+1-p2:i+1]) else 0
                avg3=sum(bp[i+1-p3:i+1])/sum(tr[i+1-p3:i+1]) if sum(tr[i+1-p3:i+1]) else 0
                result.append((4*avg1+2*avg2+avg3)/7*100)
        #print(f"[MATH][UltOsc] Last point: {result[-1]}")
        return result

    @staticmethod
    def macd(records: List[StockRecord], fast:int=12, slow:int=26, signal:int=9) -> Tuple[List[Optional[float]],List[Optional[float]],List[Optional[float]]]:
        fast_ = IndicatorGroup2.ema(records, fast)
        slow_ = IndicatorGroup2.ema(records, slow)
        macd_line=[(f-s) if f is not None and s is not None else None for f,s in zip(fast_, slow_)]
        class D: priceClose=0
        recs=[D() for _ in macd_line]
        for v,r in zip(macd_line,recs): r.priceClose=v or 0
        sig=IndicatorGroup2.ema(recs, signal)
        hist=[(m-s) if m is not None and s is not None else None for m,s in zip(macd_line, sig)]
        #print(f"[MATH][MACD] Last MACD: {macd_line[-1]}, Signal: {sig[-1]}, Histogram: {hist[-1]}")
        return macd_line, sig, hist

    @staticmethod
    def ema(records: List[StockRecord], period: int) -> List[Optional[float]]:
        closes = _extract(records, 'priceClose')
        k = 2 / (period + 1)
        ema_prev = None
        result: List[Optional[float]] = []
        for i, price in enumerate(closes):
            if i + 1 < period:
                result.append(None)
            elif i + 1 == period:
                ema_prev = sum(closes[:period]) / period
                result.append(ema_prev)
            else:
                ema_prev = price * k + ema_prev * (1 - k)  # type: ignore
                result.append(ema_prev)
        return result
    @staticmethod
    def momentum(records: List[StockRecord], period: int) -> List[Optional[float]]:
        """Tính Momentum"""
        closes = _extract(records, 'priceClose')
        result: List[Optional[float]] = []
        for i in range(len(closes)):
            if i < period:
                result.append(None)
            else:
                result.append(closes[i] - closes[i-period])
        #print(f"[MATH][Momentum] Last point: {result[-1]}")
        return result

    @staticmethod
    def roc(records: List[StockRecord], period: int) -> List[Optional[float]]:
        """Tính Rate of Change"""
        closes = _extract(records, 'priceClose')
        result: List[Optional[float]] = []
        for i in range(len(closes)):
            if i < period or closes[i-period]==0:
                result.append(None)
            else:
                result.append((closes[i]-closes[i-period])/closes[i-period]*100)
        #print(f"[MATH][ROC] Last point: {result[-1]}")
        return result

    @staticmethod
    def cci(records: List[StockRecord], period: int) -> List[Optional[float]]:
        """Tính Commodity Channel Index"""
        tp = [(r.priceHigh+r.priceLow+r.priceClose)/3 for r in records]
        result: List[Optional[float]] = []
        for i in range(len(tp)):
            if i+1<period:
                result.append(None)
            else:
                window=tp[i+1-period:i+1]
                ma=sum(window)/period
                md=sum(abs(x-ma) for x in window)/period
                result.append((tp[i]-ma)/(0.015*md) if md else None)
        #print(f"[MATH][CCI] Last point: {result[-1]}")
        return result

    @staticmethod
    def stochastic_k(records: List[StockRecord], period: int) -> List[Optional[float]]:
        """Tính Stochastic %K"""
        result: List[Optional[float]] = []
        for i in range(len(records)):
            if i+1<period:
                result.append(None)
            else:
                high=max(r.priceHigh for r in records[i+1-period:i+1])
                low=min(r.priceLow for r in records[i+1-period:i+1])
                close=records[i].priceClose
                result.append((close-low)/(high-low)*100 if high!=low else None)
        #print(f"[MATH][Stoch%K] Last point: {result[-1]}")
        return result


    @staticmethod
    def stochastic_d(records: List[StockRecord], period_k: int, period_d: int) -> List[Optional[float]]:
        """Tính Stochastic %D"""
        k=IndicatorGroup2.stochastic_k(records, period_k)
        result: List[Optional[float]] = []
        for i in range(len(k)):
            if k[i] is None or i+1<period_d:
                result.append(None)
            else:
                window=[x for x in k[i+1-period_d:i+1] if x is not None]
                result.append(sum(window)/len(window) if window else None)
        #print(f"[MATH][Stoch%D] Last point: {result[-1]}")
        return result

    @staticmethod
    def williams_r(records: List[StockRecord], period: int) -> List[Optional[float]]:
        """Tính Williams %R"""
        result: List[Optional[float]] = []
        for i in range(len(records)):
            if i+1<period:
                result.append(None)
            else:
                high=max(r.priceHigh for r in records[i+1-period:i+1])
                low=min(r.priceLow for r in records[i+1-period:i+1])
                result.append((high-records[i].priceClose)/(high-low)*-100 if high!=low else None)
        #print(f"[MATH][Williams%R] Last point: {result[-1]}")
        return result

    @staticmethod
    def ult_osc(records: List[StockRecord], p1: int=7, p2: int=14, p3: int=28) -> List[Optional[float]]:
        """Tính Ultimate Oscillator"""
        bp=[]; tr=[]; result: List[Optional[float]] = []
        for i in range(len(records)):
            if i==0: bp.append(0); tr.append(records[i].priceHigh-records[i].priceLow)
            else:
                bp.append(records[i].priceClose-min(records[i].priceLow,records[i-1].priceClose))
                tr.append(max(records[i].priceHigh-records[i].priceLow,
                            abs(records[i].priceHigh-records[i-1].priceClose),
                            abs(records[i].priceLow-records[i-1].priceClose)))
        for i in range(len(bp)):
            if i+1< p3: result.append(None)
            else:
                avg1=sum(bp[i+1-p1:i+1])/sum(tr[i+1-p1:i+1]) if sum(tr[i+1-p1:i+1]) else 0
                avg2=sum(bp[i+1-p2:i+1])/sum(tr[i+1-p2:i+1]) if sum(tr[i+1-p2:i+1]) else 0
                avg3=sum(bp[i+1-p3:i+1])/sum(tr[i+1-p3:i+1]) if sum(tr[i+1-p3:i+1]) else 0
                result.append((4*avg1+2*avg2+avg3)/7*100)
        #print(f"[MATH][UltOsc] Last point: {result[-1]}")
        return result

    @staticmethod
    def macd(records: List[StockRecord], fast:int=12, slow:int=26, signal:int=9) -> Tuple[List[Optional[float]],List[Optional[float]],List[Optional[float]]]:
        """Tính MACD, Signal line và Histogram"""
        fast_ = IndicatorGroup1.ema(records, fast); slow_ = IndicatorGroup1.ema(records, slow)
        macd_line=[(f-s) if f is not None and s is not None else None for f,s in zip(fast_, slow_)]
        class D: priceClose=0
        recs=[D() for _ in macd_line]
        for v,r in zip(macd_line,recs): r.priceClose=v or 0
        sig=IndicatorGroup1.ema(recs, signal)
        hist=[(m-s) if m is not None and s is not None else None for m,s in zip(macd_line, sig)]
        #print(f"[MATH][MACD] Last MACD: {macd_line[-1]}, Signal: {sig[-1]}, Histogram: {hist[-1]}")
        return macd_line, sig, hist

# =========================
# Nhóm 3: Biến động
# =========================
class IndicatorGroup3:
    @staticmethod
    def atr(records: List[StockRecord], period: int) -> List[Optional[float]]:
        """Tính Average True Range"""
        tr=[]; result=[None]
        for i in range(1,len(records)):
            h,l,pc=records[i].priceHigh,records[i].priceLow,records[i-1].priceClose
            tr.append(max(h-l,abs(h-pc),abs(l-pc)))
        for i in range(len(tr)):
            if i+1<period: result.append(None)
            else: result.append(sum(tr[i+1-period:i+1])/period)
        #print(f"[MATH][ATR] Last point: {result[-1]}")
        return result

    @staticmethod
    def bollinger_bands(records: List[StockRecord], period:int, num_std:float=2) -> Tuple[List[Optional[float]],List[Optional[float]],List[Optional[float]]]:
        """Tính Bollinger Bands"""
        mid=IndicatorGroup1.sma(records,period); up=[]; down=[]
        closes=_extract(records,'priceClose')
        for i in range(len(closes)):
            if i+1<period: up.append(None); down.append(None)
            else:
                window=closes[i+1-period:i+1]
                sd=statistics.pstdev(window)
                up.append(mid[i]+num_std*sd)  # type: ignore
                down.append(mid[i]-num_std*sd)
        #print(f"[MATH][Bollinger] Last Upper: {up[-1]}, Middle: {mid[-1]}, Lower: {down[-1]}")
        return up, mid, down

    @staticmethod
    def keltner_channel(records: List[StockRecord], period: int, factor: float = 2) -> Tuple[List[Optional[float]],List[Optional[float]],List[Optional[float]]]:
        """Tính Keltner Channel"""
        ema_mid=IndicatorGroup1.ema(records, period)
        atr_ = IndicatorGroup3.atr(records, period)
        up=[]; mid=ema_mid; down=[]
        for m,a in zip(ema_mid, atr_):
            if m is None or a is None: up.append(None); down.append(None)
            else: up.append(m+factor*a); down.append(m-factor*a)
        #print(f"[MATH][Keltner] Last Upper: {up[-1]}, Middle: {mid[-1]}, Lower: {down[-1]}")
        return up, mid, down

    @staticmethod
    def donchian_channel(records: List[StockRecord], period: int) -> Tuple[List[Optional[float]],List[Optional[float]]]:
        """Tính Donchian Channel"""
        up=[]; down=[]
        for i in range(len(records)):
            if i+1<period: up.append(None); down.append(None)
            else:
                high=max(r.priceHigh for r in records[i+1-period:i+1])
                low=min(r.priceLow for r in records[i+1-period:i+1])
                up.append(high); down.append(low)
        #print(f"[MATH][Donchian] Last Upper: {up[-1]}, Lower: {down[-1]}")
        return up, down

    @staticmethod
    def std_dev(records: List[StockRecord], period: int) -> List[Optional[float]]:
        """Tính độ lệch chuẩn"""
        closes=_extract(records,'priceClose')
        result=[]
        for i in range(len(closes)):
            if i+1<period: result.append(None)
            else: result.append(statistics.pstdev(closes[i+1-period:i+1]))
        #print(f"[MATH][StdDev] Last point: {result[-1]}")
        return result

    @staticmethod
    def mass_index(records: List[StockRecord], period: int = 25, ema_period: int = 9) -> List[Optional[float]]:
        """Tính Mass Index"""
        # Tính high-low range cho mỗi phiên
        hr = [r.priceHigh - r.priceLow for r in records]
        # EMA đầu tiên của hr
        k = 2 / (ema_period + 1)
        ema1: List[float] = []
        for i, x in enumerate(hr):
            if i == 0:
                ema1.append(x)
            else:
                ema1.append(x * k + ema1[-1] * (1 - k))
        # EMA thứ hai của ema1
        ema2: List[float] = []
        for i, x in enumerate(ema1):
            if i == 0:
                ema2.append(x)
            else:
                ema2.append(x * k + ema2[-1] * (1 - k))
        # Tính Mass Index: tổng tỷ lệ ema1/ema2 trong khoảng period
        result: List[Optional[float]] = []
        for i in range(len(records)):
            if i + 1 < period:
                result.append(None)
            else:
                window = []
                for j in range(i + 1 - period, i + 1):
                    if ema2[j] != 0:
                        window.append(ema1[j] / ema2[j])
                    else:
                        window.append(0)
                result.append(sum(window))
        #print(f"[MATH][MassIndex] Last point: {result[-1]}")
        return result

    @staticmethod
    def chaikin_volatility(
        records: List[StockRecord],
        period_fast: int = 10,
        period_slow: int = 20
    ) -> List[Optional[float]]:
        """Tính Chaikin Volatility"""
        # Tính khoảng cách high - low cho mỗi phiên
        hr = [r.priceHigh - r.priceLow for r in records]
        # Tạo dummy records để dùng hàm EMA
        class D:
            def __init__(self, v: float):
                self.priceClose = v
        hr_recs = [D(x) for x in hr]
        # EMA chu kỳ dài và ngắn
        ema_long = IndicatorGroup1.ema(hr_recs, period_slow)
        ema_short = IndicatorGroup1.ema(hr_recs, period_fast)
        # Tính Chaikin Volatility = (EMA_short - EMA_long) / EMA_long * 100
        result: List[Optional[float]] = []
        for long_val, short_val in zip(ema_long, ema_short):
            if long_val is None or long_val == 0 or short_val is None:
                result.append(None)
            else:
                result.append((short_val - long_val) / long_val * 100)
        #print(f"[MATH][ChaikinVolatility] Last point: {result[-1]}")
        return result
# =========================
# Nhóm 4: Volume-Based Indicators (Chỉ báo khối lượng)
# =========================
class IndicatorGroup4:
    @staticmethod
    def obv(records: List[StockRecord]) -> List[int]:
        """Tính On-Balance Volume"""
        result: List[int] = []
        obv_val = 0
        for i in range(1, len(records)):
            if records[i].priceClose > records[i-1].priceClose:
                obv_val += int(records[i].totalVolume)
            elif records[i].priceClose < records[i-1].priceClose:
                obv_val -= int(records[i].totalVolume)
            result.append(obv_val)
        #print(f"[MATH][OBV] Last point: {result[-1]}")
        return result

    @staticmethod
    def ad_line(records: List[StockRecord]) -> List[float]:
        """Tính Accumulation/Distribution Line"""
        result: List[float] = []
        ad_val = 0.0
        for r in records:
            high, low, close, volume = r.priceHigh, r.priceLow, r.priceClose, r.totalVolume
            if high != low:
                mfm = ((close - low) - (high - close)) / (high - low)
            else:
                mfm = 0.0
            mfv = mfm * volume
            ad_val += mfv
            result.append(ad_val)
        #print(f"[MATH][AccDistLine] Last point: {result[-1]}")
        return result

    @staticmethod
    def chaikin_money_flow(records: List[StockRecord], period: int = 20) -> List[Optional[float]]:
        """Tính Chaikin Money Flow"""
        mfv: List[float] = []
        vol: List[float] = []
        for r in records:
            tp = (r.priceHigh + r.priceLow + r.priceClose) / 3
            volume = r.totalVolume
            if r.priceHigh != r.priceLow:
                mfm = ((r.priceClose - r.priceLow) - (r.priceHigh - r.priceClose)) / (r.priceHigh - r.priceLow)
            else:
                mfm = 0.0
            mfv.append(mfm * volume)
            vol.append(volume)
        result: List[Optional[float]] = []
        for i in range(len(records)):
            if i + 1 < period:
                result.append(None)
            else:
                window_mfv = sum(mfv[i+1-period:i+1])
                window_vol = sum(vol[i+1-period:i+1])
                result.append(window_mfv / window_vol if window_vol != 0 else None)
        #print(f"[MATH][CMF] Last point: {result[-1]}")
        return result

    @staticmethod
    def mfi(records: List[StockRecord], period: int = 14) -> List[Optional[float]]:
        """Tính Money Flow Index"""
        tp: List[float] = []
        for r in records:
            tp.append((r.priceHigh + r.priceLow + r.priceClose) / 3)
        mf: List[float] = []
        for i in range(1, len(records)):
            if tp[i] > tp[i-1]:
                mf.append(tp[i] * records[i].totalVolume)
            else:
                mf.append(-tp[i] * records[i].totalVolume)
        result: List[Optional[float]] = [None]
        for i in range(len(mf)):
            if i + 1 < period:
                result.append(None)
            else:
                pos_mf = sum(x for x in mf[i+1-period:i+1] if x > 0)
                neg_mf = abs(sum(x for x in mf[i+1-period:i+1] if x < 0))
                if neg_mf != 0:
                    mfr = pos_mf / neg_mf
                    result.append(100 - 100 / (1 + mfr))
                else:
                    result.append(None)
        #print(f"[MATH][MFI] Last point: {result[-1]}")
        return result

    @staticmethod
    def vroc(records: List[StockRecord], period: int = 12) -> List[Optional[float]]:
        """Tính Volume Rate of Change"""
        volumes = _extract(records, 'totalVolume')
        result: List[Optional[float]] = []
        for i in range(len(volumes)):
            if i < period or volumes[i-period] == 0:
                result.append(None)
            else:
                result.append((volumes[i] - volumes[i-period]) / volumes[i-period] * 100)
        #print(f"[MATH][VROC] Last point: {result[-1]}")
        return result

    @staticmethod
    def vwap(records: List[StockRecord]) -> List[Optional[float]]:
        """Tính Volume-Weighted Average Price"""
        result: List[Optional[float]] = []
        cum_vtp = 0.0
        cum_vol = 0.0
        for r in records:
            tp = (r.priceHigh + r.priceLow + r.priceClose) / 3
            cum_vtp += tp * r.totalVolume
            cum_vol += r.totalVolume
            result.append(cum_vtp / cum_vol if cum_vol != 0 else None)
        #print(f"[MATH][VWAP] Last point: {result[-1]}")
        return result
    @staticmethod 
    def is_big_buyer(records: List[StockRecord],pretiod :int = 14) -> List[bool]:
        """Kiểm tra xem có nhà đầu tư lớn mua vào hay không"""
        if not records:
            return False
        
        def average_buy_size(_records: List[StockRecord], _period: int = 14) -> float:
            buy_sizes = []
            for r in _records[-_period-1:-1]:  # lấy 10 phiên trước phiên hiện tại
                if r.buyCount and r.buyQuantity:
                    buy_sizes.append(r.buyQuantity / r.buyCount)
            if not buy_sizes:
                return 0.0
            return sum(buy_sizes) / len(buy_sizes)
        
        result : List[bool] = []
        for i, record in enumerate(records):
            if i <= pretiod:
                result.append(False)
            else:
                if record.propTradingNetValue and record.propTradingNetValue > 0:
                    result.append(True)
                    continue
                if record.buyForeignQuantity > record.sellForeignQuantity:
                    result.append(True)
                    continue
                if record.buyCount and record.buyQuantity:
                    avg_buy_size = record.buyQuantity / record.buyCount
                    if avg_buy_size > 1.5 * average_buy_size(_records= records,_period = pretiod):  # tuỳ theo mã cổ phiếu
                        result.append(True)
                        continue
                result.append(False)
                
        return result
    @staticmethod
    def is_fomo_by_retail(records: List[StockRecord],period:int = 14) -> List[bool]:
        """Kiểm tra xem có hiện tượng FOMO (Fear of Missing Out) từ nhà đầu tư nhỏ lẻ hay không"""
        if not records:
            return []
        result: List[bool] = []
        for index, record in enumerate(records):
            if index <= period:
                result.append(False)
                continue
            if record.totalVolume > 2 * average_volume(records, period):
            # nhưng không có tự doanh hoặc ngoại mua
                if (not record.propTradingNetValue or record.propTradingNetValue <= 0) and \
                    record.buyForeignQuantity <= record.sellForeignQuantity:
                    result.append(True)
                    continue
            result.append(False)
        return result
        
# =========================
# Nhóm 5: Breadth & Market-Strength (Độ rộng thị trường)
# =========================
class IndicatorGroup5:
    @staticmethod    
    def adv_decline_line(advances: List[int], declines: List[int]) -> List[int]:
        """Tính Advance/Decline Line: tích lũy chênh lệch số cổ phiếu tăng và giảm mỗi ngày"""
        result: List[int] = []
        cum = 0
        for a, d in zip(advances, declines):
            cum += (a - d)
            result.append(cum)
        #print(f"[MATH][AdvanceDeclineLine] Last point: {result[-1]}")
        return result

    @staticmethod
    def mcclellan_oscillator(advances: List[int], declines: List[int], short_period: int = 19, long_period: int = 39) -> List[Optional[float]]:
        """Tính McClellan Oscillator: hiệu EMA ngắn hạn và dài hạn của net advances"""
        net = [a - d for a, d in zip(advances, declines)]
        def ema_list(data: List[float], period: int) -> List[Optional[float]]:
            k = 2 / (period + 1)
            ema: List[Optional[float]] = []
            prev: Optional[float] = None
            for i, v in enumerate(data):
                if i + 1 < period:
                    ema.append(None)
                elif i + 1 == period:
                    sma = sum(data[:period]) / period
                    prev = sma
                    ema.append(sma)
                else:
                    prev = v * k + prev * (1 - k)  # type: ignore
                    ema.append(prev)
            return ema
        ema_short = ema_list(net, short_period)
        ema_long = ema_list(net, long_period)
        result: List[Optional[float]] = []
        for s, l in zip(ema_short, ema_long):
            if s is None or l is None:
                result.append(None)
            else:
                result.append(s - l)
        #print(f"[MATH][McClellanOscillator] Last point: {result[-1]}")
        return result

    @staticmethod
    def trin(advances: List[int], declines: List[int], vol_adv: List[float], vol_dec: List[float]) -> List[Optional[float]]:
        """Tính TRIN (Arms Index): (adv/dec)/(vol_adv/vol_dec)"""
        result: List[Optional[float]] = []
        for a, d, va, vd in zip(advances, declines, vol_adv, vol_dec):
            if d == 0 or vd == 0:
                result.append(None)
            else:
                result.append((a / d) / (va / vd))
        #print(f"[MATH][TRIN] Last point: {result[-1]}")
        return result

    @staticmethod
    def bullish_percent_index(bulls: List[int], total: List[int]) -> List[Optional[float]]:
        """Tính Bullish Percent Index: tỉ lệ % cổ phiếu trong xu hướng tăng"""
        result: List[Optional[float]] = []
        for b, t in zip(bulls, total):
            if t == 0:
                result.append(None)
            else:
                result.append(b / t * 100)
        #print(f"[MATH][BullishPercentIndex] Last point: {result[-1]}")
        return result

# =========================
# Nhóm 6: Các chỉ báo khác
# =========================
class IndicatorGroup6:
    @staticmethod
    def pivot_points(records: List[StockRecord]) -> List[Dict[str, float]]:
        """Tính Pivot Points và các mức hỗ trợ/kháng cự (S1,S2,S3,R1,R2,R3)"""
        result: List[Dict[str, float]] = []
        for i in range(len(records)):
            if i == 0:
                result.append({})
            else:
                prev = records[i-1]
                H, L, C = prev.priceHigh, prev.priceLow, prev.priceClose
                P = (H + L + C) / 3
                S1 = 2 * P - H
                R1 = 2 * P - L
                S2 = P - (H - L)
                R2 = P + (H - L)
                S3 = L - 2 * (H - P)
                R3 = H + 2 * (P - L)
                result.append({
                    'P': P, 'S1': S1, 'R1': R1,
                    'S2': S2, 'R2': R2,
                    'S3': S3, 'R3': R3
                })
        #print(f"[MATH][PivotPoints] Last point: {result[-1]}")
        return result

    @staticmethod
    def fibonacci_retracement_extension(
        records: List[StockRecord],
        levels: Optional[List[float]] = None
    ) -> List[Dict[str, float]]:
        """Tính các mức Fibonacci retracement và extension"""
        if levels is None:
            levels = [0.236, 0.382, 0.5, 0.618, 1.0, 1.382, 1.618]
        result: List[Dict[str, float]] = []
        for i in range(len(records)):
            if i == 0:
                result.append({})
            else:
                prev = records[i-1]
                H, L = prev.priceHigh, prev.priceLow
                diff = H - L
                pts: Dict[str, float] = {}
                for lvl in levels:
                    key = f"F{int(lvl*1000)}/1000"
                    pts[f"R{lvl}"] = H + diff * lvl
                    pts[f"S{lvl}"] = L - diff * lvl
                result.append(pts)
        #print(f"[MATH][Fibonacci] Last point: {result[-1]}")
        return result

    @staticmethod
    def correlation_coefficient(
        x: List[float],
        y: List[float],
        period: int
    ) -> List[Optional[float]]:
        """Tính hệ số tương quan (Pearson) theo chu kỳ"""
        result: List[Optional[float]] = []
        for i in range(len(x)):
            if i + 1 < period:
                result.append(None)
            else:
                xs = x[i+1-period:i+1]
                ys = y[i+1-period:i+1]
                mean_x = statistics.mean(xs)
                mean_y = statistics.mean(ys)
                cov = sum((a-mean_x)*(b-mean_y) for a, b in zip(xs, ys))
                std_x = statistics.pstdev(xs)
                std_y = statistics.pstdev(ys)
                if std_x * std_y != 0:
                    result.append(cov / (std_x * std_y * period))
                else:
                    result.append(None)
        #print(f"[MATH][Correlation] Last point: {result[-1]}")
        return result
    
