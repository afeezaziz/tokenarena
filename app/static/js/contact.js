(function(){
  async function submitContact(e){
    e.preventDefault();
    const btn = document.getElementById('c-submit');
    const st = document.getElementById('c-status');
    btn.disabled = true; st.textContent = 'Sending…';
    try{
      const name = document.getElementById('c-name').value.trim();
      const email = document.getElementById('c-email').value.trim();
      const message = document.getElementById('c-message').value.trim();
      if (!name || !email || !message) throw new Error('All fields are required');
      const r = await fetch('/api/contact', { method:'POST', headers:{ 'Content-Type':'application/json' }, body: JSON.stringify({ name, email, message }) });
      const j = await r.json().catch(()=>({}));
      if (!r.ok) throw new Error(j.error || 'Send failed');
      st.textContent = 'Thanks! We will reach out.';
      if (window.TB?.showToast) TB.showToast('Message sent');
      (document.getElementById('contact-form')).reset();
    } catch(e){
      st.textContent = String(e.message || e);
      if (window.TB?.showToast) TB.showToast(String(e.message || e), 'error');
    } finally{
      btn.disabled = false;
      setTimeout(()=>{ st.textContent = ''; }, 3000);
    }
  }
  window.addEventListener('DOMContentLoaded', () => {
    document.getElementById('contact-form')?.addEventListener('submit', submitContact);
  });
})();
