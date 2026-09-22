# Phương án: BÀN PHÂN TÍCH (`src/desk/`) — làm việc như một khối phân tích CTCK

> Trạng thái: **đã thi công trọn GĐ0 → GĐ6** (19–20/09/2026). Nhật ký ở §11 — chỗ
> nào dữ liệu bác lại thiết kế thì §11 nói rõ, và có bốn chỗ như vậy.
>
> Mọi con số đếm trong §2 là **gọi thật ngày 19/09/2026** bằng token trong
> `access_token.txt`, không suy ra từ đặc tả — endpoint nào trả rỗng thì ghi thẳng là
> rỗng. Mọi ngưỡng là **đề xuất khởi điểm**, §6 là việc phải làm trước khi tin bất kỳ
> con số nào.
>
> §8 (bàn này có công bố *tỷ trọng* không) **đã được chốt: phương án B** — sổ mô phỏng
> có tỷ trọng, trọng số do quy tắc tính chứ không do model đặt.

`src/ta/` trả lời "biểu đồ **một mã** đang nói gì". `src/news/` trả lời "ngoài biểu đồ
còn chuyện gì, đã vào giá chưa". `src/macro/` trả lời "ngành nào sáng, ngành nào tối".
Ba tầng đó đều là **phép đo rời**, và mỗi tầng đã tự chặn mình rất kỹ để không nói quá.

Tài liệu này thiết kế tầng thứ tư trả lời câu mà một khối phân tích CTCK tồn tại để
trả lời: *đứng ở đâu, bao nhiêu, vì sao, và điều gì làm nó sai* — rồi **chịu trách
nhiệm** về câu đó bằng một cuốn sổ không sửa được.

---

## 0. Vì sao thêm tin tức không giải quyết được — cái thiếu nằm ở chỗ khác

Hệ thống hôm nay có bảy nguồn đo và **một** chỗ chứa ý kiến (`ta/thesis.py`, phạm vi:
một mã, một phiên). Nối chúng lại thì thiếu đúng bốn mắt xích, và cả bốn đều là xương
sống của một bản báo cáo CTCK:

| Mắt xích | Repo hôm nay | Khoảng trống |
|---|---|---|
| **Quan điểm thị trường** | `market.py` đo VNINDEX, độ rộng, phiên phân phối | Không ai *viết* quan điểm. Đo xong rồi để đó |
| **Phân bổ ngành** | `macro/score.py` chấm điểm — và §"Điểm ngành là MÔ TẢ" cấm đọc nó như dự báo | Không có nấc OW / N / UW, không có lý do theo động lực ngành |
| **Vị thế** | `thesis.py` cho tư thế + 3 mốc | Không có **quy mô**. "Nghiêng về tăng" mà không nói bao nhiêu phần trăm sổ thì không kiểm chứng được |
| **Sổ theo dõi** | `forecast.py` — nhưng là kỳ vọng *kỹ thuật tự sinh*, không phải quan điểm *do người/model phát biểu* | Không có tỷ lệ đúng, không có so với nền, không có hạn dùng của một quan điểm |

Và về **dữ liệu**, hai đầu vào kinh điển nhất của một bản báo cáo công ty thì chưa có:

1. **Định giá có chuỗi lịch sử.** `ta/fundamentals.py` chỉ giữ được ảnh chụp *hôm nay*
   và tự đóng băng từng ngày — đúng, nhưng hệ quả đã ghi trong `CLAUDE.md`: bảng hồi
   tưởng về ngày trước lượt đóng băng đầu tiên **không có** phần định giá. Nên câu mà
   mọi CTCK mở đầu — *"P/E 12,4 lần, thấp hơn trung vị 5 năm của chính nó 22%"* — hôm
   nay **không phát biểu được**. §2.3 cho thấy nó dựng lại được, và rẻ.
2. **Dòng tiền.** `buyForeignValue`, `sellForeignValue`, `propTradingNetValue`,
   `putthroughValue` nằm trong **mọi** `StockRecord` từ 2010, và hiện chỉ được dùng ở
   đúng hai chỗ: một dòng "khối ngoại ròng" của phiên cuối trong `snapshot.py:204`, và
   phần hợp đồng trong `futures.py`. Một khối phân tích CTCK mở bản tin phiên bằng con
   số này. Ta có 16 năm dữ liệu và chưa đo nó lần nào.

Thêm một nguồn nữa mà repo chưa biết là có — §2.1.

---

## 1. Một khối phân tích CTCK thật sự sản xuất cái gì

Bỏ qua phần bán hàng, sản phẩm của họ gọn trong năm thứ, khác nhau ở **nhịp** và ở
**đơn vị quyết định**:

| Sản phẩm | Nhịp | Đơn vị | Repo có sẵn phần nào | Thiếu |
|---|---|---|---|---|
| **Bản tin phiên** | mỗi phiên | thị trường | `market.py`, `futures.py`, `ranking` | dòng tiền, mã dẫn dắt chỉ số, "phiên tới nhìn gì" |
| **Chiến lược tuần/tháng** | tuần | thị trường + ngành | `sector_board`, `macro_dashboard` | quan điểm chỉ số có kịch bản, nấc phân bổ ngành, **tỷ trọng tiền mặt** |
| **Báo cáo công ty** | theo sự kiện | mã | `/report <MÃ>` đã rất gần | dải định giá lịch sử, KQKD so với chính nó, đồng thuận CTCK khác |
| **Báo cáo ngành** | quý | ngành | `sector_detail` | biến động lực ngành nối với KQKD thành viên |
| **Danh mục khuyến nghị + kết quả** | liên tục | sổ | `forecast.py` (hạt giống) | sổ lệnh mô phỏng, **bảng điểm của chính mình** |

Ba đặc điểm khiến một bản báo cáo CTCK *là* báo cáo CTCK, chứ không phải bản tổng hợp:

1. **Đi từ trên xuống, và các tầng phải khớp.** Quan điểm thị trường → phân bổ ngành →
   chọn mã → vị thế. Nếu ngành ngân hàng đang **UW** mà ba mã đầu danh mục là ngân hàng
   thì bản báo cáo tự mâu thuẫn — và người đọc bắt được ngay. Đây là thứ **kiểm tra được
   bằng code** (§5), và là giá trị lớn nhất mà kiến trúc hiện tại đang bỏ phí.
2. **Mỗi phát biểu có một con số gắn vào.** Không "thận trọng" mà "giữ 40% tiền mặt";
   không "tích cực với thép" mà "OW thép, 12% sổ". Con số là thứ làm câu nói **sai được**.
3. **Có hạn sử dụng.** Một quan điểm không được tái khẳng định là một quan điểm hết hiệu
   lực, không phải một quan điểm vẫn đúng.

Cái mà khối phân tích CTCK **không** có — và là chỗ hệ thống này thắng được họ — là
**bảng điểm công khai của chính mình**. Không CTCK nào công bố tỷ lệ đúng của các khuyến
nghị đã phát hành. Repo này đã có sẵn văn hoá đo (`calibrate.py`, `futures_stats`,
`news_stats`, nền placebo, mẫu không chồng lấn), nên đây vừa là sản phẩm khả thi nhất,
vừa là thứ khác biệt nhất.

