# SPDX-License-Identifier: MIT
## @brief Turn a benchmark cell's raw artifacts into evidence a human can actually read.
## @version 1
"""396 cells is unvettable unless the evidence is designed for reading.

The owner's requirement, verbatim: "we need to make sure that the evidence is human readable,
with a quick and easily readable reference to what the model produced ... nominally even a log
of each agents history in human readable form is valuable here for a true vetting of what
occurred for each test".

WHAT WAS MISSING. The harness FINDS each cell's transcript (`bench_arms.find_transcript`) to
count tool calls and audit arm isolation, and then throws it away. The file lives under
`~/.claude/projects/<slug>/<session>.jsonl`, which rotates — so after a run there was no
record of WHAT THE AGENT ACTUALLY DID, only its final prose. A reviewer could see the answer
and the grade but never the working, which is precisely what makes a grade checkable.

Worse, that gap already bit: 15 of 18 cells in a retracted grid reported in prose that they
were pointed at the wrong repository, and nobody read them. The transcripts would have shown
it in the first tool call.

WHAT THIS PRODUCES, per cell:

  <cell>.history.md   a readable narrative — every tool call with its arguments and a
                      short result summary, in order, with timings
  <cell>.transcript.jsonl   the raw record, preserved so the narrative can be re-derived
                            and so nothing depends on this renderer being correct

The narrative is a CONVENIENCE over the raw file, never a replacement. A reviewer who
distrusts the rendering must be able to go to the source, which is why both ship.

Usage:
  .venv/bin/python acceptance/bench/evidence.py <transcript.jsonl> <out.history.md> [--title T]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

## Tool-call arguments worth showing inline. A full argument dump makes the narrative
## unreadable — the point is to see WHAT WAS ASKED, not to re-serialise the payload.
_KEY_ARGS = ("function", "symbol", "name", "query", "q", "pattern", "repo_path", "file_path",
             "command", "path", "req_id", "direction", "max_depth", "kind", "scope")  # fmt: skip

## Arguments shown IN FULL, never truncated. These do not describe the call — they ARE the
## method, and the reviewer's question is whether the method was sound.
##
## Found in the first calibration's source-arm history, where an 80-character cap produced:
##   command=grep -rhoE '^[A-Za-z_][A-Za-z0-9_:<>,&* ]*\b([A-Za-z_][A-Za-z0-9_]*)::([A-Za-z_~
## A regex cut mid-character-class cannot be evaluated by anyone, so "did the source arm
## measure name collisions correctly?" became unanswerable from the document written to
## answer exactly that. Also the house rule: never truncate log content.
_FULL_ARGS = frozenset({"command", "pattern", "query"})

## Cap for the incidental arguments — a symbol name, a path, a direction. Long enough that
## nothing real is lost, short enough to keep one call on one line.
_ARG_CHARS = 80

## How much of a tool RESULT to show. Enough to see whether it answered; not so much that the
## narrative becomes the payload. A reviewer chasing detail has the raw jsonl.
_RESULT_CHARS = 220


## @brief Read a JSONL transcript, tolerating partial final lines.
## @param path Transcript file.
## @return Parsed records in order.
## @version 1
## @dg_internal
def _records(path: Path) -> list[dict[str, Any]]:
    """A transcript being written when the process died can end mid-line. Skipping an
    unparseable tail is right; aborting would lose the whole history for one bad byte.

    @brief Parse a transcript file.
    @return List of records.
    @version 1
    """
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


## @brief The interesting arguments of one tool call, as a short string.
## @param args Tool input mapping.
## @return Compact "k=v" summary.
## @version 2
## @dg_internal
def _args_summary(args: Any) -> str:
    """Arguments in `_FULL_ARGS` are reproduced verbatim; everything else is capped. The
    distinction is between an argument that IDENTIFIES a call and one that CONSTITUTES it —
    a truncated symbol name is still recognisable, a truncated regex is not checkable.

    @brief Summarise tool arguments for a human.
    @return Compact argument string.
    @version 2
    """
    if not isinstance(args, dict):
        return ""
    parts = []
    for key in _KEY_ARGS:
        if key in args and args[key] not in (None, "", []):
            value = str(args[key]).replace("\n", " ")
            shown = value if key in _FULL_ARGS else value[:_ARG_CHARS]
            parts.append(f"{key}={shown}")
    ## Nothing recognised: show the keys so a reviewer can tell a call was made at all.
    return ", ".join(parts) if parts else ", ".join(sorted(args)[:4])


## @brief Flatten a message's content blocks into (kind, payload) pairs.
## @param message A transcript message record.
## @return List of (kind, payload) tuples.
## @version 2
## @dg_internal
def _blocks(message: Any) -> list[tuple[str, Any]]:
    """@brief Extract content blocks from a message.
    @return (kind, payload) pairs.
    @version 2
    """
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return [("text", content)]
    if not isinstance(content, list):
        return []
    return [(b.get("type", "?"), b) for b in content if isinstance(b, dict)]


## @brief Render one transcript as a readable narrative.
## @param records Parsed transcript records.
## @param title Heading for the document.
## @return Markdown text.
## @version 1
def render(records: list[dict[str, Any]], title: str) -> str:
    """Ordered narrative of what the agent DID: each tool call with its arguments, each
    result summarised, and the final answer. Assistant prose between calls is included
    because the reasoning is often where a wrong premise becomes visible — the retracted
    grid's cells SAID they had the wrong repository, in prose, between tool calls.

    @brief Build the human-readable history document.
    @return Markdown.
    @version 1
    """
    lines = [
        f"# {title}",
        "",
        "> Machine-generated narrative of one benchmark cell. The authoritative record is the",
        "> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the",
        "> agent did without parsing JSON. If the two disagree, the JSONL is correct.",
        "",
    ]
    step = 0
    pending: dict[str, str] = {}
    final_text: list[str] = []

    for record in records:
        role = record.get("type")
        if role not in ("assistant", "user"):
            continue
        for kind, block in _blocks(record.get("message")):
            if kind == "text" and role == "assistant":
                text = block if isinstance(block, str) else block.get("text", "")
                if text.strip():
                    lines.append(f"**Reasoning.** {text.strip()[:600]}")
                    lines.append("")
                    final_text = [text.strip()]
            elif kind == "tool_use":
                step += 1
                name = str(block.get("name", "?"))
                pending[str(block.get("id", ""))] = name
                lines.append(f"### {step}. `{name}`")
                summary = _args_summary(block.get("input"))
                if summary:
                    lines.append(f"- **asked:** {summary}")
            elif kind == "tool_result":
                body = block.get("content")
                if isinstance(body, list):
                    body = " ".join(b.get("text", "") for b in body if isinstance(b, dict))
                text = str(body or "").replace("\n", " ").strip()
                flag = " ⚠ error" if block.get("is_error") else ""
                lines.append(
                    f"- **got{flag}:** {text[:_RESULT_CHARS]}"
                    + ("…" if len(text) > _RESULT_CHARS else "")
                )
                lines.append("")

    lines += [
        "---",
        "",
        "## Final answer as submitted",
        "",
        final_text[0] if final_text else "_(none captured)_",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    title = sys.argv[sys.argv.index("--title") + 1] if "--title" in sys.argv else src.stem
    dst.write_text(render(_records(src), title), encoding="utf-8")
    print(f"wrote {dst} ({dst.stat().st_size:,} bytes)")
