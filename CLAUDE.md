# dashboard-alpha-score

Công cụ phân tích kỹ thuật cổ phiếu Việt Nam. Dữ liệu giá nằm local ở `data/<MÃ>/<năm>/*.json`
(**80 mã + VNINDEX**, 2010→nay), nguồn FireAnt API.

**VNINDEX, VN30 và VN30F1M không phải cổ phiếu.** Cả ba nằm trong `data/` cùng chỗ với
80 mã và đọc bằng đúng đường `StockRecord`, nhưng: VNINDEX là **thị trường chung**, VN30 là
**tài sản cơ sở** của hợp đồng tương lai, VN30F1M+ là **hợp đồng phái sinh**. Không cái nào
xuất hiện trong rổ quét/xếp hạng (xem "Quy ước phải giữ").

Có **plugin MCP `vn-ta`** khai báo ở `.mcp.json` — đây là đường chính để làm việc với dự án này.
Kiến trúc chi tiết: đọc `AGENTS.md`.

## Người dùng muốn gì → chạy gì

| Người dùng nói | Dùng |
|---|---|
| "cập nhật giá", "lấy giá mới nhất" | `/update` → `update_prices_tool` |
| "mã nào có tín hiệu", "quét RSI/ADX", "lọc cổ phiếu" | `/scan` → `scan_signals` |
| "vẽ trendline", "hộp tích luỹ", "cấu trúc giá", "hình mẫu" | `/structure` → `analyze_structure` |
| "vai đầu vai", "2 đỉnh", "mô hình đảo chiều", "có mẫu hình gì không" | `/structure` → `analyze_structure` |
| "kháng cự ở đâu", "vùng giá quan trọng", "volume profile" | `/structure` → `analyze_structure` |
| "xu hướng thật sự", "cấu trúc tăng hay giảm", "BOS", "CHoCH" | `/deep-dive` → `technical_report` |
| "phiên hôm nay thế nào", "nến hôm nay", "volume có bất thường không" | `/deep-dive` → `technical_report` |
| "xem chi tiết mã X", "chỉ báo của X" | `/deep-dive` → `technical_report` |
| "báo cáo mã X", "xuất file HTML", "chart có trendline + hộp để tự xem" | `/report <MÃ>` → `build_dossier` |
| "báo cáo", "tổng hợp nhiều mã", "cả rổ VN30" | `/report <nhóm>` → `build_report` |
| "báo cáo tất cả cổ phiếu", "xếp hạng cả rổ", "mã nào tăng mạnh nhất" | `/rank` → `build_ranking` |
| "sắp xếp theo <tiêu chí>", "từ cao xuống thấp", "mã nào đã xác nhận" | `/rank <tiêu chí>` → `rank_list` |
| "kiểm tra kỳ vọng", "có gì mới không" | `/watch` → `check_forecasts` |
| "đặt kỳ vọng cho mã này" | `create_forecasts` |
| "phái sinh hôm nay thế nào", "basis", "chênh lệch VN30F1M", "hợp đồng tương lai" | `/futures` → `futures_snapshot` |
| "sắp đáo hạn chưa", "phiên đáo hạn", "thứ Năm thứ ba" | `/futures` → `futures_snapshot` |
| "phái sinh ảnh hưởng mã X thế nào", "mã nào chịu ảnh hưởng phái sinh" | `/futures <MÃ>` → `futures_exposure` |
| "basis chiết khấu có báo hiệu giảm không", "có đúng không", "base rate phái sinh" | `futures_stats` |
| "lãnh đạo có mua bán gì không", "giao dịch nội bộ", "cổ đông lớn" | `news_transactions` |
| "tin/giao dịch đó ảnh hưởng thế nào", "đã vào giá chưa" | `news_impact` |
| "loại giao dịch này thường làm giá chạy bao nhiêu" | `news_stats` |
| "nạp tin tức", "cập nhật sự kiện" | `update_news` |
| "plugin này làm được gì" | `/ta` → `usage_guide` |
| "…ngày 01/01/2025", "giả sử hôm nay là…", "hồi đó thế nào" | thêm `as_of` vào tool tương ứng |

Không nhớ command cũng không sao — cứ mô tả bằng tiếng Việt, chọn tool theo bảng trên.

## Mốc thời gian (`as_of`) — giả định hôm nay là một ngày trong quá khứ

Mọi tool báo cáo (`technical_report`, `scan_signals`, `analyze_structure`, `build_report`,
`build_dossier`, `build_ranking`, `rank_list`, `create_forecasts`, `check_forecasts`) nhận
thêm `as_of`. "Báo cáo FPT ngày 01/01/2025" = truyền `as_of="01/01/2025"`: mọi phiên sau mốc
bị cắt bỏ, kể cả forecast, nên kết quả đúng bằng những gì biết được tại ngày đó.

- **Ngày kiểu Việt Nam là ngày/tháng/năm.** `05/03/2025` là mùng 5 tháng 3. Dạng ISO
  (`2025-03-05`) vẫn đọc như ISO — phân biệt bằng số chữ số của nhóm đầu (`src/ta/asof.py`).