---

## 2. Kiểm kê nguồn — đã gọi thật ngày 19/09/2026

### 2.1 ⭐ Kho báo cáo phân tích của các CTCK — repo chưa từng gọi tới

`/swagger/docs/v1` có **379 path**; bốn cái dưới đây không nằm trong bất kỳ tài liệu nào
của repo:

| Endpoint | Trả về | Đã kiểm chứng |
|---|---|---|
| `GET /reports/sources` | Đơn vị phát hành | ✅ **152 nguồn** — SSI, BSC, VNDS, VCSC, Mirae Asset, KBSV, Shinhan, HSBC, Morgan Stanley, Citigroup… |
| `GET /reports/categories` | Danh mục | ✅ 9 — *Phân tích công ty*(1), *Phân tích ngành*(2), *Kinh tế vĩ mô*(3), *Tổng quan thị trường*(4), *Thị trường thế giới*(5), *Trái phiếu*(16), *Hàng hoá phái sinh*(17)… |
| `GET /reports/search` | Tìm theo `startDate`/`endDate` (bắt buộc) + `categoryID`/`sourceID`/`sectorID`/`symbol`/`keywords`, có phân trang | ✅ 01/08→19/09/2026: **530 báo cáo**. Danh mục 1 riêng năm 2026: **5.561**. Riêng FPT từ 01/2024: **136** |
| `GET /reports/{reportID}` | Chi tiết, gồm **`description` = tóm tắt của chính chuyên viên** (HTML) | ✅ ví dụ MWG/VDSC: *"KQKD Q2-2026 vượt kỳ vọng chuyên viên 15% với doanh thu thuần 48.751 tỷ (+29,5% svck), LNST Cty Mẹ 3.303 tỷ (+100,4% svck)…"* |

Đọc thử **40 tóm tắt** của danh mục 1 (06→09/2026), đếm thật:

- **199/200** bản ghi mang sẵn trường `symbol` → không cần suy ra mã, bỏ được cả lớp gán
  nhầm mà §9.5 của plan tin tức phải dựng riêng để chống.
- **16/40** tóm tắt chứa một từ khuyến nghị (`MUA`, `KHẢ QUAN`, `TRUNG LẬP`, `TÍCH CỰC`,
  `BÁN`…).
- **0/40** tóm tắt chứa **giá mục tiêu**. Giá mục tiêu nằm trong thân file PDF, và đặc tả
  **không có endpoint tải file** (grep `download|file|attach` trên 379 path: không có).

→ Kết luận thẳng, không được nói quá: dựng được **bảng theo dõi độ phủ + nhịp phát hành +
từ khuyến nghị**; **không** dựng được bảng giá mục tiêu đồng thuận nếu không bóc PDF, mà
PDF thì API không đưa. Và ngay cả khi bóc được thì đó là **tác phẩm có bản quyền của
người khác** — chỉ được rút *sự kiện số* ra dùng, không lưu trữ lại nội dung để phát
hành. §7.5 nói rõ.

### 2.2 `/symbols/{s}/estimated-price` — định giá dựng sẵn, và nó là hộp đen

Gọi thật cho FPT:

```
DCF       66.213  (trọng số 12,7%)      Graham1   87.907  ( 6,0%)
P/E       71.580  (         54,8%)      Graham2   77.895  (18,9%)
P/B       39.091  (          2,6%)      Graham3   55.215  ( 4,9%)
                         → composedPrice 71.425
```

Sáu mô hình + một giá tổng hợp có trọng số. **Nhưng**: không công bố tham số (tỷ lệ chiết
khấu, tăng trưởng giả định, kỳ EPS dùng), và là **snapshot của hôm nay** — cùng họ với
`fundamental` / `financial-indicators`, nên chịu đúng luật §"Chỉ số cơ bản chỉ có trạng
thái hôm nay": đóng băng `desk/snapshots/<mã>/<ngày>.json`, đọc bản **≤ mốc**, không rơi
về bản mới hơn. Chưa đóng băng thì **không có** chuỗi để hiệu chuẩn, và ngày không chạy
là ngày mất vĩnh viễn.

Vị trí của nó trong hệ thống: **một ý kiến của bên thứ ba có tên**, đứng cạnh đồng thuận
CTCK và cạnh dải định giá tự tính — **không** phải giá mục tiêu của bàn. Ba con số ba
nguồn đứng cạnh nhau nói được nhiều hơn một con số trung bình của cả ba, đúng lý lẽ đã
dùng cho "hai bản chấm tin không bao giờ lấy trung bình".

⚠️ **Và nó không phủ nhóm tài chính.** Lượt đóng băng đầu tiên (19/09/2026, cả 80 mã):
**53 mã có số, 27 mã trả rỗng — và cả 27 đều là ngân hàng, công ty chứng khoán hoặc
bảo hiểm** (ACB, BID, CTG, VCB, TCB, MBB, SSI, VCI, VND, BVH…). Hợp lý về mô hình — DCF
và Graham không áp được lên bảng cân đối của một ngân hàng — nhưng hệ quả thì phải nói
ra: cột định giá sẽ trống ở **một phần ba rổ**, và đó đúng là phần chiếm tỷ trọng lớn
nhất của chỉ số. Vì thế mỗi lượt chạy ghi một **nhật ký** `desk/snapshots/_runs/<ngày>.json`:
thiếu nó thì *"đã hỏi và FireAnt không có"* trông y hệt *"quên chạy"*, mà hai câu đó dẫn
tới hai hành động khác nhau.

### 2.3 ⭐ BCTC theo quý — chuỗi định giá lịch sử dựng lại được, và rẻ

```
GET /symbols/FPT/full-financial-reports?type=2&year=2026&quarter=2&limit=40
→ 22 dòng KQKD × 40 quý  (Q3/2016 → Q2/2026)   trong ĐÚNG MỘT request
```

80 mã × 1 request ≈ **100 giây** ở nhịp 1,2 s hiện tại. Đây là chỗ mở khoá lớn nhất của
cả phương án: có LNST theo quý là có **EPS trượt 4 quý**, có EPS trượt là có **chuỗi P/E
theo phiên**, và có chuỗi P/E là phát biểu được câu mà mọi báo cáo CTCK mở đầu bằng — *rẻ
hay đắt so với chính nó*, chứ không chỉ *so với ngành hôm nay*.

Mốc **không nhìn trước** thì đã nằm sẵn trên đĩa: `news/index.db` có **5.520**
`timescale_marks`, **59 quý**, sớm nhất 14/01/2015, mỗi mốc `label='F'` mang ngày công bố
+ doanh thu + lợi nhuận + YoY đã parse. Bẫy của nó ở §7.2.

### 2.4 Dòng tiền — 16 năm nằm sẵn trên đĩa, chưa đo lần nào

`StockRecord` có đủ `buyForeignQuantity/Value`, `sellForeignQuantity/Value`,
`currentForeignRoom`, `propTradingNetDealValue`, `propTradingNetPTValue`,
`propTradingNetValue`, `putthroughVolume/Value` — từ 2010, cho cả 80 mã.

Đây là nguồn **duy nhất trong phương án này hiệu chuẩn được ngay hôm nay**: đủ lịch sử,
không phụ thuộc model ngôn ngữ, không phải đợi tích luỹ tiến. Nên nó đi trước (§9).

