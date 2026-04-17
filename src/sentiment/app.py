"""Flask web app for tick sentiment analysis."""

import json
import os
import sys
from pathlib import Path

from flask import Flask, jsonify, render_template, request

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env file from src/sentiment/.env
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    with open(_env_file, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _val = _line.split("=", 1)
                _key, _val = _key.strip(), _val.strip()
                if _val and _val != "your_api_key_here":
                    os.environ.setdefault(_key, _val)

from src.sentiment.tick_loader import (
    detect_session,
    get_daily_record,
    list_available_dates,
    list_symbols_with_ticks,
    load_ticks,
)
from src.sentiment.metrics_engine import compute_metrics
from src.sentiment.history_store import (
    list_history_dates,
    load_history,
    load_single,
    save_result,
)
from src.sentiment.ai_analyst import analyze, analyze_without_ai

app = Flask(__name__, template_folder=str(Path(__file__).parent / "templates"))


@app.route("/")
def index():
    symbols = list_symbols_with_ticks()
    return render_template("index.html", symbols=symbols)


@app.route("/api/dates/<symbol>")
def api_dates(symbol):
    """Return available tick dates for a symbol."""
    dates = list_available_dates(symbol)
    history_dates = list_history_dates(symbol)
    return jsonify({"dates": dates, "history_dates": history_dates})


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """Run full analysis pipeline for a symbol + date."""
    data = request.json or {}
    symbol = data.get("symbol", "")
    date_str = data.get("date", "")
    use_ai = data.get("use_ai", True)
    lookback = data.get("lookback", 10)
    force = data.get("force", False)  # force re-analyze even if cached
    inst_value_threshold = int(data.get("inst_value_threshold", 2_000_000_000))

    if not symbol or not date_str:
        return jsonify({"error": "symbol and date required"}), 400

    # Load from cache if already analyzed and not forced
    if not force:
        cached = load_single(symbol, date_str)
        if cached:
            history = load_history(symbol, date_str, lookback=lookback)
            return jsonify({
                "metrics": cached["metrics"],
                "ai_analysis": cached["ai_analysis"],
                "from_cache": True,
                "history_summary": [
                    {
                        "date": h.get("date"),
                        "session": h.get("session"),
                        "fear_greed_score": h.get("metrics", {}).get("fear_greed", {}).get("score"),
                        "fear_greed_label": h.get("metrics", {}).get("fear_greed", {}).get("label"),
                        "whale_net": h.get("metrics", {}).get("whale", {}).get("net"),
                        "aggression_ratio": h.get("metrics", {}).get("aggression", {}).get("ratio_vol"),
                        "ai_label": h.get("ai_analysis", {}).get("sentiment_label"),
                    }
                    for h in history
                ],
            })

    # 1. Load ticks
    ticks = load_ticks(symbol, date_str)
    if not ticks:
        return jsonify({"error": f"No tick data for {symbol} on {date_str}"}), 404

    # 2. Detect session
    session = detect_session(ticks)

    # 3. Load daily reference
    daily_ref = get_daily_record(symbol, date_str)

    # 4. Compute metrics
    metrics = compute_metrics(ticks, symbol=symbol, date_str=date_str, session=session, daily_ref=daily_ref, inst_value_threshold=inst_value_threshold)

    # 5. Load history
    history = load_history(symbol, date_str, lookback=lookback)

    # 6. AI analysis
    if use_ai and os.environ.get("GOOGLE_API_KEY"):
        ai_result = analyze(metrics, history)
    else:
        ai_result = analyze_without_ai(metrics, history)

    # 7. Save result
    save_result(symbol, date_str, metrics, ai_result)

    return jsonify({
        "metrics": metrics,
        "ai_analysis": ai_result,
        "history_summary": [
            {
                "date": h.get("date"),
                "session": h.get("session"),
                "fear_greed_score": h.get("metrics", {}).get("fear_greed", {}).get("score"),
                "fear_greed_label": h.get("metrics", {}).get("fear_greed", {}).get("label"),
                "whale_net": h.get("metrics", {}).get("whale", {}).get("net"),
                "aggression_ratio": h.get("metrics", {}).get("aggression", {}).get("ratio_vol"),
                "ai_label": h.get("ai_analysis", {}).get("sentiment_label"),
            }
            for h in history
        ],
    })


@app.route("/api/history/<symbol>")
def api_history(symbol):
    """Return all saved history for a symbol."""
    dates = list_history_dates(symbol)
    results = []
    for d in dates:
        rec = load_single(symbol, d)
        if rec:
            m = rec.get("metrics", {})
            ai = rec.get("ai_analysis", {})
            results.append({
                "date": d,
                "session": rec.get("session"),
                "fear_greed_score": m.get("fear_greed", {}).get("score"),
                "fear_greed_label": m.get("fear_greed", {}).get("label"),
                "whale_net": m.get("whale", {}).get("net"),
                "aggression_ratio": m.get("aggression", {}).get("ratio_vol"),
                "ai_label": ai.get("sentiment_label"),
                "ai_summary": ai.get("summary"),
            })
    return jsonify({"symbol": symbol, "history": results})


@app.route("/api/batch_analyze", methods=["POST"])
def api_batch_analyze():
    """Analyze multiple dates for a symbol (build history)."""
    data = request.json or {}
    symbol = data.get("symbol", "")
    dates = data.get("dates", [])
    use_ai = data.get("use_ai", True)

    if not symbol or not dates:
        return jsonify({"error": "symbol and dates required"}), 400

    force = data.get("force", False)

    results = []
    for date_str in sorted(dates):
        # Skip if cached and not forced
        if not force:
            cached = load_single(symbol, date_str)
            if cached:
                m = cached.get("metrics", {})
                ai = cached.get("ai_analysis", {})
                results.append({
                    "date": date_str,
                    "fear_greed_score": m.get("fear_greed", {}).get("score"),
                    "fear_greed_label": m.get("fear_greed", {}).get("label"),
                    "whale_net": m.get("whale", {}).get("net"),
                    "ai_label": ai.get("sentiment_label"),
                    "from_cache": True,
                })
                continue

        ticks = load_ticks(symbol, date_str)
        if not ticks:
            results.append({"date": date_str, "error": "no_data"})
            continue

        session = detect_session(ticks)
        daily_ref = get_daily_record(symbol, date_str)
        inst_thresh = int(data.get("inst_value_threshold", 2_000_000_000))
        metrics = compute_metrics(ticks, symbol=symbol, date_str=date_str, session=session, daily_ref=daily_ref, inst_value_threshold=inst_thresh)
        history = load_history(symbol, date_str, lookback=10)

        if use_ai and os.environ.get("GOOGLE_API_KEY"):
            ai_result = analyze(metrics, history)
        else:
            ai_result = analyze_without_ai(metrics, history)

        save_result(symbol, date_str, metrics, ai_result)
        results.append({
            "date": date_str,
            "fear_greed_score": metrics.get("fear_greed", {}).get("score"),
            "fear_greed_label": metrics.get("fear_greed", {}).get("label"),
            "whale_net": metrics.get("whale", {}).get("net"),
            "ai_label": ai_result.get("sentiment_label"),
        })

    return jsonify({"symbol": symbol, "results": results})


def main():
    port = int(os.environ.get("PORT", 8688))
    print(f"\n  Tick Sentiment Analyzer")
    print(f"  http://localhost:{port}")
    print(f"  GOOGLE_API_KEY: {'SET' if os.environ.get('GOOGLE_API_KEY') else 'NOT SET (will use rule-based fallback)'}\n")
    app.run(host="0.0.0.0", port=port, debug=True)


if __name__ == "__main__":
    main()
