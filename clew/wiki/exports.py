# SPDX-License-Identifier: MIT
"""The site's exports: the same trace in other tools' formats (round 3, P3b).

Owner 2026-11-15 (interop: ReqIF, Sphinx-needs, Structurizr DSL) and the plan's diagram and
agent formats. Everything is written into the built site (`exports/`, and `llms*.txt` at its
root, where that convention looks) and obeys the build's audience — no requirement title or
criteria under `exclude_requirement_text`:

  * a flow as a MERMAID or PLANTUML sequence diagram, frames as loop / alt / opt blocks — for
    wikis that render them (Azure DevOps, GitHub);
  * LLMS.TXT, the site's index for agents (an H1, a one-line summary, linked sections), and
    LLMS-FULL.TXT, the same content as dense text;
  * REQIF 1.2 — one SPEC-OBJECT per requirement (id, title, text, tier), grouped in one
    SPECIFICATION;
  * SPHINX-NEEDS `needs.json` — one need per requirement, typed `req`;
  * STRUCTURIZR DSL — the system, a container per component, a relation per link.

@brief Write the site's exports.
@version 1
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape
from xml.sax.saxutils import quoteattr

from .config import Audience

## Frame kinds as sequence-diagram blocks.
_BLOCK = {"loop": "loop", "if": "alt", "else": "alt", "case": "alt", "try": "opt", "catch": "opt"}


## @brief A sequence-diagram writer: participants, messages in order, frames as nested blocks.
## @version 1
class _SequenceWriter(ABC):
    """THE BASE OWNS THE ORDER AND THE FRAMES: a frame is identified by the function it is in, its
    kind and its line, so a frame closes when the next step is no longer inside it; a subclass
    only names its syntax.

    @brief Sequence writer.
    @version 1
    """

    ## @brief Render a flow.
    ## @param flow The flow.
    ## @return The diagram text.
    ## @version 1
    ## @dg_internal
    def render(self, flow: Any) -> str:
        """@brief Render. @return Text."""
        ids = {lane.id: f"P{i}" for i, lane in enumerate(flow.lanes)}
        out = [*self.head(), *(self.participant(ids[ln.id], ln.label) for ln in flow.lanes)]
        stack: list[tuple[str, str, int]] = []
        for step in flow.steps:
            frames = [(step.caller_qualified, f.kind, f.line) for f in step.frames]
            while stack and stack != frames[: len(stack)]:
                stack.pop()
                out.append(self.indent(len(stack)) + "end")
            for frame in frames[len(stack) :]:
                out.append(self.indent(len(stack)) + self.block(frame[1], frame[2]))
                stack.append(frame)
            out.append(
                self.indent(len(stack))
                + self.message(ids[step.from_lane], ids[step.to_lane], step.callee)
            )
        while stack:
            stack.pop()
            out.append(self.indent(len(stack)) + "end")
        return "\n".join([*out, *self.tail()]) + "\n"

    ## @brief Indentation inside `depth` open blocks.
    ## @param depth Open blocks.
    ## @return Spaces.
    ## @version 1
    ## @dg_internal
    def indent(self, depth: int) -> str:
        """@brief Indent. @return Spaces."""
        return "    " * (depth + 1)

    ## @brief One frame as a block opener.
    ## @param kind The frame kind.
    ## @param line Its line.
    ## @return Text.
    ## @version 1
    ## @dg_internal
    def block(self, kind: str, line: int) -> str:
        """@brief Block. @return Text."""
        return f"{_BLOCK.get(kind, 'opt')} {kind} (line {line})"

    ## @brief The diagram's opening lines.
    ## @return Lines.
    ## @version 1
    ## @dg_internal
    @abstractmethod
    def head(self) -> list[str]:
        """@brief Head. @return Lines."""

    ## @brief The diagram's closing lines.
    ## @return Lines.
    ## @version 1
    ## @dg_internal
    @abstractmethod
    def tail(self) -> list[str]:
        """@brief Tail. @return Lines."""

    ## @brief A participant declaration.
    ## @param pid Its id.
    ## @param label Its label.
    ## @return Text.
    ## @version 1
    ## @dg_internal
    @abstractmethod
    def participant(self, pid: str, label: str) -> str:
        """@brief Participant. @return Text."""

    ## @brief One message.
    ## @param a From participant.
    ## @param b To participant.
    ## @param text The callee.
    ## @return Text.
    ## @version 1
    ## @dg_internal
    @abstractmethod
    def message(self, a: str, b: str, text: str) -> str:
        """@brief Message. @return Text."""


## @brief Mermaid `sequenceDiagram`.
## @version 1
class _Mermaid(_SequenceWriter):
    """@brief Mermaid. @version 1"""

    ## @brief Head.
    ## @return Lines.
    ## @version 1
    ## @dg_internal
    def head(self) -> list[str]:
        """@brief Head. @return Lines."""
        return ["sequenceDiagram", "    autonumber"]

    ## @brief Tail.
    ## @return Lines.
    ## @version 1
    ## @dg_internal
    def tail(self) -> list[str]:
        """@brief Tail. @return Lines."""
        return []

    ## @brief Participant.
    ## @param pid Id.
    ## @param label Label.
    ## @return Text.
    ## @version 1
    ## @dg_internal
    def participant(self, pid: str, label: str) -> str:
        """@brief Participant. @return Text."""
        return f'    participant {pid} as "{label}"'

    ## @brief Message.
    ## @param a From.
    ## @param b To.
    ## @param text Callee.
    ## @return Text.
    ## @version 1
    ## @dg_internal
    def message(self, a: str, b: str, text: str) -> str:
        """@brief Message. @return Text."""
        return f"{a}->>{b}: {text}"


## @brief PlantUML sequence diagram.
## @version 1
class _PlantUml(_SequenceWriter):
    """@brief PlantUML. @version 1"""

    ## @brief Head.
    ## @return Lines.
    ## @version 1
    ## @dg_internal
    def head(self) -> list[str]:
        """@brief Head. @return Lines."""
        return ["@startuml", "autonumber"]

    ## @brief Tail.
    ## @return Lines.
    ## @version 1
    ## @dg_internal
    def tail(self) -> list[str]:
        """@brief Tail. @return Lines."""
        return ["@enduml"]

    ## @brief Participant.
    ## @param pid Id.
    ## @param label Label.
    ## @return Text.
    ## @version 1
    ## @dg_internal
    def participant(self, pid: str, label: str) -> str:
        """@brief Participant. @return Text."""
        return f'participant "{label}" as {pid}'

    ## @brief Message.
    ## @param a From.
    ## @param b To.
    ## @param text Callee.
    ## @return Text.
    ## @version 1
    ## @dg_internal
    def message(self, a: str, b: str, text: str) -> str:
        """@brief Message. @return Text."""
        return f"{a} -> {b}: {text}"

    ## @brief PlantUML names an if/try block `alt` / `group`.
    ## @param kind The frame kind.
    ## @param line Its line.
    ## @return Text.
    ## @version 1
    ## @dg_internal
    def block(self, kind: str, line: int) -> str:
        """@brief Block. @return Text."""
        word = {"loop": "loop", "if": "alt", "else": "alt", "case": "alt"}.get(kind, "group")
        return f"{word} {kind} (line {line})"


## @brief A flow as a Mermaid sequence diagram.
## @param flow The flow.
## @return Mermaid text.
## @version 1
## @req REQ-DDB-WIKI-029
def flow_mermaid(flow: Any) -> str:
    """@brief Mermaid. @return Text."""
    return _Mermaid().render(flow)


## @brief A flow as a PlantUML sequence diagram.
## @param flow The flow.
## @return PlantUML text.
## @version 1
## @req REQ-DDB-WIKI-029
def flow_plantuml(flow: Any) -> str:
    """@brief PlantUML. @return Text."""
    return _PlantUml().render(flow)


## @brief A requirement's title and text, or empty under `exclude_requirement_text`.
## @param row The evidence row.
## @param entry Its catalog entry.
## @param rules The audience rules.
## @return (title, text).
## @version 1
## @dg_internal
def _words(row: Any, entry: dict, rules: Audience) -> tuple[str, str]:
    """@brief Title and text. @return Pair."""
    from .reqmodal import first

    if rules.exclude_requirement_text:
        return "", ""
    title = row.title or str(first(entry, "name", "title"))
    return title, str(first(entry, "acceptance_criteria", "acceptance", "description"))


## @brief Write every export into the site's extra directory.
## @param extra The directory copied to the site root.
## @param trace The gathered trace.
## @param pages The flow pages.
## @param graph The system graph.
## @param ctx title, rules (Audience), summary.
## @return None.
## @version 1
## @req REQ-DDB-WIKI-029
def write_exports(extra: Path, trace: Any, pages: list, graph: dict, ctx: dict[str, Any]) -> None:
    """@brief Write exports. @return None."""
    out = Path(extra) / "exports"
    out.mkdir(parents=True, exist_ok=True)
    rules: Audience = ctx["rules"]
    (out / "requirements.reqif").write_text(reqif(trace, rules, ctx["title"]), encoding="utf-8")
    (out / "needs.json").write_text(needs_json(trace, rules, ctx["title"]), encoding="utf-8")
    (out / "system.dsl").write_text(structurizr(graph, ctx["title"]), encoding="utf-8")
    (Path(extra) / "llms.txt").write_text(llms_txt(trace, pages, ctx), encoding="utf-8")
    (Path(extra) / "llms-full.txt").write_text(
        llms_full(trace, pages, rules, ctx), encoding="utf-8"
    )


## @brief llms.txt: the site's index for agents.
## @param trace The gathered trace.
## @param pages The flow pages.
## @param ctx title, summary.
## @return Markdown.
## @version 1
## @req REQ-DDB-WIKI-029
def llms_txt(trace: Any, pages: list, ctx: dict[str, Any]) -> str:
    """THE LLMSTXT.ORG SHAPE: an H1, a one-line summary as a quote, then H2 sections of links.

    @brief llms.txt.
    @return Text.
    """
    ev = trace.evidence
    lines = [
        f"# {ctx['title']}",
        "",
        f"> {ctx.get('summary') or 'Generated by clew wiki from the repository index.'}",
        "",
        "## Requirements",
        "",
        f"- [Requirements](requirements.html): {len(ev)} requirements, "
        f"{sum(1 for r in ev if r.tier == 'PASS')} passing",
        "",
        "## Flows",
        "",
        *(f"- [{p.title.replace('`', '')}]({p.name}.html): {p.steps} steps" for p in pages),
        "",
        "## Optional",
        "",
        "- [Full text](llms-full.txt): every requirement and flow as text",
        "- [Map](map.html): the system's components",
        "",
    ]
    return "\n".join(lines)


## @brief llms-full.txt: every requirement and flow as dense text.
## @param trace The gathered trace.
## @param pages The flow pages.
## @param rules The audience rules.
## @param ctx title.
## @return Text.
## @version 1
## @req REQ-DDB-WIKI-029
def llms_full(trace: Any, pages: list, rules: Audience, ctx: dict[str, Any]) -> str:
    """@brief llms-full.txt. @return Text."""
    out = [f"# {ctx['title']}", "", "## Requirements", ""]
    for row in trace.evidence:
        title, text = _words(row, trace.declared.get(row.req_id, {}), rules)
        impl = ", ".join(f"{n} ({f})" for n, f, _l in row.implementer_sites)
        out.append(f"{row.req_id} [{row.tier}]{' ' + title if title else ''}")
        if text:
            out.append(f"  criteria: {text}")
        out.append(f"  implemented by: {impl or 'none'}; tests: {len(row.tests)}")
    out += ["", "## Flows", ""]
    for p in pages:
        out.append(f"{p.title.replace('`', '')} — {p.name}.html")
        out += [f"  {a} -> {b}" for a, b in p.calls]
    return "\n".join(out) + "\n"


## @brief ReqIF 1.2.
## @param trace The gathered trace.
## @param rules The audience rules.
## @param title The site title.
## @return XML.
## @version 1
## @req REQ-DDB-WIKI-029
def reqif(trace: Any, rules: Audience, title: str) -> str:
    """ONE STRING DATATYPE, ONE SPEC-OBJECT-TYPE with four attributes (ID, Title, Text, Tier), one
    SPEC-OBJECT per requirement and one SPECIFICATION listing them — the shape every ReqIF tool
    imports.

    @brief ReqIF.
    @return XML.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    attrs = ("ID", "Title", "Text", "Tier")
    defs = "".join(
        f'<ATTRIBUTE-DEFINITION-STRING IDENTIFIER="ad-{a}" LONG-NAME="{a}" LAST-CHANGE="{now}">'
        "<TYPE><DATATYPE-DEFINITION-STRING-REF>dt-string</DATATYPE-DEFINITION-STRING-REF></TYPE>"
        "</ATTRIBUTE-DEFINITION-STRING>"
        for a in attrs
    )
    objects, refs = [], []
    for i, row in enumerate(trace.evidence):
        words = _words(row, trace.declared.get(row.req_id, {}), rules)
        values = dict(zip(attrs, (row.req_id, *words, row.tier), strict=True))
        vals = "".join(
            f"<ATTRIBUTE-VALUE-STRING THE-VALUE={quoteattr(v)}><DEFINITION>"
            f"<ATTRIBUTE-DEFINITION-STRING-REF>ad-{a}</ATTRIBUTE-DEFINITION-STRING-REF>"
            "</DEFINITION></ATTRIBUTE-VALUE-STRING>"
            for a, v in values.items()
            if v
        )
        objects.append(
            f'<SPEC-OBJECT IDENTIFIER="so-{i}" LAST-CHANGE="{now}"><TYPE><SPEC-OBJECT-TYPE-REF>'
            f"sot-req</SPEC-OBJECT-TYPE-REF></TYPE><VALUES>{vals}</VALUES></SPEC-OBJECT>"
        )
        refs.append(
            f'<SPEC-HIERARCHY IDENTIFIER="sh-{i}" LAST-CHANGE="{now}"><OBJECT>'
            f"<SPEC-OBJECT-REF>so-{i}</SPEC-OBJECT-REF></OBJECT></SPEC-HIERARCHY>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<REQ-IF xmlns="http://www.omg.org/spec/ReqIF/20110401/reqif.xsd">'
        f'<THE-HEADER><REQ-IF-HEADER IDENTIFIER="clew-wiki"><CREATION-TIME>{now}</CREATION-TIME>'
        "<REQ-IF-TOOL-ID>clew wiki</REQ-IF-TOOL-ID><REQ-IF-VERSION>1.2</REQ-IF-VERSION>"
        f"<SOURCE-TOOL-ID>clew</SOURCE-TOOL-ID><TITLE>{xml_escape(title)}</TITLE>"
        "</REQ-IF-HEADER></THE-HEADER><CORE-CONTENT><REQ-IF-CONTENT><DATATYPES>"
        f'<DATATYPE-DEFINITION-STRING IDENTIFIER="dt-string" MAX-LENGTH="100000" LAST-CHANGE="{now}"/>'
        f'</DATATYPES><SPEC-TYPES><SPEC-OBJECT-TYPE IDENTIFIER="sot-req" LONG-NAME="Requirement" '
        f'LAST-CHANGE="{now}"><SPEC-ATTRIBUTES>{defs}</SPEC-ATTRIBUTES></SPEC-OBJECT-TYPE>'
        f'<SPECIFICATION-TYPE IDENTIFIER="st-spec" LAST-CHANGE="{now}"/></SPEC-TYPES>'
        f"<SPEC-OBJECTS>{''.join(objects)}</SPEC-OBJECTS><SPECIFICATIONS>"
        f'<SPECIFICATION IDENTIFIER="spec-1" LONG-NAME={quoteattr(title)} LAST-CHANGE="{now}">'
        "<TYPE><SPECIFICATION-TYPE-REF>st-spec</SPECIFICATION-TYPE-REF></TYPE>"
        f"<CHILDREN>{''.join(refs)}</CHILDREN></SPECIFICATION></SPECIFICATIONS>"
        "</REQ-IF-CONTENT></CORE-CONTENT></REQ-IF>\n"
    )


