"""Ranking: the two scores, the ordering, and the round trip through JSON.

The scoring tests build snapshots and structures by hand rather than loading a
symbol, so a change in the data on disk can never turn a scoring test green or
red for the wrong reason.
"""
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.ta import ranking as R
from src.ta.boxes import BREAKDOWN_CONFIRMED, BREAKOUT_UP_CONFIRMED, BREAKOUT_UP_WEAK, INSIDE, Box
from src.ta.confluence import CONFLICT as TIER_CONFLICT
from src.ta.confluence import FULL as TIER_FULL
from src.ta.confluence import PARTIAL as TIER_PARTIAL
from src.ta.confluence import Evidence
from src.ta.formations import BEARISH, BULLISH
from src.ta.formations import CONFIRMED as F_CONFIRMED
from src.ta.formations import FAILED as F_FAILED
from src.ta.formations import FORMING as F_FORMING
from src.ta.formations import Formation
from src.ta.format import format_rank_list, format_ranking
from src.ta.snapshot import Snapshot
from src.ta.structure import Structure
from src.ta.swings import DOWNTREND, HH, HL, LH, LL, RANGE, UPTREND
from src.ta.swings import MarketStructure, StructureEvent, SwingLabel


# ---------------------------------------------------------------------------
# fixtures — hand-built inputs, no disk access
# ---------------------------------------------------------------------------
def make_snapshot(close=100.0, ema20=95.0, ema50=90.0, ema100=85.0,
                  adx=30.0, direction="up", change_20d=10.0, atr_pct=2.0,
                  rsi=55.0) -> Snapshot:
    return Snapshot(
        symbol="TEST", as_of="2026-08-25", bars=300,
        price={"close": close, "change_pct": 1.0, "change_5d": 2.0,
               "change_20d": change_20d},
        trend={"label": "Tăng — giá trên EMA20 trên EMA50", "ema20": ema20,
               "ema50": ema50, "ema100": ema100, "vs_ema20_pct": 5.0,
               "vs_ema50_pct": 11.0},
        momentum={"rsi14": rsi, "atr14": close * atr_pct / 100, "atr_pct": atr_pct},
        volume={"rvol": 1.2},
        levels={}, rsi_zone={"state": "neutral"},
        adx={"adx": adx, "direction": direction, "regime": "strong"},
    )


def make_market(trend=UPTREND, labels=(HL, HH, HL, HH), event=None,
                bars_since=3) -> MarketStructure:
    swings = [
        SwingLabel(index=i, date="2026-08-01", price=10.0 + i, kind="high",
                   label=lbl, short={HH: "HH", LH: "LH", HL: "HL", LL: "LL"}[lbl],
                   versus=10.0)
        for i, lbl in enumerate(labels)
    ]
    return MarketStructure(trend=trend, swings=swings,
                           events=[event] if event else [],
                           bars_since_event=bars_since, label="nhãn cấu trúc")


def make_formation(state=F_CONFIRMED, bias=BULLISH, **kw) -> Formation:
    defaults = dict(
        kind="double_bottom", name="Hai đáy", bias=bias, state=state, pivots=[],
        start_index=0, start_date="2026-06-01", end_index=40, end_date="2026-08-01",
        bars=40, peak=90.0, neckline_now=100.0, neckline_slope=0.0, height=10.0,
        target=110.0, invalidation=90.0, fit_atr=0.4, shoulder_volume_ratio=1.1,
    )
    defaults.update(kw)
    return Formation(**defaults)


def make_structure(box=None, formation=None, tier=TIER_FULL, market=None,
                   pattern=None) -> Structure:
    evidence = []
    if formation is not None:
        evidence = [Evidence(formation=formation, tier=tier, mark="🟢",
                             conclusion="câu kết luận", missing=[])]
    return Structure(
        symbol="TEST", as_of="2026-08-25", bars=300, close=100.0, atr14=2.0,
        box=box, pattern=pattern, market=market or make_market(),
        formations=[formation] if formation else [], evidence=evidence,
        brief=["dòng lý giải"],
    )


