// Homepage isolated init: Market Overview + Top Movers with sparklines
// Sets a guard to prevent main.js from duplicating this logic
(function(){
  window.TB_USE_HOME_INIT = true;

  function bySymbolMap(list){
    const m = new Map();
    (list||[]).forEach(t => { if (t && t.symbol) m.set(String(t.symbol).toUpperCase(), t); });
    return m;
  }

  // Lucky Spin
  function initLuckySpin(){
    const btn = document.getElementById('spin-btn'); const out = document.getElementById('spin-result');
    if (!btn || !out) return;
    btn.addEventListener('click', async ()=>{
      out.classList.remove('spin-animate'); out.textContent = 'Spinning…';
      try{
        const r = await fetch('/api/tokens?page=1&page_size=100&sort=market_cap_usd&dir=desc&sparkline=1&days=7');
        const data = await r.json(); const items = (data && data.items) || [];
        if (!items.length){ out.textContent='No tokens found.'; return; }
        const pick = items[Math.floor(Math.random()*items.length)];
        const pct = Number(pick.change_24h||0); const up = pct >= 0;
        out.innerHTML = `
          <div class="spin-card">
            <div>
              <div class="spin-sym">${pick.symbol}</div>
              <div class="spin-name">${pick.name||''}</div>
            </div>
            <div class="spin-meta">
              <span class="spin-pct ${up?'up':'down'}">${(up?'+':'')+pct.toFixed(2)}%</span>
              <a href="/t/${encodeURIComponent(pick.symbol)}" class="btn small" style="margin-left:8px">View</a>
            </div>
          </div>
        `;
      } catch {
        out.textContent = 'Spin failed. Try again.';
      }
    });
  }

  // Party Mode
  function initPartyToggle(){
    const btn = document.getElementById('party-toggle'); if (!btn) return;
    function apply(){
      if ((localStorage.getItem('tb_party')||'0') === '1') document.body.classList.add('party'); else document.body.classList.remove('party');
    }
    apply();
    btn.addEventListener('click', ()=>{
      const cur = (localStorage.getItem('tb_party')||'0') === '1';
      localStorage.setItem('tb_party', cur ? '0' : '1');
      apply();
      if (window.TB && TB.showToast) TB.showToast(cur ? 'Party off' : 'Party on!');
    });
  }

  // Tagline rotator (playful)
  function initTaglineRotator(){
    const el = document.getElementById('tagline-rotator');
    if (!el) return;
    const lines = [
      'Battle your watchlist ⚔️',
      'Numbers that go up (or down) 📈',
      'Sharpe it till you make it 🧮',
      'Sparkline snapshot — blink and you’ll miss it ✨',
      'RGB vibes on Bitcoin ⚡',
    ];
    let i = Math.floor(Math.random()*lines.length);
    const setLine = () => { el.textContent = lines[i]; el.classList.remove('fade'); void el.offsetWidth; el.classList.add('fade'); };
    setLine();
    setInterval(()=>{ i = (i+1) % lines.length; setLine(); }, 3000);
  }

  // Loot drop confetti (emoji)
  function bindLootDrop(){
    const btn = document.getElementById('loot-drop');
    if (!btn) return;
    btn.addEventListener('click', ()=>{
      const rect = btn.getBoundingClientRect();
      const centerX = rect.left + rect.width/2; const centerY = rect.top + rect.height/2;
      const emojis = ['🎉','✨','🪙','💎','🎊','⚡'];
      const N = 36;
      for (let k=0;k<N;k++){
        const span = document.createElement('span');
        span.textContent = emojis[Math.floor(Math.random()*emojis.length)];
        span.style.position = 'fixed'; span.style.left = centerX+'px'; span.style.top = centerY+'px';
        span.style.transform = 'translate(-50%, -50%) scale(1)';
        span.style.transition = 'transform 1.2s cubic-bezier(.17,.67,.32,1.2), opacity 1.2s linear';
        span.style.zIndex = '9999'; span.style.fontSize = (18 + Math.random()*10)+'px';
        document.body.appendChild(span);
        const angle = Math.random()*Math.PI*2; const dist = 60 + Math.random()*180;
        requestAnimationFrame(()=>{
          const dx = Math.cos(angle)*dist; const dy = Math.sin(angle)*dist;
          span.style.transform = `translate(calc(-50% + ${dx}px), calc(-50% + ${dy}px)) scale(${0.7 + Math.random()*0.6})`;
          span.style.opacity = '0';
          setTimeout(()=>{ span.remove(); }, 1300);
        });
      }
      if (window.TB && TB.showToast) TB.showToast('Loot dropped!');
    });
  }

  // Daily Quest (playful mini tasks)
  function loadDailyQuest(){
    const wrap = document.getElementById('daily-quest');
    if (!wrap) return;
    const todayKey = new Date().toISOString().slice(0,10);
    const STORE = `tb_daily_quests_${todayKey}`;
    function getState(){ try{ return JSON.parse(localStorage.getItem(STORE)||'{}'); }catch{ return {}; } }
    function setState(v){ try{ localStorage.setItem(STORE, JSON.stringify(v)); }catch{} }
    function updateStreakUI(){
      const pill = document.getElementById('streak-pill'); if (!pill) return;
      const cnt = parseInt(localStorage.getItem('tb_streak_count')||'0',10) || 0;
      pill.textContent = `🔥 ${cnt}-day streak`;
    }
    function markStreakIfFirstToday(){
      const last = localStorage.getItem('tb_streak_last') || '';
      const cnt = parseInt(localStorage.getItem('tb_streak_count')||'0',10) || 0;
      if (last === todayKey) { updateStreakUI(); return; }
      // compute yesterday
      const d = new Date(todayKey + 'T00:00:00Z'); const y = new Date(d.getTime() - 24*3600*1000);
      const yKey = y.toISOString().slice(0,10);
      const nextCnt = (last === yKey) ? (cnt + 1) : 1;
      localStorage.setItem('tb_streak_last', todayKey);
      localStorage.setItem('tb_streak_count', String(nextCnt));
      updateStreakUI();
    }
    const quests = [
      { id: 'vote', icon:'⚔️', title: 'Pick a champion', desc: 'Vote in Weekly Battle', act: ()=>{ const el = document.getElementById('weekly-battle'); if (el) el.scrollIntoView({behavior:'smooth'}); } },
      { id: 'movers', icon:'🚀', title: 'Flip the metric', desc: 'Change Top Movers metric', act: ()=>{ const seg = document.getElementById('movers-metric'); if (seg){ const btn = seg.querySelector('.btn:not(.active)'); btn && btn.click(); } } },
      { id: 'demo', icon:'🧪', title: 'Play in Demo', desc: 'Enable Demo Mode', act: ()=>{ if (window.TB && TB.enableMock){ TB.enableMock(true); } } },
    ];
    const state = getState();
    wrap.innerHTML = '';
    quests.forEach(q => {
      const card = document.createElement('div'); card.className = 'dq-card' + (state[q.id] ? ' done' : '');
      card.innerHTML = `
        <div class="title">${q.icon} ${q.title}</div>
        <div class="desc">${q.desc}</div>
        <div class="actions">
          <button class="btn small do">Do</button>
          <button class="btn small mark">Mark Done</button>
          <button class="btn small reset">Reset</button>
        </div>
      `;
      const doBtn = card.querySelector('.do'); const markBtn = card.querySelector('.mark'); const resetBtn = card.querySelector('.reset');
      doBtn.addEventListener('click', ()=>{ try{ q.act(); }catch{} });
      markBtn.addEventListener('click', ()=>{ const s=getState(); if (!s[q.id]) { s[q.id]=true; setState(s); card.classList.add('done'); markStreakIfFirstToday(); if (window.TB&&TB.showToast) TB.showToast('Quest complete!'); } });
      resetBtn.addEventListener('click', ()=>{ const s=getState(); delete s[q.id]; setState(s); card.classList.remove('done'); });
      wrap.appendChild(card);
    });
    updateStreakUI();
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
    initTaglineRotator();
    bindLootDrop();
    loadDailyQuest();
    initLuckySpin();
    initPartyToggle();
    wireMoversSegmented();
    await loadTopMoversWithSpark();
  });
})();
