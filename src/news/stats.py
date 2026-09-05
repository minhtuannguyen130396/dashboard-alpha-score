"""Hiệu chuẩn base rate — biến ý kiến thành thống kê. GĐ8 của kế hoạch.

Một event study đơn lẻ là một giai thoại. "Giao dịch nội bộ mua thì giá thường
chạy" chỉ trở thành phát biểu kiểm chứng được khi có phân phối phía sau, và repo
này có sẵn nguyên liệu hiếm: 80 mã × 16 năm giá, đủ để chạy lại phép đo trên
*mọi* lần sự kiện loại đó từng xảy ra.

Ba kỷ luật bắt buộc, mỗi cái chống một cách nói dối bằng số:

* **Luôn in ``n``.** ``n = 6`` thì đừng phát biểu gì cả. Con số trung vị đẹp đẽ
  dựng từ sáu quan sát là thứ nguy hiểm hơn không có số nào.
* **Trung vị + tứ phân vị, không phải trung bình.** Phân phối lợi suất có đuôi
  dày; một sự kiện +80% kéo trung bình lên và làm cả nhóm trông có lãi.
* **Tách phiên trần/sàn ra.** Phép đo ở đó bị cắt cụt (biên độ thật lớn hơn số
  đo được), nên trộn vào là **đánh giá thấp có hệ thống** đúng những sự kiện
  mạnh nhất — sai lệch theo một chiều, không phải nhiễu ngẫu nhiên.
"""
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from src.news import match as match_mod
from src.news import reaction as reaction_mod
from src.news import store
from src.news.models import DIRECTION_VN, PURCHASED, SOLD

#: Dưới ngưỡng này thì mọi con số tổng hợp bị coi là không phát biểu được.
MIN_N = 20


