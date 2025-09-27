(function(){
  async function fetchJSON(url){
    const r = await fetch(url, { headers: { 'Accept':'application/json' } });
    if (!r.ok) throw new Error('HTTP '+r.status);
    return await r.json();
  }

  function emptyRow(tbody, colSpan){
    tbody.innerHTML = '';
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = colSpan;
    td.className = 'muted';
    td.textContent = 'No data';
    tr.appendChild(td);
    tbody.appendChild(tr);
  }

  async function loadPools(){
    const tbody = document.querySelector('#tbl-pools tbody');
    if (!tbody) return;
    try{
      const rows = await fetchJSON('/api/admin/pools');
      tbody.innerHTML = '';
      if (!rows || rows.length === 0){ emptyRow(tbody, 9); return; }
      rows.forEach(p => {
        const tr = document.createElement('tr');
        const lpPlatform = `${p.lp_fee_bps}/${p.platform_fee_bps}`;
        const reservesRgb = (p.reserves && p.reserves.rgb != null) ? p.reserves.rgb : '';
        const reservesBtc = (p.reserves && p.reserves.btc != null) ? p.reserves.btc : '';
        const cells = [
          p.id,
          p.asset_rgb_symbol || p.asset_rgb_id,
          p.asset_btc_symbol || p.asset_btc_id,
          p.fee_bps,
          lpPlatform,
          reservesRgb,
          reservesBtc,
          p.is_vamm,
          p.is_active,
        ];
        cells.forEach(v => {
          const td = document.createElement('td');
          td.textContent = v === undefined || v === null ? '' : String(v);
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
    } catch(e){ console.error('admin pools', e); }
  }

  async function loadAssets(){
    const tbody = document.querySelector('#tbl-assets tbody');
    if (!tbody) return;
    try{
      const rows = await fetchJSON('/api/admin/assets');
      tbody.innerHTML = '';
      if (!rows || rows.length === 0){ emptyRow(tbody, 6); return; }
      rows.forEach(a => {
        const tr = document.createElement('tr');
        const creator = a.creator && (a.creator.display_name || a.creator.npub) ? (a.creator.display_name || a.creator.npub) : '';
        const cells = [a.id, a.symbol, a.name, a.precision, a.rln_asset_id || '', creator];
        cells.forEach(v => {
          const td = document.createElement('td');
          td.textContent = v === undefined || v === null ? '' : String(v);
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
    } catch(e){ console.error('admin assets', e); }
  }

  async function loadUsers(){
    const tbody = document.querySelector('#tbl-users tbody');
    if (!tbody) return;
    try{
      const rows = await fetchJSON('/api/admin/users');
      tbody.innerHTML = '';
      if (!rows || rows.length === 0){ emptyRow(tbody, 3); return; }
      rows.forEach(u => {
        const tr = document.createElement('tr');
        const cells = [u.id, u.npub, u.display_name || ''];
        cells.forEach(v => {
          const td = document.createElement('td');
          td.textContent = v === undefined || v === null ? '' : String(v);
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
    } catch(e){ console.error('admin users', e); }
  }

  async function loadDeposits(){
    const tbody = document.querySelector('#tbl-deposits tbody');
    if (!tbody) return;
    try{
      const rows = await fetchJSON('/api/admin/deposits');
      tbody.innerHTML = '';
      if (!rows || rows.length === 0){ emptyRow(tbody, 7); return; }
      rows.forEach(d => {
        const tr = document.createElement('tr');
        const userLbl = d.user_display_name || d.user_npub || d.user_id;
        const cells = [d.id, userLbl, d.asset_symbol || d.asset_id, d.amount, d.status, d.external_ref || '', d.created_at || ''];
        cells.forEach(v => {
          const td = document.createElement('td');
          td.textContent = v === undefined || v === null ? '' : String(v);
          tr.appendChild(td);
        });
        // Actions
        const tdAct = document.createElement('td');
        if (d.status !== 'settled'){
          const btn = document.createElement('button'); btn.className='btn btn-small'; btn.textContent='Settle';
          btn.addEventListener('click', async () => {
            try{
              const r = await fetch('/api/admin/deposits/settle', {method:'POST', headers:{'Content-Type':'application/json','Accept':'application/json'}, body: JSON.stringify({id: d.id})});
              await r.json(); await loadDeposits();
            }catch(e){ console.error('settle deposit', e); }
          });
          tdAct.appendChild(btn);
        }
        tr.appendChild(tdAct);
        tbody.appendChild(tr);
      });
    } catch(e){ console.error('admin deposits', e); }
  }

  async function loadWithdrawals(){
    const tbody = document.querySelector('#tbl-withdrawals tbody');
    if (!tbody) return;
    try{
      const rows = await fetchJSON('/api/admin/withdrawals');
      tbody.innerHTML = '';
      if (!rows || rows.length === 0){ emptyRow(tbody, 7); return; }
      rows.forEach(w => {
        const tr = document.createElement('tr');
        const userLbl = w.user_display_name || w.user_npub || w.user_id;
        const cells = [w.id, userLbl, w.asset_symbol || w.asset_id, w.amount, w.status, w.external_ref || '', w.created_at || ''];
        cells.forEach(v => {
          const td = document.createElement('td');
          td.textContent = v === undefined || v === null ? '' : String(v);
          tr.appendChild(td);
        });
        // Actions
        const tdAct = document.createElement('td');
        if (w.status !== 'sent'){
          const btn = document.createElement('button'); btn.className='btn btn-small'; btn.textContent='Mark Sent';
          btn.addEventListener('click', async () => {
            try{
              const r = await fetch('/api/admin/withdrawals/mark_sent', {method:'POST', headers:{'Content-Type':'application/json','Accept':'application/json'}, body: JSON.stringify({id: w.id})});
              await r.json(); await loadWithdrawals();
            }catch(e){ console.error('mark sent withdraw', e); }
          });
          tdAct.appendChild(btn);
        }
        tr.appendChild(tdAct);
        tbody.appendChild(tr);
      });
    } catch(e){ console.error('admin withdrawals', e); }
  }

  window.addEventListener('DOMContentLoaded', async () => {
    // Quick funds ops
    const el = (id) => document.getElementById(id);
    const msg = el('funds-msg');
    const getPayload = () => ({
      user_id: parseInt(el('funds-user-id').value || '0', 10),
      asset_id: parseInt(el('funds-asset-id').value || '0', 10),
      amount: parseFloat(el('funds-amount').value || '0'),
      external_ref: el('funds-ref').value || undefined,
    });
    const postJSON = async (url, payload) => {
      const r = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json','Accept':'application/json'}, body: JSON.stringify(payload)});
      const j = await r.json().catch(()=>({}));
      if (!r.ok){ throw new Error(j && j.error ? j.error : 'request_failed'); }
      return j;
    };
    const btnDep = el('btn-create-deposit');
    if (btnDep) btnDep.addEventListener('click', async () => {
      try{ const p = getPayload(); await postJSON('/api/admin/deposits/create', p); msg.textContent='Deposit created'; await loadDeposits(); }
      catch(e){ msg.textContent = 'Error: '+e; console.error(e); }
    });
    const btnW = el('btn-create-withdrawal');
    if (btnW) btnW.addEventListener('click', async () => {
      try{ const p = getPayload(); await postJSON('/api/admin/withdrawals/create', p); msg.textContent='Withdrawal created'; await loadWithdrawals(); }
      catch(e){ msg.textContent = 'Error: '+e; console.error(e); }
    });
    await Promise.all([
      loadPools(),
      loadAssets(),
      loadUsers(),
      loadDeposits(),
      loadWithdrawals(),
    ]);
  });
})();
