/* clew wiki — the one script every page loads (round 3, P1b). Nothing remote, no dependency.
 *
 * MODAL: one <dialog id="clew-modal"> per page. A trigger `[data-modal=KEY]` opens the inert
 * <template id="modal-KEY"> Python wrote (cloned, never parsed from strings); a page script may
 * register a builder for a key prefix (`clewModal.register('step-', fn)`). Opening pushes `#m=KEY`
 * so the state is a link and the BACK BUTTON closes it; Esc closes natively; focus returns to
 * the opener. showModal() makes the rest of the page inert, which is the focus trap.
 * MENU: below 860px the top bar's sections fold behind a labelled button.
 * GROUPS: a `[data-req-filter]` card shows only its group's `tr[data-group]` rows; again clears.
 * MAP: `[data-lens]` / `[data-level-set]` buttons set the block's lens and zoom level; CSS does
 * the rest; the `[data-trace-set]` picker shows one flow's trace. A `role=button` trigger (an SVG box) opens on Enter or Space.
 * PAN / ZOOM: a `[data-pz]` wrapper's SVG zooms on ctrl+wheel and the +/-/reset buttons, and pans
 * by dragging, through its viewBox.
 */
(function () {
  'use strict';
  var dlg = document.getElementById('clew-modal'), builders = {}, opener = null, openKey = '';

  function keyFromHash() {
    var m = /^#m=([\w.:-]+)$/.exec(location.hash);
    return m ? m[1] : '';
  }
  function content(key) {
    var tpl = document.getElementById('modal-' + key);
    if (tpl) return { title: tpl.getAttribute('data-title') || key, node: tpl.content.cloneNode(true) };
    for (var p in builders) if (key.indexOf(p) === 0) return builders[p](key.slice(p.length));
    return null;
  }
  function show(key, push) {
    var c = dlg && content(key);
    if (!c) return false;
    document.getElementById('clew-modal-title').textContent = c.title;
    var body = dlg.querySelector('.modal-body');
    body.textContent = '';
    body.appendChild(c.node);
    openKey = key;
    if (push && keyFromHash() !== key) history.pushState({ m: key }, '', '#m=' + key);
    if (!dlg.open) dlg.showModal();
    return true;
  }
  function closed() {
    openKey = '';
    if (keyFromHash()) history.back();
    if (opener && opener.focus) opener.focus();
  }
  if (dlg) {
    dlg.addEventListener('close', closed);
    dlg.querySelector('.modal-close').addEventListener('click', function () { dlg.close(); });
    dlg.addEventListener('click', function (e) { if (e.target === dlg) dlg.close(); });
    document.addEventListener('click', function (e) {
      var t = e.target.closest && e.target.closest('[data-modal]');
      if (!t) return;
      e.preventDefault();
      opener = t;
      show(t.getAttribute('data-modal'), true);
    });
    window.addEventListener('popstate', function () {
      var key = keyFromHash();
      if (!key && dlg.open) { openKey = ''; dlg.close(); }
      else if (key && key !== openKey) show(key, false);
    });
  }
  window.clewModal = {
    register: function (prefix, fn) {
      builders[prefix] = fn;
      var key = keyFromHash();
      if (key && key.indexOf(prefix) === 0) show(key, false);
    },
    open: function (key, from) { opener = from || document.activeElement; return show(key, true); }
  };
  document.addEventListener('DOMContentLoaded', function () {
    var key = keyFromHash();
    if (key) show(key, false);
  });

  document.addEventListener('keydown', function (e) {
    var t = e.target;
    if ((e.key === 'Enter' || e.key === ' ') && t.getAttribute && t.getAttribute('role') === 'button' && t.hasAttribute('data-modal')) {
      e.preventDefault(); opener = t; show(t.getAttribute('data-modal'), true);
    }
  });
  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-lens],[data-level-set]');
    var block = b && b.closest('.map-block');
    if (!block) return;
    var attr = b.hasAttribute('data-lens') ? 'data-lens' : 'data-level-set';
    block.setAttribute(attr === 'data-lens' ? 'data-lens-current' : 'data-level', b.getAttribute(attr));
    Array.prototype.forEach.call(block.querySelectorAll('[' + attr + ']'), function (o) {
      o.setAttribute('aria-pressed', String(o === b));
    });
  });

  document.addEventListener('change', function (e) {
    var s = e.target, block = s.closest && s.hasAttribute('data-trace-set') && s.closest('.map-block');
    if (!block) return;
    Array.prototype.forEach.call(block.querySelectorAll('g.trace'), function (g) {
      g.classList.toggle('on', g.getAttribute('data-trace') === s.value);
    });
  });

  document.addEventListener('click', function (e) {
    var card = e.target.closest && e.target.closest('[data-req-filter]');
    if (!card) return;
    var on = card.getAttribute('aria-pressed') !== 'true', g = card.getAttribute('data-req-filter');
    Array.prototype.forEach.call(document.querySelectorAll('[data-req-filter]'), function (c) {
      c.setAttribute('aria-pressed', String(on && c === card));
    });
    Array.prototype.forEach.call(document.querySelectorAll('tr[data-group]'), function (r) {
      r.hidden = on && r.getAttribute('data-group') !== g;
    });
  });

  var toggle = document.querySelector('.menu-toggle');
  if (toggle) toggle.addEventListener('click', function () {
    var open = toggle.getAttribute('aria-expanded') !== 'true';
    toggle.setAttribute('aria-expanded', String(open));
    document.querySelector('.top').classList.toggle('open', open);
  });

  function panZoom(wrap) {
    var svg = wrap.querySelector('svg');
    if (!svg || !svg.viewBox || !svg.viewBox.baseVal || !svg.viewBox.baseVal.width) return;
    var base = svg.viewBox.baseVal, home = [base.x, base.y, base.width, base.height], v = home.slice(), drag = null;
    function apply() { svg.setAttribute('viewBox', v.join(' ')); }
    function zoom(f) {
      var cx = v[0] + v[2] / 2, cy = v[1] + v[3] / 2;
      v[2] *= f; v[3] *= f; v[0] = cx - v[2] / 2; v[1] = cy - v[3] / 2; apply();
    }
    wrap.addEventListener('wheel', function (e) {
      if (!e.ctrlKey) return;
      e.preventDefault(); zoom(e.deltaY > 0 ? 1.15 : 1 / 1.15);
    }, { passive: false });
    svg.addEventListener('pointerdown', function (e) {
      if (e.target.closest('[data-step],[data-modal],a')) return;
      drag = [e.clientX, e.clientY, v[0], v[1]];
    });
    window.addEventListener('pointermove', function (e) {
      if (!drag) return;
      var s = v[2] / svg.clientWidth;
      v[0] = drag[2] - (e.clientX - drag[0]) * s; v[1] = drag[3] - (e.clientY - drag[1]) * s; apply();
    });
    window.addEventListener('pointerup', function () { drag = null; });
    var bar = document.createElement('div');
    bar.className = 'pz-bar';
    [['+', 1 / 1.25], ['−', 1.25], ['reset', 0]].forEach(function (b) {
      var btn = document.createElement('button');
      btn.type = 'button'; btn.textContent = b[0];
      btn.setAttribute('aria-label', b[1] ? (b[1] < 1 ? 'zoom in' : 'zoom out') : 'reset view');
      btn.addEventListener('click', function () { if (b[1]) zoom(b[1]); else { v = home.slice(); apply(); } });
      bar.appendChild(btn);
    });
    wrap.insertBefore(bar, wrap.firstChild);
  }
  Array.prototype.forEach.call(document.querySelectorAll('[data-pz]'), panZoom);
})();
