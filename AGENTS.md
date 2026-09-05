## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `python3 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"` to keep the graph current

## Project Overview

Công cụ xem biểu đồ kỹ thuật cổ phiếu Việt Nam. Entry point: `main.py` → `create_stock_selector_app()` (desktop UI tkinter).

**Luồng chính:**
1. User chọn mã cổ phiếu + khoảng ngày trong UI
2. Fetch lịch sử giá từ FireAnt API (`src/data/fireant_history_fetcher.py`)
3. Tính chỉ báo kỹ thuật (`src/analysis/technical_indicators.py`) — tự cài đặt bằng Python thuần, không dùng thư viện TA
4. `analyze_market_behavior` (`src/analysis/market_behavior_analyzer.py`) dựng chuỗi overlay theo ngày: EMA20/50, ATR14, EMA volume, big buyer / fomo retail, cùng hover payload (RSI14, MACD, ADX14, MFI14, OBV slope, swing high/low 10-20 phiên)
5. `run_chart` (`src/reporting/chart_runner.py`) nối data loader → analyzer → renderer
6. HTML chart tương tác render qua TradingView Lightweight Charts (`src/reporting/chart_renderer_v2.py` + `.js` + `.css`), xuất ra `chart/<ngày>/`

Phần chấm điểm tín hiệu mua/bán (Signal Score V4), Smart Money (V5) và backtest / trade simulator đã được gỡ bỏ. Chart chỉ hiển thị giá, volume và chỉ báo kỹ thuật — không còn marker mua/bán, score strip hay bảng lịch sử giao dịch.

**Abstractions cốt lõi:**
- `StockRecord` — một phiên giao dịch (OHLC + `dealVolume` + dòng tiền tự doanh/khối ngoại); `priceImpactVolume` = `dealVolume` là quy ước volume cho mọi chỉ báo
- `MarketBehaviorSnapshot` — chuỗi dữ liệu theo ngày cho chart renderer
- `IndicatorGroup1..6` — các nhóm chỉ báo kỹ thuật trong `technical_indicators.py` (MA, oscillator, volatility, volume, breadth, pivot)

## Plugin phân tích kỹ thuật qua MCP (`vn-ta`)

Server MCP stdio cho Claude Code, đọc trực tiếp dữ liệu local trong `data/`.
Khai báo ở `.mcp.json` (project-scoped), chạy bằng `python -m src.mcp_server`.

**Lớp engine (`src/ta/`) — thuần Python, không phụ thuộc MCP:**
- `config.py` — mọi ngưỡng RSI/ADX, 3 profile: `standard` (30/70), `aggressive` (35/65), `strict` (25/75)
- `loader.py` — universe (`vn30`/`largecap`/`midcap`/`all`/danh sách mã) + nạp giá theo từng năm, cache `lru_cache`. Nhanh hơn `load_stock_history` ~17× vì không duyệt hết 2010–2026.
  **Benchmark tách khỏi universe:** `stock_list/benchmarks.json` giữ VNINDEX (và chỉ số
  khác nếu thêm sau); `resolve_universe()` loại chúng khỏi **mọi nhóm** — `None`, `disk`,
  `all`, `vn30` — kể cả khi file nhóm lỡ liệt kê. FireAnt trả chỉ số với *đúng* schema
  của một mã (`adjRatio: 1.0`, đủ OHLC + volume), nên không tầng nào phía dưới phân biệt
  được: để yên là cả thị trường thành một dòng đứng xếp hạng cạnh từng cổ phiếu, mà nến
  chỉ số là số bình quân nên ADX/RSI/swing của nó mượt hơn hẳn — lệch âm thầm mọi phân vị
  trong `ranking.py`. Lấy được chỉ số **chỉ bằng cách gọi đích danh**:
  `resolve_universe("VNINDEX")`, `"FPT,VNINDEX"`, hoặc nhóm `benchmarks`/`index`.
  **Hợp đồng phái sinh cũng vậy, một nấc nặng hơn:** `stock_list/derivatives.json` giữ
  VN30F1M/F2M/F1Q/F2Q, cũng bị loại khỏi mọi nhóm. Để lọt vào rổ thì VN30F1M xếp hạng như một
  "mã" giá ~1980 "đồng", volume là **số hợp đồng** chứ không phải số cổ phiếu, và ATR của nó
  thổi bay mọi phân vị trong `ranking.py`. Lấy bằng cách gọi đích danh hoặc nhóm `futures`.
  Chỉ số VN30 nằm ở registry benchmark cùng VNINDEX — nó là **tài sản cơ sở** của hợp đồng.
  Ngược lại `update.update_prices` **cộng benchmark vào** khi yêu cầu là *cả rổ*
  (`include_benchmarks=True`) — loại khỏi rổ quét là đúng, nhưng loại khỏi lượt nạp thì
  chỉ số nằm im mốc dần cho tới lúc có người đem nó ra đo. Xin đích danh vài mã thì vẫn
  đúng bấy nhiêu mã đó
