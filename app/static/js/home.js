// Homepage isolated init: Market Overview + Top Movers with sparklines
// Sets a guard to prevent main.js from duplicating this logic
(function(){
  window.TB_USE_HOME_INIT = true;

  function bySymbolMap(list){
    const m = new Map();
    (list||[]).forEach(t => { if (t && t.symbol) m.set(String(t.symbol).toUpperCase(), t); });
    return m;
  }

  async function loadOverviewIsolated(){
    try{
      if (typeof setSkeletonStats === 'function') setSkeletonStats(true);
      await (typeof loadOverview === 'function' ? loadOverview() : Promise.resolve());
    } finally {
      if (typeof setSkeletonStats === 'function') setSkeletonStats(false);
    }
  }

  async function loadTopMoversWithSpark(){
    const moversWrap = document.getElementById('top-movers');
    if (!moversWrap) return;
    moversWrap.innerHTML = '';

    const metric = (window.localStorage.getItem('tb_movers_metric') || 'change_24h');
    const limit = 5;

    // Fetch movers and a batch of tokens with sparklines to map against
    const [moversRes, tokensRes] = await Promise.all([
      fetch(`/api/top-movers?metric=${encodeURIComponent(metric)}&limit=${limit}`),
      fetch('/api/tokens?page=1&page_size=500&sparkline=1&days=7&sort=market_cap_usd&dir=desc'),
    ]);
    const movers = await moversRes.json();
    const tokens = await tokensRes.json();
    const map = bySymbolMap(tokens.items || []);

    // Utilities from main.js if available
    const formatMetricSafe = (typeof formatMetric === 'function') ? formatMetric : ((m,v)=>{
      if (v === null || v === undefined || Number.isNaN(Number(v))) return '—';
      const n = Number(v);
      const isPct = m !== 'r7_sharpe' && m !== 'composite';
      return isPct ? `${n>=0?'+':''}${n.toFixed(2)}%` : n.toFixed(2);
    });
    const sparkSVG = (typeof sparklineSVG === 'function') ? sparklineSVG : (()=>'' );

    (movers || []).forEach(m => {
      const sym = String(m.symbol||'').toUpperCase();
      const t = map.get(sym) || {};
      const val = (m.value !== undefined ? m.value : m.change_24h);
      const up = Number(val) >= 0;
      const div = document.createElement('div');
      div.className = `mover ${up?'up':'down'}`;
      const spark = Array.isArray(t.sparkline) ? sparkSVG(t.sparkline) : '';
      div.innerHTML = `
        <div class="sym">${sym}</div>
        <div class="name">${m.name || t.name || ''}</div>
        <div class="pct">${formatMetricSafe(m.metric || metric, val)}</div>
        <div class="spark">${spark}</div>
      `;
      moversWrap.appendChild(div);
    });
  }

  function wireMoversSegmented(){
    const moversSeg = document.getElementById('movers-metric');
    if (!moversSeg) return;
    let moversMetric = localStorage.getItem('tb_movers_metric') || 'change_24h';
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
      await loadTopMoversWithSpark();
    });
  }

  window.addEventListener('DOMContentLoaded', async () => {
    await loadOverviewIsolated();
    wireMoversSegmented();
    await loadTopMoversWithSpark();
  });
})();
