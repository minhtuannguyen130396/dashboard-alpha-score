"""Chấm tin ngành bằng Gemini chạy nền — và **đi qua đúng validator** như Claude.

Đây là nhánh "tích luỹ tiến" của nợ H3. Giả thuyết *"điểm tin có thêm gì ngoài
các cột đo được"* không kiểm được bằng cách backfill: một model chấm tin tháng 3
vào hôm nay đã biết thị trường đi đâu sau đó, và ``as_of`` cắt được **dữ liệu**
chứ không cắt được **trí nhớ của model**. Cách duy nhất là tích luỹ về phía
trước, mỗi tuần một lượt, rồi sáu tháng nữa mới đo được.

Điều đó chỉ xảy ra nếu có cái gì chạy đều — nhận định chỉ sinh ra khi có người
gọi ``sector_submit``, và không ai nhớ làm việc đó mỗi tuần. Nên module này tồn
tại.

Hai quy ước kế thừa nguyên từ ``src/news/verdict.py``, và cái thứ ba là mới:

1. **Hỏng thì trả khoá ``error``, không trả điểm 0.** 0 nghĩa là *đã đọc và thấy
   trung tính*; hỏng nghĩa là *chưa đọc được*. Gộp hai cái đó là bịa ra một nhận
   định không ai đưa ra.
2. **Bản của Claude đè bản Gemini cùng ngày, không bao giờ ngược lại**, và hai
   bản không bao giờ lấy trung bình.
3. **Bản Gemini đi qua cùng một ``validate()``.** Nếu bản chạy nền được miễn
   kiểm thì cả tầng chống ảo giác chỉ áp cho những lượt có người ngồi xem — tức
   là áp cho đúng những lượt ít cần nó nhất. Gemini bịa một con số thì luận điểm
   đó bị loại y hệt, và ``claims_dropped`` đi theo vào file.
"""
import argparse
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.macro import icb
from src.macro import verdict as verdict_mod

DEFAULT_MODEL = "gemini-flash-latest"
SRC_GEMINI = "gemini"

#: Nhận định do Gemini viết mang tiền tố này ở ``source``. Đọc lại là biết ngay
#: ai viết — điều kiện để bản Claude biết mình được phép đè lên cái gì.
SOURCE_PREFIX = f"{SRC_GEMINI}:"


def is_gemini(source: str) -> bool:
    return str(source or "").startswith(SOURCE_PREFIX)


@dataclass
class Scored:
    """Kết quả một lượt chấm — phân biệt *hỏng* với *chấm ra điểm thấp*."""
    code: str
    name: str = ""
    verdict: Optional[verdict_mod.Verdict] = None
    error: str = ""
    skipped: str = ""

    @property
    def ok(self) -> bool:
        return self.verdict is not None and self.verdict.accepted

    def to_dict(self) -> Dict[str, Any]:
        return {"code": self.code, "name": self.name, "error": self.error,
                "skipped": self.skipped,
                "verdict": self.verdict.to_dict() if self.verdict else None}


def score_one(code: str, as_of: Optional[datetime] = None,
              model: str = DEFAULT_MODEL,
              api_key: Optional[str] = None,
              news_days: int = verdict_mod.NEWS_DAYS) -> Scored:
    """Dựng gói bằng chứng, gửi Gemini, **chạy validator**, rồi ghi file."""
    out = Scored(code=str(code))
    key = (api_key or os.environ.get("GEMINI_API_KEY")
           or os.environ.get("GOOGLE_API_KEY"))
    if not key:
        out.error = "chưa đặt GEMINI_API_KEY / GOOGLE_API_KEY"
        return out

    day = as_of or datetime.now()
    try:
        ev = verdict_mod.build_evidence(code, day, news_days=news_days)
    except Exception as exc:                               # noqa: BLE001
        out.error = f"không dựng được gói bằng chứng: {type(exc).__name__}: {exc}"
        return out
    out.name = ev.name

    # Không có tin thì **không gọi model**. Bắt nó chấm một gói rỗng là mời nó
    # dựng nhận định từ chỗ không có gì — và nó sẽ làm, vì được yêu cầu.
    if not ev.untrusted:
        out.skipped = ("không có tin nào khớp từ khoá ngành trong cửa sổ — "
                       "*chưa chấm được*, không phải *chấm ra trung tính*")
        return out

    text, err = _generate(verdict_mod.format_evidence(ev), model, key)
    if err:
        out.error = err
        return out
    payload = _extract_json(text)
    if payload is None:
        out.error = "Gemini trả về không phải JSON"
        return out

    # Ghi đè `source` bằng tên model thật. Để model tự khai là mở đường cho nó
    # ký tên người khác — và cả luật "bản Claude đè bản Gemini" dựa vào trường
    # này để biết được phép đè lên cái gì.
    payload["source"] = f"{SOURCE_PREFIX}{model}"

    v = verdict_mod.validate(payload, ev, day)
    out.verdict = v
    if v.accepted:
        _save_if_allowed(v)
    return out


