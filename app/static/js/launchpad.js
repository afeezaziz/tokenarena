(function(){
  const $ = (sel, root=document) => root.querySelector(sel);
  const $$ = (sel, root=document) => Array.from(root.querySelectorAll(sel));

  async function fetchJSON(url, opts={}){
    const res = await fetch(url, Object.assign({headers: {'Content-Type':'application/json'}}, opts));
    let data = null;
    try { data = await res.json(); } catch(e) { /* ignore */ }
    if (!res.ok) {
      const err = new Error((data && data.error) || `Request failed: ${res.status}`);
      err.status = res.status; err.data = data; throw err;
    }
    return data;
  }

  function setStatus(el, type, msg){
    if(!el) return;
    el.className = `lp-status ${type}`;
    el.textContent = msg;
    el.style.display = msg ? 'block' : 'none';
  }

  // Recent Activity utilities
  function addActivity(kind, detail){
    const wrap = $('#lp-activity');
    if (!wrap) return;
    const item = document.createElement('div');
    item.className = 'activity-item';
    const ts = new Date().toLocaleTimeString();
    item.innerHTML = `<div><strong>${kind}</strong> — ${detail}</div><div class="meta">${ts}</div>`;
    wrap.prepend(item);
    // Trim to 10
    const items = $$('.activity-item', wrap);
    if (items.length > 10){ items.slice(10).forEach(n=>n.remove()); }
  }

  function fmt(n){
    try { return Number(n).toLocaleString(undefined, {maximumFractionDigits: 8}); } catch(e){ return String(n); }
  }
  async function loadExistingAssets(){
    const select = $('#existing-asset-select');
    const list = $('#existing-assets-list');
    if(!select || !list) return;
    select.innerHTML = '<option value="">Select asset…</option>';
    list.innerHTML = '<div class="loading">Loading assets…</div>';
    try {
      const items = await fetchJSON('/api/launchpad/assets');
      const rows = Array.isArray(items) ? items : [];
      const options = ['<option value="">Select asset…</option>'];
      const cards = [];
      const sampleActivity = rows.length ? rows.slice(0, 3).map(a => `Sync · ${a.symbol} · ${a.name}`).join('\n') : '';
      addActivity('Sync', sampleActivity);
      for(const a of rows){
        options.push(`<option value="${a.symbol}" data-pool-id="${a.pool_id||''}">${a.symbol} · ${a.name}</option>`);
        cards.push(`
          <div class="asset-card">
            <div class="asset-row">
              <div class="asset-sym">${a.symbol}</div>
              <div class="asset-name">${a.name}</div>
              <div class="asset-meta">${a.pool_exists ? `Pool #${a.pool_id}` : 'No pool'}</div>
            </div>
            <div class="asset-id">${a.rln_asset_id || ''}</div>
          </div>
        `);
      }
      select.innerHTML = options.join('');
      list.innerHTML = rows.length ? cards.join('') : '<div class="no-projects">No RGB assets found yet.</div>';
      if ($('#lp-activity') && rows.length){
        addActivity('Sync', `Loaded ${rows.length} RGB assets`);
      }
    } catch(e){
      list.innerHTML = `<div class="no-projects">${e.data?.error || 'Failed to load assets'}</div>`;
    }
  }

  function bindMintForm(){
    const form = $('#mint-form');
    const status = $('#mint-status');
    const out = $('#mint-output');
    if(!form) return;

    form.addEventListener('submit', async (ev)=>{
      ev.preventDefault();
      setStatus(status, 'info', 'Minting and creating pool…');
      out.textContent = '';
      const ticker = $('#mint-ticker').value.trim().toUpperCase();
      const name = $('#mint-name').value.trim();
      const precision = parseInt($('#mint-precision').value || '0', 10) || 0;
      const supply = parseInt($('#mint-supply').value || '0', 10) || 0; // integers per RGB
      const initialPrice = parseFloat($('#mint-initial-price').value || '0');
      const virtualDepthBtc = parseFloat($('#mint-virtual-depth').value || '0');
      if(!ticker || !name || supply <= 0 || initialPrice <= 0 || virtualDepthBtc <= 0){
        setStatus(status, 'error', 'Please fill all fields correctly.');
        return;
      }
      try{
        const resp = await fetchJSON('/api/launchpad/issue_nia_and_pool', {
          method: 'POST',
          body: JSON.stringify({
            ticker, name, precision, amounts: [supply],
            initial_price: initialPrice,
            virtual_depth_btc: virtualDepthBtc,
          })
        });
        setStatus(status, 'success', `Created ${resp.asset.symbol} with pool #${resp.pool_id}. Virtual: BTC ${fmt(resp.virtual.btc)}, RGB ${fmt(resp.virtual.rgb)}`);
        out.textContent = JSON.stringify(resp, null, 2);
        addActivity('Mint+Pool', `${resp.asset.symbol} · Pool #${resp.pool_id}`);
        loadExistingAssets();
      }catch(e){
        if(e.status === 401){
          setStatus(status, 'error', 'Sign in required. Please authenticate first.');
        } else {
          setStatus(status, 'error', e.data?.error || 'Failed to mint');
        }
      }
    });
  }

  function bindPoolForm(){
    const form = $('#pool-form');
    const status = $('#pool-status');
    const out = $('#pool-output');
    if(!form) return;

    form.addEventListener('submit', async (ev)=>{
      ev.preventDefault();
      setStatus(status, 'info', 'Creating pool…');
      out.textContent = '';
      const symbol = ($('#existing-asset-select').value || '').toUpperCase();
      const rlnId = $('#pool-rln-asset-id').value.trim();
      const initialPrice = parseFloat($('#pool-initial-price').value || '0');
      const virtualDepthBtc = parseFloat($('#pool-virtual-depth').value || '0');
      const feeBps = parseInt($('#pool-fee-bps').value || '100', 10) || 100;
      const lpFeeBps = parseInt($('#pool-lp-fee-bps').value || '50', 10) || 50;
      const platformFeeBps = parseInt($('#pool-platform-fee-bps').value || '50', 10) || 50;
      if((!symbol && !rlnId) || initialPrice <= 0 || virtualDepthBtc <= 0){
        setStatus(status, 'error', 'Provide Symbol or RLN Asset ID, and valid price/depth.');
        return;
      }
      try{
        const resp = await fetchJSON('/api/launchpad/create_pool', {
          method: 'POST',
          body: JSON.stringify({
            symbol: symbol || undefined,
            rln_asset_id: rlnId || undefined,
            initial_price: initialPrice,
            virtual_depth_btc: virtualDepthBtc,
            fee_bps: feeBps,
            lp_fee_bps: lpFeeBps,
            platform_fee_bps: platformFeeBps,
          })
        });
        setStatus(status, 'success', `Pool #${resp.pool_id} created for ${resp.asset.symbol}. Virtual: BTC ${fmt(resp.virtual.btc)}, RGB ${fmt(resp.virtual.rgb)}`);
        out.textContent = JSON.stringify(resp, null, 2);
        addActivity('Create Pool', `${resp.asset.symbol} · Pool #${resp.pool_id}`);
        loadExistingAssets();
      }catch(e){
        if(e.status === 401){
          setStatus(status, 'error', 'Sign in required. Please authenticate first.');
        } else {
          setStatus(status, 'error', e.data?.error || 'Failed to create pool');
        }
      }
    });
  }

  function init(){
    bindMintForm();
    bindPoolForm();
    loadExistingAssets();
  }

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
