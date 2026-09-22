"""Hiệu chuẩn dòng tiền — D1 (khối ngoại) và D2 (tự doanh).

Đây là cửa mà ``flows.py`` phải đi qua trước khi được phép nói câu nào có dạng
*"khối ngoại mua ròng nên mã này sẽ…"*. Trước khi qua cửa, nó chỉ được phép in
số đo.

Dòng tiền là nguồn **duy nhất** trong cả tầng bàn phân tích đo được ngay hôm
nay: 16 năm dữ liệu đã nằm trên đĩa, không phụ thuộc model ngôn ngữ, không phải
đợi tích luỹ tiến như điểm tin. Nên nếu nó không tách được khỏi nền thì đó là
một kết luận **thật**, không phải một phép đo chưa chạy được — và phải in ra
đúng như vậy.

Bốn phép chặn tự lừa mình, lấy nguyên của ``macro/calibrate.py`` (dùng lại hàm,
không chép lại):

1. **So với nền placebo, không so với 0.** Phân phối lợi suất lệch phải; một
   nhóm bất kỳ cũng không có kỳ vọng bằng 0.
2. **Mẫu không chồng lấn.** Lấy mỗi phiên một quan sát với lợi suất 20 phiên
   phía trước thì hai quan sát liền kề dùng chung 19/20 dữ liệu. Cỡ mẫu vài
   chục nghìn khi đó là ảo.
3. **Bonferroni cho số phép kiểm đã chạy.** 2 chỉ số × 3 cửa sổ × 2 đuôi = 12
   phép kiểm chính; ở mức 0,05 thì 12 phép kiểm kỳ vọng sinh 0,6 dương tính
   giả, nên một p lẻ loi không nói gì.
4. **Chạy hai bản: cả rổ và bản đã loại phiên đặc biệt** (mã kín room, tuần ETF
   cơ cấu — §7.3 của plan). Bản "sạch" là **kiểm tra bền vững**, không được đếm
   thêm vào số phép kiểm; lệch nhau nhiều thì kết luận thuộc về bản đã loại.

Và một phép chặn thứ năm, phát hiện ra **ngay ở lượt chạy đầu**: chia nhóm theo
giá trị tuyệt đối gộp cả rổ thì mỗi nhóm có một *thành phần mã* khác nhau, nên
cái đo được có thể chỉ là "nhóm này gồm những mã nào". Vì thế nhóm chia theo
**phân vị trong chính mã** (``_percentile_ranks``) — mọi nhóm khi đó có cùng
thành phần mã, và phần còn lại mới là dòng tiền.

Lợi suất luôn là **tương đối so với VNINDEX**: câu hỏi là *mã này có hơn thị
trường không*, và một thị trường tăng 4% kéo mọi mã lên cùng nó.
"""
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.desk.flows import FlowPoint, build_points
from src.macro.calibrate import (Bucket, Hypothesis, _independent, _placebo,
                                 _two_sided_p)
from src.ta.loader import PROJECT_ROOT, load_prices, resolve_universe

RESULT_DIR = PROJECT_ROOT / "desk" / "calibration"
RESULT_NAME = "flows.json"

BENCHMARK = "VNINDEX"
HISTORY_START = datetime(2010, 1, 1)

#: Cửa sổ dự báo, tính bằng phiên.
HORIZONS: Tuple[int, ...] = (5, 10, 20)

#: Số nhóm chia theo độ mạnh của dòng tiền.
BUCKETS = 5

PLACEBO_DRAWS = 400

#: Dưới ngần này quan sát **độc lập** thì một nhóm không đủ để phát biểu gì.
MIN_INDEPENDENT = 30

#: Số phép kiểm chính: 2 chỉ số × 3 cửa sổ × 2 đuôi.
N_TESTS = 2 * len(HORIZONS) * 2
ALPHA = 0.05
ALPHA_BONFERRONI = ALPHA / N_TESTS

FEATURES = {
    "foreign": ("D1", "khối ngoại mua ròng (chuẩn hoá theo thanh khoản của chính mã)"),
    "prop": ("D2", "tự doanh mua ròng (chuẩn hoá theo thanh khoản của chính mã)"),
}

