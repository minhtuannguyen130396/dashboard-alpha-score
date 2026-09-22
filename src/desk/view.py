"""Quan điểm cấp thị trường và cấp ngành — gói bằng chứng + hướng dẫn viết.

Đúng kiến trúc ``ta/thesis.py``, nhân lên hai cấp mới và **không viết lại**:
code gom bằng chứng, **model đang gọi tool** đọc rồi viết kết luận, và kết luận
rơi vào ``ledger`` chứ không vào một file rời.

Vì sao hướng dẫn nằm trong chuỗi tool trả về chứ không trong
``.claude/commands/``: file đó chỉ Claude Code đọc được, còn tool thì phải dùng
được từ **mọi** MCP client — cùng lý do ``thesis.WRITING_GUIDE`` đã nằm ở đây.

Hai luật riêng của cấp này, thêm vào chín luật của tầng một mã:

* **Phải có kịch bản kèm điều kiện, không phải một con số.** "VNINDEX 1.320–
  1.360 nếu độ rộng giữ trên 55%; thủng 1.290 thì kịch bản này sai" — không
  phải "VNINDEX sẽ lên 1.350".
* **Phải nói tỷ trọng tiền mặt.** Một quan điểm "thận trọng" không kèm con số
  là câu không sai được, và câu không sai được thì không vào sổ được.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from src.desk import calendar as calendar_mod
from src.desk import flows as flows_mod
from src.desk import ledger as ledger_mod

WRITING_GUIDE_MARKET = """\
## Việc của bạn

Gói bằng chứng dưới đây đã **đo xong**. Việc còn lại là **kết luận**: ghép các
phép đo rời thành một quan điểm về thị trường, rồi nói ra nó trước khi trình
bày bằng chứng.

### Bảy luật

1. **Kết luận trước, bằng chứng sau.**
2. **Kịch bản kèm điều kiện, không phải một con số.** "1.320–1.360 nếu độ rộng
   giữ trên 55%" — không phải "sẽ lên 1.350".
3. **Phải nói tỷ trọng tiền mặt.** Không có con số đó thì "thận trọng" là câu
   không sai được, và câu không sai được thì không chấm điểm được.
4. **`trigger` và `invalidation` bắt buộc**, và phải là mốc **có thật trong gói
   bằng chứng** — mức chỉ số, ngưỡng độ rộng, số phiên phân phối. Không tự nghĩ
   ra một con số tròn trịa.
5. **Dòng tiền là MÔ TẢ.** Hiệu chuẩn D1/D2 đã chạy trên 16 năm và không giả
   thuyết nào đạt, nên không được dùng "khối ngoại mua ròng" làm **lý do chính**
   cho một quan điểm. Nêu ra thì được, dựa vào đó thì không.
6. **Hai cách đọc lệch nhau thì nói ra chỗ lệch** — chỉ số tăng mà độ rộng co
   lại, khung tuần ngược khung ngày.
7. **Không bịa.** Mọi con số phải truy ngược được về gói bằng chứng.

### Nộp lại

Gọi `desk_log_view` với `kind="market"`, `subject="VNINDEX"`, `session` =
**phiên dữ liệu** ghi ở đầu gói, `author` = tên model của chính bạn,
`stance` ∈ tang / tang_cho / trung_lap / dung_ngoai / giam, `confidence` ∈
cao / vua / thap, `horizon_sessions`, `trigger`, `invalidation`, và
`evidence` = một đoạn của chính gói này (sẽ được băm thành vân tay).
"""

WRITING_GUIDE_SECTOR = """\
## Việc của bạn

Kết luận ở **cấp ngành**: ngành này nên được nâng, giữ hay hạ tỷ trọng so với
phần còn lại của rổ, và điều gì làm kết luận đó sai.

### Sáu luật

1. **So với rổ, không so với 0.** "Ngành tăng 4%" không nói gì nếu cả thị
   trường tăng 5%.
2. **Nói ra số thành viên thật.** Chỉ số ngành ICB tính trên **toàn bộ** thành
   viên ở cả ba sàn (Năng lượng 33 mã, Công nghiệp 505), trong khi rổ ở đây chỉ
   có vài mã. "Năng lượng +9,2%" không phải chuyện của riêng BSR/PLX/PVD/PVT.
3. **Điểm ngành là MÔ TẢ, không phải dự báo** — hiệu chuẩn `macro/calibrate.py`
   đã kết luận như vậy và `score.py` bắt buộc mang `calibration_note()`.
4. **`trigger` / `invalidation` bắt buộc.**
5. **Ngành dưới 3 mã trong rổ thì mọi phép so tương đối để trống**, không trả 0.
6. **Không bịa.**

### Nộp lại

