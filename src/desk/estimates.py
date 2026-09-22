"""Định giá dựng sẵn của FireAnt — đóng băng theo ngày, vì nó chỉ có *hôm nay*.

``/symbols/{s}/estimated-price`` trả sáu mô hình kèm trọng số và một giá tổng
hợp (DCF, P/E, P/B, Graham 1/2/3). Hai điều phải nói trước khi dùng một con số
nào trong đó:

1. **Nó là hộp đen.** Không công bố tỷ lệ chiết khấu, giả định tăng trưởng hay
   kỳ EPS đã dùng. Nên vị trí của nó trong hệ thống là *ý kiến của một bên thứ
   ba có tên*, đứng cạnh đồng thuận CTCK và cạnh dải định giá tự tính — **không
   phải** giá mục tiêu của bàn, và không bao giờ được lấy trung bình với hai
   nguồn kia (trộn ba nhận định là tạo ra một nhận định không ai đưa ra cả).
2. **Nó là snapshot.** Cùng họ với ``fundamental`` / ``financial-indicators``,
   nên chịu đúng luật đã ghi trong ``CLAUDE.md``: ghi ảnh chụp theo ngày, đọc
   bản **≤ mốc**, trả ``None`` chứ không rơi về bản mới hơn. Ngày không chạy là
   ngày mất vĩnh viễn — không nguồn nào bán lại chuỗi này.

Vì (2), module này phải chạy đều **trước khi** có ai đọc tới nó. Đó là lý do nó
nằm ở giai đoạn 0 cùng ``ledger.py`` chứ không nằm ở giai đoạn định giá.
"""
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.news.fireant import get
from src.ta.loader import PROJECT_ROOT

SNAPSHOT_DIR = PROJECT_ROOT / "desk" / "snapshots"

#: Nhật ký từng lượt chạy. Có nó thì phân biệt được hai chuyện trông giống hệt
#: nhau khi đọc kho: *chưa ai chạy ngày đó* và *đã chạy, FireAnt trả rỗng cho
#: mã này*. Đo thật ngày 19/09/2026: **27/80 mã** của rổ trả rỗng, và cả 27 đều
#: là ngân hàng, công ty chứng khoán hoặc bảo hiểm — mô hình định giá của
#: FireAnt **không phủ nhóm tài chính**. Thiếu nhật ký thì cột định giá trống ở
#: VCB trông y hệt cột định giá trống vì quên chạy.
RUNS_DIR = SNAPSHOT_DIR / "_runs"

#: (khoá trong payload, khoá trọng số, tên hiển thị)
MODELS: Tuple[Tuple[str, str, str], ...] = (
    ("estimatedPriceDCF", "proportionDCF", "DCF"),
    ("estimatedPricePE", "proportionPE", "P/E"),
    ("estimatedPricePB", "proportionPB", "P/B"),
    ("estimatedPriceGraham1", "proportionGraham1", "Graham 1"),
    ("estimatedPriceGraham2", "proportionGraham2", "Graham 2"),
    ("estimatedPriceGraham3", "proportionGraham3", "Graham 3"),
)


