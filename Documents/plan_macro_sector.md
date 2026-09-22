# Phương án: tầng vĩ mô & ngành cho `dashboard-alpha-score`

> Trạng thái: **đã thi công xong GĐ 1→6** (16/09/2026). Nhật ký ở §13.
> Phần thiết kế bên dưới giữ nguyên làm bản ghi ý định ban đầu; chỗ nào
> dữ liệu bác lại thì §13 nói rõ — đặc biệt là §5, bị §7 thiết kế lại.
>
> Toàn bộ §1 đã **kiểm chứng bằng token thật ngày 15/09/2026**. Mọi con số đếm bản ghi
> trong §1 là số đếm thật từ response, không phải suy ra từ đặc tả — endpoint nào gọi
> ra rỗng thì ghi thẳng là rỗng. Mọi ngưỡng trong §5 là **đề xuất khởi điểm**, chưa
> hiệu chuẩn; §7 là việc phải làm trước khi tin bất kỳ con số nào trong đó.

Tầng `src/ta/` trả lời "biểu đồ của **một mã** đang nói gì". Tầng `src/news/` trả lời
"ngoài biểu đồ còn chuyện gì, và đã vào giá chưa" — cũng cho **một mã**. Tài liệu này
thiết kế tầng `src/macro/` trả lời một câu mà cả hai tầng kia **không thể** trả lời vì
sai đơn vị đo: *ngành nào đang sáng, ngành nào đang tối, và vì cái gì.*

---

## 0. Vì sao tầng hiện tại không trả lời được — và nó chặn ở đâu

Yêu cầu: output là **ngành**, không phụ thuộc vào bất kỳ mã nào; có điểm; có dẫn chứng.

Hôm nay hệ thống chặn đúng câu này, ở một chỗ cụ thể và có chủ ý. `classify_post`
(`src/news/digest.py:234`) xếp mọi bài gắn > 3 mã vào `GROUP_SECTOR`, rồi
`src/news/digest.py:407` gán thẳng `ST_NOT_MEASURED` — *"tin ngành/thị trường — cố ý
không quy về một mã"*.

**Cái chặn đó đúng ở cấp mã và hết hiệu lực ở cấp ngành.** Lý do chặn là *không tách
được phần đóng góp của một bài điểm tin 15 mã vào abnormal return của riêng PLX* —
không phải *không đo được gì cả*. Đổi đơn vị đo từ **mã** sang **ngành** thì lý do biến
mất: một bài về giá dầu nói về ngành dầu khí là đúng cấp, không phải suy diễn.

Ba thứ còn thiếu hẳn, và cả ba đều đã có sẵn ở FireAnt mà repo chưa gọi tới:

1. **Không có chuỗi giá cấp ngành.** Nên mọi phát biểu "ngành X mạnh" hiện phải gộp từ
   76 mã trong `data/` — mà `src/ta/sector.py` đã tự nói ra giới hạn của chính nó:
   `cntt` có 2 mã, `cham_soc_sk` có 1, dưới `MIN_PEERS=3` thì mọi phép so trả `None`.
   Rổ 76 mã là **một lát cắt**, không phải ngành.
2. **Không có biến vĩ mô.** Không lãi suất, không CPI, không tỷ giá, không giá xăng dầu.
3. **Không có tin nào không gắn mã.** Tin chỉ vào kho qua `/symbols/{mã}/posts`, nên
   một bài về xung đột Trung Đông chỉ tồn tại nếu FireAnt tình cờ gắn nó cho một mã.

---

## 1. Kiểm kê nguồn — đã xác minh bằng token thật

Gọi thật, ngày 15/09/2026, qua `src.news.fireant.get`. Cột cuối là **số đếm thật**.

| Endpoint | Trả về gì | Đã kiểm chứng |
|---|---|---|
| `/icb` | Cây ngành ICB 4 cấp | ✅ 250 dòng · 11 ngành cấp 1 · 20 cấp 2 |
| `/icb/{code}/historical-index` | **Chuỗi OHLC ngành theo phiên** | ✅ `60` → **4163 phiên** (04/01/2010 → 16/09/2026); hỏi từ 2015 thì trả 2917 — API cắt đúng khoảng xin |
| `/icb/latest-index` | Phiên mới nhất, mọi ngành | ✅ 250 ngành, đủ OHLC + dòng tiền + PE/PB |
| `/icb/{code}/rrg` | RS-Ratio + RS-Momentum theo phiên | ✅ `60` → 171 điểm (2026), khoá `date/rs/rm` |
| `/icb/{code}/statistics` | %Δ 1w/1m/3m/6m/1y + đỉnh/đáy từng cửa sổ | ✅ |
| `/icb/{code}/financial-data` | **BCTC cấp ngành theo quý** | ✅ `60` → 4 quý: PE, PB, EPS, ROE, ROA, biên, nợ/VCSH |
| `/icb/{code}/symbols` | Thành viên ngành | ✅ `60` → 33 mã |
| `/icb/industry-info?symbols=` | Mã → ngành ICB 4 cấp | ✅ **76/76** mã trong `data/` đều khớp |
| `/macro-data/types` | Nhóm chỉ số vĩ mô | ✅ 9 nhóm |
| `/macro-data/{type}/info` | **Chuỗi lịch sử + đơn vị + nguồn + kỳ công bố kế** | ✅ `InterestRate` 17 chỉ số · `Consumer` 5 |
| `/posts/groups` | Nhóm tin **không gắn mã** | ✅ 10 nhóm |
| `/posts?groupID=` | Tin theo nhóm | ✅ lùi được: offset 1000 ở nhóm 9 → 21/07/2026 |
| `/posts/sources` | Danh sách nguồn tin | ✅ 232 nguồn, có cờ *"Nguồn không hợp lệ"* |
| `/reports/search` | Báo cáo phân tích (PDF) | ✅ 1108 bản trong 01/06→15/09/2026 · lọc `categoryID=2` (ngành) từ 01/01/2026 → 163 bản |
| `/reports/categories` | Phân loại báo cáo | ✅ 9, có *Phân tích ngành*, *Kinh tế vĩ mô*, *Thị trường thế giới* |
| `/symbols/BZ=F/historical-quotes` | Chuỗi giá Brent | ❌ **rỗng** — xem §1.7 |

### 1.1 Chỉ số ngành ICB — xương sống của cả tầng

`/icb/60/historical-index` trả mỗi phiên một bản ghi có **đúng hình dạng một cây nến**,
cộng thêm những thứ mã lẻ không có:

```json
{"industryCode":"60","date":"2026-09-15T00:00:00","indexValues":{
  "ICBName":"Năng lượng","IndexOpen":86.09,"IndexHigh":91.03,"IndexLow":84.92,
  "IndexClose":90.71,"IndexPrev":85.56,"Volume":68648400,"Value":1810936406000,
  "BuyForeignValue":269714894415,"SellForeignValue":62671301158,
  "PositiveMoneyFlow":1803391736000,"NegativeMoneyFlow":1460800,
  "PE":...,"PB":...,"MarketCap":...}}
```

Ba thứ đáng chú ý, mỗi thứ mở một cột phân tích:

* **OHLC + Volume** → toàn bộ `src/ta/` chạy được nguyên xi trên ngành (§3).
* **`BuyForeignValue` / `SellForeignValue`** → khối ngoại **theo ngành**, thứ không dựng
  lại được từ 76 mã vì rổ thiếu 2/3 số mã trong ngành.
