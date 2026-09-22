"""Render markdown cho tầng tin tức — mọi câu chữ tiếng Việt tập trung ở đây.

Cùng vai trò với ``src/ta/format.py``: data structure giữ nguyên chất, câu chữ
nằm một chỗ, nên sửa một câu là terminal lẫn file HTML đổi theo.

Giọng văn theo đúng quy ước của repo: **mô tả trạng thái, không khuyến nghị**.
"CAR 5 phiên trước tin +6,1% trong khi thị trường +0,8%" là mô tả. "Nên mua" thì
không bao giờ xuất hiện ở đây.
"""
from typing import Dict, List, Optional, Sequence

from src.news.digest import (BIG_MOVE, GROUP_ORDER, GROUP_VN, NewsDigest,
                             SessionNews, STATUS_NOTE, STATUS_VN,
                             ST_NOT_MEASURED, ST_NO_SESSION)
from src.news.models import DIRECTION_VN, PURCHASED, SOLD
from src.news.reaction import Reaction

DISCLAIMER = ("_Số liệu kỹ thuật và thống kê, không phải khuyến nghị đầu tư._")


def _pct(value: Optional[float], digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{value * 100:+.{digits}f}%"


def _vol(value: Optional[float]) -> str:
    if value is None:
        return "—"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f} triệu"
    if value >= 1_000:
        return f"{value / 1_000:.0f} nghìn"
    return f"{value:.0f}"


# --- Giao dịch nội bộ / cổ đông lớn --------------------------------------

def format_execution_rate(registered: Optional[float],
                          executed: Optional[float]) -> str:
    """Diễn giải tỷ lệ thực hiện — và nói rõ khi *không đo được*.

    ``registered is None`` không phải là 0%. Đó là bản ghi từ thời quy định chưa
    bắt buộc đăng ký trước, nên không có gì để so. In "—" thay vì "0%" là khác
    biệt giữa mô tả trung thực và một tín hiệu bịa ra từ khoảng trống.
    """
    if not registered:
        return "không có đăng ký để đối chiếu"
    if executed is None:
        return "chưa có kết quả"
    rate = executed / registered
    if rate <= 0:
        return "0% — đăng ký rồi không thực hiện"
    if rate >= 0.99:
        return "100% — thực hiện đủ như đăng ký"
    return f"{rate * 100:.0f}% — thực hiện một phần"


def format_transaction(row: Dict) -> str:
    """Một dòng cho một giao dịch."""
    direction = DIRECTION_VN.get(row["direction"], "?")
    who = row["name"]
    role = row.get("position") or "cổ đông lớn"
    reg, ex = row.get("registered_volume"), row.get("execution_volume")
    when = str(row.get("start_date") or row.get("execution_date") or "")[:10]
    return (f"- **{when}** · {who} ({role}) — **{direction}** "
            f"đăng ký {_vol(reg)}, thực hiện {_vol(ex)} "
            f"→ {format_execution_rate(reg, ex)}")


def format_transactions(rows: Sequence[Dict], symbol: str,
                        limit: int = 10) -> str:
    if not rows:
        return f"## {symbol} — giao dịch nội bộ / cổ đông lớn\n\nKhông có bản ghi nào."
    insiders = [r for r in rows if r.get("position")]
    lines = [f"## {symbol} — giao dịch nội bộ / cổ đông lớn",
             "",
             f"{len(rows)} bản ghi, trong đó **{len(insiders)}** là người nội bộ "
             f"(có chức vụ), còn lại là cổ đông lớn.",
             ""]
    lines += [format_transaction(r) for r in rows[:limit]]
    if len(rows) > limit:
        lines.append(f"\n_… còn {len(rows) - limit} bản ghi nữa._")
    return "\n".join(lines)


# --- Phản ứng giá ---------------------------------------------------------

