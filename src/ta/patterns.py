"""Name the shape formed by the upper and lower trendlines.

Two slopes and whether they converge is enough to separate the classic
formations. The value is not the label but the sentence attached to it: what
the shape implies, and which level turns the implication into an action.
"""
from dataclasses import asdict, dataclass
from typing import List, Optional, Sequence

from src.analysis.technical_indicators import IndicatorGroup3
from src.data.stock_data_loader import StockRecord
from src.ta.trendlines import RESISTANCE, SUPPORT, TrendLine

NONE = "none"
RECTANGLE = "rectangle"
ASCENDING_TRIANGLE = "ascending_triangle"
DESCENDING_TRIANGLE = "descending_triangle"
SYMMETRIC_TRIANGLE = "symmetric_triangle"
RISING_CHANNEL = "rising_channel"
FALLING_CHANNEL = "falling_channel"
RISING_WEDGE = "rising_wedge"
FALLING_WEDGE = "falling_wedge"
BROADENING = "broadening"

PATTERN_NAMES = {
    NONE: "Không rõ hình mẫu",
    RECTANGLE: "Vùng đi ngang (hình chữ nhật)",
    ASCENDING_TRIANGLE: "Tam giác tăng",
    DESCENDING_TRIANGLE: "Tam giác giảm",
    SYMMETRIC_TRIANGLE: "Tam giác cân",
    RISING_CHANNEL: "Kênh giá tăng",
    FALLING_CHANNEL: "Kênh giá giảm",
    RISING_WEDGE: "Nêm tăng",
    FALLING_WEDGE: "Nêm giảm",
    BROADENING: "Mô hình loa (biên độ mở rộng)",
}

#: What each shape usually resolves into. Bias is a tendency, never a promise —
#: the wording keeps the breakout level as the thing that decides.
PATTERN_BIAS = {
    RECTANGLE: "neutral",
    ASCENDING_TRIANGLE: "bullish",
    DESCENDING_TRIANGLE: "bearish",
    SYMMETRIC_TRIANGLE: "neutral",
    RISING_CHANNEL: "bullish",
    FALLING_CHANNEL: "bearish",
    RISING_WEDGE: "bearish",
    FALLING_WEDGE: "bullish",
    BROADENING: "neutral",
    NONE: "neutral",
}


@dataclass
class Pattern:
    kind: str
    name: str
    bias: str                          # bullish | bearish | neutral
    upper_slope_pct: Optional[float]   # percent per bar
    lower_slope_pct: Optional[float]
    converging: Optional[bool]
    apex_bars: Optional[int]           # bars until the two lines meet
    upper_now: Optional[float]
    lower_now: Optional[float]
    label: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _tilt(line: TrendLine, atr: float, bars: int = 20) -> str:
    """Flat / rising / falling, judged against how far price normally travels."""
    move = line.slope * bars
    if abs(move) < 0.5 * atr:
        return "flat"
    return "rising" if move > 0 else "falling"