- `indicators_ext.py` — `adx_di()` trả `(ADX, +DI, -DI)`; `IndicatorGroup3.adx` tính +DI/-DI rồi bỏ đi nên không biết được hướng xu hướng
- `signals.py` — state machine RSI14 (vào vùng cực trị → quay đầu → chạm lại ngưỡng = sự kiện) và `adx_state()` phân vùng động lực
- `snapshot.py` — toàn bộ bức tranh kỹ thuật của 1 mã, JSON-serializable
- `scan.py` — quét theo lô đa luồng, chấm điểm hợp lưu RSI + ADX
- `pivots.py` — swing pivot dạng fractal, lọc nhiễu bằng ATR rồi ép xen kẽ H/L (ZigZag)
- `trendlines.py` — fit mọi cặp pivot cùng phía; loại đường bị giá xuyên qua giữa 2 điểm neo, chấm điểm theo **độ gần giá + độ mới + số lượt chạm**. Đường đã phá vỡ quá 25 phiên bị bỏ hẳn. `touches` đếm **lượt chạm**, không đếm số phiên
- `boxes.py` — hộp tích luỹ (range ≤ 3×ATR trong ≥ 8 phiên); breakout phân biệt *có volume xác nhận* (≥ 1.5× EMA20 volume) / *volume yếu* / *phá vỡ giả*; mục tiêu = chiều cao hộp chiếu ra
- `patterns.py` — ghép độ dốc 2 đường thành tam giác tăng/giảm/cân, kênh giá, nêm, hình chữ nhật, kèm câu lý giải
- `candles.py` — giải phẫu nến (thân/râu/vị trí đóng cửa/biên độ theo ATR) + 13 mẫu 1–3 nến.
  Cố ý **không biết ngữ cảnh**: chỉ trả hình dạng và độ "sạch", việc vị trí có ý nghĩa hay
  không là của người gọi. Nhận diện phiên trần/sàn từ `priceBasic` và loại chúng khỏi bộ
  phân loại — nến trần trông giống marubozu nhưng nghĩa ngược lại
- `formations.py` — mô hình đảo chiều đọc từ **chuỗi pivot**: 2 đỉnh/đáy, 3 đỉnh/đáy, vai đầu
  vai + ngược. Ba ràng buộc chống nhận nhầm: phải có xu hướng trước đó để đảo, tỷ lệ đo bằng
  ATR chứ không phải %, và xác nhận bằng **đóng cửa** thủng neckline chứ không phải râu nến.
  Neckline nghiêng bị chặn hai lớp: dốc quá `max_tilt`×chiều cao thì loại (đáy đang sụp =
  downtrend chứ không phải nền tạo đỉnh), và ngoại suy tối đa 30 phiên rồi giữ phẳng
- `confluence.py` — hợp lưu hình mẫu × nến × volume. Mô hình định ra 4 vùng quyết định
  (Z1 đỉnh/đáy cuối · Z2 phiên phá neckline · Z3 retest · Z4 tín hiệu ngược chiều gần đây),
  **chỉ đọc nến trong các vùng đó**. Trả về 3 mức (`full` / `partial` / `conflict`) kèm danh
  sách *còn thiếu gì* — đó mới là output dùng được, không phải một con số 0–1
- `swings.py` — cấu trúc thị trường: gắn nhãn HH/HL/LH/LL (và **EQH/EQL** khi hai swing
  ngang nhau trong 0.25×ATR — thiếu nhãn này thì vùng đi ngang bị đọc thành downtrend), rồi
  sinh sự kiện **BOS** (đi tiếp) / **CHoCH** (lần đầu bị bẻ). Mốc bị *tiêu thụ* khi vỡ nên một
  đỉnh chỉ bắn một BOS; pivot chỉ dùng được sau `confirm_lag` phiên, không nhìn trước
- `levels.py` — kháng cự/hỗ trợ **ngang** bằng gom cụm pivot theo ATR, cộng volume profile
  (volume rải đều trên biên độ từng phiên chứ không dồn vào giá đóng cửa) và các khoảng trống
  giá chưa lấp. Gap coi là đã lấp khi giá về tới mép xa, không đòi một phiên phủ hết
