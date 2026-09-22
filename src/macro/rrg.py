"""RRG — ngành đang ở góc nào của vòng xoay, và đang đi về đâu.

`/icb/{mã}/rrg` trả `{date, rs, rm}` theo phiên: **JdK RS-Ratio** và **JdK
RS-Momentum**, chuẩn công nghiệp cho phân tích xoay vòng ngành. Hai trục cắt
nhau tại 100 chia bốn góc phần tư, và ngành thường đi **thuận chiều kim đồng
hồ**: `improving` → `leading` → `weakening` → `lagging` → `improving`.

Vì sao nó đáng giá hơn một cột "% thay đổi 20 phiên": `rm` là **tốc độ biến
thiên của `rs`**, nên theo đúng cấu tạo nó xoay *trước*. Một ngành ở góc
`improving` còn yếu hơn thị trường nhưng đang thu hẹp khoảng cách — khác hẳn
một ngành `weakening` đang mạnh nhưng hết đà. Đây là thành phần duy nhất trong
trụ A có tính dẫn; phần còn lại đều mô tả hiện trạng.

⚠️ **Bản tự tính là bắt buộc, không phải tuỳ chọn.** FireAnt không công bố cửa
sổ chuẩn hoá. Một con số không tái lập được thì không kiểm chứng được, và cả
tầng này đứng trên nó. Nên `recompute()` dựng lại từ `historical-index` +
VNINDEX, `compare()` đo độ lệch, và con số đó được in ra chứ không giấu đi.
"""
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from statistics import fmean, pstdev
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.macro.icb import sector_symbol
from src.news.fireant import get
from src.ta.loader import PROJECT_ROOT, load_prices

#: Nơi cất chuỗi RRG. Không để trong ``data/`` vì ``data/`` chỉ chứa schema giá —
#: một file lạ ở đó là một file không ai biết ``loader`` có đọc hay không.
RRG_DIR = PROJECT_ROOT / "macro" / "rrg"

#: Mốc chia bốn góc. 100 là "đi ngang cùng thị trường", theo đúng định nghĩa JdK.
CENTER = 100.0

LEADING = "dan_dat"
IMPROVING = "cai_thien"
WEAKENING = "suy_yeu"
LAGGING = "tut_lai"

QUADRANT_VN = {
    LEADING: "dẫn dắt",
    IMPROVING: "đang cải thiện",
    WEAKENING: "đang suy yếu",
    LAGGING: "tụt lại",
}

#: Câu giải thích đi kèm — mỗi góc nói một trạng thái khác nhau, và cái khác
#: nhau đó mới là thứ đáng đọc.
QUADRANT_NOTE = {
    LEADING: "mạnh hơn thị trường và còn đang mạnh thêm",
    IMPROVING: "vẫn yếu hơn thị trường nhưng đang thu hẹp khoảng cách",
    WEAKENING: "còn mạnh hơn thị trường nhưng đà đang mất",
    LAGGING: "yếu hơn thị trường và còn đang yếu thêm",
}

#: Thứ tự thuận chiều kim đồng hồ — dùng để nói "đang đi về góc nào".
CLOCKWISE = [IMPROVING, LEADING, WEAKENING, LAGGING]

#: Cửa sổ của bản tự tính — **dò ra bằng đo**, không phải chọn theo cảm tính.
#:
#: JdK không công bố tham số và FireAnt không nói họ dùng cửa sổ nào, nên cách
#: duy nhất là quét tham số rồi xem bộ nào tái lập được output của họ. Kết quả
#: trên ngành `60`, 2635 phiên chung: **85,1% cùng góc phần tư**.
#:
#: Quan trọng hơn con số đó: bộ tham số này được **kiểm chéo trên bảy ngành
#: khác** không tham gia dò (`30`, `50`, `45`, `3010`, `5510`, `35`, `10`) và
#: giữ được **80,4% trung bình**. Chênh 85→80 là mức tụt nhỏ, nên bộ này mô tả
#: cách FireAnt tính chứ không phải khớp đè lên một ngành.
SHORT_WINDOW = 12
LONG_WINDOW = 26
#: Cửa sổ chuẩn hoá về quanh 100. Dài (750 phiên ≈ 3 năm) vì RS-Ratio của JdK
#: so với **lịch sử dài** của chính nó, không với vài tháng gần đây.
NORM_WINDOW = 750
#: Số phiên dùng để tính đà của RS-Ratio.
MOMENTUM_WINDOW = 5
#: Hệ số giãn của z-score. FireAnt trả giá trị bám sát 98–102, nên một độ lệch
#: chuẩn ≈ 1 điểm chỉ số là thang khớp nhất.
NORM_SCALE = 1.0

