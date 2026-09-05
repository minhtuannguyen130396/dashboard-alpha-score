"""Indicator variants the existing modules compute but do not expose.

``IndicatorGroup3.adx`` calculates +DI and -DI internally and then throws them
away, so there is no way to tell whether a strong ADX means a strong uptrend
or a strong downtrend. ``adx_di`` runs the same Wilder math and returns all
three series, index-aligned to ``records``.
"""
from typing import List, Optional, Sequence, Tuple

from src.data.stock_data_loader import StockRecord

Series = List[Optional[float]]


def _wilder(data: Sequence[float], n: int) -> List[float]:
    """Wilder's running sum — matches IndicatorGroup3.adx exactly."""
    s = sum(data[:n])
    out = [s]
    for x in data[n:]:
        s = s - s / n + x
        out.append(s)
    return out


def adx_di(records: List[StockRecord], period: int = 14) -> Tuple[Series, Series, Series]:
    """Return ``(adx, plus_di, minus_di)`` aligned to ``records``.

    ADX is Wilder's *average* of DX (the running sum divided by ``period``),
    matching the correction already documented in ``IndicatorGroup3.adx``.
    """
    n = len(records)
    empty: Series = [None] * n
    if n < 2 * period:
        return empty, list(empty), list(empty)

    tr_list: List[float] = []
    plus_dm: List[float] = []
    minus_dm: List[float] = []
    for i in range(1, n):
        h, l = records[i].priceHigh, records[i].priceLow
        pc, ph, pl = records[i - 1].priceClose, records[i - 1].priceHigh, records[i - 1].priceLow
        tr_list.append(max(h - l, abs(h - pc), abs(l - pc)))
        up = h - ph
        down = pl - l
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)

    atr_s = _wilder(tr_list, period)
    pdm_s = _wilder(plus_dm, period)
    mdm_s = _wilder(minus_dm, period)

    pdi = [100 * p / a if a else 0.0 for p, a in zip(pdm_s, atr_s)]
    mdi = [100 * m / a if a else 0.0 for m, a in zip(mdm_s, atr_s)]
    dx = [100 * abs(p - m) / (p + m) if (p + m) else 0.0 for p, m in zip(pdi, mdi)]

    plus_out: Series = [None] * n
    minus_out: Series = [None] * n
    # _wilder(x, period)[k] corresponds to record index period + k.
    for k in range(len(pdi)):
        idx = period + k
        if idx < n:
            plus_out[idx] = pdi[k]
            minus_out[idx] = mdi[k]

    adx_out: Series = [None] * n
    if len(dx) >= period:
        adx_s = _wilder(dx, period)
        offset = 2 * period - 1
        for k, v in enumerate(adx_s):
            idx = offset + k
            if idx < n:
                adx_out[idx] = v / period

    return adx_out, plus_out, minus_out
