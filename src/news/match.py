"""Ghép bài viết với giao dịch nội bộ để lấy **ngày công bố thật**.

Đây là mảnh vá cho lỗ hổng lớn nhất của tầng đo. ``holder-transactions`` cho biết
*ai giao dịch, chiều nào, bao nhiêu* nhưng **không cho biết ngày tin ra thị
trường** — nó chỉ có ``startDate`` (ngày bắt đầu được phép giao dịch). Mà thị
trường phản ứng lúc **công bố**, không phải lúc cửa sổ giao dịch mở.

Quan sát trên HPG cho thấy khoảng lệch là thật và đáng kể:

    Nguyễn Ngọc Quang bán 6.600.000   startDate 11/06/2026, công bố 05/06/2026  (6 ngày)
    Trần Vũ Minh      mua 50.000.000  startDate 12/03/2026, công bố 09/03/2026  (3 ngày)

Neo cửa sổ sự kiện vào ``startDate`` nghĩa là đặt phản ứng thật vào vùng ``t-5…t-1``
và gọi nó là "rò rỉ trước tin". Đó không phải rò rỉ — đó là **chính cái tin**, bị đo
lệch chỗ.

Ghép bằng hai bằng chứng độc lập, và cố ý đòi **ít nhất một** cái chắc:

* **Tên người** — tiêu đề CBTT gần như luôn nêu đích danh
  ("...của người nội bộ Nguyễn Ngọc Quang").
* **Khối lượng** — báo chí thường không nêu tên mà nêu số
  ("Thành viên HĐQT Hòa Phát muốn bán 6,6 triệu cổ phiếu").

Không cái nào một mình đủ tin cho mọi ca, nên hàm ghép trả về **điểm và lý do**,
không phải một cặp im lặng. Cặp ghép sai làm hỏng ``t0``, mà ``t0`` sai thì toàn bộ
event study sai theo một hướng khó phát hiện — nên thà bỏ sót còn hơn ghép bừa.
"""
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

from src.news.posts import KIND_ANNOUNCE, KIND_RESULT

#: Cửa sổ tìm bài công bố quanh ``startDate``.
#: Lùi 45 ngày vì công bố có thể đi trước khá xa; tiến 3 ngày để chừa ca báo đăng
#: trễ một hai hôm so với ngày cửa sổ giao dịch mở.
LOOKBACK_DAYS = 45
LOOKAHEAD_DAYS = 3

#: Điểm tối thiểu để chấp nhận một cặp ghép. Dưới ngưỡng thì **không ghép**, và
#: giao dịch đó giữ nguyên ``startDate`` làm mốc thay thế.
MIN_SCORE = 2

W_NAME = 2          # tên người khớp
W_VOLUME = 2        # khối lượng khớp
W_KIND = 1          # đúng loại (thông báo, không phải báo cáo kết quả)
W_DISCLOSURE = 1    # là CBTT đăng lại, không phải bài báo diễn giải


def _strip_accents(text: str) -> str:
    out = unicodedata.normalize("NFD", text or "")
    out = "".join(c for c in out if unicodedata.category(c) != "Mn")
    return out.replace("đ", "d").replace("Đ", "D").lower()


def volume_variants(volume: Optional[float]) -> List[str]:
    """Các cách một khối lượng có thể được viết trong tiêu đề tiếng Việt.

    ``6600000`` xuất hiện dưới dạng "6,6 triệu" (dấu phẩy thập phân), "6.600.000"
    (dấu chấm phân nhóm) hoặc "6600000". Sinh đủ các biến thể rồi tìm chuỗi con,
    thay vì cố parse số từ tiêu đề — parse thì gặp "6,6 triệu cổ phiếu HPG giữa
    lúc thị giá về đáy" là gãy.
    """
    if not volume or volume <= 0:
        return []
    v = int(volume)
    out = {str(v), f"{v:,}".replace(",", ".")}
    if v >= 1_000_000:
        millions = v / 1_000_000
        if abs(millions - round(millions)) < 1e-9:
            out.add(f"{int(round(millions))} trieu")
        else:
            # 6.6 -> "6,6 trieu"; chỉ giữ 1 chữ số thập phân như cách báo viết
            out.add(f"{millions:.1f}".replace(".", ",") + " trieu")
    if v >= 1_000:
        thousands = v / 1_000
        if abs(thousands - round(thousands)) < 1e-9 and v < 1_000_000:
            out.add(f"{int(round(thousands))} nghin")
    return sorted(out)


#: Các cụm chỉ *hình thức pháp lý*, không phải danh tính. Bỏ đi thì còn lại phần
#: thật sự phân biệt được tổ chức này với tổ chức khác.
_LEGAL_FORMS = re.compile(
    r"\b(cong ty|cty|ctcp|tnhh|mtv|co phan|tap doan|tong cong ty|"
    r"quy dau tu|quy|dau tu|chung khoan|pte|ltd|limited|inc|corp|"
    r"fund|trust|investment|capital|holdings?|group|co\.|jsc)\b", re.I)