def _read_pattern(r: Reaction) -> str:
    """Câu đọc mẫu hình — mô tả *chỗ biến động nằm ở đâu*, không phán quyết.

    Ba cửa sổ cố ý được so với nhau chứ không cộng lại: một mã chạy hết trước
    ngày công bố rồi đi ngang trông y hệt một mã không phản ứng gì, nếu chỉ nhìn
    tổng.
    """
    pre, imm, post = r.car_pre, r.car_immediate, r.car_post
    if pre is None and imm is None:
        return "Chưa đủ dữ liệu để đọc mẫu hình."
    parts: List[str] = []
    big = BIG_MOVE  # 3% abnormal — đủ lớn để đáng nói với cửa sổ vài phiên
    if pre is not None and abs(pre) >= big:
        parts.append(f"phần lớn biến động xảy ra **trước** ngày sự kiện "
                     f"(CAR trước {_pct(pre)})")
    if imm is not None and abs(imm) >= big:
        parts.append(f"phản ứng **tức thì** rõ ({_pct(imm)} trong 2 phiên đầu)")
    if post is not None and abs(post) >= big:
        parts.append(f"còn **trôi tiếp** sau sự kiện ({_pct(post)} trong 10 phiên)")
    if not parts:
        return ("Không cửa sổ nào vượt ngưỡng đáng kể — giá đi gần đúng như quan hệ "
                "thường ngày với thị trường.")
    return "Đọc: " + "; ".join(parts) + "."


def format_reaction(r: Reaction, title: str = "") -> str:
    head = title or f"{r.symbol} — phản ứng giá quanh {r.t0_requested}"
    lines = [f"### {head}", ""]

    if r.t0_actual and r.t0_actual != str(r.t0_requested)[:10]:
        lines.append(f"> Mốc yêu cầu **{str(r.t0_requested)[:10]}**, phiên thật gần "
                     f"nhất là **{r.t0_actual}** (mốc rơi vào ngày nghỉ).")
        lines.append("")

    if r.note and r.alpha is None:
        lines += [f"⚠️ {r.note}", "", DISCLAIMER]
        return "\n".join(lines)

    lines += [
        f"Benchmark **{r.benchmark}**, ước lượng trên {r.n_est_bars} phiên "
        f"(β = {r.beta:.2f})." if r.beta is not None else "",
        "",
        "| Cửa sổ | Ý nghĩa | Abnormal return |",
        "|---|---|---|",
        f"| t-5 … t-1 | rò rỉ trước sự kiện | **{_pct(r.car_pre)}** |",
        f"| t0 … t+1 | phản ứng tức thì | **{_pct(r.car_immediate)}** |",
        f"| t+1 … t+10 | trôi sau sự kiện | **{_pct(r.car_post)}** |",
        "",
        f"Lợi suất thô t0→t+10: **{_pct(r.ret_raw)}** "
        f"(thị trường {_pct(r.ret_benchmark)}).",
    ]
    if r.volume_ratio is not None:
        lines.append(f"Volume phiên t0: **{r.volume_ratio:.1f}×** trung bình 20 phiên "
                     f"(z = {r.volume_z}).")
    lines += ["", _read_pattern(r)]

    if r.limit_hit:
        lines += ["", "⚠️ **Có phiên trần/sàn trong cửa sổ** — biên độ thật lớn hơn "
                      "con số đo được, phép đo bị cắt cụt."]
    if r.incomplete:
        lines += ["", f"⚠️ {r.note}"]
    lines += ["", DISCLAIMER]
    return "\n".join(line for line in lines if line != "" or True)


def format_impact(symbol: str, items: Sequence[tuple]) -> str:
    """Nhiều sự kiện của một mã, mỗi cái kèm phản ứng đo được.

    ``items`` là chuỗi ``(nhãn sự kiện, Reaction)``.
    """
    if not items:
        return f"## {symbol}\n\nKhông có sự kiện nào để đo."
    out = [f"## {symbol} — sự kiện và phản ứng giá đã đo", ""]
    for label, reaction in items:
        out.append(format_reaction(reaction, title=label))
        out.append("")
    return "\n".join(out)


# --- Đầu mục tin tức N phiên gần nhất ------------------------------------

#: Nhãn ngắn đứng trước mỗi đầu mục. Đủ để phân biệt khi liếc, không chiếm dòng.
_GROUP_TAG = {"cbtt": "CBTT", "doanh_nghiep": "DN", "nganh": "Ngành"}

