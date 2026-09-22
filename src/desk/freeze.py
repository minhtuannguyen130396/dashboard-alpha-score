"""Lượt đóng băng hằng tuần — thứ duy nhất của giai đoạn 0 phải chạy đều.

    python -m src.desk.freeze [rổ]

``/symbols/{s}/estimated-price`` chỉ trả trạng thái **hôm nay**. Không có
endpoint nào trả lại định giá của tháng trước, không có nguồn nào bán lại chuỗi
đó. Nên mỗi lượt chạy là một ngày được giữ lại vĩnh viễn, và **ngày không chạy
là ngày mất vĩnh viễn** — đúng như ``update_fundamentals`` đã phải làm với chỉ
số cơ bản.

Đăng ký cùng ``weekly_macro.bat``. Không có gì đọc tới kho này cho tới giai
đoạn định giá, và đó chính là lý do phải chạy ngay từ bây giờ: tới lúc cần thì
đã muộn mấy tháng.
"""
import sys
from datetime import datetime
from typing import List, Optional, Sequence

from src.desk import estimates
from src.ta.loader import resolve_universe


def run(universe: Optional[str] = None) -> int:
    symbols: List[str] = resolve_universe(universe)
    started = datetime.now()
    print(f"[{started:%Y-%m-%d %H:%M}] đóng băng định giá cho {len(symbols)} mã "
          f"(rổ '{universe or 'all'}')")
    done, errors = estimates.refresh(symbols)
    print(f"  xong {done}/{len(symbols)} mã trong "
          f"{(datetime.now() - started).seconds}s")
    for err in errors:
        print(f"  ⚠️ {err}")

    cov = estimates.coverage()
    print(f"  kho: {cov['symbols']} mã · {cov['sessions']} ngày đã đóng băng "
          f"({cov['first']} → {cov['last']})")
    if cov["sessions"] == 1:
        print("  ℹ️ đây là ngày đầu tiên — chuỗi chỉ dài ra bằng cách chạy đều, "
              "không backfill được")
    return 0 if done else 1


def _main(argv: Optional[Sequence[str]] = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    return run(args[0] if args else None)


if __name__ == "__main__":                                     # pragma: no cover
    raise SystemExit(_main())