def make_box(state=INSIDE, position_pct=50.0, **kw) -> Box:
    defaults = dict(
        top=105.0, bottom=95.0, start_index=0, start_date="2026-07-01",
        end_index=20, end_date="2026-08-01", bars=20, height=10.0, height_pct=10.0,
        state=state, position_pct=position_pct, target=115.0, invalidation=95.0,
        label="nhãn hộp",
    )
    defaults.update(kw)
    return Box(**defaults)


def make_row(symbol="TEST", trend_score=50.0, side=R.UP, confidence=60.0,
             state=R.PARTIAL, bias=BULLISH, **kw) -> R.SymbolRank:
    body = dict(
        symbol=symbol, as_of="2026-08-25", bars=300, close=100.0, change_pct=1.0,
        change_5d=2.0, change_20d=10.0, rsi=55.0, rsi_state="neutral", rvol=1.2,
        atr_pct=2.0, vs_ema20=5.0, vs_ema50=11.0, box_position=50.0,
        box_top=105.0, box_bottom=95.0,
        trend=R.TrendRank(side=side, score=trend_score, ema_side=side, ema_label="EMA",
                          structure_side=side, structure_label="cấu trúc",
                          conflict=False, adx=30.0, adx_direction="up",
                          adx_regime="strong", components={}, reasons=["vì sao"]),
        pattern=R.PatternRank(source=R.FORMATION_SRC, name="Hai đáy", bias=bias,
                              state=state, confidence=confidence, trigger=100.0,
                              target=110.0, invalidation=90.0, note="ghi chú"),
        brief=["dòng lý giải"],
    )
    body.update(kw)
    return R.SymbolRank(**body)


# ---------------------------------------------------------------------------
# trend axis
# ---------------------------------------------------------------------------
class TrendScoreTest(unittest.TestCase):
    def test_full_stack_uptrend_scores_near_the_ceiling(self):
        rank = R.build_trend_rank(make_snapshot(), make_structure())
        self.assertEqual(rank.side, R.UP)
        self.assertGreater(rank.score, 70)
        self.assertLessEqual(rank.score, 100)

    def test_mirror_image_downtrend_scores_the_negative(self):
        up = R.build_trend_rank(make_snapshot(), make_structure())
        down = R.build_trend_rank(
            make_snapshot(ema20=105.0, ema50=110.0, ema100=115.0,
                          direction="down", change_20d=-10.0),
            make_structure(market=make_market(DOWNTREND, (LH, LL, LH, LL))),
        )
        self.assertEqual(down.side, R.DOWN)
        self.assertAlmostEqual(down.score, -up.score, delta=0.1)

    def test_no_component_can_carry_a_rank_alone(self):
        """A screaming ADX with nothing else behind it must not read as a trend."""
        snap = make_snapshot(adx=60.0, ema20=105.0, ema50=110.0, ema100=115.0,
                             direction="up", change_20d=0.0)
        rank = R.build_trend_rank(snap, make_structure(market=make_market(RANGE, (LH, LL))))
        self.assertLess(rank.score, R.TREND_SIDE_MIN)
        self.assertEqual(rank.side, R.FLAT)

    def test_adx_below_the_no_trend_threshold_pays_almost_nothing(self):
        weak = R.build_trend_rank(make_snapshot(adx=15.0), make_structure())
        strong = R.build_trend_rank(make_snapshot(adx=40.0), make_structure())
        self.assertLess(weak.components["adx"], 5)
        self.assertGreater(strong.components["adx"], 20)

    def test_move_is_measured_in_atr_not_percent(self):
        """Same 10% move is a big deal on a quiet stock, routine on a wild one."""
        quiet = R.build_trend_rank(make_snapshot(atr_pct=1.0), make_structure())
        wild = R.build_trend_rank(make_snapshot(atr_pct=5.0), make_structure())
        self.assertGreater(quiet.components["momentum"], wild.components["momentum"])

    def test_disagreement_between_ema_and_structure_is_flagged_not_averaged(self):
        snap = make_snapshot()                       # EMA stack says up
        structure = make_structure(market=make_market(DOWNTREND, (LH, LL, LH, LL)))
        rank = R.build_trend_rank(snap, structure)
        self.assertTrue(rank.conflict)
        self.assertEqual(rank.ema_side, R.UP)
        self.assertEqual(rank.structure_side, R.DOWN)

    def test_choch_votes_harder_than_bos(self):
        """A BOS restates the trend label; a CHoCH is the first crack in it."""
        bos = StructureEvent(kind="bos", direction="down", index=50, date="2026-08-01",
                             level=95.0, close=94.0)
        choch = StructureEvent(kind="choch", direction="down", index=50,
                               date="2026-08-01", level=95.0, close=94.0)
        with_bos = R.build_trend_rank(
            make_snapshot(), make_structure(market=make_market(event=bos)))
        with_choch = R.build_trend_rank(
            make_snapshot(), make_structure(market=make_market(event=choch)))
        self.assertLess(with_choch.score, with_bos.score)

    def test_a_stale_break_counts_half(self):
        event = StructureEvent(kind="choch", direction="down", index=1, date="2026-01-01",
                               level=95.0, close=94.0)
        fresh = R.build_trend_rank(
            make_snapshot(), make_structure(market=make_market(event=event, bars_since=2)))
        stale = R.build_trend_rank(
            make_snapshot(), make_structure(market=make_market(event=event, bars_since=60)))
        self.assertGreater(stale.score, fresh.score)

    def test_reasons_name_every_component(self):
        rank = R.build_trend_rank(make_snapshot(), make_structure())
        self.assertEqual(len(rank.reasons), 4)
        self.assertIn("ADX", rank.note)
        self.assertIn("EMA", rank.note)
        self.assertIn("ATR", rank.note)


