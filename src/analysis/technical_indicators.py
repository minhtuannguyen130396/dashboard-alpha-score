from typing import List, Tuple, Optional, Dict
from datetime import datetime
import pandas as pd
import math
import statistics
from src.data.stock_data_loader import StockRecord

# Helper to extract list of floats
def _extract(records: List[StockRecord], attr: str) -> List[float]:
    return [getattr(r, attr) for r in records]
def average_volume(records: List[StockRecord], period: int = 10) -> float:
    """Calculate average volume over the most recent N sessions."""
    volumes = [r.totalVolume for r in records[-period:] if r.totalVolume is not None]
    if not volumes:
        return 0.0
    return sum(volumes) / len(volumes)

# =========================
# Group 1: Moving averages
# =========================
class IndicatorGroup1:
    @staticmethod
    def sma(records: List[StockRecord], period: int) -> List[Optional[float]]:
        """Calculate the Simple Moving Average."""
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
        """Calculate the Exponential Moving Average."""
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
        """Calculate the Weighted Moving Average."""
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
        """Calculate the Volume Weighted Moving Average."""
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
        """Calculate the Hull Moving Average."""
        half = IndicatorGroup1.ema(records, period // 2)
        full = IndicatorGroup1.ema(records, period)
        diff = []
        for h, f in zip(half, full):
            diff.append((2*h - f) if h is not None and f is not None else None)
        # Wrap temporary values as dummy records.
        class D: priceClose = 0
        diff_recs = [D() for _ in diff]
        for d, rec in zip(diff, diff_recs): rec.priceClose = d or 0
        result = IndicatorGroup1.ema(diff_recs, int(math.sqrt(period)))
        #print(f"[MATH][HMA] Last point: {result[-1]}")
        return result

    @staticmethod
    def kama(records: List[StockRecord], period: int, fast: int = 2, slow: int = 30) -> List[Optional[float]]:
        """Calculate the Kaufman Adaptive Moving Average."""
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
# Group 2: Momentum
# =========================
class IndicatorGroup2:
    @staticmethod 
    def momentum(records: List[StockRecord], period: int) -> List[Optional[float]]:
        """Measure momentum using the close versus the close N periods ago."""
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
        """Measure momentum as a percentage change instead of an absolute delta."""
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
        """Calculate Momentum."""
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
        """Calculate the Rate of Change."""
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
        """Calculate the Commodity Channel Index."""
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
        """Calculate Stochastic %K."""
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
        """Calculate Stochastic %D."""
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
        """Calculate Williams %R."""
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
        """Calculate the Ultimate Oscillator."""
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
        """Calculate MACD, the signal line, and the histogram."""
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
# Group 3: Volatility
# =========================
class IndicatorGroup3:
    @staticmethod
    def atr(records: List[StockRecord], period: int) -> List[Optional[float]]:
        """Calculate the Average True Range."""
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
        """Calculate Bollinger Bands."""
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
        """Calculate the Keltner Channel."""
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
        """Calculate the Donchian Channel."""
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
        """Calculate standard deviation."""
        closes=_extract(records,'priceClose')
        result=[]
        for i in range(len(closes)):
            if i+1<period: result.append(None)
            else: result.append(statistics.pstdev(closes[i+1-period:i+1]))
        #print(f"[MATH][StdDev] Last point: {result[-1]}")
        return result

    @staticmethod
    def mass_index(records: List[StockRecord], period: int = 25, ema_period: int = 9) -> List[Optional[float]]:
        """Calculate the Mass Index."""
        # Compute the high-low range for each session.
        hr = [r.priceHigh - r.priceLow for r in records]
        # First EMA of the high-low range.
        k = 2 / (ema_period + 1)
        ema1: List[float] = []
        for i, x in enumerate(hr):
            if i == 0:
                ema1.append(x)
            else:
                ema1.append(x * k + ema1[-1] * (1 - k))
        # Second EMA applied to the first EMA.
        ema2: List[float] = []
        for i, x in enumerate(ema1):
            if i == 0:
                ema2.append(x)
            else:
                ema2.append(x * k + ema2[-1] * (1 - k))
        # Mass Index is the rolling sum of ema1/ema2 over the given period.
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
        """Calculate Chaikin Volatility."""
        # Compute the high-low distance for each session.
        hr = [r.priceHigh - r.priceLow for r in records]
        # Build dummy records so the EMA helper can be reused.
        class D:
            def __init__(self, v: float):
                self.priceClose = v
        hr_recs = [D(x) for x in hr]
        # Long and short EMA windows.
        ema_long = IndicatorGroup1.ema(hr_recs, period_slow)
        ema_short = IndicatorGroup1.ema(hr_recs, period_fast)
        # Chaikin Volatility = (EMA_short - EMA_long) / EMA_long * 100.
        result: List[Optional[float]] = []
        for long_val, short_val in zip(ema_long, ema_short):
            if long_val is None or long_val == 0 or short_val is None:
                result.append(None)
            else:
                result.append((short_val - long_val) / long_val * 100)
        #print(f"[MATH][ChaikinVolatility] Last point: {result[-1]}")
        return result
# =========================
# Group 4: Volume-based indicators
# =========================
class IndicatorGroup4:
    @staticmethod
    # Compare the current close with the previous session's close.
    def obv(records: List[StockRecord]) -> List[int]:
        """Calculate On-Balance Volume."""
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
    
    def ad_signals(records: List[StockRecord],window:int =10) -> List[int]: # estimated accuracy is around 60%
        """
        Generate divergence signals from the ADL:
        +1: bullish divergence (price makes a lower low, ADL makes a higher low)
        -1: bearish divergence (price makes a higher high, ADL makes a lower high)
        0: no divergence
        """
        def ad_line(records: List[StockRecord]) -> List[float]:
            """Calculate the Accumulation/Distribution Line (ADL)."""
            result: List[float] = []
            ad_val = 0.0
            for r in records:
                high, low, close, vol = r.priceHigh, r.priceLow, r.priceClose, r.totalVolume
                mfm = ((close - low) - (high - close)) / (high - low) if high != low else 0.0
                mfv = mfm * vol
                ad_val += mfv
                result.append(ad_val)
            return result
        def ad_smoothed(records: List[StockRecord], window: int = 10) -> List[float]:
            """Return the moving average of the ADL over the given window."""
            ad_vals = ad_line(records)
            # Use pandas rolling mean with min_periods=1 to avoid leading gaps.
            return pd.Series(ad_vals).rolling(window=window, min_periods=1).mean().tolist()
        
        """
        Generate divergence signals from the smoothed ADL:
        +1: bullish divergence (price low falls while smoothed ADL rises)
        -1: bearish divergence (price high rises while smoothed ADL falls)
        0: no signal
        """
        ad_ma = ad_smoothed(records, window)
        signals = [0] * len(records)
        for i in range(1, len(records)):
            # bullish divergence
            if (records[i].priceLow  < records[i-1].priceLow
                and ad_ma[i]          > ad_ma[i-1]):
                signals[i] = +1
            # bearish divergence
            elif (records[i].priceHigh > records[i-1].priceHigh
                and ad_ma[i]           < ad_ma[i-1]):
                signals[i] = -1
        return signals
    
    @staticmethod
    def chaikin_money_flow(records: List[StockRecord], period: int = 15, thresh:float = 0.35) -> List[Optional[int]]:
        
        """Calculate Chaikin Money Flow
            This has been tested, but the hit rate is still not very accurate.
        """
        
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
        result: List[Optional[int]] = []
        for i in range(len(records)):
            if i + 1 < period:
                result.append(0)
            else:
                window_mfv = sum(mfv[i+1-period:i+1])
                window_vol = sum(vol[i+1-period:i+1])
                money_flow_value = window_mfv / window_vol if window_vol != 0 else None
                #print(f"[ADD] flow: {money_flow_value}")
                if(money_flow_value > thresh):
                    result.append(1)
                elif (money_flow_value < - thresh):
                    result.append(-1)
                else:
                    result.append(0)
        #print(f"[MATH][CMF] Last point: {result[-1]}")
        return result

    @staticmethod
    def mfi(records: List[StockRecord], period: int = 14) -> List[Optional[float]]:
        """Calculate the Money Flow Index."""
        """This indicator helps estimate whether money is flowing in or out.
            Higher values suggest stronger buying pressure.
            Lower values suggest stronger selling pressure.
            The range is 0-100.
            This is a basic confirmation indicator."""
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
    def vroc_score(records: List[StockRecord], period: int = 14, threshold: float = 80.0) -> List[int]:
        """
        Calculate the VROC score:
        - Return 1 if current volume change versus N periods ago is above the threshold
        - Return -1 if it is below the negative threshold
        """
        # 1. Extract the volume series.
        volumes: List[float] = _extract(records, 'totalVolume')
        
        # 2. Initialize the result container.
        result: List[int] = []
        
        # 3. Iterate over each session.
        for i in range(len(volumes)):
            if i < period or volumes[i - period] == 0:
                # Not enough data yet, or avoid division by zero -> assign -1.
                result.append(-1)
            else:
                # Compute VROC as a percentage.
                vroc = (volumes[i] - volumes[i - period]) / volumes[i - period] * 100
                # Compare it against the threshold.
                if (vroc > threshold):
                    result.append(1)
                elif (vroc < -threshold):
                    result.append(-1)
                else:
                     result.append(0)
        
        return result

    @staticmethod
    def vwap(records: List[StockRecord]) -> List[Optional[float]]:
        """Calculate the Volume-Weighted Average Price."""
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
        """Check whether there is evidence of large-buyer accumulation."""
        if not records:
            return False
        
        def average_buy_size(_records: List[StockRecord], _period: int = 14) -> float:
            buy_sizes = []
            for r in _records[-_period-1:-1]:  # use the previous sessions as the baseline window
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
                    if avg_buy_size > 1.5 * average_buy_size(_records= records,_period = pretiod):  # may vary by stock symbol
                        result.append(True)
                        continue
                result.append(False)
                
        return result
    @staticmethod
    def is_fomo_by_retail(records: List[StockRecord],period:int = 14) -> List[bool]:
        """Check whether retail FOMO behavior is likely present."""
        if not records:
            return []
        result: List[bool] = []
        for index, record in enumerate(records):
            if index <= period:
                result.append(False)
                continue
            if record.totalVolume > 2 * average_volume(records, period):
            # but without proprietary trading or foreign buying support
                if (not record.propTradingNetValue or record.propTradingNetValue <= 0) and \
                    record.buyForeignQuantity <= record.sellForeignQuantity:
                    result.append(True)
                    continue
            result.append(False)
        return result
        
# =========================
# Group 5: Breadth and market strength
# =========================
class IndicatorGroup5:
    @staticmethod    
    def adv_decline_line(advances: List[int], declines: List[int]) -> List[int]:
        """Calculate the Advance/Decline Line as the cumulative net advances."""
        result: List[int] = []
        cum = 0
        for a, d in zip(advances, declines):
            cum += (a - d)
            result.append(cum)
        #print(f"[MATH][AdvanceDeclineLine] Last point: {result[-1]}")
        return result

    @staticmethod
    def mcclellan_oscillator(advances: List[int], declines: List[int], short_period: int = 19, long_period: int = 39) -> List[Optional[float]]:
        """Calculate the McClellan Oscillator as short EMA minus long EMA of net advances."""
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
        """Calculate TRIN (Arms Index): (adv/dec) / (vol_adv/vol_dec)."""
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
        """Calculate the Bullish Percent Index as the percentage of bullish stocks."""
        result: List[Optional[float]] = []
        for b, t in zip(bulls, total):
            if t == 0:
                result.append(None)
            else:
                result.append(b / t * 100)
        #print(f"[MATH][BullishPercentIndex] Last point: {result[-1]}")
        return result

# =========================
# Group 6: Other indicators
# =========================
class IndicatorGroup6:
    @staticmethod
    def pivot_points(records: List[StockRecord]) -> List[Dict[str, float]]:
        """Calculate pivot points and support/resistance levels (S1-S3, R1-R3)."""
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
        """Calculate Fibonacci retracement and extension levels."""
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
        """Calculate the rolling Pearson correlation coefficient."""
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


_LegacyIndicatorGroup4 = IndicatorGroup4


class IndicatorGroup4(_LegacyIndicatorGroup4):
    @staticmethod
    def obv(records: List[StockRecord]) -> List[int]:
        result: List[int] = [0]
        obv_val = 0
        for i in range(1, len(records)):
            if records[i].priceClose > records[i - 1].priceClose:
                obv_val += int(records[i].totalVolume)
            elif records[i].priceClose < records[i - 1].priceClose:
                obv_val -= int(records[i].totalVolume)
            result.append(obv_val)
        return result

    @staticmethod
    def is_big_buyer(records: List[StockRecord], pretiod: int = 14) -> List[bool]:
        if not records:
            return []

        def average_buy_size(end_index: int) -> float:
            start_index = max(0, end_index - pretiod)
            buy_sizes = []
            for record in records[start_index:end_index]:
                if record.buyCount and record.buyQuantity:
                    buy_sizes.append(record.buyQuantity / record.buyCount)
            return sum(buy_sizes) / len(buy_sizes) if buy_sizes else 0.0

        result: List[bool] = []
        for index, record in enumerate(records):
            if index <= pretiod:
                result.append(False)
                continue
            if record.propTradingNetValue and record.propTradingNetValue > 0:
                result.append(True)
                continue
            if record.buyForeignQuantity > record.sellForeignQuantity:
                result.append(True)
                continue
            if record.buyCount and record.buyQuantity:
                baseline = average_buy_size(index)
                average_size = record.buyQuantity / record.buyCount
                if baseline > 0 and average_size > 1.5 * baseline:
                    result.append(True)
                    continue
            result.append(False)
        return result

    @staticmethod
    def is_fomo_by_retail(records: List[StockRecord], period: int = 14) -> List[bool]:
        if not records:
            return []

        result: List[bool] = []
        for index, record in enumerate(records):
            if index <= period:
                result.append(False)
                continue

            historical_window = records[max(0, index - period):index]
            historical_avg_volume = average_volume(
                historical_window,
                min(period, len(historical_window)),
            )
            if historical_avg_volume == 0:
                result.append(False)
                continue

            if record.totalVolume > 2 * historical_avg_volume:
                if (
                    (not record.propTradingNetValue or record.propTradingNetValue <= 0)
                    and record.buyForeignQuantity <= record.sellForeignQuantity
                ):
                    result.append(True)
                    continue
            result.append(False)
        return result
