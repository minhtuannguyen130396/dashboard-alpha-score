"""Điểm ngành — **mô tả**, không phải dự báo. Và ranh giới đó do dữ liệu quyết định.

§5 của `Documents/plan_macro_sector.md` thiết kế ba trụ với trần điểm là "đề
xuất khởi điểm", kèm một câu ràng buộc: *trần điểm thật do §7 quyết*. §7 đã
chạy, và nó trả về **ba kết quả âm tính**:

* **H1** — góc RRG tại t không dự báo được lợi suất tương đối ở t+20. Cửa sổ 20
  phiên cho *dẫn dắt* một p = 0,025 trông như phát hiện; chạy thêm cửa sổ 10 và
  60 phiên thì không cửa sổ nào còn ý nghĩa. 12 phép kiểm ở mức 0,05 kỳ vọng
  sinh 0,6 dương tính giả — một p = 0,025 lẻ loi nằm gọn trong đó.
* **H2** — xu hướng ROE ngành không dự báo được gì; cả hai nhóm nằm đúng trên
  nền placebo.
* **H3** — chưa chạy được, cần ≥ 6 tháng điểm tin tích luỹ.

Hệ quả, và nó là điều khoản chính của module này: **không trụ nào được phép
tuyên bố sức dự báo.** Điểm ở đây trả lời *"ngành này đang ở đâu so với các
ngành khác, ngay lúc này"* — một câu mô tả kiểm chứng được — chứ không phải
*"ngành nào sẽ tăng"*. Hai câu đó nghe giống nhau và khác nhau hoàn toàn về
thứ người đọc được phép làm với chúng.

Điều đó **không** làm bảng này vô dụng. Nó vẫn gộp năm phép đo rời rạc thành
một thứ tự đọc được, vẫn tháo ngược ra được từng thành phần, và vẫn nói thẳng
mình đứng ở đâu. Cái nó bỏ đi chỉ là lời hứa không có bằng chứng.

Ba điều kiện của `prospect.py` giữ nguyên, cộng một điều kiện thứ tư sinh ra từ
§7:

1. Điểm luôn in kèm **mọi thành phần**, mỗi thành phần có trần riêng và câu
   giải thích riêng.
2. Ghi file riêng, không đụng `xep_hang_moi_nhat.json`.
3. Phần **đo được** và phần **model chấm** không cộng ở tầng hiển thị.
4. **Mọi output mang theo kết luận hiệu chuẩn.** Không có file hiệu chuẩn thì
   điểm vẫn tính nhưng nhãn nói thẳng là chưa ai kiểm chứng.
"""
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.macro import calibrate as cal_mod
from src.macro import fundamentals as fund_mod
from src.macro import icb, rrg
from src.ta.loader import PROJECT_ROOT, load_prices, load_recent

REPORT_DIR = PROJECT_ROOT / "reports"
BENCHMARK = "VNINDEX"

#: Trần từng thành phần. Đây là **trọng số mô tả**, không phải sức dự báo —
#: §7 đã bác bỏ sức dự báo của cả hai trụ đo được. Chúng nói "thành phần nào
#: đáng chiếm chỗ nhiều hơn trong một câu tóm tắt", và con số đó là lựa chọn
#: biên tập, được ghi ra để cãi lại.
CAP_RELATIVE = 30      # mạnh/yếu hơn thị trường bao nhiêu, 20 và 60 phiên
CAP_ROTATION = 20      # vị trí và hướng đi trên vòng xoay RRG
CAP_BREADTH = 15       # bao nhiêu phần ngành đang tham gia
CAP_FLOW = 15          # dòng tiền chủ động + khối ngoại
CAP_FUNDAMENTAL = 20   # nền tảng: lợi nhuận, tăng trưởng, định giá
BASE_CAP = (CAP_RELATIVE + CAP_ROTATION + CAP_BREADTH + CAP_FLOW
            + CAP_FUNDAMENTAL)          # = 100

#: Thang phần tin, do model ngôn ngữ chấm. Không cộng vào ``base`` ở tầng hiển
#: thị — xem điều kiện (3).
NEWS_CAP = 25


@dataclass
class Component:
    """Một thành phần điểm: giá trị, trần, và **vì sao ra con số đó**."""
    key: str
    label: str
    points: float
    cap: float
    detail: str = ""
    measured: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _scale(value: float, lo: float, hi: float, cap: float) -> float:
    """Ánh xạ tuyến tính ``[lo, hi]`` → ``[0, cap]``, cắt ở hai đầu."""
    if hi == lo:
        return 0.0
    return round(_clamp((value - lo) / (hi - lo), 0.0, 1.0) * cap, 1)