NO_CALIBRATION = ("⚠️ Dòng tiền **chưa hiệu chuẩn** — các số dưới đây là phép đo, "
                  "không phải dự báo. Chạy `desk_calibrate_flows` để biết chúng "
                  "tách được khỏi nền hay không.")
NOT_PREDICTIVE = ("Hiệu chuẩn đã chạy và **không giả thuyết nào đạt**: dòng tiền ở "
                  "đây là mô tả trạng thái, không phải tín hiệu dự báo. Đây là kết "
                  "luận của dữ liệu, không phải chỗ chưa đo.")


# ---------------------------------------------------------------------------
@dataclass
class Observation:
    date: str
    value: float          # giá trị của chỉ số dòng tiền tại t
    rel: float            # lợi suất tương đối so với VNINDEX ở t+horizon
    special: bool = False  # phiên kín room / tuần ETF cơ cấu
    symbol: str = ""
    pct_rank: float = 0.5  # phân vị của ``value`` trong chính chuỗi của mã đó


def _percentile_ranks(values: Sequence[float]) -> List[float]:
    """Phân vị của từng giá trị **trong chính chuỗi của nó**, ties chia trung bình.

    Đây là chỗ chặn một cái bẫy đã hiện ra ngay ở lượt chạy đầu: chia nhóm theo
    **giá trị tuyệt đối gộp cả rổ** thì mỗi nhóm có một *thành phần mã* khác
    nhau — mã thanh khoản mỏng đóng góp nhiều quan sát ở đuôi, mã lớn dồn vào
    giữa — nên cái đo được có thể chỉ là *nhóm này gồm những mã nào*, không phải
    *dòng tiền nói gì*. Xếp hạng trong từng mã làm mọi nhóm có cùng thành phần
    mã. Cùng lý lẽ "đo giá trị gia tăng thì phải giữ giá cố định" của
    ``newsfeat.h3_proxy``.
    """
    n = len(values)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = (avg + 0.5) / n
        i = j + 1
    return ranks


def _benchmark_map(as_of: Optional[datetime] = None) -> Dict[str, float]:
    bars = load_prices(BENCHMARK, HISTORY_START, as_of or datetime.now())
    return {b.date.strftime("%Y-%m-%d"): b.priceClose for b in bars}


def _feature_value(point: FlowPoint, feature: str) -> Optional[float]:
    if feature == "foreign":
        return point.foreign_net_pct
    if feature == "prop":
        return point.prop_net_pct
    raise ValueError(f"chỉ số dòng tiền không biết: {feature}")


def symbol_observations(symbol: str, feature: str, horizon: int,
                        bench: Dict[str, float],
                        as_of: Optional[datetime] = None,
                        points: Optional[Sequence[FlowPoint]] = None,
                        closes: Optional[Dict[str, float]] = None
                        ) -> List[Observation]:
    """Quan sát của một mã: dòng tiền tại t → lợi suất tương đối tại t+horizon.

    Nhận sẵn ``points``/``closes`` để lượt chạy cả rổ nạp mỗi mã **một lần** cho
    cả sáu tổ hợp (2 chỉ số × 3 cửa sổ) thay vì sáu lần.
    """
    if points is None or closes is None:
        bars = load_prices(symbol, HISTORY_START, as_of or datetime.now())
        points = build_points(bars)
        closes = {b.date.strftime("%Y-%m-%d"): b.priceClose for b in bars}

    usable = [p for p in points if p.date in bench and bench[p.date] > 0
              and closes.get(p.date)]
    rel = [closes[p.date] / bench[p.date] for p in usable]

    out: List[Observation] = []
    for i in range(len(usable) - horizon):
        value = _feature_value(usable[i], feature)
        if value is None or rel[i] <= 0:
            continue
        out.append(Observation(
            date=usable[i].date,
            value=value,
            rel=rel[i + horizon] / rel[i] - 1.0,
            special=bool(usable[i].room_capped or usable[i].etf_window),
            symbol=symbol.strip().upper(),
        ))
    for obs, rank in zip(out, _percentile_ranks([o.value for o in out])):
        obs.pct_rank = rank
    return out