* **`PositiveMoneyFlow` / `NegativeMoneyFlow`** → dòng tiền chủ động mua/bán, FireAnt
  tính từ tick. Repo có `src/data/flow_records.py` nhưng chỉ ở cấp mã.

**11 ngành cấp 1** (mã ICB 2019): `10` Công nghệ · `15` Viễn thông · `20` Chăm sóc sức
khoẻ · `30` Tài chính · `35` Bất động sản · `40` Tiêu dùng không thiết yếu · `45` Tiêu
dùng cơ bản · `50` Công nghiệp · `55` Vật liệu cơ bản · `60` Năng lượng · `65` Dịch vụ
hạ tầng. Cấp 2 có 20 nhóm — `3010` Ngân hàng tách khỏi `3020` Dịch vụ tài chính và
`3030` Bảo hiểm, thứ mà nhãn `tai_chinh` gộp 27 mã hiện nay không tách được.

> ⚠️ **Chỉ số ngành KHÔNG dựng từ `data/`.** Ngành `60` có 33 mã; rổ ta có 4. Chỉ số
> này chạy theo cả 33 mã, kể cả những mã ta không có và không định mua. Đó là **tính
> năng** — nó đúng nghĩa "ngành" hơn rổ của ta — nhưng phải nói ra ở mọi báo cáo, vì
> nếu không, người đọc sẽ tưởng "Năng lượng +9,2%" là điều gì đó về BSR/PLX/PVD/PVT.

### 1.2 RRG — cỗ máy xoay vòng ngành, FireAnt tính sẵn

`/icb/{code}/rrg` trả `{date, rs, rm}` theo phiên. Đây là **JdK RS-Ratio / RS-Momentum**,
chuẩn công nghiệp cho phân tích xoay vòng ngành: hai trục cắt nhau tại 100, chia bốn góc
phần tư — *leading* (rs>100, rm>100), *weakening* (rs>100, rm<100), *lagging* (rs<100,
rm<100), *improving* (rs<100, rm>100). Ngành thường đi **thuận chiều kim đồng hồ** qua
bốn góc, và `rm` **xoay trước** `rs` theo đúng cấu tạo (nó là tốc độ biến thiên của `rs`).

Đây chính là cái trả lời vế "**thời gian tới**" một cách đo được chứ không phải đoán:
một ngành ở góc *improving* là ngành còn yếu hơn thị trường nhưng đang thu hẹp khoảng
cách — khác hẳn một ngành ở *weakening* đang mạnh nhưng hết đà.

> ⚠️ Không rõ FireAnt chuẩn hoá `rs`/`rm` theo cửa sổ nào. **Bắt buộc dựng lại một bản
> tự tính** từ `historical-index` + VNINDEX để đối chiếu. Hai bản lệch nhau nhiều thì
> dùng bản tự tính (tái lập được) và ghi lại độ lệch, đừng im lặng chọn một bên.

### 1.3 BCTC cấp ngành — nền tảng, theo quý

`/icb/60/financial-data?type=quarterly&count=4` trả PE, PB, EPS, ROE, ROA, ROIC,
GrossMargin, EBITMargin, TotalDebtOverEquity, các vòng quay… **theo quý, cho cả ngành**.

Đây là thứ `update_fundamentals` hiện **không** có: bản hiện tại là snapshot hôm nay của
từng mã, không có chuỗi. Ở cấp ngành thì có chuỗi quý thật — nên câu "biên lợi nhuận
ngành đang cải thiện quý thứ ba liên tiếp" là phát biểu **kiểm chứng được**, không phải
cảm nhận.

### 1.4 Dữ liệu vĩ mô — 9 nhóm, có chuỗi lịch sử

`/macro-data/{type}/info` trả mỗi chỉ số kèm `historicalValue` đầy đủ, `unit`,
`frequency`, `source`, và `nextRelease`:

| Nhóm | Nội dung |
|---|---|
| `InterestRate` | 17 chỉ số — liên ngân hàng qua đêm/1 tuần/…, tái cấp vốn |
| `Prices` | CPI, biến động giá xuất nhập khẩu |
| `Money` | Cung tiền M0/M1/M2, dự trữ ngoại hối |
| `Trade` | Cán cân thương mại, dòng vốn, xuất nhập khẩu |
| `Business` | PMI công nghiệp, đăng ký ô tô, lao động |
| `Consumer` | Niềm tin tiêu dùng, doanh số bán lẻ, **giá xăng dầu** |
| `GDP` | GDP và tăng trưởng theo lĩnh vực |
| `Labour` · `Taxes` | Thất nghiệp, lương tối thiểu · thuế, bảo hiểm |

Ví dụ thật, *Giá xăng dầu*: `unit` = USD/lít, `frequency` = Hàng tháng, `source` = Tập
đoàn Xăng dầu Việt Nam, `range` = 2013–2026, `historicalValue` từ tháng 12/2013.

> ⚠️ **Bẫy nhìn trước nghiêm trọng hơn cả `fundamentals`.** Chuỗi vĩ mô đánh dấu theo
> **kỳ dữ liệu**, nhưng thị trường chỉ biết nó vào **ngày công bố** — CPI tháng 8 ra
> giữa tháng 9. Đọc `historicalValue` theo kỳ rồi cắt bằng `as_of` là cho báo cáo ngày
> 31/08 đọc một con số chưa ai biết. Nên mỗi chỉ số **phải mang `lag_days`** và `as_of`
> lọc theo *kỳ + lag*, không theo kỳ. Thêm nữa, số vĩ mô **bị sửa lại** sau khi công
> bố — nên vẫn phải đóng băng như `update_fundamentals`: ghi
> `macro/snapshots/<type>/<ngày>.json`, đọc bản ≤ mốc, không rơi về bản mới hơn.

### 1.5 Tin không gắn mã — đúng thứ yêu cầu đòi

`/posts?groupID=N` cho tin **không neo vào mã nào**. 10 nhóm, đáng dùng:
`1` Thị trường · `4` Kinh tế · `5` Thế giới · `9` Hàng hóa · `2` Tài chính · `6` BĐS.

Mẫu thật lấy ngày 15/09/2026:

```
nhóm 9  Hàng hóa: "Cập nhật giá xăng dầu ngày 15.9: Giá dầu thế giới tăng"
nhóm 5  Thế giới: "Thế giới thiệt hại 10% GDP nếu các quy tắc thương mại bị suy yếu"
nhóm 4  Kinh tế : "Áp lực gia tăng lên ngành hàng không toàn cầu"
```

Phân trang lùi được về quá khứ (offset 1000 ở nhóm 9 → 21/07/2026), nên **backfill được**.

`/posts/sources` (232 nguồn) mang sẵn cờ chất lượng: một số nguồn có tên bọc trong
`{… - Nguồn không hợp lệ}`. Đó là **tier nguồn có sẵn, miễn phí** — dùng đúng như §1
của plan tin tức đã quy định, thay vì tự chấm lại.

### 1.6 Báo cáo phân tích ngành — bằng chứng hạng nặng

`/reports/search?categoryID=2` → **163 báo cáo ngành** trong năm 2026, từ các CTCK:

