---
description: Báo cáo kỹ thuật chi tiết cho một hoặc nhiều mã
argument-hint: "MÃ hoặc MÃ1,MÃ2,MÃ3 hoặc tên nhóm [+ ngày, vd 01/01/2025]"
allowed-tools: mcp__vn-ta__technical_report, mcp__vn-ta__list_symbols
---

Đọc báo cáo kỹ thuật chi tiết cho: `$ARGUMENTS`

Gọi `mcp__vn-ta__technical_report` với `symbols` = tham số trên.
Nếu không có dữ liệu, dùng `mcp__vn-ta__list_symbols` để gợi ý mã gần đúng.

**Mốc thời gian (nếu có).** Trong `$ARGUMENTS` mà có một ngày — `01/01/2025`, `2025-01-01`,
`ngày 15/06/2024` — thì tách nó ra khỏi danh sách mã và truyền vào tham số `as_of`. Nghĩa là
*giả định hôm nay là ngày đó*: mọi phiên sau mốc bị cắt bỏ, kể cả forecast. Ngày kiểu Việt Nam
là ngày/tháng/năm, tool tự hiểu — cứ truyền nguyên văn người dùng gõ.

Khi có mốc, **mở đầu câu trả lời bằng một dòng nói rõ đang đứng ở ngày nào**, và đừng dùng thì
hiện tại kiểu "giá đang ở…" cho một phiên của quá khứ. Nếu mốc rơi vào ngày nghỉ, tool báo lại
phiên gần nhất có thật — nhắc lại con số đó thay vì lặp lại ngày người dùng gõ.

In nguyên báo cáo markdown. Sau đó tóm tắt ngắn gọn từng mã theo 3 ý:
xu hướng đang ở đâu, động lượng (RSI/ADX) nói gì, và vùng giá nào đáng theo dõi.
Chỉ mô tả trạng thái kỹ thuật, không đưa khuyến nghị mua/bán.

Nếu người dùng muốn cùng nội dung này ở dạng file HTML kèm biểu đồ tương tác đã kẻ
trendline + hộp tích luỹ, chạy `/report <MÃ>` (tool `build_dossier`).