- `vsa.py` — effort vs result: cao trào mua/bán, volume lớn mà giá không đi, tăng không có cầu,
  giảm không có cung, volume cạn kiệt. Cố ý không biết ngữ cảnh giống `candles.py`
- `retest.py` — helper dùng chung cho hộp, trendline và neckline: giá có quay lại mốc vừa phá
  và mốc đó có đổi vai không. Hai vế bắt buộc — *chạm* trong phiên và *đóng cửa* phía bên kia
- `structure.py` — gộp tất cả thành `Structure` (gồm `market`, `levels`, `profile`,
  `formations` + `evidence`) + phần
  `brief` diễn giải từng mốc giá; `brief` là thứ chảy tiếp vào báo cáo HTML và chart
- `render.py` — vẽ PNG bằng matplotlib (nến + EMA + box + trendline + pane RSI/ADX) và `render_interactive()` xuất chart HTML có overlay
- `overlays.py` — chuyển `Structure` thành payload `OVERLAY_DATA` cho `chart_renderer_v2.js`.
  Hộp tích luỹ đi ra **hai đường**: `boxes` (hình chữ nhật vẽ đúng số phiên nó chiếm, do
  series primitive của Lightweight Charts vẽ) và `lines` (cạnh nét đứt chiếu tới mép phải —
  chỗ giá vẫn đang giao dịch quanh đó). Mỗi đường mang 2 tên: `label` ngắn in trên trục giá
  (`#2`, `L1`), `title` đầy đủ hiện khi rê chuột — in tên dài lên trục thì mất 1/4 bề ngang chart
- `forecast.py` — kỳ vọng kiểm chứng được: điều kiện kích hoạt (+volume), mục tiêu, mức huỷ, hạn phiên.
  Mô hình đảo chiều khớp 1-1 với schema này (neckline = trigger, measured move = target,
  vai phải = invalidation) nên sinh ra `basis="neckline_break"` / `"neckline_running"`. `propose()` sinh từ cấu trúc, `evaluate()` **replay lại toàn bộ phiên sau ngày tạo** nên file lưu chỉ là cache — sửa tay hay hỏng thì lần kiểm tra sau tự chữa. Lưu ở `forecasts/<id>.json`
- `report.py` — báo cáo tổng hợp **nhiều mã**: bảng tổng quan + forecast + chi tiết từng mã. Ghi file HTML **tự chứa** (ảnh base64, không request mạng) ở `reports/<ngày>/`
- `ranking.py` — chấm điểm và **xếp hạng cả rổ** (mặc định `all`, 79 mã, ~5 s; VNINDEX bị loại, xem `loader.BENCHMARK_FILE`). Không đo
  thêm gì mới: xu hướng lấy từ `snapshot` + `swings`, mẫu hình lấy từ
  `formations`/`confluence`/`boxes`, câu chữ mượn nguyên của các module đó. Cái nó thêm vào
  là **thứ tự**. Hai trục cố ý tách rời:
  *cường độ xu hướng* (−100…+100) = ADX×hướng (±30) + xếp tầng EMA (±25) + chuỗi swing kèm
  BOS/CHoCH (±25) + quãng đường 20 phiên **đo bằng ATR** chứ không phải phần trăm (±20) —
  mỗi thành phần bị chặn trần nên không thành phần nào một mình kéo nổi một hạng;
  *độ tin cậy mẫu hình* (0–100) = **lượng bằng chứng đã tới**, không phải kích thước kỳ vọng,
  kèm nhãn `đã xác nhận` / `xác nhận một phần` / `chưa xác nhận` / `mâu thuẫn` / `hỏng`.
  Nguồn mẫu hình chọn theo **trạng thái, không theo loại**: hộp tích luỹ còn sống thắng mô
  hình đảo chiều đã hỏng; mô hình hỏng chỉ nổi lên khi không còn gì sống, và khi đó nó nổi
  lên đúng với nghĩa "mốc này thôi không dùng nữa". Xuất 2 file ở `reports/<ngày>/`: HTML tự
  chứa (4 bảng xếp sẵn + bảng toàn rổ bấm tiêu đề cột để sắp xếp, lọc theo mã/theo hướng +
  chi tiết từng mã) và JSON. `sort_rows()` nhận tên tiêu chí **cả tiếng Việt lẫn không dấu**
  (`"Độ tin cậy"` == `"do tin cay"` == `"confidence"`); `confidence` xếp theo *nhóm trạng
  thái* trước rồi mới tới điểm, nên `đã xác nhận 70` đứng trên `chưa xác nhận 95`