```
14/09  MB Securities  "Báo cáo ngành Cao su: Đón đầu chu kỳ mới"
10/09                 "Báo cáo Ngành Dầu khí: Luật Dầu khí năm 2026 được thông qua…"
09/09                 "Báo cáo Ngành phân bón: Giá urê giảm do nguồn cung Trung Quốc tăng"
03/09                 "Báo cáo triển vọng ngành Dệt may 2H2026"
```

> ⚠️ Hai hạn chế đã đo: (a) `sectorID` **luôn `null`** trong thực tế → phải suy ngành
> từ tiêu đề, và phép suy đó phải hiện ra cho người đọc bác được; (b) kết quả tìm kiếm
> **không có toàn văn**, chỉ có `fileName`/`pages` — bóc PDF là việc của một giai đoạn
> sau (plan tin tức §3.3 đã hạ ưu tiên đúng loại việc này). **Riêng tiêu đề đã là tín
> hiệu**: tiêu đề báo cáo ngành do người phân tích viết, nó nêu thẳng luận điểm.

### 1.7 Hàng hoá thế giới — mắt xích yếu nhất, phải nói thẳng

Tin nhóm 9 mang `taggedSymbols` là **ticker hàng hoá thế giới kèm giá tại thời điểm
đăng**: `BZ=F` (Brent), `CL=F` (WTI), `GC=F` (vàng), `SI=F` (bạc). Mẫu thật 15/09/2026:
`BZ=F` 102,28 (+1,47%), `CL=F` 103,23 (+2,13%).

**Nhưng `/symbols/BZ=F/historical-quotes` trả rỗng** — đã thử, không phải suy đoán. Nghĩa
là ta có **chuỗi thưa dựng từ tin**, không có chuỗi phiên sạch.

Hệ quả phải chấp nhận, đừng che: **không hồi quy được beta-theo-dầu đúng chuẩn.** Cái
làm được là chuỗi Brent lấy mẫu theo ngày có tin (dày, vì tin giá dầu ra gần như hàng
ngày) — đủ để nói *"Brent +12% trong 20 phiên, chỉ số ngành Năng lượng +9%"*, không đủ
để nói *"ngành Năng lượng có beta 0,7 với Brent"*. Chỉ số vĩ mô *Giá xăng dầu* (§1.4) là
nguồn thứ hai, sạch hơn nhưng **theo tháng** và là giá bán lẻ trong nước.

### 1.8 Cầu nối về rổ 76 mã — tồn tại, và nằm ở cuối chứ không ở đầu

`/icb/industry-info?symbols=…` khớp **76/76** mã trong `data/`, trả đủ 4 cấp ICB +
`sectorKind` (`bank` / `general`) + sàn. Đây là thứ thay được
`stock_list/list_all_stock.json` cho việc phân ngành — chuẩn ICB thật thay vì nhãn trộn
quy mô mà `src/ta/sector.py` đang phải lọc bằng `SIZE_TAGS`.

Nhưng nó là **bước cuối cùng**, không phải bước đầu (§9).

---

## 2. Nguyên tắc kế thừa

Năm nguyên tắc §0 của plan tin tức giữ nguyên. Thêm ba cái riêng của tầng này:

6. **Đơn vị phân tích là NGÀNH, và điều đó phải kiểm tra được bằng máy.** GĐ 1–3 **không
   đọc một file nào trong `data/<MÃ>/`**. Đây là một *invariant test được*, không phải
   lời hứa: một test chặn `loader.load_prices` với mã cổ phiếu trong đường chạy của
   `src/macro/` là đủ. Yêu cầu "không phụ thuộc bất cứ mã nào" biến thành một test đỏ
   khi bị vi phạm.

7. **Vĩ mô là lực nền, không phải lời tiên tri.** CPI tăng không "làm" ngành nào tăng.
   Cái nói được: *biến này đã đi tới đâu*, *ngành này trong quá khứ đi cùng chiều hay
   ngược chiều với nó*, *hiện tại lệch nhau chỗ nào*. Mọi phát biểu nhân quả một chiều
   là thứ phải chặn ở validator (§6), không phải nhắc nhở trong prompt.

8. **"Sắp tới" phải có mốc kích hoạt và mốc sai.** Kế thừa `STANCES` của
   `src/ta/thesis.py`: một nhận định về tương lai không kèm *điều gì xác nhận* và *điều
   gì bác bỏ* thì không duyệt được, nên không được viết ra.

---

## 3. Quyết định kiến trúc lớn nhất: ghi chỉ số ngành theo đúng schema giá

`benchmark.py` đã lập tiền lệ: `_PROXY_EW` ghi ra `data/_PROXY_EW/` theo **đúng schema
FireAnt**, nên `loader.load_prices` đọc được mà không sửa một dòng nào ở tầng dưới.

Làm y hệt cho ngành: `/icb/{code}/historical-index` → `data/_ICB_60/<năm>/*.json` theo
schema `StockRecord`.

Đổi lại được **toàn bộ `src/ta/` chạy trên ngành, miễn phí**: EMA20/50, RSI14, ADX14,
chuỗi swing HH/HL của `swings.py`, bounding box của `boxes.py`, trendline, `weekly.py`,
thậm chí `analyze_structure`. "Ngành Năng lượng vừa phá hộp tích luỹ 8 tuần bằng volume
1,9×" trở thành một câu **có sẵn code để nói**, không phải một tính năng mới.

> ⚠️ **Cái bẫy đi kèm, y hệt VNINDEX.** Để nguyên thì `resolve_universe(None)` phát chỉ
> số ngành ra cho mọi lần quét và xếp hạng — và một dòng "ngành Năng lượng" đứng cạnh
> từng cổ phiếu là sai đúng hai đường mà `CLAUDE.md` đã nêu cho VNINDEX: không ai *mua*
> được ngành, và nến của nó là bình quân nên ADX/RSI mượt hơn mọi thành phần, làm lệch
> âm thầm mọi phân vị trong `ranking.py`. Nên: **registry riêng
> `stock_list/sectors.json`**, `loader.py` loại khỏi **mọi nhóm** (`all`, `vn30`, `disk`,
> `None`), lấy được chỉ bằng cách gọi đích danh hoặc nhóm `sectors`. Tiền tố `_ICB_` để
> không bao giờ bị nhầm là mã.

---

## 4. Kiến trúc `src/macro/`

```
src/macro/
  icb.py        # client + nạp chỉ số ngành → data/_ICB_<code>/, registry sectors.json
  rrg.py        # RS-Ratio / RS-Momentum: lấy từ API + TỰ TÍNH LẠI để đối chiếu (§1.2)
  fundamentals.py  # BCTC ngành theo quý, đóng băng theo ngày
  series.py     # 9 nhóm vĩ mô + lag_days + đóng băng (§1.4)
  feed.py       # tin theo groupID, không gắn mã; tier nguồn từ /posts/sources
  reports.py    # tiêu đề báo cáo phân tích ngành + suy ngành từ tiêu đề (hiện ra được)
  drivers.py    # bảng ánh xạ ngành ↔ biến vĩ mô / hàng hoá — KHAI BÁO, không hard-code
  score.py      # ba trụ điểm (§5)
  verdict.py    # LLM chấm, có validator (§6)
  format.py     # toàn bộ tiếng Việt
```

