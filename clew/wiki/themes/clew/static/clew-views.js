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
  /* ONCE PER PAGE: a test page loads this from its slices AND its call flow. */
  if (window.clewViewsLoaded) return;
  window.clewViewsLoaded = true;
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
    /* GROUPS (UX review D-8): a group with no visible row hides; while filtering, matches open. */
    Array.prototype.forEach.call(document.querySelectorAll('details.tgroup'), function (g) {
      var any = g.querySelector('tbody tr:not([hidden])');
      g.hidden = !any;
      if (q) g.open = !!any;
    });
  });
  /* CHIPS: a result chip toggles the filter to its result. */
  document.addEventListener('click', function (e) {
    var c = e.target.closest && e.target.closest('[data-filter-chip]');
    var box = c && document.querySelector('[data-filter-table]');
    if (!box) return;
    var want = c.getAttribute('data-filter-chip');
    box.value = box.value === want ? '' : want;
    box.dispatchEvent(new Event('input', { bubbles: true }));
  });
  /* TESTS PLAY (W-6, X-3, owner reviews 2026-11-22): `[data-flow-play]` sections — a test's slices
   * (the steps it ran, `g.st.ex`, captioned by each step's title) and its call flow (the boxes in
   * call order, captioned with each function's brief). Each item is held for its words at 238 wpm,
   * adults' mean silent-reading rate for non-fiction (Brysbaert 2019), never under MIN_MS; the speed
   * control scales it (Mayer & Moreno 2003, segmenting). */
  var WPM = 238, MIN_MS = 1500;
  var KINDS = {
    slices: ['g.st.ex', function (g) { var t = g.querySelector('title'); return t ? t.textContent : ''; }],
    callflow: ['.callflow .box:not(.test)', function (b) {
      return b.textContent + (b.getAttribute('data-brief') ? ': ' + b.getAttribute('data-brief') : '');
    }]
  };
  function player(sec) {
    var kind = KINDS[sec.getAttribute('data-flow-play')];
    if (!kind || sec.getAttribute('data-played')) return;
    sec.setAttribute('data-played', '1');
    var items = Array.prototype.slice.call(sec.querySelectorAll(kind[0])), caption = kind[1];
    var now = sec.querySelector('.slice-now'), speed = sec.querySelector('[data-flow-speed]');
    var cursor = 0, timer = null;
    if (!items.length) return;
    function show(i) {
      items.forEach(function (g, k) { g.classList.toggle('on', k === i); });
      if (now) now.textContent = caption(items[i]);
    }
    function dwell(i) {
      var n = caption(items[i]).split(/\s+/).filter(Boolean).length;
      return Math.max(MIN_MS, n / WPM * 60000) / (speed ? +speed.value || 1 : 1);
    }
    function stop() { if (timer) { clearTimeout(timer); timer = null; } }
    function tick() {
      if (cursor >= items.length) { stop(); return; }
      show(cursor); timer = setTimeout(tick, dwell(cursor++));
    }
    function on(name, fn) {
      var b = sec.querySelector('[data-slice-control=' + name + ']');
      if (b) b.addEventListener('click', fn);
    }
    on('play', function () { stop(); cursor = 0; sec.classList.add('playing'); tick(); });
    on('pause', function () { if (timer) stop(); else if (cursor < items.length) tick(); });
    on('step', function () { stop(); sec.classList.add('playing'); if (cursor >= items.length) cursor = 0; show(cursor++); });
  }
  function players() {
    Array.prototype.forEach.call(document.querySelectorAll('[data-flow-play]'), player);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', players);
  else players();
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', watch);
  else watch();
})();
