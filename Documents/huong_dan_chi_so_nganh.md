# Hướng dẫn: tầng vĩ mô & ngành

> Trạng thái: **đã xong GĐ 1→6** (16/09/2026). Có tool riêng, có bảng, có nhận định.
> Thiết kế + nhật ký thi công + kết quả hiệu chuẩn: `Documents/plan_macro_sector.md`.

## 30 giây đầu

```
/macro                       → bảng 25 ngành, tách thành 5 cột
/sector năng lượng           → hồ sơ một ngành
macro_dashboard              → lãi suất, CPI, giá xăng dầu, PMI…
sector_members ngân hàng     → mã nào của ngành có trong rổ
update_macro                 → nạp lại toàn bộ (chậm, vài phút)
```

Nói tiếng Việt cũng được: *"ngành nào đang mạnh"*, *"xem ngành dầu khí"*, *"lãi suất
đang thế nào"*.

**Một điều phải biết trước mọi thứ khác:** bảng ngành là **mô tả hiện trạng, không
phải dự báo.** Không phải cách nói khiêm tốn — đó là kết luận của dữ liệu, xem
[phần cuối](#vì-sao-không-có-dự-báo).

---

## Mười tool

| Tool | Việc |
|---|---|
| `sector_board` (`/macro`) | Bảng 25 ngành theo điểm mô tả, 5 cột tách riêng. Ghi HTML sắp xếp được + JSON. |
| `sector_detail` (`/sector <tên>`) | Một ngành: điểm tháo thành phần, RRG, thành viên, nhận định. |
| `macro_dashboard` | 9 nhóm chỉ số vĩ mô, kèm **ngày công bố thật** và kỳ công bố kế tiếp. |
| `sector_evidence` → `sector_submit` | Hai bước: lấy gói bằng chứng đánh số → bạn viết → validator chặn ở cửa nộp. |
| `sector_members` | Ngành gồm mã nào; in **cả hai mẫu số** (niêm yết vs trong rổ). |
| `update_macro` | Nạp chỉ số ngành + RRG + BCTC ngành + vĩ mô + tin nhóm + thành viên. |
| `macro_calibrate` | Chạy lại event study: các cột có dự báo được gì không. |
| `score_sector_news_gemini` | Chấm tin ngành bằng Gemini — **tích luỹ** cho H3. Chạy nền hàng tuần. |
| `news_feature_test` | H3-proxy: feature tin cơ học có thêm gì ngoài giá không. |

Mọi tool nhận `as_of` như bình thường.

---

## Bảng ngành — đọc thế nào

```
| # | Ngành          | Điểm | Mạnh/yếu | RRG | Độ rộng | Dòng tiền | Nền tảng | Tin |
| 1 | Năng lượng  60 |   86 |       30 |   7 |      15 |        15 |       19 |  —  |
| 3 | Bất động sản 35|   67 |       26 |  20 |       2 |         0 |       18 |  —  |
```

**Điểm không bao giờ đứng một mình.** Hàng Bất động sản là lý do: RRG nói *dẫn dắt*
(20/20) nhưng độ rộng 2/14 mã và khối ngoại ở phân vị 2% — chỉ số đang được vài mã
lớn cõng, phần còn lại của ngành không tham gia. Một con số 67 giấu mất đúng điều đó.

| Cột | Trần | Đo cái gì |
|---|--:|---|
| Mạnh/yếu hơn thị trường | 30 | % ngành − % VNINDEX, trộn 20 và 60 phiên |
| Vòng xoay RRG | 20 | góc phần tư: dẫn dắt / cải thiện / suy yếu / tụt lại |
| Độ rộng | 15 | % mã **trong rổ** của ngành trên trung bình 20 phiên |
| Dòng tiền | 15 | khối ngoại ròng 5 phiên, phân vị 250 phiên của chính ngành |
| Nền tảng | 20 | dấu xu hướng ROE/biên, tăng trưởng LN, P/E so **chính ngành** |
| Tin | ±25 | **nhận định của model**, không cộng vào 5 cột trên ở bảng |

Cột **Tin để trống** nghĩa là chưa ai chấm — khác hẳn *đã chấm và thấy trung tính*.

Thành phần **chưa đo được** bị trừ khỏi mẫu số chứ không tính là 0: ngành có dưới 3 mã
trong rổ thì cột Độ rộng để trống và điểm hiển thị là `x/85` chứ không phải `x/100`.

---

## Bảng tra mã ngành

25 chuỗi phân biệt. *TV* = số mã niêm yết trên cả ba sàn · *Rổ* = số mã có trong `data/`.

### Cấp 1 — 11 ngành

| Mã | Ngành | TV | Rổ |
|---|---|--:|--:|
| `60` | **Năng lượng** (dầu khí) | 33 | 3 |
| `30` | Tài chính | 114 | 27 |
| `35` | Bất động sản | 123 | 14 |
| `50` | Công nghiệp | 505 | 13 |
| `55` | Vật liệu cơ bản | 154 | 6 |
| `45` | Hàng tiêu dùng cơ bản | 171 | 7 |
| `40` | Hàng tiêu dùng không thiết yếu | 178 | 6 |
| `65` | Các dịch vụ hạ tầng | 153 | 2 |
| `10` | Công nghệ | 32 | 2 |
| `20` | Chăm sóc sức khỏe | 59 | 1 |
| `15` | Viễn thông | 18 | 0 |

### Cấp 2 — khoan xuống khi cấp 1 quá thô

| Mã | Ngành | TV | Rổ |
|---|---|--:|--:|
| `3010` | **Ngân hàng** | 30 | 17 |
| `3020` | **Chứng khoán** (dịch vụ tài chính) | 72 | 9 |
| `3030` | Bảo hiểm | 12 | 1 |
| `5010` | Xây dựng & vật liệu xây dựng | 292 | — |
| `5020` | Sản phẩm & dịch vụ công nghiệp | 213 | — |
| `5510` | Tài nguyên cơ bản (thép, than) | 85 | — |
| `5520` | Hóa chất (phân bón) | 69 | — |
| `4040` | Bán lẻ | 32 | 3 |
| `4510` | Thực phẩm & đồ uống | 153 | — |
| `4050` | Du lịch & giải trí | 36 | 2 |
| `4010` `4020` `4030` `4520` | Ôtô · Tiêu dùng cá nhân · Truyền thông · Cửa hàng tiện lợi | | |

`sector_members` in bảng đầy đủ và cập nhật.

Gọi bằng tên cũng được: `năng lượng`, `dầu khí`, `ngân hàng`, `chứng khoán`, `thép`,
`phân bón`, `bất động sản`, `bán lẻ`, `điện`…

---

## Thêm phần tin và nhận định — hai bước

```
sector_evidence năng lượng      # bước 1: gói bằng chứng đánh số E01, E02…
                                 # bạn đọc, viết JSON theo schema in ở cuối gói
sector_submit năng lượng <JSON>  # bước 2: validator chặn ở cửa nộp
```

Validator **loại, không nhắc nhở**:

| Hỏng ở đâu | Xử lý |
|---|---|
| Luận điểm không trích `ev_id` | loại luận điểm |
| Trích `ev_id` không tồn tại | loại luận điểm |
| Số trong câu không có trong bằng chứng được trích | loại luận điểm |
| Ngày trong câu > `as_of` | loại luận điểm |
| Thiếu `trigger` hoặc `invalidation` | **loại cả nhận định** |
| Mốc kích hoạt/bác bỏ là số bịa | **loại cả nhận định** |
| Thiếu `source` (tên model viết) | **loại cả nhận định** |

Số luận điểm bị loại **được in ra**. Giấu đi thì validator chỉ làm output *trông* sạch.

**Điều validator không làm được, và phải nhớ:** nó kiểm *câu có khớp bằng chứng không*,
không kiểm *suy luận có đúng không*. "Brent +12%" khớp E20 và "ngành Năng lượng sẽ hưởng
lợi" là hai việc khác nhau. Đó là lý do `invalidation` bắt buộc — thứ chặn suy luận sai
không phải máy, mà là việc người viết phải nói trước điều gì chứng minh mình sai.

---

## Nạp dữ liệu

Không nằm trong `/update`. Chạy riêng, vài phút:

```bash
python -m src.macro.icb --levels 1,2      # chỉ số ngành → data/_ICB_*/
python -m src.macro.rrg                    # RRG + đối chiếu bản tự tính
python -m src.macro.fundamentals           # BCTC ngành, ĐÓNG BĂNG theo ngày
python -m src.macro.series                 # 9 nhóm vĩ mô, ĐÓNG BĂNG theo ngày
python -m src.macro.feed --pages 12        # tin nhóm + giá hàng hoá (nhịp hàng ngày)
python -m src.macro.members                # ánh xạ ngành → rổ
python -m src.macro.calibrate              # hiệu chuẩn
```

Hoặc một lượt qua MCP: `update_macro`.

**Một lần duy nhất, khi dựng kho:** cào sâu để có chuỗi hàng hoá dày.

```bash
python -m src.macro.feed --groups 9,5,4 --pages 180
```

~11 phút, lùi tới 05/2025. Sau đó nhịp hàng ngày 12 trang là đủ — chỉ cần bắt bài mới.

⚠️ **BCTC ngành và chuỗi vĩ mô đóng băng theo ngày.** Ngày không chạy là ngày mất vĩnh
viễn — cùng lý do với `update_fundamentals` ở tầng mã.

### Bật chạy tự động hàng tuần

`weekly_macro.bat` gói cả nhịp tuần: nạp chỉ số ngành + RRG + thành viên, **đóng băng**
BCTC ngành và chuỗi vĩ mô, nạp tin, **chấm tin bằng Gemini**, rồi hiệu chuẩn lại. Log vào
`macro/logs/weekly_<ngày>.log`.

Đăng ký (chạy một lần, trong cửa sổ Admin):

```bat
schtasks /create /tn "vn-ta macro weekly" /tr "D:\Trader\dashboard-alpha-score\weekly_macro.bat" /sc weekly /d SUN /st 07:00
```

Cần `GEMINI_API_KEY` (hoặc `GOOGLE_API_KEY`) trong biến môi trường **hệ thống** — biến
của riêng phiên terminal không đến được Task Scheduler.

---

## Bốn cảnh báo khi đọc số

**1. Chỉ số ngành không dựng từ rổ 80 mã của bạn.** Năng lượng +16,9% là chuyện của
**33 mã**, rổ ta có 3. Công nghiệp là 505 mã. Độ phủ thấp nghĩa là phần lớn sức mạnh
nằm ở mã bạn không có — `sector_members` in cả hai con số.

**2. Chuỗi vĩ mô lọc theo NGÀY CÔNG BỐ, không theo kỳ.** CPI tháng 8 ra giữa tháng 9,
nên báo cáo đứng ở 31/08 **không** thấy nó. Cột `Công bố` trong `macro_dashboard` là
mốc thật; độ trễ là **giả định** (30 ngày cho tháng, 45 cho quý) và ghi ra để cãi lại.

**3. Độ dày chuỗi hàng hoá là thứ ĐO ĐƯỢC, đọc nhãn chứ đừng đoán.** Sau lượt cào 180
trang: Brent **472 điểm phủ 97% phiên sàn**, WTI 93%, vàng 100% — đủ dày để hồi quy.
Nhưng Dow Jones chỉ 77% và bị đánh dấu **chuỗi thưa**. Mỗi chỗ dùng in kèm độ phủ thật;
dưới 80% phiên sàn là thưa.

Chỉ **4 hàng hoá + 3 chỉ số Mỹ** thật sự có dữ liệu (Brent, WTI, vàng, bạc, DJI, S&P,
Nasdaq). Đồng và khí tự nhiên **không có điểm nào** — từng được khai báo làm biến nền
cho 3 ngành, đã thay bằng chỉ số vĩ mô còn sống.

**4. RRG có hai bản, và chúng bất đồng khoảng 1/5 số phiên.** Bản FireAnt là bản hiển
thị; bản tự tính (12/26/750, đà 5 phiên) khớp **85%** trên ngành dò và **80,4%** khi
kiểm chéo bảy ngành khác. Khi hai bản nói hai góc khác nhau **ở chính phiên đang xem**,
output ghi `⚠️ bản tự tính đọc ra …` — đọc cảnh báo đó, đừng bỏ qua.

---

## Vì sao không có dự báo

Hiệu chuẩn (`macro_calibrate`) chạy trên toàn bộ 2010→nay và trả về **ba kết quả âm
tính**:

| Giả thuyết | Kết quả |
|---|---|
| Góc RRG → lợi suất tương đối ngành sau 20 phiên | *dẫn dắt* cho p = 0,025… |
| …nhưng chạy thêm cửa sổ 10 và 60 phiên | **không cửa sổ nào còn ý nghĩa** |
| Xu hướng ROE ngành → lợi suất tương đối | nằm đúng trên nền placebo |

Ba cửa sổ × bốn góc là **12 phép kiểm trên cùng dữ liệu**. Ở mức 0,05 thì kỳ vọng có
0,6 kết quả dương tính giả — một p = 0,025 lẻ loi nằm gọn trong đó. Hiệu ứng thật ở cửa
sổ 20 phiên là **+0,31 điểm phần trăm**, tỷ lệ vượt thị trường 49% so với nền 46–47%.

Báo cáo riêng cửa sổ 20 phiên và im lặng về hai cửa sổ kia là *p-hacking*, và không ai
phát hiện được. Nên phép chặn nằm trong code (`ALPHA_ADJUSTED`), không nằm trong ý chí.

**Hệ quả:** bảng ngành trả lời *"ngành này đang ở đâu so với các ngành khác, ngay lúc
này"* — mô tả kiểm chứng được. Nó **không** trả lời *"ngành nào sẽ tăng"*. Trần điểm là
**trọng số biên tập**, ghi ra để cãi lại, không phải sức dự báo đo được.

Điều đó không làm bảng vô dụng: nó vẫn gộp năm phép đo rời rạc thành một thứ tự đọc
được, vẫn tháo ngược ra được từng thành phần, vẫn nói thẳng mình đứng ở đâu. Cái nó bỏ
đi chỉ là lời hứa không có bằng chứng.

### Nợ cuối: H3 — và vì sao nó phải đợi

*Điểm tin có thêm gì ngoài các cột đo được?* — chưa trả lời được, và lý do là **nguyên
tắc chứ không phải kỹ thuật**: một model chấm tin tháng 3 vào hôm nay đã biết thị trường
đi đâu sau đó. `as_of` cắt được dữ liệu đưa vào prompt, không cắt được trí nhớ của model.
Điểm tin backfill sẽ đẹp một cách giả tạo.

Nên hai nhánh chạy song song:

**Nhánh tích luỹ tiến** — `weekly_macro.bat` gọi `score_sector_news_gemini` mỗi tuần. Sáu
tháng nữa H3 kiểm được với dữ liệu sạch. Bản Gemini đi qua **cùng validator** với bản
viết tay, và bản viết tay (`sector_submit`) **đè** bản Gemini cùng ngày — không bao giờ
ngược lại.

**Nhánh đo ngay** — `news_feature_test`. Định dùng hai feature backfill được mà không
dính nhìn trước. **Chỉ một cái sống:**

| Feature | Trạng thái |
|---|---|
| Sắc thái FireAnt gán lúc đăng | ❌ **trường rỗng** — 53.996/53.998 bài bằng 0 |
| Khối lượng tin, chuẩn hoá theo chính ngành | ✅ dùng được |

Sắc thái không phải "đo rồi thấy vô dụng" — nó là một trường có trong lược đồ mà **không
ai điền**. Kho tin gắn mã của tầng `src/news/` cũng thế (57.909/57.928), và gọi thẳng API
300 bài mẫu ra 0 hết. `news_feature_test` **loại** nó khỏi phép kiểm kèm lý do có số,
thay vì để nó chạy thành một dòng "không tách được khỏi nền" — dòng đó đọc như *đã đo và
thấy vô dụng*.

Kết quả chạy 16/09/2026 trên feature còn lại, đo **bên trong từng góc RRG** (giữ giá cố
định rồi hỏi tin còn nói gì), ngưỡng Bonferroni:

```
khối lượng tin · đang cải thiện   n=41/41   chênh +1.61%   p=0.422
khối lượng tin · dẫn dắt          n=35/35   chênh +2.64%   p=0.422
khối lượng tin · tụt lại          n=31/31   chênh −1.92%   p=0.623
```

Không nhóm nào tách được khỏi nền. Nhưng đây là **bằng chứng yếu**, không phải chứng
minh: một phép đếm bài không đọc nội dung, và nó không mã hoá nổi thứ §9.9 của plan tin
tức nêu — *"lãi ròng giảm 50% nhưng vượt 20% kế hoạch năm"*. **Không thay được việc đợi
H3 thật.**

Dù nhánh nào, luật cuối vẫn thế: **H3 âm tính thì cột Tin ở lại báo cáo nhưng không vào
điểm.**

Ba nợ còn lại đã đóng (16/09/2026): chuỗi Brent nạp sâu 16,5 tháng nên hết thưa; H2 chạy
lại trên BCTC **năm** (ít bị sửa hơn, lùi 2006) vẫn âm tính nên hạn chế "một bản đóng
băng" không che tín hiệu nào; và toàn bộ chỉ số vĩ mô quá hạn giờ **hiện tuổi** thay vì
nằm im cạnh số tươi.

---

## Chỉ số vĩ mô: 30/96 đã chết

Kiểm kê ngày 16/09/2026 — **66 còn sống, 30 quá hạn**:

| | |
|---|---|
| Tệ nhất | Lãi suất liên ngân hàng 12 tháng — **8020 ngày** (22 năm), tần suất ghi là "hàng ngày" |
| Đáng lo | Niềm tin người tiêu dùng — 1675 ngày, từng là biến khai báo **duy nhất** của ngành `40` |
| Cả nhóm chết | `InterestRate` — 17 chỉ số, không còn cái nào cập nhật |
| Nhanh nhất còn sống | **78 ngày** (chuỗi hàng tháng) — FireAnt không có chuỗi vĩ mô nào nhanh hơn tháng |

`macro_dashboard` in cột **Cũ** và liệt kê chỉ số quá hạn ở cuối; ngưỡng tính theo **tần
suất** của chính chỉ số đó (45 ngày là bình thường với quý, rất cũ với ngày). Gói bằng
chứng đính tuổi vào chính câu, nên model đọc được là số đã cũ.

`drivers.json` đã dọn: từ 2/4 biến vĩ mô quá hạn xuống **1/10**. Cái còn lại là lãi suất
liên ngân hàng — giữ vì cả nhóm không còn gì thay, và giờ nó tự khai tuổi.
