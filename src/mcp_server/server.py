"""MCP server exposing the local Vietnamese-stock TA engine to Claude Code.

Transport is stdio, so **nothing may be written to stdout** except the JSON-RPC
stream. Existing modules in this repo print progress lines, so every tool body
runs with stdout redirected to stderr.
"""
import sys
from contextlib import contextmanager, redirect_stdout
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

# Allow `python src/mcp_server/server.py` as well as `python -m src.mcp_server`.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcp.server import MCPServer                                    # noqa: E402
from mcp.server.mcpserver import Image                              # noqa: E402

from src.ta import asof as asof_mod                                 # noqa: E402
from src.ta.config import PROFILES                                  # noqa: E402
from src.ta import dossier as dossier_mod                           # noqa: E402
from src.ta.format import (                                         # noqa: E402
    format_deep_dive, format_forecast_check, format_forecast_list,
    format_futures, format_futures_exposure, format_futures_stats,
    format_rank_list, format_ranking, format_scan, format_structure,
    format_symbol_list, format_update, format_usage_guide,
)
from src.ta.forecast import check_all, propose, save as save_forecast  # noqa: E402
from src.ta import futures as futures_mod                           # noqa: E402
from src.ta import ranking as ranking_mod                           # noqa: E402
from src.ta import report as report_mod                             # noqa: E402
from src.ta.loader import GROUP_FILES, coverage, resolve_universe   # noqa: E402
from src.ta.render import render_interactive, render_structure_chart  # noqa: E402
from src.ta.scan import RULES, scan                                 # noqa: E402
from src.ta.snapshot import build_snapshot                          # noqa: E402
from src.ta.structure import build_structure                        # noqa: E402
from src.ta.update import MODES, update_prices                      # noqa: E402

from src.news import format as news_format                          # noqa: E402
from src.news import ingest as news_ingest                          # noqa: E402
from src.news import reaction as news_reaction                      # noqa: E402
from src.news import stats as news_stats_mod                        # noqa: E402
from src.news import store as news_store                            # noqa: E402
from src.news.models import DIRECTION_VN                            # noqa: E402

#: Rendering an image per symbol is expensive in tokens — keep the batch small.
_MAX_CHART_SYMBOLS = 5
#: A dossier is ~350 KB of self-contained HTML each; a whole group is not useful.
_MAX_DOSSIER_SYMBOLS = 5

mcp = MCPServer(
    name="vn-ta",
    title="Phan tich ky thuat chung khoan VN",
    version="0.1.0",
    instructions=(
        "Phan tich ky thuat co phieu Viet Nam tu du lieu local trong thu muc data/.\n"
        "Neu nguoi dung khong biet bat dau tu dau, goi `usage_guide` truoc.\n"
        "- `scan_signals`: ra soat theo lo (RSI quay dau tai nguong qua mua/qua ban, ADX > 20)\n"
        "- `analyze_structure`: trendline, bounding box, hinh mau + anh bieu do\n"
        "- `technical_report`: chi bao chi tiet 1 hoac nhieu ma\n"
        "- `build_dossier`: bao cao 1 ma ra file HTML — chart TradingView tuong tac da ve "
        "trendline + hop tich luy, kem toan bo noi dung deep-dive\n"
        "- `build_report`: bang tong hop NHIEU ma, xuat file HTML co anh PNG\n"
        "- `build_ranking`: cham diem + xep hang CA RO (mac dinh 'all') theo cuong do xu huong "
        "va do tin cay mau hinh; ghi file HTML sap xep duoc + file JSON tong hop\n"
        "- `rank_list`: doc lai file JSON do `build_ranking` ghi ra, tra ve danh sach ma da "
        "sap xep theo tieu chi nguoi dung chon, cao->thap hoac nguoc lai\n"
        "- `create_forecasts` / `check_forecasts`: dat ky vong co the kiem chung roi doi chieu\n"
        "- `futures_snapshot`: thi truong phai sinh VN30 - basis, don bay, tu doanh / "
        "khoi ngoai tren hop dong, dem nguoc toi phien dao han\n"
        "- `futures_exposure`: ma nao chiu anh huong cua dong tien phai sinh, qua duong nao\n"
        "- `futures_stats`: base rate - sau moi muc basis thi VN30 that su di dau\n"
        "- `update_prices_tool`: tai gia moi nhat tu FireAnt ve data/ va xoa cache doc\n"
        "- `list_symbols` / `list_presets`: ma nao co du lieu, nhom va nguong nao dung duoc\n"
        "Ket qua tra ve la markdown, in thang cho nguoi dung. Day la so lieu ky thuat, "
        "khong phai khuyen nghi dau tu."
    ),
)


