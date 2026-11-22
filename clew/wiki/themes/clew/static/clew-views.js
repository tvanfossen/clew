/* clew wiki — entity quick views (round 5, P5.6). A second, budgeted script loaded only by pages
 * that carry a quick view (owner Q/A 2026-11-20); clew.js stays within its own budget.
 * VIEWS: a `.views` strip's `[data-view]` tabs show one `[data-view-panel]` each. A quick view is
 * cloned into the dialog by clew.js, so a MutationObserver sets its first tab when it appears.
 * Without this script every panel stays visible, stacked under its heading. Nothing remote.
 * FILTER: an `input[data-filter-table=NAME]` hides `table.NAME` rows whose text lacks what is
 * typed (case-insensitive): the Tests tab's search, since tests leave the main one.
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
  document.addEventListener('input', function (e) {
    var box = e.target, name = box.getAttribute && box.getAttribute('data-filter-table');
    if (!name) return;
    var q = box.value.toLowerCase();
    Array.prototype.forEach.call(document.querySelectorAll('table.' + name + ' tbody tr'), function (r) {
      r.hidden = q !== '' && r.textContent.toLowerCase().indexOf(q) < 0;
    });
  });
  /* SLICES PLAY (W-6, owner review 2026-11-22): a test page's exercised steps (`g.st.ex`), in
   * order, each held for its words at 238 wpm, adults' mean silent-reading rate for non-fiction
   * (Brysbaert 2019), never under MIN_MS; the speed control scales it (Mayer & Moreno 2003,
   * segmenting). The caption is each step's own title. */
  var WPM = 238, MIN_MS = 1500;
  function slicePlayer(sec) {
    var steps = Array.prototype.slice.call(sec.querySelectorAll('g.st.ex'));
    var now = sec.querySelector('.slice-now'), speed = sec.querySelector('[data-flow-speed]');
    var cursor = 0, timer = null;
    if (!steps.length) return;
    function title(g) { var t = g.querySelector('title'); return t ? t.textContent : ''; }
    function show(i) {
      steps.forEach(function (g, k) { g.classList.toggle('on', k === i); });
      if (now) now.textContent = title(steps[i]);
    }
    function dwell(i) {
      var n = title(steps[i]).split(/\s+/).filter(Boolean).length;
      return Math.max(MIN_MS, n / WPM * 60000) / (speed ? +speed.value || 1 : 1);
    }
    function stop() { if (timer) { clearTimeout(timer); timer = null; } }
    function tick() {
      if (cursor >= steps.length) { stop(); return; }
      show(cursor); timer = setTimeout(tick, dwell(cursor++));
    }
    function on(name, fn) {
      var b = sec.querySelector('[data-slice-control=' + name + ']');
      if (b) b.addEventListener('click', fn);
    }
    on('play', function () { stop(); cursor = 0; sec.classList.add('playing'); tick(); });
    on('pause', function () { if (timer) stop(); else if (cursor < steps.length) tick(); });
    on('step', function () { stop(); sec.classList.add('playing'); if (cursor >= steps.length) cursor = 0; show(cursor++); });
  }
  function slices() {
    Array.prototype.forEach.call(document.querySelectorAll('section.exercises'), slicePlayer);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', slices);
  else slices();
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', watch);
  else watch();
})();
