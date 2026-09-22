"""Phái sinh VN30: lịch đáo hạn, đường nối hợp đồng, basis, phơi nhiễm.

Bốn chỗ dễ sai nhất của tầng này, và mỗi chỗ một bài test:

* ngày đáo hạn là **thứ Năm thứ ba**, không phải "thứ Năm cuối" hay "ngày 15";
* thứ Năm đó rơi vào ngày nghỉ thì phiên cuối lùi về phiên **liền trước**;
* ``VN30F1M`` là chuỗi **nối**, nên % thay đổi qua đường nối là số giả;
* chỉ số và hợp đồng **không được** lọt vào rổ quét/xếp hạng.
"""
import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock

from src.ta import futures as fut
from src.ta import loader
from src.ta import ranking
from src.ta.format import format_futures_brief


def _quote(symbol: str, day: str, close: float, volume: float = 1000.0,
           value: float = 1e9) -> dict:
    """Một dòng historical-quote của FireAnt, đủ trường cho ``record_from_json``."""
    return {
        "date": f"{day}T00:00:00", "symbol": symbol,
        "priceHigh": close + 1, "priceLow": close - 1, "priceOpen": close,
        "priceAverage": close, "priceClose": close, "priceBasic": close,
        "totalVolume": volume, "dealVolume": volume, "putthroughVolume": 0.0,
        "totalValue": value, "putthroughValue": 0.0,
        "buyForeignQuantity": 0.0, "buyForeignValue": 0.0,
        "sellForeignQuantity": 0.0, "sellForeignValue": 0.0,
        "buyCount": 0.0, "buyQuantity": 0.0, "sellCount": 0.0, "sellQuantity": 0.0,
        "adjRatio": 1.0, "currentForeignRoom": 0.0, "unit": 1.0,
        "propTradingNetDealValue": 0.0, "propTradingNetPTValue": 0.0,
        "propTradingNetValue": 0.0,
    }


class ExpiryCalendarTest(unittest.TestCase):
    """Thứ Năm thứ ba — luật niêm yết, không phải ước lượng."""

    def test_third_thursday_of_known_months(self):
        self.assertEqual(fut.expiry_date(2026, 9), date(2026, 9, 17))
        self.assertEqual(fut.expiry_date(2026, 8), date(2026, 8, 20))
        self.assertEqual(fut.expiry_date(2026, 7), date(2026, 7, 16))
        self.assertEqual(fut.expiry_date(2026, 6), date(2026, 6, 18))

    def test_month_starting_on_thursday_still_takes_the_third_one(self):
        # 01/01/2026 rơi vào thứ Năm: thứ Năm thứ ba là 15/01, không phải 22/01.
        self.assertEqual(date(2026, 1, 1).weekday(), 3)
        self.assertEqual(fut.expiry_date(2026, 1), date(2026, 1, 15))

    def test_every_expiry_is_a_thursday(self):
        for year in range(2018, 2031):
            for month in range(1, 13):
                self.assertEqual(fut.expiry_date(year, month).weekday(), 3)

    def test_expiry_session_falls_back_when_the_thursday_is_a_holiday(self):
        """Nghỉ lễ đúng thứ Năm thứ ba → phiên cuối là phiên liền trước.

        Không có bước lùi này thì cả tháng đó mất mốc đáo hạn: đường nối hợp
        đồng không được đánh dấu, và % thay đổi giả tạo lọt thẳng vào thống kê.
        """
        sessions = [date(2026, 9, d) for d in (14, 15, 16, 18)]   # thiếu 17 (thứ Năm)
        idx = fut.expiry_sessions(sessions)
        self.assertEqual(idx, [2])
        self.assertEqual(sessions[idx[0]], date(2026, 9, 16))

    def test_roll_is_the_session_after_expiry_not_expiry_itself(self):
        sessions = [date(2026, 9, d) for d in (15, 16, 17, 18, 21)]
        self.assertEqual(fut.expiry_sessions(sessions), [2])       # 17/09
        self.assertEqual(fut.roll_indices(sessions), {3})          # 18/09

    def test_no_roll_marked_past_the_end_of_the_series(self):
        """Phiên đáo hạn là phiên cuối cùng có dữ liệu → chưa có đường nối."""
        sessions = [date(2026, 9, d) for d in (15, 16, 17)]
        self.assertEqual(fut.roll_indices(sessions), set())


