"""Hiệu chuẩn — chứng minh từng trụ nói được điều gì, trước khi cho nó vào điểm.

`Documents/plan_news_pipeline.md` §8b đã để lại một tiền lệ đáng giữ: lượt event
study đầu tiên ra **kết quả âm tính**, và cái cứu nó khỏi thành một kết luận sai
là **placebo test** — trung vị placebo hoá ra là −0,33%, không phải 0, nên một
CAR −0,5% chẳng chứng minh gì. Tầng này đi qua đúng cửa đó.

Tài liệu bên ngoài cũng không hứa hẹn gì hơn: nghiên cứu về sentiment cấp ngành
cho kết quả trái chiều, có công trình kết luận thẳng là thiếu sức dự báo bền
vững. Nên mặc định ở đây là **hoài nghi**, không phải hy vọng.

Ba điều bắt buộc, mỗi điều chặn một cách tự lừa mình:

1. **So với nền placebo, không so với 0.** Một ngành bất kỳ ở một ngày bất kỳ
   không có lợi suất tương đối kỳ vọng bằng 0 — phân phối lợi suất lệch phải,
   và VNINDEX là chỉ số trọng số vốn hoá nên nó không phải "ngành trung bình".

2. **Cửa sổ KHÔNG chồng lấn cho mọi phát biểu về ý nghĩa thống kê.** Lấy mỗi
   phiên một quan sát với lợi suất 20 phiên phía trước thì hai quan sát liền kề
   dùng chung 19/20 dữ liệu. Cỡ mẫu 4000 khi đó là ảo — số quan sát độc lập chỉ
   khoảng 200. Bản chồng lấn vẫn in ra để mô tả, nhưng con số quyết định lấy từ
   bản không chồng lấn.

3. **Trụ nào không qua cửa thì KHÔNG vào công thức điểm.** Trần điểm ở
   `score.py` là hệ quả của file này, không phải một con số chọn trước.
"""
import json
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from statistics import fmean, median, pstdev
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.macro import fundamentals as fund_mod
from src.macro import icb, rrg
from src.ta.loader import PROJECT_ROOT, load_prices

RESULT_DIR = PROJECT_ROOT / "macro" / "calibration"

#: Cửa sổ dự báo, tính bằng phiên.
HORIZON = 20

#: Số lần lấy mẫu placebo.
PLACEBO_DRAWS = 400

#: Dưới ngưỡng này thì một nhóm không đủ quan sát độc lập để phát biểu gì.
MIN_INDEPENDENT = 30

BENCHMARK = "VNINDEX"


# ---------------------------------------------------------------------------
def forward_relative(code: str, horizon: int = HORIZON,
                     benchmark: str = BENCHMARK
                     ) -> List[Tuple[str, float]]:
    """``(ngày, lợi suất tương đối của ngành so với thị trường sau ``horizon``)``.

    Tương đối chứ không tuyệt đối: câu hỏi là *ngành này có hơn thị trường
    không*, và một thị trường tăng 4% kéo mọi ngành lên cùng nó.
    """
    start, end = datetime(2010, 1, 1), datetime.now()
    sec = load_prices(icb.sector_symbol(code), start, end)
    ben = load_prices(benchmark, start, end)
    if not sec or not ben:
        return []
    bd = {r.date.strftime("%Y-%m-%d"): r.priceClose for r in ben}

    days: List[str] = []
    rel: List[float] = []
    for r in sec:
        day = r.date.strftime("%Y-%m-%d")
        b = bd.get(day)
        if b and r.priceClose > 0:
            days.append(day)
            rel.append(r.priceClose / b)

    out = []
    for i in range(len(days) - horizon):
        base = rel[i]
        if base <= 0:
            continue
        out.append((days[i], rel[i + horizon] / base - 1.0))
    return out


@dataclass
class Bucket:
    """Một nhóm quan sát — luôn mang theo cỡ mẫu **độc lập**, không chỉ cỡ thô."""
    name: str
    n_overlapping: int = 0
    n_independent: int = 0
    median_rel: Optional[float] = None
    mean_rel: Optional[float] = None
    hit_rate: Optional[float] = None       # % quan sát vượt thị trường
    placebo_median: Optional[float] = None
    edge: Optional[float] = None           # trung vị − trung vị placebo
    p_value: Optional[float] = None
    verdict: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _independent(points: Sequence[Tuple[str, float]], horizon: int
                 ) -> List[Tuple[str, float]]:
    """Giữ mỗi ``horizon`` phiên một quan sát — cửa sổ hết chồng lấn."""
    return list(points[::horizon])