#: Trên tỷ lệ này thì các cửa sổ đo chồng lên nhau đủ nhiều để phải cảnh báo.
#: Nửa số phiên có tin nghĩa là khoảng cách trung bình giữa hai sự kiện ~2 phiên,
#: trong khi cửa sổ trước tin đã dài 5 phiên.
DENSE_NEWS_RATIO = 0.5


def _hhmm(published: str) -> str:
    """``2026-09-04T21:28:00+07:00`` → ``21:28``; rỗng khi không có giờ."""
    return published[11:16] if len(published) >= 16 and published[10:11] == "T" else ""


def _mapped_note(item) -> str:
    """Nói ra khi tin bị đẩy sang phiên sau — đây là chỗ người đọc dễ nghi nhất.

    Không giấu phép ánh xạ: thấy "đăng 21:28 ngày 04/09" dưới phiên 05/09 thì
    hiểu ngay vì sao, thay vì tưởng kho ghi sai ngày.
    """
    day = str(item.published)[:10]
    if not item.session or day == item.session:
        return ""
    hhmm = _hhmm(item.published)
    when = f"{hhmm} ngày {day[8:10]}/{day[5:7]}" if hhmm else f"ngày {day[8:10]}/{day[5:7]}"
    return f" _(đăng {when})_"


def format_digest_item(item) -> str:
    tag = _GROUP_TAG.get(item.group, item.group)
    line = f"- `{tag}` {item.title.strip()}"
    bits = [b for b in (item.source, *item.evidence) if b]
    if bits:
        line += f" — _{' · '.join(bits)}_"
    return line + _mapped_note(item)


def _digest_row(day: SessionNews) -> str:
    """Một dòng bảng tóm tắt cho một phiên."""
    r = day.reaction
    imm = _pct(r.car_immediate) if r else "—"
    pre = _pct(r.car_pre) if r else "—"
    post = _pct(r.car_post) if r and day.sessions_after >= 10 else "—"
    label = STATUS_VN.get(day.status, day.status)
    if day.status in (ST_NOT_MEASURED, ST_NO_SESSION):
        imm = pre = post = "—"
    session = day.session or "—"
    return (f"| {session} | **{label}** | {imm} | {pre} | {post} "
            f"| {len(day.items)} |")


def format_highlights(digest, limit: int = 5, title: str = "") -> str:
    """**Tin tiêu biểu & ảnh hưởng** — chỉ đầu mục và một con số, không hơn.

    Đây là khối để **liếc**: ai mở báo cáo cũng hỏi đúng một câu trước tiên —
    *"có tin gì đáng kể, và giá đã phản ứng chưa"* — mà trả lời nó bằng bảng 20
    phiên là bắt người đọc tự quét. Nên nêu vài đầu mục, mỗi cái một dòng.

    Ba chữ phải giữ đúng, vì chúng là ranh giới của cả tầng tin:

    * Con số là của **phiên**, không của tiêu đề. Dòng nào mà phiên đó có nhiều
      hơn một đầu mục thì nói ra ngay trên dòng — nếu không, người đọc sẽ đọc
      thành "tin này làm giá chạy 4%", tức một quan hệ nhân quả mà phép đo này
      không phân giải nổi.
    * Đây là **phép đo**, không phải nhận định: không bài nào được đọc nội
      dung. Nó chạy cho cả rổ mà không cần ai ngồi đọc.
    * Rỗng thì nói rõ là *chưa đo được gì*, không im lặng — một mục biến mất
      khi rỗng đọc y hệt một mục không tồn tại.
    """
    from src.news import digest as digest_mod

    head = title or "⭐ Tin tiêu biểu & ảnh hưởng"
    lines = [f"## {head}", ""]
    if digest is None or getattr(digest, "is_empty", True):
        return "\n".join(lines + [
            "Chưa có đầu mục nào trong cửa sổ — **chưa đo được**, không phải "
            "*không có tin*. Kho tin có thể chưa nạp; chạy `update_news`."])

    picks = digest_mod.highlights(digest, limit=limit)
    if not picks:
        return "\n".join(lines + [
            f"Có {digest.n_items} đầu mục nhưng **chưa phiên nào đo được phản "
            f"ứng đủ lớn** — hoặc cửa sổ sau tin chưa đầy, hoặc giá không đi xa "
            f"hơn thị trường. Xem bảng theo phiên bên dưới để biết là cái nào."])

    lines.append("Xếp theo độ lớn của phản ứng **đã đo được của phiên**, không "
                 "theo nội dung bài. Chi tiết đầy đủ ở bảng theo phiên bên dưới.")
    lines.append("")
    for h in picks:
        bits = []
        if h.car_immediate is not None:
            bits.append(f"tức thì {h.car_immediate * 100:+.1f}%")
        if h.car_post is not None:
            bits.append(f"trôi sau {h.car_post * 100:+.1f}%")
        status = STATUS_VN.get(h.status, h.status)
        tail = f" · _phiên này có {h.n_items} đầu mục_" if h.n_items > 1 else ""
        lines.append(f"- **{h.session}** · {status} ({' · '.join(bits)}) — "
                     f"“{h.title.strip()}”{tail}")
    lines += ["",
              "_Con số là của **phiên**, không của riêng tiêu đề đứng cạnh nó._"]
    return "\n".join(lines)


