"""Hai sản phẩm in ra của bàn: **bản tin phiên** và **bản chiến lược**.

Không module nào ở đây tự viết câu: chúng gọi ``format.py`` của chính tầng này
và của các tầng dưới, rồi render lại markdown đó thành HTML bằng đúng bộ
``_md_to_html`` + ``REPORT_CSS`` mà ``ta/dossier.py`` dùng. Sửa một câu ở
``format.py`` là cả terminal lẫn file HTML đổi theo — cùng quy ước đã có.

Khác nhau giữa hai sản phẩm là **ai viết phần kết luận**:

* **Bản tin phiên** không có kết luận. Nó là tập hợp phép đo của một phiên:
  chỉ số, độ rộng, dòng tiền, phái sinh, lịch xúc tác. Không cần model nào ngồi
  viết, nên nó chạy được mỗi ngày mà không tốn gì.
* **Bản chiến lược** có kết luận, và kết luận đó **phải đã nằm trong sổ**. Nếu
  sổ trống thì bản chiến lược nói thẳng là chưa có quan điểm nào — chứ không
  tự sinh ra một câu trung tính, vì một câu trung tính viết sẵn trông y hệt
  một kết luận đã có người đọc.
"""
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

from src.desk import book as book_mod
from src.desk import calendar as calendar_mod
from src.desk import consistency as consistency_mod
from src.desk import flows as flows_mod
from src.desk import format as desk_format
from src.desk import ledger as ledger_mod
from src.desk import scorecard as scorecard_mod
from src.ta import asof as asof_mod
from src.ta.loader import PROJECT_ROOT

REPORT_ROOT = PROJECT_ROOT / "reports"


# ---------------------------------------------------------------------------
def daily_brief(as_of: Optional[datetime] = None,
                as_of_requested: Optional[str] = None, limit: int = 8) -> str:
    """Bản tin phiên — toàn phép đo, không có kết luận của ai."""
    from src.ta import format as ta_format
    from src.ta import market as market_mod

    parts: List[str] = []
    board = flows_mod.build_board(None, as_of=as_of,
                                  as_of_requested=as_of_requested)
    session = board.as_of or (as_of or datetime.now()).strftime("%Y-%m-%d")
    parts.append(f"# Bản tin phiên {session}")

    try:
        regime = market_mod.build_regime(as_of=as_of)
        if regime is not None and not getattr(regime, "is_empty", False):
            parts.append("## Thị trường\n\n"
                         f"- **{getattr(regime, 'headline', '')}**\n"
                         f"- VNINDEX `{getattr(regime, 'close', '—')}` "
                         f"({getattr(regime, 'change_pct', 0):+.2f}% phiên)\n"
                         f"- RSI14 `{getattr(regime, 'rsi14', '—')}` · ADX14 "
                         f"`{getattr(regime, 'adx14', '—')}`")
    except Exception as exc:                                   # noqa: BLE001
        parts.append(f"## Thị trường\n\n⚠️ chưa đọc được: {exc}")

    parts.append(desk_format.format_flow_board(board, limit=limit))

    try:
        from src.ta import futures as futures_mod
        snap = futures_mod.build_futures_snapshot(as_of=as_of)
        parts.append("## Phái sinh\n\n" + ta_format.format_futures_brief(snap))
    except Exception:                                          # noqa: BLE001
        pass

    cal = calendar_mod.build(as_of=as_of, days=14)
    parts.append("## Phiên tới nhìn gì\n\n"
                 + desk_format.format_calendar(cal, limit=12))

    standings = ledger_mod.standings(as_of=as_of)
    open_rows = [s for s in standings if s.status == ledger_mod.OPEN]
    if open_rows:
        parts.append(desk_format.format_standings(open_rows, "Sổ đang mở"))
    return "\n\n".join(parts)


def strategy_brief(as_of: Optional[datetime] = None) -> str:
    """Bản chiến lược — quan điểm + phân bổ + sổ, và phần kiểm tra chéo."""
    standings = ledger_mod.standings(as_of=as_of)
    open_rows = [s for s in standings if s.status == ledger_mod.OPEN]
    b = book_mod.build(as_of=as_of)
    checks = consistency_mod.check(b, as_of=as_of)
    card = scorecard_mod.build(as_of=as_of)
    session = b.as_of

    parts = [f"# Chiến lược — {session}", ""]

    market = [s for s in open_rows if s.entry.kind == "market"]
    if market:
        parts.append("## Quan điểm thị trường\n\n"
                     + desk_format.format_entry(market[-1].entry,
                                                market[-1].status_label,
                                                market[-1].age_sessions))
    else:
        parts.append("## Quan điểm thị trường\n\n**Chưa có.** Đây là *chưa ai "
                     "viết*, không phải *bàn này trung lập*. Dựng gói bằng chứng "
                     "bằng `desk_market_evidence` rồi nộp qua `desk_log_view`.")

    sectors = [s for s in open_rows if s.entry.kind == "sector"]
    if sectors:
        parts.append("## Phân bổ ngành\n\n"
                     + "\n".join(desk_format.format_entry(s.entry) for s in sectors))
    else:
        parts.append("## Phân bổ ngành\n\n**Chưa có nấc ngành nào được viết.**")

    parts.append(desk_format.format_book(b))
    parts.append(desk_format.format_consistency(checks))
    parts.append(desk_format.format_scorecard(card))
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
_HTML_SHELL = """<!DOCTYPE html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{css}</style></head>
<body><div class="wrap">{body}</div>
<p class="foot">{foot}</p></body></html>
"""


def write_html(markdown: str, name: str, title: str,
               as_of: Optional[datetime] = None,
               out_dir: Optional[Path] = None) -> str:
    """Ghi file HTML **tự chứa** vào ``reports/<ngày>/``.

    Không link CDN, không ảnh ngoài — file còn phải mở được khi offline hoặc
    sau khi gửi đi nơi khác, đúng quy ước của mọi file HTML trong repo.
    """
    from src.ta.dossier import _md_to_html
    from src.ta.report import REPORT_CSS

    root = Path(out_dir) if out_dir else asof_mod.out_root(REPORT_ROOT, as_of)
    root.mkdir(parents=True, exist_ok=True)
    tag = asof_mod.file_tag(as_of)
    path = root / (f"{name}{tag}.html" if tag else f"{name}.html")
    body = _md_to_html(markdown)
    foot = ("Số liệu kỹ thuật, không phải khuyến nghị đầu tư · dựng bởi "
            f"src/desk · {datetime.now():%Y-%m-%d %H:%M}")
    path.write_text(_HTML_SHELL.format(title=title, css=REPORT_CSS, body=body,
                                       foot=foot), encoding="utf-8")
    return str(path)
