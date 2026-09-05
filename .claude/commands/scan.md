---
description: Quét tín hiệu RSI14 / ADX14 theo lô cho một nhóm cổ phiếu
argument-hint: "[vn30|largecap|midcap|all|MÃ1,MÃ2] [số phiên gần nhất] [+ ngày]"
allowed-tools: mcp__vn-ta__scan_signals, mcp__vn-ta__list_presets
---

Quét tín hiệu kỹ thuật theo lô bằng MCP server `vn-ta`.

Tham số người dùng: `$ARGUMENTS`
- Từ đầu tiên là bộ mã (mặc định `vn30` nếu bỏ trống).
- Số ở cuối, nếu có, là `recent_bars` (mặc định 5).

Gọi `mcp__vn-ta__scan_signals` với đủ 5 luật:
`rsi_oversold_reclaim,rsi_overbought_loss,rsi_turning_up,rsi_turning_down,adx_momentum`
và `detail=true`.

**Mốc thời gian (nếu có).** Trong `$ARGUMENTS` mà có một ngày — `01/01/2025`, `2025-01-01`,
`ngày 15/06/2024` — thì tách nó ra khỏi danh sách mã và truyền vào tham số `as_of`. Nghĩa là
*giả định hôm nay là ngày đó*: mọi phiên sau mốc bị cắt bỏ, kể cả forecast. Ngày kiểu Việt Nam
là ngày/tháng/năm, tool tự hiểu — cứ truyền nguyên văn người dùng gõ.

Khi có mốc, **mở đầu câu trả lời bằng một dòng nói rõ đang đứng ở ngày nào**, và đừng dùng thì
hiện tại kiểu "giá đang ở…" cho một phiên của quá khứ. Nếu mốc rơi vào ngày nghỉ, tool báo lại
phiên gần nhất có thật — nhắc lại con số đó thay vì lặp lại ngày người dùng gõ.

In nguyên kết quả markdown ra cho người dùng. Sau bảng, thêm tối đa 3 gạch đầu dòng
nêu bật mã đáng chú ý nhất và lý do (hợp lưu RSI + ADX, có phân kỳ, điểm cao).
Không thêm khuyến nghị mua/bán.