---

## 3. Kiến trúc đề xuất — `src/desk/`

Bảy module. Thứ tự dưới đây là thứ tự **phụ thuộc**, không phải thứ tự thi công (§9).

### 3.1 `ledger.py` — cuốn sổ. Làm TRƯỚC, kể cả khi chưa có gì để ghi vào

Lý lẽ y hệt luật "**Điểm tin KHÔNG backfill được**" đã ghi trong `CLAUDE.md`, và mạnh hơn
một bậc: **bảng điểm của một bàn phân tích không backfill được bằng bất kỳ giá nào**.
Không thể hôm nay ngồi viết lại xem tháng 3 mình đã nghĩ gì — mọi bản "dựng lại" đều biết
thị trường đã đi đâu. Một bàn chạy hai năm không có sổ là một bàn **không có gì để chứng
minh**, và đó là toàn bộ khác biệt giữa nó với một cột báo.

Sổ ghi **chỉ thêm, không sửa**:

```python
@dataclass(frozen=True)
class Entry:
    entry_id: str          # <loại>-<đối tượng>-<phiên>-<hash8>
    kind: str              # market | sector | stock | book
    subject: str           # "VNINDEX" | "_ICB_8350" | "FPT" | "BOOK"
    session: str           # PHIÊN DỮ LIỆU, không phải ngày hôm nay
    author: str            # tên model/người — bắt buộc, §"không biết của ai thì không duyệt được"
    stance: str            # STANCES hiện có, dùng lại nguyên
    confidence: str        # NẤC cao/vừa/thấp — book.py đổi nấc thành trọng số
    weight_pct: float|None # §8 → phương án B: trường này tồn tại
    horizon_sessions: int  # HẠN. Hết hạn mà không tái khẳng định = hết hiệu lực
    trigger: str
    invalidation: str
    target: str|None
    evidence_hash: str     # hash gói bằng chứng đã đọc — chống "hồi đó tôi có thấy cái đó đâu"
    supersedes: str|None   # đổi quan điểm thì TRỎ tới bản cũ, không đè lên nó
    created_at: str
```

Ba luật đóng vào code, không phải vào tài liệu:

- **Không có `update()`, không có `delete()`.** Đổi ý là ghi một `Entry` mới có
  `supersedes`. Cả hai bản cùng nằm trong bảng điểm.
- **`session` khoá theo phiên dữ liệu**, dùng lại nguyên cơ chế `thesis.load_thesis`:
  khớp đúng phiên hoặc trả `None`, không rơi về bản gần nhất.
- **`evidence_hash` là bắt buộc.** Nó trả lời được câu hỏi duy nhất thật sự quan trọng khi
  soi lại một quan điểm sai: *sai vì đọc thiếu, hay sai vì đọc đủ mà suy sai.* Hai loại
  sai đó chữa bằng hai cách khác hẳn nhau.

Lưu ở `desk/ledger/<năm>/<kind>/<entry_id>.json` + `desk/ledger/index.db` (SQLite, một
kết nối cho mỗi lượt ghi, `PRAGMA busy_timeout = 15s` theo đúng luật đã có).

### 3.2 `flows.py` — dòng tiền, chuẩn hoá theo chính mã

Đầu ra cho một mã, một phiên (và chuỗi của nó):

| Số đo | Cách tính | Vì sao không lấy số thô |
|---|---|---|
| `foreign_net_bn` | `(buyForeignValue − sellForeignValue)/1e9` | — |
| `foreign_net_pct` | ròng chia **giá trị khớp trung bình 20 phiên của chính mã** | 300 tỷ ở VCB là chuyện thường, ở DGW là chuyện lớn. So tuyệt đối giữa các mã là xếp hạng theo vốn hoá. (Thiết kế ban đầu gọi là `_z`; đổi tên vì nó là **tỷ lệ**, không phải điểm chuẩn — một cái tên hứa hẹn phương sai mà không tính phương sai là một cái bẫy đọc) |
| `foreign_streak` | số phiên liên tiếp cùng dấu | Một phiên là nhiễu; chuỗi là hành vi |
| `room_used_pct` | từ `currentForeignRoom` + `freeShares` | Mã **kín room** thì bán ròng của khối ngoại là cơ chế, không phải quan điểm (§7.3) |
| `prop_net_bn` | `propTradingNetDealValue` | Tự doanh — **chỉ phần khớp lệnh**; phần thoả thuận (`propTradingNetPTValue`) tách riêng |
| `pt_share_pct` | `putthroughValue / totalValue` | Phiên có tỷ trọng thoả thuận cao là phiên **sang tay**, không phải phiên cung cầu — đúng lý lẽ `priceImpactVolume` đã dùng cho volume |

Gộp lên hai cấp: **ngành** (theo `_ICB_`, gộp trên `distinct_codes()`) và **thị trường**.
Ở cấp thị trường thì con số này chính là dòng mở đầu bản tin phiên của mọi CTCK.

⚠️ Module này **không được phát biểu gì** cho tới khi qua §6.1.

### 3.3 `valuation.py` — dải định giá của chính mã, không nhìn trước

```
LNST 4 quý trượt  ←  full-financial-reports (type=2)
ngày công bố      ←  timescale_marks label='F'   (đã có trên đĩa)
giá điều chỉnh    ←  data/<MÃ>/                  (đã có trên đĩa)
      ↓
chuỗi P/E theo phiên  →  phân vị so với chính nó (3 năm / 5 năm)
                      →  so với P/E ngành (/icb/{code}/financial-data)
```

Ba ràng buộc, mỗi cái chặn một kiểu sai đã thấy ở các tầng trước:

1. **EPS chỉ được biết từ ngày công bố trở đi**, không phải từ ngày kết thúc quý — đúng
   luật "Chuỗi vĩ mô lọc theo NGÀY CÔNG BỐ" đã có. Sai lệch này **đi một chiều**: nó làm
   mọi thứ trông thông minh hơn thực tế.
2. **EPS phải quy về cùng hệ điều chỉnh với giá** (§7.1 — bẫy nặng nhất của cả phương án).
3. **Dưới 12 quý thì `comparable=False`.** Phân vị của 6 quan sát là một con số trông như
   đã đo mà chưa đo gì — cùng lý lẽ `MIN_PEERS=3` của `ta/sector.py`.

Đầu ra không bao giờ là một con số "giá hợp lý". Nó là: *P/E hiện tại `x` · phân vị `p`
trong 5 năm của chính nó · ngành `y` · và **điều gì đã xảy ra** mấy lần trước khi nó
xuống dưới phân vị 20* — câu cuối là phần duy nhất có sức nặng, và nó là **base rate**,
đo được bằng chính bộ máy `futures_stats` đang chạy.

### 3.4 `consensus.py` — CTCK khác đang nói gì, và họ nói có đúng không

Hai nửa, nửa sau mới là lý do làm nửa đầu:

**(a) Theo dõi độ phủ.** Ai viết về mã nào, bao lâu một lần, tóm tắt nói gì. Ba số đo dùng
được ngay:

- `coverage_count` 12 tháng — mã không ai viết là mã **không có người mua tổ chức**, và đó
  là thông tin về thanh khoản tương lai.
