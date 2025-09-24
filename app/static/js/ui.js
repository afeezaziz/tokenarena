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
})();
