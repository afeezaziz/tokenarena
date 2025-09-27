/* Nostr Sign-In flow using a browser Nostr extension implementing window.nostr */
(async function(){
  const area = document.getElementById('auth-area');
  const TB = (window.TB = window.TB || {});

  // OKX Nostr adapter shim: if window.nostr is missing, try mapping OKX provider
  function ensureNostrBridge(){
    try{
      // If a NIP-07 provider is already present, accept it
      if (window.nostr && (typeof window.nostr.signEvent === 'function' || typeof window.nostr.getPublicKey === 'function' || typeof window.nostr.enable === 'function')){
        return true;
      }
      // Try to discover an OKX-provided Nostr object in a few common locations
      const okx = window.okxwallet || window.okxWallet || null;
      const okxNostr = okx && (okx.nostr || okx.provider?.nostr || okx.providers?.nostr);
      if (okxNostr){
        // Map the exposed object directly; some wallets require enable() before methods are available
        window.nostr = okxNostr;
        return true;
      }
      // Fallback: some OKX builds expose an EIP-1193-like request() API for Nostr methods
      if (okx && (typeof okx.request === 'function' || okx.provider || okx.providers)){
        const rq = typeof okx.request === 'function' ? okx.request.bind(okx) : null;
        window.nostr = {
          enable: async () => {
            try { if (typeof okx.enable === 'function') { await okx.enable(); } } catch {}
            return true;
          },
          getPublicKey: async () => {
            try{ if (okx.nostr && typeof okx.nostr.getPublicKey === 'function') return okx.nostr.getPublicKey(); } catch{}
            if (rq) return rq({ method: 'nostr_getPublicKey' });
            throw new Error('nostr_unavailable');
          },
          signEvent: async (ev) => {
            try{ if (okx.nostr && typeof okx.nostr.signEvent === 'function') return okx.nostr.signEvent(ev); } catch{}
            if (rq) return rq({ method: 'nostr_signEvent', params: ev });
            throw new Error('nostr_unavailable');
          },
        };
        return true;
      }
    } catch {}
    return false;
  }

  function render(user){
    if (!area) return; // no UI surface; skip
    if (user){
      area.innerHTML = `<div class="nav"><a class="nav-link" href="/dashboard">Dashboard</a> <button id="logout-btn" class="btn">Logout</button></div>`;
      document.getElementById('logout-btn')?.addEventListener('click', async ()=>{
        await fetch('/api/auth/logout', { method:'POST' });
        if (window.TB?.showToast) TB.showToast('Logged out');
        if (TB.__mock) TB.__mock.user = null;
        load();
      });
    } else {
      area.innerHTML = `<div class="nav" style="gap:8px">
        <button id="nostr-login" class="btn">Sign in with Nostr</button>
      </div>`;
      document.getElementById('nostr-login')?.addEventListener('click', login);
    }
  }

  async function getMe(){
    try{ const r = await fetch('/api/auth/me'); const j = await r.json(); return j.user; } catch { return null; }
  }

  function renderNoExtensionUI(){
    if (!area){
      if (TB.showToast) TB.showToast('No Nostr extension detected. Install Alby or enable an OKX Nostr provider.', 'error');
      return;
    }
    const okx = window.okxwallet || window.okxWallet || null;
    const hasOKX = !!okx;
    area.innerHTML = `
      <div class="nav" style="gap:8px; flex-wrap:wrap">
        <span class="muted">${hasOKX ? 'Detected OKX Wallet, but Nostr provider is not enabled.' : 'No Nostr extension detected.'}</span>
        ${hasOKX ? '<button id="retry-okx" class="btn">Retry OKX</button>' : ''}
        <a class="nav-link" href="https://getalby.com/" target="_blank" rel="noopener">Install Alby</a>
        <a class="nav-link" href="https://chromewebstore.google.com/search/nostr" target="_blank" rel="noopener">Other extensions</a>
        <button id="demo-login" class="btn">Use Demo Mode</button>
        <button id="back-login" class="btn" style="background:transparent;border:1px solid var(--border)">Back</button>
      </div>`;
    document.getElementById('demo-login')?.addEventListener('click', () => {
      if (!TB.__mock) TB.__mock = {};
      TB.__mock.user = TB.__mock.user || { npub: 'demo'.padEnd(64,'0'), display_name: 'Demo User', avatar_url: null, npub_bech32: null };
      if (TB.enableMock) TB.enableMock(true);
      if (TB.showToast) TB.showToast('Demo mode enabled');
      load();
    });
    document.getElementById('back-login')?.addEventListener('click', async () => {
      render(null);
    });
    document.getElementById('retry-okx')?.addEventListener('click', async () => {
      ensureNostrBridge();
      await login();
    });
  }

  async function login(){
    // Attempt to bridge OKX -> window.nostr if needed
    ensureNostrBridge();
    // Some providers (including OKX) may require an explicit enable/permission step
    try{
      if (window.nostr && typeof window.nostr.enable === 'function'){
        await window.nostr.enable();
      }
    } catch(e){
      // Permission denied or not supported; continue and let getPublicKey prompt if applicable
      console.warn('nostr.enable() failed or not supported', e);
    }
    // Re-bridge in case enable() populated methods
    ensureNostrBridge();
    if (!window.nostr || (typeof window.nostr.getPublicKey !== 'function' && typeof window.nostr.signEvent !== 'function')){
      renderNoExtensionUI();
      return;
    }
    try{
      // Get pubkey from extension
      const pubkey = await window.nostr.getPublicKey();
      // Ask server for challenge
      const cr = await fetch('/api/auth/nostr/challenge', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pubkey }) });
      const { nonce } = await cr.json();
      if (!nonce){ throw new Error('No nonce'); }

      // Compose Nostr event: kind 27235 (arbitrary app-specific), content = nonce
      const ev = {
        kind: 27235,
        created_at: Math.floor(Date.now()/1000),
        tags: [],
        content: nonce,
        pubkey,
      };
      const signed = await window.nostr.signEvent(ev);

      // Send to server for verification
      const vr = await fetch('/api/auth/nostr/verify', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ event: signed }) });
      const vj = await vr.json();
      if (!vr.ok){
        const msg = String(vj?.error || 'Verify failed');
        if (/coincurve/i.test(msg)){
          if (TB.showToast) TB.showToast('Server missing crypto verification; use Demo Mode locally or install coincurve.', 'error');
        }
        throw new Error(msg);
      }
      if (window.TB?.showToast) TB.showToast('Signed in');
      await load();
      return true;
    } catch(e){
      if (window.TB?.showToast) TB.showToast(String(e.message || e), 'error');
      return false;
    }
  }

  async function load(){
    const user = await getMe();
    if (area) render(user);
    return user;
  }

  // Expose helpers even if area/inline UI is absent
  TB.getMe = getMe;
  TB.loginWithNostr = login;
  TB.logout = async () => { try{ await fetch('/api/auth/logout', { method:'POST' }); TB.__mock && (TB.__mock.user = null); } catch{} finally { await load(); } };

  await load();

  // React to settings/profile updates
  window.addEventListener('tb:profile-updated', () => { load(); });
})();
