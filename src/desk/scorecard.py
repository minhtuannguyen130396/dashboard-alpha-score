"""Bảng điểm của chính bàn — thứ không CTCK nào công bố.

Replay toàn bộ sổ đúng cách ``forecast.evaluate()`` đang làm: file trên đĩa chỉ
là cache, trạng thái tính lại từ giá. Năm luật, mỗi luật chặn một cách làm bảng
điểm đẹp lên mà không cần đúng hơn:

1. **Vào lệnh ở giá đóng cửa phiên SAU phiên ra quan điểm** (§7.6). Lúc viết
   thì phiên đó đã chốt rồi; dùng chính giá đóng cửa ấy là mua ở một mức không
   ai mua được.
2. **Trừ chi phí.** Phí + thuế + trượt giá. Bỏ ba khoản này ra thì mọi chiến
   lược xoay vòng nhanh đều thắng, và nó thắng bằng số không tồn tại. Bảng in
   **cả hai** cột — gộp trước phí là giấu chi phí, chỉ in sau phí là không so
   được với các phép đo khác trong repo.
3. **Lợi suất luôn TƯƠNG ĐỐI so với VNINDEX.** Một bàn đúng 65% trong một thị
   trường tăng 20% chưa chứng minh được gì.
4. **So với nền placebo**, không so với 0 — mã bất kỳ, cùng phiên vào, cùng
   thời gian nắm giữ.
5. **Dưới ngưỡng quan sát độc lập thì KHÔNG phát biểu.** Câu "chưa đủ để nói
   bàn này đúng hay sai" phải in ra, vì một tỷ lệ 70% trên bảy quan sát đọc
   giống hệt một tỷ lệ 70% trên bảy trăm.

Quan điểm **chưa đủ hạn** vẫn được đo tới phiên gần nhất, nhưng mang
``complete=False`` và **không vào** phần thống kê: gộp chúng là đọc nửa chừng
của những vị thế đang thắng nhiều hơn.
"""
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime
from statistics import median
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.desk import ledger as ledger_mod
from src.desk.ledger import Entry, Standing
from src.ta.loader import load_prices

BENCHMARK = "VNINDEX"

#: Chi phí vòng (mua + bán), tính bằng %: phí hai chiều + thuế bán 0,1% +
#: trượt giá. Đề xuất khởi điểm, không phải số đo.
ROUND_TRIP_COST_PCT = 0.45

#: Tư thế nào kỳ vọng giá lên, tư thế nào kỳ vọng xuống. ``None`` = không có
#: chiều, nên **không** tính vào tỷ lệ đúng — một nhận định trung lập không sai
#: được theo chiều nào cả, và đếm nó là pha loãng bảng điểm.
STANCE_DIRECTION = {"tang": 1, "tang_cho": 1, "giam": -1,
                    "trung_lap": None, "dung_ngoai": None}

#: Dưới ngần này quan sát **độc lập** thì bảng điểm chưa nói được gì.
MIN_INDEPENDENT = 50

PLACEBO_DRAWS = 400

NOT_ENOUGH = ("**Chưa đủ để nói bàn này đúng hay sai.** Một tỷ lệ đúng trên vài "
              "chục quan sát đọc giống hệt một tỷ lệ trên vài trăm, nên con số "
              "dưới đây là *mô tả sổ đã chạy tới đâu*, không phải một kết luận "
              "về chất lượng nhận định.")


@dataclass
class Outcome:
    entry_id: str
    kind: str
    subject: str
    session: str
    stance: str
    confidence: str
    horizon_sessions: int
    start_date: Optional[str] = None
    start_price: Optional[float] = None
    end_date: Optional[str] = None
    end_price: Optional[float] = None
    sessions_used: int = 0
    complete: bool = False
    raw_return: Optional[float] = None        # %
    rel_return: Optional[float] = None        # % so với VNINDEX
    rel_return_net: Optional[float] = None    # % sau chi phí vòng
    invalidated_on: Optional[str] = None
    directional_hit: Optional[bool] = None
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _series(symbol: str, start: str, as_of: Optional[datetime]
            ) -> List[Tuple[str, float]]:
    end = as_of or datetime.now()
    bars = load_prices(symbol, datetime.strptime(start, "%Y-%m-%d"), end)
    return [(b.date.strftime("%Y-%m-%d"), b.priceClose) for b in bars
            if b.priceClose]