def _generate(prompt: str, model: str, key: str) -> Tuple[str, str]:
    """Gọi Gemini. Trả ``(text, error)`` — đúng một trong hai rỗng.

    Thử SDK **mới** (``google-genai``) trước, rơi về SDK cũ
    (``google-generativeai``) nếu chưa cài. Không phải cầu kỳ vô cớ: Google đã
    tuyên bố SDK cũ **hết vòng đời**, *"no longer receiving updates or bug
    fixes"*, và module này là xương sống của một job chạy **không người trông
    suốt sáu tháng**. SDK hỏng thì việc tích luỹ dừng im lặng, và H3 vĩnh viễn
    không kiểm được — đúng thứ cả nhánh này sinh ra để tránh.

    ``src/news/verdict.py`` ở tầng mã vẫn dùng SDK cũ; chuyển nó là việc riêng,
    không nhét vào đây.
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        pass
    else:
        try:
            client = genai.Client(api_key=key)
            response = client.models.generate_content(
                model=model, contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=verdict_mod.SCORING_GUIDE))
            return (response.text or ""), ""
        except Exception as exc:                           # noqa: BLE001
            return "", f"{type(exc).__name__}: {exc}"

    try:
        import google.generativeai as legacy
    except ImportError:
        return "", ("chưa cài SDK Gemini — `pip install google-genai` "
                    "(bản cũ `google-generativeai` đã hết vòng đời)")
    try:
        legacy.configure(api_key=key)
        gen = legacy.GenerativeModel(
            model_name=model, system_instruction=verdict_mod.SCORING_GUIDE)
        return (gen.generate_content(prompt).text or ""), ""
    except Exception as exc:                               # noqa: BLE001
        return "", f"{type(exc).__name__}: {exc}"


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    raw = str(text or "").strip()
    if "```" in raw:
        for part in raw.split("```"):
            body = part.lstrip()
            if body.lower().startswith("json"):
                body = body[4:]
            body = body.strip()
            if body.startswith("{"):
                raw = body
                break
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start:end + 1])
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _save_if_allowed(v: verdict_mod.Verdict,
                     root: Optional[Path] = None) -> bool:
    """Ghi bản Gemini **trừ khi** đã có bản của người khác cùng ngày.

    Luật một chiều, kế thừa từ tầng mã: bản Claude đè bản Gemini, không bao giờ
    ngược lại. Một lượt chạy nền lúc 2 giờ sáng không được phép xoá nhận định
    mà người dùng vừa viết tay chiều hôm trước.
    """
    path = verdict_mod.verdict_path(v.code, v.as_of, root)
    if path.is_file():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            old = {}
        if old.get("source") and not is_gemini(old.get("source", "")):
            return False
    verdict_mod.save(v, root)
    return True


def score_all(codes: Optional[Sequence[str]] = None,
              as_of: Optional[datetime] = None,
              model: str = DEFAULT_MODEL,
              news_days: int = verdict_mod.NEWS_DAYS) -> List[Scored]:
    tree = icb.fetch_tree()
    names = {i.code: i.name for i in tree}
    codes = list(codes or icb.distinct_codes(tree))
    out = []
    for code in codes:
        row = score_one(code, as_of, model, news_days=news_days)
        row.name = row.name or names.get(code, "")
        out.append(row)
    return out


def format_run(rows: Sequence[Scored]) -> str:
    ok = [r for r in rows if r.ok]
    bad = [r for r in rows if r.error]
    skip = [r for r in rows if r.skipped]
    rejected = [r for r in rows if r.verdict is not None and not r.verdict.accepted]

    lines = [f"# Chấm tin ngành (Gemini) — {datetime.now():%Y-%m-%d %H:%M}", "",
             f"**{len(ok)}/{len(rows)}** ngành có nhận định mới · "
             f"{len(rejected)} bị validator loại · {len(skip)} không có tin · "
             f"{len(bad)} lỗi", ""]
    if ok:
        lines += ["| Ngành | Điểm | Tư thế | Luận điểm | Bị loại |",
                  "|---|--:|---|--:|--:|"]
        for r in sorted(ok, key=lambda x: -(x.verdict.score or 0)):
            v = r.verdict
            score = "—" if v.score is None else f"{v.score:+.0f}"
            lines.append(
                f"| {r.name} `{r.code}` | {score} | "
                f"{verdict_mod.STANCE_VN.get(v.stance, v.stance)} | "
                f"{len(v.claims)} | {len(v.claims_dropped)} |")
        lines.append("")
    if rejected:
        lines += ["**Bị validator loại** (không ghi file):"]
        for r in rejected:
            lines.append(f"- {r.name} `{r.code}`: {r.verdict.rejected}")
        lines.append("")
    if skip:
        lines += [f"**Không có tin** ({len(skip)} ngành): "
                  + ", ".join(f"`{r.code}`" for r in skip), "",
                  "*Đây là chưa chấm được, không phải chấm ra trung tính — cột "
                  "tin của các ngành này để trống.*", ""]
    if bad:
        lines += ["**Lỗi:**"]
        for r in bad[:10]:
            lines.append(f"- `{r.code}`: {r.error}")
        lines.append("")
    lines += ["---", "",
              "Nhận định của Gemini đi qua **cùng validator** với bản viết tay: "
              "luận điểm bịa số vẫn bị loại, và số bị loại vẫn in ra. Bản do "
              "người viết (`sector_submit`) **đè** bản này cùng ngày, không bao "
              "giờ ngược lại."]
    return "\n".join(lines)


def _main() -> None:
    ap = argparse.ArgumentParser(
        description="Chấm tin ngành bằng Gemini và tích luỹ nhận định")
    ap.add_argument("--codes", default="")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--news-days", type=int, default=verdict_mod.NEWS_DAYS)
    args = ap.parse_args()
    codes = [c for c in args.codes.split(",") if c.strip()] or None
    print(format_run(score_all(codes, model=args.model,
                               news_days=args.news_days)))


if __name__ == "__main__":
    _main()
