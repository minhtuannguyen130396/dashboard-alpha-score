"""Hiệu chuẩn định giá — V1: rẻ so với chính mình có dẫn được gì không.

Cùng bộ máy với ``calibrate_flows`` (dùng lại ``evaluate_buckets``, nền placebo,
mẫu không chồng lấn, ngưỡng Bonferroni), khác đúng hai chỗ — và cả hai chỗ khác
đều là chỗ dễ tự lừa mình nhất của một phép đo định giá:

1. **Phân vị phải tính THEO NHỮNG GÌ BIẾT ĐƯỢC TẠI t, không theo cả chuỗi.**
   Xếp hạng P/E hôm 03/2021 trong toàn bộ lịch sử 2016→2026 là dùng giá của
   2024 để nói rằng năm 2021 "rẻ". Sai lệch này đi **một chiều**: nó luôn làm
   chiến lược mua rẻ trông thông minh hơn thực tế, vì đáy định giá chỉ *được
   biết là đáy* sau khi mọi thứ đã xảy ra. Nên ``expanding_ranks`` chỉ nhìn về
   phía sau, và bỏ hẳn quãng đầu chưa đủ lịch sử.
2. **Cửa sổ dài hơn dòng tiền.** Định giá là lập luận nhiều quý, không phải
   nhiều phiên; 20 phiên ở đây gần như chỉ đo nhiễu. Mặc định 60 và 120 phiên.

Ba điều giữ nguyên vì chúng không phụ thuộc chỉ số nào: lợi suất luôn **tương
đối so với VNINDEX**, mẫu **không chồng lấn trong từng mã**, và kết quả âm tính
là **kết luận**, không phải chỗ chưa đo.
"""
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.desk import valuation as val_mod
from src.desk.calibrate_flows import (Observation, _benchmark_map, _independent,
                                      _percentile_ranks, evaluate_buckets,
                                      PLACEBO_DRAWS)
from src.macro.calibrate import Bucket, Hypothesis
from src.ta.loader import PROJECT_ROOT, resolve_universe

RESULT_DIR = PROJECT_ROOT / "desk" / "calibration"
RESULT_NAME = "valuation.json"

#: Cửa sổ dự báo, tính bằng phiên. Định giá là lập luận nhiều quý.
HORIZONS: Tuple[int, ...] = (60, 120)

#: Phải có ngần này phiên lịch sử thì một phân vị mới có nghĩa.
MIN_HISTORY = 250

METRICS = {
    "pe": ("V1", "P/E thấp so với chính lịch sử của mã (phân vị tính tại t)"),
    "pb": ("V2", "P/B thấp so với chính lịch sử của mã (phân vị tính tại t)"),
}

#: 2 chỉ số × 2 cửa sổ × 2 đuôi.
N_TESTS = len(METRICS) * len(HORIZONS) * 2
ALPHA = 0.05
ALPHA_BONFERRONI = ALPHA / N_TESTS

NO_CALIBRATION = ("⚠️ Dải định giá **chưa hiệu chuẩn** — phân vị dưới đây là phép "
                  "đo vị trí, không phải dự báo. Chạy `desk_calibrate_valuation` "
                  "để biết nó tách được khỏi nền hay không.")
NOT_PREDICTIVE = ("Hiệu chuẩn đã chạy và **không giả thuyết nào đạt**: rẻ so với "
                  "chính mình là một mô tả, không phải tín hiệu. Đây là kết luận "
                  "của dữ liệu, không phải chỗ chưa đo.")


def expanding_ranks(values: Sequence[Optional[float]],
                    min_history: int = MIN_HISTORY) -> List[Optional[float]]:
    """Phân vị của từng giá trị **trong quãng trước nó**, không dùng tương lai.

    Cài bằng vòng lặp thẳng: chuỗi mỗi mã vài nghìn điểm, và một phép chèn nhị
    phân ở đây tiết kiệm được vài giây nhưng thêm một chỗ sai im lặng.
    """
    out: List[Optional[float]] = []
    seen: List[float] = []
    for v in values:
        if v is None:
            out.append(None)
            continue
        if len(seen) >= min_history:
            below = sum(1 for s in seen if s < v)
            out.append(below / len(seen))
        else:
            out.append(None)
        seen.append(v)
    return out


def symbol_observations(symbol: str, metric: str, horizon: int,
                        bench: Dict[str, float],
                        as_of: Optional[datetime] = None,
                        series: Optional[val_mod.ValuationSeries] = None
                        ) -> List[Observation]:
    """Quan sát của một mã: phân vị định giá tại t → lợi suất tương đối t+h."""
    sym = symbol.strip().upper()
    series = series or val_mod.build(sym, as_of=as_of, years=12, allow_fetch=False)
    if series.is_empty:
        return []
    points = [p for p in series.points if p.date in bench and bench[p.date] > 0]
    if len(points) <= horizon:
        return []

    raw = [getattr(p, metric) for p in points]
    ranks = expanding_ranks(raw)
    rel = [p.price / bench[p.date] for p in points]

    out: List[Observation] = []
    for i in range(len(points) - horizon):
        if ranks[i] is None or rel[i] <= 0:
            continue
        out.append(Observation(date=points[i].date, value=raw[i] or 0.0,
                               rel=rel[i + horizon] / rel[i] - 1.0,
                               symbol=sym, pct_rank=ranks[i]))
    return out


