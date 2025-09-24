/* Nostr Sign-In flow using a browser Nostr extension implementing window.nostr */
(async function(){
  const area = document.getElementById('auth-area');
  if (!area) return;

  function render(user){
    if (user){
      const label = user.display_name || user.npub_bech32 || (user.npub ? (user.npub.slice(0,8)+'…') : 'User');
      const avatar = user.avatar_url ? `<img src="${user.avatar_url}" alt="avatar" class="avatar-sm" />` : '';
      area.innerHTML = `<div class="nav">${avatar}<a class="nav-link" href="/me">${label}</a> <a class="nav-link" href="/settings">Settings</a> <button id="logout-btn" class="btn">Logout</button></div>`;
      document.getElementById('logout-btn')?.addEventListener('click', async ()=>{
        await fetch('/api/auth/logout', { method:'POST' });
        if (window.TB?.showToast) TB.showToast('Logged out');
        load();
      });
    } else {
      area.innerHTML = `<button id="nostr-login" class="btn">Sign in with Nostr</button>`;
      document.getElementById('nostr-login')?.addEventListener('click', login);
    }
  }

  async function getMe(){
    try{ const r = await fetch('/api/auth/me'); const j = await r.json(); return j.user; } catch { return null; }
  }

  async function login(){
    if (!window.nostr || !window.nostr.signEvent){
      if (window.TB?.showToast) TB.showToast('Nostr extension not found', 'error');
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
