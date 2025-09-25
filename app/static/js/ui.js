(function(){
  const toast = document.getElementById('toast');
  function showToast(msg, type='info', dur=2800){
    if (!toast) return;
    toast.textContent = msg;
    toast.dataset.type = type;
    toast.hidden = false;
    window.clearTimeout(showToast.__t);
    showToast.__t = window.setTimeout(()=>{ toast.hidden = true; }, dur);
  }
  window.TB = window.TB || {};
  window.TB.showToast = showToast;

  // Theme management
  const THEME_KEY = 'tb_theme'; // 'arena' | 'light'
  function systemPreferredTheme(){
    try {
      return (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'arena' : 'light';
    } catch {
      return 'arena';
    }
  }
  function getStoredTheme(){
    const t = localStorage.getItem(THEME_KEY);
    return t || systemPreferredTheme();
  }
  function applyTheme(theme){
    const isArena = theme === 'arena';
    document.body.classList.toggle('arena', isArena);
    const btns = document.querySelectorAll('#theme-toggle, .theme-toggle');
    btns.forEach(btn => {
      // Button shows the action (what you'll switch to)
      btn.textContent = isArena ? '☀ Light' : '☾ Arena';
      btn.setAttribute('aria-pressed', String(isArena));
    });
    // Dispatch global theme change event so charts/UI can react without reloads
    window.dispatchEvent(new CustomEvent('themechange', { detail: { theme } }));
  }
  function setTheme(theme){
    localStorage.setItem(THEME_KEY, theme);
    applyTheme(theme);
  }

  function toggleTheme(){
    const newTheme = document.body.classList.contains('arena') ? 'light' : 'arena';
    setTheme(newTheme);
    if (window.TB && window.TB.showToast){
      window.TB.showToast(newTheme === 'arena' ? 'Arena theme enabled' : 'Light theme enabled');
    }
  }

  window.addEventListener('DOMContentLoaded', () => {
    // Initialize theme from storage
    applyTheme(getStoredTheme());
    // Hook up toggle buttons
    const btn = document.getElementById('theme-toggle');
    if (btn){ btn.addEventListener('click', toggleTheme); }
    document.querySelectorAll('.theme-toggle').forEach(b => b.addEventListener('click', toggleTheme));

    // If user has not explicitly chosen a theme, follow system preference changes
    const hasStored = !!localStorage.getItem(THEME_KEY);
    if (!hasStored && window.matchMedia){
      const mm = window.matchMedia('(prefers-color-scheme: dark)');
      if (mm.addEventListener){
        mm.addEventListener('change', (e) => setTheme(e.matches ? 'arena' : 'light'));
      } else if (mm.addListener){
        // Safari <14
        mm.addListener((e) => setTheme(e.matches ? 'arena' : 'light'));
      }
    }
  });
})();