class _SyntheticData(unittest.TestCase):
    """Nền chung: một thư mục ``data/`` giả, tự dọn sau mỗi test."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name)
        self._patch = mock.patch.object(loader, "DATA_DIR", self.data)
        self._patch.start()
        loader.clear_cache()
        fut._vn30_liquidity.cache_clear()

    def tearDown(self):
        self._patch.stop()
        loader.clear_cache()
        fut._vn30_liquidity.cache_clear()
        self._tmp.cleanup()

    def write(self, symbol: str, rows: list) -> None:
        by_month: dict = {}
        for row in rows:
            key = row["date"][:7]
            by_month.setdefault(key, []).append(row)
        for key, items in by_month.items():
            year = key[:4]
            path = self.data / symbol / year / f"{key}-01.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(items), encoding="utf-8")
        loader.clear_cache()


class BasisSeriesTest(_SyntheticData):
    def _write_pair(self):
        """Tháng 9/2026, hợp đồng luôn cao hơn chỉ số 5 điểm."""
        days = ["2026-09-%02d" % d for d in
                (14, 15, 16, 17, 18, 21, 22)]                      # 17/09 = đáo hạn
        self.write("VN30", [_quote("VN30", d, 1000.0 + i) for i, d in enumerate(days)])
        self.write("VN30F1M",
                   [_quote("VN30F1M", d, 1005.0 + i) for i, d in enumerate(days)])
        return days

    def test_basis_is_front_minus_spot_on_the_same_session(self):
        self._write_pair()
        points = fut.basis_series(as_of=datetime(2026, 9, 22), lookback_days=60)
        self.assertEqual(len(points), 7)
        for p in points:
            self.assertAlmostEqual(p.basis, 5.0, places=6)
            self.assertAlmostEqual(p.basis_pct, 5.0 / p.spot * 100, places=3)

    def test_sessions_to_expiry_counts_down_and_hits_zero(self):
        self._write_pair()
        points = fut.basis_series(as_of=datetime(2026, 9, 22), lookback_days=60)
        by_date = {p.date: p for p in points}
        self.assertEqual(by_date["2026-09-14"].sessions_to_expiry, 3)
        self.assertEqual(by_date["2026-09-17"].sessions_to_expiry, 0)
        self.assertTrue(by_date["2026-09-17"].is_expiry)

    def test_the_session_after_expiry_is_flagged_as_a_seam(self):
        self._write_pair()
        points = fut.basis_series(as_of=datetime(2026, 9, 22), lookback_days=60)
        rolls = [p.date for p in points if p.is_roll]
        self.assertEqual(rolls, ["2026-09-18"])

    def test_sessions_left_for_the_newest_bar_is_flagged_as_an_estimate(self):
        """Kỳ đáo hạn sau chưa xảy ra nên chỉ đếm được theo lịch — phải nói ra.

        Trộn một con số đếm chính xác với một con số ước lượng mà không gắn cờ
        là để người đọc tin nhầm mức chắc chắn.
        """
        days = ["2026-09-%02d" % d for d in (21, 22, 23)]          # đã qua 17/09
        self.write("VN30", [_quote("VN30", d, 1000.0) for d in days])
        self.write("VN30F1M", [_quote("VN30F1M", d, 1002.0) for d in days])
        points = fut.basis_series(as_of=datetime(2026, 9, 23), lookback_days=60)
        self.assertTrue(points[-1].estimated_sessions)
        # 24, 25, 28, 29, 30/09 rồi 01…15/10 = 16 ngày làm việc tới 15/10/2026.
        self.assertEqual(points[-1].sessions_to_expiry, 16)

    def test_missing_futures_data_says_so_instead_of_crashing(self):
        self.write("VN30", [_quote("VN30", "2026-09-14", 1000.0)])
        snap = fut.build_futures_snapshot(as_of=datetime(2026, 9, 14))
        self.assertEqual(snap.bars, 0)
        self.assertTrue(snap.warnings)
        self.assertIn("VN30F1M", snap.warnings[0])


class RollContaminationTest(_SyntheticData):
    """Đường nối hợp đồng không được đọc thành một cú chạy giá."""

    def test_percent_change_is_blank_on_a_roll_session(self):
        days = ["2026-09-%02d" % d for d in (16, 17, 18)]          # 18/09 = phiên nối
        self.write("VN30", [_quote("VN30", d, 1000.0) for d in days])
        # Hợp đồng nhảy 1005 -> 1080 đúng ở đường nối: đó là đổi hợp đồng, không
        # phải giá chạy 7,5%.
        self.write("VN30F1M", [
            _quote("VN30F1M", "2026-09-16", 1005.0),
            _quote("VN30F1M", "2026-09-17", 1005.0),
            _quote("VN30F1M", "2026-09-18", 1080.0),
        ])
        snap = fut.build_futures_snapshot(as_of=datetime(2026, 9, 18))
        self.assertTrue(snap.front["roll_session"])
        self.assertIsNone(snap.front["change_pct"])
        self.assertTrue(any("nối hợp đồng" in w for w in snap.warnings))

    def test_percent_change_is_reported_on_an_ordinary_session(self):
        days = ["2026-09-%02d" % d for d in (14, 15)]
        self.write("VN30", [_quote("VN30", d, 1000.0) for d in days])
        self.write("VN30F1M", [
            _quote("VN30F1M", "2026-09-14", 1000.0),
            _quote("VN30F1M", "2026-09-15", 1010.0),
        ])
        snap = fut.build_futures_snapshot(as_of=datetime(2026, 9, 15))
        self.assertFalse(snap.front["roll_session"])
        self.assertAlmostEqual(snap.front["change_pct"], 1.0, places=2)


class ExposureTest(_SyntheticData):
    def test_beta_is_withheld_when_the_sample_is_too_short(self):
        """Beta dựng từ 10 phiên là một con số, nhưng không phải một phép đo."""
        days = ["2026-09-%02d" % d for d in range(1, 11)]
        self.write("VN30", [_quote("VN30", d, 1000.0 + i) for i, d in enumerate(days)])
        self.write("TST", [_quote("TST", d, 20.0 + i * 0.1) for i, d in enumerate(days)])
        exp = fut.symbol_exposure("TST", as_of=datetime(2026, 9, 10))
        self.assertIsNone(exp.beta)
        self.assertIn("cần ≥", exp.note)

    def test_beta_recovers_a_known_slope(self):
        """Mã dựng để đi gấp đôi chỉ số → beta phải ra ~2."""
        rows_spot, rows_sym = [], []
        spot, sym = 1000.0, 100.0
        day = date(2025, 1, 1)
        steps = [0.01, -0.005, 0.008, -0.002] * 30
        for step in steps:
            while day.weekday() >= 5:
                day = date.fromordinal(day.toordinal() + 1)
            iso = day.isoformat()
            rows_spot.append(_quote("VN30", iso, spot))
            rows_sym.append(_quote("TST", iso, sym))
            spot *= 1 + step
            sym *= 1 + 2 * step
            day = date.fromordinal(day.toordinal() + 1)
        self.write("VN30", rows_spot)
        self.write("TST", rows_sym)

        exp = fut.symbol_exposure("TST", as_of=datetime(2025, 12, 31))
        self.assertIsNotNone(exp.beta)
        self.assertAlmostEqual(exp.beta, 2.0, delta=0.05)
        self.assertGreater(exp.r2, 0.95)
        self.assertFalse(exp.in_vn30)          # không có file nhóm trong data giả

    def test_unknown_symbol_reports_missing_data(self):
        self.write("VN30", [_quote("VN30", "2026-09-14", 1000.0)])
        exp = fut.symbol_exposure("NOPE", as_of=datetime(2026, 9, 14))
        self.assertEqual(exp.score, 0.0)
        self.assertIn("không có dữ liệu", exp.note)


class ThinSampleTest(_SyntheticData):
    def test_forward_stats_refuse_to_speak_on_a_short_history(self):
        days = ["2026-09-%02d" % d for d in range(1, 11)]
        self.write("VN30", [_quote("VN30", d, 1000.0) for d in days])
        self.write("VN30F1M", [_quote("VN30F1M", d, 1001.0) for d in days])
        buckets, note = fut.basis_forward_stats(as_of=datetime(2026, 9, 10))
        self.assertEqual(buckets, [])
        self.assertIn("chưa đủ", note)


class UniverseIsolationTest(unittest.TestCase):
    """Chỉ số và hợp đồng không được lọt vào rổ quét/xếp hạng.

    Đây là bài test đắt nhất trong file: nó chạy trên ``data/`` thật, vì cái
    đang bảo vệ là *cấu hình thật* — registry và các file nhóm — chứ không phải
    một nhánh code.
    """

    def test_registries_are_disjoint_and_non_empty(self):
        marks = set(loader.benchmark_symbols())
        derivs = set(loader.derivative_symbols())
        self.assertIn("VN30", marks)
        self.assertIn("VNINDEX", marks)
        self.assertIn("VN30F1M", derivs)
        self.assertFalse(marks & derivs)

    def test_no_group_ever_hands_back_an_index_or_a_contract(self):
        forbidden = loader.non_tradable_symbols()
        for group in (None, "disk", "all", "vn30", "largecap", "midcap"):
            with self.subTest(group=group):
                self.assertFalse(set(loader.resolve_universe(group)) & forbidden)

    def test_naming_one_explicitly_still_works(self):
        """Hỏi đích danh là một câu hỏi khác với hỏi cả rổ."""
        self.assertEqual(loader.resolve_universe("VNINDEX"), ["VNINDEX"])
        self.assertIn("VN30F1M", loader.resolve_universe("futures"))
        self.assertIn("VN30", loader.resolve_universe("benchmarks"))

    def test_futures_group_holds_only_derivatives(self):
        self.assertTrue(
            set(loader.resolve_universe("futures")) <= set(loader.derivative_symbols()))


# ---------------------------------------------------------------------------
# Nối vào /report và /rank
# ---------------------------------------------------------------------------
def _row(symbol="TEST", **kw) -> ranking.SymbolRank:
    """Một dòng xếp hạng tối thiểu — dựng bằng tay, không đọc đĩa.

    Cố ý không mượn helper của ``test_ta_ranking``: cái đang kiểm ở đây là vòng
    JSON của **trục phái sinh**, nó phải đứng vững kể cả khi hai trục kia đổi
    hình dạng.
    """
    body = dict(
        symbol=symbol, as_of="2026-08-25", bars=300, close=100.0, change_pct=1.0,
        change_5d=2.0, change_20d=10.0, rsi=55.0, rsi_state="neutral", rvol=1.2,
        atr_pct=2.0, vs_ema20=5.0, vs_ema50=11.0, box_position=50.0,
        box_top=105.0, box_bottom=95.0,
        trend=ranking.TrendRank(
            side=ranking.UP, score=50.0, ema_side=ranking.UP, ema_label="EMA",
            structure_side=ranking.UP, structure_label="cấu trúc", conflict=False,
            adx=30.0, adx_direction="up", adx_regime="strong",
            components={}, reasons=["vì sao"]),
        pattern=ranking.PatternRank(
            source=ranking.FORMATION_SRC, name="Hai đáy", bias="bullish",
            state=ranking.PARTIAL, confidence=60.0, trigger=100.0, target=110.0,
            invalidation=90.0, note="ghi chú"),
        brief=["dòng lý giải"],
    )
    body.update(kw)
    return ranking.SymbolRank(**body)


def _exposure(symbol="TEST", **kw) -> fut.SymbolExposure:
    body = dict(symbol=symbol, in_vn30=True, beta=1.30, r2=0.42, n_bars=120,
                rs_20=3.5, rs_60=-1.2, liquidity_share_pct=6.4,
                expiry_move_ratio=1.15, expiry_vol_ratio=1.08, n_expiries=60,
                score=71.0, channel="Cơ học", note="")
    body.update(kw)
    return fut.SymbolExposure(**body)


class RankingIntegrationTest(unittest.TestCase):
    """Trục phái sinh phải đi trọn vòng JSON, và phải **đứng riêng**.

    Bảng xếp hạng được đọc lại từ file chứ không dựng lại (``rank_list``), nên
    một trường không round-trip được sẽ im lặng biến mất ở đúng lúc người dùng
    xoay bảng — không lỗi, chỉ là cột trống.
    """

    def test_exposure_survives_the_json_round_trip(self):
        row = _row(symbol="ABC", futures=_exposure("ABC"))
        back = ranking.SymbolRank.from_dict(row.to_dict())
        self.assertIsNotNone(back.futures)
        self.assertEqual(back.futures.beta, 1.30)
        self.assertEqual(back.futures.liquidity_share_pct, 6.4)
        self.assertTrue(back.futures.in_vn30)
        self.assertEqual(back.futures_score, 71.0)

    def test_a_row_without_exposure_round_trips_as_none(self):
        """Mã chưa đo được vẫn phải đi qua được — cột trống, không phải nổ."""
        back = ranking.SymbolRank.from_dict(_row(symbol="XYZ").to_dict())
        self.assertIsNone(back.futures)
        self.assertIsNone(back.futures_score)
        self.assertIsNone(back.beta_vn30)

    def test_market_context_survives_the_json_round_trip(self):
        """`rank_list` đọc lại bảng cũ phải nói đúng tư thế phái sinh *hôm đó*.

        Nếu ảnh chụp này không đi theo file thì lần xoay bảng sau sẽ ghép bối
        cảnh của hôm nay vào một bảng của tuần trước.
        """
        snap = fut.FuturesSnapshot(
            as_of="2026-08-20", bars=500,
            basis={"points": -8.0, "pct": -0.42},
            expiry={"sessions_left": 0, "date": "2026-08-20"},
        )
        board = ranking.Ranking(as_of="2026-08-20", generated="x", universe="vn30",
                                futures=snap)
        back = ranking.Ranking.from_dict(board.to_dict())
        self.assertEqual(back.futures.as_of, "2026-08-20")
        self.assertEqual(back.futures.basis["points"], -8.0)
        self.assertEqual(back.futures.expiry["sessions_left"], 0)

    def test_exposure_never_leaks_into_the_other_two_axes(self):
        """Ba cột, ba câu hỏi. Cộng chúng vào nhau là xoá đúng chỗ khác nhau.

        Một mã cường độ +50 ngoài rổ VN30 và một mã cường độ +50 beta 1,6 nằm
        trong rổ là hai tình huống khác hẳn — nhưng *cường độ* của chúng vẫn
        phải bằng nhau, vì đó là câu trả lời cho một câu hỏi khác.
        """
        bare = _row(symbol="A")
        loaded = _row(symbol="B", futures=_exposure("B", score=95.0, beta=1.9))
        self.assertEqual(bare.trend.score, loaded.trend.score)
        self.assertEqual(bare.pattern.confidence, loaded.pattern.confidence)
        self.assertIsNone(bare.futures_score)
        self.assertEqual(loaded.futures_score, 95.0)

    def test_criterion_answers_to_vietnamese(self):
        for name in ("futures", "phái sinh", "phơi nhiễm", "ảnh hưởng phái sinh"):
            with self.subTest(name=name):
                self.assertEqual(ranking.resolve_criterion(name).key, "futures")
        self.assertEqual(ranking.resolve_criterion("beta").key, "beta")
        self.assertEqual(ranking.resolve_criterion("beta VN30").key, "beta")

    def test_sorting_by_exposure_puts_unmeasured_symbols_last(self):
        """Mã không đo được không phải mã điểm 0 — nó phải rơi xuống cuối bảng."""
        rows = [
            _row(symbol="LOW", futures=_exposure("LOW", score=12.0)),
            _row(symbol="NONE"),
            _row(symbol="HIGH", futures=_exposure("HIGH", score=88.0)),
        ]
        ordered, crit = ranking.sort_rows(rows, "phái sinh", True)
        self.assertEqual([r.symbol for r in ordered], ["HIGH", "LOW", "NONE"])
        self.assertEqual(crit.key, "futures")


class BriefRenderingTest(unittest.TestCase):
    """Khối bối cảnh dùng chung cho `/report`, `/rank` và hồ sơ một mã."""

    def _snap(self, as_of="2026-09-04") -> fut.FuturesSnapshot:
        return fut.FuturesSnapshot(
            as_of=as_of, bars=500,
            spot={"close": 1900.0},
            front={"symbol": "VN30F1M", "close": 1898.0, "contracts": 200000,
                   "rvol": 1.1},
            basis={"points": -2.0, "pct": -0.105, "percentile_same_maturity": 12.0},
            expiry={"date": "2026-09-17", "sessions_left": 9, "estimated": True},
            flow={"leverage_ratio": 3.8, "prop_net_5d_bn": -120.0,
                  "foreign_net_contracts_5d": -2400},
        )

    def test_heading_carries_the_futures_session(self):
        lines = format_futures_brief(self._snap(), None)
        self.assertIn("2026-09-04", lines[0])

    def test_a_date_gap_against_the_rest_of_the_report_is_stated(self):
        """Giá và phái sinh nạp bằng hai lượt khác nhau nên có thể lệch phiên.

        Im lặng ở đây là để người đọc ghép tư thế phái sinh của hôm nay vào một
        bảng giá của tuần trước mà không hay biết.
        """
        lines = format_futures_brief(self._snap(), None, ref_date="2026-08-28")
        self.assertTrue(any("2026-08-28" in ln and "⚠️" in ln for ln in lines))

    def test_no_warning_when_both_sides_stop_on_the_same_session(self):
        lines = format_futures_brief(self._snap(), None, ref_date="2026-09-04")
        self.assertFalse(any("⚠️" in ln for ln in lines))

    def test_missing_futures_data_renders_nothing_at_all(self):
        """Chưa nạp VN30/VN30F1M thì báo cáo phải dựng được y hệt như trước."""
        self.assertEqual(format_futures_brief(None, None), [])
        self.assertEqual(
            format_futures_brief(fut.FuturesSnapshot(as_of="-", bars=0), None), [])


if __name__ == "__main__":
    unittest.main()