# ---------------------------------------------------------------------------
# pattern axis
# ---------------------------------------------------------------------------
class PatternConfidenceTest(unittest.TestCase):
    def test_confirmed_with_full_confluence_is_the_top_state(self):
        rank = R.build_pattern_rank(
            make_structure(formation=make_formation(), tier=TIER_FULL))
        self.assertEqual(rank.state, R.CONFIRMED)
        self.assertGreater(rank.confidence, 80)

    def test_the_same_break_missing_volume_drops_a_state(self):
        full = R.build_pattern_rank(
            make_structure(formation=make_formation(), tier=TIER_FULL))
        partial = R.build_pattern_rank(
            make_structure(formation=make_formation(), tier=TIER_PARTIAL))
        self.assertEqual(partial.state, R.PARTIAL)
        self.assertLess(partial.confidence, full.confidence)

    def test_forming_reads_as_chua_xac_nhan(self):
        rank = R.build_pattern_rank(
            make_structure(formation=make_formation(state=F_FORMING), tier=TIER_PARTIAL))
        self.assertEqual(rank.state, R.PENDING)
        self.assertEqual(R.CONFIDENCE_VN[rank.state], "chưa xác nhận")

    def test_counter_evidence_reads_as_conflict(self):
        rank = R.build_pattern_rank(
            make_structure(formation=make_formation(), tier=TIER_CONFLICT))
        self.assertEqual(rank.state, R.CONFLICT)

    def test_confidence_never_reaches_a_perfect_hundred(self):
        best = make_formation(bars_since_break=1, break_volume_x=3.0)
        rank = R.build_pattern_rank(make_structure(formation=best, tier=TIER_FULL))
        self.assertLess(rank.confidence, 100.0)

    def test_a_spent_target_lowers_confidence(self):
        live = R.build_pattern_rank(
            make_structure(formation=make_formation(), tier=TIER_FULL))
        spent = R.build_pattern_rank(
            make_structure(formation=make_formation(target_hit=True), tier=TIER_FULL))
        self.assertLess(spent.confidence, live.confidence)

    def test_a_live_box_outranks_a_dead_formation(self):
        """State decides the source, not the source the state."""
        structure = make_structure(
            formation=make_formation(state=F_FAILED), tier=TIER_CONFLICT,
            box=make_box(BREAKOUT_UP_CONFIRMED, breakout_volume_x=2.1,
                         bars_since_breakout=2),
        )
        rank = R.build_pattern_rank(structure)
        self.assertEqual(rank.source, R.BOX_SRC)
        self.assertEqual(rank.state, R.CONFIRMED)

    def test_a_live_formation_outranks_a_box_it_shares_the_chart_with(self):
        structure = make_structure(
            formation=make_formation(), tier=TIER_FULL,
            box=make_box(BREAKOUT_UP_WEAK, bars_since_breakout=2),
        )
        self.assertEqual(R.build_pattern_rank(structure).source, R.FORMATION_SRC)

    def test_a_broken_formation_still_surfaces_when_nothing_else_is_live(self):
        rank = R.build_pattern_rank(
            make_structure(formation=make_formation(state=F_FAILED), tier=TIER_CONFLICT))
        self.assertEqual(rank.state, R.FAILED)

    def test_price_pinned_to_a_box_edge_beats_price_mid_box(self):
        edge = R.build_pattern_rank(make_structure(box=make_box(position_pct=90.0)))
        middle = R.build_pattern_rank(make_structure(box=make_box(position_pct=50.0)))
        self.assertGreater(edge.confidence, middle.confidence)
        self.assertEqual(edge.bias, "neutral", "sitting in a box is not a direction")

    def test_a_breakdown_carries_the_bearish_side(self):
        rank = R.build_pattern_rank(
            make_structure(box=make_box(BREAKDOWN_CONFIRMED, bars_since_breakout=2)))
        self.assertEqual(rank.bias, BEARISH)
        self.assertLess(rank.signed, 0)

    def test_no_pattern_at_all_is_its_own_state(self):
        rank = R.build_pattern_rank(make_structure())
        self.assertEqual(rank.state, R.NO_PATTERN)
        self.assertEqual(rank.confidence, 0.0)

    def test_note_is_borrowed_never_rewritten(self):
        """Wording comes from confluence/boxes so file and terminal cannot differ."""
        structure = make_structure(formation=make_formation(), tier=TIER_FULL)
        self.assertEqual(R.build_pattern_rank(structure).note, "câu kết luận")
        self.assertEqual(R.build_pattern_rank(make_structure(box=make_box())).note,
                         "nhãn hộp")


