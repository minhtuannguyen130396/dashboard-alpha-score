---
description: Thị trường phái sinh VN30 (basis, đáo hạn, dòng tiền hợp đồng) và ảnh hưởng của nó tới cổ phiếu
argument-hint: "[trống = toàn cảnh | MÃ1,MÃ2 | vn30 | 'thống kê'] [+ ngày]"
allowed-tools: mcp__vn-ta__futures_snapshot, mcp__vn-ta__futures_exposure, mcp__vn-ta__futures_stats, mcp__vn-ta__technical_report
---

Đọc thị trường phái sinh VN30 bằng MCP server `vn-ta`.

Tham số người dùng: `$ARGUMENTS`

## Chọn tool

| `$ARGUMENTS` chứa gì | Gọi gì |
|---|---|
| trống, hoặc "toàn cảnh", "hôm nay", "thị trường" | `futures_snapshot` |
| một hay nhiều mã, hoặc tên nhóm (`vn30`, `largecap`…) | `futures_snapshot` **rồi** `futures_exposure` với đúng bộ mã đó |
| "thống kê", "base rate", "lịch sử", "có đúng không" | `futures_stats` |

Khi người dùng hỏi về **một mã cụ thể**, luôn gọi cả `futures_snapshot` (trạng thái phái sinh
hôm nay) lẫn `futures_exposure` (mã đó nằm ở đâu trên đường lan truyền). Một mình bảng
exposure không trả lời được "hôm nay có gì" — nó là đặc tính dài hạn của mã, gần như không
đổi giữa hai phiên.

**Mốc thời gian.** Trong `$ARGUMENTS` mà có một ngày — `01/01/2025`, `2025-01-01`,
`ngày 15/06/2024` — thì tách ra khỏi danh sách mã và truyền vào `as_of`. Ngày kiểu Việt Nam
là ngày/tháng/năm; cứ truyền nguyên văn. Khi có mốc, mở đầu câu trả lời bằng một dòng nói rõ
đang đứng ở ngày nào, và đừng dùng thì hiện tại cho một phiên của quá khứ.

## In kết quả

In **nguyên văn** markdown tool trả về. Sau đó thêm phần đánh giá của bạn, tối đa 5 gạch đầu
dòng, theo đúng thứ tự nhân quả này:

1. **Phái sinh đang ở tư thế nào** — basis ở phân vị nào (ưu tiên phân vị *cùng quãng đường
   tới đáo hạn*, vì basis buộc phải hội tụ về 0 nên phân vị toàn cục lẫn lộn nhiều kỳ hạn),
   giữ được mấy phiên, đang nới hay đang thu hẹp.
2. **Ai đang đứng ở đó** — tự doanh và khối ngoại trên hợp đồng, 5 phiên gần nhất. Đây là
   dòng tiền *trên phái sinh*, khác dòng tiền khối ngoại trên cơ sở; nếu hai bên ngược chiều
   thì chính chỗ ngược đó là thông tin, đừng gộp lại.
3. **Đáo hạn còn bao xa** — dưới 3 phiên thì mọi phát biểu về basis phải kèm câu "đang hội tụ
   theo cơ chế", không được đọc như tín hiệu kỳ vọng.
4. **Chạm tới mã nào** — dùng cột trong bảng exposure: mã trong rổ VN30 chịu ảnh hưởng *cơ học*
   (lệnh arbitrage rơi thẳng vào), mã ngoài rổ chỉ chịu qua beta. Nêu đích danh 2–3 mã và nói
   rõ qua đường nào, kèm số.
5. **Chỗ nào không biết** — nêu thẳng nếu thiếu dữ liệu, nếu mẫu quá mỏng (`n` nhỏ, R² thấp,
   số kỳ đáo hạn ít), hoặc nếu basis đang ở vùng giữa và thật ra chẳng nói lên điều gì.

## Ranh giới

- **Mô tả trạng thái, không khuyến nghị.** "Basis chiết khấu ở phân vị 8%, tự doanh bán ròng
  310 tỷ trên hợp đồng trong 5 phiên" — được. "Nên hạ tỷ trọng" — không.
- **Đừng biến tương quan thành nhân quả.** `futures_stats` cho thấy chênh lệch giữa các nhóm
  basis là *nhỏ* và các quan sát chồng lấn nhau. Nếu định nói "basis chiết khấu báo hiệu
  giảm", phải kiểm bằng `futures_stats` trước, và nếu số không ủng hộ thì nói thẳng là không.
- **Đừng đọc % thay đổi của VN30F1M ở phiên nối hợp đồng.** Tool tự bỏ trống ô đó và ghi
  cảnh báo; nhắc lại cảnh báo thay vì tự tính lại.
- **% thanh khoản rổ không phải trọng số VN30.** Đừng gọi nó là trọng số chỉ số.