def _placebo(pool: Sequence[float], size: int, draws: int,
             seed: int = 20260916) -> List[float]:
    """Trung vị của ``draws`` lần rút ngẫu nhiên ``size`` quan sát từ cả rổ.

    Đây là "nếu nhãn không mang thông tin gì thì một nhóm cỡ này trông thế nào".
    So với 0 là so với một giả thuyết không ai đưa ra.
    """
    rng = random.Random(seed)
    out = []
    for _ in range(draws):
        out.append(median(rng.choices(pool, k=size)))
    return sorted(out)


def _two_sided_p(placebo: Sequence[float], observed: float) -> float:
    """Tỷ lệ mẫu placebo *cực đoan hơn* quan sát, hai phía.

    Không phải p-value của một kiểm định tham số — nó là tỷ lệ hoán vị, và đó
    là điều đúng cần dùng ở đây vì phân phối lợi suất không chuẩn.
    """
    if not placebo:
        return 1.0
    centre = median(placebo)
    gap = abs(observed - centre)
    extreme = sum(1 for p in placebo if abs(p - centre) >= gap)
    return extreme / len(placebo)


# ---------------------------------------------------------------------------
# H1 — RRG có dẫn được lợi suất ngành không?
# ---------------------------------------------------------------------------
@dataclass
class Hypothesis:
    name: str
    question: str
    buckets: List[Bucket] = field(default_factory=list)
    pool_median: Optional[float] = None
    pool_n: int = 0
    passed: bool = False
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["buckets"] = [b.to_dict() for b in self.buckets]
        return d


def h1_rrg(codes: Optional[Sequence[str]] = None, horizon: int = HORIZON,
           draws: int = PLACEBO_DRAWS) -> Hypothesis:
    """Góc RRG tại t → lợi suất tương đối của ngành ở t+20.

    Gộp mọi ngành vào một rổ: mỗi (ngành, phiên) là một quan sát. Tách riêng
    từng ngành thì mỗi nhóm còn vài chục quan sát độc lập, không đủ để nói gì.
    """
    codes = list(codes or icb.distinct_codes(icb.fetch_tree()))
    out = Hypothesis(
        name="H1",
        question="Góc phần tư RRG tại t có dự báo lợi suất tương đối của "
                 f"ngành ở t+{horizon} không?")

    by_quadrant: Dict[str, List[float]] = {q: [] for q in
                                           (rrg.LEADING, rrg.IMPROVING,
                                            rrg.WEAKENING, rrg.LAGGING)}
    indep: Dict[str, List[float]] = {q: [] for q in by_quadrant}
    pool: List[float] = []
    pool_indep: List[float] = []

    for code in codes:
        fwd = forward_relative(code, horizon)
        if not fwd:
            continue
        rrg_by_day = {p.date: p.quadrant for p in rrg.load(code)}
        tagged = [(d, v, rrg_by_day[d]) for d, v in fwd if d in rrg_by_day]
        if not tagged:
            continue
        pool.extend(v for _, v, _ in tagged)
        for _, v, q in tagged:
            by_quadrant[q].append(v)
        for _, v, q in tagged[::horizon]:
            indep[q].append(v)
            pool_indep.append(v)

    out.pool_n = len(pool_indep)
    out.pool_median = median(pool_indep) if pool_indep else None
    if not pool_indep:
        out.note = "không có quan sát nào — chưa nạp RRG hoặc chưa nạp giá ngành"
        return out

    for quad in (rrg.LEADING, rrg.IMPROVING, rrg.WEAKENING, rrg.LAGGING):
        vals = indep[quad]
        b = Bucket(name=rrg.QUADRANT_VN[quad],
                   n_overlapping=len(by_quadrant[quad]),
                   n_independent=len(vals))
        if len(vals) < MIN_INDEPENDENT:
            b.verdict = f"chỉ {len(vals)} quan sát độc lập — chưa đủ để nói gì"
            out.buckets.append(b)
            continue
        b.median_rel = median(vals)
        b.mean_rel = fmean(vals)
        b.hit_rate = sum(1 for v in vals if v > 0) / len(vals)
        placebo = _placebo(pool_indep, len(vals), draws)
        b.placebo_median = median(placebo)
        b.edge = b.median_rel - b.placebo_median
        b.p_value = _two_sided_p(placebo, b.median_rel)
        b.verdict = ("tách được khỏi nền" if b.p_value < 0.05
                     else "không tách được khỏi nền")
        out.buckets.append(b)

    ranked = [b for b in out.buckets if b.edge is not None]
    if len(ranked) >= 3:
        lead = next((b for b in out.buckets
                     if b.name == rrg.QUADRANT_VN[rrg.LEADING]), None)
        lag = next((b for b in out.buckets
                    if b.name == rrg.QUADRANT_VN[rrg.LAGGING]), None)
        ordered = (lead is not None and lag is not None
                   and lead.edge is not None and lag.edge is not None
                   and lead.edge > lag.edge)
        # Ngưỡng đã hiệu chỉnh cho số phép kiểm chạy trên cùng dữ liệu, xem
        # ``ALPHA`` và ``h1_multi_horizon``. Dùng 0,05 trần ở đây là đúng cách
        # sinh ra một kết quả dương tính giả.
        significant = any(b.p_value is not None and b.p_value < ALPHA_ADJUSTED
                          for b in ranked)
        out.passed = bool(ordered and significant)
        out.note = (f"thứ tự đúng chiều và có nhóm vượt ngưỡng đã hiệu chỉnh "
                    f"({ALPHA_ADJUSTED:.4f})" if out.passed else
                    f"không đạt ở ngưỡng đã hiệu chỉnh {ALPHA_ADJUSTED:.4f} "
                    f"(Bonferroni cho {N_TESTS} phép kiểm)")
    return out