@contextmanager
def _quiet():
    """Keep library print() calls off the JSON-RPC stdout stream."""
    with redirect_stdout(sys.stderr):
        yield


#: Cau mo ta tham so `as_of`, dung lai o moi tool co bao cao.
_AS_OF_DOC = (
    "as_of: MOC THOI GIAN — gia dinh 'hom nay' la ngay do, moi phien sau moc bi cat bo. "
    "Nhan '01/01/2025' (ngay/thang/nam, kieu Viet Nam) hoac '2025-01-01'. "
    "Bo trong = chay tren du lieu moi nhat."
)


def _parse_date(value: str) -> Optional[datetime]:
    """Moc hoi tuong tu chuoi nguoi dung go — xem `src/ta/asof.py`."""
    return asof_mod.parse(value)


def _cutoff(value: str) -> Tuple[Optional[datetime], Optional[str]]:
    """``(moc, loi)``. Ngay go sai la loi cua nguoi dung, khong phai su co cua server:
    tra ve cau giai thich de tool in thang ra, thay vi nem ra luong JSON-RPC."""
    try:
        return asof_mod.parse(value), None
    except ValueError as exc:
        return None, str(exc)


@mcp.tool(
    title="Danh sach ma co du lieu",
    description=(
        "Liet ke cac ma co du lieu gia trong thu muc data/, kem khoang thoi gian phu song. "
        "group: 'vn30' | 'largecap' | 'midcap' | 'all' | 'disk' (mac dinh: tat ca ma tren o dia) "
        "hoac danh sach ma ngan cach bang dau phay."
    ),
)
def list_symbols(group: str = "disk", limit: int = 200) -> str:
    with _quiet():
        symbols = resolve_universe(group)[:max(1, limit)]
        rows = []
        for sym in symbols:
            cov = coverage(sym)
            rows.append({
                "symbol": sym,
                "first": cov[0] if cov else "—",
                "last": cov[1] if cov else "—",
                "bars": cov[2] if cov else 0,
            })
        title = f"Ma co du lieu ({group})"
        return format_symbol_list(rows, title)


@mcp.tool(
    title="Bao cao ky thuat 1 hoac nhieu ma",
    description=(
        "Bao cao tong quan ky thuat cho mot hoac nhieu ma: xu huong (EMA20/50/100), "
        "dong luong (RSI14 + trang thai vung qua mua/qua ban, ADX14 + huong tu +DI/-DI, MACD, MFI), "
        "thanh khoan, vung gia tham chieu va lich su tin hieu RSI gan day. "
        "symbols: mot ma ('ANV') hoac nhieu ma ngan cach dau phay ('ANV,HPG,ACB') hoac ten nhom ('vn30'). "
        + _AS_OF_DOC
    ),
)
def technical_report(
    symbols: str,
    lookback_days: int = 400,
    profile: str = "standard",
    as_of: str = "",
) -> str:
    with _quiet():
        if profile not in PROFILES:
            return f"Profile khong hop le: {profile!r}. Chon: {', '.join(PROFILES)}"
        wanted = resolve_universe(symbols)
        if not wanted:
            return (
                f"Khong tim thay du lieu cho {symbols!r}. "
                "Dung `list_symbols` de xem cac ma san co."
            )
        cutoff, bad_date = _cutoff(as_of)
        if bad_date:
            return bad_date
        parts = []
        for sym in wanted[:20]:
            snap = build_snapshot(sym, as_of=cutoff, lookback_days=lookback_days, profile=profile)
            structure = (build_structure(sym, lookback_days=lookback_days, as_of=cutoff)
                         if snap.bars else None)
            parts.append(format_deep_dive(snap, structure))
        out = "\n\n---\n\n".join(parts)
        if len(wanted) > 20:
            out += f"\n\n_Da gioi han 20 ma dau tien trong {len(wanted)} ma yeu cau._"
        return out