- **Mốc hôm nay trở đi = không có mốc.** `parse()` trả `None`, mọi tầng trên chỉ phải kiểm
  tra một điều kiện `as_of is None`.
- **Luôn in ra hai ngày.** Mốc *yêu cầu* và phiên cuối *có thật* lệch nhau mỗi khi mốc rơi
  vào ngày nghỉ (01/01/2025 → 31/12/2024). Dải cảnh báo trong `format.asof_note` nói cả hai.
- **File hồi tưởng ghi riêng** vào `reports/asof_<ngày>/`, tên file mang chính mốc đó nên
  chạy lại là ghi đè chứ không rải bản trùng. Không bao giờ đè lên báo cáo của phiên thật.
- **Bảng xếp hạng hồi tưởng không đụng `reports/xep_hang_moi_nhat.json`.** Muốn xoay lại
  bảng đó thì `rank_list` phải nhận **cùng** `as_of` — nó tìm file trong `reports/asof_<ngày>/`.
- **Forecast không được ghi đè khi hồi tưởng.** `check_forecasts` với `as_of` chỉ xét forecast
  tạo trước mốc, replay tới mốc, và `persist=False` — file forecast là trạng thái *hôm nay*.

## Nhịp dùng hàng ngày

1. `/update` — nạp phiên mới nhất (80 mã + VNINDEX + VN30 + 4 hợp đồng phái sinh, ~15s).
   Chú ý mục "⚠️ mã còn thiếu dữ liệu" nếu có: chạy lại các mã đó với `mode=quarter`.
2. `/futures` — thị trường phái sinh đang ở tư thế nào, còn mấy phiên tới đáo hạn.
3. `/watch` — forecast nào đổi trạng thái.
4. `/scan` — tín hiệu mới trong 5 phiên gần nhất.
5. `/rank` — xếp hạng cả rổ; sau đó `/rank <tiêu chí>` để xoay bảng theo góc khác
   (đọc lại file JSON, không tính lại).
6. `/structure <MÃ>` cho mã đáng chú ý.

## Quy ước phải giữ

- **VNINDEX là thị trường, không phải cổ phiếu.** FireAnt trả nó với **đúng schema như
  một mã** (`adjRatio: 1.0`, đủ OHLC + volume) — chính sự giống nhau đó là cái bẫy: để
  yên thì `resolve_universe(None)` phát nó cho mọi lần quét và xếp hạng, và cả thị
  trường hiện ra thành một dòng đứng cạnh từng cổ phiếu. Sai hai đường: (1) không ai
  *mua* được chỉ số, nên nó không phải ứng viên; (2) nến của nó là số bình quân, nên
  ADX, RSI và chuỗi swing đều **mượt hơn** mọi mã thành phần — thêm một dòng như vậy là
  lệch âm thầm mọi phân vị trong `ranking.py`.
  Vì thế benchmark nằm ở registry riêng `stock_list/benchmarks.json` và bị `loader.py`
  loại khỏi **mọi nhóm** (`all`, `vn30`, `disk`, `None`). Muốn có thì phải **gọi đích
  danh**: `resolve_universe("VNINDEX")`, `"FPT,VNINDEX"`, hoặc nhóm `benchmarks`.
  `/update` vẫn nạp nó cùng cả rổ — chỉ số cũ mà không ai biết còn tệ hơn không có.
  Việc của nó là **so sánh**: một mã tăng 8% trong tháng mà VNINDEX tăng 9% thì đó là
  *tụt lại*, chứ không phải khoẻ — con số tuyệt đối một mình không nói được điều đó.
- **Hợp đồng phái sinh cũng bị loại khỏi rổ, một nấc gắt hơn VNINDEX.** VN30F1M/F2M/F1Q/F2Q
  nằm ở `stock_list/derivatives.json`; VN30 (tài sản cơ sở) nằm cùng VNINDEX ở
  `benchmarks.json`. Để lọt vào rổ thì VN30F1M xếp hạng như một "mã" giá ~1980 "đồng", volume
  của nó là **số hợp đồng** chứ không phải cổ phiếu, và ATR thổi bay mọi phân vị trong
  `ranking.py`. Lấy được chỉ bằng cách gọi đích danh, hoặc nhóm `futures` / `benchmarks`.
- **`VN30F1M` là chuỗi nối, không phải một hợp đồng.** Sau mỗi phiên đáo hạn (thứ Năm thứ ba)
  FireAnt cho mã này nhảy sang hợp đồng tháng kế tiếp, nên **% thay đổi qua đúng đường nối là
  số giả**. `futures.roll_indices()` đánh dấu các đường nối; `format_futures` bỏ trống ô % và
  ghi cảnh báo ở phiên đó thay vì in một cú chạy 7% không có thật. Basis không dính lỗi này —
  nó là hiệu hai mức giá trong *cùng* một phiên.