def evaluate(entry: Entry, as_of: Optional[datetime] = None,
             bench: Optional[List[Tuple[str, float]]] = None) -> Outcome:
    """Một quan điểm → kết quả đo được. Không phán quyết, chỉ số."""
    out = Outcome(entry_id=entry.entry_id, kind=entry.kind, subject=entry.subject,
                  session=entry.session, stance=entry.stance,
                  confidence=entry.confidence,
                  horizon_sessions=entry.horizon_sessions)
    if entry.kind not in ("stock", "market", "sector"):
        out.note = "cấp sổ — đo ở `book_performance`, không đo từng dòng"
        return out

    symbol = BENCHMARK if entry.kind == "market" else entry.subject
    rows = _series(symbol, entry.session, as_of)
    # Vào lệnh ở phiên SAU phiên ra quan điểm.
    after = [r for r in rows if r[0] > entry.session]
    if not after:
        out.note = "chưa có phiên nào sau phiên ra quan điểm — **chưa đo được**"
        return out

    out.start_date, out.start_price = after[0]
    window = after[:entry.horizon_sessions]
    out.end_date, out.end_price = window[-1]
    out.sessions_used = len(window)
    out.complete = len(window) >= entry.horizon_sessions

    if entry.invalidation_level:
        direction = STANCE_DIRECTION.get(entry.stance)
        for day, price in window:
            broken = (price < entry.invalidation_level if direction == 1
                      else price > entry.invalidation_level)
            if direction is not None and broken:
                out.invalidated_on = day
                out.end_date, out.end_price = day, price
                out.sessions_used = window.index((day, price)) + 1
                break

    out.raw_return = round((out.end_price / out.start_price - 1) * 100, 2)

    bench_rows = bench if bench is not None else _series(BENCHMARK, entry.session, as_of)
    bmap = dict(bench_rows)
    b0, b1 = bmap.get(out.start_date), bmap.get(out.end_date)
    if b0 and b1:
        market = (b1 / b0 - 1) * 100
        out.rel_return = round(out.raw_return - market, 2)
    else:
        out.rel_return = None
        out.note = "thiếu phiên chỉ số để so tương đối"

    if out.rel_return is not None:
        cost = 0.0 if entry.kind == "market" else ROUND_TRIP_COST_PCT
        out.rel_return_net = round(out.rel_return - cost, 2)
        direction = STANCE_DIRECTION.get(entry.stance)
        if direction is not None:
            out.directional_hit = (out.rel_return * direction) > 0
    return out


# ---------------------------------------------------------------------------
@dataclass
class Group:
    name: str
    n: int = 0
    hit_rate: Optional[float] = None
    median_rel: Optional[float] = None
    median_rel_net: Optional[float] = None
    placebo_median: Optional[float] = None
    edge: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Scorecard:
    as_of: str
    outcomes: List[Outcome] = field(default_factory=list)
    by_kind: List[Group] = field(default_factory=list)
    by_confidence: List[Group] = field(default_factory=list)
    n_complete: int = 0
    enough: bool = False
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"as_of": self.as_of, "n_complete": self.n_complete,
                "enough": self.enough, "note": self.note,
                "outcomes": [o.to_dict() for o in self.outcomes],
                "by_kind": [g.to_dict() for g in self.by_kind],
                "by_confidence": [g.to_dict() for g in self.by_confidence]}


def _placebo_pool(outcomes: Sequence[Outcome], as_of: Optional[datetime],
                  draws: int, seed: int = 20260920) -> List[float]:
    """Nền: mã **bất kỳ trong rổ**, cùng phiên vào, cùng thời gian nắm giữ.

    Không so với 0 — phân phối lợi suất tương đối không có kỳ vọng bằng 0, và
    một bàn chỉ chọn toàn mã lớn sẽ có nền khác một bàn chọn mã nhỏ.
    """
    from src.ta.loader import resolve_universe
    pool = resolve_universe(None)
    if not pool or not outcomes:
        return []
    rng = random.Random(seed)
    bench = _series(BENCHMARK, min(o.session for o in outcomes), as_of)
    bmap = dict(bench)
    out: List[float] = []
    for _ in range(draws):
        ref = rng.choice(list(outcomes))
        symbol = rng.choice(pool)
        rows = _series(symbol, ref.session, as_of)
        after = [r for r in rows if r[0] > ref.session][:ref.horizon_sessions]
        if len(after) < 2:
            continue
        b0, b1 = bmap.get(after[0][0]), bmap.get(after[-1][0])
        if not b0 or not b1:
            continue
        raw = (after[-1][1] / after[0][1] - 1) * 100
        out.append(raw - (b1 / b0 - 1) * 100)
    return sorted(out)