@mcp.tool(
    title="Quet tin hieu theo lo",
    description=(
        "Ra soat theo lo cac tin hieu ky thuat tren nhieu ma. "
        "rules (ngan cach dau phay, bo trong = tat ca): "
        "'rsi_oversold_reclaim' = RSI da xuong duoi vung qua ban, quay dau va cham lai nguong; "
        "'rsi_overbought_loss' = RSI da vuot vung qua mua, quay dau va cham lai nguong; "
        "'rsi_turning_up' / 'rsi_turning_down' = con trong vung nhung da co dau hieu quay dau; "
        "'adx_momentum' = ADX tren nguong dong luc (mac dinh 20). "
        "universe: 'vn30' | 'largecap' | 'midcap' | 'all' | danh sach ma. "
        "recent_bars: chi lay tin hieu xay ra trong N phien gan nhat. "
        + _AS_OF_DOC
    ),
)
def scan_signals(
    universe: str = "vn30",
    rules: str = "",
    profile: str = "standard",
    recent_bars: int = 5,
    min_score: int = 0,
    limit: int = 40,
    detail: bool = False,
    as_of: str = "",
) -> str:
    with _quiet():
        if profile not in PROFILES:
            return f"Profile khong hop le: {profile!r}. Chon: {', '.join(PROFILES)}"
        selected = [r.strip() for r in rules.replace(";", ",").split(",") if r.strip()]
        bad = [r for r in selected if r not in RULES]
        if bad:
            return f"Luat khong hop le: {', '.join(bad)}. Chon: {', '.join(RULES)}"
        cutoff, bad_date = _cutoff(as_of)
        if bad_date:
            return bad_date
        result = scan(
            universe=universe,
            rules=selected or None,
            profile=profile,
            recent_bars=max(1, recent_bars),
            as_of=cutoff,
            min_score=min_score,
        )
        return format_scan(result, limit=limit, show_detail=detail)


@mcp.tool(
    title="Phan tich cau truc gia + ve bieu do",
    description=(
        "Dung cau truc gia cho 1 hoac nhieu ma va ve bieu do co chu thich: "
        "swing pivot, duong noi dinh / noi day (trendline) kem so lan cham va da bi pha vo chua, "
        "bounding box vung tich luy kem trang thai breakout (co volume xac nhan hay khong), "
        "hinh mau gia (tam giac tang/giam/can, kenh gia, nem), muc tieu do duoc va muc huy. "
        "Tra ve ca phan dien giai bang chu lan anh PNG (RSI14 va ADX14 o pane duoi). "
        "symbols: 'ANV' hoac 'ANV,HPG' hoac ten nhom. "
        "lookback_days: so ngay lich su dung de dung cau truc (mac dinh 180). "
        "with_html=true ghi them file chart HTML tuong tac (TradingView) co ve san overlay. "
        + _AS_OF_DOC
    ),
)
def analyze_structure(
    symbols: str,
    lookback_days: int = 180,
    with_chart: bool = True,
    with_html: bool = False,
    as_of: str = "",
) -> list:
    with _quiet():
        wanted = resolve_universe(symbols)
        if not wanted:
            return [
                f"Khong tim thay du lieu cho {symbols!r}. "
                "Dung `list_symbols` de xem cac ma san co."
            ]
        cutoff, bad_date = _cutoff(as_of)
        if bad_date:
            return [bad_date]
        limit = _MAX_CHART_SYMBOLS if with_chart else 20
        blocks: list = []
        for sym in wanted[:limit]:
            structure = build_structure(sym, lookback_days=lookback_days, as_of=cutoff)
            path = None
            if with_chart and structure.bars:
                try:
                    path = render_structure_chart(structure)
                except Exception as exc:                 # a failed plot must not lose the text
                    structure.warnings.append(f"Khong ve duoc bieu do: {type(exc).__name__}: {exc}")
            block = format_structure(structure, image_path=path)
            if with_html and structure.bars:
                try:
                    html = render_interactive(sym, lookback_days=lookback_days,
                                              as_of=cutoff, open_browser=False)
                    block += f"\n\n🔗 Chart tuong tac: `{html}`"
                except Exception as exc:
                    block += f"\n\n⚠️ Khong ghi duoc chart HTML: {type(exc).__name__}: {exc}"
            blocks.append(block)
            if path:
                blocks.append(Image(path=path))
        if len(wanted) > limit:
            blocks.append(f"_Da gioi han {limit} ma dau tien trong {len(wanted)} ma yeu cau._")
        return blocks


@mcp.tool(
    title="Bao cao ky thuat tong hop",
    description=(
        "Bao cao tong quan ky thuat cho mot nhom ma: bang tong quan (gia, xu huong, RSI, ADX, "
        "hop tich luy, diem noi bat), trang thai forecast, va phan chi tiet tung ma kem bieu do. "
        "Ghi ra mot file HTML tu chua (anh nhung san duoi dang base64) trong thu muc reports/, "
        "va tra ve ban tom tat markdown. symbols: danh sach ma hoac ten nhom ('vn30'). "
        "max_images: so bieu do dinh kem thang vao ket qua (mac dinh 3, dat 0 neu chi can file HTML). "
        + _AS_OF_DOC +
        " Bao cao hoi tuong ghi vao reports/asof_<ngay>/ va co dai canh bao ngay trong file HTML."
    ),
)
def build_report(
    symbols: str,
    lookback_days: int = 180,
    profile: str = "standard",
    with_charts: bool = True,
    detail: bool = True,
    max_images: int = 3,
    as_of: str = "",
) -> list:
    with _quiet():
        if profile not in PROFILES:
            return [f"Profile khong hop le: {profile!r}. Chon: {', '.join(PROFILES)}"]
        cutoff, bad_date = _cutoff(as_of)
        if bad_date:
            return [bad_date]
        rep = report_mod.build(
            symbols, lookback_days=lookback_days, profile=profile,
            with_charts=with_charts, as_of=cutoff,
        )
        blocks: list = [report_mod.to_markdown(rep, detail=detail)]
        for section in rep.sections[:max(0, max_images)]:
            if section.chart_path:
                blocks.append(Image(path=section.chart_path))
        return blocks


