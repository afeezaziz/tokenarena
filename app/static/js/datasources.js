(function(){
  function el(tag, attrs={}, html=''){
    const e = document.createElement(tag);
    Object.entries(attrs).forEach(([k,v])=> e.setAttribute(k, v));
    if (html) e.innerHTML = html;
    return e;
  }
  async function loadSources(){
    const tbody = document.getElementById('datasources-tbody');
    if (!tbody) return;
    tbody.innerHTML = '';
    try{
      const res = await fetch('/api/datasources');
      const data = await res.json();
      if (!Array.isArray(data) || !data.length){
        const tr = el('tr', {}, '<td colspan="5" class="muted" style="text-align:center;padding:12px">No sources available</td>');
        tbody.appendChild(tr);
        return;
      }
      data.forEach(s => {
        const cov = (s.coverage||[]).map(x=>`<span class="tag">${x}</span>`).join(' ');
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><a href="/d/${encodeURIComponent(s.slug)}"><strong>${s.name}</strong></a><div class="muted" style="font-size:12px">${s.description||''}</div></td>
          <td>${cov}</td>
          <td>${s.freshness || ''}</td>
          <td>${s.status || ''}</td>
          <td><a class="btn" href="/d/${encodeURIComponent(s.slug)}">View</a></td>
        `;
        tbody.appendChild(tr);
      });
    } catch(e){
      console.error(e);
      if (window.TB?.showToast) TB.showToast('Failed to load sources', 'error');
    }
  }
  window.addEventListener('DOMContentLoaded', loadSources);
})();
