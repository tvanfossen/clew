/* clew wiki — the map's FILE layer, drawn when zoomed in (owner 2026-11-22: "the by file divides
 * and interconnects on zoom in the map"). A second, budgeted script (web.js is at its own budget;
 * the clew-views.js precedent): web.js calls webFiles(ctx, k, D, C) inside its world transform,
 * before it draws the dots, so the dots sit on top. Each file is one slice of its block's wedge
 * (web.py `_place`): this shades each file's slice over its rings, names it where the slice is
 * wide enough to read, and draws the calls between files, heavier for more calls. Nothing remote.
 */
function webFiles(ctx, k, D, C) {
  'use strict';
  var F = D.files || [], L = D.file_links || [], G = D.geometry;
  var rMax = G.r0 + (D.max_ring + 1) * G.band, rMid = G.r0 + (rMax - G.r0) * 0.5;
  function at(f, r) { var a = (f.a0 + f.a1) / 2; return [r * Math.cos(a), r * Math.sin(a)]; }
  /* INTERCONNECTS: one curve per pair of files, bowed toward the centre like the block links. */
  var top = 1;
  L.forEach(function (l) { top = Math.max(top, l[2]); });
  ctx.strokeStyle = C['--acc'];
  L.forEach(function (l) {
    var p = at(F[l[0]], rMid), q = at(F[l[1]], rMid), w = l[2] / top;
    ctx.globalAlpha = 0.1 + 0.45 * w;
    ctx.lineWidth = (0.6 + 2.4 * Math.sqrt(w)) / k;
    ctx.beginPath();
    ctx.moveTo(p[0], p[1]);
    ctx.quadraticCurveTo((p[0] + q[0]) * 0.2, (p[1] + q[1]) * 0.2, q[0], q[1]);
    ctx.stroke();
  });
  ctx.globalAlpha = 1;
  /* DIVIDES: each file's slice shaded over the rings its functions occupy, alternate files in
     alternate tints, so a file reads as one patch without spokes crossing the map. */
  function rad(i) { return G.r0 + i * G.band; }
  F.forEach(function (f, i) {
    ctx.beginPath();
    ctx.arc(0, 0, rad(f.r[1] + 0.5), f.a0, f.a1);
    ctx.arc(0, 0, rad(Math.max(f.r[0] - 0.5, 0)), f.a1, f.a0, true);
    ctx.closePath();
    ctx.globalAlpha = i % 2 ? 0.1 : 0.04;
    ctx.fillStyle = C['--ink2'];
    ctx.fill();
  });
  ctx.globalAlpha = 1;
  /* NAMES just outside each file's outermost functions, where its slice is 60 px wide on screen. */
  ctx.fillStyle = C['--ink2'];
  ctx.font = (11 / k) + 'px sans-serif';
  ctx.textAlign = 'center';
  F.forEach(function (f) {
    var r = rad(f.r[1] + 0.5);
    if ((f.a1 - f.a0) * r * k < 60) return;
    var p = at(f, r + 8 / k);
    ctx.fillText(f.file.split('/').pop(), p[0], p[1]);
  });
}