@mcp.tool(
    title="Ho so ky thuat 1 ma — file HTML co chart tuong tac",
    description=(
        "Xuat cho MOI ma mot file HTML tu chua trong reports/, gom: bieu do TradingView "
        "tuong tac (nen + volume + RSI + MACD + ADX, keo/zoom duoc) da ve san duong noi dinh / "
        "noi day, hop tich luy (hinh chu nhat dung tren so phien no thuc su chiem), neckline va "
        "muc tieu do duoc — reo chuot len mot duong ke se hien vi sao no duoc ve; ben duoi bieu do "
        "la toan bo noi dung deep-dive cua ma do (xu huong, dong luong, thanh khoan, vung gia, "
        "mo hinh dao chieu, dien giai, forecast dang mo). "
        "Dung khi nguoi dung muon 'bao cao mot ma', 'file HTML', 'bieu do co trendline va box'. "
        "Khac `build_report`: build_report la bang tong hop NHIEU ma kem anh PNG tinh; day la "
        "ho so tung ma voi bieu do tuong tac. "
        "symbols: 'FPT' hoac 'FPT,HPG' hoac ten nhom — toi da 5 ma moi lan. "
        + _AS_OF_DOC +
        " Ho so hoi tuong ghi vao reports/asof_<ngay>/, chart chi ve toi moc do."
    ),
)
def build_dossier(
    symbols: str,
    lookback_days: int = 260,
    profile: str = "standard",
    as_of: str = "",
) -> str:
    with _quiet():
        if profile not in PROFILES:
            return f"Profile khong hop le: {profile!r}. Chon: {', '.join(PROFILES)}"
        wanted = resolve_universe(symbols)
        if not wanted:
            return (
                f"Khong tim thay du lieu cho {symbols!r}. "
                "Dung `list_symbols` de xem cac ma san co."
            )
        cutoff, bad_date = _cutoff(as_of)
        if bad_date:
            return bad_date
        parts: list = []
        for sym in wanted[:_MAX_DOSSIER_SYMBOLS]:
            try:
                dossier = dossier_mod.build_dossier(
                    sym, lookback_days=lookback_days, profile=profile, as_of=cutoff)
            except Exception as exc:
                parts.append(f"⚠️ {sym}: {type(exc).__name__}: {exc}")
                continue
            if dossier is None:
                parts.append(f"⚠️ {sym}: khong co du lieu gia")
                continue
            parts.append(f"{dossier.markdown}\n\n📄 Ho so HTML: `{dossier.path}`")
        if len(wanted) > _MAX_DOSSIER_SYMBOLS:
            parts.append(f"_Da gioi han {_MAX_DOSSIER_SYMBOLS} ma dau tien trong "
                         f"{len(wanted)} ma yeu cau._")
        return "\n\n---\n\n".join(parts)


@mcp.tool(
    title="Xep hang ca ro ra file HTML + file JSON tong hop",
    description=(
        "Cham diem VA XEP HANG toan bo mot nhom ma theo hai truc doc lap: "
        "(1) CUONG DO XU HUONG -100..+100 = ADX x huong + xep tang EMA + chuoi swing HH/HL "
        "va BOS/CHoCH + quang duong 20 phien do bang ATR; "
        "(2) DO TIN CAY MAU HINH 0..100 kem trang thai 'da xac nhan' / 'xac nhan mot phan' / "
        "'chua xac nhan' / 'co yeu to mau thuan' / 'mau hinh hong', lay tu mo hinh dao chieu "
        "(hop luu nen + volume) hoac hop tich luy hoac hinh mau gia. "
        "Ghi ra 2 file trong reports/<ngay>/: mot file HTML tu chua (4 bang xep hang + bang "
        "toan bo cac ma bam tieu de cot de sap xep + chi tiet tung ma) va mot file JSON tong "
        "hop de `rank_list` doc lai. "
        "Dung khi nguoi dung noi 'bao cao tat ca co phieu', 'xep hang ca ro', 'ma nao tang "
        "manh nhat', 'quet toan bo thi truong'. "
        "universe: 'all' (mac dinh, moi ma co du lieu) | 'vn30' | 'largecap' | 'midcap' | "
        "danh sach ma. Chay 'all' (~125 ma) mat khoang 5 giay. "
        + _AS_OF_DOC +
        " Bang hoi tuong ghi vao reports/asof_<ngay>/ va KHONG thay the bang cua phien that; "
        "de xep lai bang do, goi `rank_list` voi cung tham so as_of."
    ),
)
def build_ranking(
    universe: str = "all",
    lookback_days: int = 260,
    profile: str = "standard",
    top: int = 8,
    as_of: str = "",
) -> str:
    with _quiet():
        if profile not in PROFILES:
            return f"Profile khong hop le: {profile!r}. Chon: {', '.join(PROFILES)}"
        cutoff, bad_date = _cutoff(as_of)
        if bad_date:
            return bad_date
        result = ranking_mod.build(
            universe=universe, lookback_days=lookback_days, profile=profile,
            as_of=cutoff,
        )
        return format_ranking(result, top=max(1, top))


