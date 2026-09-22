"""Đo phản ứng giá quanh một sự kiện — event study. GĐ5 của kế hoạch.

Đây là phần trả lời câu hỏi mà cả tầng tin tức tồn tại vì nó: **tin đó đã vào
giá chưa.** Và nó trả lời bằng cách *đo*, không phải bằng cách đoán.

Cách làm chuẩn: ước lượng quan hệ giữa mã và thị trường trên một cửa sổ *trước*
sự kiện, rồi xem những phiên quanh sự kiện lệch khỏi quan hệ đó bao nhiêu. Phần
lệch đó là ``abnormal return`` — cái còn lại sau khi đã trừ đi phần "cả thị
trường cùng lên".

Ba chi tiết quyết định kết quả đúng hay sai:

* **Cửa sổ ước lượng bỏ 10 phiên sát sự kiện.** Tin hay rò rỉ trước khi công bố;
  nếu để 10 phiên đó vào phần ước lượng thì chính đoạn rò rỉ trở thành "bình
  thường", và phản ứng đo được nhỏ đi một cách hệ thống.
* **Ba cửa sổ tách rời, không gộp.** ``CAR[-5..-1]`` là *rò rỉ trước tin*,
  ``AR[t0..t+1]`` là *phản ứng tức thì*, ``CAR[+1..+10]`` là *trôi sau tin*. Gộp
  lại thành một số là xoá đúng thứ đáng đọc: một mã chạy hết trước ngày công bố
  rồi đi ngang trông y hệt một mã không phản ứng gì.
* **Phiên trần/sàn làm phép đo bị cắt cụt.** Biên độ thật lớn hơn con số đo
  được, nên ``limit_hit`` phải được gắn cờ và mọi thống kê tổng hợp phải xử lý
  riêng — nếu không sẽ **đánh giá thấp một cách hệ thống** đúng những sự kiện
  mạnh nhất.

Module này cố ý *không* kết luận nhân quả. Nó trả về các con số và để người đọc
(hoặc tầng trên) nói câu "đã priced-in" hay "thị trường chưa tin".
"""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

from src.data.stock_data_loader import StockRecord
from src.ta import candles
from src.ta.loader import load_prices

#: Benchmark mặc định. VNINDEX **không phải một mã** — nó là thị trường chung,
#: và ở đây nó đóng đúng vai đó: mẫu số để biết mã mạnh hay yếu hơn thị trường.
DEFAULT_BENCHMARK = "VNINDEX"

#: Cửa sổ ước lượng: t-130 … t-11. Bỏ 10 phiên sát sự kiện để tránh nhiễm rò rỉ.
EST_START, EST_END = -130, -11
#: Cửa sổ sự kiện.
EVT_START, EVT_END = -5, 10
#: Số phiên tối thiểu để ước lượng có nghĩa. Dưới ngưỡng này thì trả None thay
#: vì trả một con số beta dựng từ 12 điểm.
MIN_EST_BARS = 60
#: Cửa sổ tính volume nền.
VOL_WINDOW = 20

#: Ngưỡng nhận phiên trần/sàn cho **event study** — cố ý chặt hơn
#: ``candles.BAND_PCT`` (0.06).
#:
#: ``candles`` dùng 6% vì mục đích của nó là *phân loại hình nến*: ở đó nhận nhầm
#: một phiên +6,5% đóng ở đỉnh thành "trần" chỉ làm mất một mẫu hình. Ở đây cái
#: giá phải trả ngược hẳn: phiên bị gắn cờ sẽ bị **loại khỏi thống kê**, mà
#: những phiên +6…7% đóng ở đỉnh chính là *phản ứng mạnh thật* — loại chúng đi là
#: tự cắt mất đúng phần đuôi mình đang muốn đo, và làm phân phối còn lại nghiêng
#: về phía yếu.
#:
#: Đo trên HPG (1661 phiên): ngưỡng 6% gắn cờ 39 phiên, chỉ 26 phiên thật sự
#: chạm biên — **33% là dương tính giả**. Ngưỡng 6,8% nằm ngay dưới biên HOSE (7%)
#: nên vẫn bắt trọn trần/sàn HOSE, đồng thời bắt cả HNX (10%) và UPCOM (15%) vì
#: các biên đó đều lớn hơn.
#:
#: Hạn chế còn lại: mã HNX/UPCOM chạy 7–9% đóng ở đỉnh vẫn bị gắn nhầm. Sửa hẳn
#: thì phải biết sàn của từng mã (`/symbols/{s}/profile` có `exchange`) — việc
#: cho lần sau.
LIMIT_BAND = 0.068