#: Từ viết tắt quá ngắn hoặc quá phổ thông thì không dùng làm khoá khớp.
_GENERIC_ACRONYMS = {"mtv", "tnhh", "ctcp", "pte", "ltd", "jsc", "inc", "llc", "vn"}


def name_variants(name: str) -> List[str]:
    """Các khoá có thể dùng để nhận ra chủ thể này trong một tiêu đề.

    Người thì dễ: tiêu đề nêu nguyên tên. Tổ chức thì không — bản ghi ghi
    *"Công ty TNHH MTV Đầu tư SCIC"* trong khi báo viết *"Thành viên SCIC không
    mua hết lượng cổ phiếu FPT đã đăng ký"*. So nguyên chuỗi là trượt sạch nhóm
    tổ chức, mà nhóm đó chiếm phần đáng kể các giao dịch cổ đông lớn.

    Nên ngoài tên đầy đủ, còn lấy **phần phân biệt được**: bỏ các cụm chỉ hình
    thức pháp lý ("Công ty TNHH MTV Đầu tư", "PTE.Ltd", "Fund") rồi giữ phần lõi,
    cộng thêm các từ viết tắt in hoa (SCIC, PYN) nếu có.
    """
    if not name:
        return []
    full = _strip_accents(name).strip()
    out = {full} if len(full) >= 6 else set()

    # Viết tắt in hoa lấy từ bản gốc (trước khi hạ chữ thường)
    for tok in re.findall(r"\b[A-Z]{3,}\b", name):
        low = tok.lower()
        if low not in _GENERIC_ACRONYMS:
            out.add(low)

    core = _LEGAL_FORMS.sub(" ", full)
    core = re.sub(r"[^a-z0-9\s]", " ", core)
    core = re.sub(r"\s+", " ", core).strip()
    if len(core) >= 4 and core != full:
        out.add(core)
    return sorted(out)


def name_matches(name: str, text: str) -> bool:
    """Chủ thể có được nhận ra trong đoạn văn bản không.

    So sau khi bỏ dấu, vì tiêu đề báo hay viết thiếu dấu hoặc khác kiểu hoa
    thường.
    """
    if not name or not text:
        return False
    hay = _strip_accents(text)
    return any(v in hay for v in name_variants(name))


def volume_matches(volume: Optional[float], text: str) -> bool:
    if not text:
        return False
    hay = _strip_accents(text)
    return any(v in hay for v in volume_variants(volume))


@dataclass
class Match:
    """Một cặp giao dịch ↔ bài viết, kèm điểm và lý do để người đọc bác được."""
    transaction_id: int
    post_id: int
    post_date: str
    post_title: str
    score: int
    reasons: List[str] = field(default_factory=list)
    days_before_start: Optional[int] = None
    kind: str = KIND_ANNOUNCE   # thông báo trước hay báo cáo kết quả

    def to_dict(self) -> Dict[str, Any]:
        return {
            "transaction_id": self.transaction_id, "post_id": self.post_id,
            "post_date": self.post_date, "post_title": self.post_title,
            "score": self.score, "reasons": self.reasons,
            "days_before_start": self.days_before_start,
            "kind": self.kind,
        }