- `burst` — ≥ 3 báo cáo trong 10 phiên. Một cụm như vậy **tự nó là một sự kiện**, đo được
  bằng `news/reaction.measure` có sẵn.
- `rating_word` rút từ tiêu đề + tóm tắt, **kèm nguyên văn câu chứa nó** — bác lại được,
  đúng cách `redflag.py` đang làm. Đo thật: chỉ ~40% bản ghi có từ này, nên cột trống là
  *không nói*, không phải *trung lập*.

**(b) Bảng điểm của các CTCK.** Với mỗi báo cáo, chạy event study quanh `date` bằng đúng
`reaction.measure` đang có (và **phải truyền `as_of`**, theo luật đã ghi). Ra được: sau
báo cáo của nguồn X, mã của họ thật sự đi đâu so với VNINDEX ở 1/5/10/20 phiên — so với
**nền placebo** là mã bất kỳ cùng phiên, cùng thời gian nắm giữ.

Đây là thứ không ai ở thị trường này công bố, dữ liệu thì có sẵn hàng nghìn quan sát từ
2015. ⚠️ Nó mang một sai lệch **một chiều** phải in kèm mọi kết quả, không được giấu: §7.4.

### 3.5 `calendar.py` — lịch xúc tác

Không có gì mới phải nạp, chỉ gộp thứ đã có thành một dòng thời gian **phía trước**:

| Nguồn | Sự kiện | Đã có ở |
|---|---|---|
| `timescale_marks` `F` | mùa BCTC quý — suy từ chính lịch các quý trước của **mã đó** | `news/index.db` |
| `timescale_marks` `D` | ngày GDKHQ, tỷ lệ cổ tức | `news/index.db` |
| `ta/futures.py` | phiên đáo hạn (thứ Năm thứ ba) | có sẵn |
| `macro/series.py` | kỳ công bố kế tiếp của chỉ số vĩ mô | có sẵn (`/macro-data/{type}/info`) |
| `holder_transactions` | cửa sổ đăng ký mua/bán đang mở của nội bộ | `news/index.db` |

Giá trị của nó: đây là thứ **duy nhất trong cả hệ thống nhìn về phía trước mà không phải
dự báo** — ngày đáo hạn là một sự thật lịch, không phải một ý kiến.

### 3.6 `view.py` — quan điểm thị trường & phân bổ ngành

Đúng kiến trúc `thesis.py`, nhân lên hai cấp mới, **không viết lại**:

- `build_market_evidence()` — gói bằng chứng cấp thị trường: `market.py` (chỉ số, độ rộng,
  phiên phân phối) + `weekly.py` + `flows.py` cấp thị trường + `futures.py` +
  `macro_dashboard` + `calendar` 20 phiên tới.
- `build_sector_evidence()` — đã có gần hết ở `macro/`; thêm dòng tiền ngành + KQKD thành
  viên + định giá trung vị ngành.
- `WRITING_GUIDE` riêng cho từng cấp, cùng luật với bản đang chạy, thêm **hai** luật:
  - **Phải có kịch bản kèm điều kiện, không phải một con số.** "VNINDEX 1.320–1.360 nếu độ
    rộng giữ trên 55%; thủng 1.290 thì kịch bản này sai" — không phải "VNINDEX sẽ lên
    1.350".
  - **Phải nói tỷ trọng tiền mặt.** Một quan điểm "thận trọng" không kèm con số là câu
    không sai được, và câu không sai được thì không vào sổ được.
- `submit_market_view()` / `submit_sector_view()` → ghi thẳng vào `ledger`.

### 3.7 `book.py` + `scorecard.py` — sổ lệnh mô phỏng và bảng điểm

**`book.py`** dựng danh mục mô phỏng từ các `Entry` đang còn hiệu lực. Luật quan trọng
nhất, và nó là luật chống chính mình:

> **Trọng số do QUY TẮC tính, không do model đặt.**

Model chọn *mã nào vào sổ* và *ở nấc tin cậy nào* (3 nấc). Từ đó `book.py` tính trọng số
bằng công thức cố định — nghịch đảo ATR%, chặn trần theo mã và theo ngành, phần còn lại là
tiền mặt. Lý do: một con số trọng số do model tự viết ra **âm thầm mã hoá đòn bẩy và khẩu
vị rủi ro** mà không ai duyệt được; còn "mã X, tin cậy cao" thì duyệt được. Đây đúng là lý
lẽ đã dùng khi bỏ chữ mua/bán để lấy tư thế + mốc.

**`scorecard.py`** replay toàn bộ sổ, đúng cách `forecast.evaluate()` đang làm (file trên
đĩa chỉ là cache, sửa tay thì lượt sau tự chữa). In ra:

| Cột | Ghi chú |
|---|---|
| Tỷ lệ chạm mục tiêu / bị huỷ / hết hạn | theo `kind`, **không gộp** ba cấp vào một tỷ lệ |
| Lợi suất trung vị **so với VNINDEX** | tuyệt đối trong thị trường tăng là số vô nghĩa |
| So với **nền placebo** | mã ngẫu nhiên cùng phiên, cùng thời gian nắm giữ, 1.000 lượt |
| `n` **không chồng lấn** | theo đúng luật §6 đã có |
| Hiệu chuẩn nấc tin cậy | nấc "cao" có thật sự đúng nhiều hơn nấc "vừa" không |

Một dòng bắt buộc in kèm mọi bảng điểm dưới ~50 quan sát độc lập: *chưa đủ để nói bàn này
đúng hay sai* — đúng luật "chưa đo được ≠ đã đo và thấy phẳng".

---

## 4. Đầu ra và tool MCP

| Tool | Làm gì | Ghi ra |
|---|---|---|
| `desk_daily` | Bản tin phiên: chỉ số + dòng tiền + độ rộng + phái sinh + mã dẫn dắt + lịch 5 phiên tới | `reports/<ngày>/ban_tin.html` |
| `desk_market_evidence` → `desk_submit_market` | Gói bằng chứng cấp thị trường → model viết → vào sổ | `desk/ledger/` |
| `desk_sector_allocation` | Bảng OW/N/UW đủ 25 chuỗi ngành, mỗi nấc kèm lý do + biến động lực | `reports/<ngày>/phan_bo_nganh.html` |
| `desk_strategy` | **Sản phẩm chính**: quan điểm thị trường + phân bổ ngành + danh mục + tiền mặt, một file | `reports/<ngày>/chien_luoc.html` |
| `desk_valuation <MÃ>` | Dải P/E–P/B lịch sử + base rate ở các phân vị | (chèn vào `/report`) |
| `desk_flows` | Dòng tiền theo mã/ngành/thị trường, xếp hạng theo `z` | |
| `desk_consensus <MÃ>` | Ai viết gì, khi nào + bảng điểm nguồn | |
| `desk_calendar` | Lịch xúc tác 20 phiên tới | |
| `desk_scorecard` | Bảng điểm của bàn | `reports/bang_diem.html` |

Slash command: `/desk` (bản tin phiên), `/strategy` (chiến lược tuần), `/scorecard`.
Toàn bộ câu chữ vào `src/desk/format.py` theo đúng luật đang có; HTML render lại markdown
của chính formatter đó, không tự viết câu; file tự chứa, không CDN.