@dataclass
class ModelPrice:
    name: str
    price: Optional[float] = None
    weight_pct: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Valuation:
    """Ảnh chụp định giá của một mã tại một ngày."""
    symbol: str
    snapshot_date: str
    composed: Optional[float] = None
    models: List[ModelPrice] = field(default_factory=list)
    stale_days: Optional[int] = None

    @property
    def is_empty(self) -> bool:
        return self.composed is None and not any(m.price for m in self.models)

    def spread_pct(self) -> Optional[float]:
        """Khoảng cách giữa mô hình cao nhất và thấp nhất, tính theo bản tổng hợp.

        Con số này quan trọng hơn chính ``composed``: sáu mô hình cho FPT trải
        từ 39k tới 88k, nên một giá tổng hợp 71k **trông** chính xác hơn thực
        tế rất nhiều. In độ trải ra là cách rẻ nhất để không ai đọc nó như một
        con số duy nhất.
        """
        prices = [m.price for m in self.models if m.price]
        if len(prices) < 2 or not self.composed:
            return None
        return round((max(prices) - min(prices)) / self.composed * 100, 1)

    def upside_pct(self, close: Optional[float], unit: float = 1.0) -> Optional[float]:
        """So giá tổng hợp với giá thị trường — **hai nguồn, hai đơn vị**.

        ``estimated-price`` trả **đồng** (FPT: 71.425), còn chuỗi trong ``data/``
        là **nghìn đồng** (FPT: 71,7) và mang sẵn hệ số ở ``StockRecord.unit``
        = 1000. Nhân thiếu là ra "+99.516%" — một con số vô lý tới mức buồn
        cười, nhưng nó **không ném lỗi**, chỉ lặng lẽ sai; nếu chênh lệch nhỏ
        hơn (hai nguồn cùng đơn vị trong vài trường hợp) thì không ai phát hiện.
        Nên ``unit`` là tham số bắt buộc phải nghĩ tới, và
        ``format_valuation`` còn chặn thêm một lớp khi tỷ lệ vô lý.
        """
        if not close or not self.composed:
            return None
        market = close * (unit or 1.0)
        if market <= 0:
            return None
        return round((self.composed / market - 1) * 100, 1)

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["models"] = [m.to_dict() for m in self.models]
        out["spread_pct"] = self.spread_pct()
        return out

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Valuation":
        return cls(
            symbol=str(data.get("symbol") or "").upper(),
            snapshot_date=str(data.get("snapshot_date") or ""),
            composed=data.get("composed"),
            models=[ModelPrice(**{k: v for k, v in m.items()
                                  if k in ModelPrice.__dataclass_fields__})   # noqa: SLF001
                    for m in (data.get("models") or [])],
        )


# ---------------------------------------------------------------------------
def _num(value: Any) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None      # loại NaN


def parse(symbol: str, payload: Any, snapshot_date: Optional[str] = None
          ) -> Valuation:
    """Payload → dataclass. Không mạng, không đĩa, nên test chạy trên fixture."""
    data = payload if isinstance(payload, dict) else {}
    models = [ModelPrice(name=label, price=_num(data.get(pk)),
                         weight_pct=_num(data.get(wk)))
              for pk, wk, label in MODELS]
    return Valuation(
        symbol=symbol.strip().upper(),
        snapshot_date=snapshot_date or datetime.now().strftime("%Y-%m-%d"),
        composed=_num(data.get("composedPrice")),
        models=models,
    )


def fetch(symbol: str) -> Valuation:
    return parse(symbol, get(f"/symbols/{symbol.strip().upper()}/estimated-price"))


def snapshot_path(symbol: str, date: str, root: Optional[Path] = None) -> Path:
    return (root or SNAPSHOT_DIR) / symbol.strip().upper() / f"{date}.json"


