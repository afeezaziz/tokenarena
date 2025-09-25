(function(){
  function fmtDate(iso){ try { const d = new Date(iso); return d.toLocaleDateString(); } catch { return iso; } }

  async function loadCompetitions(){
    const tbody = document.getElementById('competitions-tbody');
    if (!tbody) return;
    tbody.innerHTML = '';
    try {
      const res = await fetch('/api/competitions');
      const list = await res.json();
      if (!Array.isArray(list) || list.length === 0){
        const tr = document.createElement('tr');
        tr.innerHTML = '<td colspan="5" class="muted" style="text-align:center;padding:12px">No competitions yet</td>';
        tbody.appendChild(tr);
        return;
      }
      list.forEach(c => {
        const tr = document.createElement('tr');
        const status = (c.status||'').toLowerCase();
        const badgeColor = status === 'active' ? '#00d1b2' : (status === 'upcoming' ? '#7c5cff' : '#9ca3af');
        tr.innerHTML = `
          <td><a href="/c/${encodeURIComponent(c.slug)}"><strong>${c.title}</strong></a><div class="muted" style="font-size:12px">${c.description||''}</div></td>
          <td><span style="color:${badgeColor};text-transform:capitalize">${c.status||''}</span></td>
          <td>${fmtDate(c.start_at)} → ${fmtDate(c.end_at)}</td>
          <td>${Number(c.participants||0).toLocaleString()}</td>
          <td><a class="btn" href="/c/${encodeURIComponent(c.slug)}">View</a></td>
        `;
        tbody.appendChild(tr);
      });
    } catch(e) {
      console.error(e);
      if (window.TB?.showToast) TB.showToast('Failed to load competitions', 'error');
    }
  }

  window.addEventListener('DOMContentLoaded', loadCompetitions);
})();
