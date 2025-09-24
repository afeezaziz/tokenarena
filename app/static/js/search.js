let searchTimer;
const DEBOUNCE_MS = 200;

function clearResults(){
  const box = document.getElementById('search-results');
  if (!box) return;
  box.innerHTML = '';
  box.hidden = true;
}

function renderResults(data){
  const box = document.getElementById('search-results');
  if (!box) return;
  box.innerHTML = '';

  const makeGroup = (title) => {
    const g = document.createElement('div');
    g.className = 'group';
    const t = document.createElement('div');
    t.className = 'group-title';
    t.textContent = title;
    g.appendChild(t);
    return g;
  };

  let hasAny = false;

  if (data.tokens && data.tokens.length){
    const g = makeGroup('Tokens');
    data.tokens.forEach(t => {
      const a = document.createElement('a');
      a.href = `/t/${encodeURIComponent(t.symbol)}`;
      a.innerHTML = `<span><strong>${t.symbol}</strong> <span class="muted">${t.name}</span></span><span class="muted">$${Math.round(t.market_cap_usd).toLocaleString()}</span>`;
      g.appendChild(a);
    });
    box.appendChild(g);
    hasAny = true;
  }

  if (data.users && data.users.length){
    const g = makeGroup('Users');
    data.users.forEach(u => {
      const a = document.createElement('a');
      const linkNpub = u.npub_bech32 || u.npub;
      const labelRight = (u.npub_bech32 ? (u.npub_bech32.slice(0,16)+'…') : (u.npub ? (u.npub.slice(0,12)+'…') : ''));
      a.href = `/u/${encodeURIComponent(linkNpub)}`;
      const leftLabel = u.display_name || (u.npub_bech32 ? (u.npub_bech32.slice(0,12)+'…') : (u.npub ? (u.npub.slice(0,8)+'…') : 'User'));
      const avatar = u.avatar_url ? `<img class="avatar-sm" src="${u.avatar_url}" alt="avatar" />` : '';
      a.innerHTML = `<span style="display:flex;align-items:center;gap:8px">${avatar}<span>${leftLabel}</span></span><span class="muted">${labelRight}</span>`;
      g.appendChild(a);
    });
    box.appendChild(g);
    hasAny = true;
  }

  box.hidden = !hasAny;
}

async function doSearch(q){
  if (!q) { clearResults(); return; }
  try{
    const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
    if (!res.ok){ clearResults(); return; }
    const data = await res.json();
    renderResults(data);
  } catch(e){ clearResults(); }
}

function setupSearch(){
  const inp = document.getElementById('site-search');
  if (!inp) return;

  inp.addEventListener('input', () => {
    const q = inp.value.trim();
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(()=>doSearch(q), DEBOUNCE_MS);
  });

  document.addEventListener('click', (e) => {
    const box = document.getElementById('search-results');
    const sb = document.querySelector('.searchbar');
    if (!box || !sb) return;
    if (!sb.contains(e.target)) clearResults();
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') clearResults();
  });
}

window.addEventListener('DOMContentLoaded', setupSearch);
