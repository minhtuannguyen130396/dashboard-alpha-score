"""Render markdown cho tầng tin tức — mọi câu chữ tiếng Việt tập trung ở đây.

Cùng vai trò với ``src/ta/format.py``: data structure giữ nguyên chất, câu chữ
nằm một chỗ, nên sửa một câu là terminal lẫn file HTML đổi theo.

Giọng văn theo đúng quy ước của repo: **mô tả trạng thái, không khuyến nghị**.
"CAR 5 phiên trước tin +6,1% trong khi thị trường +0,8%" là mô tả. "Nên mua" thì
không bao giờ xuất hiện ở đây.
"""
from typing import Dict, List, Optional, Sequence

from src.news.models import DIRECTION_VN, PURCHASED, SOLD
from src.news.reaction import Reaction

DISCLAIMER = ("_Số liệu kỹ thuật và thống kê, không phải khuyến nghị đầu tư._")


def _pct(value: Optional[float], digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{value * 100:+.{digits}f}%"


def _vol(value: Optional[float]) -> str:
    if value is None:
        return "—"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f} triệu"
    if value >= 1_000:
        return f"{value / 1_000:.0f} nghìn"
    return f"{value:.0f}"


# --- Giao dịch nội bộ / cổ đông lớn --------------------------------------

def format_execution_rate(registered: Optional[float],
                          executed: Optional[float]) -> str:
    """Diễn giải tỷ lệ thực hiện — và nói rõ khi *không đo được*.

    ``registered is None`` không phải là 0%. Đó là bản ghi từ thời quy định chưa
    bắt buộc đăng ký trước, nên không có gì để so. In "—" thay vì "0%" là khác
    biệt giữa mô tả trung thực và một tín hiệu bịa ra từ khoảng trống.
    """
    if not registered:
        return "không có đăng ký để đối chiếu"
    if executed is None:
        return "chưa có kết quả"
    rate = executed / registered
    if rate <= 0:
        return "0% — đăng ký rồi không thực hiện"
    if rate >= 0.99:
        return "100% — thực hiện đủ như đăng ký"
    return f"{rate * 100:.0f}% — thực hiện một phần"


def format_transaction(row: Dict) -> str:
    """Một dòng cho một giao dịch."""
    direction = DIRECTION_VN.get(row["direction"], "?")
    who = row["name"]
    role = row.get("position") or "cổ đông lớn"
    reg, ex = row.get("registered_volume"), row.get("execution_volume")
    when = str(row.get("start_date") or row.get("execution_date") or "")[:10]
    return (f"- **{when}** · {who} ({role}) — **{direction}** "
            f"đăng ký {_vol(reg)}, thực hiện {_vol(ex)} "
            f"→ {format_execution_rate(reg, ex)}")


def format_transactions(rows: Sequence[Dict], symbol: str,
                        limit: int = 10) -> str:
    if not rows:
        return f"## {symbol} — giao dịch nội bộ / cổ đông lớn\n\nKhông có bản ghi nào."
    insiders = [r for r in rows if r.get("position")]
    lines = [f"## {symbol} — giao dịch nội bộ / cổ đông lớn",
             "",
             f"{len(rows)} bản ghi, trong đó **{len(insiders)}** là người nội bộ "
             f"(có chức vụ), còn lại là cổ đông lớn.",
             ""]
    lines += [format_transaction(r) for r in rows[:limit]]
    if len(rows) > limit:
        lines.append(f"\n_… còn {len(rows) - limit} bản ghi nữa._")
    return "\n".join(lines)


# --- Phản ứng giá ---------------------------------------------------------

def _read_pattern(r: Reaction) -> str:
    """Câu đọc mẫu hình — mô tả *chỗ biến động nằm ở đâu*, không phán quyết.

    Ba cửa sổ cố ý được so với nhau chứ không cộng lại: một mã chạy hết trước
    ngày công bố rồi đi ngang trông y hệt một mã không phản ứng gì, nếu chỉ nhìn
    tổng.
    """
    pre, imm, post = r.car_pre, r.car_immediate, r.car_post
    if pre is None and imm is None:
        return "Chưa đủ dữ liệu để đọc mẫu hình."
    parts: List[str] = []
    big = 0.03      # 3% abnormal — đủ lớn để đáng nói với cửa sổ vài phiên
    if pre is not None and abs(pre) >= big:
        parts.append(f"phần lớn biến động xảy ra **trước** ngày sự kiện "
                     f"(CAR trước {_pct(pre)})")
    if imm is not None and abs(imm) >= big:
        parts.append(f"phản ứng **tức thì** rõ ({_pct(imm)} trong 2 phiên đầu)")
    if post is not None and abs(post) >= big:
        parts.append(f"còn **trôi tiếp** sau sự kiện ({_pct(post)} trong 10 phiên)")
    if not parts:
        return ("Không cửa sổ nào vượt ngưỡng đáng kể — giá đi gần đúng như quan hệ "
                "thường ngày với thị trường.")
    return "Đọc: " + "; ".join(parts) + "."


def format_reaction(r: Reaction, title: str = "") -> str:
    head = title or f"{r.symbol} — phản ứng giá quanh {r.t0_requested}"
    lines = [f"### {head}", ""]

    if r.t0_actual and r.t0_actual != str(r.t0_requested)[:10]:
        lines.append(f"> Mốc yêu cầu **{str(r.t0_requested)[:10]}**, phiên thật gần "
                     f"nhất là **{r.t0_actual}** (mốc rơi vào ngày nghỉ).")
        lines.append("")

    if r.note and r.alpha is None:
        lines += [f"⚠️ {r.note}", "", DISCLAIMER]
        return "\n".join(lines)

    lines += [
        f"Benchmark **{r.benchmark}**, ước lượng trên {r.n_est_bars} phiên "
        f"(β = {r.beta:.2f})." if r.beta is not None else "",
        "",
        "| Cửa sổ | Ý nghĩa | Abnormal return |",
        "|---|---|---|",
        f"| t-5 … t-1 | rò rỉ trước sự kiện | **{_pct(r.car_pre)}** |",
        f"| t0 … t+1 | phản ứng tức thì | **{_pct(r.car_immediate)}** |",
        f"| t+1 … t+10 | trôi sau sự kiện | **{_pct(r.car_post)}** |",
        "",
        f"Lợi suất thô t0→t+10: **{_pct(r.ret_raw)}** "
        f"(thị trường {_pct(r.ret_benchmark)}).",
    ]
    if r.volume_ratio is not None:
        lines.append(f"Volume phiên t0: **{r.volume_ratio:.1f}×** trung bình 20 phiên "
                     f"(z = {r.volume_z}).")
    lines += ["", _read_pattern(r)]

    if r.limit_hit:
        lines += ["", "⚠️ **Có phiên trần/sàn trong cửa sổ** — biên độ thật lớn hơn "
                      "con số đo được, phép đo bị cắt cụt."]
    if r.incomplete:
        lines += ["", f"⚠️ {r.note}"]
    lines += ["", DISCLAIMER]
    return "\n".join(line for line in lines if line != "" or True)


def format_impact(symbol: str, items: Sequence[tuple]) -> str:
    """Nhiều sự kiện của một mã, mỗi cái kèm phản ứng đo được.

    ``items`` là chuỗi ``(nhãn sự kiện, Reaction)``.
    """
    if not items:
        return f"## {symbol}\n\nKhông có sự kiện nào để đo."
    out = [f"## {symbol} — sự kiện và phản ứng giá đã đo", ""]
    for label, reaction in items:
        out.append(format_reaction(reaction, title=label))
        out.append("")
    return "\n".join(out)
