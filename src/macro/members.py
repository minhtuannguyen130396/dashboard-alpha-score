"""Cầu nối ngành ↔ rổ 80 mã — và nó **cố ý** nằm ở cuối chuỗi, không ở đầu.

Cả tầng `src/macro/` chạy trên chỉ số ngành, BCTC ngành và tin không gắn mã;
không đường nào trong đó đọc `data/<MÃ>/` của một cổ phiếu. Đó là bất biến của
tầng này (§2.6 của phương án) và nó có test chặn.

Module này là chỗ **duy nhất** được phép bắc cầu ngược lại, và nó trả lời một
câu hẹp: *ngành này gồm những mã nào, và trong số đó rổ ta có mã nào*. Tách
riêng ra đây để bất biến kia vẫn kiểm tra được bằng máy — nếu phép ánh xạ nằm
rải trong `score.py` hay `report.py` thì không còn chỗ nào để chặn.

⚠️ **Hai mẫu số, và trộn chúng là sai.** `/icb/{mã}/symbols` trả **toàn bộ**
thành viên ngành trên cả ba sàn (Năng lượng 33, Công nghiệp 505); rổ trong
`data/` có 80 mã. Chỉ số ngành chạy theo mẫu số thứ nhất, còn "mã nào tôi mua
được" thuộc mẫu số thứ hai. Mọi chỗ hiển thị phải in **cả hai con số**, nếu
không người đọc sẽ tưởng "Năng lượng +16,9%" là chuyện của BSR/PLX/PVD/PVT.
"""
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from src.news.fireant import get
from src.ta.loader import PROJECT_ROOT, available_symbols, non_tradable_symbols

MEMBER_DIR = PROJECT_ROOT / "macro" / "members"


def path_for(code: str, root: Optional[Path] = None) -> Path:
    return (root or MEMBER_DIR) / f"{code}.json"


def fetch(code: str) -> List[str]:
    """Thành viên ngành — **cả sàn**, không riêng rổ ``data/``."""
    rows = get(f"/icb/{code}/symbols") or []
    return sorted({str(s).strip().upper() for s in rows if str(s).strip()})


def save(code: str, symbols: Sequence[str],
         root: Optional[Path] = None) -> Path:
    out = path_for(code, root)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(sorted(symbols), ensure_ascii=False, indent=1),
                   encoding="utf-8")
    return out


def load(code: str, root: Optional[Path] = None) -> List[str]:
    src = path_for(code, root)
    if not src.is_file():
        return []
    try:
        return list(json.loads(src.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return []


def in_basket(code: str, root: Optional[Path] = None) -> List[str]:
    """Mã của ngành này **có dữ liệu trong ``data/``** và là cổ phiếu thật.

    Loại benchmark/phái sinh/chỉ số ngành khỏi kết quả: một ngành không "chứa"
    VNINDEX, và để lọt thì mọi phép đếm độ rộng bên trên lệch một đơn vị.
    """
    have = set(available_symbols()) - non_tradable_symbols()
    return [s for s in load(code, root) if s in have]


@dataclass
class Membership:
    code: str
    name: str = ""
    listed: int = 0            # thành viên trên cả ba sàn
    in_data: List[str] = field(default_factory=list)

    @property
    def coverage(self) -> Optional[float]:
        return len(self.in_data) / self.listed if self.listed else None

    @property
    def comparable(self) -> bool:
        """Dưới 3 mã thì mọi phép so trong rổ là vô nghĩa — xem ``sector.MIN_PEERS``."""
        return len(self.in_data) >= 3

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["coverage"] = self.coverage
        d["comparable"] = self.comparable
        return d


def membership(code: str, name: str = "",
               root: Optional[Path] = None) -> Membership:
    listed = load(code, root)
    return Membership(code=str(code), name=name, listed=len(listed),
                      in_data=in_basket(code, root))


def update(codes: Optional[Sequence[str]] = None,
           root: Optional[Path] = None) -> List[Membership]:
    from src.macro import icb
    tree = icb.fetch_tree()
    names = {i.code: i.name for i in tree}
    codes = list(codes or icb.distinct_codes(tree))
    out = []
    for code in codes:
        try:
            syms = fetch(code)
        except Exception:                                  # noqa: BLE001
            syms = []
        if syms:
            save(code, syms, root)
        out.append(membership(code, names.get(code, ""), root))
    return out


def format_membership(rows: Sequence[Membership]) -> str:
    lines = ["| Mã | Ngành | Niêm yết | Trong rổ | Độ phủ | Mã |",
             "|---|---|---:|---:|---:|---|"]
    for m in sorted(rows, key=lambda r: r.code):
        cov = "—" if m.coverage is None else f"{m.coverage:.0%}"
        note = ", ".join(m.in_data) if m.in_data else "—"
        if not m.comparable and m.in_data:
            note += " ⚠️ dưới 3 mã, không so được trong rổ"
        lines.append(f"| `{m.code}` | {m.name} | {m.listed} | "
                     f"{len(m.in_data)} | {cov} | {note} |")
    lines += ["",
              "**Hai mẫu số khác nhau.** Cột *Niêm yết* là thứ chỉ số ngành "
              "chạy theo; cột *Trong rổ* là thứ bạn có dữ liệu để phân tích. "
              "Một ngành mạnh với độ phủ 12% nghĩa là phần lớn sức mạnh đó nằm "
              "ở những mã không có trong `data/`."]
    return "\n".join(lines)


def _main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Ánh xạ ngành → mã trong rổ")
    ap.add_argument("--codes", default="")
    args = ap.parse_args()
    codes = [c for c in args.codes.split(",") if c.strip()] or None
    print(format_membership(update(codes)))


if __name__ == "__main__":
    _main()