# ---------------------------------------------------------------------------
# Đa kiểm định — phép kiểm quan trọng nhất trong file này
# ---------------------------------------------------------------------------
#: Số phép kiểm chạy trên **cùng một bộ dữ liệu** khi dò H1: 3 cửa sổ × 4 góc.
N_TESTS = 12
ALPHA = 0.05
#: Bonferroni. Thô và bảo thủ, nhưng ở đây thô là đúng: thứ cần chặn là việc
#: chạy nhiều cửa sổ rồi báo cáo cái đẹp nhất.
ALPHA_ADJUSTED = ALPHA / N_TESTS

#: Các cửa sổ đã dò. Ghi ra để không ai "thử thêm một cửa sổ nữa" mà quên cộng
#: nó vào mẫu số.
HORIZONS_TESTED = (10, 20, 60)


def h1_multi_horizon(codes: Optional[Sequence[str]] = None,
                     horizons: Sequence[int] = HORIZONS_TESTED,
                     draws: int = PLACEBO_DRAWS) -> Hypothesis:
    """Chạy H1 trên **mọi** cửa sổ đã dò, rồi kết luận trên toàn bộ.

    Đây là phép kiểm quan trọng nhất ở đây, và nó tồn tại vì một chuyện đã xảy
    ra thật trong chính lượt hiệu chuẩn này: chạy cửa sổ 20 phiên cho *dẫn dắt*
    một p-value 0,025 — trông như một phát hiện. Chạy thêm 10 và 60 phiên thì
    **không cửa sổ nào còn ý nghĩa**, và hiệu ứng ở 20 phiên là +0,31 điểm phần
    trăm với tỷ lệ vượt thị trường 49% so với nền 46–47%.

    Ba cửa sổ × bốn góc là 12 phép kiểm trên cùng dữ liệu. Ở mức 0,05 thì kỳ
    vọng có **0,6 kết quả dương tính giả** — nên đúng một p = 0,025 là thứ nhiễu
    sinh ra thường xuyên, không phải bằng chứng. Báo cáo riêng cửa sổ 20 phiên
    và im lặng về hai cửa sổ kia là định nghĩa của *p-hacking*, và nó sẽ không
    bị ai phát hiện — nên phép chặn phải nằm trong code chứ không trong ý chí.
    """
    codes = list(codes or icb.distinct_codes(icb.fetch_tree()))
    out = Hypothesis(
        name="H1-đa-cửa-sổ",
        question=f"Sau khi hiệu chỉnh cho {N_TESTS} phép kiểm trên cùng dữ "
                 f"liệu, góc RRG còn dự báo được gì không?")
    best_p = 1.0
    for horizon in horizons:
        sub = h1_rrg(codes, horizon, draws)
        for b in sub.buckets:
            if b.p_value is None:
                continue
            best_p = min(best_p, b.p_value)
            b.name = f"{b.name} · {horizon} phiên"
            out.buckets.append(b)
    out.pool_n = sum(b.n_independent for b in out.buckets)
    out.passed = best_p < ALPHA_ADJUSTED
    out.note = (
        f"p nhỏ nhất qua {len(out.buckets)} phép kiểm: **{best_p:.3f}**. "
        f"Ngưỡng Bonferroni: {ALPHA_ADJUSTED:.4f}. "
        + ("Vượt ngưỡng — hiệu ứng thật."
           if out.passed else
           "**Không vượt.** Ở mức 0,05 thì 12 phép kiểm kỳ vọng sinh ra 0,6 "
           "kết quả dương tính giả; một p = 0,025 lẻ loi nằm gọn trong đó. "
           "Kết luận: góc RRG **không** chứng minh được sức dự báo trên dữ "
           "liệu này."))
    return out