def format_digest(digest: NewsDigest, title: str = "") -> str:
    """Đầu mục + trạng thái, dạng markdown — dùng chung terminal và file HTML.

    Bố cục có chủ ý: **bảng trước, đầu mục sau**. Bảng trả lời "phiên nào có
    chuyện và giá đã phản ứng chưa" trong một lần liếc; phần dưới mới là tiêu đề
    để đọc. Ngược lại thì 20 phiên tin đẩy phần đáng đọc nhất xuống cuối trang.
    """
    head = title or f"📰 Tin tức {digest.sessions} phiên gần nhất"
    if digest.note:
        return f"## {head}\n\n⚠️ {digest.note}"
    if digest.is_empty:
        return (f"## {head}\n\nKhông có đầu mục nào trong khoảng "
                f"{digest.session_from} → {digest.session_to}. "
                f"Kho tin có thể chưa nạp — chạy `update_news`.")

    counts = digest.counts or {}
    summary = " · ".join(f"**{counts.get(g, 0)}** {GROUP_VN[g]}"
                         for g in GROUP_ORDER if counts.get(g))
    lines = [
        f"## {head}",
        "",
        f"{digest.n_items} đầu mục trong {digest.sessions} phiên "
        f"({digest.session_from} → {digest.session_to}) — {summary}.",
        "",
        # Không dùng blockquote ở đây: trong hồ sơ HTML, `>` render ra dải amber
        # dành riêng cho cảnh báo mốc hồi tưởng. Một ghi chú cách đọc mà mang
        # sắc thái "dữ liệu có vấn đề" là báo động giả.
        "**Cách đọc:** trạng thái gắn cho **phiên**, không gắn cho từng tiêu đề "
        "— một phiên nhiều tin thì không tách được tin nào làm giá chạy. Bài "
        "đăng từ 14:45 trở đi tính sang phiên kế tiếp, vì phiên đó đã đóng cửa "
        "trước khi tin ra. Tin ngành/thị trường cố ý không đo.",
        "",
        "| Phiên | Trạng thái | Tức thì t0…t+1 | Trước tin t-5…t-1 | Trôi sau t+1…t+10 | Tin |",
        "|---|---|---|---|---|---|",
    ]
    lines += [_digest_row(d) for d in digest.days]

    # Mã có tin gần như mỗi phiên (VIC: 18/20) làm các cửa sổ đo chồng lên nhau:
    # t-5…t-1 của phiên D trùm lên t0…t+1 của phiên D-3. Cùng một cú chạy giá
    # khi đó hiện ra ở nhiều dòng, và đọc bảng như một chuỗi quan sát độc lập là
    # đếm một sự kiện nhiều lần. Không sửa được bằng cách đo khác — mật độ tin
    # là như vậy — nên phải nói ra.
    measured = sum(1 for d in digest.days if d.reaction is not None)
    if digest.sessions and measured >= digest.sessions * DENSE_NEWS_RATIO:
        lines += ["",
                  f"⚠️ Mã này có tin ở {measured}/{digest.sessions} phiên. Các "
                  f"cửa sổ đo **chồng lên nhau** (t-5…t-1 của phiên này trùm lên "
                  f"t0…t+1 của phiên trước đó), nên các dòng trên **không phải "
                  f"quan sát độc lập** — cùng một cú chạy giá xuất hiện ở nhiều "
                  f"dòng."]

    lines += ["", "### Đầu mục theo phiên", ""]
    for day in digest.days:
        when = day.session or "chưa có phiên"
        label = STATUS_VN.get(day.status, day.status)
        note = STATUS_NOTE.get(day.status, "")
        lines.append(f"#### {when} · {label}")
        if note:
            lines.append(f"_{note}._")
        lines.append("")
        lines += [format_digest_item(i) for i in day.items]
        if day.reaction is not None and day.reaction.limit_hit:
            lines.append("- ⚠️ **Có phiên trần/sàn trong cửa sổ** — biên độ thật "
                         "lớn hơn con số đo được.")
        lines.append("")

    if digest.n_hidden:
        lines.append(f"_… còn {digest.n_hidden} đầu mục nữa không hiển thị "
                     f"(mỗi phiên chỉ nêu vài tin, ưu tiên CBTT)._")
    lines += ["", DISCLAIMER]
    return "\n".join(lines)


