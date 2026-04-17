"""Shared numeric helpers for smart money primitives."""
import math
from typing import List, Sequence


def clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    if x != x:  # NaN
        return 0.0
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def safe_ratio(num: float, denom: float, fallback: float = 0.0) -> float:
    if denom is None or denom == 0 or denom != denom:
        return fallback
    return num / denom


def winsorize(series: Sequence[float], p: float = 0.02) -> List[float]:
    """Cap the lowest/highest p fraction of values to reduce outlier impact."""
    clean = [float(x) for x in series if x is not None]
    if len(clean) < 5:
        return clean
    sorted_vals = sorted(clean)
    k = max(1, int(len(sorted_vals) * p))
    lo = sorted_vals[k]
    hi = sorted_vals[-k - 1]
    return [min(max(x, lo), hi) for x in clean]


def rolling_zscore(series: Sequence[float], window: int = 60) -> float:
    """Z-score of the latest value within the last ``window`` entries.

    Winsorizes the window before computing mean/std to blunt single-bar
    blowouts (a common problem with prop / foreign flow).
    """
    clean = [float(x) for x in series if x is not None]
    if len(clean) < 5:
        return 0.0
    w = clean[-window:]
    latest = w[-1]
    body = winsorize(w, p=0.02)
    n = len(body)
    mean = sum(body) / n
    var = sum((x - mean) ** 2 for x in body) / n
    std = math.sqrt(var)
    if std == 0:
        return 0.0
    return (latest - mean) / std


def rank_to_signed(rank: float) -> float:
    """Map a [0..1] percentile rank to the [-1..+1] range."""
    return clamp(2.0 * rank - 1.0)


def tanh_scale(x: float, k: float = 1.0) -> float:
    """Smooth bounded mapping to [-1..+1] via tanh."""
    return math.tanh(k * x)


def mean(series: Sequence[float]) -> float:
    vals = [float(x) for x in series if x is not None]
    if not vals:
        return 0.0
    return sum(vals) / len(vals)
