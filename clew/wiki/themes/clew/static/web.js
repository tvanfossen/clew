/* clew wiki — the repository web (round 4, R3). Geometry comes laid out from Python; this file
 * only draws it, pans, zooms, moves the camera and lets the reader walk calls. Nothing remote. */
(function(){
"use strict";
var root=document.querySelector("[data-web]");if(!root)return;
var D=JSON.parse(document.getElementById("web-data").textContent);
var cv=root.querySelector("canvas"),ctx=cv.getContext("2d"),panel=root.querySelector("[data-web-panel]");
var tip=root.querySelector("[data-web-tip]"),reduce=matchMedia("(prefers-reduced-motion: reduce)").matches;
var N=D.nodes,B=D.blocks,G=D.geometry,LOD=0.55,cam={x:0,y:0,k:1},sel=-1,lens="tier",flow=null,lit={};
var outN=[],inN=[];N.forEach(function(){outN.push([]);inN.push([]);});
D.edges.forEach(function(e){outN[e[0]].push(e[1]);inN[e[1]].push(e[0]);});
var rMax=G.r0+(D.max_ring+1)*G.band;
function css(n){return getComputedStyle(document.documentElement).getPropertyValue(n).trim()||"#888";}
var C={};function colors(){["--ink","--ink2","--faint","--rule","--rule2","--paper","--surface","--muted","--acc","--err","--warn","--root","--inset","--accbg"].forEach(function(n){C[n]=css(n);});}
var TIER={PASS:"--acc",GAP:"--err",NOT_RUN:"--warn",TARGET:"--root",MISSING:"--inset",EXEMPT:"--rule"};
var OWN=["--acc","--root","--warn","--ink2","--inset","--rule"];
function hue(s){for(var h=0,i=0;i<s.length;i++)h=(h*31+s.charCodeAt(i))|0;return C[OWN[Math.abs(h)%OWN.length]];}
var pending=0,snap=null,idle=0;function later(){if(!pending)pending=requestAnimationFrame(function(){pending=0;quick();});}
function quick(){var d=devicePixelRatio||1;if(!snap){var im=document.createElement("canvas");im.width=cv.width;im.height=cv.height;im.getContext("2d").drawImage(cv,0,0);snap={im:im,x:cam.x,y:cam.y,k:cam.k};}
 var s=cam.k/snap.k,tx=((snap.x-cam.x)*cam.k+W()/2-s*W()/2)*d,ty=((snap.y-cam.y)*cam.k+H()/2-s*H()/2)*d;
 ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,cv.width,cv.height);ctx.drawImage(snap.im,tx,ty,cv.width*s,cv.height*s);ctx.setTransform(d,0,0,d,0,0);
 clearTimeout(idle);idle=setTimeout(function(){snap=null;draw();},140);}
function size(){var r=cv.getBoundingClientRect(),d=devicePixelRatio||1;cv.width=Math.max(1,r.width*d);cv.height=Math.max(1,r.height*d);ctx.setTransform(d,0,0,d,0,0);draw();}
function W(){return cv.width/(devicePixelRatio||1);}function H(){return cv.height/(devicePixelRatio||1);}
function fitK(){return Math.min(W(),H())/(2*rMax+260);}
function toS(x,y){return[(x-cam.x)*cam.k+W()/2,(y-cam.y)*cam.k+H()/2];}
function toW(sx,sy){return[(sx-W()/2)/cam.k+cam.x,(sy-H()/2)/cam.k+cam.y];}
function mid(b){var a=(b.a0+b.a1)/2,r=(G.r0+rMax)/2;return[r*Math.cos(a),r*Math.sin(a)];}
function wedge(b,r0,r1){ctx.beginPath();ctx.arc(0,0,r1,b.a0,b.a1);ctx.arc(0,0,r0,b.a1,b.a0,true);ctx.closePath();}
function draw(){
 var k=cam.k,zoomed=k>=LOD*fitK()*2.2;ctx.clearRect(0,0,W(),H());
 ctx.save();ctx.translate(W()/2,H()/2);ctx.scale(k,k);ctx.translate(-cam.x,-cam.y);
 for(var r=0;r<=D.max_ring;r++){ctx.beginPath();ctx.arc(0,0,G.r0+r*G.band,0,7);ctx.strokeStyle=C["--rule2"];ctx.lineWidth=1/k;ctx.stroke();}
 B.forEach(function(b,i){wedge(b,G.r0-G.band/2,rMax);ctx.fillStyle=lit[i]?C["--accbg"]:(i%2?C["--paper"]:C["--muted"]);ctx.globalAlpha=zoomed?0.45:0.9;ctx.fill();ctx.globalAlpha=1;ctx.strokeStyle=C["--rule"];ctx.lineWidth=1/k;ctx.stroke();});
 if(!zoomed)links();else nodes();
 ctx.restore();labels(zoomed);
}
function links(){var idx={};B.forEach(function(b,i){idx[b.id]=i;});var top=1;D.links.forEach(function(l){top=Math.max(top,l.calls);});
 D.links.forEach(function(l){var a=B[idx[l.from]],b=B[idx[l.to]];if(!a||!b)return;var p=mid(a),q=mid(b);
  ctx.beginPath();ctx.moveTo(p[0],p[1]);ctx.quadraticCurveTo((p[0]+q[0])*0.2,(p[1]+q[1])*0.2,q[0],q[1]);
  ctx.strokeStyle=C["--ink2"];ctx.globalAlpha=0.35;ctx.lineWidth=(1+5*Math.sqrt(l.calls/top))/cam.k;ctx.stroke();ctx.globalAlpha=1;});}
function col(n){if(lens==="owner")return n.owner?hue(n.owner):C["--faint"];if(lens==="changed")return n.changed?C["--warn"]:C["--rule"];if(lens==="block")return n.block%2?C["--ink2"]:C["--faint"];return n.tier?C[TIER[n.tier]||"--faint"]:C["--faint"];}
function nodes(){var k=cam.k,rad=Math.max(1.6,3.2/Math.sqrt(k))/1;
 if(sel>=0){ctx.lineWidth=1.2/k;edgeSet(sel,outN,C["--acc"]);edgeSet(sel,inN,C["--root"]);}
 if(flow){ctx.beginPath();flow.steps.forEach(function(s,i){var n=N[s];if(i)ctx.lineTo(n.x,n.y);else ctx.moveTo(n.x,n.y);});ctx.strokeStyle=C["--err"];ctx.lineWidth=2/k;ctx.stroke();}
 var w=W(),h=H(),m=rad*k+2,g={};
 for(var i=0;i<N.length;i++){var n=N[i],sx=(n.x-cam.x)*k+w/2,sy=(n.y-cam.y)*k+h/2;if(sx<-m||sy<-m||sx>w+m||sy>h+m)continue;var c=col(n);(g[c]||(g[c]=[])).push(n);}
 for(var c in g){ctx.beginPath();g[c].forEach(function(n){ctx.moveTo(n.x+rad,n.y);ctx.arc(n.x,n.y,rad,0,7);});ctx.fillStyle=c;ctx.fill();}
 if(sel>=0){var s=N[sel];ctx.beginPath();ctx.arc(s.x,s.y,rad*2.4,0,7);ctx.strokeStyle=C["--ink"];ctx.lineWidth=2/k;ctx.stroke();}}
function edgeSet(i,list,c){list[i].forEach(function(j){ctx.beginPath();ctx.moveTo(N[i].x,N[i].y);ctx.lineTo(N[j].x,N[j].y);ctx.strokeStyle=c;ctx.stroke();});}
function labels(zoomed){ctx.font="600 12px Manrope,system-ui,sans-serif";ctx.textAlign="center";ctx.textBaseline="middle";
 B.forEach(function(b,i){var a=(b.a0+b.a1)/2,r=rMax+18,p=toS(r*Math.cos(a),r*Math.sin(a));if((b.a1-b.a0)*rMax*cam.k<24&&!lit[i])return;
  ctx.fillStyle=C["--ink"];ctx.fillText(short(b.id,36),p[0],p[1]);
  if(!zoomed){ctx.font="400 11px Manrope,system-ui,sans-serif";ctx.fillStyle=C["--ink2"];ctx.fillText(b.functions+" functions",p[0],p[1]+14);ctx.font="600 12px Manrope,system-ui,sans-serif";}});
 if(cam.k<fitK()*7)return;ctx.font="400 11px 'JetBrains Mono',monospace";ctx.textAlign="left";var shown=0;
 for(var i=0;i<N.length&&shown<220;i++){var p=toS(N[i].x,N[i].y);if(p[0]<0||p[1]<0||p[0]>W()||p[1]>H())continue;ctx.fillStyle=C["--ink2"];ctx.fillText(N[i].name,p[0]+6,p[1]);shown++;}}
function short(s,n){return s.length>n?s.slice(0,n-1)+"…":s;}
/* A deep link lands instantly on load; later moves animate.
 * Camera: a smooth zoom-and-pan path (van Wijk & Nuij 2003, simplified): zoom out while moving
 * far, back in on arrival. Instant when the reader prefers reduced motion. */
var anim=0;
function fly(x,y,k,done){cancelAnimationFrame(anim);var s={x:cam.x,y:cam.y,k:cam.k};
 if(reduce){cam={x:x,y:y,k:k};draw();if(done)done();return;}
 var dist=Math.hypot(x-s.x,y-s.y)*Math.min(s.k,k),span=Math.min(W(),H()),dip=Math.min(0.8,dist/(span*2.5)),t0=performance.now(),T=650+Math.min(600,dist/3);
 (function step(t){var u=Math.min(1,(t-t0)/T),e=u<.5?2*u*u:1-Math.pow(-2*u+2,2)/2;
  cam.x=s.x+(x-s.x)*e;cam.y=s.y+(y-s.y)*e;cam.k=Math.exp(Math.log(s.k)+(Math.log(k)-Math.log(s.k))*e)*(1-dip*Math.sin(Math.PI*u));
  draw();if(u<1)anim=requestAnimationFrame(step);else if(done)done();})(t0);}
function fit(){fly(0,0,fitK());}
function focusNode(i,walk){sel=i;var n=N[i];fly(n.x,n.y,Math.max(cam.k,fitK()*9));show(i);if(!walk)hash("n="+encodeURIComponent(n.name+"@"+n.file));}
function focusBlock(i){var b=B[i],p=mid(b),span=Math.max(0.25,b.a1-b.a0);lit={};lit[i]=1;fly(p[0],p[1],Math.min(fitK()*6,fitK()*2.6/Math.min(1,span)));hash("b="+i);blockPanel(i);}
function hash(h){history.replaceState(null,"","#"+h);}
function link(i){var n=N[i];return'<button type="button" data-go="'+i+'">'+esc(n.name)+"</button>";}
function esc(s){return String(s).replace(/[&<>"]/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];});}
function list(t,xs){return xs.length?"<h4>"+t+" ("+xs.length+")</h4><ul>"+xs.slice(0,40).map(function(j){return"<li>"+link(j)+"</li>";}).join("")+(xs.length>40?"<li>… "+(xs.length-40)+" more</li>":"")+"</ul>":"<h4>"+t+"</h4><p>none drawn</p>";}
function show(i){var n=N[i],h='<button type="button" class="web-x" data-close aria-label="Close">×</button><h3>'+esc(n.name)+'</h3><p class="web-file">'+esc(n.file)+(n.line?":"+n.line:"")+"</p>"+(n.owner?'<p class="web-owner">Owner '+esc(n.owner)+"</p>":"")+"<p>"+esc(B[n.block].id)+" · ring "+n.ring+(n.tier?' · <span class="tier t-'+n.tier+'">'+n.tier+"</span>":"")+"</p>";
 if(n.href)h+='<p><a href="'+esc(n.href)+'">Source and dossier →</a></p>';h+=list("Calls",outN[i])+list("Called by",inN[i]);panel.innerHTML=h;panel.hidden=false;}
function blockPanel(i){var b=B[i],h='<button type="button" class="web-x" data-close aria-label="Close">×</button><h3>'+esc(b.id)+"</h3><p>"+b.functions+" functions · "+b.files+" files"+(b.declared?" · declared":"")+"</p>";
 if((b.inferred_files||[]).length)h+="<h4>Placed by coupling</h4><ul>"+b.inferred_files.map(function(f){return"<li><code>"+esc(f)+"</code></li>";}).join("")+"</ul>";
 if((b.req_ids||[]).length)h+="<h4>Requirements</h4><ul>"+b.req_ids.map(function(r){return'<li><a href="req-'+esc(r[0])+'.html">'+esc(r[0])+'</a> <span class="tier t-'+r[1]+'">'+r[1]+"</span></li>";}).join("")+"</ul>";
 panel.innerHTML=h;panel.hidden=false;}
function hit(sx,sy){var w=toW(sx,sy),best=-1,bd=(8/cam.k)*(8/cam.k);
 if(cam.k>=LOD*fitK()*2.2)for(var i=0;i<N.length;i++){var dx=N[i].x-w[0],dy=N[i].y-w[1],d=dx*dx+dy*dy;if(d<bd){bd=d;best=i;}}
 if(best>=0)return{n:best};var r=Math.hypot(w[0],w[1]),a=(Math.atan2(w[1],w[0])+2*Math.PI)%(2*Math.PI);
 if(r<G.r0-G.band/2||r>rMax+30)return null;for(var j=0;j<B.length;j++)if(a>=B[j].a0&&a<=B[j].a1)return{b:j};return null;}
var drag=null,moved=0;
cv.addEventListener("pointerdown",function(e){drag={x:e.clientX,y:e.clientY,cx:cam.x,cy:cam.y};moved=0;cv.setPointerCapture(e.pointerId);});
cv.addEventListener("pointermove",function(e){var r=cv.getBoundingClientRect();
 if(drag){var dx=e.clientX-drag.x,dy=e.clientY-drag.y;moved+=Math.abs(dx)+Math.abs(dy);cam.x=drag.cx-dx/cam.k;cam.y=drag.cy-dy/cam.k;later();return;}
 var h=hit(e.clientX-r.left,e.clientY-r.top);if(h&&h.n!==undefined){tip.textContent=N[h.n].name+" — "+N[h.n].file;}else if(h){tip.textContent=B[h.b].id+" — "+B[h.b].functions+" functions";}
 tip.hidden=!h;if(h){tip.style.left=(e.clientX-r.left+12)+"px";tip.style.top=(e.clientY-r.top+12)+"px";}});
cv.addEventListener("pointerup",function(e){var r=cv.getBoundingClientRect();drag=null;if(moved>6)return;var h=hit(e.clientX-r.left,e.clientY-r.top);if(!h)return;if(h.n!==undefined)focusNode(h.n);else focusBlock(h.b);});
cv.addEventListener("pointerleave",function(){tip.hidden=true;});
cv.addEventListener("wheel",function(e){e.preventDefault();var r=cv.getBoundingClientRect(),sx=e.clientX-r.left,sy=e.clientY-r.top,w=toW(sx,sy),f=Math.exp(-e.deltaY*0.0015);
 cam.k=Math.min(fitK()*60,Math.max(fitK()*0.5,cam.k*f));var w2=toW(sx,sy);cam.x+=w[0]-w2[0];cam.y+=w[1]-w2[1];later();},{passive:false});
root.addEventListener("click",function(e){var g=e.target.closest("[data-go]");if(g){focusNode(+g.dataset.go,true);return;}
 if(e.target.closest("[data-close]")){panel.hidden=true;sel=-1;lit={};draw();return;}
 var z=e.target.closest("[data-web-zoom]");if(z)fly(cam.x,cam.y,cam.k*+z.dataset.webZoom);if(e.target.closest("[data-web-fit]")){sel=-1;lit={};panel.hidden=true;fit();}});
var lensSel=root.querySelector("[data-web-lens]");if(lensSel)lensSel.addEventListener("change",function(){lens=lensSel.value;draw();});
var q=root.querySelector("[data-web-search]");q.addEventListener("keydown",function(e){if(e.key!=="Enter")return;var t=q.value.trim().toLowerCase();if(!t)return;
 var i=N.findIndex(function(n){return n.name.toLowerCase()===t;});if(i<0)i=N.findIndex(function(n){return n.name.toLowerCase().indexOf(t)>=0;});if(i>=0)focusNode(i);});
var fsel=root.querySelector("[data-web-flow]");if(fsel)fsel.addEventListener("change",function(){var f=D.flows[+fsel.value];flow=f||null;if(!f){draw();return;}var i=0;
 (function next(){if(flow!==f||i>=f.steps.length)return;sel=f.steps[i];show(sel);var n=N[sel];fly(n.x,n.y,Math.max(cam.k,fitK()*7),function(){i++;setTimeout(next,reduce?0:450);});})();});
document.addEventListener("keydown",function(e){if(e.key==="Escape"&&!panel.hidden){panel.hidden=true;sel=-1;lit={};draw();}});
function fromHash(){var h=decodeURIComponent(location.hash.slice(1));if(h.indexOf("lens=")===0){var l=h.slice(5)==="change"?"changed":h.slice(5);if(lensSel&&[].some.call(lensSel.options,function(o){return o.value===l;})){lens=l;lensSel.value=l;fly(0,0,fitK()*2.4);}return;}if(h.indexOf("b=")===0){var b=+h.slice(2);if(B[b])focusBlock(b);}
 else if(h.indexOf("n=")===0){var p=h.slice(2).split("@"),i=N.findIndex(function(n){return n.name===p[0]&&(!p[1]||n.file===p[1]);});if(i>=0)focusNode(i,true);}}
colors();new ResizeObserver(size).observe(cv);cam.k=fitK()||1;size();cam.k=fitK();draw();var keep=reduce;reduce=true;fromHash();reduce=keep;
function retheme(){colors();later();}matchMedia("(prefers-color-scheme: dark)").addEventListener("change",retheme);
new MutationObserver(retheme).observe(document.documentElement,{attributes:true,attributeFilter:["data-theme"]});
})();
