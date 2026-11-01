// apply the theme before first paint (no dark/light flash)
(function () {
  var t = 'dark';
  try { t = JSON.parse(localStorage.getItem('wtftd.theme')) || 'dark'; } catch (e) {}
  if (t === 'system') t = matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  document.documentElement.dataset.theme = t;
})();