`desk_log_view` với `kind="sector"`, `subject` = tên ngành đúng như trong gói.
"""


@dataclass
class Evidence:
    kind: str
    subject: str
    as_of: str
    blocks: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def text(self) -> str:
        return "\n\n".join(self.blocks)

    @property
    def fingerprint(self) -> str:
        return ledger_mod.hash_evidence(self.text())

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "subject": self.subject, "as_of": self.as_of,
                "fingerprint": self.fingerprint, "notes": self.notes}


def build_market_evidence(as_of: Optional[datetime] = None,
                          as_of_requested: Optional[str] = None) -> Evidence:
    """Gói bằng chứng cấp thị trường — bảy nguồn, một gói."""
    from src.desk import format as desk_format
    from src.ta import market as market_mod
    from src.ta import format as ta_format

    ev = Evidence(kind="market", subject="VNINDEX", as_of="")
    blocks: List[str] = []

    regime = None
    try:
        regime = market_mod.build_regime(as_of=as_of)
    except Exception as exc:                                   # noqa: BLE001
        ev.notes.append(f"chưa đọc được bối cảnh thị trường: {exc}")
    if regime is not None and not getattr(regime, "is_empty", False):
        ev.as_of = getattr(regime, "as_of", "") or ev.as_of
        blocks.append("## 1. Chỉ số và độ rộng\n\n"
                      + _regime_lines(regime))
    else:
        blocks.append("## 1. Chỉ số và độ rộng\n\n⚠️ **chưa đo được** — đừng đọc "
                      "thành thị trường trung tính.")

    board = flows_mod.build_board(None, as_of=as_of,
                                  as_of_requested=as_of_requested)
    ev.as_of = ev.as_of or board.as_of
    blocks.append("## 2. Dòng tiền\n\n"
                  + desk_format.format_flow_board(board, limit=6))

    try:
        from src.ta import futures as futures_mod
        snap = futures_mod.build_futures_snapshot(as_of=as_of)
        blocks.append("## 3. Phái sinh\n\n" + ta_format.format_futures(snap))
    except Exception as exc:                                   # noqa: BLE001
        ev.notes.append(f"chưa đọc được phái sinh: {exc}")

    cal = calendar_mod.build(as_of=as_of, days=20)
    blocks.append("## 4. Lịch xúc tác 20 ngày tới\n\n"
                  + desk_format.format_calendar(cal, limit=15))

    card_note = _scorecard_hint(as_of)
    if card_note:
        blocks.append("## 5. Sổ của chính bàn\n\n" + card_note)

    ev.as_of = ev.as_of or (as_of or datetime.now()).strftime("%Y-%m-%d")
    ev.blocks = blocks
    return ev


def _regime_lines(regime: Any) -> str:
    bits = [f"- **{getattr(regime, 'headline', '')}**"]
    for attr, label in (("close", "đóng cửa"), ("change_pct", "% phiên"),
                        ("rsi14", "RSI14"), ("adx14", "ADX14")):
        value = getattr(regime, attr, None)
        if value is not None:
            bits.append(f"- {label}: `{value}`")
    breadth = getattr(regime, "breadth", None)
    if breadth is not None:
        bits.append(f"- Độ rộng: {breadth.label}")
    dist = getattr(regime, "distribution_days", None)
    if dist is not None:
        bits.append(f"- Phiên phân phối gần đây: {dist}")
    return "\n".join(bits)


def _scorecard_hint(as_of: Optional[datetime]) -> str:
    from src.desk import scorecard as scorecard_mod
    card = scorecard_mod.build(as_of=as_of, draws=0)
    if not card.outcomes:
        return ("Sổ chưa có quan điểm nào — **chưa có gì để tự chấm**. Đây là "
                "thông tin: bàn này chưa có lịch sử để bạn dựa vào.")
    return (f"{card.n_complete}/{len(card.outcomes)} quan điểm đã đủ hạn. "
            f"{card.note}")


def build_sector_evidence(sector: str, as_of: Optional[datetime] = None
                          ) -> Evidence:
    """Gói bằng chứng cấp ngành. Phần lớn đã có ở ``macro/``; đây là chỗ gộp."""
    from src.desk import format as desk_format

    ev = Evidence(kind="sector", subject=sector.strip(), as_of="")
    blocks: List[str] = []
    try:
        from src.macro import format as macro_format
        from src.macro import score as macro_score
        board = macro_score.build(as_of=as_of)
        blocks.append("## 1. Bảng ngành\n\n" + macro_format.format_board(board))
        ev.as_of = getattr(board, "as_of", "") or ev.as_of
    except Exception as exc:                                   # noqa: BLE001
        ev.notes.append(f"chưa dựng được bảng ngành: {exc}")

    board = flows_mod.build_board(None, as_of=as_of)
    ev.as_of = ev.as_of or board.as_of
    rows = [s for s in board.sectors
            if sector.strip().lower() in (s.name or "").lower()]
    if rows:
        s = rows[0]
        blocks.append(
            "## 2. Dòng tiền ngành\n\n"
            f"- {s.name}: khối ngoại `{s.foreign_net_bn:+,.1f}` tỷ phiên · "
            f"`{s.foreign_net_5d_bn:+,.1f}` tỷ 5 phiên\n"
            f"- {s.n_members}/{s.n_total} mã của ngành nằm trong rổ"
            + (" — **dưới 3 mã, con số này là của mấy cái tên cụ thể chứ không "
               "phải của ngành**" if s.thin else ""))
    else:
        ev.notes.append("không khớp được ngành nào trong bảng dòng tiền")

    ev.as_of = ev.as_of or (as_of or datetime.now()).strftime("%Y-%m-%d")
    ev.blocks = blocks
    return ev


def brief(evidence: Evidence) -> str:
    """Gói bằng chứng + hướng dẫn, đúng thứ model đọc từ trên xuống."""
    guide = (WRITING_GUIDE_MARKET if evidence.kind == "market"
             else WRITING_GUIDE_SECTOR)
    head = (f"# Gói bằng chứng — {evidence.subject} · phiên {evidence.as_of}\n\n"
            f"Nộp lại với `session` = **{evidence.as_of}** (phiên dữ liệu, không "
            f"phải ngày hôm nay) và `evidence_hash` = `{evidence.fingerprint}`.")
    notes = ("\n".join(f"> ⚠️ {n}" for n in evidence.notes) + "\n\n"
             if evidence.notes else "")
    return "\n\n---\n\n".join([guide, head + "\n\n" + notes, evidence.text()])
