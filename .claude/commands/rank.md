---
description: Xếp hạng cả rổ theo cường độ xu hướng + độ tin cậy mẫu hình + phơi nhiễm phái sinh, hoặc sắp xếp lại bảng đã dựng
argument-hint: "để trống = dựng bảng cho all · hoặc 'vn30' · hoặc tiêu chí muốn sắp xếp [+ ngày]"
allowed-tools: mcp__vn-ta__build_ranking, mcp__vn-ta__rank_list, mcp__vn-ta__list_presets, mcp__vn-ta__build_prospect
---

Xếp hạng cổ phiếu: `$ARGUMENTS`

Chọn tool theo dạng tham số:

- **Để trống, hoặc tên nhóm** (`all`, `vn30`, `largecap`, `midcap`, danh sách mã)
  → `mcp__vn-ta__build_ranking`. Chấm điểm lại toàn bộ và ghi 2 file trong `reports/<ngày>/`:
  bảng HTML (bấm tiêu đề cột để tự sắp xếp) và file JSON tổng hợp. Mặc định `universe=all`.
- **Một tiêu chí sắp xếp** (`cường độ`, `độ tin cậy`, `rsi`, `rvol`, `mục tiêu`, `adx`…),
  kèm hướng (`tăng dần` / `giảm dần`) hoặc bộ lọc (`chỉ mã tăng`, `chỉ mẫu hình giảm`,
  `đã xác nhận`) → `mcp__vn-ta__rank_list`. Tool này **đọc lại file JSON** của lần
  `build_ranking` gần nhất, không tính lại — nhanh và luôn nhất quán với bảng HTML đang mở.
  Nếu chưa có bảng nào, tool báo lại; khi đó chạy `build_ranking` trước.

**Mốc thời gian (nếu có).** Trong `$ARGUMENTS` mà có một ngày — `01/01/2025`, `2025-01-01`,
`ngày 15/06/2024` — thì tách nó ra khỏi danh sách mã và truyền vào tham số `as_of`. Nghĩa là
*giả định hôm nay là ngày đó*: mọi phiên sau mốc bị cắt bỏ, kể cả forecast. Ngày kiểu Việt Nam
là ngày/tháng/năm, tool tự hiểu — cứ truyền nguyên văn người dùng gõ.

Khi có mốc, **mở đầu câu trả lời bằng một dòng nói rõ đang đứng ở ngày nào**, và đừng dùng thì
hiện tại kiểu "giá đang ở…" cho một phiên của quá khứ. Nếu mốc rơi vào ngày nghỉ, tool báo lại
phiên gần nhất có thật — nhắc lại con số đó thay vì lặp lại ngày người dùng gõ.

Bảng hồi tưởng **không** thay thế bảng của phiên thật (`build_ranking` không đụng tới
con trỏ `xep_hang_moi_nhat.json`). Nên khi người dùng xoay bảng đó theo tiêu chí khác,
phải truyền **lại cùng `as_of`** cho `rank_list` — bỏ quên là đọc nhầm sang bảng hôm nay.

Ánh xạ lời người dùng sang tham số `rank_list`:

| Người dùng nói | criterion | descending | lọc |
|---|---|---|---|
| "mã nào tăng mạnh nhất" | `trend` | true | `side=tăng` |
| "mã nào giảm sâu nhất" | `trend` | false | `side=giảm` |
| "mẫu hình tăng đáng tin nhất" | `confidence` | true | `bias=tăng` |
| "mã nào đã xác nhận rồi" | `confidence` | true | `min_confidence=đã xác nhận` |
| "sắp xếp ngược lại" | giữ nguyên | đảo | giữ nguyên |
| "RSI thấp nhất", "RVOL cao nhất" | `rsi` / `rvol` | tuỳ | — |
| "thanh khoản cao nhất", "mã nào giao dịch nhiều nhất" | `liquidity` | true | — |
| "mã nào chịu ảnh hưởng phái sinh nhất" | `futures` | true | — |
| "beta cao nhất so với VN30" | `beta` | true | — |

**Trình bày trong chat:** in bảng tool trả về, rồi **diễn giải bằng lời** — không để người
dùng tự đọc số. Nêu rõ:

1. Bảng đang sắp theo tiêu chí gì, hướng nào, lọc những gì.
2. 3–5 mã đầu bảng: điểm của chúng đến từ thành phần nào (cột *Vì sao* đã có sẵn lý do —
   ADX, xếp tầng EMA, chuỗi swing, quãng đường ATR, hay volume xác nhận).
3. Chỗ hai cách đọc xu hướng lệch nhau (dấu ⚠️): EMA nói một đằng, cấu trúc swing nói một nẻo
   — nói rõ mã nào, lệch ra sao.
4. Mốc giá quyết định của các mã đầu bảng (mốc kích hoạt / mục tiêu / mức huỷ).

**Muốn một danh sách ứng viên chứ không phải cả bảng?** Nếu người dùng hỏi "mã nào
đáng nhìn", "triển vọng cao", "lọc mã đang có mẫu hình tăng", "có cả tin tức và chỉ số
cơ bản" — đó là `/prospect` → `mcp__vn-ta__build_prospect`, không phải tool ở đây.
Bảng xếp hạng trả lời *cả rổ đang ở đâu*; danh sách triển vọng trả lời *nên nhìn kỹ mã
nào*, và nó gộp thêm định giá so với ngành, giao dịch nội bộ và nhận định tin tức.

Ba cột điểm cố ý không cộng vào nhau, vì chúng trả lời ba câu hỏi khác nhau: cường độ
xu hướng là *đang chạy mạnh cỡ nào*, độ tin cậy mẫu hình là *bằng chứng đã đủ tới đâu*,
phơi nhiễm phái sinh là *mã này nằm gần dòng tiền hợp đồng tới đâu*. Mã đáng chú ý nhất
thường là mã có hai cột nói ngược nhau — nêu ra chứ đừng gộp lại thành một nhãn.

**Bối cảnh phái sinh ở đầu bảng là lực nền chung**, không phải số của riêng mã nào. Khi
khối đó báo còn ≤ 3 phiên tới đáo hạn, hoặc basis đang ở phân vị cực trị, thì nói rõ ở
phần diễn giải rằng các mã đầu bảng có beta cao và nằm trong rổ VN30 đang chịu thêm một
lực không đến từ chính chúng. Nếu khối đó kèm cảnh báo lệch phiên (phái sinh mới hơn phần
còn lại), nhắc người dùng chạy `/update` thay vì đọc lướt qua.

Chỉ mô tả trạng thái kỹ thuật, không đưa khuyến nghị mua/bán.
