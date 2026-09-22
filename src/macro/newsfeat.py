"""Feature tin **cơ học** — backfill được, không dính nhìn trước, kiểm được ngay.

Giả thuyết H3 — *điểm tin có thêm gì ngoài các cột đo được* — không kiểm được
bằng điểm của model ngôn ngữ, và lý do là nguyên tắc chứ không phải kỹ thuật:
một model chấm tin tháng 3 vào hôm nay **đã biết** thị trường đi đâu sau đó.
``as_of`` cắt được dữ liệu đưa vào prompt, không cắt được trí nhớ của model. Nên
điểm LLM chỉ tích luỹ tiến được (``src/macro/gemini.py``), và sáu tháng nữa mới
đo.

Module này là nhánh chạy song song, trả lời một câu hẹp hơn nhưng **trả lời
được ngay**: *tin ngành, đo bằng thứ cơ học, có thêm gì ngoài giá không?*

Định dùng **hai** feature. Chỉ một cái sống.

* **Khối lượng tin** khớp từ khoá ngành trong cửa sổ, chuẩn hoá theo chính
  ngành đó. "Ngành này đang được nói tới nhiều bất thường" là một phát biểu về
  sự chú ý, đo được mà không cần đọc hiểu. ✅ dùng được.

* **Sắc thái FireAnt gán lúc đăng** (``macro_posts.sentiment``) — ❌ **trường
  này rỗng.** Đã đếm cả kho: **53.996/53.998 bài mang đúng giá trị 0**, và kho
  tin gắn mã của tầng `src/news/` cũng thế (57.909/57.928). Gọi thẳng API trên
  300 bài mẫu: **0 hết**. Đây là một trường có trong lược đồ mà không ai điền.

Chỗ nguy hiểm không phải việc thiếu một feature — mà là việc một cột hằng số
vẫn **chạy trót lọt** qua mọi phép kiểm và trả về *"không tách được khỏi nền"*.
Câu đó đọc như **đã đo và thấy vô dụng**, trong khi sự thật là **chưa đo được
gì**. Đúng ranh giới mà cả dự án này giữ ở bốn chỗ khác. Nên
``_constant_features`` chặn: cột không có phương sai thì bị loại khỏi phép kiểm
kèm lý do, không được im lặng biến thành một kết quả âm tính.

Kết quả **không** thay thế H3. Nếu feature cơ học không có giá trị gia tăng thì
đó là *bằng chứng* — không phải *chứng minh* — rằng tầng LLM cũng sẽ không: LLM
đọc được thứ mà một cột đếm bài không mã hoá nổi. Nhưng nếu nó **có** giá trị
gia tăng thì H3 đáng đợi, và ta biết điều đó trong một buổi thay vì sáu tháng.
"""
import argparse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from statistics import fmean, median, pstdev
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.macro import calibrate as cal_mod
from src.macro import drivers as drivers_mod
from src.macro import feed as feed_mod
from src.macro import icb, rrg

#: Cửa sổ gom tin, tính bằng ngày lịch.
WINDOW_DAYS = 30

#: Dưới ngần này bài trong cửa sổ thì không đủ để nói gì về ngành đó ở phiên đó.
MIN_POSTS = 3


@dataclass
class NewsFeature:
    """Tin của một ngành tại một phiên — thuần cơ học."""
    code: str
    session: str
    n_posts: int = 0
    n_scored: int = 0                   # số bài FireAnt có gán sắc thái
    mean_sentiment: Optional[float] = None
    volume_z: Optional[float] = None    # khối lượng tin so với chính ngành

    @property
    def measured(self) -> bool:
        return self.n_posts >= MIN_POSTS

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["measured"] = self.measured
        return d


def _sector_posts(conn, code: str, until: str, days: int
                  ) -> List[feed_mod.MacroPost]:
    sd = drivers_mod.for_sector(code)
    since = (datetime.fromisoformat(until) - timedelta(days=days)
             ).strftime("%Y-%m-%d")
    return feed_mod.load_posts(conn, groups=sd.groups or None, since=since,
                              until=until, keywords=sd.keywords or None,
                              limit=500)


def series(code: str, sessions: Sequence[str],
           window: int = WINDOW_DAYS) -> List[NewsFeature]:
    """Feature tin cho một ngành trên danh sách phiên.

    ``volume_z`` chuẩn hoá theo **chính ngành**, không theo cả rổ: một ngành
    lúc nào cũng được nhắc nhiều (Ngân hàng) và một ngành ít khi lên báo
    (Cửa hàng tiện lợi) không so số tuyệt đối với nhau được.
    """
    out: List[NewsFeature] = []
    with feed_mod.connect() as conn:
        for day in sessions:
            posts = _sector_posts(conn, code, day, window)
            f = NewsFeature(code=str(code), session=day, n_posts=len(posts))
            scored = [p.sentiment for p in posts if p.sentiment is not None]
            f.n_scored = len(scored)
            if scored:
                f.mean_sentiment = fmean(scored)
            out.append(f)

    counts = [f.n_posts for f in out]
    if len(counts) >= 8:
        mu, sd = fmean(counts), pstdev(counts)
        if sd > 0:
            for f in out:
                f.volume_z = (f.n_posts - mu) / sd
    return out


