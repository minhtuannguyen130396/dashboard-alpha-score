---
description: Bảng ngành — ngành nào đang mạnh, ngành nào đang yếu, tách thành 5 cột
---

Gọi `sector_board` với `$ARGUMENTS` (nếu người dùng nêu số lượng thì truyền `top`).

Sau khi in bảng, **luôn** nhắc hai điều — chúng không phải chú thích lịch sự, chúng
quyết định người đọc được phép làm gì với thứ tự trong bảng:

1. **Đây là mô tả hiện trạng, không phải dự báo.** Hiệu chuẩn đã chạy và không chứng
   minh được sức dự báo của trụ nào. Khối ghi chú ở đầu bảng nói điều đó — đừng bỏ.
2. **Chỉ số ngành chạy theo toàn bộ mã niêm yết của ngành**, không phải rổ 80 mã.
   Ngành mạnh với độ phủ thấp nghĩa là phần lớn sức mạnh nằm ở mã người dùng không có.

Khi một ngành đáng chú ý, gợi ý bước tiếp:

- `sector_detail <tên ngành>` — hồ sơ đầy đủ một ngành
- `sector_members <tên ngành>` — mã nào của ngành có trong rổ
- `sector_evidence` → bạn đọc → `sector_submit` — thêm phần tin và nhận định

Nếu bảng trống hoặc rất cũ, bảo người dùng chạy `update_macro` trước.