- `dossier.py` — hồ sơ **một mã**, cũng ghi vào `reports/<ngày>/`: chart Lightweight Charts
  *tương tác* (không phải ảnh) đã vẽ sẵn overlay, kèm toàn bộ nội dung deep-dive bên dưới.
  Hai điểm cố ý: (1) không tự viết câu nào — markdown của `format_snapshot` /
  `format_structure` được render lại thành HTML bằng `_md_to_html`, nên file và terminal
  không thể nói khác nhau; (2) nhúng thẳng thư viện trong `src/reporting/vendor/` cùng CSS/JS
  của chart, không link CDN, để file mở được offline và sau khi gửi đi.
  Thứ tự hiển thị được sắp lại **bằng CSS `order`** (chart lên đầu) thay vì tách DOM riêng
- `futures.py` — **thị trường phái sinh VN30** và đường nó chạm vào từng cổ phiếu.
  Mốc đo là **VN30, không phải VNINDEX**: hợp đồng thanh toán bằng tiền theo chính chỉ số
  VN30 của phiên đáo hạn, còn VNINDEX có thêm hàng trăm mã nhỏ không nằm trong rổ.
  Ba chỗ dễ sai được xử lý thẳng trong module:
  (1) **Basis buộc phải hội tụ về 0 vào phiên đáo hạn** — nên phân vị được tính *hai lần*,
  một lần trên 250 phiên gần nhất và một lần chỉ trên những phiên **cùng quãng đường tới
  đáo hạn** (±3 phiên); đọc −8 điểm khi còn 18 phiên giống như khi còn 1 phiên là đọc sai.
  (2) **`VN30F1M` là chuỗi nối, không phải một hợp đồng** — sau mỗi phiên đáo hạn nó nhảy
  sang tháng kế tiếp, nên % thay đổi qua đúng đường nối là số giả; `roll_indices()` đánh dấu
  các đường nối và mọi phép tính lợi suất bỏ qua chúng (basis thì không sao, nó là hiệu hai
  mức giá trong *cùng* một phiên).
  (3) **Số phiên tới đáo hạn của thanh cuối cùng chỉ ước lượng được** (kỳ sau chưa xảy ra nên
  phải đếm ngày làm việc, không trừ được ngày lễ) — cờ `estimated_sessions` nói rõ, thay vì
  trộn một số đếm chính xác với một số ước lượng.
  Ngày đáo hạn = **thứ Năm thứ ba** hằng tháng, tự lùi về phiên liền trước khi hôm đó nghỉ lễ.
  `symbol_exposure()` trả **bốn thành phần rời nhau** — trong rổ VN30 (kênh *cơ học*: lệnh
  arbitrage rơi thẳng vào 30 mã đó), beta + R² so với VN30 (kênh *gián tiếp* cho mã ngoài rổ),
  tỷ trọng **thanh khoản** trong rổ (**không phải trọng số chỉ số** — vốn hoá free-float không
  có trong `data/`), và hành vi phiên đáo hạn đo trên ~5 năm. Điểm tổng chỉ để **sắp thứ tự**;
  bảng luôn in cả bốn cột, vì gộp lại thì mã ngoài rổ beta cao trông y hệt mã trong rổ beta thấp.
  `basis_forward_stats()` là phần bắt câu chuyện "chiết khấu là điềm xấu" trả lời bằng số:
  chia lịch sử thành 5 nhóm basis rồi đo lợi suất VN30 1/3/5 phiên sau — kèm cảnh báo rằng các
  quan sát **chồng lấn** nên `n` không phải số quan sát độc lập
- `update.py` — tải giá mới từ FireAnt. Khác `fireant_history_fetcher.fetch_all_stock_history` ở 4 điểm: lọc được phạm vi (mã/nhóm, không phải luôn cả 80 mã), lỗi 1 mã không chết cả lượt, **API trả rỗng không ghi đè dữ liệu đã có**, và gọi `loader.clear_cache()` ở cuối. Phát hiện luôn lỗ hổng dữ liệu (`UpdateResult.gaps`) khi `mode` quá hẹp để lấp
- `asof.py` — **chế độ hồi tưởng**: đọc ngày người dùng gõ (`01/01/2025` là ngày/tháng/năm,
  `2025-01-01` là ISO — phân biệt bằng số chữ số nhóm đầu, không đoán theo giá trị), đẩy mốc
  tới cuối ngày để phiên của chính ngày đó vẫn được tính, và trả `None` cho mốc từ hôm nay
  trở đi (giả định hôm nay là hôm nay = chạy thật, nên tầng trên chỉ kiểm tra một điều kiện).
  Cũng giữ chỗ để file: bản hồi tưởng đi vào `reports/asof_<ngày>/` với tên mang chính mốc đó.
  Cắt chuỗi giá là *điều kiện cần nhưng chưa đủ*: forecast trên đĩa được tạo sau mốc và trạng
  thái của chúng tính từ phiên mà bản replay lẽ ra không biết — nên `report`/`dossier` lọc
  `created <= as_of` rồi đánh giá lại **không ghi đĩa**. `Snapshot`/`Structure`/`ScanResult`/
  `Report`/`Ranking`/`Dossier` đều mang `as_of_requested` (khác `as_of` = phiên cuối có thật),
  nên mọi formatter tự biết in dải cảnh báo mà không cần thêm tham số