# ---------------------------------------------------------------------------
def _rel_change(code: str, sessions: int,
                as_of: Optional[datetime] = None) -> Optional[float]:
    """% ngành − % VNINDEX qua ``sessions`` phiên."""
    days = max(sessions * 2 + 30, 120)
    sec = load_recent(icb.sector_symbol(code), days, as_of)
    ben = load_recent(BENCHMARK, days, as_of)
    if len(sec) <= sessions or len(ben) <= sessions:
        return None
    s = sec[-1].priceClose / sec[-1 - sessions].priceClose - 1
    b = ben[-1].priceClose / ben[-1 - sessions].priceClose - 1
    return (s - b) * 100


def component_relative(code: str, as_of: Optional[datetime] = None) -> Component:
    r20 = _rel_change(code, 20, as_of)
    r60 = _rel_change(code, 60, as_of)
    if r20 is None and r60 is None:
        return Component("relative", "Mạnh/yếu hơn thị trường", 0.0,
                         CAP_RELATIVE, "chưa đủ phiên để đo", measured=False)
    parts = [v for v in (r20, r60) if v is not None]
    blended = sum(parts) / len(parts)
    # −10…+10 điểm phần trăm phủ gần hết phân phối thật; ngoài dải thì cắt.
    pts = _scale(blended, -10.0, 10.0, CAP_RELATIVE)
    bits = []
    if r20 is not None:
        bits.append(f"20 phiên {r20:+.1f}đ%")
    if r60 is not None:
        bits.append(f"60 phiên {r60:+.1f}đ%")
    return Component("relative", "Mạnh/yếu hơn thị trường", pts, CAP_RELATIVE,
                     " · ".join(bits))


def component_rotation(code: str, as_of: Optional[datetime] = None,
                       view: Optional[rrg.RrgView] = None) -> Component:
    v = view or rrg.view(code, as_of=as_of)
    if v.rs is None:
        return Component("rotation", "Vòng xoay RRG", 0.0, CAP_ROTATION,
                         v.note or "chưa nạp RRG", measured=False)
    weight = {rrg.LEADING: 1.0, rrg.IMPROVING: 0.75,
              rrg.WEAKENING: 0.35, rrg.LAGGING: 0.0}
    pts = round(weight.get(v.quadrant, 0.0) * CAP_ROTATION, 1)
    detail = f"{v.label} ({rrg.QUADRANT_NOTE.get(v.quadrant, '')}), {v.sessions_in_quadrant} phiên"
    if v.disputed:
        detail += f" · ⚠️ bản tự tính đọc ra *{rrg.QUADRANT_VN[v.local_quadrant]}*"
    elif v.near_axis:
        detail += " · ⚠️ sát trục, nhãn có thể lật sau một phiên"
    return Component("rotation", "Vòng xoay RRG", pts, CAP_ROTATION, detail)


def component_breadth(code: str, as_of: Optional[datetime] = None,
                      members: Optional[Sequence[str]] = None) -> Component:
    """% thành viên ngành **có mặt trong ``data/``** đang trên EMA20.

    ⚠️ Mẫu số là rổ của ta, không phải cả ngành: Năng lượng có 33 mã niêm yết
    và ta có 4. Nên đây là *độ rộng của phần ngành ta quan sát được*, và nhãn
    phải nói ra điều đó. Ngành nào ta có dưới 3 mã thì **để trống** — trung vị
    của hai quan sát không phải độ rộng, đúng lập luận ``sector.MIN_PEERS``.
    """
    from src.macro import members as members_mod
    have = list(members or members_mod.in_basket(code))
    if len(have) < 3:
        return Component("breadth", "Độ rộng trong ngành", 0.0, CAP_BREADTH,
                         f"chỉ {len(have)} mã của ngành này có trong rổ — "
                         f"không đo được độ rộng", measured=False)
    above = 0
    counted = 0
    for sym in have:
        recs = load_recent(sym, 120, as_of)
        if len(recs) < 21:
            continue
        ema = recs[-1].priceClose
        window = [r.priceClose for r in recs[-20:]]
        counted += 1
        if ema > sum(window) / len(window):
            above += 1
    if not counted:
        return Component("breadth", "Độ rộng trong ngành", 0.0, CAP_BREADTH,
                         "không mã nào đủ phiên", measured=False)
    pct = above / counted
    return Component("breadth", "Độ rộng trong ngành",
                     round(pct * CAP_BREADTH, 1), CAP_BREADTH,
                     f"{above}/{counted} mã trong rổ trên trung bình 20 phiên "
                     f"({pct:.0%})")


