"""Chỉ số cơ bản, **đóng băng theo ngày** — vì FireAnt chỉ trả hôm nay.

``/symbols/{s}/fundamental`` và ``/symbols/{s}/financial-indicators`` là
*snapshot*: gọi hôm nay được P/E hôm nay, không có cách nào hỏi P/E ngày
01/01/2025. Đó là một lỗ hổng thẳng vào nguyên tắc ``as_of`` của cả dự án —
dùng P/E hôm nay để giải thích một tin của năm ngoái là nhìn trước, đúng thứ
mà mọi tầng khác đã cẩn thận chặn.

Cách duy nhất bịt được (§2b(a) của ``Documents/plan_news_pipeline.md``): **tự
đóng băng**. Mỗi lượt nạp ghi ``news/snapshots/<mã>/<ngày>.json``; truy vấn có
``as_of`` chỉ đọc bản ``<=`` mốc. Không bắt đầu ghi từ hôm nay thì vĩnh viễn
không dựng lại được quá khứ — không có nguồn nào bán lại chuỗi này.

Hệ quả phải nói thẳng ra ở mọi báo cáo, không giấu: một bảng hồi tưởng về ngày
trước lượt đóng băng đầu tiên **không có** phần cơ bản. ``Fundamentals`` mang
``snapshot_date`` và ``stale_days`` để tầng chữ nghĩa nói được câu đó.

``industryValue`` đi kèm sẵn trong mỗi chỉ số của ``financial-indicators`` —
trung bình ngành theo phân ngành ICB của chính FireAnt. Đó là lý do module này
không tự dựng bảng ngành để so P/E: mẫu số ngành đã có sẵn, và nó phủ cả những
mã không nằm trong ``data/`` (79 mã ở đây không phải cả ngành).
"""
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.ta.loader import PROJECT_ROOT

SNAPSHOT_DIR = PROJECT_ROOT / "news" / "snapshots"

#: Chỉ số nào "tốt khi cao", chỉ số nào "tốt khi thấp". Không có bảng này thì
#: mọi phép so với ngành đều sai dấu ở nhóm định giá: P/E **thấp** hơn ngành là
#: rẻ hơn, còn ROE **cao** hơn ngành mới là tốt hơn.
LOWER_IS_BETTER = {"P/E", "P/S", "P/B", "Nợ/VCSH"}
HIGHER_IS_BETTER = {
    "EPS", "%Lãi ròng", "%Lãi gộp", "%EBIT", "%Lãi HĐKD",
    "TT Hiện hành", "TT Nhanh", "TT Lãi vay",
    "ROA", "ROE", "ROIC", "ROCE",
    "VQ Tổng TS", "VQ HTK", "VQ KPT", "VQ TSNH",
}

#: Nhóm chỉ số dùng để chấm điểm "định giá so với ngành". Cố ý hẹp: bốn chỉ số
#: này là thứ đọc được ngay, còn nhóm vòng quay phụ thuộc mô hình kinh doanh
#: tới mức so chéo ngành thành vô nghĩa (VQ HTK của ngân hàng và của thép).
VALUATION_KEYS = ("P/E", "P/B")
QUALITY_KEYS = ("ROE", "%Lãi ròng")

GROUP_VN = {
    1: "Định giá", 2: "Khả năng sinh lợi", 3: "Sức khoẻ tài chính",
    4: "Hiệu quả sinh lời", 5: "Vòng quay",
}


