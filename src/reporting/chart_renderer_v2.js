(function () {
  'use strict';

  const BG     = '#0f1117';
  const GRID   = '#161b22';
  const BORDER = '#21262d';
  const TXT    = '#6e7681';
  const LS     = LightweightCharts.LineStyle;

  // Shared option factories — avoids spread so Lightweight Charts receives
  // plain objects without prototype chain surprises.
  function layoutOpts() {
    return {
      background: { type: 'solid', color: BG },
      textColor: TXT,
      fontSize: 12,
      fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    };
  }
  function gridOpts()  { return { vertLines: { color: GRID }, horzLines: { color: GRID } }; }
  function crosshairOpts() {
    return {
      mode: LightweightCharts.CrosshairMode.Normal,
      vertLine: { color: '#3c4153', width: 1, style: LS.Dashed, labelBackgroundColor: '#2962ff' },
      horzLine: { color: '#3c4153', width: 1, style: LS.Dashed, labelBackgroundColor: '#2962ff' },
    };
  }
  // ALL built-in scroll/scale disabled — pan & zoom implemented manually below
  function scrollOpts() { return { pressedMouseMove: false, mouseWheel: false, horzTouchDrag: false, vertTouchDrag: false }; }
  function scaleOpts()  { return { mouseWheel: false, pinch: false, axisPressedMouseMove: { time: false, price: false } }; }

  const priceEl = document.getElementById('price-chart');
  const volEl   = document.getElementById('volume-chart');
  const rsiEl   = document.getElementById('rsi-chart');
  const macdEl  = document.getElementById('macd-chart');
  const adxEl   = document.getElementById('adx-chart');

  // ── Pane geometry ────────────────────────────────────────────────────────
  // The heights live here, not in the stylesheet, and are written onto the
  // elements. Lightweight Charts draws the time axis *inside* the height it is
  // given, so a chart created taller than its box — 520 in a 480 box, which is
  // what this was — loses exactly its date row to `overflow: hidden`.
  // Only the price pane and the bottom pane carry an axis: the panes scroll
  // together, so a date row under each of them is the same row three times.
  const PANE_H = { price: 500, volume: 132, rsi: 100, macd: 100, adx: 128 };
  const PANE_EL = { price: priceEl, volume: volEl, rsi: rsiEl, macd: macdEl, adx: adxEl };
  Object.keys(PANE_H).forEach(function (key) {
    PANE_EL[key].style.height = PANE_H[key] + 'px';
  });

  // ── Price chart ──────────────────────────────────────────────────────────
  const pc = LightweightCharts.createChart(priceEl, {
    layout:          layoutOpts(),
    grid:            gridOpts(),
    crosshair:       crosshairOpts(),
    handleScroll:    scrollOpts(),
    handleScale:     scaleOpts(),
    rightPriceScale: { borderColor: BORDER },
    timeScale:       { borderColor: BORDER, timeVisible: false },
    height: PANE_H.price,
    width:  priceEl.offsetWidth,
  });

  const cs = pc.addCandlestickSeries({
    upColor:         '#26a69a',
    downColor:       '#ef5350',
    borderUpColor:   '#26a69a',
    borderDownColor: '#ef5350',
    wickUpColor:     '#26a69a',
    wickDownColor:   '#ef5350',
  });
  cs.setData(CANDLE_DATA);

  pc.addLineSeries({
    color: '#58a6ff', lineWidth: 1.5,
    priceLineVisible: false, lastValueVisible: true, title: 'EMA20',
  }).setData(EMA20_DATA);

  pc.addLineSeries({
    color: '#f0883e', lineWidth: 1.5,
    priceLineVisible: false, lastValueVisible: true, title: 'EMA50',
  }).setData(EMA50_DATA);

  // ── Structure overlays: trendlines, box edges, measured target ───────────
  // Each entry is a two-point line; Lightweight Charts joins them straight
  // through, which is exactly a projected trendline.
  const OVERLAYS = (typeof OVERLAY_DATA !== 'undefined' && OVERLAY_DATA && OVERLAY_DATA.lines) || [];
  OVERLAYS.forEach(function (ov) {
      pc.addLineSeries({
        color: ov.color,
        lineWidth: 2,
        lineStyle: ov.dashed ? LS.Dashed : LS.Solid,
        // The price axis has room for a handle ("#2", "L1"), not a sentence —
        // a dozen full titles bury the right quarter of the chart. The name and
        // the reasoning both live in the hover tooltip below.
        title: ov.label || ov.title,
        priceLineVisible: false,
        lastValueVisible: true,
        crosshairMarkerVisible: false,
      }).setData(ov.points);
    });

  // ── Bounding box as a real rectangle ─────────────────────────────────────
  // The box covers a span of bars, not the whole timeline: drawing only its two
  // edges (as the dashed projections below do) says where the levels are but
  // not when the range formed. Lightweight Charts has no rectangle series, so
  // the shape is painted by a series primitive — the supported way to draw into
  // the pane — anchored on logical indices so it survives being scrolled off.
  const BOXES = (typeof OVERLAY_DATA !== 'undefined' && OVERLAY_DATA && OVERLAY_DATA.boxes) || [];

  function boxPrimitive(box) {
    function xAt(index, time) {
      const ts = pc.timeScale();
      const byIndex = ts.logicalToCoordinate(index);
      if (byIndex !== null && byIndex !== undefined) return byIndex;
      return ts.timeToCoordinate(time);
    }

    const paneView = {
      zOrder: function () { return 'bottom'; },   // candles stay readable on top
      renderer: function () {
        return {
          draw: function (target) {
            const x0 = xAt(box.start_index, box.start);
            const x1 = xAt(box.end_index, box.end);
            const yTop = cs.priceToCoordinate(box.top);
            const yBot = cs.priceToCoordinate(box.bottom);
            if (x0 === null || x1 === null || yTop === null || yBot === null) return;
            if (x0 === undefined || x1 === undefined || yTop === undefined || yBot === undefined) return;
            target.useBitmapCoordinateSpace(function (scope) {
              const ctx = scope.context;
              const hr = scope.horizontalPixelRatio;
              const vr = scope.verticalPixelRatio;
              const left   = Math.round(Math.min(x0, x1) * hr);
              const right  = Math.round(Math.max(x0, x1) * hr);
              const top    = Math.round(Math.min(yTop, yBot) * vr);
              const bottom = Math.round(Math.max(yTop, yBot) * vr);
              ctx.save();
              ctx.fillStyle = box.fill || 'rgba(227, 179, 65, 0.14)';
              ctx.fillRect(left, top, right - left, bottom - top);
              ctx.strokeStyle = box.color || '#e3b341';
              ctx.lineWidth = Math.max(1, Math.round(1.4 * hr));
              ctx.strokeRect(left, top, right - left, bottom - top);
              if (box.id) {
                ctx.fillStyle = box.color || '#e3b341';
                ctx.font = 'bold ' + Math.round(11 * vr) + 'px -apple-system, Segoe UI, sans-serif';
                ctx.textBaseline = 'bottom';
                ctx.fillText(box.id, left + 4 * hr, top - 3 * vr);
              }
              ctx.restore();
            });
          },
        };
      },
    };

    return {
      updateAllViews: function () {},          // coords are read at draw time
      paneViews: function () { return [paneView]; },
    };
  }

  if (BOXES.length && typeof cs.attachPrimitive === 'function') {
    BOXES.forEach(function (b) { cs.attachPrimitive(boxPrimitive(b)); });
  }

  // ── Structure read-out — the same notes as the chart overlays, in prose ──
  (function renderStructurePanel() {
    const panel = document.getElementById('structure-panel');
    const data = typeof OVERLAY_DATA !== 'undefined' ? OVERLAY_DATA : null;
    const brief = (data && data.brief) || [];
    if (!panel || !brief.length) return;

    function esc(s) {
      return String(s).replace(/[&<>"]/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
      });
    }
    // The notes come through as markdown; **bold** is the only markup used.
    function fmt(s) {
      return esc(s).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    }

    let html = '';
    if (data.pattern) html += '<div class="sp-pattern">' + esc(data.pattern) + '</div>';
    html += '<ul class="sp-list">';
    brief.forEach(function (b) { html += '<li>' + fmt(b) + '</li>'; });
    html += '</ul>';
    panel.innerHTML = html;
    panel.classList.add('visible');
  })();

  // ── Overlay hover tooltip — why this trendline / box edge is drawn ───────
  // Hit-tested in pixel space (endpoint coords via timeToCoordinate /
  // priceToCoordinate, interpolated at the cursor's x) so it matches exactly
  // what Lightweight Charts renders, regardless of business-day gaps.
  const overlayTooltip = document.getElementById('overlay-tooltip');
  const OVERLAY_HIT_PX = 6;

  function handleOverlayHover(param) {
    if (!param.point || !OVERLAYS.length) { overlayTooltip.style.display = 'none'; return; }
    const cursorX = param.point.x;
    const cursorY = param.point.y;
    let best = null;
    let bestDist = OVERLAY_HIT_PX;
    OVERLAYS.forEach(function (ov) {
      if (!ov.note || !ov.points || ov.points.length < 2) return;
      const p0 = ov.points[0], p1 = ov.points[1];
      const x0 = pc.timeScale().timeToCoordinate(p0.time);
      const x1 = pc.timeScale().timeToCoordinate(p1.time);
      const y0 = cs.priceToCoordinate(p0.value);
      const y1 = cs.priceToCoordinate(p1.value);
      if (x0 === null || x1 === null || y0 === null || y1 === null) return;
      const lo = Math.min(x0, x1) - 2, hi = Math.max(x0, x1) + 2;
      if (cursorX < lo || cursorX > hi) return;
      const t = x1 === x0 ? 0 : (cursorX - x0) / (x1 - x0);
      const yAt = y0 + t * (y1 - y0);
      const dist = Math.abs(yAt - cursorY);
      if (dist < bestDist) { bestDist = dist; best = ov; }
    });
    if (!best) { overlayTooltip.style.display = 'none'; return; }
    overlayTooltip.innerHTML = '<div class="ot-title">' + best.title + '</div>' + best.note;
    overlayTooltip.style.borderLeftColor = best.color;
    overlayTooltip.style.display = 'block';
    const rect = priceEl.getBoundingClientRect();
    let left = rect.left + cursorX + 14;
    let top = rect.top + cursorY + 14;
    const tw = overlayTooltip.offsetWidth, th = overlayTooltip.offsetHeight;
    if (left + tw > window.innerWidth - 8) left = rect.left + cursorX - tw - 14;
    if (top + th > window.innerHeight - 8) top = rect.top + cursorY - th - 14;
    overlayTooltip.style.left = left + 'px';
    overlayTooltip.style.top = top + 'px';
  }

  pc.subscribeCrosshairMove(handleOverlayHover);

  // ── Volume chart ─────────────────────────────────────────────────────────
  const vc = LightweightCharts.createChart(volEl, {
    layout:          layoutOpts(),
    grid:            gridOpts(),
    crosshair:       crosshairOpts(),
    handleScroll:    scrollOpts(),
    handleScale:     scaleOpts(),
    // A little room under the bars: with the baseline flush to the bottom edge
    // the last-value tag (which sits at the latest bar's height, usually low)
    // hangs over the edge and gets clipped.
    rightPriceScale: { borderColor: BORDER, scaleMargins: { top: 0.05, bottom: 0.08 } },
    timeScale:       { borderColor: BORDER, timeVisible: false, visible: false },
    height: PANE_H.volume,
    width:  volEl.offsetWidth,
  });

  const vcSeries = vc.addHistogramSeries({
    priceFormat: { type: 'volume' },
    priceScaleId: 'right',
  });
  vcSeries.setData(VOLUME_DATA);

  vc.addLineSeries({
    color: '#bc8cff', lineWidth: 2,
    lineStyle: LS.Dashed,
    priceLineVisible: false, lastValueVisible: false,
  }).setData(EMA_VOLUME_DATA);

  // ── Indicator subcharts ──────────────────────────────────────────────────
  function makeSub(el, h) {
    return LightweightCharts.createChart(el, {
      layout: layoutOpts(),
      grid: gridOpts(),
      crosshair: crosshairOpts(),
      handleScroll: scrollOpts(),
      handleScale: scaleOpts(),
      rightPriceScale: { borderColor: BORDER, scaleMargins: { top: 0.15, bottom: 0.05 } },
      timeScale: { borderColor: BORDER, timeVisible: false, visible: false },
      height: h,
      width: el.offsetWidth,
    });
  }

  const rc = makeSub(rsiEl, PANE_H.rsi);
  const mc = makeSub(macdEl, PANE_H.macd);
  const ac = makeSub(adxEl, PANE_H.adx);
  // The bottom pane is the one that closes the stack, so it keeps a date row —
  // and is built taller than the others to pay for it out of its own height.
  ac.applyOptions({ timeScale: { visible: true, borderColor: BORDER, timeVisible: false } });

  // Build sub-series from HOVER_DATA keeping full timeline.
  // Null/undefined indicators become whitespace data points ({ time } only)
  // so every subchart has the same bar count as the price chart.
  function _ser(key) {
    return (HOVER_DATA || []).map(d => {
      const v = d.indicators && d.indicators[key];
      if (v === null || v === undefined) return { time: d.date };
      return { time: d.date, value: parseFloat(v) };
    });
  }

  const rsiSer      = _ser('rsi14');
  const macdLineSer = _ser('macd_line');
  const macdSigSer  = _ser('macd_sig');
  const macdHistSer = (HOVER_DATA || []).map(d => {
    const v = d.indicators && d.indicators.macd_hist;
    if (v === null || v === undefined) return { time: d.date };
    const fv = parseFloat(v);
    return { time: d.date, value: fv, color: fv >= 0 ? '#26a69a' : '#ef5350' };
  });
  const adxSer = _ser('adx');

  const rsiSeries = rc.addLineSeries({ color: '#e3b341', lineWidth: 2, title: 'RSI14', priceLineVisible: false });
  rsiSeries.setData(rsiSer);
  // RSI reference lines span the full timeline (whitespace points carry through)
  const rsi30 = rc.addLineSeries({ color: '#3fb950', lineWidth: 1, lineStyle: LS.Dotted, priceLineVisible: false, lastValueVisible: false });
  const rsi70 = rc.addLineSeries({ color: '#f85149', lineWidth: 1, lineStyle: LS.Dotted, priceLineVisible: false, lastValueVisible: false });
  if (rsiSer.some(p => p.value !== undefined)) {
    rsi30.setData(rsiSer.map(p => p.value !== undefined ? { time: p.time, value: 30 } : { time: p.time }));
    rsi70.setData(rsiSer.map(p => p.value !== undefined ? { time: p.time, value: 70 } : { time: p.time }));
  }

  mc.addHistogramSeries({ priceLineVisible: false, base: 0 }).setData(macdHistSer);
  const macdSeries = mc.addLineSeries({ color: '#58a6ff', lineWidth: 1.5, title: 'MACD', priceLineVisible: false });
  macdSeries.setData(macdLineSer);
  mc.addLineSeries({ color: '#f0883e', lineWidth: 1.5, title: 'Signal', priceLineVisible: false }).setData(macdSigSer);

  const adxSeries = ac.addLineSeries({ color: '#bc8cff', lineWidth: 2, title: 'ADX14', priceLineVisible: false });
  adxSeries.setData(adxSer);
  const adx20 = ac.addLineSeries({ color: '#6e7681', lineWidth: 1, lineStyle: LS.Dotted, priceLineVisible: false, lastValueVisible: false });
  if (adxSer.some(p => p.value !== undefined)) adx20.setData(adxSer.map(p => p.value !== undefined ? { time: p.time, value: 20 } : { time: p.time }));

  // ── Sync all charts via logical range ───────────────────────────────────────
  const charts = [pc, vc, rc, mc, ac];
  let _lock = false;
  function syncRange(src, dst) {
    src.timeScale().subscribeVisibleLogicalRangeChange(r => {
      if (_lock || !r) return;
      _lock = true;
      dst.timeScale().setVisibleLogicalRange(r);
      _lock = false;
    });
  }
  for (const a of charts) for (const b of charts) if (a !== b) syncRange(a, b);

  // ── Pan (drag) & Zoom (vertical wheel at cursor) — fully custom ──────────────
  // Drag on chart body OR time axis → pan all charts left/right
  // Vertical mouse wheel             → zoom around cursor position
  // Horizontal wheel / trackpad swipe → ignored
  const allChartEls = [priceEl, volEl, rsiEl, macdEl, adxEl];
  let _drag = null;

  allChartEls.forEach(el => {
    el.style.cursor = 'grab';

    el.addEventListener('mousedown', (e) => {
      if (e.button !== 0) return;
      _drag = { x: e.clientX };
      document.body.style.cursor = 'grabbing';
      e.preventDefault();
    });

    el.addEventListener('wheel', (e) => {
      e.preventDefault();
      // Ignore horizontal component (trackpad side-swipe, tilt-wheel, etc.)
      if (Math.abs(e.deltaX) >= Math.abs(e.deltaY)) return;
      const range = pc.timeScale().getVisibleLogicalRange();
      if (!range) return;
      // Cursor logical position (zoom anchor) — relative to price chart left edge
      const chartLeft  = priceEl.getBoundingClientRect().left;
      const cursorX    = e.clientX - chartLeft;
      const cursorBar  = pc.timeScale().coordinateToLogical(cursorX) ?? ((range.from + range.to) / 2);
      // Scale the range around cursor bar
      const factor  = 1 + (e.deltaY > 0 ? 0.1 : -0.1);
      const newFrom = cursorBar - (cursorBar - range.from) * factor;
      const newTo   = cursorBar + (range.to  - cursorBar) * factor;
      if (newTo - newFrom < 4) return; // hard lower-bound on zoom
      _lock = true;
      charts.forEach(c => c.timeScale().setVisibleLogicalRange({ from: newFrom, to: newTo }));
      _lock = false;
    }, { passive: false });
  });

  document.addEventListener('mousemove', (e) => {
    if (!_drag) return;
    const dx = e.clientX - _drag.x;
    _drag.x = e.clientX;
    if (dx === 0) return;
    const range = pc.timeScale().getVisibleLogicalRange();
    if (!range) return;
    // pixels → bars: visible_bars / chart_width (price chart width as reference)
    const chartWidth  = priceEl.offsetWidth || 1;
    const barsPerPixel = (range.to - range.from) / chartWidth;
    const shift = -dx * barsPerPixel;
    _lock = true;
    charts.forEach(c => c.timeScale().setVisibleLogicalRange({
      from: range.from + shift,
      to:   range.to  + shift,
    }));
    _lock = false;
  });

  document.addEventListener('mouseup', () => {
    if (!_drag) return;
    _drag = null;
    document.body.style.cursor = '';
    allChartEls.forEach(el => { el.style.cursor = 'grab'; });
  });

  // ── Hover panel ──────────────────────────────────────────────────────────
  const hoverPanel = document.getElementById('hover-panel');

  // Build O(1) lookup: date string → payload
  const HOVER_MAP = {};
  (HOVER_DATA || []).forEach(d => { HOVER_MAP[d.date] = d; });

  // Format helpers — all safe against null/undefined
  function _n(v, dec) {
    if (v === null || v === undefined) return '<span style="color:#484f58">N/A</span>';
    return parseFloat(v).toFixed(dec !== undefined ? dec : 2);
  }
  function _vol(v) {
    if (!v) return 'N/A';
    if (v >= 1e6) return (v / 1e6).toFixed(2) + 'M';
    if (v >= 1e3) return (v / 1e3).toFixed(0) + 'K';
    return String(v);
  }

  function renderHoverPanel(d) {
    const p   = d.price      || {};
    const ind = d.indicators || {};

    const rvolClr = p.rvol >= 1.5 ? '#3fb950' : p.rvol >= 1.2 ? '#e3b341' : '#c9d1d9';
    const rsiV    = ind.rsi14 !== null && ind.rsi14 !== undefined ? parseFloat(ind.rsi14) : null;
    const rsiClr  = rsiV === null ? '#484f58' : rsiV < 30 ? '#3fb950' : rsiV > 70 ? '#f85149' : '#c9d1d9';
    const adxV    = ind.adx !== null && ind.adx !== undefined ? parseFloat(ind.adx) : null;
    const adxClr  = adxV === null ? '#484f58' : adxV >= 25 ? '#3fb950' : adxV >= 20 ? '#e3b341' : '#f85149';

    hoverPanel.className = 'visible';
    hoverPanel.innerHTML = `
      <div class="hp-col">
        <div class="hp-head">${d.date} · ${d.symbol}</div>
        <div class="hp-row"><span class="hp-k">Open</span>  <span class="hp-v">${_n(p.open)}</span></div>
        <div class="hp-row"><span class="hp-k">High</span>  <span class="hp-v pos">${_n(p.high)}</span></div>
        <div class="hp-row"><span class="hp-k">Low</span>   <span class="hp-v neg">${_n(p.low)}</span></div>
        <div class="hp-row"><span class="hp-k">Close</span> <span class="hp-v">${_n(p.close)}</span></div>
        <div class="hp-row"><span class="hp-k">Deal Vol</span><span class="hp-v">${_vol(p.volume)}</span></div>
        <div class="hp-row"><span class="hp-k">RVOL</span>  <span class="hp-v" style="color:${rvolClr}">${_n(p.rvol)}</span></div>
        <div class="hp-sep"></div>
        <div class="hp-row"><span class="hp-k">EMA20</span> <span class="hp-v">${_n(ind.ema20)}</span></div>
        <div class="hp-row"><span class="hp-k">EMA50</span> <span class="hp-v">${_n(ind.ema50)}</span></div>
        <div class="hp-row"><span class="hp-k">EMA100</span><span class="hp-v">${_n(ind.ema100)}</span></div>
        <div class="hp-row"><span class="hp-k">ATR14</span> <span class="hp-v">${_n(ind.atr14)}</span></div>
      </div>
      <div class="hp-col">
        <div class="hp-head">Chỉ báo</div>
        <div class="hp-row"><span class="hp-k">RSI14</span>    <span class="hp-v" style="color:${rsiClr}">${_n(ind.rsi14,1)}</span></div>
        <div class="hp-row"><span class="hp-k">MACD line</span><span class="hp-v">${_n(ind.macd_line,3)}</span></div>
        <div class="hp-row"><span class="hp-k">MACD sig</span> <span class="hp-v">${_n(ind.macd_sig,3)}</span></div>
        <div class="hp-row"><span class="hp-k">MACD hist</span><span class="hp-v">${_n(ind.macd_hist,3)}</span></div>
        <div class="hp-row"><span class="hp-k">ADX</span>      <span class="hp-v" style="color:${adxClr}">${_n(ind.adx,1)}</span></div>
        <div class="hp-row"><span class="hp-k">MFI</span>      <span class="hp-v">${_n(ind.mfi,1)}</span></div>
        <div class="hp-row"><span class="hp-k">OBV slope</span><span class="hp-v">${_n(ind.obv_slope,0)}</span></div>
        <div class="hp-sep"></div>
        <div class="hp-row"><span class="hp-k">SW Hi 10d</span><span class="hp-v">${_n(ind.sw_hi10)}</span></div>
        <div class="hp-row"><span class="hp-k">SW Lo 10d</span><span class="hp-v">${_n(ind.sw_lo10)}</span></div>
        <div class="hp-row"><span class="hp-k">SW Hi 20d</span><span class="hp-v">${_n(ind.sw_hi20)}</span></div>
        <div class="hp-row"><span class="hp-k">SW Lo 20d</span><span class="hp-v">${_n(ind.sw_lo20)}</span></div>
      </div>`;
  }

  // Show latest day on page load so the panel is never blank
  const dates = Object.keys(HOVER_MAP).sort();
  if (dates.length > 0) renderHoverPanel(HOVER_MAP[dates[dates.length - 1]]);

  function updateSelectedDay(time) {
    if (!time) return;
    const d = HOVER_MAP[time];
    if (d) renderHoverPanel(d);
  }

  // ── Crosshair sync across all charts ────────────────────────────────────────
  // O(1) time→value maps so setCrosshairPosition gets accurate price per subchart
  const _chMap = new Map(CANDLE_DATA.map(p => [p.time, p.close]));
  const _vMap  = new Map(VOLUME_DATA.filter(p => p.value !== undefined).map(p => [p.time, p.value]));
  const _rMap  = new Map(rsiSer.filter(p => p.value !== undefined).map(p => [p.time, p.value]));
  const _mMap  = new Map(macdLineSer.filter(p => p.value !== undefined).map(p => [p.time, p.value]));
  const _aMap  = new Map(adxSer.filter(p => p.value !== undefined).map(p => [p.time, p.value]));

  // Each entry: { chart, series (for setCrosshairPosition), priceMap }
  const xhTargets = [
    { chart: pc, series: cs,         map: _chMap },
    { chart: vc, series: vcSeries,   map: _vMap  },
    { chart: rc, series: rsiSeries,  map: _rMap  },
    { chart: mc, series: macdSeries, map: _mMap  },
    { chart: ac, series: adxSeries,  map: _aMap  },
  ];

  let _xhLock = false;

  function onCrosshairMove(srcChart, param) {
    // Hover only syncs the crosshair; selected-day details update on click.
    if (_xhLock) return;
    _xhLock = true;
    xhTargets.forEach(({ chart, series, map }) => {
      if (chart === srcChart) return;
      if (!param.time) {
        chart.clearCrosshairPosition();
      } else {
        // Use actual value from that chart's series; fall back to 0 if whitespace
        const price = map.get(param.time) ?? 0;
        chart.setCrosshairPosition(price, param.time, series);
      }
    });
    _xhLock = false;
  }

  // Subscribe on every chart so hover syncs the crosshair and click selects the day.
  xhTargets.forEach(({ chart }) => {
    chart.subscribeCrosshairMove(param => onCrosshairMove(chart, param));
    chart.subscribeClick(param => updateSelectedDay(param.time));
  });

  // ── Keep each box exactly as tall as the chart inside it ─────────────────
  // Lightweight Charts lays its panes out in a <table> that ends up a few
  // pixels taller than the height it was handed (one border per row), and the
  // boxes clip with `overflow: hidden` for their rounded corners — so those few
  // pixels came off the bottom of the time axis and cut the dates in half.
  // The table is observed rather than measured once: the axis row gets its
  // height on a later render pass, so a single reading taken right after
  // createChart is still the old, too-short number.
  Object.keys(PANE_EL).forEach(function (key) {
    const el = PANE_EL[key];
    const table = el.querySelector('table');
    if (!table) return;
    new ResizeObserver(function () {
      const real = Math.ceil(table.getBoundingClientRect().height);
      if (real && real !== el.clientHeight) el.style.height = real + 'px';
    }).observe(table);
  });

  // ── Responsive resize ────────────────────────────────────────────────────
  new ResizeObserver(() => {
    const w = document.getElementById('charts-container').clientWidth;
    pc.resize(w, PANE_H.price);
    vc.resize(w, PANE_H.volume);
    rc.resize(w, PANE_H.rsi);
    mc.resize(w, PANE_H.macd);
    ac.resize(w, PANE_H.adx);
  }).observe(document.getElementById('charts-container'));

  // ── Initial fit + sync ───────────────────────────────────────────────────
  pc.timeScale().fitContent();
  pc.timeScale().applyOptions({ rightOffset: 12 });
  requestAnimationFrame(() => {
    const r = pc.timeScale().getVisibleLogicalRange();
    if (r) {
      vc.timeScale().setVisibleLogicalRange(r);
      rc.timeScale().setVisibleLogicalRange(r);
      mc.timeScale().setVisibleLogicalRange(r);
      ac.timeScale().setVisibleLogicalRange(r);
    }
  });
})();