@mcp.tool(
    title="Sap xep lai bang xep hang theo mot tieu chi",
    description=(
        "Doc lai file JSON do `build_ranking` ghi ra roi tra ve DANH SACH MA da sap xep theo "
        "mot tieu chi, tu cao xuong thap hoac nguoc lai — khong tinh toan lai. "
        "criterion: 'trend' (cuong do xu huong, co dau) | 'trend_abs' | 'pattern' | "
        "'confidence' (do tin cay mau hinh) | 'adx' | 'rsi' | 'change_pct' | 'change_5d' | "
        "'change_20d' | 'rvol' | 'atr_pct' | 'vs_ema20' | 'vs_ema50' | 'box_position' | "
        "'close' | 'target_pct' | 'risk_reward'. Nhan ca ten tieng Viet: 'cuong do', "
        "'do tin cay', 'thanh khoan', 'bien dong', 'muc tieu'... "
        "descending=false de dao chieu (thap -> cao). "
        "side loc theo xu huong ('tang' / 'giam' / 'di ngang'); "
        "bias loc theo huong mau hinh ('tang' / 'giam'); "
        "min_confidence loc theo muc tin cay toi thieu ('da xac nhan', 'xac nhan mot phan', "
        "'chua xac nhan'). path: doc mot file xep hang cu the, bo trong = ban moi nhat. "
        "as_of: doc lai BANG HOI TUONG cua moc do (vi du '01/01/2025') thay vi bang cua "
        "phien that — phai da chay `build_ranking` voi cung moc truoc."
    ),
)
def rank_list(
    criterion: str = "trend",
    descending: bool = True,
    side: str = "",
    bias: str = "",
    min_confidence: str = "",
    limit: int = 20,
    path: str = "",
    as_of: str = "",
) -> str:
    with _quiet():
        cutoff, bad_date = _cutoff(as_of)
        if bad_date:
            return bad_date
        try:
            board = ranking_mod.load_ranking(path or None, as_of=cutoff)
        except FileNotFoundError as exc:
            return str(exc)
        try:
            rows, crit = ranking_mod.sort_rows(
                board.rows, criterion=criterion, descending=descending,
                side=side, bias=bias, min_confidence=min_confidence,
                limit=max(0, limit),
            )
        except ValueError as exc:
            return str(exc)
        filters = [f for f in (
            f"xu hướng {side}" if side else "",
            f"mẫu hình {bias}" if bias else "",
            f"tin cậy ≥ {min_confidence}" if min_confidence else "",
        ) if f]
        return format_rank_list(rows, crit, descending=descending,
                                total=len(board.rows), filters=filters, as_of=board.as_of,
                                as_of_requested=board.as_of_requested)


@mcp.tool(
    title="Tao forecast tu cau truc gia",
    description=(
        "Doc cau truc gia hien tai va dat ra cac forecast co the kiem chung: dieu kien kich hoat "
        "(dong cua vuot muc gia nao, co can volume xac nhan khong), muc tieu do duoc, muc gia lam "
        "hong kich ban, va han bao nhieu phien. Cac co so: pha hop tich luy, vuot duong noi dinh, "
        "RSI bat khoi vung qua ban. Forecast duoc luu vao thu muc forecasts/ de doi chieu ve sau "
        "bang `check_forecasts`. dry_run=true chi xem thu, khong luu. "
        + _AS_OF_DOC
    ),
)
def create_forecasts(
    symbols: str,
    lookback_days: int = 180,
    dry_run: bool = False,
    as_of: str = "",
) -> str:
    with _quiet():
        wanted = resolve_universe(symbols)
        if not wanted:
            return f"Khong tim thay du lieu cho {symbols!r}."
        cutoff, bad_date = _cutoff(as_of)
        if bad_date:
            return bad_date
        made = []
        for sym in wanted[:30]:
            for forecast in propose(sym, lookback_days=lookback_days, as_of=cutoff):
                if not dry_run:
                    save_forecast(forecast)
                made.append(forecast)
        title = "Forecast de xuat (chua luu)" if dry_run else "Forecast vua tao va luu"
        return format_forecast_list(made, title)