# --- Cờ đỏ ----------------------------------------------------------------

def _ruling_bits(flag) -> List[str]:
    """Phần nói ra **ai đã đọc cờ này và kết luận gì**. Rỗng thì nói là rỗng.

    Không gộp vào phần lý do của máy: một dòng trộn "khớp cụm `khoi to`" với
    "model bảo không liên quan" thì người đọc không biết câu nào của ai, mà
    chính chỗ tách bạch đó là thứ cho phép bác lại cái bác.
    """
    from src.news import rulings as rulings_mod

    r = flag.ruling
    if not r:
        return ["⏳ **chưa ai đọc** — mới là cụm từ khớp, chưa ai xác nhận sự "
                "kiện này nói về doanh nghiệp đang xét"]
    verdict = str(r.get("verdict") or "")
    label = rulings_mod.VERDICT_VN.get(verdict, verdict)
    level = str(r.get("level") or "")
    if level:
        label += f" · mức **{rulings_mod.LEVEL_VN.get(level, level)}**"
    who = str(r.get("source") or "không rõ")
    when = str(r.get("ruled_at") or "")[:10]
    out = [f"✅ **{label}** — {who}" + (f", {when}" if when else "")]
    reason = str(r.get("reason") or "").strip()
    if reason:
        out.append(f"“{reason}”")
    return out


def _flag_line(flag) -> str:
    """Một dòng cho một ứng viên cờ — **nguyên văn tiêu đề trước, lý do sau**.

    Thứ tự đó là cả điểm của khối này: người đọc phải bác được cái cờ bằng
    chính câu đã kích hoạt nó. Một dòng chỉ ghi "rủi ro pháp lý: −30" thì
    không bác được, và một cờ không bác được là một cờ phải tin.

    Ba tầng chữ, cố ý không trộn: tiêu đề (dữ kiện), phần máy đo (cụm đã khớp,
    điểm máy chấm), phần model phán (hướng, mức, lý do, tên người phán).
    """
    from src.news.redflag import RULES_BY_KEY

    when = (flag.published or "")[:10]
    age = f"{flag.age_days} ngày trước" if flag.age_days else "hôm nay"
    head = f"- **[{flag.label}]** {flag.title.strip()}"
    raw = flag.raw_score or flag.score
    bits = [f"{when} · {age}"]
    if flag.ruling and abs(raw - flag.score) >= 0.5:
        # Máy chấm một đằng, người đọc chấm một nẻo — in cả hai. Chỉ in con số
        # cuối là giấu mất việc đã có người can thiệp, và can thiệp bao nhiêu.
        bits.append(f"máy −{raw:.0f} → **−{flag.score:.0f} điểm**")
    else:
        bits.append(f"−{flag.score:.0f} điểm")
    if flag.source:
        bits.append(flag.source)
    if flag.from_other_symbol:
        bits.append("bài lưu dưới mã khác")
    if flag.tagged_count > 3:
        bits.append(f"bài gắn {flag.tagged_count} mã")
    lines = [head, f"  _{' · '.join(bits)}_"]
    rule = RULES_BY_KEY.get(flag.key)
    detail = [f"khớp cụm `{flag.matched}`"]
    if rule is not None and rule.why:
        detail.append(rule.why)
    detail += list(flag.notes)
    lines.append(f"  _{' · '.join(detail)}_")
    lines += [f"  _{bit}_" for bit in _ruling_bits(flag)]
    if flag.url:
        lines.append(f"  <{flag.url}>")
    return "\n".join(lines)