# ---------------------------------------------------------------------------
# H3-proxy: feature tin có thêm gì ngoài giá không?
# ---------------------------------------------------------------------------
@dataclass
class Incremental:
    """Giá trị **gia tăng** — luôn đo bên trong nhóm đã phân theo giá.

    Đo một mình thì một feature tin tương quan với giá sẽ trông như có tác
    dụng, trong khi nó chỉ đang lặp lại điều mà cột giá đã nói. Câu đúng là:
    *trong số các ngành cùng ở một trạng thái giá, feature tin có tách chúng ra
    được không?*
    """
    name: str
    bucket: str                          # nhóm giá đang xét
    n_high: int = 0
    n_low: int = 0
    median_high: Optional[float] = None
    median_low: Optional[float] = None
    gap: Optional[float] = None
    p_value: Optional[float] = None
    verdict: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def h3_proxy(codes: Optional[Sequence[str]] = None,
             horizon: int = cal_mod.HORIZON,
             window: int = WINDOW_DAYS,
             draws: int = cal_mod.PLACEBO_DRAWS) -> List[Incremental]:
    """Trong từng góc RRG, feature tin có tách được lợi suất tương lai không?

    Phân tầng theo góc RRG chứ không chạy thô: nếu tin chỉ đi theo giá thì nó
    không thêm gì, và cách duy nhất thấy được điều đó là giữ giá **cố định**
    rồi hỏi tin còn nói gì.
    """
    codes = list(codes or icb.distinct_codes(icb.fetch_tree()))
    rows: Dict[Tuple[str, str], List[Tuple[float, float]]] = {}

    for code in codes:
        fwd = cal_mod.forward_relative(code, horizon)
        if not fwd:
            continue
        quad = {p.date: p.quadrant for p in rrg.load(code)}
        # Chỉ lấy phiên không chồng lấn — cùng lý do với ``calibrate``.
        picks = [(d, v) for d, v in fwd[::horizon] if d in quad]
        if not picks:
            continue
        feats = {f.session: f for f in
                 series(code, [d for d, _ in picks], window)}
        for day, value in picks:
            f = feats.get(day)
            if f is None or not f.measured:
                continue
            for name, x in (("sắc thái", f.mean_sentiment),
                            ("khối lượng tin", f.volume_z)):
                if x is None:
                    continue
                rows.setdefault((name, quad[day]), []).append((x, value))

    dead = _constant_features(rows)
    out: List[Incremental] = []
    for name in sorted(dead):
        out.append(Incremental(
            name=name, bucket="—",
            verdict=f"**chưa đo được** — {dead[name]}"))
    rows = {k: v for k, v in rows.items() if k[0] not in dead}
    for (name, bucket), pairs in sorted(rows.items()):
        inc = Incremental(name=name, bucket=rrg.QUADRANT_VN.get(bucket, bucket))
        if len(pairs) < cal_mod.MIN_INDEPENDENT * 2:
            inc.verdict = f"chỉ {len(pairs)} quan sát độc lập — chưa đủ"
            out.append(inc)
            continue
        pairs.sort(key=lambda t: t[0])
        cut = len(pairs) // 2
        low = [v for _, v in pairs[:cut]]
        high = [v for _, v in pairs[-cut:]]
        pool = [v for _, v in pairs]
        inc.n_low, inc.n_high = len(low), len(high)
        inc.median_low, inc.median_high = median(low), median(high)
        inc.gap = inc.median_high - inc.median_low
        placebo = cal_mod._placebo(pool, len(high), draws)
        inc.p_value = cal_mod._two_sided_p(placebo, inc.median_high)
        inc.verdict = ("tách được khỏi nền" if inc.p_value < cal_mod.ALPHA_ADJUSTED
                       else "không tách được khỏi nền")
        out.append(inc)
    return out


#: Giá trị trội chiếm từ ngần này trở lên thì feature coi như không mang tin.
#:
#: Không dùng "phương sai bằng 0": ``sentiment`` của FireAnt có **đúng 2 bài
#: khác 0 trên 54.000**, đủ để phương sai khác 0 và lọt qua một guard kiểm
#: hằng số tuyệt đối — rồi chạy tiếp thành một kết quả âm tính trông như đã đo.
#: Cái cần chặn là *không có tin*, không phải *hằng số toán học*.
DOMINANT_SHARE = 0.99


