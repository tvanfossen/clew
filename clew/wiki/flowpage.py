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
from .htmltable import code, source_url, table
from .svg import flow_svg


## @brief A written flow page: its name, title, the files its steps pass through, and its hops.
## v2: `hops`, for the map's flow traces (round 3, P1c-3).
## @version 2
class FlowPage(NamedTuple):
    """@brief A flow page. @version 2"""

    name: str
    title: str
    files: frozenset[str]
    ## (caller's file, callee's file) per step, in call order.
    hops: tuple[tuple[str, str], ...] = ()


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
 function build(n){var i=+n,s=data[i];if(!s)return null;groups.forEach(function(g){g.classList.remove('sel');});
  groups[i].classList.add('sel');var f=document.createDocumentFragment(),dl=document.createElement('dl');
  dl.className='kv';row(dl,'call',s.call,true);row(dl,'callee',s.callee_qualified);
  row(dl,'receives',s.signature,true);row(dl,'brief',s.brief);row(dl,'frames',s.frames);
  row(dl,'ambiguous',s.ambiguous);row(dl,'at',s.site);f.appendChild(dl);
  if(s.link){var a=document.createElement('a');a.href=s.link;a.textContent='open the call site';f.appendChild(a);}
  return {title:(i+1)+'. '+s.caller+' \\u2192 '+s.callee,node:f};}
 if(window.clewModal)window.clewModal.register('step-',build);
 groups.forEach(function(g){g.addEventListener('click',function(){
  window.clewModal&&window.clewModal.open('step-'+g.getAttribute('data-step'),g);});});
 function control(name,fn){var b=block.querySelector('[data-flow-control='+name+']');if(b)b.addEventListener('click',fn);}
 control('play',function(){svg.classList.remove('stepping','paused');groups.forEach(function(g){
  g.classList.remove('on');var c=g.getAttribute('class');g.setAttribute('class','');void g.getBBox();g.setAttribute('class',c);});cursor=0;});
 control('pause',function(){svg.classList.toggle('paused');});
 control('step',function(){if(!svg.classList.contains('stepping')){svg.classList.add('stepping');cursor=0;
  groups.forEach(function(g){g.classList.remove('on');});}
  if(cursor>=groups.length){cursor=0;groups.forEach(function(g){g.classList.remove('on');});}
  groups[cursor].classList.add('on');cursor++;});
});});</script>"""
_STYLE = (
    "<style>svg.seq.paused .cs,svg.seq.paused .cs .ca{animation-play-state:paused}"
    "svg.seq.stepping g[data-step]{opacity:.1;animation:none}"
    "svg.seq.stepping g.on{opacity:1}svg.seq.stepping g.on .ca{stroke-dashoffset:0;animation:none}"
    "svg.seq g[data-step]{cursor:pointer}</style>"
)


## @brief Write one flow's page.
## @param repo_root The repository.
## @param db The index.
## @param spec The flow declaration.
## @param source The Sphinx source directory.
## @param rules The audience rules.
## @param config The section (link template).
## @param commit The commit the site describes.
## @return The page: its name, title and the files its steps pass through.
## v2: the step table through the shared table helper (empty columns dropped); `file` selects the
## entry and names the page.
## v3: passes the entry's file to the bodies.
## v4: returns a `FlowPage` — the map (round 3, P1c) links each component to the flows through it.
## v5: with its hops (P1c-3).
## @version 5
## @req REQ-DDB-WIKI-014
def flow_page(
    repo_root: Path,
    db: Path,
    spec: FlowSpec,
    source: Path,
    rules: Audience,
    config: WikiConfig,
    commit: str,
) -> FlowPage:
    """THE STEP TABLE LINKS THE CALL SITE — the caller's file at the call's line (`site_file`),
    not the callee's file. The table drops a column no step fills.

    @brief Render one flow page.
    @return The page.
    """
    flow = derive_flow(
        db,
        repo_root,
        spec.entry,
        qualified=spec.qualified,
        depth=spec.depth,
        lanes=spec.lanes,
        stop_at=spec.stop_at,
        file=spec.file,
    )
    name = page_name(spec)
    data = step_data(db, repo_root, flow, rules, config.link_template, commit)
    lines = [
        f"# {spec.title or 'Flow: ' + spec.entry}",
        "",
        "```{raw} html",
        _block(flow, data, spec.animate),
        "```",
        "",
    ]
    rows = []
    for i, (step, row) in enumerate(zip(flow.steps, data, strict=True), start=1):
        site = (
            f'<a href="{escape(row["link"])}">{escape(row["site"])}</a>'
            if row["link"]
            else code(row["site"])
        )
        rows.append([str(i), code(step.caller), code(step.callee), escape(row["frames"]), site])
    head = ["#", "caller", "callee", "frames", "call site"]
    lines += ["```{raw} html", table(head, rows, cls="steps", numeric=("#",)), "```", ""]
    if not rules.exclude_bodies:
        lines += _bodies(db, repo_root, flow, spec.file)
    (source / f"{name}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    files = {s.file for s in flow.steps} | {s.site_file for s in flow.steps if s.site_file}
    hops = tuple((s.site_file, s.file) for s in flow.steps if s.site_file)
    return FlowPage(name, spec.title or "Flow: " + spec.entry, frozenset(files), hops)


## @brief A flow's page name: the entry, and its file when the flow selects one.
## @param spec The flow.
## @return The page name.
## @version 1
## @dg_internal
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


## @brief The diagram, controls, data and script, as one raw HTML block.
## @param flow The flow.
## @param data The step data.
## @param animate Whether the diagram plays.
## @return HTML.
## v2: the step opens the page's shared modal (round 3, P1b) — deep-linked as `#m=step-N` — not
## a dialog of its own; the diagram pans and zooms.
## @version 2
## @dg_internal
def _block(flow: Flow, data: list[dict[str, Any]], animate: bool) -> str:
    """`<` IS ESCAPED IN THE JSON so no repository text can close the script element.

    @brief Assemble the block.
    @return HTML.
    """
    blob = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    buttons = "".join(
        f'<button type="button" data-flow-control="{c}">{c}</button>'
        for c in ("play", "pause", "step")
    )
    return (
        f'<div class="flow-block">{_STYLE}<div class="flow-controls">{buttons}</div>'
        f'<div class="flow-wrap" data-pz>{flow_svg(flow, animate=animate)}</div>'
        f'<script type="application/json" class="flow-data">{blob}</script>'
        f"{_SCRIPT}</div>"
    )


## @brief The callee signatures and briefs of a flow's steps.
## @param db The index.
## @param flow The flow.
## @return {(callee, qualified): (signature, brief)}.
## v2: the brief as plain text — doxygen stores it as XML (`<para>…</para>`), which the step modal
## printed verbatim (round 3, P1b screenshots).
## @version 2
## @dg_internal
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


## @brief The call expression at a call site, read across lines until its parentheses close.
## @param repo_root The repository.
## @param rel The caller's file.
## @param line The call's line.
## @return The text, or "" when the file cannot be read.
## @version 1
## @dg_internal
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


## @brief The entry's own body: read from its file's span when the flow selected it by file.
## @param db The index.
## @param repo_root The repository.
## @param flow The flow.
## @param file The entry's file, or None.
## @return Markdown lines.
## @version 1
## @dg_internal
def _entry_body(db: Path, repo_root: Path, flow: Flow, file: str | None) -> list[str]:
    """A NAME SEVERAL FILES SHARE (`main`) cannot be looked up by name: the entry's span is read
    from its own file, so the page shows the function the diagram is of.

    @brief Entry body.
    @return Lines.
    """
    if not file:
        return _dossier_body(db, repo_root, flow.entry, flow.entry_qualified)
    from ..query._common import connect

    with connect(db) as conn:
        row = conn.execute(
            "SELECT m.bodystart, m.bodyend FROM memberdef m JOIN path p ON p.rowid = m.file_id "
            "WHERE m.kind = 'function' AND m.name = ? AND p.name = ? AND m.bodystart > 0",
            (flow.entry, file),
        ).fetchone()
    try:
        text = (Path(repo_root) / file).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    if not row:
        return []
    return [
        f"### `{flow.entry}`",
        "",
        f"`{file}`",
        "",
        "```",
        *text[row[0] - 1 : row[1]],
        "```",
        "",
    ]


## @brief One function's body section, as dossier excerpts it.
## @param db The index.
## @param repo_root The repository.
## @param name The function.
## @param qual Its qualified name.
## @return Markdown lines; [] when the index has no body for it.
## @version 1
## @dg_internal
def _dossier_body(db: Path, repo_root: Path, name: str, qual: str) -> list[str]:
    """@brief Body section. @return Lines."""
    from ..query import export_dossier

    payload = export_dossier(db, name, qualified=qual or None, repo_root=repo_root)
    body = payload.get("body") or {}
    if not body.get("lines"):
        return []
    return [
        f"### `{qual or name}`",
        "",
        f"`{body.get('file', '')}`",
        "",
        "```",
        *body["lines"],
        "```",
        "",
    ]


## @brief The source bodies of every function a flow reaches, as code blocks.
## @param db The index.
## @param repo_root The repository.
## @param flow The flow.
## @return Markdown lines.
## @param file The entry's file, when the flow selected it by file.
## v2: the entry's body read from its own file when selected by file.
## @version 2
## @dg_internal
def _bodies(db: Path, repo_root: Path, flow: Flow, file: str | None = None) -> list[str]:
    """THE INDEX'S OWN BODY EXCERPT (export_dossier), so a page shows what `dossier` shows.

    @brief Body sections.
    @return Lines.
    """
    seen = [(s.callee, s.callee_qualified) for s in flow.steps if s.callee_qualified]
    out: list[str] = ["", "## Functions", ""]
    out += _entry_body(db, repo_root, flow, file)
    for name, qual in dict.fromkeys(seen):
        out += _dossier_body(db, repo_root, name, qual)
    return out