#: Dưới mức khớp này thì bản API và bản tự tính coi như nói hai chuyện khác
#: nhau, và báo cáo phải nói ra thay vì chọn im lặng một bên.
MIN_AGREEMENT = 0.70

DEFAULT_BENCHMARK = "VNINDEX"


@dataclass
class RrgPoint:
    date: str
    rs: float
    rm: float

    @property
    def quadrant(self) -> str:
        return classify(self.rs, self.rm)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def classify(rs: float, rm: float) -> str:
    """Góc phần tư. Đúng định nghĩa JdK, không có vùng đệm.

    Không đặt vùng đệm quanh 100 là có chủ ý: một ngành nằm sát trục thì
    ``distance()`` đã nói nó sát trục rồi. Thêm một nhãn "trung lập" thứ năm là
    che mất chính thông tin đó — người đọc sẽ tưởng có bốn góc rõ ràng cộng một
    vùng lặng, thay vì thấy nó *đang đi qua* trục.
    """
    if rs >= CENTER:
        return LEADING if rm >= CENTER else WEAKENING
    return IMPROVING if rm >= CENTER else LAGGING


def distance(rs: float, rm: float) -> float:
    """Khoảng cách tới **trục gần nhất** — không phải tới tâm.

    Cái quyết định nhãn góc có lật hay không là trục nào ở gần: `rs = 100,33`
    thì chỉ cần nhích 0,34 là ngành rơi từ *suy yếu* xuống *tụt lại*, bất kể
    `rm` đang ở đâu. Đo khoảng cách tới tâm sẽ gọi một điểm như vậy là "xa tâm,
    nhãn chắc" — đúng ngược với sự thật.
    """
    return min(abs(rs - CENTER), abs(rm - CENTER))


# ---------------------------------------------------------------------------
# Nạp từ API
# ---------------------------------------------------------------------------
def fetch(code: str, start: str = "2010-01-01",
          end: Optional[str] = None) -> List[RrgPoint]:
    """Chuỗi RRG của một ngành, sắp theo ngày tăng dần.

    Đã kiểm: giá trị **không** đổi theo khoảng ngày xin — FireAnt tính trên cả
    chuỗi rồi cắt. Nên nạp một lần từ 2010 là đủ, không phải lo cửa sổ.
    """
    end = end or datetime.now().strftime("%Y-%m-%d")
    rows = get(f"/icb/{code}/rrg", {"startDate": start, "endDate": end}) or []
    out: List[RrgPoint] = []
    for row in rows:
        day = str(row.get("date") or "")[:10]
        rs, rm = row.get("rs"), row.get("rm")
        if not day or rs is None or rm is None:
            continue
        out.append(RrgPoint(date=day, rs=float(rs), rm=float(rm)))
    out.sort(key=lambda p: p.date)
    return out


def path_for(code: str, root: Optional[Path] = None) -> Path:
    return (root or RRG_DIR) / f"{code}.json"