- `format.py` — render markdown; mọi câu chữ tiếng Việt tập trung ở đây, data structure giữ nguyên chất

**Lớp MCP (`src/mcp_server/server.py`)** chỉ là vỏ mỏng, 16 tool: `list_symbols`,
`technical_report`, `scan_signals`, `analyze_structure`, `build_report`, `build_dossier`,
`build_ranking`, `rank_list`, `create_forecasts`, `check_forecasts`, `update_prices_tool`,
`futures_snapshot`, `futures_exposure`, `futures_stats`, `usage_guide`, `list_presets`.
Transport stdio nên mọi tool chạy trong `_quiet()`
(redirect stdout → stderr) vì các module cũ có `print()`. `analyze_structure` và `build_report`
trả về cả text lẫn `ImageContent` (PNG) nên Claude nhìn thấy được biểu đồ; `build_dossier` chỉ
trả text + đường dẫn file — biểu đồ của nó là thứ người dùng mở ra tương tác, không phải ảnh
để Claude nhìn. `technical_report` và `build_dossier` dùng chung `format_deep_dive()`.

**Vòng đời forecast:** `pending` → `triggered` → `hit_target` / `invalidated` / `expired`.
Không có cron, không có notify nền — `check_forecasts` chạy khi người dùng gọi, thay đổi trạng
thái được in ra ngay tại đó.

**Chart HTML tương tác** giờ nhận thêm tham số `overlays` — `render_chart()` có `open_browser`
để MCP ghi file mà không bật Chrome, và trả về đường dẫn. `chart_runner.run_chart` tự động vẽ
kèm trendline + box. Ba mảnh dùng chung giữa chart rời và dossier nằm ở
`chart_renderer_v2`: `build_series()` (dữ liệu), `chart_body_html()` (khung DOM + id mà JS tra
cứu), `chart_data_script()` (khối `<script>` bơm biến). Sửa một chỗ là cả hai đổi theo.

**Chiều cao pane và trục thời gian** — chỗ này từng hỏng theo hai cách, cả hai đều biểu hiện
giống nhau (dãy ngày bị cắt đôi):

1. Lightweight Charts vẽ trục thời gian **bên trong** chiều cao được cấp, mà hộp chứa lại
   `overflow: hidden` (để bo góc). Chart tạo cao hơn hộp (520 trong hộp 480) là mất đúng dải
   ngày. Nay chỉ còn một nguồn số: `PANE_H` trong JS, ghi thẳng vào `style.height` của hộp,
   dùng lại y nguyên khi resize; thêm một `ResizeObserver` bám vào chính `<table>` của chart
   để hộp luôn cao đúng bằng nội dung (hàng trục lấy chiều cao ở lượt render sau, đo một lần
   ngay sau `createChart` là còn số cũ).
2. Chart dựng pane bằng `<table>`, nên **CSS bảng của trang chủ ăn vào ruột chart**:
   `REPORT_CSS` có `table { margin: 12px 0 }` đẩy cả chart xuống 12px. `chart_renderer_v2.css`
   tự thủ bằng khối `#charts-container table/td` — thắng nhờ specificity (id + type) nên
   không phụ thuộc thứ tự nạp stylesheet. Đừng bỏ khối này khi dọn CSS.

Chỉ pane giá và pane dưới cùng có trục ngày; volume/RSI/MACD tắt trục vì 5 pane cuộn chung
nhau, in ngày dưới mỗi pane là in lại đúng một dãy đó năm lần.

