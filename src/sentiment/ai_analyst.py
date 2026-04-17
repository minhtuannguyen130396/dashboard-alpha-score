"""Send computed metrics to Google Gemini for AI commentary."""

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

GUIDE_PATH = Path(__file__).parent / "sentiment_guide.md"
DEFAULT_MODEL = "gemini-flash-latest"


def _load_guide(guide_path: Path = GUIDE_PATH) -> str:
    with open(guide_path, "r", encoding="utf-8") as f:
        return f.read()


def _build_history_summary(history: List[dict]) -> str:
    """Create a concise summary of historical results for the prompt."""
    if not history:
        return "Không có dữ liệu lịch sử."
    lines = []
    for h in history:
        m = h.get("metrics", {})
        ai = h.get("ai_analysis", {})
        fg = m.get("fear_greed", {})
        whale = m.get("whale", {})
        agg = m.get("aggression", {})
        lines.append(
            f"- {h.get('date', '?')} ({h.get('session', '?')}): "
            f"F&G={fg.get('score', '?')}/{fg.get('max_score', 7)} [{fg.get('label', '?')}], "
            f"WhaleNet={whale.get('net', 0):+,}, "
            f"AggrRatio={agg.get('ratio_vol', 0):.2f}, "
            f"AI_label={ai.get('sentiment_label', 'N/A')}"
        )
    return "\n".join(lines)


def _extract_json(text: str) -> dict:
    """Extract JSON from AI response, handling markdown code blocks."""
    # Try direct parse first
    text = text.strip()
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    # Try extracting from ```json ... ```
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    # Last resort: find first { to last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    return {"error": "Failed to parse AI response", "raw": text[:2000]}


def analyze(
    metrics: dict,
    history: List[dict],
    guide_path: Path = GUIDE_PATH,
    model: str = DEFAULT_MODEL,
    api_key: Optional[str] = None,
) -> dict:
    """Send metrics to Gemini and get structured analysis.

    Requires google-generativeai package and GOOGLE_API_KEY env var.
    """
    try:
        import google.generativeai as genai
    except ImportError:
        return {
            "error": "google-generativeai not installed. Run: pip install google-generativeai",
            "sentiment_label": "UNKNOWN",
            "score": 0,
            "summary": "Không thể phân tích - thiếu thư viện google-generativeai",
        }

    key = api_key or os.environ.get("GOOGLE_API_KEY", "")
    if not key:
        return {
            "error": "GOOGLE_API_KEY not set",
            "sentiment_label": "UNKNOWN",
            "score": 0,
            "summary": "Không thể phân tích - chưa cấu hình API key",
        }

    genai.configure(api_key=key)

    guide_text = _load_guide(guide_path)
    history_summary = _build_history_summary(history)

    # Build concise metrics for prompt (exclude flow_5m to save tokens)
    metrics_for_prompt = {k: v for k, v in metrics.items() if k != "flow_5m"}

    user_prompt = f"""Phân tích tâm lý thị trường cho cổ phiếu {metrics.get('symbol', '?')} ngày {metrics.get('date', '?')} (phiên: {metrics.get('session', '?')}).

## Dữ liệu metrics hiện tại:
```json
{json.dumps(metrics_for_prompt, ensure_ascii=False, indent=2)}
```

## Lịch sử các phiên trước:
{history_summary}

Hãy phân tích và trả về JSON theo format trong hướng dẫn."""

    try:
        gen_model = genai.GenerativeModel(
            model_name=model,
            system_instruction=guide_text,
        )
        response = gen_model.generate_content(user_prompt)
        result = _extract_json(response.text)
        return result
    except Exception as e:
        return {
            "error": str(e),
            "sentiment_label": "ERROR",
            "score": 0,
            "summary": f"Lỗi khi gọi Gemini API: {e}",
        }


def analyze_without_ai(metrics: dict, history: List[dict]) -> dict:
    """Fallback: generate basic analysis without AI (rule-based).

    Used when API key is not available or for testing.
    """
    fg = metrics.get("fear_greed", {})
    whale = metrics.get("whale", {})
    agg = metrics.get("aggression", {})
    mom = metrics.get("momentum", {})

    score = fg.get("score", 0)
    label = fg.get("label", "NEUTRAL")

    # Compare with history
    vs_history = "Không có dữ liệu lịch sử để so sánh."
    if history:
        prev = history[-1]
        prev_fg = prev.get("metrics", {}).get("fear_greed", {})
        prev_score = prev_fg.get("score", 0)
        prev_label = prev_fg.get("label", "?")
        prev_whale = prev.get("metrics", {}).get("whale", {}).get("net", 0)
        change = score - prev_score
        vs_history = (
            f"So với phiên trước ({prev.get('date', '?')}): "
            f"F&G {prev_score:+d} -> {score:+d} ({change:+d}), "
            f"Label: {prev_label} -> {label}. "
            f"Whale net: {prev_whale:+,} -> {whale.get('net', 0):+,}."
        )

    whale_net = whale.get("net", 0)
    if whale_net > 0:
        whale_interp = f"Cá mập MUA ròng {whale_net:,} cp - tín hiệu tích lũy."
    else:
        whale_interp = f"Cá mập BÁN ròng {abs(whale_net):,} cp - tín hiệu phân phối."

    risk = "MEDIUM"
    if score <= -3:
        risk = "HIGH"
    elif score >= 3:
        risk = "LOW"

    return {
        "sentiment_label": label,
        "score": score,
        "summary": f"Phiên {metrics.get('session', '?')} {metrics.get('date', '?')}: "
        f"Tâm lý {label} (điểm {score:+d}/{fg.get('max_score', 7)}). "
        f"Aggression ratio={agg.get('ratio_vol', 0):.2f}. "
        f"Whale net={whale_net:+,}. "
        f"Momentum {mom.get('direction', '?')}.",
        "key_signals": [f.get("detail", "") for f in fg.get("factors", []) if f.get("score", 0) != 0],
        "vs_history": vs_history,
        "whale_interpretation": whale_interp,
        "risk_level": risk,
        "outlook": "Cần thêm dữ liệu để dự báo (phân tích rule-based).",
        "recommendation": "Theo dõi whale flow và aggression ratio phiên tiếp theo.",
        "_source": "rule_based",
    }