@mcp.tool(
    title="Kiem tra forecast da dat",
    description=(
        "Doi chieu moi forecast da luu voi du lieu gia moi nhat va bao cac thay doi trang thai: "
        "cho kich hoat -> da kich hoat -> dat muc tieu / bi phu dinh / het han. "
        "Day la buoc 'thong bao' — chay khi nguoi dung goi. "
        "symbols: bo trong = tat ca. include_closed=true xem ca forecast da dong. "
        + _AS_OF_DOC +
        " Khi co as_of: chi xet forecast tao truoc moc, replay den moc, va KHONG ghi de "
        "trang thai that tren dia."
    ),
)
def check_forecasts(symbols: str = "", include_closed: bool = False,
                    as_of: str = "") -> str:
    with _quiet():
        cutoff, bad_date = _cutoff(as_of)
        if bad_date:
            return bad_date
        wanted = resolve_universe(symbols) if symbols.strip() else None
        result = check_all(wanted, open_only=not include_closed, as_of=cutoff)
        return format_forecast_check(result, include_closed=include_closed)


@mcp.tool(
    title="Cap nhat gia moi nhat tu FireAnt",
    description=(
        "Tai gia moi nhat tu FireAnt API ve thu muc data/ roi xoa cache doc, nen cac tool khac "
        "thay du lieu moi ngay lap tuc (khong can khoi dong lai server). "
        "mode: 'latest' = chi thang hien tai (nhanh nhat, dung hang ngay); "
        "'recent' = thang nay + thang truoc (an toan khi vua sang thang); "
        "'quarter' = 4 thang gan nhat; 'full' = toan bo lich su tu 2010 (rat cham). "
        "universe: 'vn30' | 'largecap' | 'midcap' | 'all' | 'disk' (mac dinh: moi ma dang co "
        "du lieu tren o dia) hoac danh sach ma ngan cach dau phay. "
        "Can token FireAnt trong bien moi truong FIREANT_BEARER_TOKEN hoac file access_token.txt. "
        "Phan hoi rong tu API se KHONG ghi de du lieu da co."
    ),
)
def update_prices_tool(
    universe: str = "disk",
    mode: str = "latest",
    months: int = 0,
    max_workers: int = 6,
) -> str:
    with _quiet():
        if mode not in MODES:
            return f"Mode khong hop le: {mode!r}. Chon: {', '.join(MODES)}"
        result = update_prices(
            universe=universe, mode=mode,
            months=months if months > 0 else None,
            max_workers=max(1, min(max_workers, 12)),
        )
        return format_update(result)


@mcp.tool(
    title="Huong dan su dung plugin",
    description=(
        "Bang tra cuu toan bo command va tool cua plugin vn-ta: dung cai nao cho viec gi, "
        "cac nhom ma / luat quet / profile nguong co san, va nhip dung hang ngay. "
        "Goi khi nguoi dung hoi 'plugin nay lam duoc gi', 'co nhung command nao', "
        "'chay gi bay gio', hoac khi ho khong biet bat dau tu dau."
    ),
)
def usage_guide() -> str:
    return format_usage_guide()


@mcp.tool(
    title="Cac nhom ma va profile co san",
    description="Liet ke ten nhom ma (universe) va cac profile nguong RSI/ADX co the dung.",
)
def list_presets() -> str:
    lines = ["## Nhom ma (universe)", ""]
    for key, filename in GROUP_FILES.items():
        lines.append(f"- `{key}` — tu `stock_list/{filename}`")
    lines += ["- `disk` — tat ca ma co du lieu tren o dia", "",
              "## Profile nguong", ""]
    for name, cfg in PROFILES.items():
        lines.append(
            f"- `{name}` — RSI qua ban {cfg.rsi.oversold:.0f} / qua mua {cfg.rsi.overbought:.0f}, "
            f"ADX dong luc >= {cfg.adx.trend_threshold:.0f}"
        )
    lines += ["", "## Luat quet", ""]
    for rule in RULES:
        lines.append(f"- `{rule}`")
    lines += ["", "## Tieu chi xep hang (`rank_list`)", ""]
    for key, crit in ranking_mod.CRITERIA.items():
        lines.append(f"- `{key}` — {crit.label}")
    return "\n".join(lines)