def _quantile(values: Sequence[float], q: float) -> Optional[float]:
    """Phân vị kiểu nội suy tuyến tính. Không kéo numpy vào chỉ vì việc này."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = q * (len(ordered) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    frac = pos - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


@dataclass
class Distribution:
    """Phân phối của một cửa sổ đo, trên một nhóm sự kiện."""
    n: int = 0
    median: Optional[float] = None
    p25: Optional[float] = None
    p75: Optional[float] = None
    pct_positive: Optional[float] = None

    @classmethod
    def of(cls, values: Sequence[float]) -> "Distribution":
        vals = [v for v in values if v is not None]
        if not vals:
            return cls()
        return cls(
            n=len(vals),
            median=round(_quantile(vals, 0.5), 6),
            p25=round(_quantile(vals, 0.25), 6),
            p75=round(_quantile(vals, 0.75), 6),
            pct_positive=round(sum(1 for v in vals if v > 0) / len(vals), 4),
        )


@dataclass
class BucketStats:
    """Thống kê cho một nhóm sự kiện (ví dụ: người nội bộ MUA, thực hiện đủ)."""
    label: str
    n_events: int = 0
    n_limit_excluded: int = 0
    n_matched_t0: int = 0        # số ca dùng ngày công bố THẬT
    n_proxy_t0: int = 0          # số ca phải lùi về startDate
    car_pre: Distribution = field(default_factory=Distribution)
    car_immediate: Distribution = field(default_factory=Distribution)
    car_post: Distribution = field(default_factory=Distribution)
    volume_ratio: Distribution = field(default_factory=Distribution)

    @property
    def reportable(self) -> bool:
        """Đủ quan sát để phát biểu chưa. Chưa đủ thì im, đừng nói cho có."""
        return self.n_events >= MIN_N

    def to_dict(self) -> dict:
        d = asdict(self)
        d["reportable"] = self.reportable
        return d


def _bucket_label(row: dict) -> Optional[str]:
    """Xếp một giao dịch vào nhóm. ``None`` = không xếp được, bỏ qua.

    Nhóm chia theo ba trục **rời nhau** chứ không gộp thành một điểm: ai giao
    dịch (nội bộ / cổ đông lớn), chiều nào, và có làm đúng như đăng ký không.
    Trục thứ ba là thứ ít nơi nào đo, và là chỗ có thông tin.
    """
    direction = row.get("direction")
    if direction not in (PURCHASED, SOLD):
        return None                       # quyền mua: cơ chế khác, để riêng
    who = "nội bộ" if row.get("position") else "cổ đông lớn"
    verb = DIRECTION_VN[direction]

    reg, ex = row.get("registered_volume"), row.get("execution_volume")
    if not reg:
        done = "không rõ đăng ký"
    elif ex is None:
        done = "chưa có kết quả"
    else:
        rate = ex / reg
        if rate <= 0:
            done = "không thực hiện"
        elif rate >= 0.99:
            done = "thực hiện đủ"
        else:
            done = "thực hiện một phần"
    return f"{who} · {verb} · {done}"


def collect(symbols: Sequence[str], db_path=None,
            benchmark: str = reaction_mod.DEFAULT_BENCHMARK,
            exclude_limit: bool = True,
            progress: Optional[Callable[[str, int, int], None]] = None,
            use_matched_t0: bool = True,
            only_matched: bool = False
            ) -> Tuple[Dict[str, BucketStats], List[dict]]:
    """Chạy event study cho mọi giao dịch của ``symbols``, gom theo nhóm.

    ``use_matched_t0`` ghép giao dịch với bài công bố (``match.py``) để lấy
    **ngày tin ra thị trường** thay cho ``startDate``. Khoảng lệch giữa hai mốc
    này đo được là 3–6 ngày trên các ca đã kiểm — đủ để đẩy phản ứng thật ra
    khỏi cửa sổ ``t0…t+1`` và vào vùng bị gọi nhầm là "rò rỉ trước tin".

    ``only_matched`` giữ **đúng** những ca có ngày công bố thật. Tập này nhỏ hơn
    nhiều nhưng sạch; trộn nó với tập dùng mốc thay thế là pha loãng phần đo
    đúng bằng phần đo lệch, rồi kết luận trên hỗn hợp đó.

    Trả ``(thống kê theo nhóm, danh sách bản ghi thô)``. Bản ghi thô được trả
    cùng để soi lại được từng ca — một bảng thống kê không lần ngược về được
    từng quan sát là bảng không kiểm chứng được.
    """
    buckets: Dict[str, BucketStats] = {}
    raw: List[dict] = []
    acc: Dict[str, Dict[str, List[float]]] = {}

    with store.connect(db_path) as conn:
        for i, sym in enumerate(symbols, 1):
            if progress:
                progress(sym, i, len(symbols))
            rows = store.load_holder_transactions(conn, sym)
            matches: Dict[int, Any] = {}
            if use_matched_t0 and rows:
                posts = store.load_posts(conn, sym, insider_only=True, limit=2000)
                if posts:
                    matches = match_mod.match_symbol(rows, posts)
            for row in rows:
                label = _bucket_label(row)
                if not label:
                    continue
                m = matches.get(row["transaction_id"])
                if only_matched and m is None:
                    continue
                if use_matched_t0:
                    t0, t0_source = match_mod.effective_t0(row, m)
                else:
                    t0 = str(row.get("start_date") or row.get("execution_date") or "")[:10]
                    t0_source = "start_date_proxy"
                if not t0:
                    continue
                res = reaction_mod.measure(sym, t0, benchmark=benchmark)
                if res.beta is None or res.car_immediate is None:
                    continue

                b = buckets.setdefault(label, BucketStats(label=label))
                if exclude_limit and res.limit_hit:
                    b.n_limit_excluded += 1
                    continue

                b.n_events += 1
                if t0_source == "post_date":
                    b.n_matched_t0 += 1
                else:
                    b.n_proxy_t0 += 1
                slot = acc.setdefault(label, {"pre": [], "imm": [], "post": [], "vol": []})
                slot["pre"].append(res.car_pre)
                slot["imm"].append(res.car_immediate)
                slot["post"].append(res.car_post)
                slot["vol"].append(res.volume_ratio)

                raw.append({
                    "symbol": sym, "label": label, "name": row.get("name"),
                    "position": row.get("position"), "t0": res.t0_actual,
                    "t0_source": t0_source,
                    "matched_post": m.to_dict() if m is not None else None,
                    "car_pre": res.car_pre, "car_immediate": res.car_immediate,
                    "car_post": res.car_post, "volume_ratio": res.volume_ratio,
                    "limit_hit": res.limit_hit,
                })

    for label, slot in acc.items():
        b = buckets[label]
        b.car_pre = Distribution.of(slot["pre"])
        b.car_immediate = Distribution.of(slot["imm"])
        b.car_post = Distribution.of(slot["post"])
        b.volume_ratio = Distribution.of(slot["vol"])
    return buckets, raw


# --- Render ---------------------------------------------------------------

def _pct(v: Optional[float]) -> str:
    return "—" if v is None else f"{v * 100:+.1f}%"


def format_stats(buckets: Dict[str, BucketStats]) -> str:
    """Bảng base rate. Nhóm chưa đủ ``n`` bị tách riêng chứ không in số."""
    if not buckets:
        return "Chưa có sự kiện nào đo được."

    ready = sorted((b for b in buckets.values() if b.reportable),
                   key=lambda b: -b.n_events)
    thin = sorted((b for b in buckets.values() if not b.reportable),
                  key=lambda b: -b.n_events)

    out = ["## Base rate — phản ứng giá theo nhóm giao dịch", ""]
    if ready:
        out += [
            "| Nhóm | n | CAR trước (trung vị) | Tức thì | Trôi sau | % dương (tức thì) |",
            "|---|---|---|---|---|---|",
        ]
        for b in ready:
            out.append(
                f"| {b.label} | {b.n_events} | {_pct(b.car_pre.median)} "
                f"| {_pct(b.car_immediate.median)} | {_pct(b.car_post.median)} "
                f"| {b.car_immediate.pct_positive * 100:.0f}% |"
                if b.car_immediate.pct_positive is not None else
                f"| {b.label} | {b.n_events} | — | — | — | — |"
            )
        out.append("")
        out.append("Khoảng tứ phân vị (cửa sổ tức thì):")
        out.append("")
        for b in ready:
            out.append(f"- **{b.label}** (n={b.n_events}): "
                       f"p25 {_pct(b.car_immediate.p25)} · "
                       f"trung vị {_pct(b.car_immediate.median)} · "
                       f"p75 {_pct(b.car_immediate.p75)}")
    else:
        out.append(f"_Chưa nhóm nào đạt ngưỡng n ≥ {MIN_N} để phát biểu._")

    if thin:
        out += ["", f"### Chưa đủ quan sát (n < {MIN_N}) — không phát biểu", ""]
        for b in thin:
            out.append(f"- {b.label}: n={b.n_events}")

    matched = sum(b.n_matched_t0 for b in buckets.values())
    proxy = sum(b.n_proxy_t0 for b in buckets.values())
    if matched or proxy:
        total = matched + proxy
        out += ["", f"**Mốc `t0`:** {matched}/{total} ca ({matched / total * 100:.0f}%) "
                    f"dùng **ngày công bố thật** ghép từ bài viết; "
                    f"{proxy} ca lùi về `startDate` làm mốc thay thế."]
        if proxy > matched:
            out.append("⚠️ Phần lớn vẫn là mốc thay thế — công bố đi trước `startDate` "
                       "trung vị 6 ngày, nên những ca đó có phản ứng thật nằm lệch vào "
                       "cửa sổ *trước sự kiện*, không phải cửa sổ tức thì.")

    excluded = sum(b.n_limit_excluded for b in buckets.values())
    if excluded:
        out += ["", f"_{excluded} sự kiện có phiên trần/sàn đã bị loại khỏi thống kê: "
                    "phép đo ở đó bị cắt cụt nên trộn vào sẽ đánh giá thấp có hệ thống "
                    "đúng những sự kiện mạnh nhất._"]
    out += ["", "_Số liệu thống kê, không phải khuyến nghị đầu tư._"]
    return "\n".join(out)

def placebo(symbols: Sequence[str], n_samples: int = 400,
            start_year: int = 2018, seed: int = 42,
            benchmark: str = reaction_mod.DEFAULT_BENCHMARK) -> Distribution:
    """Phân phối abnormal return trên những ngày **ngẫu nhiên** — nhóm đối chứng.

    Đây là phép kiểm chứng bắt buộc phải chạy trước khi tin bất kỳ con số nào ở
    ``collect()``. Nếu nhóm sự kiện thật cho trung vị −0,4% mà ngày ngẫu nhiên
    cũng cho −0,2% với cùng khoảng tứ phân vị, thì "hiệu ứng" đo được **không
    phải hiệu ứng** — nó là nền.

    Nền đó không bằng 0 vì một lý do có thật: VNINDEX là chỉ số **trọng số vốn
    hoá**, còn rổ đo là 79 mã riêng lẻ đều tay. Vài mã vốn hoá lớn kéo chỉ số,
    nên abnormal return trung vị của một mã bất kỳ lệch nhẹ về âm một cách máy
    móc. Biết nền ở đâu thì mới đọc được phần nhô lên khỏi nền.
    """
    import random
    from datetime import datetime, timedelta

    rng = random.Random(seed)
    span_days = (datetime.now() - datetime(start_year, 1, 1)).days - 40
    vals: List[float] = []
    for _ in range(n_samples):
        sym = rng.choice(list(symbols))
        day = datetime(start_year, 1, 1) + timedelta(days=rng.randint(0, span_days))
        res = reaction_mod.measure(sym, day.strftime("%Y-%m-%d"), benchmark=benchmark)
        if res.car_immediate is not None and not res.limit_hit:
            vals.append(res.car_immediate)
    return Distribution.of(vals)


def format_with_placebo(buckets: Dict[str, BucketStats],
                        baseline: Distribution) -> str:
    """Bảng base rate kèm nhóm đối chứng, và **cảnh báo khi không tách khỏi nền**."""
    out = [format_stats(buckets), "", "### Nhóm đối chứng — ngày ngẫu nhiên", ""]
    if baseline.n == 0:
        out.append("_Chưa chạy được nhóm đối chứng._")
        return "\n".join(out)
    out += [
        f"Trên **{baseline.n}** ngày ngẫu nhiên (không phải ngày sự kiện): "
        f"trung vị **{_pct(baseline.median)}**, "
        f"p25 {_pct(baseline.p25)} · p75 {_pct(baseline.p75)}, "
        f"{baseline.pct_positive * 100:.0f}% dương.",
        "",
    ]
    indistinct = [
        b.label for b in buckets.values()
        if b.reportable and b.car_immediate.median is not None
        and baseline.median is not None
        and abs(b.car_immediate.median - baseline.median) < 0.005
    ]
    if indistinct:
        out += [
            "⚠️ **Các nhóm sau không tách khỏi nền** (lệch trung vị < 0,5đ%) — "
            "con số của chúng không nói lên điều gì về sự kiện:",
            "",
        ] + [f"- {label}" for label in indistinct]
    return "\n".join(out)