**Hai bước của việc xếp hạng** — `build_ranking` tính rồi ghi đĩa, `rank_list` chỉ đọc lại
file JSON đó và sắp xếp. Tách ra vì người dùng thường xoay bảng nhiều lần liên tiếp ("giờ
xếp theo RSI đi", "đảo ngược lại xem"): tính lại 80 mã mỗi lần vừa chậm vừa có nguy cơ lệch
với file HTML họ đang mở. `save_json` ghi bản có ngày giờ **và** làm mới bản trỏ cố định
`reports/xep_hang_moi_nhat.json`, nên `rank_list` không cần tham số đường dẫn.

**Slash command:** `.claude/commands/{ta,scan,deep-dive,structure,report,rank,watch,update}.md`.
`/ta` in bảng tra cứu do `format_usage_guide()` sinh **từ chính các hằng số đang chạy**
(`GROUP_FILES`, `RULES`, `PROFILES`, `MODES`) nên không thể lệch so với code.

**Cho session mới:** `CLAUDE.md` (tự nạp mỗi session) chứa bảng "người dùng nói gì → chạy gì",
quy ước volume/cache/stdio, và nhịp dùng hàng ngày. Sửa command hay tool thì cập nhật cả
`CLAUDE.md` và `_COMMAND_MAP` trong `src/ta/format.py`.

## Tầng tin tức & sự kiện (`src/news/`) — GĐ1b

Kế hoạch đầy đủ: `documents/plan_news_pipeline.md`. Hiện đã có phần **dữ liệu có
cấu trúc** (nhóm A + B của taxonomy), chưa có phần tin tức dạng văn bản.

- `fireant.py` — client cho các endpoint FireAnt mà tầng giá không dùng. Hai endpoint
  **rất dễ nhầm**: `/symbols/{s}/transactions` là giao dịch của *chính tổ chức*
  (cổ phiếu quỹ, `position` luôn null); `/symbols/{s}/holder-transactions` mới là
  giao dịch **cổ đông lớn / người nội bộ** (có `position` thật). Dò nhầm cái đầu là
  lý do bản khảo sát đầu tiên kết luận sai về cấu trúc dữ liệu
- `models.py` — `HolderTransaction`, `TimescaleMark`. Enum chiều mua/bán
  (`0=Mua, 1=Bán, 2/3=quyền mua`) lấy **nguyên từ đặc tả** `/swagger/docs/v1`, nên
  mỗi bản ghi mang `direction_source="swagger_enum"`. Không bao giờ suy chiều từ phản
  ứng giá — đó chính là thứ event study đang *đo*, suy ngược lại là vòng tròn
- `parse.py` — payload → dataclass, **không mạng không đĩa** nên test chạy trên fixture.
  `parse_mark_title` rút số từ chuỗi `title` của `timescale-marks` (`"BCTC quý 4/2025|DT:
  20.225,5 tỷ, +14,9%"`, `"Ngày KHQ: 28/05/2026"`) — chuỗi này FireAnt viết cho *người
  đọc*, format đổi là gãy, nên hàm trả dict rỗng thay vì ném lỗi và `raw_title` luôn
  được giữ nguyên bên cạnh
- `store.py` — SQLite ở `news/index.db`, upsert theo khoá tự nhiên nên chạy lại nhiều
  lần vẫn ra một kho
- `ingest.py` — GĐ1b: nạp `holder-transactions` + `timescale-marks`. Lỗi một mã không
  giết cả lượt

**Ba chỗ dễ sai, đã có test chặn:**

1. **`registeredVolume = None` KHÁC `= 0`.** Bản ghi trước ~2014 không có đăng ký vì
   quy định khi đó chưa bắt buộc → tỷ lệ thực hiện *không định nghĩa được*. Ép về 0 là
   biến "không đo được" thành "đăng ký rồi không làm" — một tín hiệu bịa ra từ khoảng trống
2. **Không lọc `as_of` theo `first_seen` mặc định.** Lọc như vậy thì mọi backfill thành
   vô dụng: nạp lịch sử hôm nay là mọi mốc hồi tưởng trước hôm nay trả rỗng, và phần hiệu
   chuẩn base rate chết theo. `first_seen` chống *nội dung bị sửa sau* — đúng cho bài báo,
   vô nghĩa cho một giao dịch năm 2020 bất biến. Ai cần chặt thì `strict_first_seen=True`
3. **`holder-transactions` không có ngày công bố.** `t0` dùng `startDate` làm mốc thay
   thế và khai báo qua `t0_source="start_date_proxy"`. Riêng BCTC/cổ tức thì
   `timescale-marks` cho ngày công bố thật (`t0_source="timescale_mark"`)

- `reaction.py` — **event study** (GĐ5): ước lượng α/β trên t-130…t-11 (bỏ 10 phiên sát
  sự kiện để không nuốt mất phần rò rỉ tin), rồi đo abnormal return trên t-5…t+10. Trả
  **ba cửa sổ tách rời** — rò rỉ trước / tức thì / trôi sau — vì gộp lại là xoá đúng thứ
  đáng đọc: mã chạy hết trước ngày công bố trông y hệt mã không phản ứng
- `stats.py` — base rate: chạy lại phép đo trên *mọi* sự kiện cùng loại rồi trả **phân
  phối** (trung vị + tứ phân vị + % dương), không phải trung bình. Nhóm dưới `MIN_N=20`
  bị tách riêng và **không in số**
- `format.py` — toàn bộ câu chữ tiếng Việt, giữ disclaimer

**Ba chỗ dễ sai nữa, ở tầng đo:**

4. **Cửa sổ ước lượng phải bỏ 10 phiên sát sự kiện.** Tin hay rò rỉ trước công bố; để
   đoạn đó vào phần ước lượng là biến chính nó thành "bình thường", và phản ứng đo được
   nhỏ đi một cách hệ thống
5. **Ba cửa sổ không được cộng lại thành một số.** Xem trên
6. **Phiên trần/sàn làm phép đo bị cắt cụt** — biên độ thật lớn hơn số đo được, nên
   `limit_hit` được gắn cờ và `stats.collect` loại chúng khỏi thống kê. Trộn vào là
   đánh giá thấp *có hệ thống* đúng những sự kiện mạnh nhất, sai lệch một chiều chứ
   không phải nhiễu

- `posts.py` — nạp tin tức (GĐ1). **Cố ý không nạp toàn văn**: toàn văn ở
  `/posts/{id}` là 1 request/bài, ~200.000 bài cho cả rổ = ~66 giờ. Response `list`
  rẻ hơn 100 lần và đã có `title` + `description` + `date` + `postSource` +
  `taggedSymbols` — đủ cho lọc, xếp lịch, khử trùng lặp. `fetch_body()` nạp lười theo
  `post_id`, và `upsert_posts` dùng `COALESCE` để lượt ghi sau (`body=None`) không xoá
  toàn văn đã tốn request để lấy

**Phát hiện quan trọng nhất của `posts.py`:** feed tin tức có lẫn **CBTT đăng lại
nguyên văn**, nhận ra bằng tiền tố mã (`"HPG: Thông báo giao dịch cổ phiếu của người
nội bộ..."`). Đó là thứ `holder-transactions` **không có**: *ngày tin ra thị trường*.
Hai loại phải tách: `thong_bao_giao_dich` (trước, là mốc thị trường phản ứng) và
`bao_cao_ket_qua` (sau khi xong). Đã ghép được 2 cặp trên HPG: thông báo đến **trước
`startDate` 3–6 ngày** — đúng giả thuyết lệch `t0` ở §8b.

Luật nhận diện cần **cả hai** điều kiện (đối tượng là cổ phiếu **và** chủ thể là người
nội bộ). Chỉ một vế thì bắt nhầm, và đây là ca thật: *"HPG: Hòa Phát nhận hồ sơ đăng ký
mua nhà ở xã hội"* (đối tượng là nhà) và *"Fubon ETF dự kiến mua, bán cổ phiếu nào"*
(chủ thể là quỹ). Siết luật đưa 16 → 8 bài trên 600, và 8 bài còn lại đều đúng.

- `match.py` — ghép giao dịch ↔ bài công bố để lấy **ngày tin ra thị trường**.
  `holder-transactions` chỉ có `startDate` (ngày cửa sổ giao dịch mở), mà thị trường
  phản ứng lúc *công bố*. Đo trên 170 giao dịch từ 2023: **52% ghép được**, và công bố
  đi trước `startDate` **trung vị 6 ngày**. Nghĩa là neo cửa sổ vào `startDate` đặt
  phản ứng thật vào vùng `t-5…t-1` rồi gọi nó là "rò rỉ trước tin" — không phải rò rỉ,
  là chính cái tin bị đo lệch chỗ.
  Ghép bằng **hai bằng chứng độc lập**: tên người (CBTT nêu đích danh) và khối lượng
  (báo chí nêu số, không nêu tên — `6.600.000` viết là `"6,6 triệu"`). Trả `Match` kèm
  **điểm và lý do** để bác được; dưới `MIN_SCORE` thì **không ghép** và giữ mốc thay
  thế, vì ghép sai làm hỏng `t0` theo một hướng rất khó phát hiện

**MCP:** 4 tool mới — `update_news`, `news_transactions`, `news_impact`, `news_stats`
(tổng 17 tool).

Test: `tests/test_news_store.py` (chiều giao dịch lấy từ enum, None≠0, backfill vẫn hồi
tưởng được, parse `title` hỏng không làm nổ, upsert không nhân đôi);
`tests/test_news_reaction.py` (beta, cả thị trường cùng lên thì không phải abnormal,
ba cửa sổ tách rời, cửa sổ ước lượng bỏ 10 phiên, cờ trần/sàn — chuỗi giá dựng tay);
`tests/test_news_stats.py` (trung vị không bị ca ngoại lệ kéo, ngưỡng n, quyền mua
không gộp vào mua/bán thường);
`tests/test_news_posts.py` (nhận diện CBTT, thông báo vs kết quả, 3 dương tính giả
bắt được từ dữ liệu thật, dedupe giữ bản sớm nhất, nạp lại không xoá toàn văn);
`tests/test_news_match.py` (biến thể khối lượng kiểu Việt, ghép đúng cặp thật của HPG,
ngoài cửa sổ thì không ghép, cùng điểm thì chọn bài sớm hơn, không ghép bừa).

**Dependency:** `requirements.txt` cho máy local (app + plugin, gồm `mcp>=2.0.0` và
`matplotlib`); `requirements.server.txt` vẫn dành cho máy Linux thu thập dữ liệu.

**Cache & dữ liệu mới:** `loader._load_year` cache theo `(mã, năm, chữ ký file)` — chữ ký là
`(số file, mtime mới nhất)` của thư mục năm đó. Nghĩa là cache **tự hết hạn** khi bất kỳ tiến
trình nào ghi vào `data/`: MCP server, UI tkinter, script tay, rsync từ server. Không phụ thuộc
vào việc bên ghi có nhớ gọi `clear_cache()` hay không.

Lưu ý khi sửa chỗ này: phải soi mtime **từng file**, không phải mtime thư mục — ghi đè
`2026-08-01.json` tại chỗ (đúng cái mà refetch theo tháng làm) không làm đổi mtime thư mục.
Chi phí ~0.1 ms mỗi (mã, năm), so với ~25 ms để parse. `clear_cache()` vẫn giữ để giải phóng
bộ nhớ, không còn cần cho tính đúng đắn.

Thư mục sinh ra khi chạy (đã gitignore): `chart/`, `reports/`, `forecasts/`.

Test: `tests/test_ta_signals.py` (state machine RSI + đối chiếu ADX với bản cũ),
`tests/test_ta_structure.py` (pivot, trendline, box, pattern, render),
`tests/test_ta_candles.py` (giải phẫu nến, 13 mẫu, phiên trần/sàn),
`tests/test_ta_formations.py` (2 đỉnh / vai đầu vai, neckline, vòng đời hình thành→xác nhận→hỏng),
`tests/test_ta_confluence.py` (vùng quyết định, 3 mức hợp lưu, câu kết luận),
`tests/test_ta_swings.py` (nhãn HH/HL/EQH, BOS vs CHoCH, không nhìn trước),
`tests/test_ta_levels.py` (gom cụm, volume profile, gap chưa lấp, ngưỡng khoảng cách),
`tests/test_ta_vsa.py` (cao trào, churn, no-demand/supply, volume cạn),
`tests/test_ta_forecast.py` (vòng đời forecast, xác nhận volume, lưu/đọc đĩa),
`tests/test_ta_report.py` (báo cáo + HTML tự chứa),
`tests/test_ta_ranking.py` (hai trục điểm, thứ tự, tên tiêu chí tiếng Việt, vòng JSON,
HTML tự chứa + escape — phần chấm điểm dựng input bằng tay nên dữ liệu trên đĩa đổi không
làm test xanh/đỏ nhầm),
`tests/test_ta_dossier.py` (markdown→HTML có escape, chart là dữ liệu sống chứ không phải ảnh,
không request mạng),
`tests/test_ta_update.py` (cửa sổ tháng, từng mode, không ghi đè khi API rỗng, cache được xoá —
toàn bộ mock `requests`, không gọi mạng),
`tests/test_ta_asof.py` (đọc ngày kiểu Việt Nam vs ISO, mốc từ hôm nay trở đi = chạy thật,
dữ liệu bị cắt đúng tại mốc, dải cảnh báo, forecast sau mốc bị ẩn và bản hồi tưởng không ghi
đè trạng thái thật, bảng xếp hạng hồi tưởng không thay bảng của phiên thật),
`tests/test_ta_futures.py` (thứ Năm thứ ba kể cả tháng bắt đầu bằng thứ Năm, lùi phiên khi
đáo hạn rơi vào ngày nghỉ, đường nối hợp đồng không được đọc thành cú chạy giá, beta bị giữ
lại khi mẫu quá ngắn, và — chạy trên `data/` thật vì cái đang bảo vệ là *cấu hình* — chỉ số
lẫn hợp đồng không lọt vào bất kỳ nhóm nào).
