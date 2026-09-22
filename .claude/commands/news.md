---
description: Đầu mục tin tức 20 phiên gần nhất của một mã, kèm trạng thái tin đã vào giá hay chưa
argument-hint: "MÃ [+ số phiên, vd 40] [+ ngày, vd 01/01/2025]"
allowed-tools: mcp__vn-ta__news_digest, mcp__vn-ta__news_transactions, mcp__vn-ta__news_impact, mcp__vn-ta__list_symbols
---

Liệt kê đầu mục tin tức cho: `$ARGUMENTS`

Dùng `mcp__vn-ta__news_digest`. Mặc định 20 phiên; nếu người dùng nêu số phiên khác
trong `$ARGUMENTS` thì truyền vào `sessions`.

**Kho chỉ lưu đầu mục** — tiêu đề, nguồn, ngày — cố ý không lưu toàn văn. Nếu người
dùng hỏi nội dung chi tiết một bài, nói rõ là kho không có và họ cần mở link nguồn.

## Đọc kết quả cho đúng

Bảng trả về gom theo **phiên**, không theo từng bài. Ba điều phải giữ khi tóm tắt:

- **Trạng thái là của phiên, không của một tiêu đề.** Một phiên thường có nhiều tin;
  không tách được tin nào làm giá chạy. Đừng viết "tin X làm giá tăng 4%" — viết
  "phiên có tin X tăng 4% so với thị trường".
- **`giá chạy trước tin` không phải là tin xấu.** Nó nói biến động nằm ở 5 phiên
  *trước* ngày tin ra. Có thể là rò rỉ, có thể là tin chỉ xác nhận thứ thị trường đã
  biết. Cả hai đều là *mô tả*, không phải cáo buộc.
- **`chưa phản ứng` chỉ có nghĩa khi đã đủ 10 phiên.** Trạng thái `chưa đủ phiên` và
  `mới 1 phiên` nghĩa là *chưa đo được*, khác hẳn *đã đo và thấy phẳng*. Đừng gộp hai
  cái thành "không ảnh hưởng".

Khi bảng kèm cảnh báo **chồng cửa sổ** (mã có tin gần như mỗi phiên), nhắc lại cảnh báo
đó — các dòng khi ấy không phải quan sát độc lập, cùng một cú chạy giá hiện ở nhiều dòng.

## Mốc thời gian

Có ngày trong `$ARGUMENTS` thì tách ra, truyền vào `as_of`. Ngày kiểu Việt Nam là
ngày/tháng/năm. Khi đó cả tin lẫn phép đo phản ứng đều bị cắt tại mốc — các phiên sát
mốc sẽ hiện `mới 1 phiên` / `chưa đủ phiên`, đó là đúng chứ không phải thiếu dữ liệu.

## Đi tiếp

- Muốn số đầy đủ của một giao dịch nội bộ (ba cửa sổ, volume, cờ trần/sàn) →
  `mcp__vn-ta__news_impact`.
- Muốn danh sách giao dịch nội bộ kèm tỷ lệ thực hiện → `mcp__vn-ta__news_transactions`.
- Kho rỗng → bảo người dùng chạy `update_news`.

Chỉ mô tả trạng thái, không đưa khuyến nghị mua/bán.
