function fmtDate(iso){
  try { const d = new Date(iso); return d.toLocaleDateString(); } catch { return iso; }
}

async function loadCompetitionPage(){
  const root = document.getElementById('competition-page');
  if (!root) return;
  const slug = root.dataset.slug;

  const res = await fetch(`/api/competition/${encodeURIComponent(slug)}`);
  if (!res.ok){ console.error('Competition not found'); return; }
  const d = await res.json();

  document.getElementById('comp-title').textContent = d.title;
  document.getElementById('comp-desc').textContent = d.description || '';
  document.getElementById('comp-dates').textContent = `${fmtDate(d.start_at)} → ${fmtDate(d.end_at)}`;

  const tbody = document.getElementById('leaderboard-tbody');
  tbody.innerHTML = '';
  d.leaderboard.forEach(row => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${row.rank}</td>
      <td><a href="/u/${encodeURIComponent(row.npub)}">${row.display_name || row.npub.slice(0,8)+'…'}</a></td>
      <td>${row.score.toFixed(2)}</td>
    `;
    tbody.appendChild(tr);
  });
}

window.addEventListener('DOMContentLoaded', loadCompetitionPage);