# ---------------------------------------------------------------------------
# H2 — nền tảng có thêm gì ngoài H1?
# ---------------------------------------------------------------------------
def h2_fundamentals(codes: Optional[Sequence[str]] = None,
                    horizon: int = HORIZON, field_name: str = "ROE",
                    draws: int = PLACEBO_DRAWS) -> Hypothesis:
    """Xu hướng ROE của ngành tại t → lợi suất tương đối ở t+20.

    ⚠️ **Một hạn chế phải nói thẳng, và nó không sửa được bằng code.** Chỉ có
    **một** bản đóng băng BCTC (chạy lần đầu hôm nay), nên "giá trị ROE quý
    2/2020" ở đây là giá trị *như FireAnt công bố hôm nay*, có thể đã được sửa
    lại so với bản ra năm 2020. ``PUBLISH_LAG`` chặn được việc đọc một quý chưa
    công bố, nhưng **không** chặn được việc đọc bản đã sửa của một quý đã công
    bố. Kết quả H2 vì thế lạc quan hơn thực tế một chút, và sẽ chỉ sạch dần khi
    kho ảnh chụp dày lên theo thời gian.
    """
    codes = list(codes or icb.distinct_codes(icb.fetch_tree()))
    out = Hypothesis(
        name="H2",
        question=f"Xu hướng {field_name} của ngành có dự báo lợi suất tương "
                 f"đối ở t+{horizon} không?",
        note="⚠️ dùng giá trị BCTC *đã sửa* — chỉ có một bản đóng băng")

    up: List[float] = []
    down: List[float] = []
    pool: List[float] = []
    n_over_up = n_over_down = 0

    for code in codes:
        fwd = forward_relative(code, horizon)
        quarters = fund_mod.load(code)
        if not fwd or len(quarters) < 6:
            continue
        # Với mỗi phiên, tìm các quý **đã công bố** trước phiên đó rồi lấy dốc.
        known = [(q.known_from.strftime("%Y-%m-%d"), q.get(field_name))
                 for q in quarters]
        known = [(d, v) for d, v in known if v is not None]
        if len(known) < 6:
            continue
        for day, value in fwd[::horizon]:
            seen = [v for d, v in known if d <= day]
            if len(seen) < 4:
                continue
            slope = fund_mod._slope(seen[-4:])
            if slope is None:
                continue
            pool.append(value)
            (up if slope > 0 else down).append(value)
        for day, _ in fwd:
            seen = sum(1 for d, _v in known if d <= day)
            if seen >= 4:
                n_over_up += 1

    out.pool_n = len(pool)
    out.pool_median = median(pool) if pool else None
    if len(pool) < MIN_INDEPENDENT * 2:
        out.note += f" · chỉ {len(pool)} quan sát độc lập — chưa đủ"
        return out

    for name, vals in (("xu hướng đi lên", up), ("xu hướng đi xuống", down)):
        b = Bucket(name=name, n_overlapping=n_over_up, n_independent=len(vals))
        if len(vals) < MIN_INDEPENDENT:
            b.verdict = f"chỉ {len(vals)} quan sát độc lập — chưa đủ để nói gì"
            out.buckets.append(b)
            continue
        b.median_rel = median(vals)
        b.mean_rel = fmean(vals)
        b.hit_rate = sum(1 for v in vals if v > 0) / len(vals)
        placebo = _placebo(pool, len(vals), draws)
        b.placebo_median = median(placebo)
        b.edge = b.median_rel - b.placebo_median
        b.p_value = _two_sided_p(placebo, b.median_rel)
        b.verdict = ("tách được khỏi nền" if b.p_value < 0.05
                     else "không tách được khỏi nền")
        out.buckets.append(b)

    ok = [b for b in out.buckets if b.edge is not None]
    if len(ok) == 2:
        out.passed = bool(ok[0].edge > ok[1].edge
                          and any(b.p_value < 0.05 for b in ok))
        out.note += (" · đạt" if out.passed else
                     " · không đạt: hai nhóm không tách khỏi nền")
    return out