## @brief Sphinx-needs `needs.json`.
## @param trace The gathered trace.
## @param rules The audience rules.
## @param title The site title.
## @return JSON.
## @version 1
## @req REQ-DDB-WIKI-029
def needs_json(trace: Any, rules: Audience, title: str) -> str:
    """THE NEEDS-JSON SHAPE (`needs_builder`): a project, a current version, and per version the
    needs keyed by id with their amount.

    @brief needs.json.
    @return JSON.
    """
    needs = {}
    for row in trace.evidence:
        name, text = _words(row, trace.declared.get(row.req_id, {}), rules)
        needs[row.req_id] = {
            "id": row.req_id,
            "type": "req",
            "title": name,
            "content": text,
            "status": row.tier,
            "tags": [],
            "links": [],
            "sections": [],
        }
    payload = {
        "created": datetime.now(timezone.utc).isoformat(),
        "project": title,
        "current_version": "current",
        "versions": {"current": {"needs": needs, "needs_amount": len(needs)}},
    }
    return json.dumps(payload, indent=2)


## @brief Structurizr DSL: the system, a container per component, a relation per link.
## @param graph The system graph.
## @param title The site title.
## @return DSL.
## @version 1
## @req REQ-DDB-WIKI-029
def structurizr(graph: dict, title: str) -> str:
    """@brief Structurizr. @return DSL."""
    ids = {c["id"]: f"c{i}" for i, c in enumerate(graph["components"])}
    lines = [
        "workspace {",
        "    model {",
        f"        system = softwareSystem {json.dumps(title)} {{",
    ]
    lines += [
        f"            {ids[c['id']]} = container {json.dumps(c['id'])} "
        f'"{c["functions"]} functions, {c["files"]} files"'
        for c in graph["components"]
    ]
    lines.append("        }")
    lines += [
        f'        {ids[link["from"]]} -> {ids[link["to"]]} "{link["calls"]} calls"'
        for link in graph["links"]
        if link["from"] in ids and link["to"] in ids
    ]
    lines += [
        "    }",
        "    views {",
        "        container system {",
        "            include *",
        "            autolayout tb",
        "        }",
        "    }",
        "}",
        "",
    ]
    return "\n".join(lines)
