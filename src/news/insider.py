"""Người trong nhà đang mua hay đang bán — gộp thành **một con số so được**.

``news_transactions`` in ra từng giao dịch một, đủ chi tiết để đọc. Ở đây cần
thứ khác: một số duy nhất để xếp 79 mã cạnh nhau. Hai cái bẫy phải tránh:

1. **Số cổ phiếu tuyệt đối không so được giữa hai mã.** 1 triệu cổ của một mã
   có 200 triệu cổ tự do là một chuyện; 1 triệu cổ của mã có 4 tỷ cổ là hạt
   bụi. Mẫu số bắt buộc là ``freeShares`` — cũng đúng lý do
   ``news/fireant.fundamental`` ghi trong docstring của nó.

2. **Đăng ký không phải đã thực hiện.** Phần lớn bản ghi trong kho có
   ``execution_volume`` rỗng: người ta mới *đăng ký* mua trong một cửa sổ 30
   ngày, chưa mua. Gộp hai loại vào một con số là biến ý định thành sự thật.
   ``InsiderFlow`` giữ hai vế riêng và ``net_ratio`` ưu tiên phần đã thực hiện,
   chỉ rơi về phần đăng ký khi không có gì khác — kèm cờ ``registered_only``
   để tầng chữ nghĩa nói đúng chữ.

Mốc thời gian dùng ``start_date``: bảng này **không có ngày công bố** (§2b hạn
chế (b) của plan). Với câu hỏi ở đây — "gần đây người trong nhà đang làm gì" —
mốc thay thế đó đủ dùng, nhưng nó vẫn là mốc thay thế và ``t0_source`` nói vậy.
"""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

from src.news import store as store_mod
from src.news.models import PURCHASED, SOLD, STOCK_RIGHT_PURCHASED, STOCK_RIGHT_SOLD

#: Cửa sổ mặc định. 90 ngày ~ một quý: đủ dài để bắt được một đợt đăng ký mua,
#: đủ ngắn để không kéo theo chuyện của năm ngoái.
WINDOW_DAYS = 90

#: Chiều nào tính là mua. Quyền mua đi cùng chiều với cổ phiếu — đăng ký mua
#: quyền là bỏ thêm tiền vào, bán quyền là rút ra.
BUY_SIDES = {PURCHASED, STOCK_RIGHT_PURCHASED}
SELL_SIDES = {SOLD, STOCK_RIGHT_SOLD}


@dataclass
class InsiderFlow:
    """Dòng mua/bán của lãnh đạo + cổ đông lớn trong một cửa sổ."""
    symbol: str
    window_days: int
    n_records: int
    executed_buy: float = 0.0
    executed_sell: float = 0.0
    registered_buy: float = 0.0
    registered_sell: float = 0.0
    free_shares: Optional[float] = None
    #: Ròng chia cổ phiếu tự do, tính bằng **phần trăm**. ``None`` = không có
    #: mẫu số, và khi đó không được suy ra 0.
    net_ratio_pct: Optional[float] = None
    registered_only: bool = False
    t0_source: str = "start_date_proxy"
    top_names: List[str] = None         # 3 tên lớn nhất, kèm chiều

    def __post_init__(self):
        if self.top_names is None:
            self.top_names = []

    @property
    def executed_net(self) -> float:
        return self.executed_buy - self.executed_sell

    @property
    def registered_net(self) -> float:
        return self.registered_buy - self.registered_sell

    @property
    def is_empty(self) -> bool:
        return self.n_records == 0

    @property
    def label(self) -> str:
        if self.is_empty:
            return "không có giao dịch nội bộ trong cửa sổ"
        side = "mua ròng" if (self.net_ratio_pct or 0) > 0 else "bán ròng"
        if self.net_ratio_pct is None:
            side = "mua ròng" if self.executed_net + self.registered_net > 0 else "bán ròng"
            return f"{self.n_records} giao dịch, {side} (thiếu freeShares nên chưa chuẩn hoá được)"
        kind = "đăng ký" if self.registered_only else "đã thực hiện"
        return (f"{self.n_records} giao dịch, {side} {abs(self.net_ratio_pct):.2f}% "
                f"cổ phiếu tự do ({kind})")

    def to_dict(self) -> dict:
        data = asdict(self)
        data["executed_net"] = self.executed_net
        data["registered_net"] = self.registered_net
        data["label"] = self.label
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InsiderFlow":
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in known})


def _vol(row: Dict[str, Any], key: str) -> float:
    value = row.get(key)
    try:
        return float(value) if value else 0.0
    except (TypeError, ValueError):
        return 0.0


def summarise(symbol: str, rows: Sequence[Dict[str, Any]],
              free_shares: Optional[float] = None,
              window_days: int = WINDOW_DAYS) -> InsiderFlow:
    """Gộp các bản ghi đã lọc sẵn thành một ``InsiderFlow``."""
    flow = InsiderFlow(symbol=symbol.upper(), window_days=window_days,
                       n_records=len(rows), free_shares=free_shares)
    sized: List[tuple] = []
    for row in rows:
        direction = row.get("direction")
        executed = _vol(row, "execution_volume")
        registered = _vol(row, "registered_volume")
        if direction in BUY_SIDES:
            flow.executed_buy += executed
            flow.registered_buy += registered
            sized.append((max(executed, registered), row.get("name") or "?", "mua"))
        elif direction in SELL_SIDES:
            flow.executed_sell += executed
            flow.registered_sell += registered
            sized.append((max(executed, registered), row.get("name") or "?", "bán"))

    net = flow.executed_net
    if flow.executed_buy == 0.0 and flow.executed_sell == 0.0:
        net = flow.registered_net
        flow.registered_only = bool(rows)
    if free_shares:
        flow.net_ratio_pct = round(net / free_shares * 100.0, 3)

    sized.sort(key=lambda t: -t[0])
    flow.top_names = [f"{name} {side} {vol:,.0f}" for vol, name, side in sized[:3]]
    return flow


def build(symbol: str, as_of: Optional[datetime] = None,
          window_days: int = WINDOW_DAYS,
          free_shares: Optional[float] = None,
          db_path=None) -> InsiderFlow:
    """Đọc kho và gộp — một mã, một cửa sổ."""
    sym = symbol.strip().upper()
    end = as_of or datetime.now()
    start = (end - timedelta(days=window_days)).strftime("%Y-%m-%d")
    with store_mod.connect(db_path) as conn:
        rows = store_mod.load_holder_transactions(
            conn, sym, as_of=end.strftime("%Y-%m-%d"))
    recent = [r for r in rows if str(r.get("start_date") or "")[:10] >= start]
    return summarise(sym, recent, free_shares=free_shares, window_days=window_days)