`drivers.py` đọc `stock_list/drivers.json` — khai báo, đúng cách plan tin tức §6 đã chọn
cho taxonomy, để sửa luật không phải sửa code và bảng luật test được độc lập:

```json
{
  "60": {
    "ten": "Năng lượng",
    "bien": [
      {"nguon": "post_ticker", "ma": "BZ=F", "chieu": "cung",
       "ly_do": "Giá dầu Brent — đầu vào của lọc dầu, đầu ra của thăm dò"},
      {"nguon": "macro", "id": 90, "chieu": "cung", "do_tre_ngay": 30,
       "ly_do": "Giá xăng dầu bán lẻ trong nước (tháng)"}
    ],
    "nhom_tin": [9, 5],
    "tu_khoa": ["giá dầu", "OPEC", "Brent", "lọc dầu", "khí"]
  }
}
```

`chieu` chỉ nhận `cung` / `nguoc` / `khong_ro`. **`khong_ro` là giá trị hợp lệ và là mặc
định** — bịa một chiều tương quan cho đủ bảng là đúng kiểu sai mà cả tài liệu này chống.
Và `chieu` khai báo ở đây là **giả thuyết**, §7 đo lại; chỗ nào đo ngược với khai báo thì
chính chỗ lệch là thông tin.

---

## 5. Điểm ngành — ba trụ, và luật không được gộp

`CLAUDE.md` cấm cộng ba cột xếp hạng thành "điểm cổ phiếu". Nhưng `src/ta/prospect.py`
đã lập tiền lệ cho một điểm tổng hợp **hợp lệ**, với ba điều kiện. Điểm ngành đi đúng ba
điều kiện đó:

1. **Luôn in kèm thành phần.** Một dòng 71 điểm luôn tháo được thành *vị thế 30 + nền
   tảng 22 + tin 19*, mỗi phần có trần riêng và câu giải thích riêng.
2. **Ghi file riêng**, không đụng `xep_hang_moi_nhat.json` hay file của `prospect`.
3. **Phần đo được và phần nhận định không cộng ở tầng hiển thị.** `base = A + B` là phép
   đo; `C` là nhận định của một model ngôn ngữ. Chúng chỉ gặp nhau ở `total`, và **`total`
   không bao giờ được in một mình**.

### Trụ A — Vị thế tương đối (đo được, từ giá ngành) · trần 40

| Thành phần | Nguồn | Trần |
|---|---|---|
| Góc phần tư RRG + hướng đi trong góc | `rrg.py` | 14 |
| Sức mạnh tương đối vs VNINDEX, 20/60 phiên | `_ICB_*` + `VNINDEX` | 10 |
| Độ rộng trong ngành (% thành viên trên EMA20) | `/icb/{code}/symbols` + giá | 8 |
| Dòng tiền: `PositiveMoneyFlow` ròng + khối ngoại ròng, phân vị 250 phiên | `historical-index` | 8 |

RRG ăn điểm cao nhất vì nó là thành phần duy nhất trong trụ A có **tính dẫn** theo cấu
tạo (`rm` xoay trước `rs`) — phần còn lại đều là mô tả hiện trạng.

### Trụ B — Nền tảng (đo được, từ BCTC ngành) · trần 30

| Thành phần | Trần |
|---|---|
| Xu hướng ROE / biên lợi nhuận 4–8 quý (dấu của độ dốc, không phải mức) | 12 |
| Tăng trưởng EPS ngành so cùng kỳ | 10 |
| Định giá: PE/PB ở **phân vị lịch sử của chính ngành đó** | 8 |

> Định giá **chỉ so ngành với chính nó theo thời gian**, tuyệt đối không so PE ngân hàng
> với PE công nghệ. PE 8 của Năng lượng và PE 18 của Công nghệ không nói lên cái nào rẻ
> hơn — chúng là hai phân phối khác nhau. Xếp hạng chéo theo PE thô là cách chắc chắn
> nhất để bảng này vô dụng.

### Trụ C — Bối cảnh vĩ mô + tin (nhận định, LLM chấm) · thang −25…+25

Model đọc gói bằng chứng (§6) gồm: tin nhóm không gắn mã đã lọc theo `tu_khoa` của ngành,
tiêu đề báo cáo phân tích ngành, trạng thái các biến vĩ mô liên quan kèm **ngày công
bố**, và diễn biến hàng hoá liên quan. Trả JSON có cấu trúc, mọi luận điểm gắn `ev_id`.

### Vế "thời gian tới" — trả bằng tư thế, không bằng dự báo

Output không phải "ngành X sẽ tăng". Nó là, theo đúng khuôn `thesis.py`:

```
NĂNG LƯỢNG (ICB 60) — 71/100 · tư thế: tang_cho
  Vị thế 30/40 · Nền tảng 22/30 · Tin +19/25  (không cộng dồn — ba cột riêng)
  Kích hoạt   : chỉ số ngành đóng cửa trên 92,4 (đỉnh 14/09) kèm volume > 1,5× TB20
  Bác bỏ      : rm cắt xuống dưới 100 trong khi rs < 100 → rơi về góc lagging
  Mốc         : 105,2 (đỉnh 6 tháng, 16/03/2026)
```

Mốc phải là **số có thật trong gói bằng chứng** — đỉnh/đáy từ `statistics`, cạnh hộp từ
`boxes.py` — không phải số tròn tự nghĩ ra. Luật này đã có ở `CLAUDE.md`, giữ nguyên.

---

## 6. Chống ảo giác — sáu tầng, mỗi tầng chặn một kiểu sai khác nhau

Đây là phần cốt lõi của yêu cầu, nên nó được thiết kế như một **cơ chế**, không phải một
lời dặn trong prompt. Nguyên tắc chung, theo hướng các công trình về *evidence-backed
generation*: **tách phần có bằng chứng chống lưng khỏi phần model tự nhớ ra, rồi chặn
phần sau** — bằng máy, trước khi ghi file.

**Tầng 1 — Gói bằng chứng là bảng đánh số.** Mọi mẩu bằng chứng mang một `ev_id`
(`E01`, `E02`…) kèm nguồn, ngày, và giá trị. Model không được đưa gì vào ngoài gói.

**Tầng 2 — Mọi luận điểm phải mang `ev_id`.** Schema JSON bắt buộc:

```json
{"score": 19, "stance": "tang_cho",
 "claims": [
   {"text": "Giá dầu Brent tăng 12% trong 20 phiên gần nhất",
    "evidence": ["E04","E07"], "kind": "so_lieu"},
   {"text": "Luật Dầu khí 2026 được thông qua",
    "evidence": ["E11"], "kind": "su_kien"}],
 "trigger": {"text": "...", "evidence": ["E02"]},
 "invalidation": {"text": "...", "evidence": ["E02"]}}
```

**Tầng 3 — Validator loại luận điểm, không nhắc nhở.** Chạy **trước** khi ghi file:

| Kiểm tra | Xử lý khi hỏng |
|---|---|
| `evidence` rỗng hoặc `ev_id` không tồn tại trong gói | **loại claim** |
| Con số trong `text` không khớp con số nào trong các `ev_id` được trích (sau chuẩn hoá `1.234,5` / `1,2 triệu`, dung sai làm tròn) | **loại claim** |
| Ngày trong `text` > `as_of` | **loại claim** |
| `trigger` / `invalidation` không phải số có trong gói | **loại cả nhận định**, ghi `chưa đủ căn cứ` |

