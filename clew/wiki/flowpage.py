# SPDX-License-Identifier: MIT
"""One flow's page: the diagram, its interactive layer, the step table and the bodies reached.

1.4.0 W5, and W18 (owner 2026-11-15: "interactive", "show data carried in modal"). The diagram
is `svg.flow_svg`; around it the page adds, inline and same-origin:

  * PLAY / PAUSE / STEP controls — replay the animation, freeze it, or reveal one step at a time;
  * the site's shared MODAL per step (round 3, P1b: `#m=step-N`), opened by clicking it, holding
    the DATA THE STEP CARRIES: the call
    expression as written at the call site (the arguments passed), the callee's signature and
    brief (what it receives), the frames around the call, and a link to the call site.

The step data is a JSON block the script reads with `textContent` and writes with `textContent` —
no repository text is ever parsed as HTML. An audience that EXCLUDES BODIES gets no call text: the
call expression is source code, so it is redacted like a body (signatures stay — they are the
interface).

@brief Render a flow page.
@version 3
"""

from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path
from typing import Any, NamedTuple

from .config import Audience, FlowSpec, WikiConfig
from .flow import Flow, derive_flow
from .lanes import per_flow_lanes
from .htmltable import code, gherkin, md_title, plural, source_url, table
from .slices import slices_of
from .svg import flow_svg
from .symbols import symbol_href


## @brief A written flow page: its name, title, the files its steps pass through, and its hops.
## v2: `hops`, for the map's flow traces (round 3, P1c-3).
## v3: `functions`, so a requirement lists the flows its implementers are on (P1d).
## v4: `role`, `steps`, `requirements` — the Flows page groups and summarises them (P1e).
## v5: `calls`, for llms-full.txt (P3b).
## @version 5
class FlowPage(NamedTuple):
    """@brief A flow page. @version 6"""

    name: str
    title: str
    files: frozenset[str]
    ## (caller's file, callee's file) per step, in call order.
    hops: tuple[tuple[str, str], ...] = ()
    ## (function, file) of every caller and callee — what a requirement's implementer must be.
    functions: frozenset[tuple[str, str]] = frozenset()
    ## `product`, `threads` or `tooling`.
    role: str = ""
    ## How many steps the flow draws.
    steps: int = 0
    ## Requirements its functions implement.
    requirements: frozenset[str] = frozenset()
    ## (caller, callee) per step, in call order.
    calls: tuple[tuple[str, str], ...] = ()
    ## Round 5: the derived flow, and each test's slice of it (from per-test coverage).
    flow: Any = None
    slices: Any = None
    ## W-1 (owner review 2026-11-22): the flow's declared intent, shown under its title.
    intent: str = ""