@mcp.tool(
    title="Nap giao dich noi bo + lich su kien tu FireAnt",
    description=(
        "Tai giao dich cua co dong lon / nguoi noi bo (dang ky va thuc hien, co nhan Mua/Ban) "
        "va cac moc su kien (BCTC, co tuc kem ngay GDKHQ) ve kho news/index.db. "
        "universe: 'vn30' | 'largecap' | 'midcap' | 'all' | 'disk' hoac danh sach ma ngan cach dau phay. "
        "Chay lai nhieu lan khong nhan doi ban ghi. Can token FireAnt."
    ),
)
def update_news(universe: str = "vn30", marks_start: str = "2015-01-01") -> str:
    with _quiet():
        symbols = resolve_universe(universe)
        if not symbols:
            return f"Khong co ma nao trong nhom {universe!r}."
        result = news_ingest.ingest(symbols, marks_start=marks_start)
        lines = [
            f"## Nap tin tuc & su kien — {len(symbols)} ma",
            "",
            f"- Giao dich noi bo / co dong lon: **{result.total_transactions}**",
            f"- Moc su kien (BCTC, co tuc): **{result.total_marks}**",
        ]
        if result.failed:
            lines += ["", f"⚠️ {len(result.failed)} ma loi:"]
            lines += [f"  - {f.symbol}: {f.error}" for f in result.failed[:10]]
        return "\n".join(lines)


@mcp.tool(
    title="Giao dich noi bo / co dong lon cua mot ma",
    description=(
        "Liet ke giao dich cua nguoi noi bo (co chuc vu) va co dong lon: chieu Mua/Ban, "
        "khoi luong DANG KY va khoi luong THUC HIEN, kem ty le thuc hien. "
        "Ty le nay la phan co thong tin nhat: dang ky mua nhieu ma khong mua duoc thuong la do "
        "gia chay vuot muc san sang tra, chu khong phai doi y. "
        "Doc kho news/index.db — chay update_news truoc neu kho rong. " + _AS_OF_DOC
    ),
)
def news_transactions(symbol: str, limit: int = 15, as_of: str = "") -> str:
    with _quiet():
        cutoff, err = _cutoff(as_of)
        if err:
            return err
        sym = symbol.strip().upper()
        with news_store.connect() as conn:
            rows = news_store.load_holder_transactions(
                conn, sym, as_of=cutoff.strftime("%Y-%m-%d") if cutoff else None)
        return news_format.format_transactions(rows, sym, limit=max(1, limit))


@mcp.tool(
    title="Do phan ung gia quanh giao dich noi bo",
    description=(
        "Event study: do abnormal return quanh cac giao dich noi bo gan nhat cua mot ma, "
        "so voi VNINDEX. Tra ve ba cua so TACH ROI — CAR truoc su kien (ro ri tin), "
        "phan ung tuc thi (t0..t+1), va troi sau su kien (t+1..t+10) — vi gop lai se xoa "
        "dung thu dang doc: mot ma chay het truoc ngay cong bo trong y het mot ma khong phan ung. "
        "Kem volume so voi trung binh 20 phien va canh bao neu co phien tran/san. " + _AS_OF_DOC
    ),
)
def news_impact(symbol: str, limit: int = 3, insiders_only: bool = True,
                as_of: str = "") -> str:
    with _quiet():
        cutoff, err = _cutoff(as_of)
        if err:
            return err
        sym = symbol.strip().upper()
        with news_store.connect() as conn:
            rows = news_store.load_holder_transactions(
                conn, sym, as_of=cutoff.strftime("%Y-%m-%d") if cutoff else None)
        if insiders_only:
            rows = [r for r in rows if r.get("position")]
        rows = [r for r in rows if r.get("start_date") or r.get("execution_date")]
        if not rows:
            return (f"Khong co giao dich nao cua {sym} de do. "
                    "Chay update_news truoc, hoac dat insiders_only=false.")
        items = []
        for r in rows[:max(1, limit)]:
            t0 = r.get("start_date") or r.get("execution_date")
            label = (f"{sym} — {r['name']} ({r.get('position') or 'co dong lon'}) "
                     f"{DIRECTION_VN.get(r['direction'], '?')} "
                     f"{(r.get('execution_volume') or 0):,.0f} cp")
            items.append((label, news_reaction.measure(sym, t0)))
        return news_format.format_impact(sym, items)