@dataclass
class Indicator:
    """Một chỉ số, kèm **trung bình ngành của chính nó**."""
    key: str                          # shortName, ví dụ "P/E"
    name: str
    group: int
    value: Optional[float]
    industry: Optional[float]
    change_pct: Optional[float] = None   # % đổi so với kỳ trước, do FireAnt tính

    @property
    def gap_pct(self) -> Optional[float]:
        """Cách ngành bao nhiêu phần trăm, **đã quy về dấu 'tốt hơn là dương'**.

        Không quy dấu ở đây thì mọi tầng trên phải nhớ P/E ngược chiều ROE, và
        chỉ cần một chỗ quên là điểm định giá đảo dấu im lặng.
        """
        if self.value is None or not self.industry:
            return None
        raw = (self.value - self.industry) / abs(self.industry) * 100.0
        if self.key in LOWER_IS_BETTER:
            raw = -raw
        elif self.key not in HIGHER_IS_BETTER:
            return None                 # không biết chiều thì không phát biểu
        return round(raw, 1)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["gap_pct"] = self.gap_pct
        return data


@dataclass
class Fundamentals:
    """Ảnh chụp chỉ số cơ bản của một mã tại một ngày cụ thể."""
    symbol: str
    snapshot_date: str                # ngày file được đóng băng
    fetched_at: str = ""
    #: Từ ``/fundamental`` — quy mô và sở hữu, thứ ``financial-indicators`` không có.
    pe: Optional[float] = None
    eps: Optional[float] = None
    beta: Optional[float] = None
    market_cap: Optional[float] = None
    shares_outstanding: Optional[float] = None
    free_shares: Optional[float] = None
    dividend_yield: Optional[float] = None
    foreign_ownership: Optional[float] = None
    insider_ownership: Optional[float] = None
    institution_ownership: Optional[float] = None
    price_change_1y: Optional[float] = None
    high_52w: Optional[float] = None
    low_52w: Optional[float] = None
    avg_volume_3m: Optional[float] = None
    #: Từ ``/financial-indicators`` — 20 chỉ số, mỗi cái kèm trung bình ngành.
    indicators: Dict[str, Indicator] = field(default_factory=dict)
    #: Từ ``/profile`` — mã ngành ICB, để biết ``industryValue`` là ngành nào.
    icb_code: str = ""
    company_name: str = ""
    #: Số ngày từ lúc đóng băng tới mốc đang đứng. Tầng chữ nghĩa dùng để cảnh báo.
    stale_days: Optional[int] = None

    @property
    def is_empty(self) -> bool:
        return not self.indicators and self.pe is None

    def get(self, key: str) -> Optional[Indicator]:
        return self.indicators.get(key)

    def gap(self, key: str) -> Optional[float]:
        ind = self.indicators.get(key)
        return ind.gap_pct if ind else None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["indicators"] = {k: v.to_dict() for k, v in self.indicators.items()}
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Fundamentals":
        raw = dict(data)
        inds = raw.pop("indicators", {}) or {}
        parsed = {}
        for k, v in inds.items():
            v = {kk: vv for kk, vv in v.items() if kk != "gap_pct"}
            parsed[k] = Indicator(**v)
        raw.pop("gap_pct", None)
        known = {f for f in cls.__dataclass_fields__ if f != "indicators"}
        return cls(indicators=parsed, **{k: v for k, v in raw.items() if k in known})


# ---------------------------------------------------------------------------
# Nạp từ FireAnt và đóng băng
# ---------------------------------------------------------------------------
def _parse_indicators(payload: Any) -> Dict[str, Indicator]:
    out: Dict[str, Indicator] = {}
    if not isinstance(payload, list):
        return out
    for row in payload:
        if not isinstance(row, dict):
            continue
        key = (row.get("shortName") or row.get("name") or "").strip()
        if not key:
            continue
        out[key] = Indicator(
            key=key,
            name=(row.get("name") or key).strip(),
            group=int(row.get("group") or 0),
            value=row.get("value"),
            industry=row.get("industryValue"),
            change_pct=row.get("change"),
        )
    return out


