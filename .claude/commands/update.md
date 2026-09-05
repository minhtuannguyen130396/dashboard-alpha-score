---
description: Tải giá mới nhất từ FireAnt về data/ (mặc định tháng hiện tại)
argument-hint: "[vn30|all|MÃ1,MÃ2] [latest|recent|quarter|full]"
allowed-tools: mcp__vn-ta__update_prices_tool, mcp__vn-ta__list_symbols
---

Cập nhật dữ liệu giá: `$ARGUMENTS`

Cách đọc tham số (bỏ trống thì dùng mặc định):
- Phần không phải tên mode là `universe` — mặc định `disk` (mọi mã đang có dữ liệu).
- Từ nào thuộc `latest` / `recent` / `quarter` / `full` là `mode` — mặc định `latest`.

Gọi `mcp__vn-ta__update_prices_tool`.

**Chỉ dùng `full` khi người dùng nói rõ** — nó tải lại toàn bộ lịch sử từ 2010 cho từng mã,
mất rất nhiều thời gian và request. Nếu tham số có `full` mà bạn thấy có vẻ nhầm,
hỏi lại trước khi chạy.

In nguyên kết quả. Nếu có mã cập nhật được phiên mới, nhắc người dùng rằng
`/watch` và `/scan` giờ đã thấy dữ liệu mới (cache đã xoá, không cần khởi động lại).
Nếu lỗi thiếu token, chỉ rõ cần đặt `FIREANT_BEARER_TOKEN` hoặc ghi vào `access_token.txt`
— đừng tự đi tìm hay tạo token.
