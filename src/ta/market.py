"""Bối cảnh thị trường chung: cái nền mà mọi mã đứng lên trên.

``CLAUDE.md`` đã nói việc của VNINDEX là **so sánh** — một mã tăng 8% trong
tháng mà chỉ số tăng 9% là *tụt lại*, không phải khoẻ. Module này làm nốt vế
còn lại của câu đó: trước khi so, phải biết chính cái nền đang đi lên hay đi
xuống, và nó đang kéo theo bao nhiêu mã.

Ba phép đo, ba câu hỏi khác nhau — cố ý **không** gộp thành một điểm:

* **Chỉ số** (VNINDEX): nền đang ở đâu so với MA20/MA50 của chính nó, khung
  ngày và khung tuần.
* **Độ rộng**: bao nhiêu phần trăm rổ đang trên EMA20. Chỉ số là bình quân có
  trọng số — ba mã vốn hoá lớn kéo nó lên trong khi 60 mã còn lại đi xuống là
  chuyện xảy ra thật, và chỉ độ rộng nhìn thấy điều đó.
* **Phiên phân phối**: chỉ số giảm kèm volume *lớn hơn* phiên trước. Đây là
  phép đo O'Neil, và nó trả lời đúng câu checklist hỏi — "chỉ số vừa có phiên
  phân phối mạnh chưa" — mà hai phép đo trên không trả lời được.

Độ rộng **đọc lại** ``reports/xep_hang_moi_nhat.json`` chứ không quét lại cả
rổ: ``build_ranking`` đã tính ``vs_ema20`` cho đủ 79 mã, và dựng lại lần nữa
cho một hồ sơ một mã là trả giá 79 lượt nạp để lấy một con số. Đúng quy ước
"xếp hạng lại thì đọc file JSON, đừng dựng lại" — kèm cái giá của nó: bảng cũ
thì độ rộng cũng cũ, nên ``stale_days`` luôn đi theo.
"""
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, List, Optional, Sequence

from src.ta import weekly as weekly_mod
from src.ta.snapshot import Snapshot, build_snapshot
from src.ta.weekly import WeeklyView

#: Chỉ số nền. VNINDEX chứ không phải VN30: câu hỏi ở đây là "cả thị trường
#: đang đi đâu", và VN30 bỏ ra ngoài hàng trăm mã vừa và nhỏ.
INDEX_SYMBOL = "VNINDEX"

#: Cửa sổ đếm phiên phân phối. 25 phiên ≈ 5 tuần giao dịch — đủ dài để một
#: chuỗi phân phối hiện ra thành cụm, đủ ngắn để phiên của tháng trước không
#: còn nói gì về tư thế hôm nay.
DISTRIBUTION_WINDOW = 25

#: Chỉ số giảm dưới mức này thì chưa tính là phân phối — dao động 0,1% là
#: nhiễu làm tròn của một chỉ số bình quân, không phải ai đó bán ra.
DISTRIBUTION_DROP_PCT = 0.2

#: Bảng xếp hạng cũ hơn ngần này phiên thì độ rộng nói về một thị trường khác.
BREADTH_STALE_DAYS = 5


@dataclass
class Breadth:
    """Độ rộng — bao nhiêu mã trong rổ thật sự đang đi cùng chiều chỉ số."""
    source_as_of: str
    n: int
    above_ema20: int = 0
    above_ema50: int = 0
    trend_up: int = 0
    trend_down: int = 0
    stale_days: int = 0
    note: str = ""

    @property
    def pct_above_ema20(self) -> Optional[float]:
        return round(self.above_ema20 / self.n * 100, 1) if self.n else None

    @property
    def pct_above_ema50(self) -> Optional[float]:
        return round(self.above_ema50 / self.n * 100, 1) if self.n else None

    @property
    def pct_trend_up(self) -> Optional[float]:
        return round(self.trend_up / self.n * 100, 1) if self.n else None

    @property
    def label(self) -> str:
        pct = self.pct_above_ema20
        if pct is None:
            return "chưa đo được độ rộng"
        if pct >= 70:
            read = "dòng tiền lan rộng"
        elif pct >= 50:
            read = "dòng tiền còn giữ được phần lớn rổ"
        elif pct >= 30:
            read = "dòng tiền đang co lại"
        else:
            read = "dòng tiền suy kiệt, chỉ còn số ít mã giữ được"
        return f"{pct:g}% rổ trên EMA20 ({self.above_ema20}/{self.n}) — {read}"

    def to_dict(self) -> dict:
        out = asdict(self)
        out.update(pct_above_ema20=self.pct_above_ema20,
                   pct_above_ema50=self.pct_above_ema50,
                   pct_trend_up=self.pct_trend_up, label=self.label)
        return out