Đây là cách làm mà các công trình về *atomic claim verification* trong lĩnh vực tài
chính dùng: bẻ output thành từng luận điểm nguyên tử rồi kiểm từng cái theo **loại**
(số liệu thì tính lại, sự kiện thì đối chiếu thực thể). Ta làm bản rút gọn: so khớp số
và so khớp ngày — hai loại chiếm gần hết ảo giác thực tế trong văn bản tài chính.

**Tầng 4 — Kết quả kiểm định lưu cùng nhận định, và in ra.** `claims_total`,
`claims_dropped`, lý do từng cái. Một nhận định bị loại 4/9 luận điểm là một nhận định
người đọc cần biết là yếu. Giấu con số đó đi thì tầng 3 chỉ làm output **trông** sạch.

**Tầng 5 — Ranh giới `<untrusted source="…">`.** Đã có trong repo
(`src/news/verdict.py:321`); giữ nguyên, mở rộng cho nguồn mới. Tầng này giờ quan trọng
hơn hẳn: nhóm `Thế giới` và `Hàng hóa` là tin dịch từ nguồn ngoài, không qua bộ lọc CBTT
nào.

**Tầng 6 — "Chưa đo được" ≠ 0.** Ngành không có tin trong cửa sổ → cột tin **để trống**,
không phải 0. Biến vĩ mô chưa tới kỳ công bố → *chưa có số mới*, không phải *đi ngang*.
Luật này đã có ở `CLAUDE.md` cho ba chỗ khác nhau; đây là chỗ thứ tư.

> **Một điều validator KHÔNG làm được, phải nói ra:** nó kiểm *luận điểm có khớp bằng
> chứng không*, không kiểm *suy luận có đúng không*. "Brent +12%" khớp E04 và "ngành
> Năng lượng sẽ hưởng lợi" là hai việc khác nhau — cái sau là suy luận kinh tế mà không
> phép kiểm tự động nào bắt được. Đó chính là lý do §5 bắt mọi nhận định mang
> `invalidation`: thứ chặn suy luận sai không phải validator, mà là việc người viết phải
> nói trước điều gì sẽ chứng minh mình sai.

---

## 7. Hiệu chuẩn — phải chứng minh trước khi tin

Plan tin tức §8b đã có một **kết quả âm tính** được ghi lại tử tế: event study đầu tiên
không tách được khỏi nền, và placebo test chỉ ra trung vị placebo −0,33% chứ không phải
0. Tầng này phải qua đúng cửa đó. Tài liệu bên ngoài cũng không hứa hẹn gì hơn: nghiên
cứu về sentiment cấp ngành cho kết quả **trái chiều**, có công trình kết luận thẳng rằng
điểm sentiment *"lack robust predictive power"* kể cả khi tách phần riêng của doanh
nghiệp. Nên mặc định phải là hoài nghi, không phải hy vọng.

**H1 — RRG có dẫn được lợi suất ngành không?** 11 ngành × ~2900 phiên (2015→nay). Mỗi
(ngành, phiên) là một quan sát: góc phần tư tại t → lợi suất tương đối của chỉ số ngành
so với VNINDEX ở t+20. So với **nền placebo** (ngày ngẫu nhiên, cùng ngành) chứ không so
với 0. Kỳ vọng: *improving* và *leading* hơn *lagging*; nếu không thì trụ A phải bỏ RRG.

**H2 — trụ B có thêm gì ngoài H1?** Cùng khung, biến là xu hướng ROE/EPS. Kiểm **phần
tăng thêm** khi đã có H1, không kiểm một mình — hai biến cùng đo "ngành đang khoẻ" thì
cái thứ hai không đáng một cột riêng.

**H3 — trụ C có thêm gì ngoài A+B?** Đây là câu đắt nhất và đáng nghi nhất. Chỉ chạy
được sau khi có ≥ 6 tháng điểm tin tích luỹ. **Nếu H3 âm tính thì trụ C vẫn ở lại báo
cáo nhưng KHÔNG vào điểm** — nó trở thành phần *diễn giải* (vì sao ngành này đang được
nói tới), đúng vai mà `sector_outlook` đang giữ hôm nay.

**Cửa chặn:** trụ nào không qua được placebo thì **không vào công thức điểm**. Trần điểm
ở §5 là đề xuất; §7 là thứ quyết định trần thật.

---

## 8. Bề mặt MCP

| Tool | Việc |
|---|---|
| `update_macro` | Nạp chỉ số ngành + BCTC ngành + chuỗi vĩ mô + tin nhóm. Đóng băng theo ngày. |
| `sector_board` | **Output chính**: 11 (hoặc 20) ngành xếp theo điểm, ba cột tách, kèm tư thế + kích hoạt + bác bỏ. Nhận `as_of`. |
| `sector_detail <ngành>` | Một ngành: chart chỉ số + RRG + chuỗi BCTC + biến vĩ mô liên quan + đầu mục tin có `ev_id`. |
| `macro_dashboard` | 9 nhóm vĩ mô: giá trị mới nhất, kỳ trước, phân vị lịch sử, **ngày công bố kế tiếp**. |
| `sector_evidence` → `sector_submit` | Hai bước như `prospect_evidence` → `prospect_score_news`: tool trả gói bằng chứng đánh số, model đọc rồi nộp, validator §6 chặn ở cửa nộp. |
| `sector_stats` | Base rate: sau mỗi góc RRG / mỗi mức điểm thì ngành thật sự đi đâu (§7). |
| `sector_members <ngành>` | Cầu nối cuối: mã nào của ngành này có trong `data/`. **Riêng một tool**, để §2.6 không bị phá. |

`/macro` cho bảng ngành, `/sector <tên>` cho một ngành.

---

## 9. Lộ trình

**GĐ 0 — Kiểm kê (✅ xong, chính là §1).** Đã gọi thật, đã biết cái gì có cái gì không.

**GĐ 1 — Chỉ số ngành + registry.** `icb.py` ghi `data/_ICB_*/`, `stock_list/sectors.json`,
`loader.py` loại khỏi mọi nhóm. Kiểm kê độ phủ lịch sử **từng ngành** (mới xác minh mã
`60` có 2917 phiên; các ngành khác chưa đếm). *Cửa ra: `technical_report("_ICB_60")`
chạy được, và `resolve_universe(None)` không chứa nó.*

**GĐ 2 — RRG + BCTC ngành.** `rrg.py` với **bản tự tính đối chiếu** bắt buộc.
*Cửa ra: bảng 11 ngành với góc phần tư + xu hướng ROE, thuần số, chưa có LLM.*

**GĐ 3 — Vĩ mô + tin nhóm.** `series.py` (lag + đóng băng), `feed.py`, `drivers.json`.
*Cửa ra: `macro_dashboard` chạy; trả lời được "ngành nào đang có tin gì" mà không đọc
một file `data/<MÃ>/` nào — có test chặn.*

**GĐ 4 — Hiệu chuẩn (§7).** Trước §5, không phải sau. Trần điểm do GĐ này quyết.

**GĐ 5 — Điểm + LLM + validator.** `score.py`, `verdict.py`, sáu tầng §6.
*Cửa ra: `claims_dropped` in ra được, và có test với gói bằng chứng cố tình chứa số sai
để chứng minh validator loại thật.*