## The most lines a call expression is read across.
_CALL_LINES = 6
## The page's interactive layer: no dependency, nothing remote.
_SCRIPT = """<script>document.addEventListener('DOMContentLoaded',function(){
document.querySelectorAll('.flow-block').forEach(function(block){
 var data=JSON.parse(block.querySelector('script.flow-data').textContent);
 var svg=block.querySelector('svg.seq'),cursor=0;
 var groups=Array.prototype.slice.call(svg.querySelectorAll('g[data-step]'));
 function row(dl,k,v,code){if(!v)return;var dt=document.createElement('dt'),dd=document.createElement('dd');
  dt.textContent=k;var el=code?document.createElement('pre'):document.createElement('span');el.textContent=v;
  dd.appendChild(el);dl.appendChild(dt);dl.appendChild(dd);}
 function at(i){return svg.querySelector('g[data-step="'+i+'"]');}
 /* LIVE SYNC (P5.6): the step table follows the diagram, and a row opens its step. */
 var trs=Array.prototype.slice.call(document.querySelectorAll('table.steps tr[data-step]'));
 function sync(g){var ids=(g.getAttribute('data-steps')||g.getAttribute('data-step')).split(' '),first=null;
  trs.forEach(function(r){var on=ids.indexOf(r.getAttribute('data-step'))>=0;r.classList.toggle('on',on);if(on&&!first)first=r;});
  }
 trs.forEach(function(r){r.addEventListener('click',function(){var g=at(r.getAttribute('data-step'));
  if(g&&window.clewModal)window.clewModal.open('step-'+g.getAttribute('data-step'),g);});});
 function build(n){var i=+n,s=data[i],g=at(i);if(!s||!g)return null;groups.forEach(function(g){g.classList.remove('sel');});
  g.classList.add('sel');sync(g);var f=document.createDocumentFragment(),dl=document.createElement('dl');
  dl.className='kv';row(dl,'call',s.call,true);row(dl,'callee',s.callee_qualified);
  row(dl,'receives',s.signature,true);row(dl,'brief',s.brief);row(dl,'frames',s.frames);
  row(dl,'ambiguous',s.ambiguous);row(dl,'at',s.site);
  row(dl,'called with',s.called_with,true);row(dl,'returned',s.returned,true);f.appendChild(dl);
  if(s.link){var a=document.createElement('a');a.href=s.link;a.textContent='open the call site';f.appendChild(a);}
  return {title:(i+1)+'. '+s.caller+' \\u2192 '+s.callee,node:f};}
 if(window.clewModal)window.clewModal.register('step-',build);
 groups.forEach(function(g){g.addEventListener('animationstart',function(){sync(g);});});
 groups.forEach(function(g){g.addEventListener('click',function(){
  if(presenting){now(+g.getAttribute('data-step'));return;}
  window.clewModal&&window.clewModal.open('step-'+g.getAttribute('data-step'),g);});});
 function control(name,fn){var b=block.querySelector('[data-flow-control='+name+']');if(b)b.addEventListener('click',fn);}
 /* W-3 (owner review 2026-11-22): READING PACE. A step dwells for its words at 238 wpm, adults'
    mean silent-reading rate for non-fiction (Brysbaert 2019, J. Memory and Language 109:104047),
    never under MIN_MS; the speed control scales it. Learner-paced segments: Mayer & Moreno 2003. */
 var WPM=238,MIN_MS=1500,timer=null,speedEl=block.querySelector('[data-flow-speed]');
 var modal=document.getElementById('clew-modal'),wrap=block.querySelector('.flow-wrap'),home=wrap&&wrap.parentNode;
 var stage=null,presenting=false;
 function words(s){return [s.caller,s.callee,s.brief,s.call].join(' ').split(/\s+/).filter(Boolean).length;}
 function dwell(i){var s=data[i]||{},sp=speedEl?+speedEl.value:1;return Math.max(MIN_MS,words(s)/WPM*60000)/(sp||1);}
 function now(i){if(!presenting)return;var b=build(i),box=stage.querySelector('.flow-now');if(!b||!box)return;
  box.textContent='';
  /* X-1: the scenario line this step builds, above the step itself. */
  if(data[i]&&data[i].seg){var g=document.createElement('p');g.className='now-seg';g.textContent=data[i].seg;box.appendChild(g);}
  var h=document.createElement('h3');h.textContent=b.title;box.appendChild(h);box.appendChild(b.node);}
 function show(i){if(!svg.classList.contains('stepping')){svg.classList.add('stepping');groups.forEach(function(g){g.classList.remove('on');});}
  groups.forEach(function(g,k){g.classList.toggle('on',k<=i);});sync(groups[i]);now(+groups[i].getAttribute('data-step'));}
 function stop(){if(timer){clearTimeout(timer);timer=null;}}
 function tick(){if(cursor>=groups.length){stop();return;}show(cursor);var i=cursor++;timer=setTimeout(tick,dwell(+groups[i].getAttribute('data-step')));}
 control('play',function(){stop();svg.classList.remove('paused');cursor=0;tick();});
 control('pause',function(){if(timer)stop();else if(cursor<groups.length)tick();});
 control('step',function(){stop();if(cursor>=groups.length)cursor=0;show(cursor);cursor++;});
 function label(){var o=block.querySelectorAll('[data-flow-speed-label]');for(var k=0;k<o.length;k++)o[k].textContent='\u00d7'+(+speedEl.value);}
 if(speedEl){speedEl.addEventListener('input',label);label();}
 /* W-7: PRESENT, in the page's one modal (`clew-modal`): the controls, the diagram and the current
    step side by side; the table stays on the page. Closing moves them back. */
 function present(){var ctl=home.querySelector('.flow-controls');stage=document.createElement('div');
  stage.className='flow-present-body';var st=document.createElement('div');st.className='flow-stage';
  var aside=document.createElement('aside');aside.className='flow-now';aside.setAttribute('aria-live','polite');
  aside.textContent='Play or step to read each call here.';st.appendChild(ctl);st.appendChild(wrap);
  stage.appendChild(st);stage.appendChild(aside);presenting=true;modal.classList.add('wide');
  return {title:((document.querySelector('h1')||{}).textContent||'Flow').replace(/\u00b6/g,'').trim(),node:stage};}
 if(window.clewModal&&modal){window.clewModal.register('flow-present',present);
  modal.addEventListener('close',function(){if(!presenting)return;presenting=false;modal.classList.remove('wide');
   home.insertBefore(stage.querySelector('.flow-controls'),home.firstChild);home.appendChild(wrap);});}
 control('present',function(){if(presenting||!window.clewModal)return;window.clewModal.open('flow-present',this);
  if(cursor>0)now(+groups[cursor-1].getAttribute('data-step'));});
 var sl=document.getElementById('flow-slices'),slices=sl?JSON.parse(sl.textContent):{};
 function lit(){var m=/^#test=(.+)$/.exec(location.hash),t=m&&decodeURIComponent(m[1]),on=t&&slices[t];
  var note=block.querySelector('.slice-note');if(note)note.remove();
  groups.forEach(function(g){var ids=(g.getAttribute('data-steps')||g.getAttribute('data-step')).split(' ');
   var hit=on&&ids.some(function(k){return on.indexOf(+k)>=0;});
   g.classList.toggle('ex',!!hit);g.classList.toggle('dim',!!on&&!hit);});
  if(on){var p=document.createElement('p');p.className='slice-note';
   p.textContent='Lit: the steps test '+t+' exercised ('+on.length+' of '+data.length+').';
   block.insertBefore(p,block.firstChild);}}
 lit();window.addEventListener('hashchange',lit);
 /* A-1 (UX review): an overview row brings its first step into view in the diagram's box. */
 function holder(i){return at(i)||groups.filter(function(g){return (g.getAttribute('data-steps')||'').split(' ').indexOf(String(i))>=0;})[0];}
 var ov=block.previousElementSibling;if(ov&&ov.classList.contains('flow-overview'))ov.addEventListener('click',function(e){
  var li=e.target.closest('[data-goto]'),g=li&&holder(+li.getAttribute('data-goto'));if(!g)return;
  groups.forEach(function(x){x.classList.remove('sel');});g.classList.add('sel');sync(g);
  var b=g.getBBox();/* inside the diagram's own box only: the page never jumps (W-7). */wrap.scrollTo({top:Math.max(0,b.y-60),left:Math.max(0,b.x-60),behavior:'smooth'});});
});});</script>"""
_STYLE = (
    "<style>svg.seq.paused .cs,svg.seq.paused .cs .ca{animation-play-state:paused}"
    "svg.seq.stepping g[data-step]{opacity:.1;animation:none}"
    "svg.seq.stepping g.on{opacity:1}svg.seq.stepping g.on .ca{stroke-dashoffset:0;animation:none}"
    "svg.seq g[data-step]{cursor:pointer}"
    ## A-1 (UX review): the diagram scrolls in its own box; the overview is a numbered list.
    ".flow-wrap{max-height:80vh;overflow:auto}.flow-overview{margin:6px 0 12px}"
    ".flow-overview .ov-h{font:600 12px var(--sans);color:var(--ink2);margin:0 0 4px}"
    ".flow-overview ol{margin:0;padding-left:22px}.flow-overview li{margin:2px 0}"
    ".seg-go{all:unset;cursor:pointer;color:var(--acc);font-weight:600}.seg-go:hover{text-decoration:underline}"
    ".seg-meta{margin-left:8px;font-size:12px;color:var(--ink2)}"
    ".flow-overview .kw{color:var(--acc);font-weight:700}.flow-overview li.plain{color:var(--ink2)}"
    ## W-3/W-7 (owner review 2026-11-22): the speed control and the present dialog.
    ".flow-speed{margin-left:12px;font-size:13px}.flow-speed input{vertical-align:middle;width:110px}"
    ".flow-present-body{display:grid;grid-template-columns:minmax(0,1fr) minmax(220px,340px);gap:16px}"
    ".flow-present-body .flow-stage{overflow:auto;max-height:82vh}.flow-present-body .flow-now{"
    "overflow:auto;max-height:82vh;font-size:14px}@media (max-width:760px){.flow-present-body{"
    "grid-template-columns:minmax(0,1fr)}}</style>"
)


