"""Turn a ``Structure`` into overlay data for the interactive HTML chart.

Trendlines are two-point line series; the library joins them straight through.
The consolidation box goes out twice, because it means two things: a filled
rectangle over the bars it actually covers (``boxes`` — painted by a series
primitive, since Lightweight Charts has no rectangle series), and the dashed
edges projected to the right edge (``lines``), which is where the levels are
still being traded against. Same drawing as the PNG in ``render.py``.

Every line carries two names: ``label`` is the handle painted on the price axis
(``#2``, ``L1``) and ``title`` is the full name shown when the line is hovered.
Putting the long one on the axis costs a quarter of the chart width.
"""
from typing import Any, Dict, List

from src.ta.formations import BEARISH, CONFIRMED, FAILED
from src.ta.levels import KIND_LABELS
from src.ta.structure import Structure
from src.ta.trendlines import RESISTANCE

RES_COLOR = "#f85149"
SUP_COLOR = "#3fb950"
BOX_COLOR = "#e3b341"
BOX_FILL = "rgba(227, 179, 65, 0.14)"
ZONE_COLOR = "#8b949e"


def build_overlays(structure: Structure) -> Dict[str, Any]:
    """Overlay payload for ``chart_renderer_v2``; empty dict when nothing drawn."""
    recs = structure.records
    if not recs:
        return {}

    last_time = recs[-1].date.strftime("%Y-%m-%d")
    lines: List[Dict[str, Any]] = []

    for line in structure.trendlines:
        start = recs[line.p1_index].date.strftime("%Y-%m-%d")
        lines.append({
            "title": line.name + (" (đã phá)" if line.broken else ""),
            "label": line.id,
            "color": RES_COLOR if line.kind == RESISTANCE else SUP_COLOR,
            "dashed": line.broken,
            "note": line.label,
            "points": [
                {"time": start, "value": round(line.value_at(line.p1_index), 2)},
                {"time": last_time, "value": round(line.value_at(len(recs) - 1), 2)},
            ],
        })

    boxes: List[Dict[str, Any]] = []
    box = structure.box
    if box is not None:
        box_start = recs[box.start_index].date.strftime("%Y-%m-%d")
        boxes.append({
            "id": box.id,
            "title": f"Hộp tích luỹ {box.id}".strip(),
            "note": box.label,
            "color": BOX_COLOR,
            "fill": BOX_FILL,
            "top": box.top,
            "bottom": box.bottom,
            # Both are sent: the logical index survives being scrolled off
            # screen, the date is the fallback when the series is re-indexed.
            "start_index": box.start_index,
            "end_index": box.end_index,
            "start": box_start,
            "end": recs[box.end_index].date.strftime("%Y-%m-%d"),
        })
        for level, name, side in ((box.top, "Cạnh trên hộp", "trên"),
                                  (box.bottom, "Cạnh dưới hộp", "dưới")):
            lines.append({
                "title": f"{name} {box.id}".strip(),
                "label": f"{box.id} {side}".strip(),
                "color": BOX_COLOR,
                "dashed": True,
                "note": box.label,
                "points": [{"time": box_start, "value": level},
                           {"time": last_time, "value": level}],
            })
        if box.target is not None:
            lines.append({
                "title": f"Mục tiêu {box.id}".strip(),
                "label": f"MT {box.id}".strip(),
                "color": SUP_COLOR if box.target > box.top else RES_COLOR,
                "dashed": True,
                "note": f"Mục tiêu đo được từ chiều cao hộp: {box.target}"
                        + (" — đã chạm" if box.target_hit else "")
                        + (f". Mất hiệu lực nếu đóng cửa qua {box.invalidation}."
                           if box.invalidation is not None else ""),
                "points": [{"time": box.breakout_date or box_start, "value": box.target},
                           {"time": last_time, "value": box.target}],
            })

    for level in getattr(structure, "levels", []):
        lines.append({
            "title": f"{level.id} {KIND_LABELS.get(level.kind, level.kind)}".strip(),
            "label": level.id,
            "color": ZONE_COLOR,
            "dashed": True,
            "note": level.label,
            "points": [{"time": recs[0].date.strftime("%Y-%m-%d"), "value": level.price},
                       {"time": last_time, "value": level.price}],
        })

    # Necklines last so they sit on top of the box edges they often cross.
    for ev in getattr(structure, "evidence", []):
        f = ev.formation
        colour = RES_COLOR if f.bias == BEARISH else SUP_COLOR
        start = recs[f.pivots[1].index].date.strftime("%Y-%m-%d")
        lines.append({
            "title": f"Neckline {f.id} {f.name}".strip(),
            "label": f"NL {f.id}".strip(),
            "color": colour,
            "dashed": f.state != CONFIRMED,
            "note": ev.conclusion,
            "points": [
                {"time": start, "value": round(f.neckline_at(f.pivots[1].index), 2)},
                {"time": last_time, "value": round(f.neckline_at(len(recs) - 1), 2)},
            ],
        })
        if f.target is not None and f.state != FAILED:
            lines.append({
                "title": f"Mục tiêu {f.id}".strip(),
                "label": f"MT {f.id}".strip(),
                "color": colour,
                "dashed": True,
                "note": f"Mục tiêu đo được từ chiều cao {f.name.lower()}: {f.target}"
                        + (" — đã chạm" if f.target_hit else ""),
                "points": [{"time": f.break_date or start, "value": f.target},
                           {"time": last_time, "value": f.target}],
            })

    return {
        "lines": lines,
        "boxes": boxes,
        "pattern": structure.pattern.name if structure.pattern else None,
        "formations": [
            {"id": ev.formation.id, "name": ev.formation.name,
             "state": ev.formation.state, "tier": ev.tier,
             "conclusion": ev.conclusion}
            for ev in getattr(structure, "evidence", [])
        ],
        "levels": [l.to_dict() for l in getattr(structure, "levels", [])],
        "profile": {"poc": structure.profile.poc,
                    "value_low": structure.profile.value_low,
                    "value_high": structure.profile.value_high}
        if getattr(structure, "profile", None) else None,
        "brief": structure.brief,
    }
