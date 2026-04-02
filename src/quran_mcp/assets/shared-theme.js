/* shared-theme.js — FOUC prevention + theme toggle for all Quran MCP pages.
 * MUST be loaded as a blocking <script> in <head> BEFORE any stylesheet. */
(function () {
  var KEY = 'quran-docs-theme';
  var root = document.documentElement;

  function systemTheme() {
    return matchMedia('(prefers-color-scheme:dark)').matches ? 'dark' : 'light';
  }

  function getPreference() {
    return localStorage.getItem(KEY) || 'system';
  }

  function apply(pref) {
    var resolved = pref === 'system' ? systemTheme() : pref;
    root.setAttribute('data-theme', resolved);
    root.setAttribute('data-resolved', resolved);

    // Sync toggle buttons (if any exist on the page)
    document.querySelectorAll('.theme-toggle button, .theme-fab').forEach(function (el) {
      if (el.dataset.theme) {
        el.classList.toggle('active', el.dataset.theme === pref);
      }
      if (el.classList.contains('theme-fab')) {
        el.querySelectorAll('.fab-icon').forEach(function (icon) {
          icon.style.display = icon.dataset.show === resolved ? 'block' : 'none';
        });
      }
    });
  }

  function setTheme(pref) {
    if (pref === 'system') {
      localStorage.removeItem(KEY);
    } else {
      localStorage.setItem(KEY, pref);
    }
    apply(pref);
  }

  // Apply immediately (FOUC prevention)
  apply(getPreference());

  // React to OS-level theme changes
  matchMedia('(prefers-color-scheme:dark)').addEventListener('change', function () {
    if (getPreference() === 'system') apply('system');
  });

  // Public API
  window.__setTheme = setTheme;
  window.__cycleTheme = function () {
    var order = ['light', 'system', 'dark'];
    var current = order.indexOf(getPreference());
    setTheme(order[(current + 1) % 3]);
  };
})();