**GĐ 6 — Báo cáo HTML + cầu nối về rổ 76 mã.**

Thứ tự này có một tính chất đáng giá: **GĐ 1–3 đã tự đứng được**. Kể cả khi GĐ 4 cho kết
quả âm tính và không có điểm nào ra đời, ba giai đoạn đầu vẫn để lại chỉ số ngành, RRG,
BCTC ngành và bảng vĩ mô — tức là vẫn trả lời được câu hỏi ban đầu, chỉ bằng số thay vì
bằng điểm.

---

## 10. Quy ước phải giữ

* **Chỉ số ngành không phải cổ phiếu, và nó nguy hiểm hơn VNINDEX** vì có tới 11–20 cái.
  Registry riêng, tiền tố `_ICB_`, loại khỏi mọi nhóm, gọi đích danh mới ra.
* **Chỉ số ngành chạy theo cả ngành, không theo rổ 76 mã.** Mọi báo cáo phải nói ra số
  thành viên của ngành và số mã ta thật sự có (`33` vs `4` với Năng lượng).
* **Vĩ mô lọc theo NGÀY CÔNG BỐ, không theo kỳ dữ liệu.** `lag_days` bắt buộc.
* **Số vĩ mô bị sửa lại → phải đóng băng theo ngày**, đọc bản ≤ mốc, không rơi về bản mới.
* **PE/PB chỉ so ngành với chính nó theo thời gian**, không xếp hạng chéo giữa các ngành.
* **`total` không bao giờ in một mình**; ba cột luôn đi cùng.
* **Phần đo được và phần LLM chấm không bao giờ lấy trung bình.**
* **Luận điểm không có `ev_id` thì bị loại, và số luận điểm bị loại phải in ra.**
* **`chieu` trong `drivers.json` mặc định là `khong_ro`**, và là giả thuyết cho tới khi
  §7 đo lại.
* **Nhận định về tương lai phải có `trigger` và `invalidation` là số có thật trong gói.**
* **Ngành cấp 1 hay cấp 2 phải nói rõ ở mọi bảng** — `30` Tài chính và `3010` Ngân hàng
  là hai dòng khác nhau, trộn lẫn là đếm ngân hàng hai lần.

---

## 11. Rủi ro đã biết

1. **Kết quả âm tính ở §7.** Xác suất thật, có tiền lệ (§8b của plan tin tức) và tài
   liệu ngoài cũng trái chiều. Giảm thiểu: GĐ 1–3 tự đứng được mà không cần điểm.
2. **11 ngành là mẫu nhỏ.** Mỗi phiên chỉ 11 quan sát, và chúng **tương quan mạnh với
   nhau** (cùng chịu VNINDEX). "Ngành tốt nhất trong 11" có thể chỉ là nhiễu xếp hạng.
   Giảm thiểu: báo cáo khoảng cách điểm, và nói thẳng khi top-3 nằm trong vòng vài điểm.
3. **API đổi hoặc bị rút quyền.** `/icb/*` và `/macro-data/*` chưa từng dùng, không có
   gì bảo đảm chúng ổn định như `historical-quotes`. Giảm thiểu: nạp là ghi xuống đĩa,
   không gọi trực tiếp lúc báo cáo.
4. **`sectorID` rỗng ở báo cáo phân tích** → suy ngành từ tiêu đề, có thể sai. Giảm
   thiểu: hiện phép suy ra cho người đọc bác được, đúng như ô "đăng lúc…" của `digest`.
5. **Prompt injection qua nhóm `Thế giới` / `Hàng hóa`.** Nguồn rộng hơn và ít kiểm duyệt
   hơn tin gắn mã. Giảm thiểu: `<untrusted>` + validator (một chỉ thị nhét trong bài
   không tạo ra được `ev_id` hợp lệ, nên tầng 3 loại claim đó dù model có nghe theo).
6. **Ảo giác "ngành được lợi".** Loại ảo giác không validator nào bắt được (§6). Giảm
   thiểu duy nhất: bắt buộc `invalidation`.

---

## 12. Quyết định — đã chốt 16/09/2026

Cả bốn chốt theo đề xuất.

1. ~~**Ngành cấp 1 (11) hay cấp 2 (20)?**~~ — **chốt: dựng cả hai, hiển thị cấp 1, cho
   khoan xuống cấp 2.** Cấp 1 gọn cho một bảng quét mắt; cấp 2 tách được Ngân hàng /
   Dịch vụ tài chính / Bảo hiểm, mà ở thị trường Việt Nam ba cái đó chạy rất khác nhau.
   Chi phí thêm gần như bằng 0 vì cùng một endpoint. → `sectors.json` mang cả 31 mã
   ngành, `level` là trường bắt buộc, và mọi bảng phải nói rõ đang ở cấp nào.

2. ~~**Brent: chuỗi thưa hay nguồn ngoài?**~~ — **chốt: chấp nhận chuỗi thưa ở GĐ 3**,
   ghi rõ là thưa, hoãn nguồn ngoài tới khi §7 chứng minh biến hàng hoá thật sự đóng
   góp. Thêm một nguồn ngoài là thêm một đường phụ thuộc mạng, một khoá API, một lịch
   bảo trì — trả giá đó trước khi biết nó có ích là ngược thứ tự.

3. ~~**Ai chấm trụ C?**~~ — **chốt: giữ nguyên mô hình `score_news_gemini` +
   `prospect_score_news`** — Gemini chạy nền, Claude trong phiên, *bản Claude đè bản
   Gemini cùng ngày, không bao giờ ngược lại, không bao giờ lấy trung bình*. 11–20 ngành
   nhỏ hơn 76 mã nhiều, nên Claude chấm trực tiếp cho **toàn bộ** bảng là khả thi.

4. ~~**Bảng này có ảnh hưởng `/prospect` không?**~~ — **chốt: không.** Gộp hai đơn vị đo
   khác nhau sẽ âm thầm biến bảng triển vọng thành bảng ngành. Nếu §7 cho kết quả dương
   tính mạnh thì mở lại như một **cột riêng**, không phải một khoản cộng.

---

## 13. Nhật ký thi công

### 16/09/2026 — GĐ 2→6 xong

`rrg.py` · `fundamentals.py` · `series.py` · `feed.py` · `drivers.py` ·
`members.py` · `calibrate.py` · `score.py` · `verdict.py` · `format.py` ·
8 tool MCP · `tests/test_macro_layer.py` (53 test). **751/751 test xanh.**

**Dữ liệu đã nạp:** RRG 25 ngành (4163 điểm mỗi ngành) · BCTC ngành 40 quý mỗi
ngành (2016Q3→2026Q2) · 96 chỉ số vĩ mô, 6684 quan sát, 9 nhóm · 3599 bài tin
không gắn mã · chuỗi Brent/WTI/vàng/bạc thưa · ánh xạ 25 ngành → rổ.

#### Kết quả hiệu chuẩn — §7 trả về BA kết quả âm tính

| Giả thuyết | Kết luận |
|---|---|
| H1 · góc RRG → lợi suất tương đối t+20 | ❌ *dẫn dắt* cho p = 0,025, nhưng… |
| H1 đa cửa sổ · 10/20/60 phiên | ❌ **không cửa sổ nào vượt ngưỡng Bonferroni 0,0042** |
| H2 · xu hướng ROE ngành | ❌ cả hai nhóm nằm đúng trên nền placebo |
| H3 · điểm tin | ⏸ chưa chạy được, cần ≥ 6 tháng tích luỹ |