def fetch(symbol: str) -> Fundamentals:
    """Gọi FireAnt, dựng ``Fundamentals`` cho **hôm nay**. Có chạm mạng."""
    from src.news import fireant

    sym = symbol.strip().upper()
    base = fireant.fundamental(sym) or {}
    indicators = _parse_indicators(fireant.get(f"/symbols/{sym}/financial-indicators"))
    profile = fireant.get(f"/symbols/{sym}/profile")
    profile = profile if isinstance(profile, dict) else {}
    now = datetime.now()
    return Fundamentals(
        symbol=sym,
        snapshot_date=now.strftime("%Y-%m-%d"),
        fetched_at=now.strftime("%Y-%m-%d %H:%M"),
        pe=base.get("pe"),
        eps=base.get("eps"),
        beta=base.get("beta"),
        market_cap=base.get("marketCap"),
        shares_outstanding=base.get("sharesOutstanding"),
        free_shares=base.get("freeShares"),
        dividend_yield=base.get("dividendYield"),
        foreign_ownership=base.get("foreignOwnership"),
        insider_ownership=base.get("insiderOwnership"),
        institution_ownership=base.get("institutionOwnership"),
        price_change_1y=base.get("priceChange1y"),
        high_52w=base.get("high52Week"),
        low_52w=base.get("low52Week"),
        avg_volume_3m=base.get("avgVolume3m"),
        indicators=indicators,
        icb_code=str(profile.get("icbCode") or ""),
        company_name=str(profile.get("companyName") or ""),
    )


def snapshot_path(symbol: str, date: str, root: Optional[Path] = None) -> Path:
    return (root or SNAPSHOT_DIR) / symbol.strip().upper() / f"{date}.json"


def freeze(fund: Fundamentals, root: Optional[Path] = None) -> Path:
    """Ghi ảnh chụp. Ghi đè bản cùng ngày — chạy hai lần một ngày không rải file."""
    path = snapshot_path(fund.symbol, fund.snapshot_date, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(fund.to_dict(), f, ensure_ascii=False, indent=1)
    return path


def available_dates(symbol: str, root: Optional[Path] = None) -> List[str]:
    """Ngày của mọi ảnh chụp đã có, cũ → mới."""
    folder = (root or SNAPSHOT_DIR) / symbol.strip().upper()
    if not folder.is_dir():
        return []
    return sorted(p.stem for p in folder.glob("*.json"))


def load(symbol: str, as_of: Optional[datetime] = None,
         root: Optional[Path] = None) -> Optional[Fundamentals]:
    """Ảnh chụp mới nhất **không muộn hơn** ``as_of``; ``None`` nếu chưa có bản nào.

    Trả ``None`` thay vì ảnh chụp gần nhất bất kể ngày, vì lấy bản muộn hơn mốc
    chính là cái nhìn trước mà cả module này sinh ra để chặn.
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
    path = snapshot_path(sym, chosen, root)
    with path.open("r", encoding="utf-8") as f:
        fund = Fundamentals.from_dict(json.load(f))
    try:
        delta = datetime.strptime(limit, "%Y-%m-%d") - datetime.strptime(chosen, "%Y-%m-%d")
        fund.stale_days = delta.days
    except ValueError:
        fund.stale_days = None
    return fund


def refresh(symbols: List[str], root: Optional[Path] = None,
            on_error: str = "collect") -> Tuple[int, List[str]]:
    """Nạp + đóng băng cả loạt. Trả ``(số mã xong, danh sách lỗi)``.

    Một mã lỗi không được giết cả lượt: ảnh chụp bị thiếu một ngày còn vá được
    ở lượt sau, còn hỏng giữa chừng thì cả loạt mất ngày hôm đó.
    """
    done, errors = 0, []
    for sym in symbols:
        try:
            fund = fetch(sym)
            if fund.is_empty:
                errors.append(f"{sym}: FireAnt trả rỗng")
                continue
            freeze(fund, root)
            done += 1
        except Exception as exc:        # noqa: BLE001 — xem docstring
            if on_error != "collect":
                raise
            errors.append(f"{sym}: {type(exc).__name__}: {exc}")
    return done, errors
