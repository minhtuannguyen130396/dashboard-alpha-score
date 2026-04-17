"""Compute sentiment metrics from tick data."""

from collections import defaultdict
from typing import Dict, List, Optional


def _parse_time(ts: str):
    """Extract (hour, minute) from timestamp string."""
    try:
        time_part = ts.split("T")[1]
        parts = time_part.split(":")
        return int(parts[0]), int(parts[1])
    except Exception:
        return 0, 0


def _parse_time_str(ts: str) -> str:
    """Extract HH:MM:SS from timestamp."""
    try:
        return ts.split("T")[1][:8]
    except Exception:
        return ts


DEFAULT_INST_VALUE_THRESHOLD = 2_000_000_000  # 2 tỷ VND


def compute_metrics(
    ticks: List[dict],
    symbol: str = "",
    date_str: str = "",
    session: str = "",
    daily_ref: Optional[dict] = None,
    inst_value_threshold: int = DEFAULT_INST_VALUE_THRESHOLD,
) -> dict:
    """Compute all sentiment metrics from tick data.

    Returns a JSON-serializable dict with all computed indicators.
    """
    if not ticks:
        return {"symbol": symbol, "date": date_str, "error": "no_data"}

    # --- Basic aggregation ---
    agg_buy_vol = 0
    agg_sell_vol = 0
    agg_neutral_vol = 0
    agg_buy_count = 0
    agg_sell_count = 0
    agg_neutral_count = 0

    volumes = [t.get("volume", 0) or 0 for t in ticks]
    vol_sorted = sorted(volumes, reverse=True)
    whale_threshold = vol_sorted[max(0, int(len(vol_sorted) * 0.05))]

    # Whale tracking
    whale_buy_vol = 0
    whale_sell_vol = 0
    whale_buy_count = 0
    whale_sell_count = 0
    whale_buy_vwap_num = 0.0
    whale_sell_vwap_num = 0.0

    # Bot detection
    vol_counts = defaultdict(int)
    for t in ticks:
        vol_counts[t.get("volume", 0) or 0] += 1
    bot_volumes = {v for v, c in vol_counts.items() if c >= 10 and v > 0}
    bot_tick_count = sum(1 for t in ticks if (t.get("volume", 0) or 0) in bot_volumes)
    top_bots = sorted(
        [(v, c) for v, c in vol_counts.items() if c >= 10 and v > 0],
        key=lambda x: x[1],
        reverse=True,
    )[:5]

    # Hourly flow
    hourly_buy = defaultdict(int)
    hourly_sell = defaultdict(int)

    # Price tracking
    prices = []
    price_changes = []
    prev_price = None

    # Large orders
    large_orders = []

    # 5-minute bucket flow
    bucket_5m = defaultdict(lambda: {"count": 0, "vol": 0, "buy": 0, "sell": 0})

    for t in ticks:
        vol = t.get("volume", 0) or 0
        price = t.get("price", 0) or 0
        side = t.get("side", "")
        ts = t.get("ts", "")
        h, m = _parse_time(ts)

        prices.append(price)
        if prev_price and price != prev_price:
            price_changes.append(price - prev_price)
        prev_price = price

        # Aggregate buy/sell
        if side == "B":
            agg_buy_vol += vol
            agg_buy_count += 1
            hourly_buy[h] += vol
        elif side == "S":
            agg_sell_vol += vol
            agg_sell_count += 1
            hourly_sell[h] += vol
        else:
            agg_neutral_vol += vol
            agg_neutral_count += 1

        # 5-min bucket
        bucket_key = f"{h:02d}:{(m // 5) * 5:02d}"
        bucket_5m[bucket_key]["count"] += 1
        bucket_5m[bucket_key]["vol"] += vol
        if side == "B":
            bucket_5m[bucket_key]["buy"] += vol
        elif side == "S":
            bucket_5m[bucket_key]["sell"] += vol

        # Whale detection
        if vol >= whale_threshold:
            if side == "B":
                whale_buy_vol += vol
                whale_buy_count += 1
                whale_buy_vwap_num += price * vol
            elif side == "S":
                whale_sell_vol += vol
                whale_sell_count += 1
                whale_sell_vwap_num += price * vol

            # Track extra-large orders (top 2% or 2x whale threshold)
            if vol >= whale_threshold * 2:
                large_orders.append(
                    {"time": _parse_time_str(ts), "price": price, "vol": vol, "side": side or "N"}
                )

    # Sort large orders by volume, keep top 15
    large_orders.sort(key=lambda x: x["vol"], reverse=True)
    large_orders = large_orders[:15]

    # --- Derived metrics ---

    # Aggression ratio
    agg_ratio_vol = agg_buy_vol / agg_sell_vol if agg_sell_vol > 0 else 0
    agg_ratio_count = agg_buy_count / agg_sell_count if agg_sell_count > 0 else 0

    # Whale VWAP
    whale_buy_vwap = whale_buy_vwap_num / whale_buy_vol if whale_buy_vol > 0 else 0
    whale_sell_vwap = whale_sell_vwap_num / whale_sell_vol if whale_sell_vol > 0 else 0
    whale_net = whale_buy_vol - whale_sell_vol

    # Bot percentage
    bot_pct = bot_tick_count / len(ticks) * 100 if ticks else 0

    # Hourly flow list
    all_hours = sorted(set(list(hourly_buy.keys()) + list(hourly_sell.keys())))
    hourly_flow = []
    for h in all_hours:
        b = hourly_buy.get(h, 0)
        s = hourly_sell.get(h, 0)
        hourly_flow.append({"hour": h, "buy": b, "sell": s, "net": b - s})

    # 5-minute flow
    flow_5m = []
    for bucket_key in sorted(bucket_5m.keys()):
        d = bucket_5m[bucket_key]
        net = d["buy"] - d["sell"]
        flow_5m.append({
            "time": bucket_key,
            "ticks": d["count"],
            "vol": d["vol"],
            "buy": d["buy"],
            "sell": d["sell"],
            "net": net,
        })

    # Order size distribution
    dist_buckets = [
        ("<1K", 0, 1000),
        ("1-5K", 1000, 5000),
        ("5-10K", 5000, 10000),
        ("10-50K", 10000, 50000),
        ("50-100K", 50000, 100000),
        (">100K", 100000, float("inf")),
    ]
    order_dist = {}
    total_vol_all = sum(volumes) or 1
    for label, lo, hi in dist_buckets:
        cnt = sum(1 for v in volumes if lo <= v < hi)
        vol_sum = sum(v for v in volumes if lo <= v < hi)
        order_dist[label] = {
            "count": cnt,
            "pct_count": round(cnt / len(ticks) * 100, 1) if ticks else 0,
            "vol": vol_sum,
            "pct_vol": round(vol_sum / total_vol_all * 100, 1),
        }

    # Momentum - split session into 3 parts
    n = len(ticks)
    third = n // 3
    parts = [ticks[:third], ticks[third : 2 * third], ticks[2 * third :]]
    momentum_parts = []
    for part in parts:
        b = sum(t.get("volume", 0) or 0 for t in part if t.get("side") == "B")
        s = sum(t.get("volume", 0) or 0 for t in part if t.get("side") == "S")
        p_list = [t.get("price", 0) for t in part if t.get("price")]
        momentum_parts.append({
            "net": b - s,
            "buy": b,
            "sell": s,
            "price_start": p_list[0] if p_list else 0,
            "price_end": p_list[-1] if p_list else 0,
        })
    p1_net = momentum_parts[0]["net"] if momentum_parts else 0
    p3_net = momentum_parts[2]["net"] if len(momentum_parts) > 2 else 0
    momentum_direction = "increasing" if p3_net > p1_net else "decreasing"

    # Price sensitivity
    up_moves = [c for c in price_changes if c > 0]
    down_moves = [c for c in price_changes if c < 0]
    avg_up = sum(up_moves) / len(up_moves) if up_moves else 0
    avg_down = sum(down_moves) / len(down_moves) if down_moves else 0
    asymmetry = abs(avg_down) / avg_up if avg_up > 0 else 0
    if asymmetry > 1.3:
        sensitivity_label = "fear_dominant"
    elif asymmetry < 0.7:
        sensitivity_label = "greed_dominant"
    else:
        sensitivity_label = "balanced"

    # --- Fear & Greed Composite ---
    fg_score = 0
    fg_factors = []

    # Factor 1: Aggression ratio
    if agg_ratio_vol > 1.2:
        fg_score += 2
        fg_factors.append({"name": "aggression", "score": 2, "detail": f"Buyers aggressive (ratio={agg_ratio_vol:.2f})"})
    elif agg_ratio_vol > 1.0:
        fg_score += 1
        fg_factors.append({"name": "aggression", "score": 1, "detail": f"Slightly bullish (ratio={agg_ratio_vol:.2f})"})
    elif agg_ratio_vol > 0.8:
        fg_factors.append({"name": "aggression", "score": 0, "detail": f"Neutral (ratio={agg_ratio_vol:.2f})"})
    else:
        fg_score -= 2
        fg_factors.append({"name": "aggression", "score": -2, "detail": f"Sellers aggressive (ratio={agg_ratio_vol:.2f})"})

    # Factor 2: Price asymmetry
    if asymmetry > 1.3:
        fg_score -= 1
        fg_factors.append({"name": "price_impact", "score": -1, "detail": f"Down moves stronger ({asymmetry:.2f}x)"})
    elif asymmetry < 0.7:
        fg_score += 1
        fg_factors.append({"name": "price_impact", "score": 1, "detail": f"Up moves stronger ({asymmetry:.2f}x)"})
    else:
        fg_factors.append({"name": "price_impact", "score": 0, "detail": f"Balanced ({asymmetry:.2f}x)"})

    # Factor 3: Momentum
    if p3_net > p1_net + 100000:
        fg_score += 1
        fg_factors.append({"name": "momentum", "score": 1, "detail": "Increasing momentum"})
    elif p3_net < p1_net - 100000:
        fg_score -= 1
        fg_factors.append({"name": "momentum", "score": -1, "detail": "Decreasing momentum"})
    else:
        fg_factors.append({"name": "momentum", "score": 0, "detail": "Stable momentum"})

    # Factor 4: Institutional direction (lệnh có giá trị >= inst_value_threshold)
    inst_buy = sum(
        t.get("volume", 0) or 0
        for t in ticks
        if t.get("side") == "B"
        and (t.get("price", 0) or 0) * (t.get("volume", 0) or 0) >= inst_value_threshold
    )
    inst_sell = sum(
        t.get("volume", 0) or 0
        for t in ticks
        if t.get("side") == "S"
        and (t.get("price", 0) or 0) * (t.get("volume", 0) or 0) >= inst_value_threshold
    )
    thresh_label = f"{inst_value_threshold // 1_000_000:,}tr"
    if inst_buy > inst_sell * 1.5 and inst_sell > 0:
        fg_score += 2
        fg_factors.append({"name": "institutional", "score": 2, "detail": f"Institutions buying (>{thresh_label})"})
    elif inst_sell > inst_buy * 1.5 and inst_buy > 0:
        fg_score -= 2
        fg_factors.append({"name": "institutional", "score": -2, "detail": f"Institutions selling (>{thresh_label})"})
    elif inst_buy > 0 or inst_sell > 0:
        fg_factors.append({"name": "institutional", "score": 0, "detail": f"Institutions balanced (>{thresh_label})"})

    # Factor 5: Volume intensity
    if len(ticks) > 2500:
        fg_score += 1
        fg_factors.append({"name": "volume_intensity", "score": 1, "detail": f"High activity ({len(ticks)} ticks)"})
    elif len(ticks) < 1500:
        fg_score -= 1
        fg_factors.append({"name": "volume_intensity", "score": -1, "detail": f"Low activity ({len(ticks)} ticks)"})
    else:
        fg_factors.append({"name": "volume_intensity", "score": 0, "detail": f"Normal activity ({len(ticks)} ticks)"})

    # Fear & Greed label
    if fg_score >= 4:
        fg_label = "EXTREME_GREED"
    elif fg_score >= 2:
        fg_label = "GREED"
    elif fg_score >= 1:
        fg_label = "SLIGHT_GREED"
    elif fg_score == 0:
        fg_label = "NEUTRAL"
    elif fg_score >= -1:
        fg_label = "SLIGHT_FEAR"
    elif fg_score >= -3:
        fg_label = "FEAR"
    else:
        fg_label = "EXTREME_FEAR"

    # Daily ref data
    ref_info = {}
    if daily_ref:
        ref_info = {
            "close": daily_ref.get("priceClose", 0),
            "open": daily_ref.get("priceOpen", 0),
            "high": daily_ref.get("priceHigh", 0),
            "low": daily_ref.get("priceLow", 0),
            "total_volume": daily_ref.get("totalVolume", 0),
            "foreign_buy": daily_ref.get("buyForeignQuantity", 0),
            "foreign_sell": daily_ref.get("sellForeignQuantity", 0),
            "foreign_net": (daily_ref.get("buyForeignQuantity", 0) or 0)
            - (daily_ref.get("sellForeignQuantity", 0) or 0),
            "prop_net_value": daily_ref.get("propTradingNetDealValue", 0),
        }

    return {
        "symbol": symbol,
        "date": date_str,
        "session": session,
        "price": {
            "open": prices[0] if prices else 0,
            "last": prices[-1] if prices else 0,
            "high": max(prices) if prices else 0,
            "low": min(prices) if prices else 0,
        },
        "aggression": {
            "buy_vol": agg_buy_vol,
            "sell_vol": agg_sell_vol,
            "neutral_vol": agg_neutral_vol,
            "ratio_vol": round(agg_ratio_vol, 3),
            "buy_count": agg_buy_count,
            "sell_count": agg_sell_count,
            "ratio_count": round(agg_ratio_count, 3),
        },
        "whale": {
            "threshold": whale_threshold,
            "buy_vol": whale_buy_vol,
            "sell_vol": whale_sell_vol,
            "net": whale_net,
            "buy_vwap": round(whale_buy_vwap, 2),
            "sell_vwap": round(whale_sell_vwap, 2),
            "buy_count": whale_buy_count,
            "sell_count": whale_sell_count,
        },
        "bot": {
            "pct": round(bot_pct, 1),
            "top_repeated": [{"vol": v, "count": c} for v, c in top_bots],
        },
        "hourly_flow": hourly_flow,
        "flow_5m": flow_5m,
        "order_distribution": order_dist,
        "momentum": {
            "parts": momentum_parts,
            "direction": momentum_direction,
        },
        "price_sensitivity": {
            "avg_up_dong": round(avg_up * 1000, 1),
            "avg_down_dong": round(avg_down * 1000, 1),
            "up_count": len(up_moves),
            "down_count": len(down_moves),
            "asymmetry": round(asymmetry, 2),
            "interpretation": sensitivity_label,
        },
        "fear_greed": {
            "score": fg_score,
            "max_score": 7,
            "label": fg_label,
            "factors": fg_factors,
        },
        "large_orders": large_orders,
        "summary": {
            "total_ticks": len(ticks),
            "total_volume": sum(volumes),
            "net_buy_sell": agg_buy_vol - agg_sell_vol,
        },
        "daily_ref": ref_info,
    }