# ---------------------------------------------------------------------------
@dataclass
class ValuationCalibration:
    generated: str
    universe: str
    n_symbols: int
    hypotheses: List[Hypothesis] = field(default_factory=list)
    n_tests: int = N_TESTS
    alpha: float = ALPHA_BONFERRONI
    note: str = ""

    @property
    def any_passed(self) -> bool:
        return any(h.passed for h in self.hypotheses)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["hypotheses"] = [h.to_dict() for h in self.hypotheses]
        d["any_passed"] = self.any_passed
        return d


#: Nhiều lần rút hơn dòng tiền vì nhóm ở đây nhỏ hơn hẳn (vài trăm quan sát
#: thay vì vài nghìn), nên phép hoán vị rẻ — và vì đuôi của V2 rơi đúng sát sàn
#: phân giải ở lượt chạy đầu.
DRAWS = 2000


def run(universe: Optional[str] = None, as_of: Optional[datetime] = None,
        horizons: Sequence[int] = HORIZONS, draws: int = DRAWS
        ) -> ValuationCalibration:
    symbols = resolve_universe(universe)
    bench = _benchmark_map(as_of)
    cached: Dict[str, val_mod.ValuationSeries] = {}
    for sym in symbols:
        try:
            s = val_mod.build(sym, as_of=as_of, years=12, allow_fetch=False)
        except Exception:                                      # noqa: BLE001
            continue
        if not s.is_empty:
            cached[sym] = s

    hyps: List[Hypothesis] = []
    for metric, (code, label) in METRICS.items():
        for horizon in horizons:
            pooled: List[Observation] = []
            for sym, series in cached.items():
                obs = symbol_observations(sym, metric, horizon, bench, as_of,
                                          series=series)
                pooled.extend(_independent(obs, horizon))
            hyps.append(evaluate_buckets(
                pooled, name=f"{code}-{horizon}p",
                question=(f"{label} tại t → lợi suất tương đối {horizon} phiên sau"),
                alpha=ALPHA_BONFERRONI, draws=draws,
                low_label="rẻ nhất so với chính mình",
                high_label="đắt nhất so với chính mình", unit="x",
                expect=-1))

    return ValuationCalibration(
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
        universe=universe or "all", n_symbols=len(cached), hypotheses=hyps,
        note=("Phân vị tính **tại thời điểm t** bằng chính lịch sử trước đó "
              f"(tối thiểu {MIN_HISTORY} phiên), không dùng cả chuỗi — xếp hạng "
              "bằng toàn bộ lịch sử là dùng giá của tương lai để gọi một mức "
              "định giá là 'rẻ'. Nhóm 1 = **rẻ nhất**, nên chiều đăng ký trước "
              "là *rẻ vượt nền / đắt thua nền* (`expect=-1`) — ngược chiều với "
              "dòng tiền, và dùng nhầm chiều là đọc một kết quả đúng thành "
              "'không đạt'. Ngưỡng Bonferroni áp cho cả hai đuôi. "
              "⚠️ Mẫu hết chồng lấn trong từng mã, không hết tương quan giữa "
              "các mã."))


def result_path(root: Optional[Path] = None) -> Path:
    return (root or RESULT_DIR) / RESULT_NAME


def save(cal: ValuationCalibration, root: Optional[Path] = None) -> Path:
    path = result_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cal.to_dict(), ensure_ascii=False, indent=1),
                    encoding="utf-8")
    return path


def load(root: Optional[Path] = None) -> Optional[ValuationCalibration]:
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
    return ValuationCalibration(
        generated=data.get("generated", ""), universe=data.get("universe", ""),
        n_symbols=data.get("n_symbols", 0), hypotheses=hyps,
        n_tests=data.get("n_tests", N_TESTS),
        alpha=data.get("alpha", ALPHA_BONFERRONI), note=data.get("note", ""))


def calibration_note(root: Optional[Path] = None) -> Tuple[str, bool]:
    cal = load(root)
    if cal is None:
        return NO_CALIBRATION, False
    if not cal.any_passed:
        return f"{NOT_PREDICTIVE} (hiệu chuẩn {cal.generated})", False
    passed = [h.name for h in cal.hypotheses if h.passed]
    return (f"Hiệu chuẩn {cal.generated}: đạt {', '.join(passed)} "
            f"(ngưỡng Bonferroni {cal.alpha:.5f} cho {cal.n_tests} phép kiểm)."), True


def _main(argv: Optional[Sequence[str]] = None) -> int:       # pragma: no cover
    import sys
    args = list(argv if argv is not None else sys.argv[1:])
    started = datetime.now()
    cal = run(args[0] if args else None)
    path = save(cal)
    from src.desk.format import format_valuation_calibration
    print(format_valuation_calibration(cal))
    print(f"\nGhi {path} trong {(datetime.now() - started).seconds}s")
    return 0


if __name__ == "__main__":                                    # pragma: no cover
    raise SystemExit(_main())
