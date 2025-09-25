(function(){
  function setText(id, txt){ const el = document.getElementById(id); if (el) el.textContent = txt; }
  function setHTML(id, html){ const el = document.getElementById(id); if (el) el.innerHTML = html; }
  function fmtDateTime(iso){ try { const d = new Date(iso); return d.toLocaleString(); } catch { return iso; } }

  async function loadDatasource(){
    const root = document.getElementById('datasource-page');
    if (!root) return;
    const slug = root.dataset.slug;
    try {
      const res = await fetch(`/api/datasource/${encodeURIComponent(slug)}`);
      if (!res.ok){ throw new Error('Source not found'); }
      const d = await res.json();
      setText('ds-name', d.name || slug);
      const web = document.getElementById('ds-website');
      if (web){ web.innerHTML = d.website ? `<a href="${d.website}" target="_blank" rel="noopener">${d.website}</a>` : ''; }
      setText('ds-status', d.status || '—');
      setText('ds-last-sync', d.last_sync_at ? fmtDateTime(d.last_sync_at) : '—');

      const cov = Array.isArray(d.coverage) ? d.coverage : [];
      setHTML('ds-coverage', cov.map(c => {
        if (typeof c === 'string') return `<div class="tag">${c}</div>`;
        return `<div style="margin:6px 0"><strong>${c.key}</strong> — <span class="muted">${c.desc||''}</span></div>`;
      }).join(''));

      const changelog = Array.isArray(d.changelog) ? d.changelog : [];
      setHTML('ds-changelog', changelog.map(ch => {
        return `<div style="margin:6px 0"><strong>${ch.version}</strong>: <span class="muted">${ch.note||''}</span></div>`;
      }).join(''));
    } catch(e){
      console.error(e);
      if (window.TB?.showToast) TB.showToast('Failed to load data source', 'error');
    }
  }

  window.addEventListener('DOMContentLoaded', loadDatasource);
})();
