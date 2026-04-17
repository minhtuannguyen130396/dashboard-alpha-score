"""Deterministic narrative generation for smart money signals (no LLM)."""
from typing import Dict

from src.analysis.smart_money.types import FlowPrimitive


def _fmt_billion(value: float) -> str:
    return f"{value / 1e9:.1f} tỷ"


def generate_narrative(
    primitives: Dict[str, FlowPrimitive],
    composite: float,
    label: str,
    is_toxic: bool = False,
) -> str:
    if is_toxic:
        return ("CẢNH BÁO TOXIC: giá tăng nhưng dòng tiền thông minh "
                "đang thoái — có thể là bẫy retail FOMO.")
    parts = []
    prop = primitives.get("prop")
    foreign = primitives.get("foreign")

    if prop and prop.confidence > 0.3:
        short_sum = prop.components.get("short_sum", 0.0)
        if prop.value > 0.3:
            parts.append(f"Tự doanh mua ròng mạnh ({_fmt_billion(short_sum)}/10 phiên)")
        elif prop.value > 0.1:
            parts.append(f"Tự doanh mua ròng nhẹ ({_fmt_billion(short_sum)}/10 phiên)")
        elif prop.value < -0.3:
            parts.append(f"Tự doanh bán ròng ({_fmt_billion(short_sum)}/10 phiên)")
        elif prop.value < -0.1:
            parts.append(f"Tự doanh bán ròng nhẹ ({_fmt_billion(short_sum)}/10 phiên)")

    if foreign and foreign.confidence > 0.3:
        short_sum = foreign.components.get("short_sum", 0.0)
        if foreign.value > 0.3:
            parts.append(f"Khối ngoại mua ròng mạnh ({_fmt_billion(short_sum)}/10 phiên)")
        elif foreign.value > 0.1:
            parts.append(f"Khối ngoại mua ròng nhẹ ({_fmt_billion(short_sum)}/10 phiên)")
        elif foreign.value < -0.3:
            parts.append(f"Khối ngoại bán ròng ({_fmt_billion(short_sum)}/10 phiên)")
        elif foreign.value < -0.1:
            parts.append(f"Khối ngoại bán ròng nhẹ ({_fmt_billion(short_sum)}/10 phiên)")

    if prop and foreign and prop.confidence > 0.3 and foreign.confidence > 0.3:
        product = prop.value * foreign.value
        if product > 0.09:
            parts.append("Tự doanh và khối ngoại cùng chiều")
        elif product < -0.09:
            parts.append("Tự doanh và khối ngoại ngược chiều")

    div = primitives.get("divergence")
    if div and div.confidence > 0.3 and abs(div.value) > 0.2:
        if div.value > 0:
            parts.append("Phân kỳ bullish: giá đáy mới, dòng tiền giữ vững")
        else:
            parts.append("Phân kỳ bearish: giá đỉnh mới, dòng tiền yếu đi")

    conc = primitives.get("concentration")
    if conc and conc.confidence > 0.3 and abs(conc.value) > 0.3:
        if conc.value > 0:
            parts.append("Load-up day: dòng tiền dồn vào hôm nay")
        else:
            parts.append("Load-down day: xả mạnh hôm nay")

    if not parts:
        return f"Dòng tiền thông minh: {label} (chưa đủ tín hiệu)."
    return ". ".join(parts) + "."