Phép kiểm cứu cả tầng này khỏi một kết luận sai là **H1 đa cửa sổ**, và nó sinh
ra từ một chuyện xảy ra thật trong chính lượt chạy: cửa sổ 20 phiên cho *dẫn
dắt* p = 0,025 — trông như một phát hiện, và nếu dừng ở đó thì nó đã thành trần
điểm của trụ A. Chạy thêm 10 và 60 phiên thì **không cửa sổ nào còn ý nghĩa**;
hiệu ứng ở 20 phiên là +0,31 điểm phần trăm với tỷ lệ vượt thị trường 49% so với
nền 46–47%. Ba cửa sổ × bốn góc là 12 phép kiểm trên cùng dữ liệu, kỳ vọng 0,6
dương tính giả ở mức 0,05 — một p = 0,025 lẻ loi nằm gọn trong đó.

Báo cáo riêng cửa sổ 20 phiên và im lặng về hai cửa sổ kia là định nghĩa của
p-hacking, và **không ai phát hiện được**. Nên phép chặn nằm trong
`calibrate.ALPHA_ADJUSTED` chứ không nằm trong ý chí của người chạy.

Ghi chú thêm, xác nhận đúng bài học §8b của plan tin tức: trung vị placebo của
lợi suất tương đối ngành là **−0,42%**, không phải 0 — VNINDEX là chỉ số trọng
số vốn hoá nên nó không phải "ngành trung bình".

#### Hệ quả: §5 phải thiết kế lại, và bản thiết kế lại nằm trong code

Điểm ngành **không được phép tuyên bố sức dự báo**. `score.py` trả lời *"ngành
này đang ở đâu so với các ngành khác, ngay lúc này"* — mô tả kiểm chứng được —
chứ không phải *"ngành nào sẽ tăng"*. Trần điểm là **trọng số biên tập**, ghi ra
để cãi lại, không phải sức dự báo đo được. Mọi output bắt buộc mang
`calibration_note()`; chưa chạy hiệu chuẩn thì nhãn nói thẳng là chưa ai kiểm
chứng — *chưa kiểm chứng* khác *đã kiểm chứng và thấy yếu*.

Điều đó không làm bảng vô dụng: nó vẫn gộp năm phép đo rời rạc thành một thứ tự
đọc được, vẫn tháo ngược ra được, vẫn nói thẳng mình đứng ở đâu. Cái bỏ đi chỉ
là lời hứa không có bằng chứng.

#### Bốn lỗi tìm ra khi dựng, và mỗi lỗi để lại một test

1. **RRG bản tự tính khớp 50,6% — bằng tung đồng xu.** Đà tính bằng hiệu *một
   phiên* của một chuỗi đã chuẩn hoá gần như thuần nhiễu. Dò tham số ra
   12/26/750 với đà theo tỷ lệ 5 phiên → **85,1%**, và **kiểm chéo trên bảy
   ngành không tham gia dò** giữ được 80,4%. Chênh 85→80 nhỏ, nên bộ tham số mô
   tả cách FireAnt tính chứ không khớp đè lên một ngành.
2. **Bốn nhóm vĩ mô lặng lẽ trả 0 quan sát.** Parser ngày chỉ đọc được dạng
   `"8/26"`; FireAnt dùng **bốn** dạng (`"9/13"`, `"Q2/17"`, `1986`,
   `"2026-03-16"`). Trong bốn nhóm mất trắng có `InterestRate` — biến nền của
   Ngân hàng, BĐS và Bán lẻ. Không lỗi nào ném ra: một nhóm rỗng trông y hệt một
   nhóm FireAnt không có dữ liệu, nên nó sống sót qua cả lượt kiểm tra đầu.
3. **Một bài tin mang ngày 16/10/2026 khi phiên cuối là 16/09** — toà soạn gõ
   nhầm tháng. Một bản ghi như vậy hiện ra trong **mọi** báo cáo hồi tưởng như
   tin đã biết: nhìn trước không giới hạn, không phát hiện được từ phía đọc.
   Cùng lượt đó `US.VFS` (cổ phiếu VinFast) lọt vào bảng giá hàng hoá vì bộ lọc
   nhận mọi chuỗi có dấu chấm.
4. **Validator loại nhầm câu ĐÚNG — ba lần, ba nguyên nhân khác nhau.**
   (a) `100.33` bị đọc thành `10033` vì bộ sinh biến thể coi dấu chấm là phân
   nhóm; (b) `numbers` khai báo tay **thay thế** thay vì **cộng thêm** vào số
   rút từ chính câu bằng chứng, nên "20 điểm dữ liệu" thành số bịa; (c) phép
   kiểm số chạy trước phép kiểm ngày nên `2027-01-01` bị báo là *"số không có
   trong bằng chứng: 2027, −1, −1"* thay vì *"ngày ở tương lai"* — câu bị loại
   đúng, **lý do sai**, mà lý do mới là thứ người đọc dùng để bác lại validator.
   Một validator quá tay còn tệ hơn không có: người dùng sẽ tắt nó.

Ngoài ra `P/E 8,15` từng hiện thành `"815,2%"` trong gói bằng chứng — đoán kiểu
dữ liệu theo độ lớn ("nhỏ hơn 10 thì chắc là tỷ lệ") thay vì theo nhóm trường.
Con số sai đó đi thẳng vào thứ model đọc để viết nhận định.

#### Đóng nợ — cùng ngày, sau khi rà lại

**Nợ "Brent thưa" — đóng.** Con số "35 điểm ≈ 1 tháng" là hệ quả của việc chỉ cào 12
trang, không phải giới hạn của nguồn: nhóm Hàng hoá lùi được tới 05/2025 (offset 9000
vẫn có bài). Cào 180 trang → Brent **472 điểm phủ 97% phiên sàn**, WTI 93%, vàng 100%.
Đủ dày để hồi quy. MXV vẫn là ngõ cụt — có mã `QO` (ICE Brent) nhưng endpoint chỉ trả
metadata, không có giá.

Bài học đắt hơn con số: `QuoteSeries.sparse` được viết là hằng số `True` *"để chỗ dùng
không quên"*, và nó thành một lời nói dối ngay khi dữ liệu dày lên — code, tài liệu và
gói bằng chứng đều tiếp tục dán nhãn "không đủ hồi quy beta". Giờ nó **đo**: độ phủ tính
bằng số **phiên sàn có giá** chia tổng phiên sàn, dùng lịch VNINDEX thật. Lấy
`len(points)/trading_days` rồi cắt ở 1.0 cũng sai — Brent cho 138% → "100%", che mất
việc chỉ 331/342 phiên thật sự khớp.

**Nợ "BCTC một bản đóng băng" — đóng, bằng cách đo chứ không bằng cách sửa.** Chạy lại H2
trên BCTC **năm** (ít bị sửa hơn quý, lùi tới 2006): ROE p = 0,318, GrossMargin p = 0,757.
Cũng âm tính. Nên hạn chế đó **không giấu tín hiệu nào** — kết luận H2 đúng theo cả hai
đường dữ liệu. Vẫn đúng là bảng hồi tưởng trước hôm nay không có định giá.

