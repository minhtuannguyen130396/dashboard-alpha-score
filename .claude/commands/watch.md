---
description: Đối chiếu các forecast đã đặt với dữ liệu mới nhất và báo thay đổi
argument-hint: "[MÃ1,MÃ2 — bỏ trống = tất cả] [closed] [+ ngày]"
allowed-tools: mcp__vn-ta__check_forecasts, mcp__vn-ta__create_forecasts
---

Kiểm tra forecast: `$ARGUMENTS`

Gọi `mcp__vn-ta__check_forecasts`. Nếu tham số có chữ `closed` thì đặt
`include_closed=true`, phần còn lại là danh sách mã (bỏ trống = tất cả).

**Mốc thời gian (nếu có).** Trong `$ARGUMENTS` mà có một ngày — `01/01/2025`, `2025-01-01`,
`ngày 15/06/2024` — thì tách nó ra khỏi danh sách mã và truyền vào tham số `as_of`. Nghĩa là
*giả định hôm nay là ngày đó*: mọi phiên sau mốc bị cắt bỏ, kể cả forecast. Ngày kiểu Việt Nam
là ngày/tháng/năm, tool tự hiểu — cứ truyền nguyên văn người dùng gõ.

Khi có mốc, **mở đầu câu trả lời bằng một dòng nói rõ đang đứng ở ngày nào**, và đừng dùng thì
hiện tại kiểu "giá đang ở…" cho một phiên của quá khứ. Nếu mốc rơi vào ngày nghỉ, tool báo lại
phiên gần nhất có thật — nhắc lại con số đó thay vì lặp lại ngày người dùng gõ.

Với `as_of`, `check_forecasts` chỉ xét forecast tạo trước mốc và replay tới mốc; kết quả
**không** ghi đè trạng thái thật trên đĩa, nên chạy thử thoải mái.

In nguyên kết quả. Nếu có mục "🔔 forecast đổi trạng thái", nhấn mạnh phần đó lên đầu
câu trả lời — đây là điều người dùng cần biết ngay.

Nếu chưa có forecast nào đang mở, nói rõ và gợi ý chạy
`mcp__vn-ta__create_forecasts` cho nhóm mã họ quan tâm (đừng tự chạy khi chưa được yêu cầu).