# ---------------------------------------------------------------------------
# ordering
# ---------------------------------------------------------------------------
class SortTest(unittest.TestCase):
    def setUp(self):
        self.rows = [
            make_row("AAA", trend_score=80.0, side=R.UP, confidence=90.0,
                     state=R.PENDING, bias=BULLISH),
            make_row("BBB", trend_score=-60.0, side=R.DOWN, confidence=70.0,
                     state=R.CONFIRMED, bias=BEARISH),
            make_row("CCC", trend_score=5.0, side=R.FLAT, confidence=40.0,
                     state=R.PARTIAL, bias=BULLISH),
        ]

    def test_default_is_trend_high_to_low(self):
        rows, crit = R.sort_rows(self.rows)
        self.assertEqual(crit.key, "trend")
        self.assertEqual([r.symbol for r in rows], ["AAA", "CCC", "BBB"])

    def test_descending_false_reverses_it(self):
        rows, _ = R.sort_rows(self.rows, "trend", descending=False)
        self.assertEqual([r.symbol for r in rows], ["BBB", "CCC", "AAA"])

    def test_confidence_orders_by_state_band_before_score(self):
        """`đã xác nhận 70` must outrank `chưa xác nhận 90`."""
        rows, _ = R.sort_rows(self.rows, "confidence")
        self.assertEqual([r.symbol for r in rows], ["BBB", "CCC", "AAA"])

    def test_side_filter_keeps_only_that_trend(self):
        rows, _ = R.sort_rows(self.rows, "trend", side="giảm")
        self.assertEqual([r.symbol for r in rows], ["BBB"])

    def test_bias_filter_keeps_only_that_pattern_direction(self):
        rows, _ = R.sort_rows(self.rows, "confidence", bias="tăng")
        self.assertEqual({r.symbol for r in rows}, {"AAA", "CCC"})

    def test_min_confidence_is_a_floor_on_the_state_not_the_score(self):
        rows, _ = R.sort_rows(self.rows, "confidence", min_confidence="xác nhận một phần")
        self.assertEqual({r.symbol for r in rows}, {"BBB", "CCC"})

    def test_missing_values_sort_last_in_both_directions(self):
        rows = self.rows + [make_row("ZZZ", rsi=None)]
        high, _ = R.sort_rows(rows, "rsi", descending=True)
        low, _ = R.sort_rows(rows, "rsi", descending=False)
        self.assertEqual(high[-1].symbol, "ZZZ")
        self.assertEqual(low[-1].symbol, "ZZZ")

    def test_vietnamese_names_resolve_with_or_without_accents(self):
        for name in ("cường độ", "cuong do", "Cường Độ", "trend"):
            self.assertEqual(R.resolve_criterion(name).key, "trend")
        for name in ("độ tin cậy", "do tin cay", "confidence"):
            self.assertEqual(R.resolve_criterion(name).key, "confidence")

    def test_an_unknown_criterion_lists_the_valid_ones(self):
        with self.assertRaises(ValueError) as ctx:
            R.sort_rows(self.rows, "không có tiêu chí này")
        self.assertIn("confidence", str(ctx.exception))

    def test_an_unknown_filter_value_is_rejected(self):
        with self.assertRaises(ValueError):
            R.sort_rows(self.rows, "trend", side="ngang ngửa gì đó")

    def test_limit_trims_after_sorting_not_before(self):
        rows, _ = R.sort_rows(self.rows, "trend", limit=1)
        self.assertEqual([r.symbol for r in rows], ["AAA"])