@dataclass
class Reaction:
    """Phản ứng đo được quanh một sự kiện. Toàn số, không có phán quyết."""
    symbol: str
    t0_requested: str
    t0_actual: Optional[str]          # phiên thật gần nhất — lệch khi t0 rơi vào ngày nghỉ
    benchmark: str
    n_est_bars: int

    alpha: Optional[float] = None
    beta: Optional[float] = None

    ar: Dict[str, float] = field(default_factory=dict)   # {"t-1": .., "t+0": ..}
    car_pre: Optional[float] = None      # CAR[-5..-1]  — rò rỉ trước tin
    car_immediate: Optional[float] = None  # AR[t0] + AR[t+1] — phản ứng tức thì
    car_post: Optional[float] = None     # CAR[+1..+10] — trôi sau tin

    ret_raw: Optional[float] = None      # lợi suất thô t0..t+10, chưa trừ thị trường
    ret_benchmark: Optional[float] = None
    volume_z: Optional[float] = None
    volume_ratio: Optional[float] = None  # volume t0 / trung bình 20 phiên
    limit_hit: bool = False
    limit_states: List[str] = field(default_factory=list)

    incomplete: bool = False             # thiếu phiên sau t0 (sự kiện quá mới)
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# --- Trợ giúp ------------------------------------------------------------

def _returns(records: Sequence[StockRecord]) -> List[float]:
    out = []
    for prev, cur in zip(records, records[1:]):
        if prev.priceClose:
            out.append(cur.priceClose / prev.priceClose - 1.0)
        else:
            out.append(0.0)
    return out


def _ols(y: Sequence[float], x: Sequence[float]) -> Tuple[float, float]:
    """alpha, beta bằng bình phương nhỏ nhất. Thuần Python, khớp phong cách repo."""
    n = len(y)
    if n == 0:
        return 0.0, 0.0
    mx = sum(x) / n
    my = sum(y) / n
    sxx = sum((xi - mx) ** 2 for xi in x)
    if sxx == 0:
        return my, 0.0
    sxy = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    beta = sxy / sxx
    return my - beta * mx, beta


def _index_of_session(records: Sequence[StockRecord], target: datetime) -> Optional[int]:
    """Vị trí phiên **tại hoặc trước** ``target``.

    Sự kiện rơi vào thứ Bảy hay ngày lễ thì phiên tác động là phiên gần nhất
    trước đó — cùng nguyên tắc với chế độ hồi tưởng của ``ta/asof.py``.
    """
    hit = None
    for i, r in enumerate(records):
        if r.date <= target:
            hit = i
        else:
            break
    return hit


def _parse_date(value: str) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:len(fmt) + 2].rstrip("Z"), fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "").split("+")[0])
    except ValueError:
        return None


def _align(sym_recs: Sequence[StockRecord],
           bench_recs: Sequence[StockRecord]) -> Tuple[List[StockRecord], List[StockRecord]]:
    """Giữ đúng những phiên cả hai bên cùng có.

    Mã nghỉ giao dịch một phiên mà thị trường vẫn chạy (hoặc ngược lại) thì hai
    chuỗi lệch nhau, và mọi phép trừ sau đó so nhầm ngày.
    """
    by_date = {r.date: r for r in bench_recs}
    s_out, b_out = [], []
    for r in sym_recs:
        b = by_date.get(r.date)
        if b is not None:
            s_out.append(r)
            b_out.append(b)
    return s_out, b_out


# --- Phép đo chính --------------------------------------------------------

