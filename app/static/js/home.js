// Homepage isolated init: Market Overview + Top Movers with sparklines
// Sets a guard to prevent main.js from duplicating this logic
(function(){
  window.TB_USE_HOME_INIT = true;

  function bySymbolMap(list){
    const m = new Map();
    (list||[]).forEach(t => { if (t && t.symbol) m.set(String(t.symbol).toUpperCase(), t); });
    return m;
  }

  // Top marquee ticker (home)
  async function loadHomeTicker(){
    const wrap = document.getElementById('home-ticker');
    if (!wrap) return;
    wrap.innerHTML = '';
    try{
      const r = await fetch('/api/top-movers?metric=change_24h&limit=12');
      const items = await r.json();
      const track = document.createElement('div');
      track.className = 'ticker-track';
      const make = (m)=>{
        const val = (m.value !== undefined ? m.value : m.change_24h);
        const up = Number(val) >= 0; const d = document.createElement('div'); d.className='tick-item';
        d.innerHTML = `<span class="sym">${m.symbol}</span><span class="val ${up?'up':'down'}">${(Number(val)>=0?'+':'')+Number(val).toFixed(2)}%</span>`; return d;
      };
      for (let k=0;k<2;k++){ (items||[]).forEach(m=>track.appendChild(make(m))); }
      wrap.appendChild(track);
    } catch{}
  }

  // Weekly battle: head-to-head of top 4 by mcap
  async function loadWeeklyBattle(){
    const cont = document.getElementById('weekly-battle');
    if (!cont) return;
    cont.innerHTML = '<div class="muted">Loading matchups…</div>';
    try{
      const r = await fetch('/api/tokens?page=1&page_size=4&sort=market_cap_usd&dir=desc&sparkline=1&days=7');
      const data = await r.json();
      const items = (data && data.items) || [];
      if (items.length < 2){ cont.innerHTML = '<div class="muted">Not enough tokens for battles</div>'; return; }
      const mkCard = (t)=>{
        const el = document.createElement('div'); el.className='wb-card';
        const ch = (t.change_24h||0); const up = Number(ch)>=0;
        el.innerHTML = `
          <div class="wb-head"><span class="sym">${t.symbol}</span><span class="name">${t.name||''}</span></div>
          <div class="wb-spark">${(window.sparklineSVG? sparklineSVG(t.sparkline||[]) : '')}</div>
          <div class="wb-meta">MCap ${t.market_cap_usd? new Intl.NumberFormat('en-US',{notation:'compact',compactDisplay:'short'}).format(t.market_cap_usd):'—'} · <span class="${up?'up':'down'}">${(Number(ch)>=0?'+':'')+Number(ch).toFixed(2)}%</span></div>
        `; return el;
      };
      function loadVotes(){ try{ return JSON.parse(localStorage.getItem('tb_battle_votes')||'{}'); }catch{ return {}; } }
      function saveVotes(v){ try{ localStorage.setItem('tb_battle_votes', JSON.stringify(v)); }catch{} }
      function renderBars(ctrl, aSym, bSym, votes){
        const key = `${aSym}_vs_${bSym}`;
        const st = votes[key] || { A: 0, B: 0, choice: null };
        const total = Math.max(1, st.A + st.B);
        const aPct = Math.round((st.A/total)*100);
        const bPct = 100 - aPct;
        ctrl.querySelector('.wb-bar-a .fill').style.width = aPct + '%';
        ctrl.querySelector('.wb-bar-b .fill').style.width = bPct + '%';
        ctrl.querySelector('.wb-bar-a .pct').textContent = aPct + '%';
        ctrl.querySelector('.wb-bar-b .pct').textContent = bPct + '%';
        ctrl.querySelectorAll('button').forEach(btn=>btn.classList.remove('active'));
        if (st.choice === 'A') ctrl.querySelector('.vote-a').classList.add('active');
        if (st.choice === 'B') ctrl.querySelector('.vote-b').classList.add('active');
      }
      function makeCtrl(aSym, bSym){
        const div = document.createElement('div');
        div.className = 'wb-ctrl';
        div.innerHTML = `
          <div class="wb-bars">
            <div class="wb-bar wb-bar-a"><div class="fill"></div><span class="pct">0%</span></div>
            <div class="wb-bar wb-bar-b"><div class="fill"></div><span class="pct">0%</span></div>
          </div>
          <div class="wb-actions">
            <button class="btn small vote-a" aria-pressed="false">Vote ${aSym}</button>
            <button class="btn small vote-b" aria-pressed="false">Vote ${bSym}</button>
          </div>
        `;
        const votes = loadVotes();
        renderBars(div, aSym, bSym, votes);
        div.querySelector('.vote-a').addEventListener('click', ()=>{
          const v = loadVotes(); const key = `${aSym}_vs_${bSym}`; v[key] = v[key] || { A: 0, B: 0, choice: null };
          if (v[key].choice !== 'A'){ v[key].A += 1; v[key].choice = 'A'; saveVotes(v); renderBars(div, aSym, bSym, v); }
        });
        div.querySelector('.vote-b').addEventListener('click', ()=>{
          const v = loadVotes(); const key = `${aSym}_vs_${bSym}`; v[key] = v[key] || { A: 0, B: 0, choice: null };
          if (v[key].choice !== 'B'){ v[key].B += 1; v[key].choice = 'B'; saveVotes(v); renderBars(div, aSym, bSym, v); }
        });
        return div;
      }
      const grid = document.createElement('div'); grid.className='wb-grid';
      const vs1 = document.createElement('div'); vs1.className='wb-match';
      const vs2 = document.createElement('div'); vs2.className='wb-match';
      const a1 = items[0], b1 = items[1];
      vs1.appendChild(mkCard(a1)); vs1.appendChild(document.createElement('div')).className='wb-vs'; vs1.lastChild.textContent='VS'; vs1.appendChild(mkCard(b1));
      vs1.appendChild(makeCtrl(a1.symbol, b1.symbol));
      if (items[2]){
        const a2 = items[2], b2 = items[3] || items[0];
        vs2.appendChild(mkCard(a2)); vs2.appendChild(document.createElement('div')).className='wb-vs'; vs2.lastChild.textContent='VS'; vs2.appendChild(mkCard(b2));
        vs2.appendChild(makeCtrl(a2.symbol, b2.symbol));
      }
      grid.appendChild(vs1); if (items[2]) grid.appendChild(vs2);
      cont.innerHTML=''; cont.appendChild(grid);
    } catch{ cont.innerHTML = ''; }
  }

  // Spotlights: competitions and sources
  async function loadSpotlights(){
    const compWrap = document.getElementById('spotlight-competitions');
    const srcWrap = document.getElementById('spotlight-sources');
    try{
      if (compWrap){
        const r = await fetch('/api/competitions'); const list = await r.json();
        compWrap.innerHTML = '';
        (list||[]).slice(0,3).forEach(c => {
          const d = document.createElement('div'); d.className='spot-card';
          d.innerHTML = `<div class="spot-title">${c.title||c.slug}</div><div class="spot-desc muted small">${c.description||''}</div><div class="spot-meta">${(c.status||'').toUpperCase()}</div>`;
          compWrap.appendChild(d);
        });
      }
    } catch{}
    try{
      if (srcWrap){
        const r = await fetch('/api/datasources'); const rows = await r.json();
        srcWrap.innerHTML = '';
        (rows||[]).slice(0,3).forEach(s => {
          const d = document.createElement('div'); d.className='spot-card';
          d.innerHTML = `<div class="spot-title">${s.name||s.slug}</div><div class="spot-desc muted small">${s.description||''}</div><div class="spot-meta">${(s.status||'operational')}</div>`;
          srcWrap.appendChild(d);
        });
      }
    } catch{}
  }
  // helpers
  function easeOutCubic(t){ return 1 - Math.pow(1 - t, 3); }
  function countUp(el, to, duration=1200, fmt=(v)=>String(v)){
    if (!el) return;
    const start = performance.now();
    const from = 0;
    function tick(now){
      const p = Math.min(1, (now - start)/duration);
      const v = from + (to - from) * easeOutCubic(p);
      el.textContent = fmt(v);
      if (p < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  function fmtInt(n){ try{ return Math.round(n).toLocaleString(); }catch{ return String(Math.round(n)); } }
  function fmtUSD(n){ try{ return new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format(Math.round(n)); }catch{ return '$'+fmtInt(n); } }

  async function loadOverviewIsolated(){
    try{
      if (typeof setSkeletonStats === 'function') setSkeletonStats(true);
      // Use shared loader for stats on page
      await (typeof loadOverview === 'function' ? loadOverview() : Promise.resolve());
      // Fetch raw numbers for hero counters
      let d = null;
      try{ const r = await fetch('/api/overview'); d = await r.json(); } catch {}
      const heroTokens = document.getElementById('hero-tokens');
      const heroHolders = document.getElementById('hero-holders');
      const heroVolume = document.getElementById('hero-volume');
      if (d){
        if (heroTokens) countUp(heroTokens, Number(d.total_tokens||0), 1200, fmtInt);
        if (heroHolders) countUp(heroHolders, Number(d.total_holders||0), 1200, fmtInt);
        if (heroVolume) countUp(heroVolume, Number(d.volume_24h_usd||0), 1200, fmtUSD);
      }
    } finally {
      if (typeof setSkeletonStats === 'function') setSkeletonStats(false);
    }
  }

  async function loadTopMoversWithSpark(){
    const moversWrap = document.getElementById('top-movers');
    if (!moversWrap) return;
    moversWrap.innerHTML = '';

    const metric = (window.localStorage.getItem('tb_movers_metric') || 'change_24h');
    const limit = 8;

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
    await loadHomeTicker();
    await loadWeeklyBattle();
    await loadSpotlights();
    wireMoversSegmented();
    await loadTopMoversWithSpark();
  });
})();