- **Basis phải đọc kèm quãng đường tới đáo hạn.** Nó **buộc phải** hội tụ về 0 vào phiên đáo
  hạn, đó là cơ chế chứ không phải tâm lý: −8 điểm khi còn 18 phiên là chiết khấu thật, −8
  điểm khi còn 1 phiên gần như chỉ là nhiễu. Vì thế `futures.py` trả **hai** phân vị — một
  trên 250 phiên gần nhất, một chỉ trên các phiên cùng quãng đường tới đáo hạn (±3) — và câu
  đọc luôn ưu tiên phân vị thứ hai.
- **"% thanh khoản rổ" không phải trọng số VN30.** Trọng số chỉ số tính theo vốn hoá free
  float có trần 10%, dữ liệu đó không nằm trong `data/`. Cái đo được là tỷ trọng giá trị khớp
  lệnh — nó trả lời câu khác (lệnh mua/bán cả rổ rơi vào đâu nhiều nhất), nên nhãn phải giữ
  đúng chữ "thanh khoản".
- **Volume**: `priceImpactVolume` = `dealVolume` cho mọi chỉ báo liên quan giá.
  `totalVolume` là tổng sàn (deal + thoả thuận), không dùng cho chỉ báo.
- **Cache**: `src/ta/loader._load_year` khoá theo `(mã, năm, chữ ký file)` nên tự hết hạn khi
  file đổi. Nếu sửa chỗ này, phải soi mtime **từng file** — mtime thư mục không đổi khi ghi
  đè file tại chỗ.
- **MCP stdio**: mọi tool phải chạy trong `_quiet()` (stdout → stderr). Một dòng `print()`
  lọt ra stdout là phá luồng JSON-RPC.
- **File HTML xuất ra phải tự chứa**: hồ sơ 1 mã (`dossier.py`) nhúng luôn thư viện
  Lightweight Charts từ `src/reporting/vendor/`, kèm CSS + JS của chart. Không được thay
  bằng link CDN — file còn phải mở được khi offline hoặc sau khi gửi đi nơi khác.
- **Chữ nghĩa trong file HTML lấy từ `format.py`**: dossier render lại markdown của
  `format_snapshot` / `format_structure` chứ không tự viết câu. Sửa một câu ở `format.py`
  là cả terminal lẫn file HTML đổi theo.
- **Cách diễn đạt**: output mô tả *trạng thái kỹ thuật* ("breakout xác nhận bằng volume 1.7×"),
  không đưa khuyến nghị mua/bán. Giữ dòng disclaimer trong `src/ta/format.py`.
- **Nến chỉ đọc trong vùng quyết định**: `confluence.py` chỉ quét nến ở Z1 (đỉnh/đáy cuối
  của mô hình), Z2 (phiên phá neckline), Z3 (retest), Z4 (10 phiên gần nhất, tìm tín hiệu
  ngược chiều). Đừng nới ra quét cả chuỗi — nhân chéo hai tín hiệu nhiễu ra nhiễu bình phương.
- **Phiên trần/sàn không đọc được hình nến**: đóng cửa giá trần trông y hệt marubozu tăng
  nhưng nghĩa ngược lại (dư mua chất đống, không phải lực mua thắng). `candles.py` nhận diện
  qua `priceBasic` rồi loại khỏi mọi bộ phân loại hình nến — `vsa.py` cũng bỏ qua các phiên này.
- **Hai cách đọc xu hướng, in cả hai**: EMA20/EMA50 là ý kiến đã làm mượt; chuỗi swing HH/HL
  trong `swings.py` là điều chính chuỗi giá nói ra. Khi hai bên lệch nhau thì chính chỗ lệch
  là thông tin — đừng gộp lại thành một nhãn.
- **Đỉnh/đáy bằng nhau là EQH/EQL, không phải LH/LL**: so sánh tuyệt đối làm một vùng đi ngang
  phẳng bị đọc thành downtrend. Dung sai 0.25×ATR trong `swings.py`.
- **Hai điểm xếp hạng không được cộng vào nhau**: `ranking.py` trả *cường độ xu hướng*
  (−100…+100, đang chạy mạnh cỡ nào) và *độ tin cậy mẫu hình* (0–100, bằng chứng đã đủ tới
  đâu) thành hai cột riêng. Gộp lại thành một "điểm cổ phiếu" là giấu đúng trường hợp đáng
  chú ý nhất: mẫu hình đảo chiều đã xác nhận nằm ngược xu hướng đang chạy.
- **Xếp hạng lại thì đọc file JSON, đừng dựng lại**: `build_ranking` ghi `xep_hang_*.json`
  kèm bản trỏ cố định `reports/xep_hang_moi_nhat.json`; `rank_list` đọc lại file đó nên mọi
  cách sắp xếp đều nhất quán với file HTML người dùng đang mở.

## Chạy

```bash
python -m pytest tests/ -q          # 444 test
python main.py                      # UI tkinter (chỉ còn dùng để xem chart nhanh)
```

Cần token FireAnt trong `access_token.txt` hoặc biến môi trường `FIREANT_BEARER_TOKEN`
để `/update` chạy được.