**`/report <MÃ>` được bổ sung ba khối**, không đổi cấu trúc hai tầng: dải định giá (tầng
DIỄN GIẢI), đồng thuận CTCK (tầng DIỄN GIẢI), và một dòng trong KẾT LUẬN nếu mã đang nằm
trong sổ — *"đang ở sổ từ 04/09, tư thế tăng, mốc huỷ 22.3"*.

---

## 5. Chuỗi quyết định phải khớp — và code kiểm tra được

Đây là phần mà không CTCK nào kiểm tra tự động, và là lý do các bản báo cáo của họ hay tự
mâu thuẫn. `desk/consistency.py` chạy trước khi xuất bất kỳ sản phẩm nào:

| Kiểm tra | Loại hay cảnh báo |
|---|---|
| Mã trong sổ thuộc ngành đang **UW** | ⚠️ cảnh báo — hợp lệ nếu quan điểm mã nói rõ *vì sao ngược ngành*, nhưng phải nói |
| Quan điểm thị trường `giam` mà tiền mặt < 30% | ⚠️ cảnh báo, in cả hai con số cạnh nhau |
| Mã có **cờ đỏ** nhóm hình sự đang trong sổ | ❌ **loại** — đúng luật `thesis` đã có |
| Quan điểm quá `horizon` chưa tái khẳng định | ❌ tự chuyển `expired`, rơi khỏi sổ |
| Tổng trọng số ≠ 100% (gồm tiền mặt) | ❌ loại |
| Mã trong sổ dưới ngưỡng thanh khoản của `prospect` | ❌ loại, cùng lý lẽ "thanh khoản là cửa vào, không phải điểm" |

Số lượng vi phạm **in ra**, không giấu — đúng luật của `macro/verdict.py`: giấu đi thì bộ
kiểm tra chỉ làm output *trông* sạch.

---

## 6. Hiệu chuẩn — ai được lên tiếng sau khi đo được cái gì

Không module nào ở §3 được phát biểu trước khi qua cửa của nó. Ba nhóm, **khác nhau ở chỗ
có đo được hôm nay hay không** — đây là phần quan trọng nhất của cả tài liệu:

### 6.1 Đo được NGAY (có đủ lịch sử trên đĩa)

| Giả thuyết | Cách đo | Nền so sánh |
|---|---|---|
| **D1** — mua ròng khối ngoại chuẩn hoá dự báo lợi suất vượt trội 5/10/20 phiên | chia 5 nhóm theo `foreign_net_pct`, đo lợi suất tương đối, mẫu **không chồng lấn** | placebo: xáo ngày, giữ nguyên phân phối |
| **D2** — tự doanh mua ròng cũng vậy | như trên | như trên |
| **V1** — P/E dưới phân vị 20 của chính mã cho lợi suất 60 phiên khác nền | phân tầng theo ngành để khỏi đo lại "ngành nào rẻ" | placebo |
| **C1** — báo cáo CTCK có sức dự báo, và **nguồn nào** | event study quanh `date`, tách theo `sourceID` | placebo + §7.4 |

Bonferroni cho số phép kiểm đã chạy, đúng như `macro/calibrate.py`. Kết quả **không đạt
cũng phải in**, và in ở chỗ người dùng thấy — `macro/score.py` đã phải mang
`calibration_note()` theo mọi output vì đúng chuyện này.

### 6.2 Chỉ tích luỹ TIẾN được (không backfill)

- Quan điểm của bàn (`ledger`) — cùng lý do H3: model viết hôm nay **đã biết** thị trường
  tháng 3 đi đâu. `as_of` cắt được dữ liệu vào prompt, **không cắt được trí nhớ của
  model**.
- `estimated-price` của FireAnt — snapshot, chỉ có từ ngày bắt đầu đóng băng.

Cả hai vào `weekly_macro.bat` (đã đăng ký Task Scheduler) ngay từ giai đoạn 0, kể cả khi
chưa có gì đọc chúng. **Ngày không chạy là ngày mất vĩnh viễn.**

### 6.3 Không bao giờ đo được — phải nói ra chứ không lờ đi

Chất lượng *lập luận* trong một quan điểm. `consistency.py` kiểm được câu có khớp bằng
chứng, không kiểm được suy luận có đúng — y hệt giới hạn `macro/verdict.py` đã ghi. Nên
`invalidation` là bắt buộc ở mọi cấp: nó là thứ duy nhất biến một lập luận không kiểm được
thành một phát biểu kiểm được.

---

## 7. Bảy chỗ dễ sai

### 7.1 ⚠️ P/E lịch sử nhảy bậc ở mỗi lần chia cổ tức cổ phiếu — bẫy nặng nhất

`data/` lưu giá **đã điều chỉnh về hệ hôm nay** (`record_from_json` chia giá cho
`adjRatio`, nhân volume lên). BCTC thì **không** điều chỉnh: EPS quý 3/2016 là EPS trên số
cổ phiếu năm 2016. Lấy giá điều chỉnh chia EPS thô là được một chuỗi P/E **nhảy một bậc
đúng mỗi lần doanh nghiệp chia cổ phiếu** — và nó trông hoàn toàn bình thường, giống hệt
một đợt định giá lại của thị trường.

Cách chặn: quy EPS về **cùng hệ** bằng tích luỹ `adjRatio` từ quý đó tới nay, và
`valuation.py` phải **tự kiểm tra**: chuỗi P/E có bước nhảy > 25% trong một phiên mà giá
không nhảy tương ứng → ném cảnh báo, không im lặng trả số. Kiểm chứng chéo miễn phí:
`fundamental.eps` hôm nay phải khớp EPS trượt tự tính của phiên hôm nay.

### 7.2 Ngày công bố BCTC bị dồn cục ở hạn nộp

Đếm thật trong `news/index.db`: mốc `F_2026_2` có ở **80/80** mã, trong đó **60 mã rơi
đúng 30/07/2026** — đó là *hạn nộp*, không phải ngày từng doanh nghiệp thật sự nộp. 20 mã
còn lại rải từ 15/07.

Hướng đúng là hướng **an toàn**: dùng thẳng ngày mốc. Nếu nó là hạn nộp thì nó **muộn hơn
hoặc bằng** ngày công bố thật → kết quả *thận trọng*, không nhìn trước. Cấm đi ngược lại
(suy ra một ngày sớm hơn). Muốn chính xác hơn thì đối chiếu với bài trong `posts` nói về
BCTC quý đó và lấy ngày **sớm hơn** — nhưng chỉ khi bài đó có thật, không suy.

### 7.3 Khối ngoại bán ròng ở mã kín room không phải quan điểm

Mã đã chạm trần sở hữu nước ngoài thì lệnh mua của khối ngoại **không vào được**, nên dòng
ròng âm là cơ chế chứ không phải góc nhìn. Tương tự, các phiên **ETF cơ cấu** (VNM ETF,
FTSE, Fubon) tạo ra mua/bán ròng khổng lồ không mang thông tin về doanh nghiệp.
`flows.py` phải mang cờ `room_capped` và `etf_review_window`, và mọi phép hiệu chuẩn ở
§6.1 phải chạy **cả hai bản** — có và không có các phiên đó. Lệch nhau nhiều thì kết luận
thuộc về bản đã loại.