def save(code: str, points: Sequence[RrgPoint],
         root: Optional[Path] = None) -> Path:
    out = path_for(code, root)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps([p.to_dict() for p in points],
                              ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def load(code: str, as_of: Optional[datetime] = None,
         root: Optional[Path] = None) -> List[RrgPoint]:
    """Đọc lại chuỗi đã nạp, cắt tại ``as_of``.

    Cắt ở đây chứ không ở tầng gọi: RRG là chuỗi đã tính sẵn nên rất dễ bị đọc
    quá mốc mà không ai để ý — một điểm RRG của ngày mai nói về giá của ngày mai.
    """
    src = path_for(code, root)
    if not src.is_file():
        return []
    try:
        rows = json.loads(src.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    points = [RrgPoint(**r) for r in rows]
    if as_of is not None:
        limit = as_of.strftime("%Y-%m-%d")
        points = [p for p in points if p.date <= limit]
    return points


# ---------------------------------------------------------------------------
# Bản tự tính
# ---------------------------------------------------------------------------
def _sma(values: Sequence[float], window: int) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    run = 0.0
    for i, v in enumerate(values):
        run += v
        if i >= window:
            run -= values[i - window]
        out.append(run / window if i >= window - 1 else None)
    return out


def _normalise(values: Sequence[Optional[float]], window: int,
               scale: float) -> List[Optional[float]]:
    """Z-score trượt, dời về quanh ``CENTER``.

    Dùng ``pstdev`` chứ không ``stdev``: đây là cả cửa sổ, không phải mẫu rút ra
    từ nó. Cửa sổ phẳng (độ lệch 0) trả đúng ``CENTER`` — không chia cho 0.
    """
    out: List[Optional[float]] = []
    buf: List[float] = []
    for v in values:
        if v is None:
            out.append(None)
            continue
        buf.append(v)
        if len(buf) > window:
            buf.pop(0)
        if len(buf) < window:
            out.append(None)
            continue
        sd = pstdev(buf)
        out.append(CENTER if sd == 0 else CENTER + scale * (v - fmean(buf)) / sd)
    return out


def recompute(code: str, benchmark: str = DEFAULT_BENCHMARK,
              short: int = SHORT_WINDOW, long: int = LONG_WINDOW,
              norm: int = NORM_WINDOW, momentum: int = MOMENTUM_WINDOW,
              as_of: Optional[datetime] = None) -> List[RrgPoint]:
    """Dựng lại RS-Ratio / RS-Momentum từ chuỗi giá — bản tái lập được.

    Công thức, viết ra để cãi được:

        rs       = 100 × giá_ngành / giá_benchmark
        thô      = 100 × (SMA(rs, 12) − SMA(rs, 26)) / SMA(rs, 26) + 100
        RS-Ratio = chuẩn hoá(thô, cửa sổ 750) quanh 100
        đà       = 100 × RS-Ratio / RS-Ratio lùi 5 phiên
        RS-Mom   = chuẩn hoá(đà, cửa sổ 750) quanh 100

    Lượt đầu dùng hiệu **một phiên** cho đà và chỉ khớp FireAnt 50,6% — đúng
    bằng tung đồng xu. Hiệu một phiên của một chuỗi đã chuẩn hoá gần như thuần
    nhiễu; tỷ lệ qua 5 phiên mới ra thứ FireAnt đang vẽ.

    Chỉ giữ các phiên **có mặt ở cả hai chuỗi**. Ghép theo chỉ số mảng thay vì
    theo ngày là cách chắc chắn nhất để lệch pha một phiên mà không ai thấy —
    ngành và VNINDEX không luôn có đúng cùng tập phiên.
    """
    end = as_of or datetime.now()
    start = datetime(2010, 1, 1)
    sec = load_prices(sector_symbol(code), start, end)
    ben = load_prices(benchmark, start, end)
    if not sec or not ben:
        return []
    ben_by_day = {r.date.strftime("%Y-%m-%d"): r.priceClose for r in ben}

    days: List[str] = []
    ratio: List[float] = []
    for rec in sec:
        day = rec.date.strftime("%Y-%m-%d")
        base = ben_by_day.get(day)
        if not base or rec.priceClose <= 0:
            continue
        days.append(day)
        ratio.append(100.0 * rec.priceClose / base)

    if len(ratio) < long + norm:
        return []

    s_short = _sma(ratio, short)
    s_long = _sma(ratio, long)
    raw: List[Optional[float]] = []
    for a, b in zip(s_short, s_long):
        raw.append(None if a is None or b is None or b == 0
                   else 100.0 * (a - b) / b + CENTER)

    rs_series = _normalise(raw, norm, NORM_SCALE)
    mom_raw: List[Optional[float]] = [None] * momentum
    for i in range(momentum, len(rs_series)):
        prev, cur = rs_series[i - momentum], rs_series[i]
        mom_raw.append(None if prev is None or cur is None or prev == 0
                       else 100.0 * cur / prev)
    rm_series = _normalise(mom_raw, norm, NORM_SCALE)

    return [RrgPoint(date=d, rs=round(rs, 2), rm=round(rm, 2))
            for d, rs, rm in zip(days, rs_series, rm_series)
            if rs is not None and rm is not None]


@dataclass
class Agreement:
    """Bản API và bản tự tính khớp nhau tới đâu — con số phải in ra, không giấu."""
    code: str
    overlap: int = 0
    same_quadrant: int = 0
    rs_corr: Optional[float] = None
    rm_corr: Optional[float] = None

    @property
    def quadrant_rate(self) -> Optional[float]:
        return self.same_quadrant / self.overlap if self.overlap else None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["quadrant_rate"] = self.quadrant_rate
        return d


def _corr(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    if len(xs) < 3:
        return None
    mx, my = fmean(xs), fmean(ys)
    sx, sy = pstdev(xs), pstdev(ys)
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (len(xs) * sx * sy)


def compare(code: str, api: Sequence[RrgPoint],
            local: Sequence[RrgPoint]) -> Agreement:
    """Đo độ khớp trên các phiên có ở **cả hai** bản.

    Cái đáng đo là **tỷ lệ cùng góc phần tư**, không phải sai số tuyệt đối: cả
    tầng trên chỉ dùng nhãn góc, nên hai bản lệch 0,4 điểm mà cùng góc thì không
    có hậu quả gì, còn lệch 0,05 điểm ngay sát trục thì đổi hẳn kết luận.
    """
    a = {p.date: p for p in api}
    b = {p.date: p for p in local}
    both = sorted(set(a) & set(b))
    out = Agreement(code=code, overlap=len(both))
    if not both:
        return out
    out.same_quadrant = sum(1 for d in both
                            if a[d].quadrant == b[d].quadrant)
    out.rs_corr = _corr([a[d].rs for d in both], [b[d].rs for d in both])
    out.rm_corr = _corr([a[d].rm for d in both], [b[d].rm for d in both])
    return out


# ---------------------------------------------------------------------------
# Đọc trạng thái
# ---------------------------------------------------------------------------
@dataclass
class RrgView:
    """Ngành này đang ở đâu trên vòng xoay, và đi được bao lâu rồi."""
    code: str
    date: str = ""
    rs: Optional[float] = None
    rm: Optional[float] = None
    quadrant: str = ""
    sessions_in_quadrant: int = 0
    prev_quadrant: str = ""
    rs_delta_5: Optional[float] = None     # đổi bao nhiêu sau 5 phiên
    rm_delta_5: Optional[float] = None
    distance: Optional[float] = None
    #: Góc mà **bản tự tính** cho ra ở cùng phiên. Rỗng = chưa đối chiếu được.
    local_quadrant: str = ""
    note: str = ""

    @property
    def label(self) -> str:
        return QUADRANT_VN.get(self.quadrant, "chưa đo được")

    @property
    def near_axis(self) -> bool:
        """Sát trục thì nhãn góc mong manh — phải nói ra thay vì tuyên bố chắc."""
        return self.distance is not None and self.distance < 0.35

    @property
    def disputed(self) -> bool:
        """Hai bản nói hai góc khác nhau **ở chính phiên này**.

        Tỷ lệ khớp tổng thể 80% là một thống kê; nó không nói phiên hôm nay có
        nằm trong 20% kia hay không. Cờ này nói. Đặt nó ở mức từng phiên là để
        người đọc gặp bất đồng đúng lúc nó ảnh hưởng tới kết luận, thay vì đọc
        một con số trung bình ở cuối tài liệu rồi quên.
        """
        return bool(self.local_quadrant) and self.local_quadrant != self.quadrant

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["label"] = self.label
        d["near_axis"] = self.near_axis
        d["disputed"] = self.disputed
        return d


def view(code: str, points: Optional[Sequence[RrgPoint]] = None,
         as_of: Optional[datetime] = None,
         local: Optional[Sequence[RrgPoint]] = None) -> RrgView:
    pts = list(points) if points is not None else load(code, as_of=as_of)
    out = RrgView(code=code)
    if not pts:
        out.note = "chưa nạp RRG — chạy `python -m src.macro.rrg`"
        return out
    last = pts[-1]
    out.date, out.rs, out.rm = last.date, last.rs, last.rm
    out.quadrant = last.quadrant
    out.distance = round(distance(last.rs, last.rm), 3)

    run = 0
    for p in reversed(pts):
        if p.quadrant != out.quadrant:
            out.prev_quadrant = p.quadrant
            break
        run += 1
    out.sessions_in_quadrant = run

    if len(pts) > 5:
        out.rs_delta_5 = round(last.rs - pts[-6].rs, 2)
        out.rm_delta_5 = round(last.rm - pts[-6].rm, 2)

    if local:
        for p in reversed(local):
            if p.date == last.date:
                out.local_quadrant = p.quadrant
                break
    if out.disputed:
        out.note = (f"bản tự tính đọc ra *{QUADRANT_VN[out.local_quadrant]}* — "
                    f"hai cách tính không đồng ý ở phiên này")
    elif out.near_axis:
        out.note = "nằm sát trục, nhãn góc có thể đổi chỉ sau một phiên"
    return out


def update(codes: Sequence[str], start: str = "2010-01-01",
           end: Optional[str] = None, verify: bool = True,
           root: Optional[Path] = None) -> List[Tuple[str, int, Optional[Agreement]]]:
    """Nạp RRG cho danh sách ngành, ghi đĩa, và đối chiếu với bản tự tính."""
    out = []
    for code in codes:
        try:
            pts = fetch(code, start, end)
        except Exception as exc:                          # noqa: BLE001
            out.append((code, 0, None))
            continue
        if pts:
            save(code, pts, root)
        agree = compare(code, pts, recompute(code)) if verify and pts else None
        out.append((code, len(pts), agree))
    return out


def view_verified(code: str, as_of: Optional[datetime] = None) -> RrgView:
    """``view()`` kèm bản tự tính — dùng ở mọi chỗ ra quyết định.

    Tách khỏi ``view()`` vì bản tự tính tốn một lượt nạp giá; chỗ nào chỉ cần
    nhãn góc để hiển thị thì dùng ``view()``, chỗ nào **kết luận** dựa vào nhãn
    đó thì phải trả cái giá này.
    """
    return view(code, as_of=as_of, local=recompute(code, as_of=as_of))


def _main() -> None:
    import argparse
    from src.macro import icb

    ap = argparse.ArgumentParser(description="Nạp RRG ngành và đối chiếu bản tự tính")
    ap.add_argument("--codes", default="")
    ap.add_argument("--no-verify", action="store_true")
    args = ap.parse_args()

    tree = icb.fetch_tree()
    codes = ([c for c in args.codes.split(",") if c.strip()]
             or icb.distinct_codes(tree))
    names = {i.code: i.name for i in tree}

    rows = update(codes, verify=not args.no_verify)
    print("| Mã | Ngành | Điểm | Góc hiện tại | Phiên trong góc | Khớp bản tự tính |")
    print("|---|---|---:|---|---:|---|")
    for code, n, agree in rows:
        v = view(code)
        rate = ("—" if agree is None or agree.quadrant_rate is None
                else f"{agree.quadrant_rate:.0%} ({agree.overlap} phiên)")
        print(f"| `{code}` | {names.get(code, '')} | {n} | {v.label} | "
              f"{v.sessions_in_quadrant} | {rate} |")


if __name__ == "__main__":
    _main()
