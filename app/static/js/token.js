/* global Chart */

function fmtCurrency(n, frac=2) {
  try { return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: frac }).format(n); } catch { return `$${Number(n).toLocaleString()}`; }
}
function fmtNumber(n) {
  try { return new Intl.NumberFormat('en-US').format(n); } catch { return Number(n).toLocaleString(); }
}
function fmtPct(n){ return `${(Number(n) >= 0 ? '+' : '')}${Number(n).toFixed(2)}%`; }

let priceChart, holdersChart;

async function loadTokenPage(){
  const root = document.getElementById('token-page');
  if (!root) return;
  const symbol = root.dataset.symbol;

  // Details and top holders
  const res = await fetch(`/api/token/${encodeURIComponent(symbol)}`);
  if (!res.ok){ console.error('Token not found'); return; }
  const d = await res.json();

  document.getElementById('tok-name').textContent = d.name;
  document.getElementById('tok-price').textContent = fmtCurrency(d.price_usd, 6);
  document.getElementById('tok-mcap').textContent = fmtCurrency(d.market_cap_usd, 0);
  document.getElementById('tok-holders').textContent = fmtNumber(d.holders_count);
  const changeEl = document.getElementById('tok-change');
  changeEl.textContent = fmtPct(d.change_24h);
  changeEl.style.color = d.change_24h >= 0 ? '#00d1b2' : '#ff5c7c';

  const tbody = document.getElementById('top-holders');
  tbody.innerHTML = '';
  d.top_holders.forEach((r, i) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${i+1}</td>
      <td><a href="/u/${encodeURIComponent(r.npub)}">${r.display_name || r.npub.slice(0,8)+'…'}</a></td>
      <td>${fmtNumber(r.quantity)}</td>
      <td>${fmtCurrency(r.value_usd)}</td>
    `;
    tbody.appendChild(tr);
  });

  // Charts with range toggle
  const rangeWrap = document.getElementById('token-range');
  let currentRange = '30d';
  if (rangeWrap){
    rangeWrap.addEventListener('click', (e) => {
      const btn = e.target.closest('.btn');
      if (!btn) return;
      currentRange = btn.dataset.range;
      rangeWrap.querySelectorAll('.btn').forEach(b=>b.classList.remove('active'));
      btn.classList.add('active');
      loadCharts(symbol, currentRange);
    });
  }
  await loadCharts(symbol, currentRange);
}

async function loadCharts(symbol, range){
  // skeleton placeholder by quickly clearing datasets (optional)
  const res2 = await fetch(`/api/chart/token/${encodeURIComponent(symbol)}?range=${encodeURIComponent(range)}`);
  if (!res2.ok) return;
  const ch = await res2.json();

  const ctx1 = document.getElementById('priceChart');
  const ctx2 = document.getElementById('holdersChart');

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
    plugins: { legend: { labels: { color: legendColor } } }
  };

  if (priceChart) priceChart.destroy();
  if (holdersChart) holdersChart.destroy();

  priceChart = new Chart(ctx1, {
    type: 'line',
    data: { labels: ch.labels, datasets: [{ label: `${symbol} Price`, data: ch.prices, borderColor: '#7c5cff', backgroundColor: 'rgba(124,92,255,0.2)', fill: true, tension: 0.3 }] },
    options: commonOptions
  });

  holdersChart = new Chart(ctx2, {
    type: 'line',
    data: { labels: ch.labels, datasets: [{ label: 'Holders', data: ch.holders, borderColor: '#00d1b2', backgroundColor: 'rgba(0,209,178,0.2)', fill: true, tension: 0.3 }] },
    options: commonOptions
  });
}

window.addEventListener('DOMContentLoaded', loadTokenPage);
