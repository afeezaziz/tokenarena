/* global Chart */

let tokensChart, holdersChart;
let tokensData = [];
let sortKey = localStorage.getItem('tb_sort_key') || 'market_cap_usd';
let sortDir = localStorage.getItem('tb_sort_dir') || 'desc';
let sortingBound = false;
let currentPage = parseInt(localStorage.getItem('tb_tokens_page') || '1', 10);
let pageSize = parseInt(localStorage.getItem('tb_tokens_page_size') || '10', 10);
let totalCount = 0;
let tokensQuery = localStorage.getItem('tb_tokens_query') || '';
let sparkDays = parseInt(localStorage.getItem('tb_spark_days') || '7', 10);
let moversMetric = localStorage.getItem('tb_movers_metric') || 'change_24h';
let tableMetric = localStorage.getItem('tb_table_metric') || 'change_24h';
let sortByMetric = (localStorage.getItem('tb_sort_metric') || '0') === '1';
let minMcap = localStorage.getItem('tb_min_mcap') || '';
let minVolume = localStorage.getItem('tb_min_volume') || '';

function fmtCurrency(n) {
  try { return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n); } catch { return `$${Number(n).toLocaleString()}`; }
}

async function loadChangelogWidget(){
  const wrap = document.getElementById('whats-new-list');
  if (!wrap) return;
  wrap.innerHTML = '';
  try{
    const r = await fetch('/api/changelog?limit=3');
    const items = await r.json();
    if (!Array.isArray(items) || items.length === 0){
      const div = document.createElement('div');
      div.className = 'muted';
      div.textContent = 'No updates yet.';
      wrap.appendChild(div);
      return;
    }
    items.forEach(it => {
      const card = document.createElement('div');
      card.className = 'panel';
      const date = it.date || '';
      const title = it.title || '';
      const notes = Array.isArray(it.items) ? it.items : [];
      card.innerHTML = `
        <h3>${title || date}</h3>
        <ul class="muted">${notes.map(n => `<li>${n}</li>`).join('')}</ul>
      `;
      wrap.appendChild(card);
    });
  } catch(e){ console.error(e); }
}
function fmtNumber(n) {
  try { return new Intl.NumberFormat('en-US').format(n); } catch { return Number(n).toLocaleString(); }
}
function fmtPct(n){ return `${(Number(n) >= 0 ? '+' : '')}${Number(n).toFixed(2)}%`; }

// Simple watchlist using localStorage
const WATCH_KEY = 'tb_watchlist';
function getWatchlist(){
  try { const v = JSON.parse(localStorage.getItem(WATCH_KEY) || '[]'); return Array.isArray(v) ? v : []; } catch { return []; }
}
function isWatched(sym){
  if (!sym) return false; const s = String(sym).toUpperCase();
  return getWatchlist().includes(s);
}
function toggleWatchlist(sym){
  if (!sym) return false; const s = String(sym).toUpperCase();
  const list = getWatchlist();
  const idx = list.indexOf(s);
  if (idx >= 0) list.splice(idx, 1); else list.push(s);
  try { localStorage.setItem(WATCH_KEY, JSON.stringify(list)); } catch {}
  return list.includes(s);
}

function metricLabel(m){
  switch (m) {
    case 'change_24h': return '24h';
    case 'r7': return '7D';
    case 'r30': return '30D';
    case 'r7_sharpe': return 'Sharpe 7D';
    case 'holders_growth_pct_24h': return 'Holders 24h';
    case 'share_delta_7d': return 'Share Δ 7D';
    case 'composite': return 'Composite';
    default: return 'Metric';
  }
}

function metricValue(t, m){
  if (!t) return null;
  switch (m){
    case 'change_24h': return t.change_24h;
    case 'r7': return t.r7;
    case 'r30': return t.r30;
    case 'r7_sharpe': return t.r7_sharpe;
    case 'holders_growth_pct_24h': return t.holders_growth_pct_24h;
    case 'share_delta_7d': return t.share_delta_7d;
    case 'composite': return t.composite;
    default: return null;
  }
}