def classify(
    records: List[StockRecord],
    lines: Sequence[TrendLine],
    atr: Optional[Sequence[Optional[float]]] = None,
) -> Pattern:
    upper = next((l for l in lines if l.kind == RESISTANCE), None)
    lower = next((l for l in lines if l.kind == SUPPORT), None)
    if upper is None or lower is None or not records:
        return Pattern(NONE, PATTERN_NAMES[NONE], "neutral", None, None, None, None,
                       upper.value_now if upper else None,
                       lower.value_now if lower else None,
                       label="Chưa đủ đường xu hướng hai phía để xác định hình mẫu.")

    atr_s = list(atr) if atr is not None else IndicatorGroup3.atr(records, 14)
    atr_now = next((float(v) for v in reversed(atr_s) if v is not None),
                   sum(r.priceHigh - r.priceLow for r in records) / len(records))

    n = len(records)
    up_tilt = _tilt(upper, atr_now)
    low_tilt = _tilt(lower, atr_now)

    overlap_start = max(upper.p1_index, lower.p1_index)
    gap_start = upper.value_at(overlap_start) - lower.value_at(overlap_start)
    gap_now = upper.value_at(n - 1) - lower.value_at(n - 1)
    converging = gap_now < 0.7 * gap_start if gap_start > 0 else False

    slope_gap = upper.slope - lower.slope
    apex_bars = None
    if slope_gap < 0 and gap_now > 0:
        bars = gap_now / -slope_gap
        if 0 < bars < 200:
            apex_bars = int(round(bars))

    if up_tilt == "flat" and low_tilt == "rising":
        kind = ASCENDING_TRIANGLE
    elif up_tilt == "falling" and low_tilt == "flat":
        kind = DESCENDING_TRIANGLE
    elif up_tilt == "falling" and low_tilt == "rising":
        kind = SYMMETRIC_TRIANGLE
    elif up_tilt == "flat" and low_tilt == "flat":
        kind = RECTANGLE
    elif up_tilt == "rising" and low_tilt == "rising":
        kind = RISING_WEDGE if converging else RISING_CHANNEL
    elif up_tilt == "falling" and low_tilt == "falling":
        kind = FALLING_WEDGE if converging else FALLING_CHANNEL
    elif up_tilt == "rising" and low_tilt == "falling":
        kind = BROADENING
    else:
        kind = NONE

    pattern = Pattern(
        kind=kind,
        name=PATTERN_NAMES[kind],
        bias=PATTERN_BIAS[kind],
        upper_slope_pct=upper.slope_pct_per_bar,
        lower_slope_pct=lower.slope_pct_per_bar,
        converging=converging,
        apex_bars=apex_bars,
        upper_now=upper.value_now,
        lower_now=lower.value_now,
    )
    pattern.label = describe_pattern(pattern)
    return pattern


def describe_pattern(p: Pattern) -> str:
    if p.kind == NONE:
        return p.label or "Chưa đủ đường xu hướng hai phía để xác định hình mẫu."

    edges = f"Cạnh trên {p.upper_now}, cạnh dưới {p.lower_now}"
    apex = f" Hai cạnh hội tụ sau khoảng {p.apex_bars} phiên." if p.apex_bars else ""

    meaning = {
        ASCENDING_TRIANGLE: (
            f"Đáy nâng dần ép vào kháng cự ngang {p.upper_now} — bên mua kiên nhẫn hơn. "
            f"Vượt {p.upper_now} kèm volume là điểm mua; thủng cạnh dưới thì mô hình hỏng."
        ),
        DESCENDING_TRIANGLE: (
            f"Đỉnh thấp dần ép xuống hỗ trợ ngang {p.lower_now} — bên bán chủ động. "
            f"Thủng {p.lower_now} là tín hiệu bán; vượt cạnh trên mới đảo được kịch bản."
        ),
        SYMMETRIC_TRIANGLE: (
            f"Biên độ co lại từ cả hai phía, chưa bên nào thắng. "
            f"Chờ đóng cửa ra ngoài {p.lower_now}–{p.upper_now} rồi mới hành động theo hướng đó."
        ),
        RECTANGLE: (
            f"Giá đi ngang giữa {p.lower_now} và {p.upper_now}. "
            f"Chiến thuật vùng: mua cạnh dưới bán cạnh trên, hoặc chờ phá vỡ kèm volume."
        ),
        RISING_CHANNEL: (
            f"Kênh tăng đều. Cạnh dưới {p.lower_now} là vùng mua theo xu hướng, "
            f"cạnh trên {p.upper_now} là vùng chốt; thủng cạnh dưới là gãy xu hướng."
        ),
        FALLING_CHANNEL: (
            f"Kênh giảm đều. Cạnh trên {p.upper_now} là vùng bán/hạ tỷ trọng; "
            f"chỉ khi vượt {p.upper_now} mới tính đến đảo chiều."
        ),
        RISING_WEDGE: (
            f"Nêm tăng — giá còn lên nhưng đà yếu dần, thường kết thúc bằng phá xuống. "
            f"Mốc cảnh báo là cạnh dưới {p.lower_now}."
        ),
        FALLING_WEDGE: (
            f"Nêm giảm — đà bán cạn dần, thường kết thúc bằng phá lên. "
            f"Mốc kích hoạt là cạnh trên {p.upper_now}."
        ),
        BROADENING: (
            "Biên độ mở rộng hai phía — thị trường mất phương hướng, rủi ro whipsaw cao. "
            "Nên đứng ngoài cho đến khi biên độ co lại."
        ),
    }[p.kind]

    return f"**{p.name}.** {edges}.{apex} {meaning}"