def _bucket_edges(values: Sequence[float], n: int = BUCKETS) -> List[float]:
    """Mốc chia nhóm theo phân vị của **chính mẫu**, không phải ngưỡng chọn trước.

    Mốc trùng nhau bị **gộp lại**. Không gộp là sinh ra một nhóm rỗng trông như
    "đã đo và không có quan sát nào", trong khi sự thật là hai mốc bằng nhau vì
    một khối giá trị giống hệt (ví dụ 8–14% số phiên có dòng tiền đúng bằng 0)
    chiếm trọn một phân vị — lượt chạy đầu của D2 ra đúng như vậy: nhóm 3 rỗng
    và nhóm 4 phình lên 9.991 quan sát.
    """
    ordered = sorted(values)
    if not ordered:
        return []
    raw = [ordered[int(len(ordered) * k / n)] for k in range(1, n)]
    out: List[float] = []
    for edge in raw:
        if not out or edge > out[-1]:
            out.append(edge)
    return out


def _bucket_index(value: float, edges: Sequence[float]) -> int:
    for i, edge in enumerate(edges):
        if value < edge:
            return i
    return len(edges)


def split_buckets(rows: Sequence[Observation], n: int = BUCKETS
                  ) -> List[List[Observation]]:
    """Chia quan sát thành nhóm theo ``pct_rank``, **bỏ hẳn nhóm rỗng**.

    Một nhóm rỗng in ra kèm dấu `—` đọc y hệt "đã đo và không có gì", trong khi
    sự thật là phép chia không tách được ở đó — khối giá trị bằng nhau nằm trọn
    trong một phân vị. Bỏ nhóm rỗng đi và nói ra số nhóm thật là cách duy nhất
    không để hai chuyện đó trông giống nhau.
    """
    if not rows:
        return []
    edges = _bucket_edges([o.pct_rank for o in rows], n)
    groups: List[List[Observation]] = [[] for _ in range(len(edges) + 1)]
    for o in rows:
        groups[_bucket_index(o.pct_rank, edges)].append(o)
    return [g for g in groups if g]


def _bucket_name(i: int, n: int, values: Sequence[float],
                 low_label: str = "thấp nhất", high_label: str = "cao nhất",
                 unit: str = "%") -> str:
    """Tên nhóm mang luôn **khoảng giá trị thật** của nó.

    Không có khoảng thì "nhóm 4" là một cái nhãn không kiểm chứng được: người
    đọc không biết nó gồm phiên mua ròng cỡ nào, mà đó mới là thứ họ cần để bác
    lại kết luận. Nhãn hai đuôi và đơn vị là tham số vì cùng bộ máy này chạy cho
    cả dòng tiền (`%` thanh khoản, "bán/mua ròng") lẫn định giá (`x` lần, "rẻ/
    đắt") — để mặc nhãn của dòng tiền cho bảng định giá là in ra một câu sai.
    """
    if values:
        sign = "+" if unit == "%" else ""
        span = f" [{min(values):{sign}.1f}{unit} → {max(values):{sign}.1f}{unit}]"
    else:
        span = ""
    if i == 0:
        return f"nhóm 1 — {low_label}{span}"
    if i == n - 1:
        return f"nhóm {n} — {high_label}{span}"
    return f"nhóm {i + 1}{span}"


