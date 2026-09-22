---
description: Vẽ trendline + bounding box và giải thích cấu trúc giá
argument-hint: "MÃ hoặc MÃ1,MÃ2 [số ngày lịch sử] [+ ngày, vd 01/01/2025]"
allowed-tools: mcp__vn-ta__analyze_structure, mcp__vn-ta__list_symbols
---

Phân tích cấu trúc giá cho: `$ARGUMENTS`

Từ đầu tiên là mã (hoặc danh sách mã / tên nhóm). Số ở cuối, nếu có, là `lookback_days`
(mặc định 180).

Gọi `mcp__vn-ta__analyze_structure` với `with_chart=true`.

**Mốc thời gian (nếu có).** Trong `$ARGUMENTS` mà có một ngày — `01/01/2025`, `2025-01-01`,
`ngày 15/06/2024` — thì tách nó ra khỏi danh sách mã và truyền vào tham số `as_of`. Nghĩa là
*giả định hôm nay là ngày đó*: mọi phiên sau mốc bị cắt bỏ, kể cả forecast. Ngày kiểu Việt Nam
là ngày/tháng/năm, tool tự hiểu — cứ truyền nguyên văn người dùng gõ.

Khi có mốc, **mở đầu câu trả lời bằng một dòng nói rõ đang đứng ở ngày nào**, và đừng dùng thì
hiện tại kiểu "giá đang ở…" cho một phiên của quá khứ. Nếu mốc rơi vào ngày nghỉ, tool báo lại
phiên gần nhất có thật — nhắc lại con số đó thay vì lặp lại ngày người dùng gõ.

Trình bày kết quả theo thứ tự: bảng bounding box → danh sách đường xu hướng →
phần diễn giải → ảnh biểu đồ. Giữ nguyên ID (`#1`, `#2`…) của hộp và từng đường —
ID hiện cả trên ảnh biểu đồ, người dùng sẽ hỏi lại theo ID đó.

Khi người dùng hỏi về một ID, trả lời hai ý, mỗi ý một câu:
- **Vì sao vẽ như vậy**: hai pivot làm neo (ngày + giá), số lần chạm, giá chưa xuyên qua
  trong đoạn đó.
- **Ý nghĩa**: đường đang ở mức nào, giá cách bao nhiêu %, còn hiệu lực hay đã phá vỡ.

Sau đó thêm đúng 3 gạch đầu dòng:
1. Mốc giá nào kích hoạt kịch bản tăng (kèm điều kiện volume nếu có).
2. Mốc giá nào làm hỏng cấu trúc.
3. Hiện tại giá đang ở đâu giữa hai mốc đó.

Chỉ mô tả trạng thái kỹ thuật, không đưa khuyến nghị mua/bán.
