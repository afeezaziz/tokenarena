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

function fmtCurrency(n) {
  try { return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n); } catch { return `$${Number(n).toLocaleString()}`; }
}
function fmtNumber(n) {
  try { return new Intl.NumberFormat('en-US').format(n); } catch { return Number(n).toLocaleString(); }
}
function fmtPct(n){ return `${(Number(n) >= 0 ? '+' : '')}${Number(n).toFixed(2)}%`; }

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
  tokensData.forEach((t, i) => {
    const tr = document.createElement('tr');
    tr.dataset.symbol = t.symbol;
    tr.innerHTML = `
      <td>${(currentPage-1)*pageSize + i + 1}</td>
      <td><a href="/t/${encodeURIComponent(t.symbol)}"><strong>${t.symbol}</strong></a> <span class="muted">${t.name}</span></td>
      <td>${fmtCurrency(t.price_usd)}</td>
      <td>${sparklineSVG(t.sparkline || [])}</td>
      <td>${fmtCurrency(t.market_cap_usd)}</td>
      <td>${fmtNumber(t.holders_count)}</td>
      <td style="color:${t.change_24h>=0?'#00d1b2':'#ff5c7c'}">${fmtPct(t.change_24h)}</td>
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
      h.classList.toggle('active', h.dataset.key === sortKey);
      const arrow = h.querySelector('.arrow');
      if (arrow){ arrow.textContent = (h.dataset.key === sortKey && sortDir === 'asc') ? '▲' : '▼'; }
    });
  }
  updateIndicators();

  headers.forEach(h => {
    h.addEventListener('click', () => {
      const key = h.dataset.key;
      if (sortKey === key) {
        sortDir = sortDir === 'asc' ? 'desc' : 'asc';
      } else {
        sortKey = key;
        sortDir = (key === 'symbol') ? 'asc' : 'desc';
      }
      localStorage.setItem('tb_sort_key', sortKey);
      localStorage.setItem('tb_sort_dir', sortDir);
      updateIndicators();
      // reset to first page when sorting changes
      currentPage = 1;
      localStorage.setItem('tb_tokens_page', String(currentPage));
      fetchTokensData();
    });
  });

  // Row click navigation (event delegation)
  const tbody = document.getElementById('tokens-tbody');
  if (tbody){
    tbody.addEventListener('click', (e) => {
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
  document.getElementById('stat-market-cap').textContent = fmtCurrency(d.total_market_cap_usd || 0);
  document.getElementById('stat-volume').textContent = fmtCurrency(d.volume_24h_usd || 0);
  document.getElementById('stat-tokens').textContent = fmtNumber(d.total_tokens || 0);
  document.getElementById('stat-holders').textContent = fmtNumber(d.total_holders || 0);
  document.getElementById('stat-dominance').textContent = `${(d.dominance_pct || 0).toFixed(2)}%`;
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
      tr.innerHTML = '<td colspan="7"><div class="skeleton" style="height:16px; width:100%"></div></td>';
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
  const res = await fetch(`/api/tokens?${params.toString()}`);
  const data = await res.json();
  tokensData = data.items || [];
  totalCount = data.total || 0;
  renderTokensTable();
  renderPagination();
}

async function loadTopMovers(){
  const moversWrap = document.getElementById('top-movers');
  if (!moversWrap) return;
  moversWrap.innerHTML = '';
  const res = await fetch('/api/top-movers?limit=5');
  const movers = await res.json();
  movers.forEach(m => {
    const div = document.createElement('div');
    div.className = `mover ${m.change_24h>=0?'up':'down'}`;
    div.innerHTML = `
      <div class="sym">${m.symbol}</div>
      <div class="name">${m.name}</div>
      <div class="pct">${fmtPct(m.change_24h)}</div>
    `;
    moversWrap.appendChild(div);
  });
}

async function loadTokens(){
  bindTokensTableSorting();
  await fetchTokensData();
  await loadTopMovers();
}


async function loadGlobalCharts(range='30d'){
  const res = await fetch(`/api/chart/global?range=${encodeURIComponent(range)}`);
  const d = await res.json();

  const ctx1 = document.getElementById('globalTokensChart');
  const ctx2 = document.getElementById('globalHoldersChart');

  const commonOptions = {
    responsive: true,
    scales: {
      x: { ticks: { color: '#64748b' }, grid: { color: 'rgba(0,0,0,0.08)'} },
      y: { ticks: { color: '#64748b' }, grid: { color: 'rgba(0,0,0,0.08)'} },
    },
    plugins: {
      legend: { labels: { color: '#0f172a' } },
      tooltip: { mode: 'index', intersect: false },
    }
  };

  if (tokensChart) tokensChart.destroy();
  if (holdersChart) holdersChart.destroy();

  tokensChart = new Chart(ctx1, {
    type: 'line',
    data: {
      labels: d.labels,
      datasets: [{
        label: 'Tokens', data: d.tokens,
        borderColor: '#7c5cff', backgroundColor: 'rgba(124,92,255,0.2)', tension: 0.3,
        fill: true
      }]
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
  setSkeletonStats(true);
  await loadOverview();
  setSkeletonStats(false);
  await loadTokens();
  // range toggle
  const rangeWrap = document.getElementById('global-range');
  let currentRange = localStorage.getItem('tb_global_range') || '30d';
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
      loadGlobalCharts(currentRange);
    });
  }
  await loadGlobalCharts(currentRange);

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
        change_24h: t.change_24h,
      }));
      const headers = ['Rank','Symbol','Name','PriceUSD','MarketCapUSD','Holders','Change24h'];
      const csv = [headers.join(',')].concat(rows.map(r => [r.rank,r.symbol,r.name,r.price_usd,r.market_cap_usd,r.holders_count,r.change_24h].join(','))).join('\n');
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `token-battles-page-${currentPage}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      if (window.TB && window.TB.showToast) window.TB.showToast('Exported current page as CSV');
    });
  }
});