def evaluate_buckets(rows: Sequence[Observation], name: str, question: str,
                     alpha: float = ALPHA_BONFERRONI,
                     draws: int = PLACEBO_DRAWS,
                     low_label: str = "thấp nhất", high_label: str = "cao nhất",
                     unit: str = "%", expect: int = 1) -> Hypothesis:
    """Chia nhóm theo ``pct_rank`` rồi hỏi từng nhóm có khác nền không.

    Tách riêng để tầng định giá dùng lại **đúng bộ máy này** thay vì chép sang
    một bản thứ hai — hai bản chấm điểm song song là hai bản trôi xa nhau, và
    bản nào sai thì không ai biết.
    """
    pool = [o.rel for o in rows]
    hyp = Hypothesis(name=name, question=question, pool_n=len(pool),
                     pool_median=(round(median(pool) * 100, 3) if pool else None))
    if len(rows) < MIN_INDEPENDENT * BUCKETS:
        hyp.note = (f"chỉ {len(rows)} quan sát độc lập — **chưa đo được**, "
                    "không phải đã đo và thấy phẳng")
        return hyp

    # Chia nhóm theo **phân vị trong chính mã**, không theo giá trị tuyệt đối
    # gộp cả rổ — xem ``_percentile_ranks``.
    groups = split_buckets(rows)
    if len(groups) < BUCKETS:
        hyp.note = (f"chỉ tách được {len(groups)} nhóm thay vì {BUCKETS} — một "
                    "khối quan sát mang cùng một giá trị chiếm trọn hơn một "
                    "phân vị. ")

    for i, grp in enumerate(groups):
        rels = [o.rel for o in grp]
        b = Bucket(name=_bucket_name(i, len(groups), [o.value for o in grp],
                                     low_label, high_label, unit),
                   n_independent=len(grp))
        if len(grp) < MIN_INDEPENDENT:
            b.verdict = "chưa đủ quan sát độc lập"
            hyp.buckets.append(b)
            continue
        obs_median = median(rels)
        placebo = _placebo(pool, len(rels), draws)
        b.median_rel = round(obs_median * 100, 3)
        b.mean_rel = round(sum(rels) / len(rels) * 100, 3)
        b.hit_rate = round(sum(1 for r in rels if r > 0) / len(rels) * 100, 1)
        b.placebo_median = round(median(placebo) * 100, 3)
        b.edge = round((obs_median - median(placebo)) * 100, 3)
        b.p_value = round(_two_sided_p(placebo, obs_median), 4)
        b.verdict = ("tách khỏi nền" if b.p_value < alpha
                     else "không tách khỏi nền")
        hyp.buckets.append(b)

    top = hyp.buckets[-1] if hyp.buckets else None
    bottom = hyp.buckets[0] if hyp.buckets else None
    hits = []
    # ``expect`` là **chiều đã đăng ký trước** của giả thuyết, và nó khác nhau
    # theo chỉ số: dòng tiền mạnh hơn thì kỳ vọng lợi suất **cao hơn**
    # (``expect=+1``), còn định giá cao hơn thì kỳ vọng lợi suất **thấp hơn**
    # (``expect=-1``). Dùng chung một chiều cho cả hai là đọc một kết quả đúng
    # chiều của định giá thành "không đạt" — đã xảy ra thật ở lượt chạy đầu của
    # V2-120p (nhóm đắt nhất thua nền 5,2 điểm, p 0,005, bị báo là không đạt).
    if top and top.p_value is not None and top.p_value < alpha \
            and (top.edge or 0) * expect > 0:
        hits.append(f"nhóm {high_label} "
                    + ("vượt nền" if expect > 0 else "thua nền"))
    if bottom and bottom.p_value is not None and bottom.p_value < alpha \
            and (bottom.edge or 0) * expect < 0:
        hits.append(f"nhóm {low_label} "
                    + ("thua nền" if expect > 0 else "vượt nền"))
    hyp.passed = bool(hits)
    hyp.note += ("; ".join(hits) if hits else
                 f"không đuôi nào qua ngưỡng Bonferroni {alpha:.5f}")

    # Sàn phân giải của phép hoán vị: với ``draws`` lần rút, p nhỏ nhất khác 0
    # là 1/draws. Một p nằm sát sàn đó được dựng từ một hai lần rút, nên nó
    # **chưa đo được chính xác**, chỉ mới "nhỏ hơn sàn".
    floor = 2.0 / max(draws, 1)
    tight = [b for b in (top, bottom)
             if b and b.p_value is not None and b.p_value <= floor]
    if tight:
        hyp.note += (f" · ⚠️ p của đuôi nằm sát sàn phân giải placebo "
                     f"({floor:.4f} với {draws} lần rút) — tăng số lần rút "
                     "trước khi tin con số đó")
    return hyp


def build_hypothesis(observations: Sequence[Observation], feature: str,
                     horizon: int, exclude_special: bool,
                     draws: int = PLACEBO_DRAWS) -> Hypothesis:
    """D1/D2 — vỏ mỏng quanh ``evaluate_buckets``, chỉ lo đặt tên và lọc mẫu."""
    code, label = FEATURES[feature]
    rows = [o for o in observations if not (exclude_special and o.special)]
    variant = "đã loại phiên kín room / tuần ETF" if exclude_special else "cả rổ"
    return evaluate_buckets(
        rows,
        name=f"{code}-{horizon}p{'-sach' if exclude_special else ''}",
        question=(f"{label} tại t → lợi suất tương đối {horizon} phiên sau "
                  f"({variant}; nhóm chia theo phân vị trong chính mã)"),
        draws=draws, low_label="bán ròng mạnh nhất",
        high_label="mua ròng mạnh nhất", unit="%")