#: Câu đóng của khối, nói ra chính xác cái gì do máy làm và cái gì do người đọc.
READING_NOTE = (
    "**Cách đọc điểm trừ.** Máy chỉ **tìm ứng viên**: cụm từ khớp → trọng số "
    "nhóm × độ tin cậy × độ cũ. Nó không đọc được chiều của một sự kiện *đối "
    "với mã đang xét* — một cuộc điều tra chống bán phá giá là tin xấu với bên "
    "bị điều tra và tin tốt với bên đề nghị, mà cả hai cùng khớp đúng một cụm. "
    "Nên mỗi ứng viên phải qua một lượt đọc của model: giữ (và chấm lại theo "
    "nấc `nặng`/`vừa`/`nhẹ`), bác vì không liên quan, hoặc lật thành *có lợi*. "
    "Tổng lấy cờ nặng nhất cộng một phần các cờ còn lại, chặn ở 50."
)


def _dismissed_block(rf) -> List[str]:
    """Khối "đã bác" — **một dòng mỗi cái**, không in lại phần máy đo.

    Cờ đã qua một lượt đọc thì phần chi tiết của máy (cụm đã khớp, độ tin cậy,
    bài gắn mấy mã) không còn là thứ ai cần: nó là *lý lẽ của bộ lọc*, mà bộ
    lọc vừa bị bác. In lại nó ở đây chỉ làm loãng phần còn hiệu lực phía trên.

    Nhưng **không xoá hẳn**: giữ đúng tiêu đề, hướng bác và lý do, vì cái giá
    hai bên vẫn không đối xứng — một dòng thừa tốn hai giây để lướt qua, một
    vụ khởi tố bị bác nhầm rồi giấu đi là mua vào mà không biết. Một dòng là
    vừa đủ để bác lại cái bác, và đủ ngắn để không ai phải cuộn qua nó.
    """
    from src.news.rulings import V_FAVOURABLE, VERDICT_VN

    if not rf.dismissed:
        return []
    n_good = sum(1 for f in rf.dismissed
                 if (f.ruling or {}).get("verdict") == V_FAVOURABLE)
    who = ", ".join(rf.judged_by) or "model"
    lines = ["", f"### Đã bác — {len(rf.dismissed)} ứng viên, không tính điểm trừ",
             "",
             f"{who} đọc nguyên văn và thấy không phải cờ đỏ của mã này"
             + (f", trong đó **{n_good}** thật ra là tin **có lợi**"
                if n_good else "")
             + ". Một dòng mỗi cái, đủ để bác lại nếu bạn thấy sai:",
             ""]
    for f in rf.dismissed:
        r = f.ruling or {}
        label = VERDICT_VN.get(str(r.get("verdict") or ""), "đã bác")
        reason = str(r.get("reason") or "").strip()
        lines.append(
            f"- “{f.title.strip()}” · {f.published[:10]} — **{label}**"
            + (f": {reason}" if reason else ""))
    return lines