def freeze(val: Valuation, root: Optional[Path] = None) -> Path:
    """Ghi ảnh chụp; chạy hai lần trong ngày thì ghi đè, không rải file."""
    path = snapshot_path(val.symbol, val.snapshot_date, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(val.to_dict(), f, ensure_ascii=False, indent=1)
    return path


def available_dates(symbol: str, root: Optional[Path] = None) -> List[str]:
    folder = (root or SNAPSHOT_DIR) / symbol.strip().upper()
    if not folder.is_dir():
        return []
    return sorted(p.stem for p in folder.glob("*.json"))


def load(symbol: str, as_of: Optional[datetime] = None,
         root: Optional[Path] = None) -> Optional[Valuation]:
    """Ảnh chụp mới nhất **không muộn hơn** ``as_of``; ``None`` nếu chưa có.

    Không rơi về bản mới hơn — lấy một định giá tính sau mốc để giải thích một
    phiên trước mốc chính là cái nhìn trước mà chế độ hồi tưởng sinh ra để chặn.
    """
    sym = symbol.strip().upper()
    dates = available_dates(sym, root)
    if not dates:
        return None
    limit = (as_of or datetime.now()).strftime("%Y-%m-%d")
    usable = [d for d in dates if d <= limit]
    if not usable:
        return None
    chosen = usable[-1]
    with snapshot_path(sym, chosen, root).open("r", encoding="utf-8") as f:
        val = Valuation.from_dict(json.load(f))
    try:
        val.stale_days = (datetime.strptime(limit, "%Y-%m-%d")
                          - datetime.strptime(chosen, "%Y-%m-%d")).days
    except ValueError:
        val.stale_days = None
    return val


def runs_dir(root: Optional[Path] = None) -> Path:
    return (root / "_runs") if root else RUNS_DIR


def record_run(done: Sequence[str], empty: Sequence[str], failed: Sequence[str] = (),
               day: Optional[str] = None, root: Optional[Path] = None) -> Path:
    day = day or datetime.now().strftime("%Y-%m-%d")
    path = runs_dir(root) / f"{day}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"date": day, "done": sorted(done),
                                "empty": sorted(empty), "failed": sorted(failed)},
                               ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def last_run(as_of: Optional[datetime] = None, root: Optional[Path] = None
             ) -> Optional[Dict[str, Any]]:
    folder = runs_dir(root)
    if not folder.is_dir():
        return None
    limit = (as_of or datetime.now()).strftime("%Y-%m-%d")
    days = sorted(p.stem for p in folder.glob("*.json") if p.stem <= limit)
    if not days:
        return None
    try:
        return json.loads((folder / f"{days[-1]}.json").read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def returned_empty(symbol: str, as_of: Optional[datetime] = None,
                   root: Optional[Path] = None) -> bool:
    """Lượt gần nhất **đã hỏi** mã này và FireAnt trả rỗng?

    Khác hẳn "chưa chạy ngày nào": cái đầu là *đã đo và không có*, cái sau là
    *chưa đo*. Với nhóm tài chính thì câu trả lời đúng luôn là cái đầu.
    """
    run = last_run(as_of, root)
    return bool(run and symbol.strip().upper() in (run.get("empty") or []))


def refresh(symbols: Sequence[str], root: Optional[Path] = None
            ) -> Tuple[int, List[str]]:
    """Nạp + đóng băng cả loạt. Trả ``(số mã xong, danh sách lỗi)``.

    Một mã lỗi không giết cả lượt: thiếu một mã còn vá được ở lượt sau, còn
    hỏng giữa chừng thì cả loạt mất ngày hôm đó — mà ngày thì không lấy lại được.
    """
    done: List[str] = []
    empty: List[str] = []
    failed: List[str] = []
    errors: List[str] = []
    for sym in symbols:
        sym = sym.strip().upper()
        try:
            val = fetch(sym)
            if val.is_empty:
                empty.append(sym)
                errors.append(f"{sym}: FireAnt trả rỗng")
                continue
            freeze(val, root)
            done.append(sym)
        except Exception as exc:        # noqa: BLE001 — xem docstring
            failed.append(sym)
            errors.append(f"{sym}: {exc}")
    record_run(done, empty, failed, root=root)
    return len(done), errors


def coverage(symbols: Optional[Sequence[str]] = None,
             root: Optional[Path] = None) -> Dict[str, Any]:
    """Kho đã đóng băng được bao nhiêu — số này chỉ tăng, và chỉ khi có chạy."""
    base = root or SNAPSHOT_DIR
    syms = list(symbols) if symbols else sorted(
        p.name for p in base.glob("*") if p.is_dir() and not p.name.startswith("_"))
    days: Dict[str, int] = {}
    for s in syms:
        for d in available_dates(s, root):
            days[d] = days.get(d, 0) + 1
    ordered = sorted(days)
    return {"symbols": len(syms), "sessions": len(ordered),
            "first": ordered[0] if ordered else None,
            "last": ordered[-1] if ordered else None,
            "per_day": days}