# ---------------------------------------------------------------------------
@dataclass
class FlowCalibration:
    generated: str
    universe: str
    n_symbols: int
    hypotheses: List[Hypothesis] = field(default_factory=list)
    robustness: List[Hypothesis] = field(default_factory=list)
    n_tests: int = N_TESTS
    alpha: float = ALPHA_BONFERRONI
    prop_first_session: Optional[str] = None
    note: str = ""
    postscript: str = ""

    def passed(self, name: str) -> bool:
        return any(h.name == name and h.passed for h in self.hypotheses)

    @property
    def any_passed(self) -> bool:
        return any(h.passed for h in self.hypotheses)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["hypotheses"] = [h.to_dict() for h in self.hypotheses]
        d["robustness"] = [h.to_dict() for h in self.robustness]
        d["any_passed"] = self.any_passed
        return d


def _postscript(hyps: Sequence[Hypothesis]) -> str:
    """Bắt các nhóm GIỮA có p nhỏ — và gọi đúng tên chúng là *quan sát hậu nghiệm*.

    Giả thuyết đăng ký trước chỉ nói về hai đuôi. Một nhóm giữa đẹp đều đặn là
    thứ đáng ghi lại, nhưng nếu gọi nó là "kết quả" thì đó chính là kiểu tìm
    tòi hậu nghiệm mà ngưỡng Bonferroni sinh ra để chặn. Cách duy nhất để nó
    thành kết quả là **đăng ký trước rồi kiểm trên quãng khác**.
    """
    hits = []
    for h in hyps:
        mid = h.buckets[1:-1]
        for b in mid:
            if b.p_value is not None and b.p_value < ALPHA_BONFERRONI:
                hits.append(f"{h.name}/{b.name.split(' [')[0]}")
    if not hits:
        return ""
    return ("⚠️ **Quan sát hậu nghiệm, chưa phải kết quả:** nhóm *giữa* (dòng tiền "
            f"gần bằng 0) qua ngưỡng ở {len(hits)} chỗ — {', '.join(hits[:6])}. "
            "Giả thuyết đăng ký trước chỉ nói về hai đuôi, nên con số này không "
            "được đọc như một phát hiện: muốn dùng thì phải đăng ký thành giả "
            "thuyết riêng rồi kiểm trên một quãng thời gian khác.")


def _load_symbol(symbol: str, as_of: Optional[datetime]
                 ) -> Tuple[List[FlowPoint], Dict[str, float]]:
    bars = load_prices(symbol, HISTORY_START, as_of or datetime.now())
    return build_points(bars), {b.date.strftime("%Y-%m-%d"): b.priceClose
                                for b in bars}