def _constant_features(rows: Dict[Tuple[str, str], List[Tuple[float, float]]]
                       ) -> Dict[str, str]:
    """Feature nào không mang tin trên **toàn bộ** quan sát — loại kèm lý do.

    Một cột gần như hằng số chạy trót lọt qua mọi phép kiểm và trả về *"không
    tách được khỏi nền"*. Câu đó đọc như **đã đo và thấy vô dụng**, trong khi
    sự thật là **chưa đo được gì**. Đã xảy ra thật với ``sentiment`` của
    FireAnt: một trường có trong lược đồ mà không ai điền — 53.996/53.998 bài
    mang đúng giá trị 0, và hai bài còn lại đủ để qua mặt phép kiểm phương sai.
    """
    from collections import Counter

    by_name: Dict[str, List[float]] = {}
    for (name, _bucket), pairs in rows.items():
        by_name.setdefault(name, []).extend(x for x, _ in pairs)
    dead: Dict[str, str] = {}
    for name, xs in by_name.items():
        if len(xs) < 2:
            dead[name] = f"chỉ {len(xs)} quan sát"
            continue
        value, count = Counter(xs).most_common(1)[0]
        share = count / len(xs)
        if share >= DOMINANT_SHARE:
            dead[name] = (f"{share:.1%} trong {len(xs)} quan sát mang đúng một "
                          f"giá trị ({value:g}) — nguồn không điền trường này, "
                          f"nên đây là *chưa đo được*, không phải *đã đo và "
                          f"thấy vô dụng*")
    return dead


def format_h3(rows: Sequence[Incremental], horizon: int = cal_mod.HORIZON) -> str:
    lines = [f"# H3-proxy — feature tin cơ học, cửa sổ {horizon} phiên", "",
             "Feature **backfill được mà không dính nhìn trước**, đo **bên "
             "trong từng góc RRG** — giữ giá cố định rồi hỏi tin còn nói thêm "
             "gì. Feature nào là cột hằng số thì bị loại kèm lý do, **không** "
             "được im lặng biến thành một kết quả âm tính.", "",
             "| Feature | Góc RRG | n cao/thấp | Trung vị cao | Trung vị thấp | Chênh | p | Kết luận |",
             "|---|---|---:|---:|---:|---:|---:|---|"]
    for r in rows:
        def pct(v):
            return "—" if v is None else f"{v * 100:+.2f}%"
        p = "—" if r.p_value is None else f"{r.p_value:.3f}"
        n = f"{r.n_high}/{r.n_low}" if r.n_high else "—"
        lines.append(f"| {r.name} | {r.bucket} | {n} | {pct(r.median_high)} | "
                     f"{pct(r.median_low)} | {pct(r.gap)} | {p} | {r.verdict} |")

    ok = [r for r in rows if r.p_value is not None
          and r.p_value < cal_mod.ALPHA_ADJUSTED]
    lines += ["", "---", ""]
    if ok:
        lines.append(
            f"**{len(ok)} nhóm tách được khỏi nền** ở ngưỡng đã hiệu chỉnh "
            f"({cal_mod.ALPHA_ADJUSTED:.4f}). Feature tin cơ học có giá trị gia "
            f"tăng → H3 với điểm LLM đáng đợi.")
    else:
        lines.append(
            f"**Không nhóm nào tách được khỏi nền** ở ngưỡng đã hiệu chỉnh "
            f"({cal_mod.ALPHA_ADJUSTED:.4f}).")
    dead = [r for r in rows if r.verdict.startswith("**chưa đo được**")]
    if dead:
        lines += ["",
                  f"⚠️ **{len(dead)} feature không đo được** (xem cột "
                  f"cuối). Chúng bị **loại khỏi** phép kiểm chứ không bị "
                  f"tính là kết quả âm tính — một cột hằng số vẫn chạy "
                  f"trót lọt và trả về *không tách được khỏi nền*, câu đó "
                  f"đọc như *đã đo và thấy vô dụng*."]
    lines += ["",
              "⚠️ Kết quả này **không thay thế H3**, và giờ còn yếu hơn "
              "dự tính ban đầu: kế hoạch là đo **hai** feature, nhưng sắc "
              "thái của FireAnt hoá ra là trường rỗng, nên chỉ còn **khối "
              "lượng tin** — một phép đếm bài, không đọc nội dung. Nó "
              "không mã hoá nổi thứ §9.9 của plan tin tức nêu: *lãi ròng "
              "giảm 50% nhưng vượt 20% kế hoạch năm*. Nên âm tính ở đây "
              "là **bằng chứng yếu**, không phải **chứng minh**, rằng "
              "tầng LLM cũng sẽ không thêm gì — và nó không thay được "
              "việc đợi H3 thật."]
    return "\n".join(lines)


def _main() -> None:
    ap = argparse.ArgumentParser(description="H3-proxy: feature tin cơ học")
    ap.add_argument("--horizon", type=int, default=cal_mod.HORIZON)
    ap.add_argument("--window", type=int, default=WINDOW_DAYS)
    ap.add_argument("--codes", default="")
    args = ap.parse_args()
    codes = [c for c in args.codes.split(",") if c.strip()] or None
    print(format_h3(h3_proxy(codes, args.horizon, args.window), args.horizon))


if __name__ == "__main__":
    _main()
