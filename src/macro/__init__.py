"""Tầng vĩ mô & ngành — đơn vị phân tích là NGÀNH, không phải mã.

Thiết kế đầy đủ: ``Documents/plan_macro_sector.md``.

Bất biến quan trọng nhất của tầng này, và nó **test được**: đường chạy của
``src/macro/`` không đọc một file nào trong ``data/<MÃ>/`` của cổ phiếu. Ngành
có chuỗi giá riêng do FireAnt tính trên **toàn bộ** thành viên ngành — 33 mã với
Năng lượng, trong khi rổ ``data/`` chỉ có 4. Gộp 4 mã lại rồi gọi đó là ngành là
đúng cái sai mà ``src/ta/sector.py`` đã phải tự cảnh báo bằng ``MIN_PEERS``.
"""