### 7.4 Ngày báo cáo CTCK ≠ ngày thông tin ra thị trường

Khách hàng tổ chức của CTCK đọc báo cáo **trước** khi nó lên FireAnt. Nên event study ở
§3.4(b) đo một quãng **đã bị dịch**, và sai lệch đi **một chiều**: nó làm báo cáo trông
như *đến sau* một cú chạy giá, tức làm các CTCK trông tệ hơn thực tế.

Phải in kèm mọi bảng điểm nguồn, và đo thêm cửa sổ **−5 phiên** trước ngày báo cáo: nếu
phần lớn mức tăng đã xảy ra trước đó, đó chính là dấu vết của độ trễ công bố, không phải
bằng chứng rằng CTCK viết sau khi giá chạy.

### 7.5 Báo cáo CTCK là tác phẩm có bản quyền của người khác

Lưu và dùng: `reportID`, nguồn, ngày, mã, tiêu đề, và **trích đoạn ngắn có dẫn nguồn**.
Không lưu trữ lại toàn văn để phát hành, không tái xuất bản nội dung trong file HTML gửi
đi. Mọi chữ lấy về đi qua `<untrusted source="...">` như mọi văn bản internet khác trong
repo — kho này còn **nhạy hơn** kho tin thường vì nó là văn bản *được viết để thuyết phục*.

### 7.6 Danh mục mô phỏng phải chịu chi phí, nếu không nó là một trò gian lận lịch sự

Vào lệnh ở **giá đóng cửa phiên SAU** phiên ra quan điểm (không phải giá đóng cửa của
chính phiên đó — lúc viết thì phiên đã chốt rồi), trừ phí + thuế + một mức trượt giá theo
thanh khoản của mã. Bỏ ba khoản này ra thì mọi chiến lược xoay vòng nhanh đều thắng, và nó
thắng bằng số không tồn tại.

### 7.7 Sổ không có cửa ra thì bảng điểm vô nghĩa

Mỗi `Entry` **bắt buộc** có `horizon_sessions`. Hết hạn là rơi khỏi sổ, kể cả khi đang
lãi. Không có luật này thì mọi vị thế thua đều "vẫn đang chờ" và tỷ lệ đúng luôn đẹp —
đúng cơ chế tự lừa mình mà `forecast.py` đã chặn bằng trạng thái `expired`.

---

## 8. ⚠️ Quyết định của người dùng: bàn này có công bố tỷ trọng không

Quy ước đang chạy, ghi trong `CLAUDE.md`: *"output mô tả trạng thái kỹ thuật, không đưa
khuyến nghị mua/bán"*, và `STANCES` cố ý bỏ chữ mua/bán vì *"không giả vờ biết khẩu vị rủi
ro, quy mô vị thế hay khung thời gian của người đọc"*.

Một bàn phân tích kiểu CTCK **đi ngược đúng chỗ đó**: sản phẩm của nó là tỷ trọng. Không
thể có cả hai, nên phải chọn:

| | **A. Giữ nguyên quy ước** | **B. Sổ mô phỏng có tỷ trọng** (đề xuất) |
|---|---|---|
| Đầu ra | tư thế + mốc như hiện nay, thêm bối cảnh trên xuống | thêm **một sổ mô phỏng của bàn**: mã, tỷ trọng, tiền mặt |
| Bảng điểm | chỉ chấm được *hướng* | chấm được cả *phân bổ* — thứ quyết định phần lớn kết quả thật |
| Rủi ro | sản phẩm vẫn không đủ giống một bản báo cáo CTCK | dễ bị đọc thành khuyến nghị đầu tư cho người đọc |
| Cách gỡ rủi ro | — | gọi đúng tên: **"danh mục mô phỏng của bàn"**, có bảng điểm đi kèm, giữ nguyên disclaimer, trọng số do **quy tắc** tính (§3.7) chứ không do model đặt |

**Đề xuất B**, vì đúng một lý do: tỷ trọng là thứ làm quan điểm **sai được**. Một bàn phát
biểu "nghiêng về tăng" 40 lần không bao giờ bị chấm điểm; một bàn giữ 60% cổ phiếu qua một
nhịp giảm 12% thì bị. Và toàn bộ giá trị của §3.1 + §3.7 chỉ tồn tại dưới phương án B.

Nếu chọn A thì §3.7 rút về *"danh sách theo dõi có xếp hạng"* và bảng điểm chỉ còn cột tỷ
lệ đúng của hướng — phần còn lại của phương án giữ nguyên.

---

## 9. Lộ trình

Thứ tự này không theo độ hữu ích thấy ngay, mà theo **cái gì mất vĩnh viễn nếu chưa bắt
đầu**.

| GĐ | Nội dung | Vì sao đứng ở đây | Ước lượng |
|---|---|---|---|
| **0** | `ledger.py` + đóng băng `estimated-price` hằng tuần vào `weekly_macro.bat` | **Không backfill được.** Chưa có gì đọc nó cũng phải chạy | 1 buổi |
| **1** | `flows.py` + hiệu chuẩn D1/D2 | Nguồn duy nhất đo được ngay, 16 năm dữ liệu, không tốn request nào | 2–3 buổi |
| **2** | `valuation.py` + hiệu chuẩn V1 | Mở khoá câu mở đầu của mọi báo cáo công ty; 80 request một lượt | 3–4 buổi |
| **3** | `consensus.py` + hiệu chuẩn C1 | Nguồn hoàn toàn mới (§2.1), và bảng điểm CTCK là sản phẩm không ai có | 3–4 buổi |
| **4** | `calendar.py` + `desk_daily` | Sản phẩm đầu tiên người dùng **thấy** hằng ngày | 2 buổi |
| **5** | `view.py` + `book.py` + `consistency.py` + `desk_strategy` | Cần GĐ1–4 làm bằng chứng đầu vào | 4–5 buổi |
| **6** | `scorecard.py` | Chỉ có ý nghĩa sau khi sổ đã chạy ≥ 3 tháng | 2 buổi |

Test đi kèm từng giai đoạn, theo đúng khuôn 794 test hiện có: fixture tĩnh, không mạng,
không đĩa cho tầng parse; mỗi bẫy ở §7 có **một test mang đúng tên bẫy đó**.

---

## 10. Cái KHÔNG làm, và vì sao

- **Không dự phóng EPS.** Bàn này không có chuyên viên đi gặp doanh nghiệp. Một con số EPS
  2027 do model ngôn ngữ viết ra là đúng thứ "bịa số" mà cả repo được dựng để chặn. Thay
  thế: EPS **trượt** (đo được) + kế hoạch năm doanh nghiệp tự công bố (trích dẫn được) +
  đồng thuận CTCK (của người khác, có tên).
- **Không tự ra giá mục tiêu.** Giá mục tiêu đòi dự phóng. Thay bằng **dải định giá lịch
  sử** + base rate — trả lời được câu *"đắt hay rẻ so với chính nó, và mấy lần trước ở mức
  này thì sao"*, tức phần dùng được của một giá mục tiêu, bỏ phần bịa.
