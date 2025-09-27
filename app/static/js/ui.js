(function(){
  const toast = document.getElementById('toast');
  function showToast(msg, type='info', dur=2800){
    if (!toast) return;
    toast.textContent = msg;
    toast.dataset.type = type;
    toast.hidden = false;
    window.clearTimeout(showToast.__t);
    showToast.__t = window.setTimeout(()=>{ toast.hidden = true; }, dur);
  }

  function updateActiveNav(){
    const containers = document.querySelectorAll('header .nav, .mobile-nav .mobile-nav-links');
    if (!containers || containers.length === 0) return;
    const curPath = window.location.pathname.replace(/\/$/, '') || '/';
    const curHash = window.location.hash || '';
    containers.forEach(container => {
      const links = container.querySelectorAll('.nav-link');
      links.forEach(a => { a.classList.remove('active'); a.removeAttribute('aria-current'); });
      // Prefer hash-based link when on charts
      if (curHash === '#charts'){
        const chartsLink = Array.from(links).find(a => (a.getAttribute('href')||'').endsWith('/#charts'));
        if (chartsLink){ chartsLink.classList.add('active'); chartsLink.setAttribute('aria-current','page'); return; }
      }
      // Otherwise match by pathname
      let match = null;
      for (const a of links){
        try{
          const u = new URL(a.href, window.location.origin);
          const p = u.pathname.replace(/\/$/, '') || '/';
          const h = u.hash || '';
          if (h) continue; // avoid anchor links here
          if (p === curPath){ match = a; break; }
        } catch { /* noop */ }
      }
      if (match){ match.classList.add('active'); match.setAttribute('aria-current','page'); }
    });
  }
  window.TB = window.TB || {};
  window.TB.showToast = showToast;

  // Theme management
  const THEME_KEY = 'tb_theme'; // 'arena' | 'light'
  function systemPreferredTheme(){
    try {
      return (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'arena' : 'light';
    } catch {
      return 'arena';
    }
  }
  function getStoredTheme(){
    // Force Arena theme always
    try { localStorage.setItem(THEME_KEY, 'arena'); } catch {}
    return 'arena';
  }
  function applyTheme(theme){
    const isArena = theme === 'arena';
    document.body.classList.toggle('arena', isArena);
    const btns = document.querySelectorAll('#theme-toggle, .theme-toggle');
    btns.forEach(btn => {
      // Button shows the action (what you'll switch to)
      btn.textContent = isArena ? '☀ Light' : '☾ Arena';
      btn.setAttribute('aria-pressed', String(isArena));
    });
    // Dispatch global theme change event so charts/UI can react without reloads
    window.dispatchEvent(new CustomEvent('themechange', { detail: { theme } }));
  }
  function setTheme(theme){
    localStorage.setItem(THEME_KEY, theme);
    applyTheme(theme);
  }

  function toggleTheme(){
    // Prevent switching: always enforce Arena
    setTheme('arena');
    if (window.TB && window.TB.showToast){ window.TB.showToast('Arena theme enforced'); }
  }

  // Demo / Mock Data Mode
  const MOCK_KEY = 'tb_mock';
  const originalFetch = window.fetch.bind(window);
  const TB = (window.TB = window.TB || {});
  TB.__mock = TB.__mock || { enabled: false, tokens: null, users: null, user: null, config: null, prng: null };

  const CFG_KEY = 'tb_mock_cfg';
  const DEFAULT_CFG = {
    seed: 1337,
    size: 200,
    volatility: 'normal', // calm | normal | degen
    seriesDays: 30,
    netDelayMs: 0,
    failRatePct: 0,
  };

  function loadMockConfig(){
    try {
      const raw = localStorage.getItem(CFG_KEY);
      const parsed = raw ? JSON.parse(raw) : {};
      return { ...DEFAULT_CFG, ...(parsed || {}) };
    } catch { return { ...DEFAULT_CFG }; }
  }
  function saveMockConfig(cfg){
    try { localStorage.setItem(CFG_KEY, JSON.stringify(cfg)); } catch {}
  }
  function setMockConfig(cfg){ TB.__mock.config = { ...DEFAULT_CFG, ...(cfg || {}) }; saveMockConfig(TB.__mock.config); }

  // Seedable PRNG (Mulberry32)
  function mulberry32(a){
    return function() {
      let t = a += 0x6D2B79F5;
      t = Math.imul(t ^ t >>> 15, t | 1);
      t ^= t + Math.imul(t ^ t >>> 7, t | 61);
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    }
  }
  function setSeed(seed){ TB.__mock.prng = mulberry32((seed>>>0) || 123456789); }

  function isMockEnabled(){ return !!TB.__mock.enabled; }
  function setMockEnabled(v){
    TB.__mock.enabled = !!v;
    localStorage.setItem(MOCK_KEY, TB.__mock.enabled ? '1' : '0');
  }
  TB.isMockEnabled = isMockEnabled;
  TB.enableMock = function(v){
    setMockEnabled(!!v);
    if (TB.showToast) TB.showToast(isMockEnabled() ? 'Demo mode enabled' : 'Demo mode disabled');
    if (isMockEnabled()){ if (!TB.__mock.tokens) { seedMockData(); } }
    updateDemoButtonUI();
  };
  TB.applyDemoPreset = function(preset){
    const cfg = TB.__mock.config || DEFAULT_CFG;
    const v = { ...cfg };
    if (preset === 'calm-small') { v.volatility='calm'; v.size=100; v.seriesDays=30; }
    else if (preset === 'normal-medium') { v.volatility='normal'; v.size=500; v.seriesDays=30; }
    else if (preset === 'degen-large') { v.volatility='degen'; v.size=1000; v.seriesDays=90; }
    else return;
    setMockConfig(v);
    TB.__mock.tokens = null; TB.__mock.users = null; seedMockData(); updateDemoButtonUI();
    if (TB.showToast) TB.showToast('Preset applied');
  };
  TB.toggleMock = function(){ TB.enableMock(!isMockEnabled()); };

  // Early initialize mock mode and patch fetch so it's active before other DOMContentLoaded handlers run
  ensureFetchPatched();
  setMockEnabled(localStorage.getItem(MOCK_KEY) === '1');

  // Random helpers (seedable)
  function __rand(){ return TB.__mock.prng ? TB.__mock.prng() : Math.random(); }
  function rand(min, max){ return __rand() * (max - min) + min; }
  function randint(min, max){ return Math.floor(rand(min, max+1)); }
  function pick(arr){ return arr[Math.floor(__rand()*arr.length)] }

  // Network simulation for mocks
  async function maybeDelay(){
    const ms = (TB.__mock.config && TB.__mock.config.netDelayMs) || 0;
    if (ms > 0) await new Promise(res => setTimeout(res, ms));
  }
  function maybeFail(){
    const p = (TB.__mock.config && TB.__mock.config.failRatePct) || 0;
    if (p > 0 && __rand()*100 < p){
      return new Response(JSON.stringify({ error: 'mock_failure' }), { status: 500, headers: { 'Content-Type': 'application/json' }});
    }
    return null;
  }

  function symbolFor(i){ return 'TK' + String(i+1).padStart(3,'0'); }
  function volatilityAmp(){
    const v = (TB.__mock.config && TB.__mock.config.volatility) || 'normal';
    if (v === 'calm') return 0.03;
    if (v === 'degen') return 0.25;
    return 0.10; // normal
  }
  function seedMockData(){
    if (TB.__mock.tokens && TB.__mock.users) return;
    const cfg = TB.__mock.config || DEFAULT_CFG;
    // Re-seed PRNG
    setSeed(cfg.seed);
    const N = Math.max(10, Math.min(5000, parseInt(cfg.size||200,10)));
    const tokens = [];
    for (let i=0;i<N;i++){
      const sym = symbolFor(i);
      const basePrice = rand(0.0001, 100);
      const amp = volatilityAmp();
      const price = (basePrice * (1 + rand(-amp, amp))).toFixed(6);
      const mcap = Math.max(1, Math.round(rand(1e5, 5e9)));
      const holders = randint(10, 200000);
      const ch24 = parseFloat((rand(-amp*100, amp*100)).toFixed(2));
      const vol24 = Math.max(0, Math.round(mcap * rand(0.001, 0.6)));
      const sparkLen = 1 + (TB.__mock.sparkDays || cfg.seriesDays || 7);
      const spark = Array.from({length: sparkLen}, ()=> parseFloat((basePrice*(1+rand(-amp,amp))).toFixed(6)));
      tokens.push({
        id: i+1,
        symbol: sym,
        name: sym + ' Token',
        price_usd: parseFloat(price),
        market_cap_usd: mcap,
        volume_24h_usd: vol24,
        holders_count: holders,
        change_24h: ch24,
        last_updated: new Date().toISOString(),
        r7: parseFloat((rand(-amp*300,amp*300)).toFixed(2)),
        r30: parseFloat((rand(-amp*800,amp*800)).toFixed(2)),
        r7_sharpe: parseFloat((rand(-3,3)).toFixed(2)),
        holders_growth_pct_24h: parseFloat((rand(-10,15)).toFixed(2)),
        share_delta_7d: parseFloat((rand(-1,1)).toFixed(2)),
        turnover_pct: parseFloat((rand(0,50)).toFixed(2)),
        composite: parseFloat((rand(-3,3)).toFixed(2)),
        sparkline: spark,
      });
    }
    const users = Array.from({length: 8}, (_, i) => ({
      id: i+1,
      npub: 'demo'+(i+1).toString(16).padStart(8,'0').repeat(8).slice(0,64),
      npub_bech32: null,
      display_name: 'User '+(i+1),
      avatar_url: null,
      bio: 'Demo user',
    }));
    TB.__mock.tokens = tokens;
    TB.__mock.users = users;
  }

  function mockJson(data, status=200){
    return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
  }

  async function mockFetch(input, init){
    const url = typeof input === 'string' ? input : input.url;
    const u = new URL(url, window.location.origin);
    const p = u.pathname;
    if (!TB.__mock.tokens || !TB.__mock.users) { try { seedMockData(); } catch {} }
    await maybeDelay();
    const fail = maybeFail();
    if (fail) return fail;

    // Auth endpoints
    if (p === '/api/auth/me'){
      return mockJson({ user: TB.__mock.user ? {
        npub: TB.__mock.user.npub,
        npub_bech32: TB.__mock.user.npub_bech32 || null,
        display_name: TB.__mock.user.display_name || 'Demo User',
        avatar_url: TB.__mock.user.avatar_url || null,
      } : null });
    }
    if (p === '/api/auth/logout'){
      TB.__mock.user = null;
      return mockJson({ ok: true });
    }
    if (p === '/api/auth/nostr/challenge'){
      return mockJson({ nonce: 'mock-nonce', expires_at: new Date(Date.now()+5*60*1000).toISOString() });
    }
    if (p === '/api/auth/nostr/verify'){
      if (!TB.__mock.user){
        TB.__mock.user = { npub: 'demo'.padEnd(64,'0'), display_name: 'Demo User', avatar_url: null };
      }
      return mockJson({ ok: true, user: { npub: TB.__mock.user.npub, display_name: TB.__mock.user.display_name } });
    }

    // Data seed
    seedMockData();

    if (p === '/api/overview'){
      const total_tokens = TB.__mock.tokens.length;
      const total_holders = TB.__mock.tokens.reduce((a,t)=>a + (t.holders_count||0), 0);
      const total_market_cap_usd = TB.__mock.tokens.reduce((a,t)=>a + (t.market_cap_usd||0), 0);
      const volume_24h_usd = TB.__mock.tokens.reduce((a,t)=>a + (t.volume_24h_usd||0), 0);
      const dominance_pct = (TB.__mock.tokens.reduce((m,t)=>Math.max(m,t.market_cap_usd||0),0) / (total_market_cap_usd||1)) * 100;
      return mockJson({ total_tokens, total_holders, total_market_cap_usd, volume_24h_usd, dominance_pct });
    }

    

    if (p === '/api/top-movers'){
      const metric = (u.searchParams.get('metric')||'change_24h');
      const limit = Math.min(50, Math.max(1, parseInt(u.searchParams.get('limit')||'5',10)));
      const arr = TB.__mock.tokens.slice().sort((a,b)=>{
        const aa = Number.isFinite(+a[metric]) ? +a[metric] : -Infinity;
        const bb = Number.isFinite(+b[metric]) ? +b[metric] : -Infinity;
        return bb - aa;
      }).slice(0, limit).map(t => ({ symbol: t.symbol, name: t.name, value: t[metric], metric }));
      return mockJson(arr);
    }

    if (p === '/api/tokens'){
      const page = Math.max(1, parseInt(u.searchParams.get('page')||'1',10));
      const page_size = Math.min(100, Math.max(1, parseInt(u.searchParams.get('page_size')||'10',10)));
      const q = (u.searchParams.get('q')||'').toLowerCase();
      const min_mcap = parseFloat(u.searchParams.get('min_mcap')||'');
      const min_volume = parseFloat(u.searchParams.get('min_volume')||'');
      const sortKey = (u.searchParams.get('sort')||'market_cap_usd');
      const dir = (u.searchParams.get('dir')||'desc').toLowerCase() === 'asc' ? 'asc' : 'desc';
      const metric = u.searchParams.get('metric') || '';
      const wantSpark = (u.searchParams.get('sparkline')||'0') === '1';
      const days = parseInt(u.searchParams.get('days')||'7', 10) || 7;

      let arr = TB.__mock.tokens.slice();
      if (q){ arr = arr.filter(t => t.symbol.toLowerCase().includes(q) || (t.name||'').toLowerCase().includes(q)); }
      if (!Number.isNaN(min_mcap)) arr = arr.filter(t => (t.market_cap_usd||0) >= min_mcap);
      if (!Number.isNaN(min_volume)) arr = arr.filter(t => (t.volume_24h_usd||0) >= min_volume);

      // Sort: by metric if requested, else by sortKey
      const sKey = metric || sortKey;
      arr.sort((a,b) => {
        const av = Number(a[sKey]); const bv = Number(b[sKey]);
        const aa = Number.isFinite(av) ? av : (sKey==='symbol' ? a.symbol : -Infinity);
        const bb = Number.isFinite(bv) ? bv : (sKey==='symbol' ? b.symbol : -Infinity);
        if (sKey === 'symbol') return dir==='asc' ? String(aa).localeCompare(String(bb)) : String(bb).localeCompare(String(aa));
        return dir==='asc' ? (aa - bb) : (bb - aa);
      });

      const total = arr.length;
      const start = (page - 1) * page_size;
      const pageItems = arr.slice(start, start + page_size).map(t => {
        const item = { ...t };
        if (wantSpark){
          const baseLen = Array.isArray(t.sparkline) ? t.sparkline.length : 0;
          if (baseLen >= days) item.sparkline = t.sparkline.slice(baseLen - days);
          else {
            // generate a small sparkline from current price
            const amp = volatilityAmp(); let base = t.price_usd || rand(0.02, 12);
            item.sparkline = Array.from({length: days}, ()=> parseFloat((base = Math.max(0.0001, base*(1+rand(-amp, amp)))).toFixed(4)));
          }
        }
        return item;
      });
      return mockJson({ items: pageItems, total });
    }

    if (p === '/api/chart/global'){
      const cfg = TB.__mock.config || DEFAULT_CFG;
      const len = (u.searchParams.get('range')||'') === '7d' ? 7 : (u.searchParams.get('range')==='90d' ? 90 : (u.searchParams.get('range')==='all' ? cfg.seriesDays : 30));
      const labels = Array.from({length: len}, (_,i)=>`Day ${i+1}`);
      const amp = volatilityAmp();
      let tok = randint(60, 140);
      const tokens = labels.map(()=> (tok = Math.max(1, Math.round(tok * (1 + rand(-amp/4, amp/4))))));
      let hol = randint(4000, 20000);
      const holders = labels.map(()=> (hol = Math.max(1, Math.round(hol * (1 + rand(-amp/8, amp/6))))));
      return mockJson({ labels, tokens, holders });
    }

    if (p.startsWith('/api/token/')){
      const sym = decodeURIComponent(p.split('/').pop()||'').toUpperCase();
      const t = TB.__mock.tokens.find(x => x.symbol === sym) || TB.__mock.tokens[0];
      const top_holders = Array.from({length: 10}, (_,i)=>({ npub: 'demo'+(i+10).toString(16).padStart(8,'0').repeat(8).slice(0,64), display_name: 'Holder '+(i+1), quantity: randint(10,10000), value_usd: randint(100, 100000) }));
      return mockJson({ name: t.name, price_usd: t.price_usd, market_cap_usd: t.market_cap_usd, holders_count: t.holders_count, change_24h: t.change_24h, top_holders });
    }

    if (p.startsWith('/api/chart/token/')){
      const cfg = TB.__mock.config || DEFAULT_CFG;
      const range = (u.searchParams.get('range')||'');
      const len = range==='7d' ? 7 : range==='90d' ? 90 : range==='all' ? cfg.seriesDays : 30;
      const labels = Array.from({length: len}, (_,i)=>`Day ${i+1}`);
      const amp = volatilityAmp();
      let base = rand(0.02, 12);
      const prices = labels.map(()=> parseFloat((base = Math.max(0.0001, base*(1+rand(-amp, amp)))).toFixed(4)));
      let hol = randint(50, 10000);
      const holders = labels.map(()=> (hol = Math.max(1, Math.round(hol*(1+rand(-amp/6, amp/4))))));
      return mockJson({ labels, prices, holders });
    }

    if (p.startsWith('/api/competition/')){
      const slug = decodeURIComponent(p.split('/').pop()||'');
      const start = new Date(Date.now() - 3*24*3600*1000).toISOString();
      const end = new Date(Date.now() + 4*24*3600*1000).toISOString();
      const leaderboard = Array.from({length: 15}, (_,i)=>({ rank: i+1, npub: 'demo'+(i+20).toString(16).padStart(8,'0').repeat(8).slice(0,64), display_name: 'Trader '+(i+1), score: parseFloat((rand(0, 100)).toFixed(2)) }));
      return mockJson({ title: `Demo Cup: ${slug}`, description: 'A friendly mock competition for demo purposes.', start_at: start, end_at: end, leaderboard });
    }

    if (p === '/api/competitions'){
      const now = Date.now();
      const mk = (slug, title, offsetStartDays, durationDays, participants, status) => {
        const start = new Date(now + offsetStartDays*24*3600*1000).toISOString();
        const end = new Date(now + (offsetStartDays+durationDays)*24*3600*1000).toISOString();
        return { slug, title, description: 'Demo competition', start_at: start, end_at: end, participants, status };
      };
      const list = [
        mk('demo-cup', 'Demo Cup', -3, 7, 124, 'active'),
        mk('speed-run', 'Speed Run', 2, 5, 0, 'upcoming'),
        mk('arena-open', 'Arena Open', -14, 7, 342, 'past'),
        mk('nostr-classic', 'Nostr Classic', -1, 14, 56, 'active'),
      ];
      return mockJson(list);
    }

    if (p === '/api/datasources'){
      const sources = [
        { slug: 'lnfi', name: 'LNFI', description: 'Lightning Fi: token, prices, holders and volume (Nostr native).', coverage: ['tokens','prices','holders','snapshots'], freshness: '~15m', website: 'https://lnfi.io/', status: 'operational', last_sync_at: new Date().toISOString() },
        { slug: 'mempool-relays', name: 'Mempool Relays', description: 'Aggregated relay events for market activity.', coverage: ['relays','activity'], freshness: '~5m', website: 'https://github.com/nostr-protocol/', status: 'operational', last_sync_at: new Date().toISOString() },
      ];
      return mockJson(sources);
    }

    if (p.startsWith('/api/datasource/')){
      const slug = decodeURIComponent(p.split('/').pop()||'');
      const base = {
        'lnfi': {
          slug: 'lnfi', name: 'LNFI', website: 'https://lnfi.io/', description: 'Lightning Fi: token registry, prices, holders, market data.',
          coverage: [
            { key: 'tokens', desc: 'Token registry and metadata' },
            { key: 'prices', desc: 'Spot and historical prices' },
            { key: 'holders', desc: 'Holders count and growth' },
            { key: 'snapshots', desc: 'Daily snapshots for charts' },
          ], status: 'operational', last_sync_at: new Date().toISOString(),
          changelog: [ { version: '2025-09-01', note: 'Added holders growth 24h.' }, { version: '2025-08-15', note: 'Initial integration.' } ]
        },
        'mempool-relays': {
          slug: 'mempool-relays', name: 'Mempool Relays', website: 'https://github.com/nostr-protocol/', description: 'Relay activity and liquidity hints.',
          coverage: [ { key: 'relays', desc: 'Relay list and basic stats' }, { key: 'activity', desc: 'Event rates and spikes' } ],
          status: 'operational', last_sync_at: new Date().toISOString(),
          changelog: [ { version: '2025-09-05', note: 'Added activity spikes.' } ]
        }
      };
      const ds = base[slug] || base['lnfi'];
      return mockJson(ds);
    }

    // Launchpad: assets list
    if (p === '/api/launchpad/assets'){
      // Build a small deterministic set of RGB assets derived from mock tokens
      const rows = (TB.__mock.tokens || []).slice(0, 10).map((t, i) => ({
        id: i+1,
        symbol: (t.symbol || ('RGB'+(i+1))).toUpperCase(),
        name: t.name || ('RGB Asset ' + (i+1)),
        precision: randint(0, 6),
        rln_asset_id: 'rgb1' + String(i).padStart(6, '0') + 'x'.repeat(10),
        pool_exists: i % 3 === 0,
        pool_id: i % 3 === 0 ? (100 + i) : null,
      }));
      return mockJson(rows);
    }

    // Launchpad: mint-and-pool
    if (p === '/api/launchpad/issue_nia_and_pool' && init && (init.method||'').toUpperCase() === 'POST'){
      try { const body = typeof init.body === 'string' ? JSON.parse(init.body) : {}; console.log('Mock issue NIA', body); } catch {}
      const pool_id = randint(200, 999);
      return mockJson({
        ok: true,
        asset: { id: randint(1000, 9999), symbol: 'MOCK', rln_asset_id: 'rgb1mock' },
        pool_id,
        virtual: { btc: 0.25, rgb: 0.25 / 0.00001 },
      });
    }

    // Launchpad: create pool
    if (p === '/api/launchpad/create_pool' && init && (init.method||'').toUpperCase() === 'POST'){
      try { const body = typeof init.body === 'string' ? JSON.parse(init.body) : {}; console.log('Mock create pool', body); } catch {}
      const pool_id = randint(1000, 9999);
      return mockJson({
        ok: true,
        asset: { id: randint(1, 999), symbol: 'EXIST', rln_asset_id: 'rgb1exist' },
        pool_id,
        virtual: { btc: 0.25, rgb: 25000 },
        fees: { fee_bps: 100, lp_fee_bps: 50, platform_fee_bps: 50 },
      });
    }

    // Wallet: BTC balance (RLN)
    if (p === '/api/rln/btcbalance' && init && (init.method||'').toUpperCase() === 'POST'){
      return mockJson({
        onchain: { confirmed_sat: 12345678, total_sat: 15000000 },
        ln: { local_msat: 250000000, remote_msat: 50000000 },
      });
    }

    // Wallet: assets
    if (p === '/api/wallet/assets'){
      const rows = [
        { asset_id: 1, symbol: 'BTC', name: 'Bitcoin', precision: 8, rln_asset_id: null, balance: 0.12345678, available: 0.12000000 },
        { asset_id: 2, symbol: 'ARENA', name: 'Token Arena', precision: 0, rln_asset_id: 'rgb1arena', balance: 5000, available: 4800 },
        { asset_id: 3, symbol: 'RGBX', name: 'RGB X', precision: 2, rln_asset_id: 'rgb1x', balance: 12345.67, available: 12000.00 },
        { asset_id: 4, symbol: 'GAME', name: 'Game Coin', precision: 0, rln_asset_id: 'rgb1game', balance: 42, available: 40 },
      ];
      return mockJson(rows);
    }

    // Wallet: deposits
    if (p === '/api/wallet/deposits'){
      const now = Date.now();
      const rows = [
        { id: 1, asset_id: 1, asset_symbol: 'BTC', amount: 0.01, status: 'settled', external_ref: 'lnbc1...', created_at: new Date(now-86400000).toISOString(), settled_at: new Date(now-86300000).toISOString() },
        { id: 2, asset_id: 2, asset_symbol: 'ARENA', amount: 1000, status: 'pending', external_ref: 'rgb1inv...', created_at: new Date(now-3600000).toISOString(), settled_at: null },
      ];
      return mockJson(rows);
    }

    // Wallet: withdrawals
    if (p === '/api/wallet/withdrawals'){
      const now = Date.now();
      const rows = [
        { id: 3, asset_id: 1, asset_symbol: 'BTC', amount: 0.005, status: 'sent', external_ref: 'bc1q...', created_at: new Date(now-7200000).toISOString(), settled_at: new Date(now-7100000).toISOString() },
        { id: 4, asset_id: 3, asset_symbol: 'RGBX', amount: 250.25, status: 'pending', external_ref: 'rgb1inv...', created_at: new Date(now-1800000).toISOString(), settled_at: null },
      ];
      return mockJson(rows);
    }

    // Wallet: create BTC deposit invoice
    if (p === '/api/wallet/deposit/btc_invoice' && init && (init.method||'').toUpperCase() === 'POST'){
      return mockJson({ ok: true, invoice: 'lnbc1mockinvoicexyz...', deposit_id: randint(1000,9999) });
    }

    // Wallet: create RGB deposit invoice
    if (p === '/api/wallet/deposit/rgb_invoice' && init && (init.method||'').toUpperCase() === 'POST'){
      return mockJson({ ok: true, invoice: 'rgb1mockinvoiceabc...', deposit_id: randint(1000,9999) });
    }

    // Wallet: withdrawal request
    if (p === '/api/wallet/withdraw/request' && init && (init.method||'').toUpperCase() === 'POST'){
      return mockJson({ ok: true, withdrawal_id: randint(1000,9999) });
    }

    if (p.startsWith('/api/user/')){
      const npub = decodeURIComponent(p.split('/').pop()||'');
      const urec = TB.__mock.users[0];
      const holdings = TB.__mock.tokens.slice(0, 8).map(t => ({ symbol: t.symbol, name: t.name, quantity: randint(1, 1000), price_usd: t.price_usd, value_usd: Math.round(t.price_usd * randint(1, 1000)), pct: rand(0,30) }));
      const total_value_usd = holdings.reduce((a,h)=>a + h.value_usd, 0);
      return mockJson({ user: { ...urec, npub_bech32: null }, portfolio: { total_value_usd, total_tokens: holdings.length, holdings } });
    }

    if (p === '/api/search'){
      const q = (u.searchParams.get('q')||'').toLowerCase();
      const tokens = TB.__mock.tokens.filter(t => t.symbol.toLowerCase().includes(q) || (t.name||'').toLowerCase().includes(q)).slice(0, 5);
      const users = TB.__mock.users.filter(us => (us.display_name||'').toLowerCase().includes(q)).slice(0, 5);
      return mockJson({ tokens, users });
    }

    if (p === '/api/changelog'){
      const limit = Math.max(1, Math.min(10, parseInt(u.searchParams.get('limit')||'5',10)));
      const base = [
        { date: '2025-09-25', title: 'Business Pages & Demo Controls', items: ['Added Features, Pricing, Docs, Methodology, About, Contact, Roadmap, Changelog pages', 'Demo Settings: seed, size, volatility, series, delay, fail rate, deep-link presets', 'Settings/Profile fully mocked in Demo Mode'] },
        { date: '2025-09-20', title: 'Competitions & Sources', items: ['Competitions list + details (mock)', 'Data Sources list + details (mock)'] },
        { date: '2025-09-15', title: 'Improvements', items: ['New tokens table empty state', 'Search UX refined'] },
      ];
      return mockJson(base.slice(0, limit));
    }

    if (p === '/api/contact' && init && (init.method||'').toUpperCase() === 'POST'){
      try{ const body = typeof init.body === 'string' ? JSON.parse(init.body) : {}; console.log('Mock contact', body); } catch {}
      return mockJson({ ok: true });
    }

    // Profile & Settings (demo)
    if (p === '/api/profile' && (!init || (init.method||'GET').toUpperCase()==='GET')){
      const urec = TB.__mock.user || TB.__mock.users?.[0] || { npub: 'demo'.padEnd(64,'0'), display_name: 'Demo User', avatar_url: null, bio: '' };
      return mockJson({
        npub: urec.npub,
        npub_bech32: null,
        display_name: urec.display_name || 'Demo User',
        avatar_url: urec.avatar_url || null,
        bio: urec.bio || '',
        joined_at: new Date(Date.now()-7*24*3600*1000).toISOString(),
      });
    }
    if (p === '/api/profile' && init && (init.method||'').toUpperCase()==='POST'){
      try{
        const body = typeof init.body === 'string' ? JSON.parse(init.body) : {};
        TB.__mock.user = TB.__mock.user || { npub: 'demo'.padEnd(64,'0') };
        TB.__mock.user.display_name = (body.display_name || TB.__mock.user.display_name || 'Demo User');
        TB.__mock.user.bio = (body.bio || TB.__mock.user.bio || '');
      } catch {}
      return mockJson({ ok: true });
    }
    if (p === '/api/profile/avatar/presign'){
      // Encourage local upload fallback
      return new Response(JSON.stringify({ error: 's3_disabled' }), { status: 400, headers: { 'Content-Type': 'application/json' } });
    }
    if (p === '/api/profile/avatar'){
      TB.__mock.user = TB.__mock.user || { npub: 'demo'.padEnd(64,'0') };
      // Set a demo avatar
      const url = `https://picsum.photos/seed/${encodeURIComponent(String(TB.__mock.config?.seed||'demo'))}/120`;
      TB.__mock.user.avatar_url = url;
      return mockJson({ ok: true, avatar_url: url });
    }
    if (p === '/api/profile/avatar/complete'){
      const url = `https://picsum.photos/seed/${encodeURIComponent(String(TB.__mock.config?.seed||'demo'))}/120`;
      TB.__mock.user = TB.__mock.user || { npub: 'demo'.padEnd(64,'0') };
      TB.__mock.user.avatar_url = url;
      return mockJson({ ok: true, avatar_url: url });
    }

    // Default passthrough in demo mode if not matched
    return originalFetch(input, init);
  }

  // Patch fetch only when mock is enabled
  function ensureFetchPatched(){
    if (window.fetch === mockFetch) return;
    window.fetch = async (input, init) => {
      if (isMockEnabled()) return mockFetch(input, init);
      return originalFetch(input, init);
    };
  }

  function updateDemoButtonUI(){
    const btn = document.getElementById('demo-toggle');
    if (!btn) return;
    if (isMockEnabled()){
      btn.textContent = 'Demo On';
      btn.classList.add('active');
      btn.setAttribute('aria-pressed', 'true');
    } else {
      btn.textContent = 'Demo Off';
      btn.classList.remove('active');
      btn.setAttribute('aria-pressed', 'false');
    }
    ensureDemoBanner();
  }

  function ensureDemoBanner(){
    let b = document.getElementById('demo-banner');
    if (!isMockEnabled()){
      if (b) b.remove();
      return;
    }
    if (!b){
      b = document.createElement('div');
      b.id = 'demo-banner';
      b.textContent = 'Demo Mode';
      b.style.position = 'fixed'; b.style.top = '10px'; b.style.right = '10px';
      b.style.padding = '6px 10px'; b.style.borderRadius = '999px';
      b.style.fontWeight = '600'; b.style.fontSize = '12px';
      b.style.background = '#7c5cff'; b.style.color = 'white';
      b.style.zIndex = '9999';
      document.body.appendChild(b);
    }
  }

  // Layout: keep space for fixed header/footer using CSS vars
  function updateLayoutVars(){
    try{
      const header = document.querySelector('.site-header');
      const footer = document.querySelector('.site-footer');
      const h = header ? header.offsetHeight : 64;
      const f = footer ? footer.offsetHeight : 40;
      document.body.style.setProperty('--header-h', h + 'px');
      document.body.style.setProperty('--footer-h', f + 'px');
    } catch{}
  }

  function showDemoSettings(){
    let panel = document.getElementById('demo-settings');
    if (!panel){
      panel = document.createElement('div');
      panel.id = 'demo-settings';
      panel.style.position = 'fixed'; panel.style.top = '64px'; panel.style.right = '10px';
      panel.style.width = '320px'; panel.style.maxWidth = '90vw';
      panel.style.background = 'var(--panel, #0b0f1a)';
      panel.style.border = '1px solid var(--border, #2c2f36)'; panel.style.borderRadius = '10px';
      panel.style.padding = '12px'; panel.style.boxShadow = '0 10px 30px rgba(0,0,0,0.25)';
      panel.style.zIndex = '9999';
      panel.innerHTML = `
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
          <strong>Demo Settings</strong>
          <button id="demo-close" class="btn" style="background:transparent;border:1px solid var(--border)">✕</button>
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px">
          <button class="btn" data-preset="calm-small">Calm · Small</button>
          <button class="btn" data-preset="normal-medium">Normal · Medium</button>
          <button class="btn" data-preset="degen-large">Degen · Large</button>
        </div>
        <div class="form-grid" style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
          <label>Seed<input id="demo-seed" type="number" class="search-input small" value="" /></label>
          <label>Size<input id="demo-size" type="number" class="search-input small" value="" /></label>
          <label>Volatility<select id="demo-vol" class="search-input small"><option value="calm">calm</option><option value="normal">normal</option><option value="degen">degen</option></select></label>
          <label>Series<select id="demo-series" class="search-input small"><option value="7">7D</option><option value="30">30D</option><option value="90">90D</option></select></label>
          <label>Delay (ms)<input id="demo-delay" type="number" class="search-input small" min="0" max="5000" /></label>
          <label>Fail %<input id="demo-fail" type="number" class="search-input small" min="0" max="50" /></label>
        </div>
        <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:10px;flex-wrap:wrap">
          <button id="demo-copy" class="btn" title="Copy deep-link with current demo config">Copy Link</button>
          <button id="demo-reset" class="btn">Reset</button>
          <button id="demo-apply" class="btn">Apply</button>
        </div>
      `;
      document.body.appendChild(panel);
      panel.querySelector('#demo-close').addEventListener('click', ()=> panel.remove());
      panel.querySelectorAll('[data-preset]').forEach(btn => btn.addEventListener('click', (e)=>{
        const p = e.currentTarget.dataset.preset;
        TB.applyDemoPreset && TB.applyDemoPreset(p);
      }));
      panel.querySelector('#demo-copy').addEventListener('click', ()=>{
        const cfg = TB.__mock.config || DEFAULT_CFG;
        const sp = new URLSearchParams();
        sp.set('demo','1'); sp.set('seed', String(cfg.seed)); sp.set('size', String(cfg.size));
        sp.set('vol', cfg.volatility); sp.set('series', String(cfg.seriesDays)); sp.set('delay', String(cfg.netDelayMs)); sp.set('fail', String(cfg.failRatePct));
        const link = `${location.origin}${location.pathname}?${sp.toString()}`;
        navigator.clipboard.writeText(link).then(()=>{ if (TB.showToast) TB.showToast('Link copied'); });
      });
      panel.querySelector('#demo-apply').addEventListener('click', ()=>{
        const cfg = TB.__mock.config || DEFAULT_CFG;
        const v = {
          seed: parseInt(document.getElementById('demo-seed').value||cfg.seed,10),
          size: parseInt(document.getElementById('demo-size').value||cfg.size,10),
          volatility: String(document.getElementById('demo-vol').value||cfg.volatility),
          seriesDays: parseInt(document.getElementById('demo-series').value||cfg.seriesDays,10),
          netDelayMs: parseInt(document.getElementById('demo-delay').value||cfg.netDelayMs,10),
          failRatePct: parseFloat(document.getElementById('demo-fail').value||cfg.failRatePct),
        };
        setMockConfig(v);
        // re-seed and regenerate data
        TB.__mock.tokens = null; TB.__mock.users = null;
        seedMockData(); updateDemoButtonUI();
        if (TB.showToast) TB.showToast('Demo settings applied');
      });
      panel.querySelector('#demo-reset').addEventListener('click', ()=>{
        setMockConfig({ ...DEFAULT_CFG });
        TB.__mock.tokens = null; TB.__mock.users = null; seedMockData(); updateDemoButtonUI();
        if (TB.showToast) TB.showToast('Demo settings reset');
      });
    }
    // set current values
    const cfg = TB.__mock.config || DEFAULT_CFG;
    panel.querySelector('#demo-seed').value = cfg.seed;
    panel.querySelector('#demo-size').value = cfg.size;
    panel.querySelector('#demo-vol').value = cfg.volatility;
    panel.querySelector('#demo-series').value = String(cfg.seriesDays === 7 ? 7 : cfg.seriesDays === 90 ? 90 : 30);
    panel.querySelector('#demo-delay').value = cfg.netDelayMs;
    panel.querySelector('#demo-fail').value = cfg.failRatePct;
  }

  window.addEventListener('DOMContentLoaded', () => {
    // Initialize theme from storage
    applyTheme(getStoredTheme());
    // Hook up toggle buttons
    const btn = document.getElementById('theme-toggle');
    if (btn){ btn.addEventListener('click', toggleTheme); }
    document.querySelectorAll('.theme-toggle').forEach(b => b.addEventListener('click', toggleTheme));

    // If user has not explicitly chosen a theme, follow system preference changes
    const hasStored = !!localStorage.getItem(THEME_KEY);
    if (!hasStored && window.matchMedia){
      const mm = window.matchMedia('(prefers-color-scheme: dark)');
      if (mm.addEventListener){
        mm.addEventListener('change', (e) => setTheme(e.matches ? 'arena' : 'light'));
      } else if (mm.addListener){
        // Safari <14
        mm.addListener((e) => setTheme(e.matches ? 'arena' : 'light'));
      }
    }

    // Initialize Demo/Mock mode and inject toggle UI
    ensureFetchPatched();
    // Load config and apply
    setMockConfig(loadMockConfig());
    const storedMock = localStorage.getItem(MOCK_KEY) === '1';
    setMockEnabled(storedMock);
    // Deep link presets e.g., ?demo=1&seed=123&size=500&vol=degen&series=90&delay=300&fail=2
    try{
      const sp = new URLSearchParams(window.location.search);
      if (sp.get('demo') === '1' || sp.get('demo') === 'true'){
        const cfg = { ...TB.__mock.config };
        if (sp.get('seed')) cfg.seed = parseInt(sp.get('seed'),10);
        if (sp.get('size')) cfg.size = parseInt(sp.get('size'),10);
        if (sp.get('vol')) cfg.volatility = String(sp.get('vol'));
        if (sp.get('series')) cfg.seriesDays = parseInt(sp.get('series'),10);
        if (sp.get('delay')) cfg.netDelayMs = parseInt(sp.get('delay'),10);
        if (sp.get('fail')) cfg.failRatePct = parseFloat(sp.get('fail'));
        setMockConfig(cfg);
        TB.enableMock && TB.enableMock(true);
        TB.__mock.tokens = null; TB.__mock.users = null; seedMockData();
        if (TB.showToast) TB.showToast('Demo preset applied');
      }
    } catch {}
    const tools = document.querySelector('.tool-buttons');
    if (tools && !document.getElementById('demo-toggle')){
      const demoBtn = document.createElement('button');
      demoBtn.id = 'demo-toggle';
      demoBtn.className = 'btn';
      demoBtn.type = 'button';
      demoBtn.title = 'Toggle Demo Mode (uses mock data)';
      demoBtn.addEventListener('click', () => TB.toggleMock());
      tools.appendChild(demoBtn);
      const settingsBtn = document.createElement('button');
      settingsBtn.id = 'demo-settings-btn';
      settingsBtn.className = 'btn';
      settingsBtn.type = 'button';
      settingsBtn.title = 'Demo Settings';
      settingsBtn.textContent = 'Demo Settings';
      settingsBtn.addEventListener('click', showDemoSettings);
      tools.appendChild(settingsBtn);
    }
    updateDemoButtonUI();
    ensureDemoBanner();
    updateActiveNav();
    // Layout vars for fixed header/footer
    updateLayoutVars();
    window.addEventListener('resize', updateLayoutVars);
    window.addEventListener('hashchange', updateActiveNav);
    window.addEventListener('popstate', updateActiveNav);

    // Mobile menu toggle
    const mobileToggle = document.getElementById('mobile-toggle');
    const mobileNav = document.getElementById('mobile-nav');
    if (mobileToggle && mobileNav){
      mobileToggle.addEventListener('click', () => {
        const open = document.body.classList.toggle('mobile-menu-open');
        mobileToggle.setAttribute('aria-expanded', String(open));
        updateLayoutVars();
      });
      mobileNav.querySelectorAll('a.nav-link').forEach(a => a.addEventListener('click', () => {
        document.body.classList.remove('mobile-menu-open');
        mobileToggle.setAttribute('aria-expanded', 'false');
        updateLayoutVars();
      }));
      document.addEventListener('keydown', (e)=>{
        if (e.key === 'Escape'){
          document.body.classList.remove('mobile-menu-open');
          updateLayoutVars();
          mobileToggle.setAttribute('aria-expanded', 'false');
        }
      });
    }

    // Newsletter form (simple UX)
    const newsletter = document.getElementById('newsletter-form');
    if (newsletter){
      newsletter.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = newsletter.querySelector('button[type="submit"]');
        const emailInput = newsletter.querySelector('input[name="email"]');
        if (btn){ btn.disabled = true; btn.textContent = 'Subscribing...'; }
        try{
          // No backend endpoint yet; simulate async and toast
          await new Promise(res => setTimeout(res, 500));
          if (window.TB && window.TB.showToast){ window.TB.showToast('Thanks for subscribing!'); }
          if (emailInput) emailInput.value = '';
        } finally {
          if (btn){ btn.disabled = false; btn.textContent = 'Subscribe'; }
        }
      });
    }

    // Footer ticker tape
    (function initTicker(){
      const track = document.getElementById('ticker-track');
      if (!track) return;
      const speedPxPerSec = 70; // adjust for comfortable speed
      async function load(){
        try{
          const [tokensRes, movers24Res, movers7Res] = await Promise.all([
            fetch('/api/tokens?page=1&page_size=100&sort=market_cap_usd&dir=desc'),
            fetch('/api/top-movers?metric=change_24h&limit=12'),
            fetch('/api/top-movers?metric=r7&limit=12'),
          ]);
          const tokensData = await tokensRes.json();
          const movers24 = (await movers24Res.json()) || [];
          const movers7 = (await movers7Res.json()) || [];
          const items = Array.isArray(tokensData.items) ? tokensData.items : [];
          render(items, movers24, movers7);
        } catch(e){
          // fallback: no data
          render([], [], []);
        }
      }
      function fmtPrice(v){
        const x = Number(v||0);
        if (x >= 1000) return `$${x.toLocaleString(undefined,{maximumFractionDigits:0})}`;
        if (x >= 1) return `$${x.toLocaleString(undefined,{maximumFractionDigits:2})}`;
        return `$${x.toLocaleString(undefined,{minimumFractionDigits:4, maximumFractionDigits:6})}`;
      }
      function fmtChg(v){
        const n = Number(v||0);
        const sign = n>0?'+':'';
        return `${sign}${n.toFixed(2)}%`;
      }
      function render(items, movers24, movers7){
        // Clear
        track.innerHTML = '';
        const bySym = new Map();
        (items||[]).forEach(it=>{ if (it && it.symbol) bySym.set(String(it.symbol).toUpperCase(), it); });

        const segTop24 = Array.isArray(movers24) ? movers24.slice(0, 10) : [];
        const segTop7 = Array.isArray(movers7) ? movers7.slice(0, 10) : [];
        const topDecorated = [];
        segTop24.forEach(m => {
          const sym = String(m.symbol||'').toUpperCase();
          const base = bySym.get(sym) || { symbol: sym, price_usd: 0, change_24h: m.value };
          topDecorated.push({ ...base, _badge: 'Top 24h', _badgeClass: 'b24' });
        });
        segTop7.forEach(m => {
          const sym = String(m.symbol||'').toUpperCase();
          const base = bySym.get(sym) || { symbol: sym, price_usd: 0, r7: m.value, change_24h: 0 };
          topDecorated.push({ ...base, _badge: 'Top 7D', _badgeClass: 'b7' });
        });

        // Fill the rest with top by mcap so ticker is rich
        const rest = (items||[]).filter(it => !topDecorated.find(x => (x.symbol||'') === (it.symbol||''))).slice(0, 20);
        const list = [...topDecorated, ...rest];
        const frag = document.createDocumentFragment();
        const src = list.length ? list : [
          { symbol: 'ARENA', price_usd: 1.0, change_24h: 2.5 },
          { symbol: 'GLXY', price_usd: 0.245, change_24h: -1.2 },
          { symbol: 'NX', price_usd: 12.42, change_24h: 4.1 },
        ];
        src.forEach(it => {
          const item = document.createElement('div');
          item.className = 'ticker-item ' + ((Number(it.change_24h||0) >= 0) ? 'up' : 'down');
          const sym = document.createElement('span'); sym.className='sym'; sym.textContent = String(it.symbol||'—').toUpperCase();
          const price = document.createElement('span'); price.className='price'; price.textContent = fmtPrice(it.price_usd);
          const chg = document.createElement('span'); chg.className='chg'; chg.textContent = fmtChg(it.change_24h);
          item.append(sym, price, chg);
          if (typeof it.r7 === 'number' && !isNaN(it.r7)){
            const r7 = document.createElement('span'); r7.className='chg'; r7.textContent = `7D ${fmtChg(it.r7)}`; item.appendChild(r7);
          }
          if (it._badge){
            const badge = document.createElement('span'); badge.className = `badge ${it._badgeClass||''}`; badge.textContent = it._badge; item.appendChild(badge);
          }
          frag.appendChild(item);
        });
        // Append twice for seamless loop
        const frag2 = frag.cloneNode(true);
        track.appendChild(frag);
        track.appendChild(frag2);
        // Adjust animation duration based on width
        requestAnimationFrame(()=>{
          try{
            const totalWidth = track.scrollWidth; // includes both copies
            const halfWidth = totalWidth / 2; // one copy width
            const duration = Math.max(20, Math.round(halfWidth / speedPxPerSec));
            track.style.animationDuration = `${duration}s`;
          } catch{}
        });
      }
      load();
      // Periodic refresh
      setInterval(load, 60*1000);
      // Adapt speed on resize
      window.addEventListener('resize', ()=>{
        const ev = new Event('ticker-resize');
        document.dispatchEvent(ev);
      });
      document.addEventListener('ticker-resize', ()=>{
        // Recompute duration
        try{
          const totalWidth = track.scrollWidth;
          const halfWidth = totalWidth / 2;
          const duration = Math.max(20, Math.round(halfWidth / speedPxPerSec));
          track.style.animationDuration = `${duration}s`;
        } catch{}
      });
    })();

    // Dashboard CTA: sign-in via Nostr if not authenticated; otherwise navigate
    async function getUserAuth(){
      try{
        if (window.TB && typeof window.TB.getMe === 'function'){
          return await window.TB.getMe();
        }
        const r = await fetch('/api/auth/me');
        const j = await r.json();
        return j.user;
      } catch{ return null; }
    }
    function wireDashboardCTA(){
      const links = document.querySelectorAll('header a[href="/dashboard"], .mobile-nav a[href="/dashboard"]');
      links.forEach(a => {
        a.addEventListener('click', async (e) => {
          // Only intercept left-click/enter without modifier keys
          if (e.defaultPrevented) return;
          if (e.button !== 0) return; // left button
          if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
          e.preventDefault();
          const user = await getUserAuth();
          if (user){ window.location.href = '/dashboard'; return; }
          // Try Nostr login (Alby/OKX via shim)
          let ok = false;
          if (window.TB && typeof window.TB.loginWithNostr === 'function'){
            ok = await window.TB.loginWithNostr();
          }
          if (ok){ window.location.href = '/dashboard'; }
          else if (window.TB && typeof window.TB.showToast === 'function'){
            window.TB.showToast('No Nostr provider detected. Install Alby or use OKX wallet with Nostr support.', 'error');
          }
        });
      });
    }
    wireDashboardCTA();
  });
})();