@mcp.tool(
    title="Base rate — loai giao dich nay thuong lam gia chay bao nhieu",
    description=(
        "Chay event study tren MOI giao dich cua ca ro roi gom theo nhom "
        "(noi bo / co dong lon x mua / ban x thuc hien du / mot phan / khong thuc hien), "
        "tra ve phan phoi (trung vi + tu phan vi + ty le duong), khong phai trung binh. "
        "Nhom duoi 20 quan sat KHONG duoc phat bieu so — chi bao la thieu du lieu. "
        "Su kien co phien tran/san bi loai vi phep do o do bi cat cut. "
        "Cham: moi giao dich la mot lan nap chuoi gia."
    ),
)
def news_stats(universe: str = "vn30", exclude_limit: bool = True) -> str:
    with _quiet():
        symbols = resolve_universe(universe)
        if not symbols:
            return f"Khong co ma nao trong nhom {universe!r}."
        buckets, raw = news_stats_mod.collect(
            symbols, exclude_limit=exclude_limit)
        header = (f"_Tren {len(symbols)} ma, {len(raw)} su kien do duoc._\n\n")
        return header + news_stats_mod.format_stats(buckets)


@mcp.tool(
    title="Thi truong phai sinh VN30 hom nay",
    description=(
        "Anh chup thi truong phai sinh: basis (chenh lech VN30F1M - VN30) kem HAI phan vi "
        "(toan bo lich su, va chi tren nhung phien CUNG QUANG DUONG toi dao han - basis buoc "
        "phai hoi tu ve 0 nen doc mot con so basis ma khong kem so phien con lai la doc sai), "
        "cau truc ky han F2M-F1M, thanh khoan hop dong, ty le gia tri danh nghia phai sinh / "
        "gia tri khop lenh ro VN30, tu doanh va khoi ngoai TREN HOP DONG, va dem nguoc toi "
        "phien dao han (thu Nam thu ba hang thang). Kem phan giai thich anh huong lan toi co "
        "phieu di qua duong nao. Moc do la VN30, KHONG phai VNINDEX. " + _AS_OF_DOC
    ),
)
def futures_snapshot(as_of: str = "", mechanism: bool = True) -> str:
    with _quiet():
        cutoff, err = _cutoff(as_of)
        if err:
            return err
        snap = futures_mod.build_futures_snapshot(cutoff)
        return format_futures(snap, mechanism=mechanism)


@mcp.tool(
    title="Ma nao chiu anh huong cua dong tien phai sinh",
    description=(
        "Voi tung ma: co nam trong ro VN30 khong (duong lan truyen CO HOC - lenh arbitrage roi "
        "thang vao 30 ma do), beta va R2 so voi VN30 (duong GIAN TIEP cho ma ngoai ro), ty trong "
        "THANH KHOAN trong ro (khong phai trong so chi so - du lieu von hoa free-float khong co "
        "trong data/), va hanh vi phien dao han do tren ~5 nam (bien do va volume phien dao han "
        "chia cho phien thuong). Bon thanh phan in rieng canh diem tong; diem chi de SAP THU TU. "
        "symbols: mot ma, danh sach ngan cach dau phay, hoac nhom 'vn30'/'largecap'/'midcap'/'all'. "
        + _AS_OF_DOC
    ),
)
def futures_exposure(symbols: str = "vn30", limit: int = 40, as_of: str = "") -> str:
    with _quiet():
        cutoff, err = _cutoff(as_of)
        if err:
            return err
        rows = futures_mod.basket_exposure(symbols, cutoff)
        if not rows:
            return (f"Khong co ma nao trong {symbols!r} co du lieu. "
                    "Dung list_symbols de xem cac ma co san.")
        return format_futures_exposure(
            rows, title=f"Muc chiu anh huong cua dong tien phai sinh - {symbols}",
            limit=max(1, limit))


@mcp.tool(
    title="Base rate - sau moi muc basis thi VN30 di dau",
    description=(
        "Chia toan bo lich su phai sinh (tu 2017-08) thanh 5 nhom theo basis, roi do loi suat "
        "VN30 trong 1/3/5 phien TIEP THEO cua tung nhom: trung vi va ty le phien tang. "
        "Day la phan bat cau chuyen 'basis chiet khau la diem xau' phai tra loi bang so. "
        "Luu y khi doc: cac quan sat CHONG LAN nhau nen n khong phai so quan sat doc lap, "
        "va nen chung duong o moi nhom vi VN30 tang trong giai doan lay mau - cai dang doc la "
        "chenh lech GIUA cac nhom. " + _AS_OF_DOC
    ),
)
def futures_stats(as_of: str = "") -> str:
    with _quiet():
        cutoff, err = _cutoff(as_of)
        if err:
            return err
        buckets, note = futures_mod.basis_forward_stats(cutoff)
        return format_futures_stats(buckets, note)


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()
