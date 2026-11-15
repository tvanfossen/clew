# SPDX-License-Identifier: MIT
"""One flow's page: the diagram, its interactive layer, the step table and the bodies reached.

1.4.0 W5, and W18 (owner 2026-11-15: "interactive", "show data carried in modal"). The diagram
is `svg.flow_svg`; around it the page adds, inline and same-origin:

  * PLAY / PAUSE / STEP controls — replay the animation, freeze it, or reveal one step at a time;
  * a DIALOG per step, opened by clicking it, holding the DATA THE STEP CARRIES: the call
    expression as written at the call site (the arguments passed), the callee's signature and
    brief (what it receives), the frames around the call, and a link to the call site.

The step data is a JSON block the script reads with `textContent` and writes with `textContent` —
no repository text is ever parsed as HTML. An audience that EXCLUDES BODIES gets no call text: the
call expression is source code, so it is redacted like a body (signatures stay — they are the
interface).

@brief Render a flow page.
@version 1
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import Audience, FlowSpec, WikiConfig
from .flow import Flow, derive_flow
from .svg import flow_svg

## The most lines a call expression is read across.
_CALL_LINES = 6
## The page's interactive layer: no dependency, nothing remote.
_SCRIPT = """<script>(function(){
document.querySelectorAll('.flow-block').forEach(function(block){
 var data=JSON.parse(block.querySelector('script.flow-data').textContent);
 var svg=block.querySelector('svg.seq'),dlg=block.querySelector('dialog.flow-step');
 var groups=Array.prototype.slice.call(svg.querySelectorAll('g[data-step]')),cursor=0;
 function row(dl,k,v,code){if(!v)return;var dt=document.createElement('dt'),dd=document.createElement('dd');
  dt.textContent=k;var el=code?document.createElement('pre'):document.createElement('span');el.textContent=v;
  dd.appendChild(el);dl.appendChild(dt);dl.appendChild(dd);}
 function show(i){var s=data[i];dlg.querySelector('h3').textContent=(i+1)+'. '+s.caller+' \\u2192 '+s.callee;
  var dl=dlg.querySelector('dl');dl.textContent='';row(dl,'call',s.call,true);row(dl,'callee',s.callee_qualified);
  row(dl,'receives',s.signature,true);row(dl,'brief',s.brief);row(dl,'frames',s.frames);
  row(dl,'ambiguous',s.ambiguous);row(dl,'at',s.site);var a=dlg.querySelector('a.site');
  if(s.link){a.href=s.link;a.hidden=false;}else{a.hidden=true;}dlg.showModal();}
 groups.forEach(function(g){g.addEventListener('click',function(){show(+g.getAttribute('data-step'));});});
 dlg.querySelector('button').addEventListener('click',function(){dlg.close();});
 function control(name,fn){var b=block.querySelector('[data-flow-control='+name+']');if(b)b.addEventListener('click',fn);}
 control('play',function(){svg.classList.remove('stepping','paused');groups.forEach(function(g){
  g.classList.remove('on');var c=g.getAttribute('class');g.setAttribute('class','');void g.getBBox();g.setAttribute('class',c);});cursor=0;});
 control('pause',function(){svg.classList.toggle('paused');});
 control('step',function(){if(!svg.classList.contains('stepping')){svg.classList.add('stepping');cursor=0;
  groups.forEach(function(g){g.classList.remove('on');});}
  if(cursor>=groups.length){cursor=0;groups.forEach(function(g){g.classList.remove('on');});}
  groups[cursor].classList.add('on');cursor++;});
});})();</script>"""
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
## @return The page name.
## @version 1
## @req REQ-DDB-WIKI-014
def flow_page(
    repo_root: Path,
    db: Path,
    spec: FlowSpec,
    source: Path,
    rules: Audience,
    config: WikiConfig,
    commit: str,
) -> str:
    """THE STEP TABLE LINKS THE CALL SITE — the caller's file at the call's line (`site_file`),
    not the callee's file.

    @brief Render one flow page.
    @return Page name.
    """
    from .build import _link

    flow = derive_flow(
        db,
        repo_root,
        spec.entry,
        qualified=spec.qualified,
        depth=spec.depth,
        lanes=spec.lanes,
        stop_at=spec.stop_at,
    )
    name = f"flow-{spec.entry}"
    data = step_data(db, repo_root, flow, rules, config.link_template, commit)
    lines = [
        f"# {spec.title or 'Flow: ' + spec.entry}",
        "",
        "```{raw} html",
        _block(flow, data, spec.animate),
        "```",
        "",
        "| # | caller | callee | frames | call site |",
        "|---|---|---|---|---|",
    ]
    for i, step in enumerate(flow.steps, start=1):
        frames = " ".join(f.kind for f in step.frames)
        where = _link(config.link_template, commit, step.site_file or step.file, step.line)
        lines.append(f"| {i} | `{step.caller}` | `{step.callee}` | {frames} | {where} |")
    if not rules.exclude_bodies:
        lines += _bodies(db, repo_root, flow)
    (source / f"{name}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return name


## @brief The data each step carries, for its dialog.
## @param db The index.
## @param repo_root The repository.
## @param flow The flow.
## @param rules The audience rules (no call text when bodies are excluded).
## @param template The source link template.
## @param commit The commit.
## @return One mapping per step.
## @version 1
## @req REQ-DDB-WIKI-014
def step_data(
    db: Path, repo_root: Path, flow: Flow, rules: Audience, template: str, commit: str
) -> list[dict[str, Any]]:
    """@brief Gather step data. @return Rows."""
    from .build import _link

    signatures = _signatures(db, flow)
    out = []
    for step in flow.steps:
        site = step.site_file or step.file
        link = _link(template, commit, site, step.line)
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
                "link": link[link.index("(") + 1 : -1] if link.startswith("[") else "",
            }
        )
    return out


## @brief The diagram, controls, dialog, data and script, as one raw HTML block.
## @param flow The flow.
## @param data The step data.
## @param animate Whether the diagram plays.
## @return HTML.
## @version 1
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
        f'<div class="flow-wrap">{flow_svg(flow, animate=animate)}</div>'
        '<dialog class="flow-step"><h3></h3><dl></dl>'
        '<p><a class="site" hidden>open the call site</a></p>'
        '<button type="button">close</button></dialog>'
        f'<script type="application/json" class="flow-data">{blob}</script>'
        f"{_SCRIPT}</div>"
    )


## @brief The callee signatures and briefs of a flow's steps.
## @param db The index.
## @param flow The flow.
## @return {(callee, qualified): (signature, brief)}.
## @version 1
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
                out[key] = (f"{row[0] or ''}{row[1] or ''}".strip(), str(row[2] or "").strip())
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


## @brief The source bodies of every function a flow reaches, as code blocks.
## @param db The index.
## @param repo_root The repository.
## @param flow The flow.
## @return Markdown lines.
## @version 1
## @dg_internal
def _bodies(db: Path, repo_root: Path, flow: Flow) -> list[str]:
    """THE INDEX'S OWN BODY EXCERPT (export_dossier), so a page shows what `dossier` shows.

    @brief Body sections.
    @return Lines.
    """
    from ..query import export_dossier

    seen: list[tuple[str, str]] = [(flow.entry, flow.entry_qualified)]
    seen += [(s.callee, s.callee_qualified) for s in flow.steps if s.callee_qualified]
    out: list[str] = ["", "## Functions", ""]
    for name, qual in dict.fromkeys(seen):
        payload = export_dossier(db, name, qualified=qual or None, repo_root=repo_root)
        body = payload.get("body") or {}
        if not body.get("lines"):
            continue
        out += [f"### `{qual or name}`", "", f"`{body.get('file', '')}`", "", "```"]
        out += [*body["lines"], "```", ""]
    return out
