/* Nostr Sign-In flow using a browser Nostr extension implementing window.nostr */
(async function(){
  const area = document.getElementById('auth-area');
  if (!area) return;
  const TB = (window.TB = window.TB || {});

  function render(user){
    if (user){
      const label = user.display_name || user.npub_bech32 || (user.npub ? (user.npub.slice(0,8)+'…') : 'User');
      const avatar = user.avatar_url ? `<img src="${user.avatar_url}" alt="avatar" class="avatar-sm" />` : '';
      const linkNpub = user.npub_bech32 || user.npub || '';
      const profileHref = linkNpub ? `/u/${encodeURIComponent(linkNpub)}` : '/';
      const showSettings = true;
      area.innerHTML = `<div class="nav">${avatar}<a class="nav-link" href="${profileHref}">${label}</a>${showSettings ? ' <a class="nav-link" href="/settings">Settings</a>' : ''} <button id="logout-btn" class="btn">Logout</button></div>`;
      document.getElementById('logout-btn')?.addEventListener('click', async ()=>{
        await fetch('/api/auth/logout', { method:'POST' });
        if (window.TB?.showToast) TB.showToast('Logged out');
        // clear demo user if any
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
    area.innerHTML = `
      <div class="nav" style="gap:8px; flex-wrap:wrap">
        <span class="muted">No Nostr extension detected.</span>
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
  }

  async function login(){
    if (!window.nostr || !window.nostr.signEvent){
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
      if (!vr.ok){ throw new Error(vj.error || 'Verify failed'); }
      if (window.TB?.showToast) TB.showToast('Signed in');
      load();
    } catch(e){
      if (window.TB?.showToast) TB.showToast(String(e.message || e), 'error');
    }
  }

  async function load(){
    const user = await getMe();
    render(user);
  }

  await load();

  // React to settings/profile updates
  window.addEventListener('tb:profile-updated', () => { load(); });
})();