**Nợ "lãi suất cũ" — to hơn báo cáo ban đầu, đã đóng phần đóng được.** Không phải một
chuỗi: kiểm kê 96 chỉ số cho **30 cái quá hạn**, tệ nhất 8020 ngày. Niềm tin người tiêu
dùng chết 1675 ngày mà đang là biến khai báo duy nhất của ngành `40`. Cả nhóm
`InterestRate` (17 chỉ số) không còn cái nào sống. Chuỗi nhanh nhất còn sống trễ **78
ngày** — đó là trần cứng của tầng vĩ mô, không sửa được từ phía repo.

Đã làm: ngưỡng quá hạn tính theo **tần suất** chứ không theo mốc chung; `macro_dashboard`
thêm cột tuổi + danh sách quá hạn; gói bằng chứng đính tuổi vào chính câu; `drivers.json`
thay biến chết bằng biến sống (2/4 quá hạn → 1/10). Ba biến hàng hoá (`HG=F`, `NG=F`)
cũng bị bỏ vì **0 điểm dữ liệu** — chỉ 4 hàng hoá thật sự xuất hiện trong kho tin.

**Đo lại chiều đã khai báo, lần đầu có đủ dữ liệu:**

| Ngành | Biến | r | Khai báo | Đo được |
|---|---|--:|---|---|
| Năng lượng | Brent | +0,117 | cùng chiều | **chưa rõ** (< 0,15) |
| Hóa chất | Brent | −0,083 | ngược chiều | **chưa rõ** (< 0,15) |

Cả hai đúng dấu nhưng dưới ngưỡng `MIN_ABS_CORR`. Đúng thứ bảng khai báo sinh ra để
nói: giả thuyết không bị bác, nhưng cũng chưa được xác nhận — và nó trả `khong_ro` thay
vì làm tròn thành một kết luận.

#### Còn nợ

* **H3 chưa chạy được** — cần ≥ 6 tháng điểm tin tích luỹ. Tới lúc đó, nếu âm
  tính thì trụ tin **ở lại báo cáo nhưng không vào điểm**.
* **Chuỗi Brent vẫn thưa** (35 điểm, ~1 tháng) và lấy mẫu theo ngày có tin. Đủ
  đọc xu hướng, không đủ hồi quy beta. Quyết định §12.2 giữ nguyên.
* **BCTC ngành mới có một bản đóng băng**, nên H2 chạy trên giá trị *đã sửa*.
  Chỉ sạch dần khi kho ảnh chụp dày lên — không có cách nào rút ngắn.

---

### 16/09/2026 — GĐ 1 xong

`src/macro/icb.py` · `stock_list/sectors.json` · `loader.py` loại chỉ số ngành khỏi mọi
nhóm · `tests/test_macro_icb.py` (27 test) + 2 test hồi quy trong `test_ta_ranking.py`.
Hướng dẫn dùng: `Documents/huong_dan_chi_so_nganh.md`.

**Độ phủ, đã nạp thật:** 31/31 ngành cấp 1+2, **mỗi ngành 4163 phiên, 04/01/2010 →
16/09/2026**. Không ngành nào thiếu dữ liệu — dự phòng `MIN_SESSIONS` và nhánh `thin`
chưa phải dùng tới lần nào. Số thành viên chênh nhau rất xa: Bảo hiểm 12, Ôtô 13, Năng
lượng 33, Ngân hàng 30 … Công nghiệp **505**.

**Cửa ra đã qua:**

* `technical_report("_ICB_60")` chạy nguyên xi — EMA20/50/100, RSI, ADX, chuỗi swing
  HH→HL→EQH→LL, CHoCH, RVOL, khối ngoại ròng. Không sửa một dòng nào ở `src/ta/`.
* `resolve_universe(None)` trả **80 mã, không có `_ICB_*`**; `"all"`, `"disk"`, `"vn30"`
  cũng sạch. Gọi đích danh `"_ICB_60"` hoặc nhóm `"sectors"` thì ra.

**Một phát hiện không có trong thiết kế, và nó là bẫy thật.** Sáu trong mười một ngành
cấp 1 có **đúng một** con cấp 2, và khi đó FireAnt trả hai chuỗi **trùng khít từng
phiên** — đã đối chiếu 400 phiên trên cả sáu cặp: `10`≡`1010`, `15`≡`1510`, `20`≡`2010`,
`35`≡`3510`, `60`≡`6010`, `65`≡`6510`. Nên **31 mã ngành chỉ là 25 chuỗi phân biệt**.

Quyết định §12.1 ("dựng cả hai cấp") vẫn đúng — nhưng nó kéo theo một hệ quả mà lúc chốt
chưa ai thấy: một bảng "5 ngành mạnh nhất" chạy trên 31 dòng sẽ hiện *Năng lượng* hai
lần dưới hai cái tên khác nhau, ăn hai suất bằng đúng một thông tin, và người đọc không
có cách nào phát hiện. `duplicate_map()` đánh dấu, `distinct_codes()` trả 25 mã, registry
mang `duplicate_of`, và có test đối chiếu **chính chuỗi giá trên đĩa** chứ không tin bảng.

**Một lỗi thật, tìm ra lúc thử tool và đã sửa.** Mở nhóm `sectors` cho
`resolve_universe` kéo theo một hệ quả không ai dự tính: `build_ranking("sectors")` chạy
được, và `save_json` làm mới `reports/xep_hang_moi_nhat.json` — bản trỏ cố định — bằng 31
dòng **chỉ số ngành**. Hai chỗ đọc bản trỏ đó đều hỏng theo, im lặng: `rank_list` xoay lại
bảng cổ phiếu thì ra ngành, và `market.Breadth` đếm "bao nhiêu phần trăm **mã** trên EMA20"
thì đếm ngành — con số đó đi vào **mọi** hồ sơ 1 mã mà không có gì báo, vì cả hai đều là
danh sách symbol có `vs_ema20`. `ranking.is_stock_board()` chặn: bảng có một dòng không
phải cổ phiếu thì vẫn ghi bản có ngày tháng nhưng không đụng bản trỏ. Cùng lý do với luật
"bảng hồi tưởng không đụng bản trỏ" đã có sẵn, chỉ khác đường vào. Bản trỏ đã dựng lại
bằng `build_ranking("all")` (79 mã).

**Một việc còn nợ, để lại cho GĐ 2 chứ không sửa lén ở đây.** `format_snapshot` đọc hình
nến trên chỉ số ngành — bản chạy thử trả về *"Sao băng"*, *"Doji"*, *"Nhảy giá lên"* cho
`_ICB_60`. Nến của một chỉ số là **số bình quân của 33 mã**: không có ai "bị đánh xuống
từ vùng cao" ở đó, và râu trên dài chỉ nghĩa là các mã thành phần lệch pha nhau trong
phiên. Đây đúng loại lỗi mà `CLAUDE.md` đã chặn cho phiên trần/sàn (`candles.py` loại
chúng khỏi mọi bộ phân loại vì "đóng cửa giá trần trông y hệt marubozu tăng nhưng nghĩa
ngược lại"). Cùng lập luận, khác đối tượng. Sửa ở tầng `format` của GĐ 2, khi tầng đó ra
đời — không nhét vào GĐ 1.