## @brief The lines any test ran, per file.
## @param coverage {file: {line: tests}}.
## @return {file: lines}.
## @version 1
## @utility
def _executed(coverage: dict[str, dict[int, set[str]]]) -> dict[str, set[int]]:
    """@brief Union of all tests' lines. @return Lines."""
    return {
        rel: {line for line, tests in lines.items() if tests} for rel, lines in coverage.items()
    }


## @brief Write one flow's page.
## @param repo_root The repository.
## @param db The index.
## @param spec The flow declaration.
## @param source The Sphinx source directory.
## @param rules The audience rules.
## @param config The section (link template).
## @param commit The commit the site describes.
## @param req_of {(function, file): requirement ids} — the badges on each step.
## @param trace (file, OTLP document) of an imported run of this flow's test, or None.
## @return The page: its name, title and the files its steps pass through.
## v2: the step table through the shared table helper (empty columns dropped); `file` selects the
## entry and names the page.
## v3: passes the entry's file to the bodies.
## v4: returns a `FlowPage` — the map (round 3, P1c) links each component to the flows through it.
## v5: with its hops (P1c-3).
## v6: with its functions (P1d).
## v7: a requirements column — each step's callee's requirements, linked (P1e); `req_of`.
## v8: each callee links to its symbol section (P1f).
## v9: the functions section links symbol sections instead of repeating each body (P2b: the
## repeated dossiers were 37 of 86 s of clew's build).
## v10: Mermaid and PlantUML exports of the diagram, linked from the page (P3b).
## v11: a test's flow names its test node for a traced run (P4b).
## v12: an imported trace of its test is drawn over it (P4b-2).
## @param coverage {file: {line: tests}} — per-test coverage, or None when unmeasured.
## v13 (OWNER 2026-11-17, round 5): with per-test coverage a master flow grows where tests ran,
## each test's slice of it rides inline (`#test=<name>` lights it), and a not-run stub is a row.
## v14: measured_depth / max_steps from the flow, else the site (2.0.0, R5-CFG C1/C2)
## v15: block lanes and the actor (2.0.0, P5.6)
## v16: replay with values (2.0.0, P5.6)
## v17: live sync with the step table (2.0.0, P5.6)
## v18: call-site cell via _site_cell (W-8)
## v19: flow preface (W-1, W-5)
## v20: story view (X-1)
## v21: scenario bands in the diagram replace the story list (owner 2026-11-22)
## v22: UX review A (owner Q/A 2026-11-22): internal runs fold, per-flow lanes, overview first
## @version 22
## @req REQ-DDB-WIKI-050
## @req REQ-DDB-WIKI-014
## @req REQ-DDB-WIKI-041
def flow_page(
    repo_root: Path,
    db: Path,
    spec: FlowSpec,
    source: Path,
    rules: Audience,
    config: WikiConfig,
    commit: str,
    req_of: dict[tuple[str, str], list[str]] | None = None,
    trace: tuple[str, dict[str, Any]] | None = None,
    coverage: dict[str, dict[int, set[str]]] | None = None,
    blocks: dict[str, str] | None = None,
    actor: str = "",
) -> FlowPage:
    """THE STEP TABLE LINKS THE CALL SITE — the caller's file at the call's line (`site_file`),
    not the callee's file. The table drops a column no step fills.

    @brief Render one flow page.
    @return The page.
    """
    executed = _executed(coverage) if coverage is not None and spec.role != "tests" else None
    flow = derive_flow(
        db,
        repo_root,
        spec.entry,
        qualified=spec.qualified,
        depth=spec.depth,
        lanes=spec.lanes,
        stop_at=spec.stop_at,
        file=spec.file,
        executed=executed,
        ## R5-CFG C1/C2 (2.0.0): the flow's own values, else the site's; both apply only to a
        ## MEASURED flow (an unmeasured one is bounded by its depth, as before).
        max_steps=(spec.max_steps or config.measured_steps) if executed is not None else None,
        measured_depth=spec.measured_depth or config.measured_depth,
        ## P5.6 (owner, round 5): block lanes and the actor.
        blocks=blocks,
        actor=actor,
    )
    slices = slices_of(flow, coverage) if coverage is not None and spec.role != "tests" else {}
    ## UX review A-2 (owner Q/A 2026-11-22): the DIAGRAM's lanes are chosen per flow; the exports
    ## and `clew wiki flow` keep derive_flow's.
    drawn = per_flow_lanes(flow)
    name = page_name(spec)
    data = step_data(db, repo_root, flow, rules, config.link_template, commit)
    ## P5.6, REPLAY WITH VALUES: a recorded run gives each step it confirmed its values.
    if trace is not None:
        data = with_values(data, trace[1], rules)
    declared = _segments(spec, flow)
    lines = [
        f"# {spec.title or 'Flow: ' + spec.entry}",
        "",
        "```{raw} html",
        ## W-1/W-5: what the flow is for, its scenario and a worked example, above the diagram.
        _preface(spec, scenario_shown=bool(declared)),
        ## A-1 (UX review, owner Q/A 2026-11-22): the overview, then the diagram in its own box.
        _overview(drawn, declared or _top_segments(drawn, data), spec.scenario if declared else ()),
        _block(drawn, data, spec.animate, test_node(spec), declared),
        "```",
        "",
    ]
    rows = []
    for i, (step, row) in enumerate(zip(flow.steps, data, strict=True), start=1):
        site = _site_cell(step, row)
        reqs = _badges((req_of or {}).get((step.callee, step.file), ()))
        callee = f'<a href="{escape(symbol_href(step.callee, step.file))}">{code(step.callee)}</a>'
        if step.not_run:
            callee = f'<span class="nr">… {step.not_run} not run</span>'
        ## X-1: what the step does, in the table that already lists the steps.
        what = escape(row.get("brief") or "")
        rows.append([str(i), code(step.caller), callee, what, reqs, escape(row["frames"]), site])
    head = ["#", "caller", "callee", "what it does", "requirements", "frames", "call site"]
    ## P5.6, LIVE SYNC: each row names its step, so the page script can light it as the diagram plays.
    marks = [f' data-step="{i}"' for i in range(len(rows))]
    steps_table = table(head, rows, cls="steps", numeric=("#",), row_attrs=marks)
    ## A-1: the step table folds under its count (live sync still lights its rows).
    steps_table = (
        f'<details class="fold steps-fold"><summary>All {plural(len(rows), "step")}</summary>'
        f"{steps_table}</details>"
    )
    lines += ["```{raw} html", steps_table, "```", ""]
    if trace is not None:
        lines += ["```{raw} html", imported_trace(flow, *trace), "```", ""]
    if slices:
        payload = json.dumps(
            {t: list(c.exercised) for t, c in slices.items()}, separators=(",", ":")
        )
        payload = payload.replace("</", "<\\/")
        lines += [
            "```{raw} html",
            f'<script type="application/json" id="flow-slices">{payload}</script>',
            "```",
            "",
        ]
    files = {s.file for s in flow.steps} | {s.site_file for s in flow.steps if s.site_file}
    hops = tuple((s.site_file, s.file) for s in flow.steps if s.site_file and s.callee)
    functions = {(s.callee, s.file) for s in flow.steps if s.callee} | {
        (s.caller, s.site_file) for s in flow.steps if s.site_file
    }
    lines += _functions(functions)
    lines += _diagram_exports(flow, source, name)
    (source / f"{name}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    title = spec.title or "Flow: " + spec.entry
    reqs = frozenset(r for f in functions for r in (req_of or {}).get(f, ()))
    calls = tuple((s.caller, s.callee) for s in flow.steps if s.callee)
    return FlowPage(
        name,
        title,
        frozenset(files),
        hops,
        frozenset(functions),
        spec.role,
        len(flow.steps),
        reqs,
        calls,
        ## A-2: test pages draw their slices on the same lanes as this page.
        drawn,
        slices,
        spec.intent,
    )


## @brief An imported trace drawn over the flow: per-step CSS and a panel saying what it found.
## @param flow The flow.
## @param rel The trace's file.
## @param otlp The trace.
## @return HTML.
## v2: discovered calls fold (UX review A-1)
## @version 2
## @req REQ-DDB-WIKI-036
def imported_trace(flow: Flow, rel: str, otlp: dict[str, Any]) -> str:
    """STATIC, so a published site carries it: each predicted step is styled CONFIRMED or dimmed
    as NOT EXECUTED by a CSS rule on its `data-step`; discovered calls and the failure are listed.

    @brief Imported trace overlay.
    @return HTML.
    """
    from .tracerun import failure_of, overlay

    result = overlay([(s.caller, s.callee) for s in flow.steps], otlp)
    rules = "".join(
        f'svg.seq g[data-step="{i}"]{{opacity:.25}}'
        if state != "confirmed"
        else f'svg.seq g[data-step="{i}"] line{{stroke:#3D6B2E;stroke-width:3}}'
        for i, state in enumerate(result["steps"])
    )
    confirmed = result["steps"].count("confirmed")
    lines = [
        f"Imported trace <code>{escape(rel)}</code>: {confirmed} of {len(result['steps'])} "
        "predicted steps confirmed; the rest are dimmed."
    ]
    found = [
        f"<li><code>{escape(a)}</code> → <code>{escape(b)}</code></li>"
        for a, b in result["discovered"]
    ]
    failed = failure_of(otlp)
    if failed:
        where = f" at line {escape(failed['line'])}" if failed["line"] else ""
        lines.append(
            f'<span class="bad">Failed in <code>{escape(failed["span"])}</code>{where}: '
            f"{escape(failed['message'])}</span>"
        )
    body = "".join(f"<p>{line}</p>" for line in lines)
    ## A-1 (UX review, owner Q/A 2026-11-22): what the run discovered folds under its count
    ## (5,777 px on clew's dossier flow); the summary and any failure stay in view.
    if found:
        body += (
            f'<details class="fold"><summary>{plural(len(found), "discovered call")} not in the '
            f"flow</summary><ul>{''.join(found)}</ul></details>"
        )
    return f'<style>{rules}</style><div class="trace-panel imported">{body}</div>'


## @brief A test flow's pytest node id, or "" for any other flow.
## @param spec The flow.
## @return `file::name`, or "".
## @version 1
## @req REQ-DDB-WIKI-035
def test_node(spec: FlowSpec) -> str:
    """@brief Node id. @return Text."""
    return f"{spec.file}::{spec.entry}" if spec.role == "tests" and spec.file else ""


## @brief A flow's page name: the entry, and its file when the flow selects one.
## @param spec The flow.
## @return The page name.
## @version 1
## @utility
def page_name(spec: FlowSpec) -> str:
    """@brief Name a page. @return Name."""
    import re

    suffix = "-" + re.sub(r"[^A-Za-z0-9]+", "-", spec.file).strip("-") if spec.file else ""
    return f"flow-{spec.entry}{suffix}"


## @brief The data each step carries, for its dialog.
## @param db The index.
## @param repo_root The repository.
## @param flow The flow.
## @param rules The audience rules (no call text when bodies are excluded).
## @param template The source link template.
## @param commit The commit.
## @return One mapping per step.
## v2: links from the template directly (`source_url`).
## @version 2
## @req REQ-DDB-WIKI-014
def step_data(
    db: Path, repo_root: Path, flow: Flow, rules: Audience, template: str, commit: str
) -> list[dict[str, Any]]:
    """@brief Gather step data. @return Rows."""
    signatures = _signatures(db, flow)
    out = []
    for step in flow.steps:
        site = step.site_file or step.file
        link = source_url(template, commit, site, step.line)
        sig, brief = signatures.get((step.callee, step.callee_qualified), ("", ""))
        out.append(
            {
                "caller": step.caller,
                "callee": step.callee,
                "callee_qualified": step.callee_qualified,
                "call": "" if rules.exclude_bodies else _call_text(repo_root, site, step.line),
                "signature": sig,
                "brief": brief,
                "frames": ", ".join(f"{f.kind} (line {f.line})" for f in step.frames),
                "ambiguous": ", ".join(step.ambiguous),
                "site": f"{site}:{step.line}",
                "link": link,
            }
        )
    return out


## @brief Step data with each confirmed step's recorded values (replay with values, P5.6).
## @param data The step data, one row per step.
## @param otlp The recorded run.
## @param rules The audience: values are withheld with the bodies.
## @return New rows; a step the run never made carries no values.
## @version 1
## @req REQ-DDB-WIKI-049
def with_values(
    data: list[dict[str, Any]], otlp: dict[str, Any], rules: Audience
) -> list[dict[str, Any]]:
    """RUNTIME DATA IS WITHHELD WITH THE BODIES: an audience that may not see source does not see
    the values it computed either.

    @brief Merge values.
    @return Rows.
    """
    if rules.exclude_bodies:
        return data
    from .tracerun import overlay

    values = overlay([(r["caller"], r["callee"]) for r in data], otlp)["values"]
    return [
        {**row, "called_with": v["args"], "returned": v["return"]} if v else row
        for row, v in zip(data, values, strict=True)
    ]


## @brief The diagram, controls, data and script, as one raw HTML block.
## @param flow The flow.
## @param data The step data.
## @param animate Whether the diagram plays.
## @param node The test's node id when the flow is a test's, else "".
## @return HTML.
## v2: the step opens the page's shared modal (round 3, P1b) — deep-linked as `#m=step-N` — not
## a dialog of its own; the diagram pans and zooms.
## v3: a test's flow names its test (`data-test-node`), so the hub can run it traced (P4b).
## v4: controls and present dialog (W-3, W-7)
## v5: scenario bands in the diagram replace the story list (owner 2026-11-22)
## @version 5
## @utility
def _block(
    flow: Flow,
    data: list[dict[str, Any]],
    animate: bool,
    node: str = "",
    segments: dict | None = None,
) -> str:
    """`<` IS ESCAPED IN THE JSON so no repository text can close the script element.

    @brief Assemble the block.
    @return HTML.
    """
    ## X-1: each step carries the scenario line it builds, for present mode's step panel.
    current = ""
    for i, row in enumerate(data):
        current = (segments or {}).get(i, current)
        row["seg"] = current
    blob = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    attr = f' data-test-node="{escape(node)}"' if node else ""

    return (
        f'<div class="flow-block"{attr}>{_STYLE}<div class="flow-home">{_controls()}'
        f'<div class="flow-wrap" data-pz>{flow_svg(flow, animate=animate, segments=segments)}</div></div>'
        f'<script type="application/json" class="flow-data">{blob}</script>'
        f"{_SCRIPT}</div>"
    )


## @brief The player's controls: play, pause, step, present, and the reading-speed slider.
## @return HTML.
## @version 1
## @utility
def _controls() -> str:
    """W-3: the speed scales the reading-paced dwell, ×0.25 (slowest) to ×2.

    @brief Controls.
    @return HTML.
    """
    buttons = "".join(
        f'<button type="button" data-flow-control="{c}">{c}</button>'
        for c in ("play", "pause", "step", "present")
    )
    speed = (
        '<label class="flow-speed">speed <input type="range" min="0.25" max="2" step="0.25" '
        'value="1" data-flow-speed aria-label="playback speed"> <output data-flow-speed-label>'
        "\u00d71</output></label>"
    )
    return f'<div class="flow-controls">{buttons}{speed}</div>'


## @brief The callee signatures and briefs of a flow's steps.
## @param db The index.
## @param flow The flow.
## @return {(callee, qualified): (signature, brief)}.
## v2: the brief as plain text — doxygen stores it as XML (`<para>…</para>`), which the step modal
## printed verbatim (round 3, P1b screenshots).
## @version 2
## @utility
def _signatures(db: Path, flow: Flow) -> dict[tuple[str, str], tuple[str, str]]:
    """@brief Read signatures. @return Map."""
    from ..query._common import connect, identity_rowids

    out: dict[tuple[str, str], tuple[str, str]] = {}
    with connect(db) as conn:
        for step in flow.steps:
            key = (step.callee, step.callee_qualified)
            if key in out or not step.callee_qualified:
                continue
            rowids = identity_rowids(conn, step.callee, step.callee_qualified)
            if not rowids:
                continue
            row = conn.execute(
                "SELECT definition, argsstring, briefdescription FROM memberdef WHERE rowid = ?",
                (min(rowids),),
            ).fetchone()
            if row:
                brief = " ".join(re.sub(r"<[^>]+>", " ", str(row[2] or "")).split())
                out[key] = (f"{row[0] or ''}{row[1] or ''}".strip(), brief)
    return out


## @brief A flow's declared intent, scenario and worked example, in reading order.
## @param spec The flow.
## @return HTML, or "" when it declares none.
## v2: scenario drawn once, as the overview (UX review A-1)
## @version 2
## @utility
def _preface(spec: Any, scenario_shown: bool = False) -> str:
    """W-1/W-5 (owner review 2026-11-22): the abstract first — what the flow is for — then its
    Gherkin scenario, always shown, then the example. Declared text only; escaped.

    @brief Flow preface.
    @return HTML.
    """
    parts = []
    if spec.intent:
        parts.append(f'<p class="intent">{escape(spec.intent)}</p>')
    ## A-1: an anchored scenario is drawn once, as the overview (`scenario_shown`).
    if spec.scenario and not scenario_shown:
        parts.append(gherkin(spec.scenario))
    if spec.example:
        given, got = spec.example
        parts.append(
            '<div class="example"><p class="ex-h">Worked example</p>'
            f'<pre class="ex-in">{escape(given)}</pre><pre class="ex-out">{escape(got)}</pre></div>'
        )
    return f'<div class="flow-preface">{"".join(parts)}</div>' if parts else ""


## @brief Where each anchored scenario line begins in a flow: step index → the line.
## @param spec The flow (its scenario and anchors).
## @param flow The derived flow.
## @return {step index: scenario line}.
## @version 1
## @utility
def _segments(spec: Any, flow: Any) -> dict[int, str]:
    """X-1 (owner 2026-11-22): an anchored line begins at the first step, searching forward from
    the previous anchor, whose callee its `at` names; an anchor the flow never reaches draws nothing.
    The segments are drawn IN the diagram as bands — the story list that duplicated the step table
    is gone (owner: "a no").

    @brief Segment starts.
    @return Map.
    """
    out: dict[int, str] = {}
    cursor = 0
    for line, at in zip(spec.scenario or (), spec.scenario_at or ()):
        hit = next(
            (i for i in range(cursor, len(flow.steps)) if at and flow.steps[i].callee == at), None
        )
        if hit is not None:
            out[hit] = line
            cursor = hit
    return out


## @brief The overview's segments when none is declared: the entry's top-level calls.
## @param flow The drawn flow.
## @param data Its step rows (`brief`).
## @return {step index: "callee — brief"}.
## @version 1
## @utility
def _top_segments(flow: Any, data: list[dict[str, Any]]) -> dict[int, str]:
    """A-1 (UX review, owner Q/A 2026-11-22). Measured on clew's flows: 1-11 top-level calls each.
    One top-level call says nothing, so the overview goes one level down until there are two.

    @brief Derived segments.
    @return Map.
    """
    depths = sorted({s.depth for s in flow.steps})
    heads: list[int] = []
    for level in depths:
        heads = [i for i, s in enumerate(flow.steps) if s.depth == level]
        if len(heads) > 1:
            break
    out = {}
    for i in heads:
        step, brief = flow.steps[i], (data[i].get("brief") or "") if i < len(data) else ""
        name = step.callee or _message_of(step)
        out[i] = f"{name} — {brief}" if brief else name
    return out


## @brief A not-run stub's words.
## @param step The stub.
## @return Text.
## @version 1
## @utility
def _message_of(step: Any) -> str:
    """@brief Stub label. @return Text."""
    return f"… {plural(step.not_run, 'call')} not run"


## @brief The overview: one row per segment, its steps and lanes, each bringing its part into view.
## @param flow The drawn flow.
## @param segments {first step index: what it does}.
## @param scenario The declared scenario, when its lines are the segments: every line is listed,
## the anchored ones as segments.
## @return HTML ("" for a flow with fewer than two steps).
## @version 1
## @utility
def _overview(flow: Any, segments: dict[int, str], scenario: tuple[str, ...] = ()) -> str:
    """A-1 (UX review, owner Q/A 2026-11-22): summary first. A row's `data-goto` is its first
    step; the page script scrolls the diagram's box to it and selects it. A declared scenario is
    drawn ONCE, here (found in the browser: the overview repeated the Gherkin block above it).

    @brief Overview.
    @return HTML.
    """
    if len(flow.steps) < 2 or not segments:
        return ""
    starts = sorted(segments)
    ends = {
        i: (starts[n + 1] if n + 1 < len(starts) else len(flow.steps)) - 1
        for n, i in enumerate(starts)
    }
    at = {text: i for i, text in segments.items()}
    lines = scenario or tuple(segments[i] for i in starts)
    rows = [
        _segment_row(flow, at[line], ends[at[line]], line, bool(scenario))
        if line in at
        else f'<li class="plain">{_keyword(line)}</li>'
        for line in lines
        if str(line).strip()
    ]
    return (
        '<div class="flow-overview"><p class="ov-h">Overview · '
        f"{plural(len(flow.steps), 'step')}, {plural(len(flow.lanes), 'lane')}</p>"
        f'<ol class="segments">{"".join(rows)}</ol></div>'
    )


## @brief One overview row: its words, then its step span and the lanes it touches.
## @param flow The drawn flow.
## @param i Its first step.
## @param end Its last step.
## @param text Its words.
## @param keyword Mark the Gherkin keyword.
## @return HTML.
## @version 1
## @utility
def _segment_row(flow: Any, i: int, end: int, text: str, keyword: bool) -> str:
    """@brief Segment row. @return HTML."""
    lanes = list(
        dict.fromkeys(x for s in flow.steps[i : end + 1] for x in (s.from_lane, s.to_lane))
    )
    shown = ", ".join(escape(x) for x in lanes[:3]) + (
        f" +{len(lanes) - 3}" if len(lanes) > 3 else ""
    )
    span = f"step {i + 1}" if end == i else f"steps {i + 1}–{end + 1}"
    words = _keyword(text) if keyword else escape(text)
    return (
        f'<li data-goto="{i}"><button type="button" class="seg-go">{words}</button>'
        f'<span class="seg-meta">{span} · {shown}</span></li>'
    )


## @brief A scenario line with its keyword marked.
## @param line The line.
## @return HTML.
## @version 1
## @utility
def _keyword(line: str) -> str:
    """@brief Keyword. @return HTML."""
    kw, _sp, rest = str(line).partition(" ")
    return f'<span class="kw">{escape(kw)}</span> {escape(rest)}'


## @brief A step row's call-site cell: a link to the line, plain text, or nothing for a stub.
## @param step The step.
## @param row Its row data (`link`, `site`).
## @return HTML.
## @version 1
## @utility
def _site_cell(step: Any, row: dict[str, Any]) -> str:
    """W-8 (owner review 2026-11-22): a not-run stub stands for several calls, so it names no line
    (it showed `clew/cli.py:0`).

    @brief Call-site cell.
    @return HTML.
    """
    if step.not_run:
        return ""
    if row["link"]:
        return f'<a href="{escape(row["link"])}">{escape(row["site"])}</a>'
    return code(row["site"])


## @brief The call expression at a call site, read across lines until its parentheses close.
## @param repo_root The repository.
## @param rel The caller's file.
## @param line The call's line.
## @return The text, or "" when the file cannot be read.
## @version 1
## @utility
def _call_text(repo_root: Path, rel: str, line: int) -> str:
    """@brief Read the call. @return Text."""
    try:
        lines = (Path(repo_root) / rel).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    out: list[str] = []
    depth = 0
    for text in lines[max(0, line - 1) : line - 1 + _CALL_LINES]:
        out.append(text.rstrip())
        depth += text.count("(") - text.count(")")
        if depth <= 0:
            break
    return "\n".join(out).strip()


## @brief Write the flow as Mermaid, PlantUML and DOT into the site's exports, and link them.
## @param flow The flow.
## @param source The Sphinx source directory (its `_extra` is copied to the site root).
## @param name The page name.
## @return Markdown lines.
## v2 (2.0.0, P5.7): Graphviz DOT (S7).
## @version 2
## @utility
def _diagram_exports(flow: Flow, source: Path, name: str) -> list[str]:
    """@brief Diagram exports. @return Lines."""
    from .exports import flow_dot, flow_mermaid, flow_plantuml

    out = Path(source) / "_extra" / "exports" / "flows"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{name}.mmd").write_text(flow_mermaid(flow), encoding="utf-8")
    (out / f"{name}.puml").write_text(flow_plantuml(flow), encoding="utf-8")
    ## S7 (2.0.0, P5.7): Graphviz DOT beside them.
    (out / f"{name}.dot").write_text(flow_dot(flow), encoding="utf-8")
    links = (
        f'<p class="exports">This diagram as <a href="exports/flows/{name}.mmd">Mermaid</a> · '
        f'<a href="exports/flows/{name}.puml">PlantUML</a> · '
        f'<a href="exports/flows/{name}.dot">Graphviz DOT</a></p>'
    )
    return ["```{raw} html", links, "```", ""]


## @brief The functions a flow reaches, each linked to its symbol section.
## @param functions (function, file) pairs.
## @return Markdown lines.
## v2: UX review A (owner Q/A 2026-11-22): internal runs fold, per-flow lanes, overview first
## @version 2
## @utility
def _functions(functions: set[tuple[str, str]]) -> list[str]:
    """ONE BODY PER FUNCTION, on its symbol section: the flow page links there rather than
    repeating it — the repeated dossier per function was 37 of 86 s of clew's own build
    (cProfile, 333 export_dossier calls at ~110 ms).

    @brief Function links.
    @return Lines.
    """
    items = "".join(
        f'<li><a href="{escape(symbol_href(n, f))}">{code(n)}</a> '
        f'<span class="ver">{escape(f)}</span></li>'
        for n, f in sorted(functions, key=lambda k: (k[1], k[0]))
    )
    ## A-1 (UX review, owner Q/A 2026-11-22): folded under its count.
    fold = (
        f'<details class="fold"><summary>{plural(len(functions), "function")}</summary>'
        f'<ul class="modal-list">{items}</ul></details>'
    )
    return ["## Functions", "", "```{raw} html", fold, "```", ""]


## @brief Requirement badges, each linked to its row on the requirements page.
## @param reqs Requirement ids.
## @return HTML ("" for none).
## v2: fold many; link the page (UX review D-10)
## @version 2
## @utility
def _badges(reqs: Any) -> str:
    """UX review D-10 (owner Q/A 2026-11-22): three or fewer inline; more fold under their count,
    and each pill opens the requirement's own page.

    @brief Badges.
    @return HTML.
    """
    from .reqmodal import page_of

    pills = [
        f'<a class="req-badge" href="{escape(page_of(r))}.html">{escape(r)}</a>'
        for r in sorted(set(reqs))
    ]
    if len(pills) <= 3:
        return " ".join(pills)
    return f'<details class="fold"><summary>{len(pills)} requirements</summary>{" ".join(pills)}</details>'


## @brief The Flows page: flows grouped by role, tooling folded away.
## @param source The Sphinx source directory.
## @param pages The flow pages.
## @param unmatched (file, root span) of imported traces that matched no flow.
## @param not_drawn (entry, file, reason) of discovered flows that could not be derived.
## @return The page name, or "" when there is no flow.
## v2: a Tests role and the cap's disclosure (P2b).
## v3: imported traces that matched no flow are listed (P4b-2).
## v4 (round 4): discovered flows that could not be drawn are listed with the reason.
## v5 (round 5): no cap to disclose — tests are slices of the master flows, not flows of their own.
## @version 5
## @req REQ-DDB-WIKI-023
def flows_index(
    source: Path,
    pages: list[FlowPage],
    unmatched: tuple = (),
    not_drawn: tuple = (),
) -> str:
    """OWNER 2026-11-15: the product's flows first — console scripts, declared roots, mains
    outside tooling — then thread entries, then tooling (scripts, harnesses) folded. A role
    with no flow has no section.

    @brief Write flows.md.
    @return Page name.
    """
    if not pages and not not_drawn:
        return ""
    lines = ["# Flows", "", _FLOWS_LEAD, ""]
    for role, heading, lead in _ROLES:
        members = sorted((p for p in pages if (p.role or "product") == role), key=lambda p: p.title)
        if members:
            lines += [
                f"## {heading}",
                "",
                lead,
                "",
                "```{raw} html",
                _role_block(role, members),
                "```",
                "",
            ]
    if unmatched:
        lines += ["Imported traces whose test has no flow here:", ""]
        lines += [f"- `{rel}` — root `{root}`" for rel, root in unmatched]
        lines.append("")
    if not_drawn:
        lines += ["Entry points found but not drawn:", ""]
        lines += [f"- `{e}` (`{f}`) — not drawn: {r}" for e, f, r in not_drawn]
        lines.append("")
    names = [p.name for p in pages]
    lines += ["```{toctree}", ":hidden:", ":maxdepth: 1", "", *names, "```", ""]
    (Path(source) / "flows.md").write_text("\n".join(lines), encoding="utf-8")
    return "flows"


## @brief A flow's title cell: its readable name, the entry under it in monospace, its intent.
## @param p The flow page.
## @return HTML.
## @version 1
## @utility
def _title_cell(p: FlowPage) -> str:
    """UX review E-11 (owner Q/A 2026-11-22): ONE PATTERN. A discovered flow's stored title is
    `<name> — <entry> (<file>)` (build._actor_of reads that shape, so it stays); the cell shows the
    name as the title and the entry and file under it, small and monospace.

    @brief Title cell.
    @return HTML.
    """
    name, _sep, where = p.title.partition(" — ")
    entry = f'<br><span class="entry">{md_title(where)}</span>' if where else ""
    intent = f'<br><span class="intent">{escape(p.intent)}</span>' if p.intent else ""
    return f'<a href="{escape(p.name)}.html">{md_title(name)}</a>{entry}{intent}'


## @brief One role's flows as a table, folded for tooling.
## @param role The role.
## @param members Its flow pages.
## @return HTML.
## v2: the tests role folds too (P2b).
## v3: intent under the title (W-1)
## v4: one title pattern; untraced muted (UX review E-11)
## @version 4
## @utility
def _role_block(role: str, members: list[FlowPage]) -> str:
    """@brief Role block. @return HTML."""
    rows = [
        [
            _title_cell(p),
            str(p.steps) if p.steps else '<span class="untraced">not traced</span>',
            _badges(p.requirements),
        ]
        for p in members
    ]
    ## E-11: a flow that draws nothing is muted, not listed as a peer.
    attrs = ["" if p.steps else ' class="untraced"' for p in members]
    body = table(
        ["flow", "steps", "requirements"], rows, numeric=("steps",), keep=("flow",), row_attrs=attrs
    )
    if role in _FOLDED:
        ## E-22: "1 test flow", "3 tooling flows".
        adjective = {"tests": "test", "threads": "thread"}.get(role, role)
        body = (
            f"<details><summary>{plural(len(members), 'flow', adjective)}</summary>{body}</details>"
        )
    return f'<section class="flow-role" data-role="{role}">{body}</section>'


_FLOWS_LEAD = (
    "Sequence diagrams derived from the index: every step is a call the index resolved, in the "
    "caller's source order. Click a step for the data it carries."
)
## (role, heading, lead), in page order.
_ROLES = (
    (
        "product",
        "Product",
        "What the shipped code does: console scripts, declared roots, programs.",
    ),
    ("threads", "Threads", "Each thread's entry function and what it reaches."),
    ("tooling", "Tooling", "Scripts and harnesses around the product."),
    ("tests", "Tests", "Each directly linked test as a flow: what it calls, in order."),
)
## Roles whose section is folded away.
_FOLDED = ("tooling", "tests")