def component_flow(code: str, as_of: Optional[datetime] = None) -> Component:
    """Dòng tiền chủ động + khối ngoại, so với chính ngành 250 phiên gần nhất."""
    recs = load_recent(icb.sector_symbol(code), 420, as_of)
    if len(recs) < 60:
        return Component("flow", "Dòng tiền", 0.0, CAP_FLOW,
                         "chưa đủ phiên", measured=False)
    window = recs[-250:]
    net_foreign = [r.buyForeignValue - r.sellForeignValue for r in window]
    recent = sum(net_foreign[-5:])
    below = sum(1 for v in net_foreign if v < recent)
    pct = below / len(net_foreign)
    sign = "mua ròng" if recent > 0 else "bán ròng"
    return Component("flow", "Dòng tiền khối ngoại",
                     round(pct * CAP_FLOW, 1), CAP_FLOW,
                     f"5 phiên {sign} {abs(recent)/1e9:,.0f} tỷ — phân vị "
                     f"{pct:.0%} của 250 phiên")


def component_fundamental(code: str,
                          as_of: Optional[datetime] = None) -> Component:
    """Nền tảng: dấu xu hướng ROE + biên, và định giá so với **chính ngành**.

    ⚠️ §7/H2 đã bác bỏ sức dự báo của xu hướng ROE. Thành phần này ở lại vì nó
    **mô tả** một thứ có thật và kiểm chứng được — biên đang giãn hay co — chứ
    không phải vì nó dự báo được gì. Trần 20 là trọng số biên tập.
    """
    f = fund_mod.build(code, as_of)
    if not f.measured:
        return Component("fundamental", "Nền tảng", 0.0, CAP_FUNDAMENTAL,
                         f.note, measured=False)
    pts = 0.0
    bits = []
    for name, weight in (("ROE", 5.0), ("GrossMargin", 4.0), ("EBITMargin", 3.0)):
        m = f.find(name)
        if m and m.improving is not None:
            gain = weight if m.improving else 0.0
            pts += gain
            bits.append(f"{m.label} {'↑' if m.improving else '↓'}")
    growth = f.find("ProfitGrowth_TTM")
    if growth and growth.latest is not None:
        gain = _scale(growth.latest, -0.3, 0.5, 4.0)
        pts += gain
        bits.append(f"LN TTM {growth.latest*100:+.0f}%")
    pe = f.find("PE")
    if pe and pe.percentile is not None:
        gain = round((1 - pe.percentile) * 4.0, 1)     # rẻ so với lịch sử = điểm
        pts += gain
        bits.append(f"P/E ở phân vị {pe.percentile:.0%} lịch sử ngành")
    return Component("fundamental", "Nền tảng", round(min(pts, CAP_FUNDAMENTAL), 1),
                     CAP_FUNDAMENTAL,
                     f"{f.latest_quarter} · " + (" · ".join(bits) or "chưa đo được"))


# ---------------------------------------------------------------------------
@dataclass
class SectorScore:
    code: str
    name: str = ""
    level: int = 1
    as_of: str = ""
    components: List[Component] = field(default_factory=list)
    news_score: Optional[float] = None
    news_label: str = ""
    news_source: str = ""

    @property
    def base(self) -> float:
        return round(sum(c.points for c in self.components), 1)

    @property
    def measured_caps(self) -> float:
        return sum(c.cap for c in self.components if c.measured)

    @property
    def gaps(self) -> List[str]:
        return [c.label for c in self.components if not c.measured]

    @property
    def total(self) -> Optional[float]:
        """``base`` + phần tin. **Không bao giờ in một mình** — xem điều kiện (3)."""
        if self.news_score is None:
            return None
        return round(self.base + self.news_score, 1)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code, "name": self.name, "level": self.level,
            "as_of": self.as_of,
            "components": [c.to_dict() for c in self.components],
            "base": self.base, "measured_caps": self.measured_caps,
            "gaps": self.gaps,
            "news_score": self.news_score, "news_label": self.news_label,
            "news_source": self.news_source, "total": self.total,
        }


def score_sector(code: str, name: str = "", level: int = 1,
                 as_of: Optional[datetime] = None) -> SectorScore:
    day = as_of or datetime.now()
    out = SectorScore(code=str(code), name=name, level=level,
                      as_of=day.strftime("%Y-%m-%d"))
    out.components = [
        component_relative(code, as_of),
        component_rotation(code, as_of),
        component_breadth(code, as_of),
        component_flow(code, as_of),
        component_fundamental(code, as_of),
    ]
    return out