def _parse_day(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d")
    except ValueError:
        return None


def score_pair(tx: Dict[str, Any], post: Dict[str, Any],
               want_kind: str = KIND_ANNOUNCE) -> tuple:
    """Chấm điểm một cặp. Trả ``(điểm, lý do)``."""
    reasons: List[str] = []
    score = 0
    text = f"{post.get('title') or ''} {post.get('description') or ''}"

    if name_matches(tx.get("name") or "", text):
        score += W_NAME
        reasons.append("tên người khớp")
    if volume_matches(tx.get("registered_volume") or tx.get("execution_volume"), text):
        score += W_VOLUME
        reasons.append("khối lượng khớp")
    if post.get("disclosure_kind") == want_kind:
        score += W_KIND
        reasons.append("đúng loại công bố")
    if post.get("is_disclosure"):
        score += W_DISCLOSURE
        reasons.append("bản CBTT đăng lại")
    return score, reasons


def is_credible(post: Dict[str, Any], reasons: Sequence[str]) -> bool:
    """Cặp này có đủ tin để ghép không, khi tập ứng viên là **toàn bộ** bài viết.

    Đây là chỗ dễ sai nhất của cả module. Bản đầu chỉ đưa vào tập ứng viên những
    bài đã được ``disclosure_kind`` gắn nhãn — tức dùng luật từ khoá làm **cổng**.
    Hệ quả: tiêu đề *"Lão tướng FPT Bùi Quang Ngọc bán xong 2 triệu cổ phiếu"* bị
    loại ngay từ vòng gắn nhãn (không có từ chỉ chức vụ nào), dù nó nêu **đúng
    tên** và **đúng khối lượng** của giao dịch đang cần ghép.

    Sửa đúng là hạ ``disclosure_kind`` xuống thành *điểm cộng* và mở tập ứng viên
    ra toàn bộ. Nhưng mở tập ra thì phải siết bằng chứng, vì tập lớn hơn ~100 lần:

    * **Tên người khớp thì nhận.** Một bài chứa "Bùi Quang Ngọc" gần như chắc
      chắn nói về người đó.
    * **Chỉ khối lượng khớp thì chưa.** Chuỗi "2 triệu" xuất hiện đầy trong tin
      thị trường thường ngày; nó chỉ đủ tin khi bài đã được nhận là tin giao dịch
      nội bộ.
    """
    has_name = "tên người khớp" in reasons
    has_volume = "khối lượng khớp" in reasons
    if has_name:
        return True
    return has_volume and bool(post.get("disclosure_kind"))


def _best_in_window(tx: Dict[str, Any], posts: Sequence[Dict[str, Any]],
                    start: datetime, lo_days: int, hi_days: int,
                    want_kind: str, min_score: int) -> Optional[Match]:
    lo = start - timedelta(days=lo_days)
    hi = start + timedelta(days=hi_days)
    best: Optional[Match] = None
    for post in posts:
        when = _parse_day(post.get("date"))
        if when is None or not (lo <= when <= hi):
            continue
        score, reasons = score_pair(tx, post, want_kind=want_kind)
        if score < min_score or not is_credible(post, reasons):
            continue
        cand = Match(
            transaction_id=tx["transaction_id"], post_id=post["post_id"],
            post_date=str(post.get("date"))[:10],
            post_title=post.get("title") or "", score=score, reasons=reasons,
            days_before_start=(start - when).days,
            kind=want_kind,
        )
        if best is None or (cand.score, -_day_key(cand)) > (best.score, -_day_key(best)):
            best = cand
    return best


def find_announcement(tx: Dict[str, Any], posts: Sequence[Dict[str, Any]],
                      lookback: int = LOOKBACK_DAYS,
                      lookahead: int = LOOKAHEAD_DAYS,
                      min_score: int = MIN_SCORE,
                      allow_result_fallback: bool = True) -> Optional[Match]:
    """Bài công bố khớp nhất cho một giao dịch, hoặc ``None`` nếu không đủ tin.

    Khi hai bài cùng điểm, chọn bài **sớm hơn**: cùng một tin thường ra CBTT
    trước rồi báo chí viết lại sau, và ngày thị trường biết là ngày đầu tiên.

    ``allow_result_fallback`` mở một lượt tìm thứ hai cho **báo cáo kết quả** khi
    không có thông báo trước. Cần thiết vì một phần đáng kể bản ghi có
    ``registeredVolume = None`` — thời chưa bắt buộc đăng ký trước, nên **chưa
    từng có** thông báo để mà tìm, và bản tin kết quả là lần đầu thị trường biết.
    Hai loại này được đánh dấu khác nhau ở ``Match.kind`` vì chúng đo **hai sự
    kiện khác nhau**: một cái là *ý định*, một cái là *xác nhận đã xong*.
    """
    start = _parse_day(tx.get("start_date")) or _parse_day(tx.get("execution_date"))
    if start is None:
        return None

    hit = _best_in_window(tx, posts, start, lookback, lookahead,
                          KIND_ANNOUNCE, min_score)
    if hit is not None or not allow_result_fallback:
        return hit
    # Lượt hai: bản tin kết quả, cửa sổ dời về sau vì nó ra sau khi giao dịch xong.
    return _best_in_window(tx, posts, start, 10, 60, KIND_RESULT, min_score)


def _day_key(m: Match) -> int:
    d = _parse_day(m.post_date)
    return int(d.timestamp() // 86400) if d else 0


def match_symbol(transactions: Sequence[Dict[str, Any]],
                 posts: Sequence[Dict[str, Any]],
                 min_score: int = MIN_SCORE) -> Dict[int, Match]:
    """Ghép toàn bộ giao dịch của một mã. Trả ``{transaction_id: Match}``."""
    out: Dict[int, Match] = {}
    for tx in transactions:
        m = find_announcement(tx, posts, min_score=min_score)
        if m is not None:
            out[tx["transaction_id"]] = m
    return out


def effective_t0(tx: Dict[str, Any], match: Optional[Match]) -> tuple:
    """``(mốc dùng cho event study, nguồn của mốc)``.

    Có bài công bố khớp thì dùng ngày bài; không thì lùi về ``startDate`` và
    **nói rõ đó là mốc thay thế** — người đọc phải phân biệt được con số nào
    đứng trên ngày thật và con số nào đứng trên phỏng đoán.
    """
    if match is not None:
        # Phân biệt hai nguồn: ngày thông báo là mốc thị trường biết *ý định*;
        # ngày báo cáo kết quả là mốc biết *đã xong*. Gộp nhãn là mất phân biệt.
        src = "post_date" if match.kind == KIND_ANNOUNCE else "post_result_date"
        return match.post_date, src
    return (str(tx.get("start_date") or tx.get("execution_date") or "")[:10],
            "start_date_proxy")