def measure(symbol: str, t0: str, benchmark: str = DEFAULT_BENCHMARK,
            band_pct: float = LIMIT_BAND,
            as_of: Optional[datetime] = None) -> Reaction:
    """Đo phản ứng quanh ``t0``.

    ``t0`` là ngày sự kiện dạng ISO hoặc dd/mm/yyyy. Phiên thật dùng làm mốc là
    phiên tại hoặc trước ``t0``; hai ngày này lệch nhau mỗi khi sự kiện rơi vào
    ngày nghỉ, nên cả hai đều được trả về.

    ``as_of`` cắt **phần đuôi** của chuỗi giá. Không có nó thì cửa sổ sau sự kiện
    luôn chạy tới ``t0 + 40 ngày`` bất kể mốc hồi tưởng, nên một báo cáo đứng ở
    01/01/2025 vẫn đọc được giá tháng 2/2025 để kết luận "tin đã vào giá" — đúng
    kiểu nhìn trước mà ``as_of`` sinh ra để chặn. Cắt ở đây thay vì ở tầng gọi
    vì ``incomplete`` phải phản ánh *thiếu phiên tại thời điểm đó*, không phải
    thiếu phiên hôm nay.
    """
    target = _parse_date(t0)
    if target is None:
        return Reaction(symbol=symbol, t0_requested=t0, t0_actual=None,
                        benchmark=benchmark, n_est_bars=0,
                        note="không đọc được ngày sự kiện")

    # Nạp rộng hơn cửa sổ cần dùng: 130 phiên ~ 190 ngày lịch, cộng đệm.
    start = target - timedelta(days=400)
    end = target + timedelta(days=40)
    if as_of is not None and as_of < end:
        end = as_of
    sym_recs = load_prices(symbol, start, end)
    bench_recs = load_prices(benchmark, start, end)
    if not sym_recs:
        return Reaction(symbol=symbol, t0_requested=t0, t0_actual=None,
                        benchmark=benchmark, n_est_bars=0,
                        note=f"không có dữ liệu giá cho {symbol}")
    if not bench_recs:
        return Reaction(symbol=symbol, t0_requested=t0, t0_actual=None,
                        benchmark=benchmark, n_est_bars=0,
                        note=f"không có dữ liệu benchmark {benchmark}")

    sym_recs, bench_recs = _align(sym_recs, bench_recs)
    i0 = _index_of_session(sym_recs, target)
    if i0 is None:
        return Reaction(symbol=symbol, t0_requested=t0, t0_actual=None,
                        benchmark=benchmark, n_est_bars=0,
                        note="không có phiên nào tại hoặc trước mốc sự kiện")

    result = Reaction(
        symbol=symbol, t0_requested=t0,
        t0_actual=sym_recs[i0].date.strftime("%Y-%m-%d"),
        benchmark=benchmark, n_est_bars=0,
    )

    # Lợi suất: r[k] là lợi suất của phiên k+1 so với phiên k.
    r_sym = _returns(sym_recs)
    r_ben = _returns(bench_recs)

    # --- Ước lượng alpha/beta trên cửa sổ trước sự kiện --------------------
    lo = max(0, i0 + EST_START)
    hi = i0 + EST_END                      # loại trừ 10 phiên sát sự kiện
    est_y = r_sym[lo:hi] if hi > lo else []
    est_x = r_ben[lo:hi] if hi > lo else []
    result.n_est_bars = len(est_y)
    if len(est_y) < MIN_EST_BARS:
        result.note = (f"chỉ có {len(est_y)} phiên để ước lượng "
                       f"(cần ≥ {MIN_EST_BARS}) — không tính abnormal return")
        return result
    result.alpha, result.beta = _ols(est_y, est_x)

    # --- Abnormal return trong cửa sổ sự kiện -----------------------------
    ar: Dict[str, float] = {}
    for k in range(EVT_START, EVT_END + 1):
        idx = i0 + k                       # chỉ số phiên
        ri = idx - 1                       # lợi suất của phiên đó nằm ở r[idx-1]
        if ri < 0 or ri >= len(r_sym):
            continue
        expected = result.alpha + result.beta * r_ben[ri]
        ar[f"t{k:+d}"] = r_sym[ri] - expected
    result.ar = {k: round(v, 6) for k, v in ar.items()}

    def _sum(ks: Sequence[str]) -> Optional[float]:
        vals = [ar[k] for k in ks if k in ar]
        return round(sum(vals), 6) if vals else None

    result.car_pre = _sum([f"t{k:+d}" for k in range(-5, 0)])
    result.car_immediate = _sum(["t+0", "t+1"])
    result.car_post = _sum([f"t{k:+d}" for k in range(1, 11)])
    if "t+10" not in ar:
        result.incomplete = True
        if not result.note:
            result.note = "chưa đủ 10 phiên sau sự kiện — cửa sổ sau còn dở"

    # --- Lợi suất thô để đối chiếu ----------------------------------------
    last = min(i0 + EVT_END, len(sym_recs) - 1)
    if sym_recs[i0].priceClose:
        result.ret_raw = round(
            sym_recs[last].priceClose / sym_recs[i0].priceClose - 1.0, 6)
    if bench_recs[i0].priceClose:
        result.ret_benchmark = round(
            bench_recs[last].priceClose / bench_recs[i0].priceClose - 1.0, 6)

    # --- Volume quanh sự kiện ---------------------------------------------
    vlo = max(0, i0 - VOL_WINDOW)
    base = [r.dealVolume for r in sym_recs[vlo:i0] if r.dealVolume]
    if base:
        mean = sum(base) / len(base)
        var = sum((v - mean) ** 2 for v in base) / len(base)
        sd = var ** 0.5
        v0 = sym_recs[i0].dealVolume or 0.0
        result.volume_ratio = round(v0 / mean, 3) if mean else None
        result.volume_z = round((v0 - mean) / sd, 3) if sd else None

    # --- Trần/sàn: phép đo bị cắt cụt -------------------------------------
    states = []
    for k in range(0, min(EVT_END, len(sym_recs) - 1 - i0) + 1):
        st = candles.limit_state(sym_recs[i0 + k], band_pct)
        states.append(st)
    result.limit_states = states
    result.limit_hit = any(s in (candles.CEILING, candles.FLOOR) for s in states)

    return result