# ---------------------------------------------------------------------------
@dataclass
class Calibration:
    generated: str
    horizon: int
    hypotheses: List[Hypothesis] = field(default_factory=list)

    def passed(self, name: str) -> bool:
        for h in self.hypotheses:
            if h.name == name:
                return h.passed
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {"generated": self.generated, "horizon": self.horizon,
                "hypotheses": [h.to_dict() for h in self.hypotheses]}


def result_path(root: Optional[Path] = None) -> Path:
    return (root or RESULT_DIR) / "latest.json"


def save(cal: Calibration, root: Optional[Path] = None) -> Path:
    out = result_path(root)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cal.to_dict(), ensure_ascii=False, indent=1),
                   encoding="utf-8")
    return out


def load(root: Optional[Path] = None) -> Optional[Calibration]:
    src = result_path(root)
    if not src.is_file():
        return None
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    cal = Calibration(generated=data.get("generated", ""),
                      horizon=int(data.get("horizon") or HORIZON))
    for h in data.get("hypotheses") or []:
        hyp = Hypothesis(name=h.get("name", ""), question=h.get("question", ""),
                         pool_median=h.get("pool_median"),
                         pool_n=int(h.get("pool_n") or 0),
                         passed=bool(h.get("passed")), note=h.get("note", ""))
        hyp.buckets = [Bucket(**b) for b in h.get("buckets") or []]
        cal.hypotheses.append(hyp)
    return cal


def run(codes: Optional[Sequence[str]] = None,
        horizon: int = HORIZON) -> Calibration:
    codes = list(codes or icb.distinct_codes(icb.fetch_tree()))
    cal = Calibration(generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
                      horizon=horizon)
    cal.hypotheses.append(h1_rrg(codes, horizon))
    cal.hypotheses.append(h1_multi_horizon(codes))
    cal.hypotheses.append(h2_fundamentals(codes, horizon))
    return cal


def _pct(v: Optional[float]) -> str:
    return "—" if v is None else f"{v * 100:+.2f}%"


def format_calibration(cal: Calibration) -> str:
    lines = [f"# Hiệu chuẩn tầng ngành — {cal.generated}", "",
             f"Cửa sổ dự báo **{cal.horizon} phiên**. Lợi suất là **tương đối "
             f"so với VNINDEX**. Mọi con số quyết định lấy từ mẫu **không chồng "
             f"lấn** (mỗi {cal.horizon} phiên một quan sát); cột *thô* chỉ để "
             f"thấy quy mô dữ liệu.", ""]
    for h in cal.hypotheses:
        mark = "✅ ĐẠT" if h.passed else "❌ KHÔNG ĐẠT"
        lines += [f"## {h.name} — {mark}", "", f"*{h.question}*", ""]
        if h.pool_median is not None:
            lines.append(f"Nền chung: trung vị {_pct(h.pool_median)} trên "
                         f"{h.pool_n} quan sát độc lập.")
            lines.append("")
        lines += ["| Nhóm | Độc lập | Thô | Trung vị | Nền placebo | Chênh | % vượt TT | p | Kết luận |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|---|"]
        for b in h.buckets:
            p = "—" if b.p_value is None else f"{b.p_value:.3f}"
            hit = "—" if b.hit_rate is None else f"{b.hit_rate:.0%}"
            lines.append(
                f"| {b.name} | {b.n_independent} | {b.n_overlapping} | "
                f"{_pct(b.median_rel)} | {_pct(b.placebo_median)} | "
                f"{_pct(b.edge)} | {hit} | {p} | {b.verdict} |")
        if h.note:
            lines += ["", h.note]
        lines.append("")

    lines += ["---", "",
              "**Trụ nào không qua cửa thì không vào công thức điểm.** Trần "
              "điểm trong `score.py` là hệ quả của bảng này, không phải một "
              "con số chọn trước."]
    return "\n".join(lines)


def _main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Hiệu chuẩn tầng ngành")
    ap.add_argument("--horizon", type=int, default=HORIZON)
    ap.add_argument("--codes", default="")
    args = ap.parse_args()
    codes = [c for c in args.codes.split(",") if c.strip()] or None
    cal = run(codes, args.horizon)
    save(cal)
    print(format_calibration(cal))


if __name__ == "__main__":
    _main()
