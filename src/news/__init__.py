"""Tầng tin tức và sự kiện doanh nghiệp.

``src/ta/`` trả lời "biểu đồ đang nói gì". Tầng này trả lời "ngoài biểu đồ còn
chuyện gì đang xảy ra", và câu hỏi thật sự khó: *chuyện đó đã vào giá chưa.*

Thiết kế đầy đủ ở ``documents/plan_news_pipeline.md``. Hai điều cần biết trước
khi sửa bất cứ file nào ở đây:

* **Bằng chứng, không phán quyết.** Module ở đây trả sự kiện + số liệu + trích
  dẫn nguồn. Việc "tin này tốt hay xấu" là của tầng trên và của người đọc.
* **Enum phải có nguồn.** Không suy nghĩa của field từ tên nó, cũng không suy
  chiều mua/bán từ phản ứng giá (đó là thứ event study đang *đo*). Đặc tả
  FireAnt ở ``/swagger/docs/v1`` là nguồn sự thật; giá trị nào phải suy gián
  tiếp thì mang theo ``direction_source``.
"""