@dataclass
class MarketRegime:
    """Tư thế của cả nền, gói lại đủ để một model đọc mà không phải tra thêm."""
    as_of: str = ""
    symbol: str = INDEX_SYMBOL
    bars: int = 0
    close: Optional[float] = None
    change_pct: Optional[float] = None
    change_5d: Optional[float] = None
    change_20d: Optional[float] = None
    vs_ema20_pct: Optional[float] = None
    vs_ema50_pct: Optional[float] = None
    rsi14: Optional[float] = None
    adx14: Optional[float] = None
    adx_direction: str = ""
    trend_label: str = ""
    structure_label: str = ""
    weekly: Optional[WeeklyView] = None
    breadth: Optional[Breadth] = None
    distribution_days: Optional[int] = None
    distribution_dates: List[str] = field(default_factory=list)
    #: ``up`` / ``down`` / ``flat`` — rút gọn của chỉ số khung ngày, để tầng
    #: trên so với mã mà không phải tự đọc lại bốn con số.
    side: str = "flat"
    notes: List[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return self.bars == 0

    @property
    def headline(self) -> str:
        """Một câu kết luận về cái nền — chỗ mọi mục 1 của báo cáo bắt đầu."""
        if self.is_empty:
            return "Chưa đọc được VNINDEX — không có bối cảnh thị trường"
        names = {"up": "Thị trường đang tăng", "down": "Thị trường đang giảm",
                 "flat": "Thị trường đi ngang / chưa rõ chiều"}
        parts = [names.get(self.side, names["flat"])]
        if self.breadth is not None and self.breadth.pct_above_ema20 is not None:
            parts.append(self.breadth.label)
        if self.distribution_days:
            parts.append(f"{self.distribution_days} phiên phân phối trong "
                         f"{DISTRIBUTION_WINDOW} phiên gần nhất")
        return " · ".join(parts)

    def to_dict(self) -> dict:
        out = asdict(self)
        out["weekly"] = self.weekly.to_dict() if self.weekly else None
        out["breadth"] = self.breadth.to_dict() if self.breadth else None
        out["headline"] = self.headline
        return out


def load_board(as_of: Optional[datetime] = None):
    """Bảng xếp hạng đã lưu, hoặc ``None`` khi chưa dựng bảng nào.

    Nuốt lỗi có chủ ý: hồ sơ kỹ thuật không được chết vì một file phụ chưa có.
    Người gọi phân biệt bằng ``None`` rồi tự nói ra là thiếu.
    """
    from src.ta import ranking as ranking_mod
    try:
        return ranking_mod.load_ranking(as_of=as_of)
    except Exception:                                    # noqa: BLE001
        return None


def build_breadth(board, ref_date: str = "") -> Optional[Breadth]:
    """Độ rộng rút từ bảng xếp hạng đã lưu."""
    if board is None or not getattr(board, "rows", None):
        return None
    rows = [r for r in board.rows if r.close is not None]
    if not rows:
        return None

    out = Breadth(source_as_of=board.as_of, n=len(rows))
    for r in rows:
        if (r.vs_ema20 or 0) > 0:
            out.above_ema20 += 1
        if (r.vs_ema50 or 0) > 0:
            out.above_ema50 += 1
        side = getattr(r.trend, "side", "") if r.trend is not None else ""
        if side == "up":
            out.trend_up += 1
        elif side == "down":
            out.trend_down += 1

    if ref_date and board.as_of and board.as_of != ref_date:
        try:
            delta = (datetime.strptime(ref_date, "%Y-%m-%d")
                     - datetime.strptime(board.as_of, "%Y-%m-%d")).days
        except ValueError:
            delta = 0
        out.stale_days = max(delta, 0)
        if out.stale_days >= BREADTH_STALE_DAYS:
            out.note = (f"Bảng xếp hạng dừng ở {board.as_of}, báo cáo đứng ở {ref_date} "
                        f"— độ rộng đang nói về một thị trường cách đây "
                        f"{out.stale_days} ngày. Chạy `build_ranking` để làm mới.")
        else:
            out.note = f"Độ rộng lấy từ bảng xếp hạng ngày {board.as_of}."
    return out


def distribution_days(records: Sequence[Any],
                      window: int = DISTRIBUTION_WINDOW) -> List[str]:
    """Ngày của các phiên phân phối trong ``window`` phiên gần nhất.

    Định nghĩa O'Neil: chỉ số **giảm** đáng kể trong khi volume **cao hơn**
    phiên liền trước. Volume tăng trong một phiên giảm nghĩa là có người chủ
    động bán ra, chứ không phải thị trường nghỉ tay — đó là chỗ nó khác một
    phiên giảm volume thấp, thứ chỉ nói lên là không ai muốn mua.
    """
    recs = list(records)[-(window + 1):]
    out: List[str] = []
    for prev, cur in zip(recs, recs[1:]):
        if not prev.priceClose:
            continue
        drop = (cur.priceClose / prev.priceClose - 1.0) * 100
        if drop <= -DISTRIBUTION_DROP_PCT and cur.priceImpactVolume > prev.priceImpactVolume:
            out.append(cur.date.strftime("%Y-%m-%d"))
    return out


def build_regime(as_of: Optional[datetime] = None,
                 board: Any = None,
                 snapshot: Optional[Snapshot] = None) -> MarketRegime:
    """Bối cảnh thị trường cho một mốc. ``board`` truyền sẵn để khỏi đọc file hai lần."""
    snap = snapshot if snapshot is not None else build_snapshot(
        INDEX_SYMBOL, as_of=as_of, lookback_days=400)
    if not snap.bars:
        return MarketRegime(notes=[
            f"Chưa nạp được {INDEX_SYMBOL} — chạy `/update` để có bối cảnh thị trường. "
            f"Không có nó thì mọi câu 'mã này khoẻ hay yếu' đều thiếu mẫu số."])

    out = MarketRegime(
        as_of=snap.as_of, bars=snap.bars,
        close=snap.price.get("close"),
        change_pct=snap.price.get("change_pct"),
        change_5d=snap.price.get("change_5d"),
        change_20d=snap.price.get("change_20d"),
        vs_ema20_pct=snap.trend.get("vs_ema20_pct"),
        vs_ema50_pct=snap.trend.get("vs_ema50_pct"),
        rsi14=snap.momentum.get("rsi14"),
        adx14=snap.adx.get("adx"),
        adx_direction=snap.adx.get("direction", ""),
        trend_label=snap.trend.get("label", ""),
        structure_label=snap.trend.get("structure_label", ""),
    )

    e20, e50 = out.vs_ema20_pct, out.vs_ema50_pct
    if e20 is not None and e50 is not None:
        if e20 > 0 and e50 > 0:
            out.side = "up"
        elif e20 < 0 and e50 < 0:
            out.side = "down"

    out.weekly = weekly_mod.build_view(INDEX_SYMBOL, as_of)

    board = board if board is not None else load_board(as_of)
    out.breadth = build_breadth(board, ref_date=snap.as_of)
    if out.breadth is None:
        out.notes.append(
            "Chưa có bảng xếp hạng nào nên **độ rộng thị trường để trống** — chạy "
            "`build_ranking` trước. Đây là chỗ trống, không phải 'độ rộng trung tính'.")
    elif out.breadth.note:
        out.notes.append(out.breadth.note)

    # Chuỗi giá của chính chỉ số, để đếm phiên phân phối. ``build_snapshot``
    # không giữ lại records nên nạp riêng — một mã, rẻ.
    from src.ta.loader import load_recent
    recs = load_recent(INDEX_SYMBOL, 120, as_of)
    out.distribution_dates = distribution_days(recs)
    out.distribution_days = len(out.distribution_dates)
    return out