def format_redflags(rf, title: str = "", compact: bool = False) -> str:
    """Khối cờ đỏ dạng markdown — dùng chung terminal, gói bằng chứng, file HTML.

    Khối này **luôn được in**, kể cả khi sạch cờ: một mục trống nói "đã quét,
    không thấy gì" khác hẳn một mục không tồn tại, và người đọc không có cách
    nào phân biệt hai thứ đó nếu nó biến mất khi rỗng. Cùng lý do, nó phân biệt
    **bốn** trạng thái chứ không hai: chưa quét được / quét rồi không có ứng
    viên nào / có ứng viên nhưng chưa ai đọc / đã đọc xong.
    """
    from src.news.redflag import RULES_BY_KEY

    head = title or "🚩 Cờ đỏ — sự kiện pháp lý, quản trị, triển vọng"
    lines = [f"## {head}", ""]

    if rf is None:
        return "\n".join(lines + [
            "⚠️ **Chưa quét được cờ đỏ** — kho tin không đọc được. Đây là *chưa "
            "biết*, không phải *không có*."])

    window = f"{rf.window_days} ngày tới {rf.as_of}"
    if rf.is_empty and not rf.dismissed:
        lines += [
            f"**Không có cờ nào** trong {window} · đã quét {rf.n_scanned} bài.",
            "",
            "Quét theo sự kiện có tên (khởi tố, điều tra, xử phạt, huỷ niêm yết, "
            "chậm trả trái phiếu, ý kiến kiểm toán, tin đồn, triển vọng xấu), "
            "trên cả tiêu đề lẫn tóm tắt, và gồm cả bài đang lưu dưới mã khác.",
        ]
        if rf.note:
            lines += ["", f"⚠️ {rf.note}"]
        return "\n".join(lines)

    if rf.is_empty:
        # Mọi ứng viên đã bị bác. **Không** được rút gọn thành "không có cờ
        # nào": hai câu đó khác nhau đúng ở chỗ người đọc cần biết — một bên là
        # kho tin sạch, một bên là có người đã quyết định rằng nó sạch, và
        # quyết định đó bác lại được.
        lines += [
            f"**Không còn cờ nào sau khi đọc** — cả {len(rf.dismissed)} ứng viên "
            f"trong {window} đều bị bác"
            + (f" bởi {', '.join(rf.judged_by)}" if rf.judged_by else "")
            + f". Máy chấm −{rf.penalty_raw:.0f} trước khi đọc.",
        ]
        lines += _dismissed_block(rf)
        lines += ["", READING_NOTE]
        if rf.note:
            lines += ["", f"⚠️ {rf.note}"]
        return "\n".join(lines)

    score_line = f"### {rf.level_label} · điểm trừ **−{rf.penalty:.0f}**"
    if rf.penalty_raw and abs(rf.penalty_raw - rf.penalty) >= 0.5:
        score_line += f" _(máy chấm −{rf.penalty_raw:.0f} trước khi đọc)_"
    lines += [score_line, ""]
    groups = " · ".join(RULES_BY_KEY[k].label for k in rf.keys
                        if k in RULES_BY_KEY)
    lines += [f"{len(rf.flags)} đầu mục trong {window} ({rf.n_scanned} bài đã "
              f"quét) — {groups}.", ""]

    # Trạng thái đọc đứng ngay dưới điểm, không để xuống cuối khối: nó quyết
    # định con số phía trên đáng tin tới đâu, nên đọc sau con số là đọc muộn.
    if rf.n_pending:
        lines += [f"⏳ **{rf.n_pending}/{len(rf.flags)} ứng viên chưa ai đọc.** "
                  f"Điểm trừ của chúng do bộ lọc cụm từ chấm, mà bộ lọc đó "
                  f"không phân biệt được tin xấu *với mã này* và tin xấu *với "
                  f"một mã khác trong cùng bài*. Đây là **chưa duyệt**, không "
                  f"phải đã duyệt.", ""]
    elif rf.judged_by:
        lines += [f"✅ Cả {len(rf.flags)} cờ còn lại đã qua lượt đọc của "
                  f"{', '.join(rf.judged_by)}.", ""]

    if rf.has_critical:
        lines += ["> **Nhóm hình sự / thao túng đã dính.** Mọi kết luận nghiêng "
                  "về phía tăng phải nói ra điều này trước, không được để nó "
                  "nằm dưới phần số liệu.", ""]

    shown = rf.flags if not compact else rf.flags[:5]
    lines += [_flag_line(f) for f in shown]
    if compact and len(rf.flags) > len(shown):
        lines.append(f"\n_… còn {len(rf.flags) - len(shown)} đầu mục nữa._")

    lines += _dismissed_block(rf)
    lines += ["", READING_NOTE, "",
              "_Máy bắt thừa chứ không bắt thiếu, và mỗi dòng mang nguyên văn "
              "tiêu đề để bác lại được._"]
    if rf.note:
        lines += ["", f"⚠️ {rf.note}"]
    return "\n".join(lines)


