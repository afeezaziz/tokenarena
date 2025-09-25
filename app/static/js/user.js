/* global Chart */

function fmtCurrency(n) {
  try { return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n); } catch { return `$${Number(n).toLocaleString()}`; }
}
function fmtNumber(n) {
  try { return new Intl.NumberFormat('en-US').format(n); } catch { return Number(n).toLocaleString(); }
}

let allocChart;

async function loadUserPage(){
  const root = document.getElementById('user-page');
  if (!root) return;
  const npub = root.dataset.npub;
  try {
    const res = await fetch(`/api/user/${encodeURIComponent(npub)}`);
    if (!res.ok) throw new Error('User not found');
    const d = await res.json();

    // Header
    const name = d.user.display_name || (d.user.npub_bech32 ? d.user.npub_bech32.slice(0,12)+'…' : d.user.npub.slice(0,8)+'…');
    document.getElementById('user-name').textContent = name;
    document.getElementById('user-npub').textContent = d.user.npub_bech32 || d.user.npub;
    const avatar = document.getElementById('user-avatar');
    if (d.user.avatar_url){
      avatar.style.backgroundImage = `url(${d.user.avatar_url})`;
      avatar.style.backgroundSize = 'cover';
      avatar.style.backgroundPosition = 'center';
      avatar.textContent = '';
    }

    // Stats
    document.getElementById('portfolio-value').textContent = fmtCurrency(d.portfolio.total_value_usd || 0);
    document.getElementById('tokens-held').textContent = fmtNumber(d.portfolio.total_tokens || 0);

    // Holdings table
    const tbody = document.getElementById('holdings-tbody');
    tbody.innerHTML = '';
    d.portfolio.holdings.forEach(h => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><strong>${h.symbol}</strong> <span class="muted">${h.name}</span></td>
        <td>${fmtNumber(h.quantity)}</td>
        <td>${fmtCurrency(h.price_usd)}</td>
        <td>${fmtCurrency(h.value_usd)}</td>
        <td>${h.pct.toFixed(1)}%</td>
      `;
      tbody.appendChild(tr);
    });

    // Allocation chart
    if (allocChart) allocChart.destroy();
    const ctx = document.getElementById('allocChart');
    const labels = d.portfolio.holdings.map(h => h.symbol);
    const data = d.portfolio.holdings.map(h => h.value_usd);
    const palette = ['#7c5cff','#00d1b2','#ff5c7c','#ffd166','#06d6a0','#118ab2','#ef476f','#8338ec','#fb5607','#3a86ff'];
    allocChart = new Chart(ctx, {
      type: 'doughnut',
      data: { labels, datasets: [{ data, backgroundColor: labels.map((_,i)=>palette[i%palette.length]) }] },
      options: {
        plugins: { legend: { labels: { color: (document.body.classList.contains('arena') ? '#e5e7eb' : '#0f172a') } } }
      }
    });
    // Update legend colors when theme toggles
    window.addEventListener('themechange', () => {
      if (!allocChart) return;
      const legendColor = document.body.classList.contains('arena') ? '#e5e7eb' : '#0f172a';
      allocChart.options.plugins.legend.labels.color = legendColor;
      allocChart.update();
    });
  } catch (e) {
    console.error(e);
  }
}

window.addEventListener('DOMContentLoaded', loadUserPage);
