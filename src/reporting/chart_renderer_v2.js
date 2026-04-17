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

  // ── Price chart ──────────────────────────────────────────────────────────
  const pc = LightweightCharts.createChart(priceEl, {
    layout:          layoutOpts(),
    grid:            gridOpts(),
    crosshair:       crosshairOpts(),
    handleScroll:    scrollOpts(),
    handleScale:     scaleOpts(),
    rightPriceScale: { borderColor: BORDER },
    timeScale:       { borderColor: BORDER, timeVisible: false },
    height: 520,
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

  // Markers (all types merged and sorted by time)
  const markers = [
    ...BUY_MARKERS.map(m => ({
      time: m.time, position: 'belowBar', color: '#3fb950',
      shape: 'arrowUp', size: 1, text: m.score.toFixed(1),
    })),
    ...SELL_MARKERS.map(m => ({
      time: m.time, position: 'aboveBar', color: '#f85149',
      shape: 'arrowDown', size: 1, text: m.score.toFixed(1),
    })),
    ...ACTUAL_BUY_MARKERS.map(m => ({
      time: m.time, position: 'belowBar', color: '#2962ff',
      shape: 'circle', size: 0.8, text: '',
    })),
    ...ACTUAL_SELL_MARKERS.map(m => ({
      time: m.time, position: 'aboveBar', color: '#e3b341',
      shape: 'circle', size: 0.8, text: '',
    })),
  ].sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0));
  cs.setMarkers(markers);

  // ── Volume chart ─────────────────────────────────────────────────────────
  const vc = LightweightCharts.createChart(volEl, {
    layout:          layoutOpts(),
    grid:            gridOpts(),
    crosshair:       crosshairOpts(),
    handleScroll:    scrollOpts(),
    handleScale:     scaleOpts(),
    rightPriceScale: { borderColor: BORDER, scaleMargins: { top: 0.05, bottom: 0 } },
    timeScale:       { borderColor: BORDER, timeVisible: true },
    height: 170,
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

  // ── RSI chart ────────────────────────────────────────────────────────────
  const rsiEl  = document.getElementById('rsi-chart');
  const macdEl = document.getElementById('macd-chart');
  const adxEl  = document.getElementById('adx-chart');

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

  const smEl = document.getElementById('smartmoney-chart');
  const smc  = makeSub(smEl, 110);
  const rc = makeSub(rsiEl, 100);
  const mc = makeSub(macdEl, 100);
  const ac = makeSub(adxEl, 100);
  ac.applyOptions({ timeScale: { visible: true, borderColor: BORDER, timeVisible: true } });

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

  // Smart-money series come out of d.smart_money rather than d.indicators
  function _smSer(key) {
    return (HOVER_DATA || []).map(d => {
      const v = d.smart_money && d.smart_money[key];
      if (v === null || v === undefined) return { time: d.date };
      return { time: d.date, value: parseFloat(v) };
    });
  }
  const smSetupSer   = _smSer('setup_composite');
  const smTriggerSer = _smSer('trigger_composite');

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

  // Smart money composite lines + 0 reference
  const smSetupSeries = smc.addLineSeries({
    color: '#26a69a', lineWidth: 2, title: 'SM Setup',
    priceLineVisible: false, lastValueVisible: true,
  });
  smSetupSeries.setData(smSetupSer);
  const smTriggerSeries = smc.addLineSeries({
    color: '#bc8cff', lineWidth: 2, title: 'SM Trigger',
    priceLineVisible: false, lastValueVisible: true,
  });
  smTriggerSeries.setData(smTriggerSer);
  const smZero = smc.addLineSeries({
    color: '#6e7681', lineWidth: 1, lineStyle: LS.Dotted,
    priceLineVisible: false, lastValueVisible: false,
  });
  if (smSetupSer.length > 0) {
    smZero.setData(smSetupSer.map(p => ({ time: p.time, value: 0 })));
  }
  // Lock the visible range to ±1 so an all-zero series still shows the zero line
  smc.priceScale('right').applyOptions({ autoScale: false });
  smSetupSeries.applyOptions({
    autoscaleInfoProvider: () => ({ priceRange: { minValue: -1, maxValue: 1 } }),
  });

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
  const charts = [pc, vc, smc, rc, mc, ac];
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
  const allChartEls = [priceEl, volEl, smEl, rsiEl, macdEl, adxEl];
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

  // ── Info bar (always visible, updates on crosshair hover over signal) ──────
  const infoBar = document.getElementById('info-bar');
  const MARKER_MAP = {};
  BUY_MARKERS.forEach(m  => { MARKER_MAP[m.time + '_b'] = { label: '▲ Mua',  score: m.score, reason: m.reason, cls: 'pos' }; });
  SELL_MARKERS.forEach(m => { MARKER_MAP[m.time + '_s'] = { label: '▼ Bán',  score: m.score, reason: m.reason, cls: 'neg' }; });

  function renderInfoBar(info) {
    infoBar.innerHTML =
      '<span class="' + info.cls + '">' + info.label + '</span>' +
      '&nbsp;&nbsp;Score: <b>' + info.score.toFixed(2) + '</b>' +
      (info.reason ? '&nbsp;&nbsp;·&nbsp;&nbsp;<span style="color:#8b949e">' + info.reason + '</span>' : '');
  }

  // Default: last signal (buy or sell) by time
  const allSignals = [
    ...BUY_MARKERS.map(m  => ({ time: m.time, info: MARKER_MAP[m.time + '_b'] })),
    ...SELL_MARKERS.map(m => ({ time: m.time, info: MARKER_MAP[m.time + '_s'] })),
  ].sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0));
  if (allSignals.length > 0) renderInfoBar(allSignals[allSignals.length - 1].info);

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
  function _bar(v) {
    if (v === null || v === undefined) return _n(v);
    const pct = Math.min(Math.round(v * 100), 100);
    const col  = pct >= 70 ? '#3fb950' : pct >= 55 ? '#e3b341' : '#6e7681';
    return `<span class="hp-bar" style="width:${pct}px;background:${col}"></span>${pct}%`;
  }
  function _srow(label, v) {
    if (v === undefined || v === null) return '';
    return `<div class="hp-row"><span class="hp-k">${label}</span><span class="hp-v">${_bar(v)}</span></div>`;
  }

  function renderHoverPanel(d) {
    const p   = d.price        || {};
    const ind = d.indicators   || {};
    const sc  = d.scores       || {};
    const sig = d.signals      || {};

    const isBuy  = sig.is_buy;
    const isSale = sig.is_sale;
    const sigClr = isBuy ? '#3fb950' : (isSale ? '#f85149' : '#8b949e');
    const sigLbl = isBuy ? '▲ MUA'  : (isSale ? '▼ BÁN'  : '—');
    const regime = (sig.regime || '').replace(/_/g, ' ');

    const rvolClr = p.rvol >= 1.5 ? '#3fb950' : p.rvol >= 1.2 ? '#e3b341' : '#c9d1d9';
    const rsiV    = ind.rsi14 !== null && ind.rsi14 !== undefined ? parseFloat(ind.rsi14) : null;
    const rsiClr  = rsiV === null ? '#484f58' : rsiV < 30 ? '#3fb950' : rsiV > 70 ? '#f85149' : '#c9d1d9';
    const adxV    = ind.adx !== null && ind.adx !== undefined ? parseFloat(ind.adx) : null;
    const adxClr  = adxV === null ? '#484f58' : adxV >= 25 ? '#3fb950' : adxV >= 20 ? '#e3b341' : '#f85149';

    const sm = d.smart_money || {};
    const smLabel = (sm.label || 'neutral');
    const SM_TXT_COLOR = {
      strong_bull: '#3fb950', bull: '#26a69a', neutral: '#8b949e',
      bear: '#ef5350', strong_bear: '#b02a37', toxic: '#d63384',
    };
    const smClr = SM_TXT_COLOR[smLabel] || '#8b949e';
    function _smRow(label, v) {
      if (v === undefined || v === null) return '';
      const num = parseFloat(v);
      const col = num > 0 ? '#3fb950' : num < 0 ? '#f85149' : '#8b949e';
      return `<div class="hp-row"><span class="hp-k">${label}</span>` +
             `<span class="hp-v" style="color:${col}">${num.toFixed(3)}</span></div>`;
    }

    const reasons  = (d.reasons  || []).join(' · ') || '—';
    const blkHtml  = (d.blockers || []).length
      ? `<span style="color:#f85149">${d.blockers.join('<br>')}</span>`
      : '<span style="color:#3fb950">—</span>';

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
      </div>
      <div class="hp-col">
        <div class="hp-head">Điểm số &amp; Tín hiệu</div>
        ${_srow('Final',       sc.final)}
        ${_srow('Setup',       sc.setup)}
        ${_srow('Trigger',     sc.trigger)}
        <div class="hp-sep"></div>
        ${_srow('Candle',      sc.candle)}
        ${_srow('Trend',       sc.trend)}
        ${_srow('Momentum',    sc.momentum)}
        ${_srow('Volume',      sc.volume)}
        ${_srow('Structure',   sc.structure)}
        ${_srow('Confirm',     sc.confirmation)}
        ${_srow('Context',     sc.context)}
        ${_srow('Pivot',       sc.pivot)}
        <div class="hp-sep"></div>
        <div style="color:${smClr};font-weight:700;font-size:11px;letter-spacing:.5px;text-transform:uppercase">Smart money · ${smLabel.replace(/_/g,' ')}</div>
        ${_smRow('SM Setup',   sm.setup_composite)}
        ${_smRow('SM Trigger', sm.trigger_composite)}
        ${_srow('SM Conf',     sm.confidence)}
        ${sm.narrative ? `<div class="hp-tag" style="margin-top:3px">${sm.narrative}</div>` : ''}
        <div class="hp-sep"></div>
        <div style="color:${sigClr};font-weight:700;font-size:13px">${sigLbl}${regime ? ' · ' + regime : ''}</div>
        <div class="hp-tag" style="margin-top:3px">${reasons}</div>
        <div class="hp-sep"></div>
        <div class="hp-tag">Blockers: ${blkHtml}</div>
      </div>`;
  }

  // Show latest day on page load so the panel is never blank
  const dates = Object.keys(HOVER_MAP).sort();
  if (dates.length > 0) renderHoverPanel(HOVER_MAP[dates[dates.length - 1]]);

  function updateSelectedDay(time) {
    if (!time) return;
    const d = HOVER_MAP[time];
    if (d) renderHoverPanel(d);
    const info = MARKER_MAP[time + '_b'] || MARKER_MAP[time + '_s'];
    if (info) renderInfoBar(info);
  }

  // ── Crosshair sync across all charts ────────────────────────────────────────
  // O(1) time→value maps so setCrosshairPosition gets accurate price per subchart
  const _chMap = new Map(CANDLE_DATA.map(p => [p.time, p.close]));
  const _vMap  = new Map(VOLUME_DATA.filter(p => p.value !== undefined).map(p => [p.time, p.value]));
  const _smMap = new Map(smSetupSer.filter(p => p.value !== undefined).map(p => [p.time, p.value]));
  const _rMap  = new Map(rsiSer.filter(p => p.value !== undefined).map(p => [p.time, p.value]));
  const _mMap  = new Map(macdLineSer.filter(p => p.value !== undefined).map(p => [p.time, p.value]));
  const _aMap  = new Map(adxSer.filter(p => p.value !== undefined).map(p => [p.time, p.value]));

  // Each entry: { chart, series (for setCrosshairPosition), priceMap }
  const xhTargets = [
    { chart: pc,  series: cs,            map: _chMap },
    { chart: vc,  series: vcSeries,      map: _vMap  },
    { chart: smc, series: smSetupSeries, map: _smMap },
    { chart: rc,  series: rsiSeries,     map: _rMap  },
    { chart: mc,  series: macdSeries,    map: _mMap  },
    { chart: ac,  series: adxSeries,     map: _aMap  },
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

  // ── Visible-range helper ─────────────────────────────────────────────────
  // Both heatmap strips use the price chart's logical range so they pan/zoom
  // in lockstep with the candle/volume/indicator subcharts. Returns the
  // float window {from, to} clamped against the actual data bounds.
  function visibleWindow() {
    const data = HOVER_DATA || [];
    const n = data.length;
    if (!n) return null;
    const r = pc.timeScale().getVisibleLogicalRange();
    let from = r ? r.from : 0;
    let to   = r ? r.to   : n - 1;
    if (from < 0) from = 0;
    if (to > n - 1) to = n - 1;
    if (to <= from) return null;
    return { from, to, n };
  }

  // ── Score strip heatmap ──────────────────────────────────────────────────
  function drawScoreStrip() {
    const canvas = document.getElementById('score-strip-canvas');
    if (!canvas) return;
    const W = canvas.parentElement.clientWidth;
    const H = 26;
    canvas.width = W;
    canvas.height = H;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#0b0e14';
    ctx.fillRect(0, 0, W, H);

    const data = HOVER_DATA || [];
    const win = visibleWindow();
    if (!win) return;
    const cw = W / (win.to - win.from);
    const i0 = Math.max(0, Math.floor(win.from));
    const i1 = Math.min(data.length - 1, Math.ceil(win.to));

    for (let i = i0; i <= i1; i++) {
      const x = (i - win.from) * cw;
      const sc = (data[i].scores || {}).final;
      if (sc !== undefined && sc !== null) {
        const v = Math.max(0, Math.min(1, sc));
        let col;
        if (v < 0.4)        col = `rgba(110,118,129,${0.25 + v})`;
        else if (v < 0.65)  col = `rgba(227,179,65,${0.5 + (v - 0.4)})`;
        else                col = `rgba(63,185,80,${0.6 + (v - 0.65)})`;
        ctx.fillStyle = col;
        ctx.fillRect(x, 0, Math.ceil(cw), H);
      }
      const sig = data[i].signals || {};
      if (sig.is_buy) {
        ctx.fillStyle = '#3fb950';
        ctx.fillRect(x, H - 4, Math.ceil(cw), 4);
      } else if (sig.is_sale) {
        ctx.fillStyle = '#f85149';
        ctx.fillRect(x, 0, Math.ceil(cw), 4);
      }
    }
  }

  // ── Smart-money label strip ──────────────────────────────────────────────
  const SM_COLOR = {
    strong_bull: '#1e8449',
    bull:        '#3fb950',
    neutral:     '#30363d',
    bear:        '#ef5350',
    strong_bear: '#b02a37',
    toxic:       '#d63384',
  };
  function drawSmStrip() {
    const canvas = document.getElementById('smartmoney-strip-canvas');
    if (!canvas) return;
    const W = canvas.parentElement.clientWidth;
    const H = 22;
    canvas.width = W;
    canvas.height = H;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#0b0e14';
    ctx.fillRect(0, 0, W, H);

    const data = HOVER_DATA || [];
    const win = visibleWindow();
    if (!win) return;
    const cw = W / (win.to - win.from);
    const i0 = Math.max(0, Math.floor(win.from));
    const i1 = Math.min(data.length - 1, Math.ceil(win.to));

    for (let i = i0; i <= i1; i++) {
      const x = (i - win.from) * cw;
      const sm = data[i].smart_money || {};
      const lbl = sm.label || 'neutral';
      const conf = Math.max(0, Math.min(1, parseFloat(sm.confidence) || 0));
      const baseCol = SM_COLOR[lbl] || SM_COLOR.neutral;
      const alpha = lbl === 'neutral' ? 0.35 : (0.35 + 0.65 * conf);
      ctx.fillStyle = _hexToRgba(baseCol, alpha);
      ctx.fillRect(x, 0, Math.ceil(cw), H);
    }
  }

  // Redraw both strips whenever the price chart's visible range changes
  // (pan, zoom, sync from another subchart). We only need to subscribe on
  // the price chart because every other chart pushes its range back into pc
  // through syncRange().
  function redrawStrips() { drawScoreStrip(); drawSmStrip(); }
  pc.timeScale().subscribeVisibleLogicalRangeChange(redrawStrips);
  drawScoreStrip();
  function _hexToRgba(hex, a) {
    const h = hex.replace('#', '');
    const r = parseInt(h.substring(0, 2), 16);
    const g = parseInt(h.substring(2, 4), 16);
    const b = parseInt(h.substring(4, 6), 16);
    return 'rgba(' + r + ',' + g + ',' + b + ',' + a + ')';
  }
  drawSmStrip();

  // ── Responsive resize ────────────────────────────────────────────────────
  new ResizeObserver(() => {
    const w = document.getElementById('charts-container').clientWidth;
    pc.resize(w, 480);
    vc.resize(w, 130);
    smc.resize(w, 110);
    rc.resize(w, 100);
    mc.resize(w, 100);
    ac.resize(w, 100);
    drawScoreStrip();
    drawSmStrip();
  }).observe(document.getElementById('charts-container'));

  // ── Initial fit + sync ───────────────────────────────────────────────────
  pc.timeScale().fitContent();
  pc.timeScale().applyOptions({ rightOffset: 12 });
  requestAnimationFrame(() => {
    const r = pc.timeScale().getVisibleLogicalRange();
    if (r) {
      vc.timeScale().setVisibleLogicalRange(r);
      smc.timeScale().setVisibleLogicalRange(r);
      rc.timeScale().setVisibleLogicalRange(r);
      mc.timeScale().setVisibleLogicalRange(r);
      ac.timeScale().setVisibleLogicalRange(r);
    }
  });
})();