def run(universe: Optional[str] = None, as_of: Optional[datetime] = None,
        horizons: Sequence[int] = HORIZONS, draws: int = PLACEBO_DRAWS
        ) -> FlowCalibration:
    """Chạy D1 + D2 trên cả rổ. Nạp mỗi mã đúng một lần."""
    symbols = resolve_universe(universe)
    bench = _benchmark_map(as_of)
    cached: Dict[str, Tuple[List[FlowPoint], Dict[str, float]]] = {}
    prop_first: Optional[str] = None
    for sym in symbols:
        try:
            cached[sym] = _load_symbol(sym, as_of)
        except Exception:                                      # noqa: BLE001
            continue
        for p in cached[sym][0]:
            if p.prop_net_bn is not None:
                if prop_first is None or p.date < prop_first:
                    prop_first = p.date
                break

    hyps: List[Hypothesis] = []
    robust: List[Hypothesis] = []
    for feature in FEATURES:
        for horizon in horizons:
            pooled: List[Observation] = []
            for sym, (points, closes) in cached.items():
                obs = symbol_observations(sym, feature, horizon, bench, as_of,
                                          points=points, closes=closes)
                # Mẫu không chồng lấn **trong từng mã** rồi mới gộp: cắt sau khi
                # gộp là vẫn giữ nguyên chồng lấn, chỉ trông như đã xử lý.
                pooled.extend(_independent(obs, horizon))
            hyps.append(build_hypothesis(pooled, feature, horizon, False, draws))
            robust.append(build_hypothesis(pooled, feature, horizon, True, draws))

    note = ("Lợi suất là **tương đối so với VNINDEX**. Bản 'sạch' (đã loại phiên "
            "kín room và tuần ETF cơ cấu) là kiểm tra bền vững, **không** đếm "
            "thêm vào số phép kiểm. ⚠️ Mẫu hết chồng lấn **trong từng mã**, "
            "không hết tương quan **giữa các mã**: 80 mã cùng một phiên chịu "
            "chung một thị trường, nên số quan sát thật sự độc lập còn thấp hơn "
            "`n` in ra — đọc p-value kèm điều đó.")
    if prop_first:
        note += (f" Số tự doanh chỉ có từ {prop_first} trở đi, nên D2 chạy trên "
                 "một quãng ngắn hơn D1.")
    return FlowCalibration(
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
        universe=universe or "all",
        n_symbols=len(cached),
        hypotheses=hyps,
        robustness=robust,
        prop_first_session=prop_first,
        note=note,
        postscript=_postscript(hyps),
    )


def result_path(root: Optional[Path] = None) -> Path:
    return (root or RESULT_DIR) / RESULT_NAME


def save(cal: FlowCalibration, root: Optional[Path] = None) -> Path:
    path = result_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cal.to_dict(), ensure_ascii=False, indent=1),
                    encoding="utf-8")
    return path


def load(root: Optional[Path] = None) -> Optional[FlowCalibration]:
    path = result_path(root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    hyps = []
    for h in data.get("hypotheses") or []:
        hyp = Hypothesis(name=h.get("name", ""), question=h.get("question", ""),
                         pool_median=h.get("pool_median"), pool_n=h.get("pool_n", 0),
                         passed=bool(h.get("passed")), note=h.get("note", ""))
        hyp.buckets = [Bucket(**{k: v for k, v in b.items()
                                 if k in Bucket.__dataclass_fields__})   # noqa: SLF001
                       for b in (h.get("buckets") or [])]
        hyps.append(hyp)
    return FlowCalibration(
        generated=data.get("generated", ""), universe=data.get("universe", ""),
        n_symbols=data.get("n_symbols", 0), hypotheses=hyps,
        n_tests=data.get("n_tests", N_TESTS), alpha=data.get("alpha", ALPHA_BONFERRONI),
        prop_first_session=data.get("prop_first_session"), note=data.get("note", ""),
        postscript=data.get("postscript", ""))


def calibration_note(root: Optional[Path] = None) -> Tuple[str, bool]:
    """Câu phải đi kèm **mọi** output dòng tiền có chữ.

    Ba trạng thái, và chúng khác nhau: *chưa chạy*, *đã chạy và không đạt*,
    *đã chạy và có cái đạt*. Gộp hai cái đầu lại là nói rằng đã đo trong khi
    chưa đo.
    """
    cal = load(root)
    if cal is None:
        return NO_CALIBRATION, False
    if not cal.any_passed:
        return f"{NOT_PREDICTIVE} (hiệu chuẩn {cal.generated})", False
    passed = [h.name for h in cal.hypotheses if h.passed]
    return (f"Hiệu chuẩn {cal.generated}: đạt {', '.join(passed)} "
            f"(ngưỡng Bonferroni {cal.alpha:.5f} cho {cal.n_tests} phép kiểm)."), True


def _main(argv: Optional[Sequence[str]] = None) -> int:        # pragma: no cover
    import sys
    args = list(argv if argv is not None else sys.argv[1:])
    started = datetime.now()
    cal = run(args[0] if args else None)
    path = save(cal)
    from src.desk.format import format_flow_calibration
    print(format_flow_calibration(cal))
    print(f"\nGhi {path} trong {(datetime.now() - started).seconds}s")
    return 0


if __name__ == "__main__":                                     # pragma: no cover
    raise SystemExit(_main())
