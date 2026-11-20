/* clew wiki — entity quick views (round 5, P5.6). A second, budgeted script loaded only by pages
 * that carry a quick view (owner Q/A 2026-11-20); clew.js stays within its own budget.
 * VIEWS: a `.views` strip's `[data-view]` tabs show one `[data-view-panel]` each. A quick view is
 * cloned into the dialog by clew.js, so a MutationObserver sets its first tab when it appears.
 * Without this script every panel stays visible, stacked under its heading. Nothing remote.
 */
(function () {
  'use strict';
  function pick(root, view) {
    Array.prototype.forEach.call(root.querySelectorAll('[data-view-panel]'), function (p) {
      p.hidden = p.getAttribute('data-view-panel') !== view;
    });
    Array.prototype.forEach.call(root.querySelectorAll('.view-tab'), function (b) {
      b.setAttribute('aria-selected', b.getAttribute('data-view') === view ? 'true' : 'false');
    });
  }
  function init(root) {
    var first = root.querySelector('.view-tab');
    if (first && !root.querySelector('.view-tab[aria-selected]')) pick(root, first.getAttribute('data-view'));
  }
  document.addEventListener('click', function (e) {
    var tab = e.target.closest && e.target.closest('.view-tab');
    if (tab) pick(tab.closest('.modal-body') || document, tab.getAttribute('data-view'));
  });
  /* ON DOMContentLoaded: this script sits in the page content and the dialog in the layout after
   * it, so at parse time the dialog does not exist yet (found in a browser: no tab was set). */
  function watch() {
    var dlg = document.getElementById('clew-modal');
    if (!dlg || !window.MutationObserver) return;
    var check = function () {
      var body = dlg.querySelector('.modal-body');
      if (body && body.querySelector('.views')) init(body);
    };
    new MutationObserver(check).observe(dlg, { childList: true, subtree: true });
    check();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', watch);
  else watch();
})();