def redflag_badge(rf) -> str:
    """Một dòng cực ngắn cho đầu báo cáo / dòng bảng. Rỗng khi sạch cờ."""
    from src.news.redflag import LEVEL_CLEAN

    if rf is None or rf.is_empty or rf.level == LEVEL_CLEAN:
        return ""
    return rf.headline


# ---------------------------------------------------------------------------
# nạp tin tức
# ---------------------------------------------------------------------------

def format_news_ingest(result, universe: str, mode: str,
                       with_posts: bool = True, limit: int = 15) -> str:
    """Lượt nạp tin vừa rồi thật sự thêm được gì.

    Hai con số phải đứng riêng: **ghi** gồm cả phần ghi đè do lượt nạp chồng lấn
    vài ngày với lần trước, **mới** là phần kho chưa từng có. In một mình con số
    ghi là báo "150 bài" cho một lượt thêm đúng 2 bài — nghe như có chuyện trong
    khi không có gì.

    Mã chạm trần trang phải hiện thành mục riêng, không lẫn vào ghi chú: nó
    nghĩa là mã đó **còn bài chưa nạp**, và lượt chạy tiếp theo cũng sẽ không
    lấy nốt nếu vẫn dùng mode cũ.
    """
    n = len(result.symbols)
    lines = [
        f"## Nạp tin tức & sự kiện — {n} mã · `{mode}`",
        "",
        f"**Phạm vi:** {universe} · {n} mã",
        "",
        f"- Giao dịch nội bộ / cổ đông lớn: **{result.total_transactions}** bản ghi",
        f"- Mốc sự kiện (BCTC, cổ tức): **{result.total_marks}**",
    ]
    if with_posts:
        lines.append(
            f"- Đầu mục tin: **{result.total_posts_new} bài mới** "
            f"(ghi {result.total_posts} dòng — phần chênh là ghi đè, "
            f"do lượt nạp cố ý chồng lấn vài ngày với lần trước)"
        )
    else:
        lines.append("- Đầu mục tin: **bỏ qua** (`with_posts=false`)")
    lines.append("")

    fresh = sorted((s for s in result.symbols if s.posts_new),
                   key=lambda s: -s.posts_new)
    if fresh:
        lines += ["| Mã | Bài mới | Nạp từ |", "|----|--------:|--------|"]
        for s in fresh[:limit]:
            lines.append(f"| **{s.symbol}** | {s.posts_new} | {s.posts_since or 'cả kho'} |")
        lines.append("")
        if len(fresh) > limit:
            lines.append(f"_… và {len(fresh) - limit} mã nữa có bài mới._")
            lines.append("")

    cut = result.truncated
    if cut:
        lines += [
            f"### ⚠️ {len(cut)} mã còn bài chưa nạp",
            "",
            "Phân trang dừng vì hết ngân sách trang, **không phải** vì đã lùi đủ "
            "xa — nghĩa là quãng giữa mốc cần và bài cũ nhất lấy được vẫn trống. "
            "Chạy lại các mã này với mode rộng hơn:",
            "",
            f"`{','.join(s.symbol for s in cut[:20])}` → `mode=\"quarter\"` "
            "(hoặc `full` nếu kho của mã còn rỗng).",
            "",
        ]

    if result.failed:
        lines += [f"### ⚠️ {len(result.failed)} mã lỗi", ""]
        lines += [f"- **{f.symbol}**: {f.error}" for f in result.failed[:10]]
        if len(result.failed) > 10:
            lines.append(f"- _… và {len(result.failed) - 10} mã nữa._")
        lines.append("")

    lines.append(
        "_Kho chỉ lưu **đầu mục** — tiêu đề, nguồn, ngày — cố ý không lưu toàn văn._"
    )
    return "\n".join(lines)
