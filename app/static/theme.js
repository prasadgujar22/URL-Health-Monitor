/* Theme preference is deliberately independent of monitoring and API code.
   This script runs in the head, before the stylesheet and first paint. */
(() => {
  const key = 'url-health-theme';
  const choices = new Set(['light', 'dark', 'system']);
  const root = document.documentElement;
  const media = window.matchMedia('(prefers-color-scheme: dark)');
  let preference = 'system';

  try {
    const saved = window.localStorage.getItem(key);
    if (choices.has(saved)) preference = saved;
  } catch (_) {
    // Storage can be unavailable in private or restricted browsing contexts.
  }

  function apply() {
    const theme = preference === 'system' ? (media.matches ? 'dark' : 'light') : preference;
    root.dataset.theme = theme;
    root.style.colorScheme = theme;
  }

  apply();
  media.addEventListener('change', apply);

  document.addEventListener('DOMContentLoaded', () => {
    const selector = document.getElementById('theme-select');
    if (!selector) return;
    selector.value = preference;
    selector.addEventListener('change', () => {
      if (!choices.has(selector.value)) return;
      preference = selector.value;
      try {
        window.localStorage.setItem(key, preference);
      } catch (_) {
        // Keep the selected theme for this page when persistence is unavailable.
      }
      apply();
    });
  });
})();