- **Không gộp ba cấp quan điểm thành một điểm số.** Cùng luật "ba điểm xếp hạng không được
  cộng vào nhau".
- **Không lấy trung bình `estimated-price` của FireAnt với đồng thuận CTCK với dải tự
  tính.** Trộn ba nhận định là tạo ra một nhận định không ai đưa ra cả.
- **Không đụng tới diễn đàn / mạng xã hội.** Tier 4 của plan tin tức vẫn đóng.

---

## 11. Nhật ký thi công

### GĐ0 — sổ + đóng băng định giá (19/09/2026)

`src/desk/ledger.py`, `src/desk/estimates.py`, `src/desk/freeze.py`, bước 6 của
`weekly_macro.bat`. Ba chỗ thiết kế bị sửa khi chạm vào code thật:

1. **`Entry` có thêm `confidence`.** §3.7 nói model chọn nấc tin cậy còn quy tắc tính
   trọng số, nhưng bản phác `Entry` lại không có chỗ nào chứa cái nấc đó — nên nó sẽ
   phải nằm trong `note`, tức là không kiểm tra được. Giờ là trường có validator.
2. **Trạng thái là dẫn xuất, không lưu trên đĩa.** `open` / `superseded` / `expired`
   tính lại mỗi lần đọc từ (phiên, hạn, có ai trỏ `supersedes` tới không). Lưu trạng
   thái xuống file là tạo ra một bản sao có thể lệch với sự thật — đúng lý lẽ
   `forecast.evaluate()` đã dùng khi coi file trên đĩa chỉ là cache.
3. **Nhật ký lượt chạy cho `estimates`** — sinh ra từ phát hiện ở §2.2: 27/80 mã tài
   chính không có định giá. Thiếu nhật ký thì cột trống không đọc được.

Lượt đóng băng đầu: 53 mã, 1 ngày. Chuỗi này **chỉ dài ra bằng cách chạy đều**.

### GĐ1 — dòng tiền + hiệu chuẩn D1/D2 (19/09/2026)

`src/desk/flows.py`, `src/desk/calibrate_flows.py`, bước 7 của `weekly_macro.bat`.

**Hai lỗi đo đạc lộ ra ở lượt chạy đầu, và cả hai đều thuộc loại chạy trót lọt:**

1. **Chia nhóm theo giá trị tuyệt đối gộp cả rổ = đo nhầm thứ khác.** Mỗi nhóm khi
   đó có một *thành phần mã* khác nhau (mã mỏng dồn về hai đuôi vì mẫu số nhỏ), nên
   cái tách ra được có thể chỉ là "nhóm này gồm những mã nào". Đã đổi sang chia theo
   **phân vị trong chính mã** (`_percentile_ranks`) — mọi nhóm có cùng thành phần mã,
   và cỡ nhóm về đúng bằng nhau (9.082 / 9.070 / 9.066 / 9.110 / 9.083). Cùng lý lẽ
   "đo giá trị gia tăng thì phải giữ giá cố định" của `newsfeat.h3_proxy`.
2. **Mốc phân vị trùng nhau sinh ra một nhóm rỗng trông như đã đo.** 8–14% số phiên
   có dòng tiền đúng bằng 0, đủ để hai mốc phân vị bằng nhau; lượt đầu của D2 ra
   *nhóm 3 rỗng, nhóm 4 phình lên 9.991 quan sát* và bảng vẫn in ra bình thường với
   một hàng toàn dấu `—`. Giờ mốc trùng bị **gộp**, nhóm rỗng bị bỏ, và số nhóm thật
   được nói ra.

**Kết quả — cả 12 phép kiểm chính đều KHÔNG ĐẠT**, ở cả bản cả rổ lẫn bản đã loại
phiên kín room / tuần ETF:

| | 5 phiên | 10 phiên | 20 phiên |
|---|---|---|---|
| **D1** khối ngoại, nhóm mua ròng mạnh nhất | −0,28% (p 0,03) | −0,42% (p 0,09) | −0,52% (p 0,46) |
| **D1** khối ngoại, nhóm bán ròng mạnh nhất | −0,17% (p 0,55) | −0,29% (p 0,97) | −0,27% (p 0,55) |
| **D2** tự doanh, nhóm mua ròng mạnh nhất | −0,27% (p 0,32) | −0,40% (p 0,66) | −0,68% (p 0,62) |

(trung vị lợi suất tương đối so với VNINDEX; nền placebo −0,20% / −0,28% / −0,38%;
ngưỡng Bonferroni 0,00417.)

Ba điều đáng ghi lại, và phải ghi **đúng mức**:

- **Đây là kết quả âm tính thật, không phải phép đo chưa chạy được.** 16 năm dữ liệu,
  45.411 quan sát độc lập ở cửa sổ 5 phiên. Nên `calibration_note()` nói thẳng: dòng
  tiền ở tầng này là **mô tả trạng thái**, không phải tín hiệu dự báo — và đó là kết
  luận của dữ liệu.
- **Dấu đi ngược câu chuyện phổ biến.** Nhóm khối ngoại mua ròng mạnh nhất có trung vị
  **thấp hơn nền** ở cả ba cửa sổ. Không đủ ý nghĩa để phát biểu, nhưng đủ để nói rằng
  "khối ngoại mua ròng nên mã sẽ tăng" không có chỗ dựa trong chính dữ liệu này.
- **Nhóm *giữa* (dòng tiền gần bằng 0) đẹp đều đặn ở cả sáu giả thuyết**, và ở D2-5p
  thì p nhỏ hơn cả ngưỡng Bonferroni. Đây **không** được tính là phát hiện: giả thuyết
  đăng ký trước chỉ nói về hai đuôi, nên `_postscript()` tự bắt và dán nhãn *quan sát
  hậu nghiệm*. Muốn dùng thì phải đăng ký thành giả thuyết riêng rồi kiểm trên một
  quãng thời gian khác.

**Hệ quả cho các giai đoạn sau:** dòng tiền vẫn nằm trong bản tin phiên (GĐ4) như một
**số đo người đọc muốn thấy**, nhưng nó **không được vào công thức điểm nào**, và
`view.py` (GĐ5) không được dùng nó làm lý do chính cho một quan điểm. Trần điểm ở đây
là hệ quả của file hiệu chuẩn, giống hệt quan hệ giữa `macro/calibrate.py` và
`macro/score.py`.

### GĐ2 — dải định giá lịch sử (20/09/2026)

`src/desk/financials.py` + `valuation.py` + `calibrate_valuation.py`. Nạp BCTC quý
cho **80/80 mã trong 249 giây** (2 request/mã, 40 kỳ mỗi lượt) — đúng như §2.3 đã
ước lượng.

Câu mà repo trước đây không phát biểu được, giờ phát biểu được, ví dụ phiên
18/09/2026: *HPG P/E 7,13 — phân vị 26 trong 5 năm của chính mã, thấp hơn trung vị
5 năm 48%; P/B 1,17 — phân vị 13*. EPS tự tính đối chiếu với EPS FireAnt công bố
lệch 0,05% (VCB), 0,6% (FPT), 10% (HPG).

**Ba chỗ đọc số phải sửa sau khi chạm dữ liệu thật:**