function formatMetric(m, v){
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '—';
  if (m === 'r7_sharpe' || m === 'composite') return Number(v).toFixed(2);
  return fmtPct(v);
}

function setSkeletonStats(active){
  const ids = ['stat-market-cap','stat-volume','stat-tokens','stat-holders','stat-dominance'];
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    if (active) { el.classList.add('skeleton'); el.textContent = '      '; }
    else { el.classList.remove('skeleton'); }
  });
}

function sparklineSVG(values){
  const w = 80, h = 24, pad = 2;
  if (!values || values.length < 2) {
    return `<svg width="${w}" height="${h}"></svg>`;
  }
  const min = Math.min(...values), max = Math.max(...values);
  const span = (max - min) || 1;
  const step = (w - pad*2) / (values.length - 1);
  let d = '';
  for (let i=0;i<values.length;i++){
    const x = pad + i*step;
    const y = pad + (h - pad*2) - ((values[i]-min)/span)*(h - pad*2);
    d += (i===0 ? 'M' : 'L') + x.toFixed(1) + ' ' + y.toFixed(1) + ' ';
  }
  const up = values[values.length-1] - values[0] >= 0;
  const stroke = up ? '#00d1b2' : '#ff5c7c';
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><path d="${d.trim()}" fill="none" stroke="${stroke}" stroke-width="2" stroke-linecap="round"/></svg>`;
}

function renderTokensTable(){
  const tbody = document.getElementById('tokens-tbody');
  if (!tbody) return;
  tbody.innerHTML = '';
  if (!tokensData || tokensData.length === 0){
    const tr = document.createElement('tr');
    tr.innerHTML = '<td colspan="8" class="muted" style="text-align:center;padding:12px">No results</td>';
    tbody.appendChild(tr);
    return;
  }
  const lastTh = document.querySelector('.tokens-table thead th:last-child');
  const hasActionsCol = !!(document.querySelector('.tokens-table thead .actions-col') || (lastTh && /actions/i.test((lastTh.textContent||'').trim())));
  tokensData.forEach((t, i) => {
    const tr = document.createElement('tr');
    tr.dataset.symbol = t.symbol;
    let actionsHtml = '';
    if (hasActionsCol){
      const watched = isWatched && isWatched(t.symbol);
      actionsHtml = `<td class="actions"><a class="btn small" href="/t/${encodeURIComponent(t.symbol)}">View</a> <button class="btn small star-btn" data-symbol="${t.symbol}" aria-pressed="${watched?'true':'false'}">${watched?'★':'☆'}</button></td>`;
    }
    tr.innerHTML = `
      <td>${(currentPage-1)*pageSize + i + 1}</td>
      <td><a href="/t/${encodeURIComponent(t.symbol)}"><strong>${t.symbol}</strong></a> <span class="muted">${t.name}</span></td>
      <td>${fmtCurrency(t.price_usd)}</td>
      <td>${sparklineSVG(t.sparkline || [])}</td>
      <td>${fmtCurrency(t.market_cap_usd)}</td>
      <td>${fmtNumber(t.holders_count)}</td>
      <td class="metric-cell">${formatMetric(tableMetric, metricValue(t, tableMetric))}</td>
      <td style="color:${t.change_24h>=0?'#00d1b2':'#ff5c7c'}">${fmtPct(t.change_24h)}</td>
      ${actionsHtml}
    `;
    tbody.appendChild(tr);
  });
}

function bindTokensTableSorting(){
  if (sortingBound) return;
  sortingBound = true;
  const headers = document.querySelectorAll('.tokens-table th.sortable');

  function updateIndicators(){
    headers.forEach(h => {
      const isMetric = h.dataset.metric === 'metric';
      const active = isMetric ? sortByMetric : (h.dataset.key === sortKey);
      h.classList.toggle('active', active);
      const arrow = h.querySelector('.arrow');
      if (arrow){
        const asc = sortDir === 'asc';
        arrow.textContent = active && asc ? '▲' : '▼';
      }
      // Accessibility: reflect sorting state
      if (active){
        h.setAttribute('aria-sort', sortDir === 'asc' ? 'ascending' : 'descending');
      } else {
        h.setAttribute('aria-sort', 'none');
      }
    });
  }
  updateIndicators();

  headers.forEach(h => {
    h.addEventListener('click', () => {
      if (h.dataset.metric === 'metric'){
        // toggle metric sorting locally
        sortByMetric = !sortByMetric || (sortKey !== null); // enable metric sorting
        // If already sorting by metric, toggle direction
        if (sortByMetric && h.classList.contains('active')){
          sortDir = sortDir === 'asc' ? 'desc' : 'asc';
        } else {
          sortDir = 'desc';
        }
        localStorage.setItem('tb_sort_metric', sortByMetric ? '1' : '0');
        localStorage.setItem('tb_sort_dir', sortDir);
        sortTokensDataByMetric();
        updateIndicators();
        renderTokensTable();
      } else {
        const key = h.dataset.key;
        if (!key) return;
        sortByMetric = false;
        if (sortKey === key) {
          sortDir = sortDir === 'asc' ? 'desc' : 'asc';
        } else {
          sortKey = key;
          sortDir = (key === 'symbol') ? 'asc' : 'desc';
        }
        localStorage.setItem('tb_sort_metric', '0');
        localStorage.setItem('tb_sort_key', sortKey);
        localStorage.setItem('tb_sort_dir', sortDir);
        updateIndicators();
        // reset to first page when sorting changes
        currentPage = 1;
        localStorage.setItem('tb_tokens_page', String(currentPage));
        fetchTokensData();
      }
    });
  });

  // Row click navigation (event delegation)
  const tbody = document.getElementById('tokens-tbody');
  if (tbody){
    tbody.addEventListener('click', (e) => {
      const star = e.target.closest('button.star-btn');
      if (star){
        const sym = star.dataset.symbol;
        if (sym && toggleWatchlist){
          const on = toggleWatchlist(sym);
          star.textContent = on ? '★' : '☆';
          star.setAttribute('aria-pressed', on ? 'true' : 'false');
          if (window.TB && TB.showToast) TB.showToast(on ? `Added ${sym} to watchlist` : `Removed ${sym} from watchlist`);
        }
        e.stopPropagation();
        e.preventDefault();
        return;
      }
      const a = e.target.closest('a');
      if (a) return; // let anchor clicks work
      const tr = e.target.closest('tr');
      if (!tr || !tr.dataset.symbol) return;
      window.location.href = `/t/${encodeURIComponent(tr.dataset.symbol)}`;
    });
  }
}

async function loadOverview(){
  const res = await fetch('/api/overview');
  const d = await res.json();
  const mcapEl = document.getElementById('stat-market-cap');
  const volEl = document.getElementById('stat-volume');
  const tokEl = document.getElementById('stat-tokens');
  const holdersEl = document.getElementById('stat-holders');
  const domEl = document.getElementById('stat-dominance');
  if (mcapEl) mcapEl.textContent = fmtCurrency(d.total_market_cap_usd || 0);
  if (volEl) volEl.textContent = fmtCurrency(d.volume_24h_usd || 0);
  if (tokEl) tokEl.textContent = fmtNumber(d.total_tokens || 0);
  if (holdersEl) holdersEl.textContent = fmtNumber(d.total_holders || 0);
  if (domEl) domEl.textContent = `${(d.dominance_pct || 0).toFixed(2)}%`;
}

function renderPagination(){
  const el = document.getElementById('tokens-pagination');
  if (!el) return;
  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));
  el.innerHTML = '';
  if (totalPages <= 1) return;

  const mkBtn = (label, page, disabled=false, active=false) => {
    const a = document.createElement('a');
    a.href = '#';
    a.className = 'page-btn' + (active ? ' active' : '');
    if (disabled) a.setAttribute('disabled','');
    a.dataset.page = String(page);
    a.textContent = label;
    return a;
  };

  el.appendChild(mkBtn('«', 1, currentPage===1));
  el.appendChild(mkBtn('‹', Math.max(1, currentPage-1), currentPage===1));

  const totalPagesToShow = 7;
  let start = Math.max(1, currentPage - Math.floor(totalPagesToShow/2));
  let end = Math.min(totalPages, start + totalPagesToShow - 1);
  if (end - start + 1 < totalPagesToShow) start = Math.max(1, end - totalPagesToShow + 1);

  if (start > 1) {
    el.appendChild(mkBtn('1', 1, false, currentPage===1));
    if (start > 2) {
      const span = document.createElement('span');
      span.className = 'muted';
      span.textContent = '…';
      el.appendChild(span);
    }
  }

  for (let p=start; p<=end; p++){
    el.appendChild(mkBtn(String(p), p, false, p===currentPage));
  }

  if (end < totalPages) {
    if (end < totalPages - 1) {
      const span = document.createElement('span');
      span.className = 'muted';
      span.textContent = '…';
      el.appendChild(span);
    }
    el.appendChild(mkBtn(String(totalPages), totalPages, false, currentPage===totalPages));
  }

  el.appendChild(mkBtn('›', Math.min(totalPages, currentPage+1), currentPage===totalPages));
  el.appendChild(mkBtn('»', totalPages, currentPage===totalPages));

  el.addEventListener('click', (e) => {
    const a = e.target.closest('a.page-btn');
    if (!a) return;
    e.preventDefault();
    const p = parseInt(a.dataset.page, 10);
    if (!p || p === currentPage) return;
    currentPage = p;
    localStorage.setItem('tb_tokens_page', String(currentPage));
    fetchTokensData();
  }, { once: true });
}

async function fetchTokensData(){
  const tbody = document.getElementById('tokens-tbody');
  if (tbody){
    tbody.innerHTML = '';
    for (let i=0;i<10;i++){
      const tr = document.createElement('tr');
      tr.innerHTML = '<td colspan="8"><div class="skeleton" style="height:16px; width:100%"></div></td>';
      tbody.appendChild(tr);
    }
  }

  const params = new URLSearchParams({
    page: String(currentPage),
    page_size: String(pageSize),
    sort: sortKey,
    dir: sortDir,
    sparkline: '1',
    days: String(sparkDays),
  });
  if (tokensQuery) params.set('q', tokensQuery);
  if (minMcap && !Number.isNaN(Number(minMcap))) params.set('min_mcap', String(minMcap));
  if (minVolume && !Number.isNaN(Number(minVolume))) params.set('min_volume', String(minVolume));
  if (sortByMetric && tableMetric){ params.set('metric', tableMetric); }
  const res = await fetch(`/api/tokens?${params.toString()}`);
  const data = await res.json();
  tokensData = data.items || [];
  totalCount = data.total || 0;
  if (sortByMetric) sortTokensDataByMetric();
  renderTokensTable();
  renderPagination();
}

async function loadTopMovers(){
  const moversWrap = document.getElementById('top-movers');
  if (!moversWrap) return;
  moversWrap.innerHTML = '';
  const mp = new URLSearchParams({ limit: '5', metric: moversMetric });
  if (minMcap && !Number.isNaN(Number(minMcap))) mp.set('min_mcap', String(minMcap));
  if (minVolume && !Number.isNaN(Number(minVolume))) mp.set('min_volume', String(minVolume));
  const res = await fetch(`/api/top-movers?${mp.toString()}`);
  const movers = await res.json();
  movers.forEach(m => {
    const div = document.createElement('div');
    const val = (m.value !== undefined ? m.value : m.change_24h);
    const up = Number(val) >= 0;
    div.className = `mover ${up?'up':'down'}`;
    div.innerHTML = `
      <div class="sym">${m.symbol}</div>
      <div class="name">${m.name}</div>
      <div class="pct">${formatMetric(m.metric || moversMetric, val)}</div>
    `;
    moversWrap.appendChild(div);
  });
}

// Footer ticker using top movers
async function initTicker(){
  const track = document.getElementById('ticker-track') || (document.getElementById('ticker') && document.getElementById('ticker').querySelector('.ticker-track'));
  if (!track) return;
  try{
    const res = await fetch('/api/top-movers?metric=change_24h&limit=12');
    const items = await res.json();
    track.innerHTML = '';
    const make = (m) => {
      const val = (m.value !== undefined ? m.value : m.change_24h);
      const up = Number(val) >= 0;
      const el = document.createElement('div');
      el.className = 'tick-item';
      el.innerHTML = `<span class="sym">${m.symbol}</span><span class="val ${up?'up':'down'}">${formatMetric(m.metric || 'change_24h', val)}</span>`;
      return el;
    };
    // Duplicate to create continuous strip
    for (let k=0; k<2; k++){
      (items || []).forEach(m => track.appendChild(make(m)));
    }
  } catch(e){ /* noop */ }
}

async function loadTokens(){
  bindTokensTableSorting();
  await fetchTokensData();
  if (!window.TB_USE_HOME_INIT){
    await loadTopMovers();
  }
}


async function loadGlobalCharts(range='30d'){
  const res = await fetch(`/api/chart/global?range=${encodeURIComponent(range)}`);
  const d = await res.json();

  const ctx1 = document.getElementById('globalTokensChart');
  const ctx2 = document.getElementById('globalHoldersChart');
  if (!ctx1 || !ctx2) return; // charts not present on this page

  const isArena = document.body.classList.contains('arena');
  const tickColor = isArena ? '#9ca3af' : '#64748b';
  const gridColor = isArena ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)';
  const legendColor = isArena ? '#e5e7eb' : '#0f172a';

  const commonOptions = {
    responsive: true,
    scales: {
      x: { ticks: { color: tickColor }, grid: { color: gridColor } },
      y: { ticks: { color: tickColor }, grid: { color: gridColor } },
    },
    plugins: {
      legend: { labels: { color: legendColor } },
      tooltip: { mode: 'index', intersect: false },
    }
  };

  if (tokensChart) tokensChart.destroy();
  if (holdersChart) holdersChart.destroy();

  const chartType = (localStorage.getItem('tb_chart_type') || 'line');
  const tokensBaseType = (chartType === 'bar') ? 'bar' : 'line';
  const indicator = (localStorage.getItem('tb_indicator') || 'none');
  // Simple SMA overlay
  function simpleSMA(arr, windowSize=5){
    const out = [];
    for (let i=0; i<arr.length; i++){
      const s = Math.max(0, i - windowSize + 1);
      let sum = 0, c = 0;
      for (let j=s; j<=i; j++){ sum += Number(arr[j]||0); c++; }
      out.push(c ? Number((sum/c).toFixed(2)) : 0);
    }
    return out;
  }
  const extraDatasets = [];
  if (indicator === 'sma' || indicator === 'ema'){
    extraDatasets.push({ label: indicator.toUpperCase(), data: simpleSMA(d.tokens, 5), borderColor: '#ffd166', backgroundColor: 'rgba(255,209,102,0.2)', tension: 0.3, fill: false, borderDash: [4,3] });
  }
  tokensChart = new Chart(ctx1, {
    type: tokensBaseType,
    data: {
      labels: d.labels,
      datasets: ([{
        label: 'Tokens', data: d.tokens,
        borderColor: '#7c5cff', backgroundColor: 'rgba(124,92,255,0.2)', tension: 0.3,
        fill: true
      }]).concat(extraDatasets)
    },
    options: commonOptions
  });

  holdersChart = new Chart(ctx2, {
    type: 'line',
    data: {
      labels: d.labels,
      datasets: [{
        label: 'Holders', data: d.holders,
        borderColor: '#00d1b2', backgroundColor: 'rgba(0,209,178,0.2)', tension: 0.3,
        fill: true
      }]
    },
    options: commonOptions
  });
}

window.addEventListener('DOMContentLoaded', async () => {
  // If home.js is present, it will render Overview and Top Movers.
  if (!window.TB_USE_HOME_INIT){
    setSkeletonStats(true);
    await loadOverview();
    setSkeletonStats(false);
  }
  await loadTokens();
  // range toggle
  const rangeWrap = document.getElementById('global-range');
  let currentRange = localStorage.getItem('tb_global_range') || '30d';
  window.TB = window.TB || {};
  window.TB.globalRange = currentRange;
  if (rangeWrap){
    // reflect stored range
    const btnStored = rangeWrap.querySelector(`.btn[data-range="${currentRange}"]`);
    if (btnStored){
      rangeWrap.querySelectorAll('.btn').forEach(b=>b.classList.remove('active'));
      btnStored.classList.add('active');
    }
    rangeWrap.addEventListener('click', (e) => {
      const btn = e.target.closest('.btn');
      if (!btn) return;
      currentRange = btn.dataset.range;
      rangeWrap.querySelectorAll('.btn').forEach(b=>b.classList.remove('active'));
      btn.classList.add('active');
      localStorage.setItem('tb_global_range', currentRange);
      window.TB.globalRange = currentRange;
      loadGlobalCharts(currentRange);
    });
  }
  await loadGlobalCharts(currentRange);
  await loadChangelogWidget();

  // Optional chart controls (Arena advanced UI)
  const chartTypeSeg = document.getElementById('chart-type');
  if (chartTypeSeg){
    const stored = localStorage.getItem('tb_chart_type') || 'line';
    const btnStored = chartTypeSeg.querySelector(`.btn[data-type="${stored}"]`);
    if (btnStored){ chartTypeSeg.querySelectorAll('.btn').forEach(b=>b.classList.remove('active')); btnStored.classList.add('active'); }
    chartTypeSeg.addEventListener('click', (e) => {
      const btn = e.target.closest('.btn'); if (!btn) return;
      chartTypeSeg.querySelectorAll('.btn').forEach(b=>b.classList.remove('active'));
      btn.classList.add('active');
      localStorage.setItem('tb_chart_type', btn.dataset.type);
      loadGlobalCharts(window.TB && TB.globalRange ? TB.globalRange : currentRange);
    });
  }
  const indicatorsSeg = document.getElementById('indicators');
  if (indicatorsSeg){
    const storedI = localStorage.getItem('tb_indicator') || 'none';
    const btnStoredI = indicatorsSeg.querySelector(`.btn[data-indicator="${storedI}"]`);
    if (btnStoredI){ indicatorsSeg.querySelectorAll('.btn').forEach(b=>b.classList.remove('active')); btnStoredI.classList.add('active'); }
    indicatorsSeg.addEventListener('click', (e) => {
      const btn = e.target.closest('.btn'); if (!btn) return;
      indicatorsSeg.querySelectorAll('.btn').forEach(b=>b.classList.remove('active'));
      btn.classList.add('active');
      localStorage.setItem('tb_indicator', btn.dataset.indicator);
      loadGlobalCharts(window.TB && TB.globalRange ? TB.globalRange : currentRange);
    });
  }

  // Reset filters and Save View (Arena advanced UI)
  const resetBtn = document.getElementById('reset-filters');
  if (resetBtn){
    resetBtn.addEventListener('click', () => {
      localStorage.removeItem('tb_tokens_query');
      localStorage.removeItem('tb_min_mcap');
      localStorage.removeItem('tb_min_volume');
      localStorage.setItem('tb_sort_key','market_cap_usd');
      localStorage.setItem('tb_sort_dir','desc');
      localStorage.setItem('tb_sort_metric','0');
      tokensQuery=''; minMcap=''; minVolume=''; sortKey='market_cap_usd'; sortDir='desc'; sortByMetric=false;
      currentPage = 1; localStorage.setItem('tb_tokens_page','1');
      fetchTokensData();
      if (window.TB && TB.showToast) TB.showToast('Filters reset');
    });
  }
  const saveBtn = document.getElementById('save-view');
  if (saveBtn){
    saveBtn.addEventListener('click', () => {
      const view = { tokensQuery, minMcap, minVolume, sortKey, sortDir, sortByMetric, tableMetric, sparkDays, pageSize, ts: Date.now() };
      localStorage.setItem('tb_saved_view', JSON.stringify(view));
      if (window.TB && TB.showToast) TB.showToast('View saved');
    });
  }
  const tableViewSeg = document.getElementById('table-view');
  if (tableViewSeg){
    const curView = localStorage.getItem('tb_table_view') || 'table';
    const btnStored = tableViewSeg.querySelector(`.btn[data-view="${curView}"]`);
    if (btnStored){ tableViewSeg.querySelectorAll('.btn').forEach(b=>b.classList.remove('active')); btnStored.classList.add('active'); }
    tableViewSeg.addEventListener('click', (e) => {
      const btn = e.target.closest('.btn'); if (!btn) return;
      tableViewSeg.querySelectorAll('.btn').forEach(b=>b.classList.remove('active'));
      btn.classList.add('active');
      localStorage.setItem('tb_table_view', btn.dataset.view);
      if (window.TB && TB.showToast) TB.showToast(`View: ${btn.dataset.view}`);
    });
  }

  // Footer ticker (uses top movers)
  initTicker();

  // Demo presets segmented control (home)
  const demoPresets = document.getElementById('demo-presets-buttons');
  if (demoPresets){
    demoPresets.addEventListener('click', (e) => {
      const btn = e.target.closest('.btn');
      if (!btn) return;
      const preset = btn.dataset.preset;
      if (!preset) return;
      // Toggle UI state
      demoPresets.querySelectorAll('.btn').forEach(b=>b.classList.remove('active'));
      btn.classList.add('active');
      // Apply preset (this seeds data) and ensure demo is on
      if (window.TB && TB.applyDemoPreset){ TB.applyDemoPreset(preset); }
      if (window.TB && TB.enableMock){ TB.enableMock(true); }
    });
  }

  // movers metric segmented (skip if home.js manages it)
  if (!window.TB_USE_HOME_INIT){
    const moversSeg = document.getElementById('movers-metric');
    if (moversSeg){
      const btnStored = moversSeg.querySelector(`.btn[data-metric="${moversMetric}"]`);
      if (btnStored){
        moversSeg.querySelectorAll('.btn').forEach(b=>b.classList.remove('active'));
        btnStored.classList.add('active');
      }
      moversSeg.addEventListener('click', async (e) => {
        const btn = e.target.closest('.btn');
        if (!btn) return;
        moversSeg.querySelectorAll('.btn').forEach(b=>b.classList.remove('active'));
        btn.classList.add('active');
        moversMetric = btn.dataset.metric;
        localStorage.setItem('tb_movers_metric', moversMetric);
        await loadTopMovers();
      });
    }
  }

  // table metric segmented
  const tableSeg = document.getElementById('table-metric');
  const metricLabelEl = document.getElementById('metric-col-label');
  if (metricLabelEl) metricLabelEl.innerHTML = `${metricLabel(tableMetric)} <span class="arrow">▼</span>`;
  if (tableSeg){
    const btnStored = tableSeg.querySelector(`.btn[data-metric="${tableMetric}"]`);
    if (btnStored){
      tableSeg.querySelectorAll('.btn').forEach(b=>b.classList.remove('active'));
      btnStored.classList.add('active');
    }
    tableSeg.addEventListener('click', (e) => {
      const btn = e.target.closest('.btn');
      if (!btn) return;
      tableSeg.querySelectorAll('.btn').forEach(b=>b.classList.remove('active'));
      btn.classList.add('active');
      tableMetric = btn.dataset.metric;
      localStorage.setItem('tb_table_metric', tableMetric);
      if (metricLabelEl) metricLabelEl.innerHTML = `${metricLabel(tableMetric)} <span class="arrow">▼</span>`;
      if (sortByMetric) sortTokensDataByMetric();
      renderTokensTable();
    });
  }

  // page-size selector
  const sel = document.getElementById('page-size');
  if (sel){
    // reflect stored
    if ([10,25,50].includes(pageSize)) sel.value = String(pageSize);
    sel.addEventListener('change', () => {
      const v = parseInt(sel.value, 10);
      if (!v) return;
      pageSize = v;
      localStorage.setItem('tb_tokens_page_size', String(pageSize));
      currentPage = 1;
      localStorage.setItem('tb_tokens_page', '1');
      fetchTokensData();
    });
  }

  // filter box
  const filter = document.getElementById('tokens-filter');
  if (filter){
    filter.value = tokensQuery;
    let t;
    filter.addEventListener('input', () => {
      window.clearTimeout(t);
      t = window.setTimeout(() => {
        tokensQuery = filter.value.trim();
        localStorage.setItem('tb_tokens_query', tokensQuery);
        currentPage = 1;
        localStorage.setItem('tb_tokens_page', '1');
        fetchTokensData();
      }, 250);
    });
  }

  // threshold inputs
  const minMcapEl = document.getElementById('min-mcap');
  const minVolEl = document.getElementById('min-volume');
  if (minMcapEl){ minMcapEl.value = minMcap; }
  if (minVolEl){ minVolEl.value = minVolume; }
  const debounce = (fn, d=300) => { let id; return (...a)=>{ clearTimeout(id); id=setTimeout(()=>fn(...a), d); }; };
  const onThresh = debounce(() => {
    minMcap = (minMcapEl && minMcapEl.value) ? minMcapEl.value : '';
    minVolume = (minVolEl && minVolEl.value) ? minVolEl.value : '';
    localStorage.setItem('tb_min_mcap', minMcap);
    localStorage.setItem('tb_min_volume', minVolume);
    currentPage = 1; localStorage.setItem('tb_tokens_page', '1');
    fetchTokensData();
    loadTopMovers();
  }, 300);
  if (minMcapEl){ minMcapEl.addEventListener('input', onThresh); }
  if (minVolEl){ minVolEl.addEventListener('input', onThresh); }

  // sparkline range toggle
  const spark = document.getElementById('spark-range');
  const sparkLabel = document.getElementById('spark-col-label');
  if (spark && sparkLabel){
    // reflect stored
    const btnStored = spark.querySelector(`.btn[data-days="${sparkDays}"]`);
    if (btnStored){
      spark.querySelectorAll('.btn').forEach(b=>b.classList.remove('active'));
      btnStored.classList.add('active');
      sparkLabel.textContent = `${sparkDays}d`;
    }
    spark.addEventListener('click', (e) => {
      const btn = e.target.closest('.btn');
      if (!btn) return;
      spark.querySelectorAll('.btn').forEach(b=>b.classList.remove('active'));
      btn.classList.add('active');
      sparkDays = parseInt(btn.dataset.days, 10) || 7;
      localStorage.setItem('tb_spark_days', String(sparkDays));
      sparkLabel.textContent = `${sparkDays}d`;
      fetchTokensData();
    });
  }

  // export CSV (current page)
  const exportBtn = document.getElementById('export-csv');
  if (exportBtn){
    exportBtn.addEventListener('click', () => {
      const rows = tokensData.map((t, i) => ({
        rank: (currentPage-1)*pageSize + i + 1,
        symbol: t.symbol,
        name: t.name,
        price_usd: t.price_usd,
        market_cap_usd: t.market_cap_usd,
        holders_count: t.holders_count,
        metric: metricLabel(tableMetric),
        metric_value: formatMetric(tableMetric, metricValue(t, tableMetric)),
        change_24h: t.change_24h,
      }));
      const headers = ['Rank','Symbol','Name','PriceUSD','MarketCapUSD','Holders','Metric','MetricVal','Change24h'];
      const csv = [headers.join(',')].concat(rows.map(r => [r.rank,r.symbol,r.name,r.price_usd,r.market_cap_usd,r.holders_count,r.metric,r.metric_value,r.change_24h].join(','))).join('\n');
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `token-arena-page-${currentPage}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      if (window.TB && window.TB.showToast) window.TB.showToast('Exported current page as CSV');
    });
  }
  // Respond to theme changes by redrawing charts with new colors
  window.addEventListener('themechange', () => {
    const r = (window.TB && window.TB.globalRange) ? window.TB.globalRange : (localStorage.getItem('tb_global_range') || '30d');
    loadGlobalCharts(r);
  });
});

function sortTokensDataByMetric(){
  const m = tableMetric;
  const asc = sortDir === 'asc';
  tokensData.sort((a, b) => {
    const va = Number(metricValue(a, m));
    const vb = Number(metricValue(b, m));
    const aa = Number.isFinite(va) ? va : -Infinity;
    const bb = Number.isFinite(vb) ? vb : -Infinity;
    return asc ? (aa - bb) : (bb - aa);
  });
}