# ---------------------------------------------------------------------------
# artefacts
# ---------------------------------------------------------------------------
class ArtefactTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._patches = [
            mock.patch.object(R, "REPORT_DIR", self.tmp / "reports"),
            mock.patch.object(R, "LATEST_JSON", self.tmp / "reports" / "latest.json"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def _board(self):
        return R.Ranking(as_of="2026-08-25", generated="2026-08-26 10:00", universe="test",
                         rows=[make_row("AAA", 80.0, R.UP), make_row("BBB", -60.0, R.DOWN)])

    def test_json_round_trip_preserves_both_scores(self):
        board = self._board()
        R.save_json(board)
        again = R.load_ranking()
        self.assertEqual([r.symbol for r in again.rows], ["AAA", "BBB"])
        self.assertEqual(again.rows[0].trend.score, 80.0)
        self.assertEqual(again.rows[0].pattern.state, R.PARTIAL)
        self.assertEqual(again.rows[0].trend.note, board.rows[0].trend.note)

    def test_save_refreshes_the_stable_latest_pointer(self):
        R.save_json(self._board())
        self.assertTrue(R.LATEST_JSON.is_file())
        payload = json.loads(R.LATEST_JSON.read_text(encoding="utf-8"))
        self.assertEqual(len(payload["rows"]), 2)

    def test_loading_before_any_build_says_what_to_run(self):
        with self.assertRaises(FileNotFoundError) as ctx:
            R.load_ranking()
        self.assertIn("build_ranking", str(ctx.exception))

    def test_html_is_self_contained_and_needs_no_network(self):
        path = R.write_html(self._board())
        html = Path(path).read_text(encoding="utf-8")
        self.assertIn("<title>", html)
        self.assertFalse(re.search(r'(src|href)="https?://', html),
                         "the board must open offline")
        self.assertIn("Xu hướng tăng", html)
        self.assertIn("Chi tiết từng mã", html)

    def test_html_escapes_prose_coming_from_the_data(self):
        board = self._board()
        board.rows[0].pattern.note = '<script>alert("x")</script>'
        html = Path(R.write_html(board)).read_text(encoding="utf-8")
        body = html.split("<body>", 1)[1]
        self.assertNotIn("<script>alert", body)
        self.assertIn("&lt;script&gt;", body)

    def test_html_carries_sortable_values_not_just_formatted_text(self):
        html = Path(R.write_html(self._board())).read_text(encoding="utf-8")
        self.assertIn('data-sortable', html)
        self.assertIn('data-v="80.0"', html)
        self.assertIn('data-side="up"', html)


# ---------------------------------------------------------------------------
# end to end, against the data on disk
# ---------------------------------------------------------------------------
class BuildTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._patch = mock.patch.object(R, "LATEST_JSON", self.tmp / "latest.json")
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def test_builds_every_requested_symbol_and_writes_both_files(self):
        board = R.build("ACB,HPG,FPT", lookback_days=180, out_dir=str(self.tmp))
        self.assertEqual({r.symbol for r in board.rows}, {"ACB", "HPG", "FPT"})
        self.assertTrue(Path(board.html_path).is_file())
        self.assertTrue(Path(board.json_path).is_file())
        for row in board.rows:
            self.assertIn(row.trend.side, (R.UP, R.DOWN, R.FLAT))
            self.assertIn(row.pattern.state, R.CONFIDENCE_VN)
            self.assertTrue(row.trend.reasons)

    def test_an_unknown_universe_says_so_instead_of_raising(self):
        board = R.build("KHONGCOMA", out_dir=str(self.tmp))
        self.assertEqual(board.rows, [])
        self.assertTrue(board.skipped)

    def test_one_broken_symbol_does_not_kill_the_batch(self):
        real = R._build_row

        def flaky(symbol, *args, **kwargs):
            if symbol == "HPG":
                raise RuntimeError("hỏng")
            return real(symbol, *args, **kwargs)

        with mock.patch.object(R, "_build_row", flaky):
            board = R.build("ACB,HPG,FPT", lookback_days=180, out_dir=str(self.tmp))
        self.assertEqual({r.symbol for r in board.rows}, {"ACB", "FPT"})
        self.assertTrue(any("HPG" in s for s in board.skipped))


# ---------------------------------------------------------------------------
# markdown for the chat
# ---------------------------------------------------------------------------
class FormatTest(unittest.TestCase):
    def setUp(self):
        self.board = R.Ranking(
            as_of="2026-08-25", generated="2026-08-26 10:00", universe="all",
            rows=[make_row("AAA", 80.0, R.UP, state=R.CONFIRMED),
                  make_row("BBB", -60.0, R.DOWN, bias=BEARISH)],
            html_path="reports/x.html", json_path="reports/x.json")

    def test_summary_prints_both_axes_and_both_file_paths(self):
        md = format_ranking(self.board, top=2)
        self.assertIn("Xu hướng — xếp theo cường độ", md)
        self.assertIn("Mẫu hình — xếp theo độ tin cậy", md)
        self.assertIn("reports/x.html", md)
        self.assertIn("reports/x.json", md)
        self.assertIn("**AAA**", md)

    def test_summary_reports_the_distribution(self):
        md = format_ranking(self.board)
        self.assertIn("Phân bố", md)
        self.assertIn("**1** tăng", md)

    def test_list_states_the_criterion_direction_and_reason(self):
        rows, crit = R.sort_rows(self.board.rows, "trend")
        md = format_rank_list(rows, crit, descending=True, total=2, as_of="2026-08-25")
        self.assertIn("cao → thấp", md)
        self.assertIn(crit.explain, md, "the criterion has to explain itself")
        self.assertIn("Vì sao", md)

    def test_list_does_not_print_the_same_number_twice(self):
        rows, crit = R.sort_rows(self.board.rows, "trend")
        header = format_rank_list(rows, crit).splitlines()[6]
        self.assertNotIn("Cường độ", header.replace("Cường độ xu hướng", ""))

    def test_an_empty_result_says_so(self):
        rows, crit = R.sort_rows(self.board.rows, "trend", side="đi ngang")
        self.assertIn("Không có mã nào", format_rank_list(rows, crit))

    def test_every_criterion_renders(self):
        for key in R.CRITERIA:
            rows, crit = R.sort_rows(self.board.rows, key)
            self.assertIn(crit.label, format_rank_list(rows, crit), key)


if __name__ == "__main__":
    unittest.main()
