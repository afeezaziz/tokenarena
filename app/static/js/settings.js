(function(){
  const placeholder = 'data:image/svg+xml;utf8,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="100%" height="100%" fill="#e5e7eb"/><text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="14" fill="#9ca3af">NP</text></svg>');
  const MAX_W = 320, MAX_H = 320; // client-side resize target for avatars

  async function compressImage(file){
    try{
      const img = await new Promise((resolve, reject) => {
        const url = URL.createObjectURL(file);
        const i = new Image();
        i.onload = () => { URL.revokeObjectURL(url); resolve(i); };
        i.onerror = (e) => { URL.revokeObjectURL(url); reject(e); };
        i.src = url;
      });
      const ratio = Math.min(1, MAX_W / img.width, MAX_H / img.height);
      const w = Math.max(1, Math.round(img.width * ratio));
      const h = Math.max(1, Math.round(img.height * ratio));
      const canvas = document.createElement('canvas');
      canvas.width = w; canvas.height = h;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0, w, h);
      const blob = await new Promise(res => canvas.toBlob(res, 'image/webp', 0.9));
      if (!blob) return file;
      return new File([blob], (file.name.replace(/\.[^.]+$/, '') || 'avatar') + '.webp', { type: 'image/webp' });
    } catch {
      return file;
    }
  }

  async function loadProfile(){
    try{
      const r = await fetch('/api/profile');
      if (r.status === 401){ window.location.href = '/'; return; }
      const d = await r.json();
      document.getElementById('display_name').value = d.display_name || '';
      document.getElementById('bio').value = d.bio || '';
      const prev = document.getElementById('avatar_preview');
      prev.src = d.avatar_url || placeholder;
      const bech = d.npub_bech32 || '';
      const hex = d.npub || '';
      const view = document.getElementById('pubkey_view');
      view.innerHTML = '';
      if (bech) {
        const b = document.createElement('div');
        b.textContent = bech;
        view.appendChild(b);
      }
      if (hex) {
        const h = document.createElement('div');
        h.textContent = hex;
        view.appendChild(h);
      }
    } catch(e){
      console.error(e);
    }
  }

  async function saveProfile(){
    const btn = document.getElementById('save-settings');
    const status = document.getElementById('save-status');
    btn.disabled = true; status.textContent = 'Saving...';
    try{
      const body = {
        display_name: document.getElementById('display_name').value.trim(),
        bio: document.getElementById('bio').value.trim(),
      };
      const r = await fetch('/api/profile', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
      const j = await r.json().catch(()=>({}));
      if (!r.ok){ throw new Error(j.error || 'Save failed'); }
      status.textContent = 'Saved';
      if (window.TB && TB.showToast) TB.showToast('Profile updated');
      window.dispatchEvent(new CustomEvent('tb:profile-updated', { detail: { display_name: body.display_name } }));
    } catch(e){
      status.textContent = String(e.message || e);
      if (window.TB && TB.showToast) TB.showToast(String(e.message || e), 'error');
    } finally{
      btn.disabled = false;
      setTimeout(()=>{ status.textContent=''; }, 2000);
    }
  }

  async function uploadAvatar(){
    const fileInput = document.getElementById('avatar_file');
    const file = fileInput.files && fileInput.files[0];
    if (!file){ if (window.TB?.showToast) TB.showToast('Choose a file first', 'error'); return; }
    const btn = document.getElementById('upload_avatar');
    const status = document.getElementById('save-status');
    btn.disabled = true; status.textContent = 'Uploading...';
    try{
      // Compress client-side
      const comp = await compressImage(file);

      // Try S3 presigned upload first
      const presign = await fetch('/api/profile/avatar/presign', { method:'POST', headers:{ 'Content-Type':'application/json' }, body: JSON.stringify({ content_type: comp.type || 'image/webp' }) });
      if (presign.ok){
        const p = await presign.json();
        const fd = new FormData();
        Object.entries(p.fields || {}).forEach(([k,v]) => fd.append(k, v));
        fd.append('file', comp);
        const up = await fetch(p.url, { method:'POST', body: fd });
        if (!up.ok && up.status !== 204 && up.status !== 201) throw new Error('S3 upload failed');
        // tell server to set avatar_url
        const fin = await fetch('/api/profile/avatar/complete', { method:'POST', headers:{ 'Content-Type':'application/json' }, body: JSON.stringify({ key: p.key }) });
        const fj = await fin.json();
        if (!fin.ok) throw new Error(fj.error || 'Finalize failed');
        document.getElementById('avatar_preview').src = fj.avatar_url || placeholder;
        if (window.TB && TB.showToast) TB.showToast('Avatar updated');
        window.dispatchEvent(new CustomEvent('tb:profile-updated', { detail: { avatar_url: fj.avatar_url } }));
      } else {
        // Fallback to local upload
        const fd = new FormData();
        fd.append('avatar', comp);
        const r = await fetch('/api/profile/avatar', { method:'POST', body: fd });
        const j = await r.json();
        if (!r.ok){ throw new Error(j.error || 'Upload failed'); }
        document.getElementById('avatar_preview').src = j.avatar_url || placeholder;
        if (window.TB && TB.showToast) TB.showToast('Avatar updated');
        window.dispatchEvent(new CustomEvent('tb:profile-updated', { detail: { avatar_url: j.avatar_url } }));
      }
    } catch(e){
      if (window.TB && TB.showToast) TB.showToast(String(e.message || e), 'error');
    } finally{
      btn.disabled = false; status.textContent = '';
    }
  }

  window.addEventListener('DOMContentLoaded', () => {
    loadProfile();
    document.getElementById('save-settings')?.addEventListener('click', saveProfile);
    document.getElementById('avatar_file')?.addEventListener('change', (e) => {
      const file = e.target.files && e.target.files[0];
      if (file){
        const url = URL.createObjectURL(file);
        const img = document.getElementById('avatar_preview');
        img.src = url;
      }
    });
    document.getElementById('upload_avatar')?.addEventListener('click', uploadAvatar);
  });
})();