1. **Ngân hàng dùng mẫu KQKD khác hẳn.** HPG có 21 dòng, kết ở *"Lợi nhuận sau
   thuế của cổ đông của công ty mẹ"* (id 21); VCB có 23 dòng và **không có** dòng
   đó. Khớp theo id là im lặng lấy nhầm dòng cho cả nhóm ngân hàng — 27/80 mã.
2. **Vốn chủ sở hữu của ngân hàng tên là "Vốn và các quỹ".** Thiếu mẫu này thì P/B
   trống cho đúng nhóm mà P/B là thước đo *chính*.
3. **Số cổ phiếu phải suy từ vốn góp ÷ 10.000đ**, và thứ tự ưu tiên tên dòng quan
   trọng: SSI có cả "vốn góp của chủ sở hữu" (2,503 tỷ cp — đúng) lẫn "vốn đầu tư
   của chủ sở hữu" (3,04 tỷ — đã gồm thặng dư, sai).

**Kết quả hiệu chuẩn V1/V2 — 1/8 phép kiểm đạt:**

| | 60 phiên | 120 phiên |
|---|---|---|
| **V1** P/E, nhóm rẻ nhất | +0,70 pp (p 0,29) | +1,66 pp (p 0,52) |
| **V2** P/B, nhóm rẻ nhất | +1,02 pp (p 0,11) | +2,13 pp (p 0,38) |
| **V2** P/B, nhóm **đắt** nhất | −0,57 pp (p 0,34) | **−5,22 pp (p 0,002) ✅** |

Đọc đúng mức: **rẻ so với chính mình không dẫn được gì** ở cả bốn phép kiểm của
đuôi rẻ. Thứ sống sót là đuôi *đắt* của P/B ở 120 phiên — đắt so với chính mình
thì thua nền 5,2 điểm phần trăm, qua ngưỡng Bonferroni 0,00625. Một kết quả trên
tám, và nó nằm ở đuôi mà người ta ít dùng để mua.

**Hai lỗi đo đạc lộ ra ngay trong lượt chạy:**

- **Chiều của giả thuyết bị dùng chung với dòng tiền.** Quy tắc "đạt" đang là
  *nhóm cao nhất vượt nền*, đúng cho dòng tiền và **ngược** cho định giá. Lượt đầu
  báo V2-120p "không đạt" trong khi nó đạt. Nay `expect` là tham số đăng ký trước.
- **p nằm sát sàn phân giải của phép hoán vị.** Với 400 lần rút, p nhỏ nhất khác 0
  là 0,0025, nên một p = 0,005 chỉ dựng từ hai lần rút. Tăng lên 2.000 lần rút cho
  tầng định giá (nhóm ở đây vài trăm quan sát nên phép hoán vị rẻ), và
  `evaluate_buckets` nay tự cảnh báo khi p chạm sàn.

### GĐ3 — đồng thuận CTCK (20/09/2026)

`src/desk/consensus.py`. Nạp **756 báo cáo** trong cửa sổ 23/05→20/09/2026 (danh
mục *Phân tích công ty*) trong 56 giây, kèm 40 tóm tắt; 716 tóm tắt còn thiếu vì
ngân sách request, và con số đó **được in ra** thay vì để lượt chạy trông như đã
đủ.

**Bộ lọc từ khuyến nghị phải qua ba cửa** — và lý do là một phép đo, không phải
cẩn thận thừa: bản *"FPT - MUA: Chủ động thích nghi"* bị đọc thành **BÁN**, vì tóm
tắt có cụm "doanh thu **bán hàng**". Cùng họ với luật cờ đỏ (`"an tu"` nằm trong
*"cổ phần từ"*), nhưng nặng hơn: ở đây chính từ khuyến nghị **là** một từ thường
dùng, nên đệm khoảng trắng hai đầu không cứu được. Ba cửa: từ không nhập nhằng
(`khả quan`, `trung lập`, `nắm giữ`…) đi thẳng; từ một âm tiết phải **viết hoa
trong tiêu đề** hoặc nằm trong câu có cụm báo hiệu hẹp; và mọi đường đều qua kiểm
phủ định — *"kinh doanh không khả quan"* không phải khuyến nghị KHẢ QUAN. Hai cụm
đã phải bỏ khỏi danh sách báo hiệu vì chúng là từ thường: `duy trì` và `đánh giá`
(*"nhu cầu trang sức duy trì tích cực"*).

Sau khi siết: **46/707** bản mang từ khuyến nghị (MUA 41, KHẢ QUAN 4, BÁN 1).
Trước khi siết là 58, trong đó có cả nhãn ngược dấu. Giá mục tiêu vẫn **không lấy
được** — nó nằm trong thân PDF và API không có đường tải file, nên bàn này không
dựng bảng giá mục tiêu đồng thuận.

### GĐ4 — lịch xúc tác (20/09/2026)

`src/desk/calendar.py`. Gộp năm nguồn đã có thành một dòng thời gian phía trước,
tách `certain` khỏi ước lượng. Hai phát hiện ở tầng dưới:

- **Kho mốc sự kiện bị cắt ở hôm nay.** `news/ingest.py` gọi `timescale-marks` với
  `end = hôm nay`, nên kho **không bao giờ** có nổi một mốc phía trước và phần
  ngày giao dịch không hưởng quyền của lịch luôn trống — mà không có gì báo. Nay
  `MARKS_FORWARD_DAYS = 120`.
- **`next_release` của FireAnt là trường chết.** Đếm cả kho: 31/96 chỉ số có giá
  trị, và mốc **xa nhất trong toàn kho là 2023-12-31**. Nên lịch vĩ mô nói thẳng
  là *nguồn không cho biết*, không phải *kỳ này không có gì công bố* — cùng họ với
  `macro_posts.sentiment`.

### GĐ5 + GĐ6 — sổ, kiểm tra chéo, bảng điểm (20/09/2026)

`book.py` + `consistency.py` + `view.py` + `scorecard.py` + `products.py`.

`Entry` được thêm **ba trường số tuỳ chọn** (`trigger_level`,
`invalidation_level`, `target_level`): câu chữ vẫn là bắt buộc vì mốc phải đọc
được ("đóng cửa > 24.8 **với volume ≥ 1,5× TB20**" không nhét vào một con số
được), nhưng bảng điểm thì cần số để replay. Số là **thêm vào**, không thay thế —
không có số thì vẫn đo được lợi suất tương đối, chỉ không replay được mốc huỷ.

Chạy thử đầy đủ trên sổ tạm: 3 quan điểm → sổ mô phỏng → kiểm tra chéo → bảng
điểm có nền placebo và cột sau chi phí. Sổ thật vẫn **trống** — và đó là đúng:
bàn chưa viết quan điểm nào, nên mọi sản phẩm nói thẳng "chưa có ai viết" thay vì
dựng một câu trung tính.

### Nhịp chạy

`weekly_macro.bat` nay 10 bước, và **đã đăng ký với Task Scheduler ngày
20/09/2026** (07:00 Chủ nhật, lần chạy tới 27/09) — trước đó nó chưa từng được
đăng ký trên máy này, nên bước 6 (đóng băng định giá, không backfill được) lẽ ra
đã mất mỗi tuần.
