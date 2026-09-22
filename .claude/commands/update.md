---
description: Tải giá mới nhất từ FireAnt về data/ và nạp tin tức về news/index.db (mặc định tháng hiện tại)
argument-hint: "[vn30|all|MÃ1,MÃ2] [latest|recent|quarter|full] [no-news|only-news]"
allowed-tools: mcp__vn-ta__update_prices_tool, mcp__vn-ta__update_news, mcp__vn-ta__list_symbols
---

Cập nhật dữ liệu: `$ARGUMENTS`

Cách đọc tham số (bỏ trống thì dùng mặc định) — **một bộ tham số dùng chung cho cả hai bước**:

- Phần không phải tên mode là `universe` — mặc định `disk` (mọi mã đang có dữ liệu).
- Từ nào thuộc `latest` / `recent` / `quarter` / `full` là `mode` — mặc định `latest`.
- `no-news` / `chỉ giá` = bỏ bước 2. `chỉ tin` / `only-news` = bỏ bước 1.

Nghĩa là `/update` nạp giá **và** tin cho cả rổ; `/update FPT` nạp giá và tin của riêng FPT;
`/update vn30 recent` truyền cùng `universe="vn30"`, `mode="recent"` xuống cả hai bước.

## Bước 1 — giá

Gọi `mcp__vn-ta__update_prices_tool` với `universe` và `mode` vừa đọc được.

**Chỉ dùng `full` khi người dùng nói rõ** — nó tải lại toàn bộ lịch sử từ 2010 cho từng mã,
mất rất nhiều thời gian và request. Nếu tham số có `full` mà bạn thấy có vẻ nhầm,
hỏi lại trước khi chạy.

In nguyên kết quả. Chú ý mục "⚠️ mã còn thiếu dữ liệu" nếu có.

## Bước 2 — tin tức

Gọi `mcp__vn-ta__update_news` với **đúng** `universe` và `mode` đó.

**Chạy sau bước 1, không chạy trước.** Trạng thái "tin đã vào giá chưa" trong `news_digest`
đo bằng chính các phiên vừa nạp ở bước 1; nạp tin trên chuỗi giá cũ thì các phiên sát hôm nay
hiện `chưa đủ phiên` một cách giả tạo.

Mode ở đây nói *lùi bao xa*, không nói *nạp lại bao nhiêu*: mốc lùi luôn **nối tiếp chỗ kho
đang dừng**, nên `latest` vẫn lấp kín cả quãng bỏ bê nếu lâu ngày không chạy. `full` là ~30
request cho **mỗi** mã — chỉ dùng khi dựng kho lần đầu cho một mã mới, đừng chạy cho cả rổ
nếu người dùng không nói rõ.

**Bước này chậm hơn bước 1 một bậc** và đó là bản chất chứ không phải lỗi: FireAnt giữ nhịp
1,2 giây/request, mà nạp tin là 2 request cố định + 1–5 trang bài cho **mỗi** mã. Cả rổ ở
`latest` là ~5–10 phút, một mã là vài giây. Nếu người dùng chỉ muốn giá nhanh như trước thì
`/update no-news` (~15s) — nói cho họ biết lựa chọn đó khi họ có vẻ đang vội.

In nguyên kết quả. Hai con số trong đó khác nhau và đừng gộp lại khi tóm tắt: **bài mới** là
phần kho chưa từng có, **số dòng ghi** lớn hơn vì lượt nạp cố ý chồng lấn vài ngày với lần
trước. Nếu có mục "⚠️ mã còn bài chưa nạp" thì nhắc lại nguyên văn — nó nghĩa là lượt nạp bị
cắt cụt, chạy lại đúng mấy mã đó với `mode="quarter"`.

## Sau khi chạy

Nếu có mã cập nhật được phiên mới, nhắc người dùng rằng `/watch` và `/scan` giờ đã thấy dữ
liệu mới (cache đã xoá, không cần khởi động lại), và `/news <MÃ>` / `/report <MÃ>` đã đọc
được tin của phiên vừa nạp.

Nếu lỗi thiếu token, chỉ rõ cần đặt `FIREANT_BEARER_TOKEN` hoặc ghi vào `access_token.txt`
— đừng tự đi tìm hay tạo token. Cùng một token dùng cho cả hai bước, nên bước 1 chạy được
mà bước 2 báo thiếu token là chuyện khác, hãy in nguyên lỗi.