@dataclass
class Board:
    """Bảng ngành — luôn mang theo kết luận hiệu chuẩn, xem điều kiện (4)."""
    generated: str
    as_of: str
    rows: List[SectorScore] = field(default_factory=list)
    calibration: str = ""
    predictive: bool = False
    json_path: str = ""
    html_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"generated": self.generated, "as_of": self.as_of,
                "rows": [r.to_dict() for r in self.rows],
                "calibration": self.calibration, "predictive": self.predictive,
                "json_path": self.json_path, "html_path": self.html_path}


#: Câu phải đi kèm mọi bảng khi hiệu chuẩn không qua. Một chỗ, không rải rác.
NOT_PREDICTIVE = (
    "Bảng này **mô tả hiện trạng**, không dự báo. Hiệu chuẩn (§7) đã chạy và "
    "**không** chứng minh được sức dự báo của bất kỳ trụ nào: góc RRG không "
    "tách khỏi nền sau khi hiệu chỉnh cho 12 phép kiểm, và xu hướng ROE ngành "
    "không tách khỏi nền ở bất kỳ nhóm nào. Đọc thứ tự ở đây như *ngành nào "
    "đang mạnh*, không phải *ngành nào sẽ mạnh*."
)

NO_CALIBRATION = (
    "⚠️ **Chưa chạy hiệu chuẩn.** Chạy `python -m src.macro.calibrate` trước "
    "khi tin bất kỳ con số nào ở đây. Chưa kiểm chứng khác với đã kiểm chứng "
    "và thấy yếu."
)


def calibration_note() -> Tuple[str, bool]:
    cal = cal_mod.load()
    if cal is None:
        return NO_CALIBRATION, False
    any_passed = any(h.passed for h in cal.hypotheses)
    if not any_passed:
        return NOT_PREDICTIVE, False
    lines = [f"Hiệu chuẩn {cal.generated}: "
             + ", ".join(f"{h.name} {'đạt' if h.passed else 'không đạt'}"
                         for h in cal.hypotheses)]
    return " ".join(lines), True


def build(codes: Optional[Sequence[str]] = None,
          as_of: Optional[datetime] = None,
          verdicts: Optional[Dict[str, Any]] = None) -> Board:
    tree = icb.fetch_tree()
    names = {i.code: i.name for i in tree}
    levels = {i.code: i.level for i in tree}
    codes = list(codes or icb.distinct_codes(tree))
    day = as_of or datetime.now()

    note, predictive = calibration_note()
    board = Board(generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
                  as_of=day.strftime("%Y-%m-%d"),
                  calibration=note, predictive=predictive)
    for code in codes:
        row = score_sector(code, names.get(code, ""), levels.get(code, 1), day)
        v = (verdicts or {}).get(code)
        if v:
            row.news_score = v.get("score")
            row.news_label = v.get("label", "")
            row.news_source = v.get("source", "")
        board.rows.append(row)
    board.rows.sort(key=lambda r: r.base, reverse=True)
    return board


# ---------------------------------------------------------------------------
def board_path(as_of: Optional[datetime] = None) -> Path:
    from src.ta import asof as asof_mod
    root = asof_mod.out_root(REPORT_DIR, as_of, None)
    tag = asof_mod.file_tag(as_of)
    return root / f"bang_nganh_{tag}.json"


def save(board: Board, as_of: Optional[datetime] = None) -> str:
    path = board_path(as_of)
    path.parent.mkdir(parents=True, exist_ok=True)
    board.json_path = str(path)
    path.write_text(json.dumps(board.to_dict(), ensure_ascii=False, indent=1),
                    encoding="utf-8")
    return str(path)


def load_board(path: Optional[Path] = None,
               as_of: Optional[datetime] = None) -> Optional[Board]:
    src = Path(path) if path else board_path(as_of)
    if not src.is_file():
        return None
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    board = Board(generated=data.get("generated", ""),
                  as_of=data.get("as_of", ""),
                  calibration=data.get("calibration", ""),
                  predictive=bool(data.get("predictive")),
                  json_path=data.get("json_path", ""),
                  html_path=data.get("html_path", ""))
    for r in data.get("rows") or []:
        row = SectorScore(code=r["code"], name=r.get("name", ""),
                          level=int(r.get("level") or 1),
                          as_of=r.get("as_of", ""),
                          news_score=r.get("news_score"),
                          news_label=r.get("news_label", ""),
                          news_source=r.get("news_source", ""))
        row.components = [Component(**c) for c in r.get("components") or []]
        board.rows.append(row)
    return board
