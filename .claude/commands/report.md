---
description: Báo cáo kỹ thuật ra file HTML — 1 mã có chart tương tác, nhiều mã là bảng tổng hợp
argument-hint: "MÃ (1–5 mã) hoặc vn30 / largecap / midcap [+ ngày, vd 01/01/2025]"
allowed-tools: mcp__vn-ta__build_dossier, mcp__vn-ta__build_report, mcp__vn-ta__list_symbols
---

Dựng báo cáo kỹ thuật cho: `$ARGUMENTS`

Chọn tool theo phạm vi:

- **1–5 mã cụ thể** (`FPT`, `HPG,ACB`) → `mcp__vn-ta__build_dossier`.
  Mỗi mã ra một file HTML tự chứa: biểu đồ TradingView tương tác (kéo/zoom, 5 pane) đã kẻ
  sẵn trendline, hộp tích luỹ vẽ thành hình chữ nhật, neckline và mục tiêu đo được — rê chuột
  lên một đường sẽ hiện lý do nó được vẽ — kèm toàn bộ nội dung `/deep-dive` bên dưới.
- **Tên nhóm** (`vn30`, `largecap`, `midcap`) → `mcp__vn-ta__build_report` với
  `with_charts=true`, `detail=true`, `max_images=3` (bảng tổng hợp + ảnh PNG tĩnh).

**Mốc thời gian (nếu có).** Trong `$ARGUMENTS` mà có một ngày — `01/01/2025`, `2025-01-01`,
`ngày 15/06/2024` — thì tách nó ra khỏi danh sách mã và truyền vào tham số `as_of`. Nghĩa là
*giả định hôm nay là ngày đó*: mọi phiên sau mốc bị cắt bỏ, kể cả forecast. Ngày kiểu Việt Nam
là ngày/tháng/năm, tool tự hiểu — cứ truyền nguyên văn người dùng gõ.

Khi có mốc, **mở đầu câu trả lời bằng một dòng nói rõ đang đứng ở ngày nào**, và đừng dùng thì
hiện tại kiểu "giá đang ở…" cho một phiên của quá khứ. Nếu mốc rơi vào ngày nghỉ, tool báo lại
phiên gần nhất có thật — nhắc lại con số đó thay vì lặp lại ngày người dùng gõ.

Báo cáo hồi tưởng ghi vào `reports/asof_<ngày>/` và mang sẵn một dải cảnh báo trong
chính file HTML, nên gửi file đi nơi khác vẫn không ai đọc nhầm thành số liệu hôm nay.

Nếu không có dữ liệu, dùng `mcp__vn-ta__list_symbols` để gợi ý mã gần đúng.

Trình bày: nêu đường dẫn file HTML trước (người dùng mở nó ra xem), sau đó tóm tắt.
Với hồ sơ 1 mã, tóm tắt đúng 3 ý: xu hướng đang ở đâu, động lượng (RSI/ADX) nói gì,
và mốc giá nào quyết định (kèm điều kiện volume nếu có).
Với báo cáo nhóm, kết thúc bằng 3–5 gạch đầu dòng xếp hạng mã đáng theo dõi,
mỗi dòng nêu rõ mốc giá quyết định.

Chỉ mô tả trạng thái kỹ thuật, không đưa khuyến nghị mua/bán.