def _group(name: str, rows: Sequence[Outcome],
           placebo: Sequence[float]) -> Group:
    usable = [o for o in rows if o.rel_return is not None]
    g = Group(name=name, n=len(usable))
    if not usable:
        return g
    directional = [o for o in usable if o.directional_hit is not None]
    if directional:
        g.hit_rate = round(sum(1 for o in directional if o.directional_hit)
                           / len(directional) * 100, 1)
    g.median_rel = round(median(o.rel_return for o in usable), 2)
    nets = [o.rel_return_net for o in usable if o.rel_return_net is not None]
    if nets:
        g.median_rel_net = round(median(nets), 2)
    if placebo:
        g.placebo_median = round(median(placebo), 2)
        g.edge = round(g.median_rel - g.placebo_median, 2)
    return g


def build(as_of: Optional[datetime] = None,
          standings: Optional[Sequence[Standing]] = None,
          root=None, draws: int = PLACEBO_DRAWS) -> Scorecard:
    """Bảng điểm tới ``as_of``. Chỉ quan điểm **đã đủ hạn** vào thống kê."""
    rows = list(standings if standings is not None
                else ledger_mod.standings(as_of=as_of, root=root))
    day = (as_of or datetime.now()).strftime("%Y-%m-%d")
    card = Scorecard(as_of=day)
    if not rows:
        card.note = ("Sổ trống — **chưa có gì để chấm**. Đây là *chưa ai viết*, "
                     "không phải *bàn này chưa đúng lần nào*.")
        return card

    bench = _series(BENCHMARK, min(s.entry.session for s in rows), as_of)
    card.outcomes = [evaluate(s.entry, as_of, bench) for s in rows]
    complete = [o for o in card.outcomes if o.complete or o.invalidated_on]
    card.n_complete = len(complete)
    card.enough = card.n_complete >= MIN_INDEPENDENT

    placebo = _placebo_pool(complete, as_of, draws) if complete else []
    kinds = sorted({o.kind for o in complete})
    card.by_kind = [_group(k, [o for o in complete if o.kind == k], placebo)
                    for k in kinds]
    confs = sorted({o.confidence for o in complete})
    card.by_confidence = [
        _group(c, [o for o in complete if o.confidence == c], placebo)
        for c in confs]

    pending = len(card.outcomes) - card.n_complete
    card.note = ("" if card.enough else NOT_ENOUGH)
    if pending:
        card.note += (f" · {pending} quan điểm **chưa đủ hạn** — đo tới phiên gần "
                      "nhất nhưng không vào thống kê.")
    return card


# ---------------------------------------------------------------------------
@dataclass
class BookRun:
    """Kết quả của sổ mô phỏng: có trọng số, có chi phí, so với chỉ số."""
    as_of: str
    n_positions: int = 0
    invested_pct: float = 0.0
    cash_pct: float = 100.0
    weighted_rel: Optional[float] = None       # % so với VNINDEX, đã nhân trọng số
    weighted_rel_net: Optional[float] = None
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def book_performance(as_of: Optional[datetime] = None, root=None) -> BookRun:
    """Sổ đang mở đã đi được bao xa — **tính cả phần tiền mặt**.

    Tiền mặt là một vị thế: một sổ 30% cổ phiếu trong nhịp giảm 10% chỉ mất 3%,
    và bỏ nó ra khỏi phép tính là xoá đúng phần quyết định nhất của phân bổ.
    """
    from src.desk import book as book_mod
    b = book_mod.build(as_of=as_of, root=root)
    run = BookRun(as_of=b.as_of, n_positions=len(b.positions),
                  invested_pct=b.invested_pct, cash_pct=b.cash_pct)
    if not b.positions:
        run.note = "sổ toàn tiền mặt — không có gì để đo"
        return run

    entries = {s.entry.entry_id: s.entry
               for s in ledger_mod.open_entries(kind="stock", as_of=as_of, root=root)}
    bench = _series(BENCHMARK,
                    min(e.session for e in entries.values()), as_of) if entries else []
    total_w, acc, acc_net = 0.0, 0.0, 0.0
    for pos in b.positions:
        entry = entries.get(pos.entry_id)
        if entry is None:
            continue
        out = evaluate(entry, as_of, bench)
        if out.rel_return is None:
            continue
        total_w += pos.weight_pct
        acc += pos.weight_pct * out.rel_return
        acc_net += pos.weight_pct * (out.rel_return_net or out.rel_return)
    if total_w <= 0:
        run.note = "chưa đo được vị thế nào"
        return run
    run.weighted_rel = round(acc / 100.0, 2)
    run.weighted_rel_net = round(acc_net / 100.0, 2)
    run.note = (f"Đóng góp tính trên tỷ trọng thật ({total_w:.0f}% sổ đo được); "
                f"phần tiền mặt {b.cash_pct:g}% đóng góp 0 theo định nghĩa.")
    return run
