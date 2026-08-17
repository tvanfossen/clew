# SPDX-License-Identifier: MIT
"""WHY the index arm read source, attributed to the lookup that failed first.

`tool_usage` answers "which tools were called, how often" from the runner's log. That is
the right question for grinding and adoption and it cannot answer this one, because a log
line records a call and not what came BACK. The difference decides which of two opposite
fixes applies:

  * the model over-explores            -> a prompting problem
  * the index answered nothing usable  -> a defect list

MEASURED, and it settled that question. Across the six four-tool mbedtls cells, 39 of 114
calls (34.2%) returned nothing usable from the index — 21 empty, 7 not-found, and 11 source
reads that went beyond anything the index had cited. The call count was not a behaviour to
prompt away; every extra call had a named cause, and classifying them produced five defects
that a score could not have shown:

  * five natural prose phrasings, all empty, all followed by grep on the SAME file the
    corpus already held (FTS5's implicit AND -> gh#389)
  * nine config-symbol lookups, all empty, because the gate harvest was Kconfig-only
    (gh#390) and then unreachable from `search` (gh#394)
  * a file row classifying as a class (gh#391)

THE ATTRIBUTION IS THE POINT, not the totals. `review_count` already says HOW OFTEN the
index arm read source; the owner's ruling is that a source read is a failure mode whose
cause has to be justified in grading rather than forbidden. So each source read is paired
with the index call that immediately preceded it and that call's outcome — which turns "7
Reads" into "7 Reads, 5 of them after an EMPTY prose query", and that is actionable where a
count is not.

AND IT IMMEDIATELY CORRECTED ITS OWN FIRST ANSWER, which is why the `cited`/`beyond` column
exists. The first version reported 27 source reads as 27 wasted calls and 48.2% overall. But
16 of those 27 opened a file the preceding index reply had ALREADY NAMED — the brief permits
reading a cited line to confirm it, so those are the tool working, not failing. Excluding
them gives 34.2%. A bare source-read count can be argued in either direction from the same
transcript; the split cannot.

CLASSIFICATION READS THE RESPONSE ENVELOPE, NEVER THE PROSE. `count: 0`, `found: false`,
`rows: 0` are the server's own words for "nothing". Judging intent from the model's
narration would reintroduce exactly the ambiguity this exists to remove, and calls it cannot
classify are reported as UNKNOWN and counted rather than silently bucketed.

@brief Classify index-arm tool calls by outcome and attribute each source read.
@version 1
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

## Tools that read the repository directly. Their presence in the INDEX arm is the arm
## falling back to the thing it is meant to replace, which is the signal this module exists
## for. `Bash` is included because a `Bash` call in a benchmark cell is overwhelmingly a
## source read (`cat`, `grep`, `ls`) — the same reasoning `bench_arms._SOURCE_READING_TOOLS`
## records, and the two lists are kept in step deliberately.
SOURCE_TOOLS: frozenset[str] = frozenset({"Read", "Grep", "Glob", "Bash"})

## Outcome buckets. ROWS is the only one that answered the caller; the rest are the 48.2%.
ROWS = "ROWS"
EMPTY = "EMPTY"
NOTFOUND = "NOTFOUND"
SOURCE = "SOURCE"
UNKNOWN = "UNKNOWN"

## An index call is ours when it carries the server prefix. Matched as a PREFIX rather than
## against an enumeration, for the reason `bench_arms.MCP_TOOL_PREFIX` records: membership
## lists are what keep going stale when the surface changes.
_INDEX_PREFIX = "mcp__clew__"


## @brief Pair every tool use in one transcript with its result.
## @param path Transcript JSONL written by `claude -p`.
## @return Ordered (tool name, input mapping, result text) triples.
## @version 1
def calls(path: Path) -> list[tuple[str, dict, str]]:
    """Uses and results are SEPARATE records joined by `tool_use_id`, so both passes are
    required. A single pass over assistant records would report what was ASKED and never
    what came back — which is the whole distinction between this module and `tool_usage`.

    @brief Extract ordered (name, input, result) triples.
    @return Call triples in call order.
    @version 1
    """
    uses: dict[str, tuple[str, dict]] = {}
    order: list[str] = []
    results: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        for block in _blocks(row):
            if block.get("type") == "tool_use":
                uses[block["id"]] = (block.get("name", "?"), block.get("input", {}))
                order.append(block["id"])
            elif block.get("type") == "tool_result":
                results[block.get("tool_use_id", "")] = _flatten(block.get("content"))
    return [(uses[i][0], uses[i][1], results.get(i, "")) for i in order if i in uses]


## @brief The content blocks of one transcript record, whatever shape it carries.
## @param row Parsed JSONL record.
## @return Block mappings, empty when the record carries none.
## @version 1
def _blocks(row: object) -> list[dict]:
    """@brief Yield a record's content blocks.
    @return List of block mappings.
    @version 1
    """
    if not isinstance(row, dict):
        return []
    message = row.get("message")
    content = message.get("content") if isinstance(message, dict) else row.get("content")
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


## @brief Flatten a tool result's content to plain text.
## @param content Result content: a string, or a list of blocks.
## @return Flattened text.
## @version 1
def _flatten(content: object) -> str:
    """@brief Reduce result content to one string.
    @return Text.
    @version 1
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""


## @brief Bucket one call by what its response says, not by what was asked.
## @param name Tool name.
## @param result Response text.
## @return One of ROWS / EMPTY / NOTFOUND / SOURCE / UNKNOWN.
## @version 1
def classify(name: str, result: str) -> str:
    """Order matters. A source tool is a fallback whatever it returned, and an index tool is
    judged only on whether it produced rows. `found: false` and `count: 0` are the server's
    own words, so they are read literally rather than inferred from payload size — a short
    payload can be a complete answer and a long one can be an emptiness note.

    @brief Label one call by its outcome.
    @return Bucket name.
    @version 1
    """
    if name in SOURCE_TOOLS:
        return SOURCE
    if not result:
        return UNKNOWN
    dense = result.replace(" ", "")
    if '"found":false' in dense:
        return NOTFOUND
    if '"count":0' in dense or '"rows":0' in dense:
        return EMPTY
    return ROWS


## @brief The repo-relative-ish path a source-reading call targets, if it names one.
## @param args The call's input mapping.
## @return A path string, or '' when the call names none.
## @version 1
def _target_path(args: dict) -> str:
    """`Read`/`Glob` name it directly; a `Bash` command hides it inside a shell line, so the
    longest slash-bearing token is taken as the best available guess. Deliberately crude and
    only ever used to ask "did the index already mention this file", where a wrong guess
    degrades to `unknown` rather than to a false claim.

    @brief Extract the file a source read targets.
    @return Path-like string, or ''.
    @version 1
    """
    for key in ("file_path", "path", "pattern"):
        value = args.get(key)
        if isinstance(value, str) and value:
            return value
    command = args.get("command")
    if isinstance(command, str):
        tokens = [t for t in command.split() if "/" in t]
        return max(tokens, key=len) if tokens else ""
    return ""


## @brief Attribute each source read to the index call that preceded it.
## @param triples Ordered call triples from `calls`.
## @return List of (source tool, preceding index tool, outcome, whether the index cited it).
## @version 2
def attribute(triples: list[tuple[str, dict, str]]) -> list[tuple[str, str, str, str]]:
    """THE IMMEDIATELY PRECEDING INDEX CALL, not a search back through the whole cell. The
    claim being made is narrow on purpose — "this lookup ran, then the agent read source" —
    and it is checkable from the transcript. Reaching further back for a more satisfying
    culprit would be inference dressed as measurement.

    A source read with NO index call before it is reported with `'-'` rather than dropped:
    it means the agent went to source FIRST, which is a different and worse finding than
    falling back after a miss, and dropping it would hide the case that matters most.

    THE FOURTH COLUMN IS WHAT MAKES THIS USABLE, and it exists because the first version of
    this function produced a misleading table. Most source reads in the measured run followed
    a `dossier` that RETURNED ROWS, which reads as "the index answered and the agent ignored
    it" — but the brief explicitly permits `Read` to confirm a line the index has already
    cited, and that is not waste. The two are told apart mechanically: if the file being read
    APPEARS IN the preceding index reply, the index sent the agent there (`cited`); if it does
    not, the read discovered something the index did not give (`beyond`).

    `beyond` is the number that indicts the index. `cited` is the tool working as documented.
    Collapsing them, as a bare source-read count does, is how "48% wasted calls" could be
    argued in either direction from the same transcript.

    @brief Pair each source read with the preceding lookup, its outcome, and whether it was cited.
    @return Attribution rows.
    @version 2
    """
    out: list[tuple[str, str, str, str]] = []
    last_index: tuple[str, str, str] = ("-", "-", "")
    for name, args, result in triples:
        bucket = classify(name, result)
        if bucket == SOURCE:
            path = _target_path(args)
            if not path:
                seen = "unknown"
            else:
                ## Compared on the BASENAME too: the index writes repo-relative paths while a
                ## cell may Read an absolute or `~`-prefixed one, and a literal containment
                ## test would then report `beyond` for a file the index had plainly cited.
                base = path.rsplit("/", 1)[-1]
                seen = "cited" if (path in last_index[2] or base in last_index[2]) else "beyond"
            out.append((name, last_index[0], last_index[1], seen))
        elif name.startswith(_INDEX_PREFIX):
            last_index = (name.removeprefix(_INDEX_PREFIX), bucket, result)
    return out


## @brief Render the audit for every index-arm cell in a run directory.
## @param history Directory holding `*_mcp_*.transcript.jsonl`.
## @return Markdown report text.
## @version 1
def report(history: Path) -> str:
    """Index-arm cells ONLY. A source read by the source arm is the whole method, and
    labelling it would bury the signal under 100% noise — the shape of a guard that fires on
    the ordinary case, which this project has shipped twice and paid for both times.

    @brief Build the fallback-audit markdown.
    @return Report text.
    @version 1
    """
    lines = ["## Fallback audit — index arm", ""]
    pooled: Counter[str] = Counter()
    rows: list[str] = [
        "| cell | calls | ROWS | EMPTY | NOTFOUND | source reads |",
        "|---|---|---|---|---|---|",
    ]
    attributions: list[str] = []
    for path in sorted(history.glob("*_mcp_*.transcript.jsonl")):
        triples = calls(path)
        buckets = Counter(classify(n, r) for n, _, r in triples)
        pooled.update(buckets)
        cell = path.name.split(".")[0]
        rows.append(
            f"| {cell} | {len(triples)} | {buckets[ROWS]} | {buckets[EMPTY]} "
            f"| {buckets[NOTFOUND]} | {buckets[SOURCE]} |"
        )
        for source_tool, after, outcome, seen in attribute(triples):
            attributions.append(f"| {cell} | {source_tool} | {after} | {outcome} | {seen} |")
            pooled[f"read:{seen}"] += 1

    ## COUNTED FROM THE BUCKETS ONLY, so the pooled `read:*` tallies added during
    ## attribution cannot inflate the denominator.
    total = sum(pooled[b] for b in (ROWS, EMPTY, NOTFOUND, SOURCE, UNKNOWN))
    lines += rows
    if total:
        ## TWO NUMBERS, BECAUSE ONE OF THEM IS WRONG ON ITS OWN. Counting every source read
        ## as waste says 48.2% on the measured run; but 16 of those 27 reads opened a file
        ## the index had just cited, which the brief permits and which is the tool working.
        ## The honest indictment excludes those and lands at 34.2%. Publishing the larger
        ## figure alone would overstate the defect — the same "report the axis that hurts"
        ## discipline applied against my own conclusion.
        unusable = pooled[EMPTY] + pooled[NOTFOUND] + pooled["read:beyond"]
        naive = pooled[EMPTY] + pooled[NOTFOUND] + pooled[SOURCE]
        lines += [
            "",
            f"**{unusable} of {total} calls ({unusable / total:.1%}) returned nothing usable "
            f"from the index** — empty, not-found, or a source read that went BEYOND what the "
            f"index cited.",
            "",
            f"Counting every source read as waste gives {naive} ({naive / total:.1%}), which "
            f"OVERSTATES it: {pooled['read:cited']} of those reads confirmed a line the index "
            f"had already named.",
        ]
    if attributions:
        beyond, cited = pooled["read:beyond"], pooled["read:cited"]
        lines += [
            "",
            "### Which lookup preceded each source read",
            "",
            "`after` is the index call immediately before the read; `-` means the agent went "
            "to source FIRST. `cited` means the file was already named in that reply — the "
            "brief permits reading it to confirm a line, so those are the tool working. "
            "**`beyond` is the number that indicts the index**: the read found something the "
            "index did not give.",
            "",
            f"**{beyond} beyond, {cited} cited.**",
            "",
            "| cell | read with | after | outcome | file |",
            "|---|---|---|---|---|",
            *attributions,
        ]
    if pooled[UNKNOWN]:
        lines += ["", f"{pooled[UNKNOWN]} call(s) could not be classified and are NOT bucketed."]
    return "\n".join(lines) + "\n"


## @brief The verbatim call sequence for one run, index and source calls interleaved.
## @param history The run's history directory.
## @return Markdown listing every call in order with its request and its outcome.
## @version 1
def sequence(history: Path) -> str:
    """WHY THE VERBATIM TEXT AND NOT ANOTHER COUNT. `report` says six source reads went BEYOND
    what the index cited, which is the right aggregate and cannot say WHAT the agent went looking
    for. A fix has to be aimed at a specific missing field, and "6 beyond" aims at nothing — the
    same number is produced by six different defects and by one defect six times.

    THE ORDER IS THE EVIDENCE. A grep that follows a rows-returning index call is either the agent
    confirming a cited line or the agent going after something the reply did not carry, and only
    the pair read together distinguishes them. Printing the calls interleaved, in call order, is
    what makes the transition visible.

    Requests are TRUNCATED, deliberately and to a stated width: a `Bash` command can be a whole
    script and an index reply can be tens of kilobytes, and this is a routing aid pointing at the
    transcript rather than a substitute for reading it.

    @brief Print every call in order with its request and outcome.
    @return Markdown sequence listing.
    @version 1
    """
    lines: list[str] = ["## Call sequence — index arm", ""]
    for path in sorted(history.glob("*.transcript.jsonl")):
        lines += [
            f"### {path.name.split('.')[0]}",
            "",
            "| # | tool | request | outcome |",
            "|---|---|---|---|",
        ]
        for position, (name, args, result) in enumerate(calls(path), start=1):
            request = args.get("command") or args.get("pattern") or args.get("text")
            request = request or args.get("subject") or args.get("file_path") or ""
            request = str(request).replace("|", "\\|").replace("\n", " ")[:_REQUEST_WIDTH]
            outcome = classify(name, result)
            short = name.replace(_INDEX_PREFIX, "")
            lines.append(f"| {position} | {short} | `{request}` | {outcome} ({len(result)}B) |")
        lines.append("")
    return "\n".join(lines) + "\n"


## Characters of a request echoed in the sequence listing. Wide enough that a grep pattern and a
## short shell pipeline survive intact, which is what the listing exists to show.
_REQUEST_WIDTH = 110


## @brief CLI: print the fallback audit for one run's history directory.
## @return 0 on success, 1 when the directory is absent.
## @version 2
def main() -> int:
    """@brief Print the fallback audit, or the verbatim call sequence.
    @return Exit status.
    @version 2
    """
    if len(sys.argv) < 2:
        print("usage: fallback_audit.py <run-dir-or-history-dir> [--sequence]", file=sys.stderr)
        return 1
    given = Path(sys.argv[1])
    history = given if given.name == "history" else given / "history"
    if not history.is_dir():
        print(f"no history directory at {history}", file=sys.stderr)
        return 1
    if "--unretrieved" in sys.argv:
        print(unretrieved(history), end="")
    else:
        print(sequence(history) if "--sequence" in sys.argv else report(history), end="")
    return 0


## @brief Citations an answer makes that appear in NO tool result of its own transcript.
## @param history The run's history directory.
## @return Markdown table of unretrieved citations per cell, with a per-arm rate.
## @version 1
def unretrieved(history: Path) -> str:
    """THE OBSERVABLE SIGNATURE OF RECALL RATHER THAN RETRIEVAL. An answer that cites
    `library/threading.c:182` while no tool result in its own transcript contains that path or that
    line did not READ the fact — it produced it. Retrieval cannot explain such a citation; a
    training prior can, and mbedtls is a widely-mirrored library.

    THIS IS EVIDENCE, NOT PROOF, and the direction of the error is worth stating. A citation can
    also be UNRETRIEVED because the agent inferred it correctly from an adjacent line it did read,
    or because the path appears in a form this matcher does not align (a relative vs absolute
    spelling). So the count is an UPPER BOUND on recall. What makes it useful is the COMPARISON: the
    same measure applied to both arms, and later to an obscure target beside a famous one, is a
    difference that no matching artifact explains away.

    WHY IT MATTERS FOR THE GRID. If the source arm is answering partly from memory of a public
    library, then "src beats index on mbedtls" measures the corpus, not the tools — and the honest
    comparison needs a target the model cannot have memorised. This function is what turns that from
    an argument into a number.

    MATCHED AT FILE GRANULARITY, NOT LINE, AND THE FIRST VERSION WAS WRONG FOR EXACTLY THE REASON
    THIS PROJECT KEEPS RE-LEARNING. It compared `basename:line` pairs and reported 98% of index-arm
    citations and 85% of source-arm citations as unretrieved — a number so high it could only be the
    DETECTOR failing. It was: a dossier reports a location as JSON (`"file": "threading.c",
    "line_start": 182`) and a `Read` returns line-numbered content, so neither renders the
    `file.c:182` spelling the regex required. The measure was scoring tool OUTPUT FORMATS.

    A file's basename appearing anywhere in any tool result is format-independent, and the claim it
    supports is weaker but sound: the answer cited a file the transcript never mentions. Line-level
    recall stays unmeasured, and saying so is better than a number that describes a regex.

    @brief Count answer citations absent from every tool result.
    @return Markdown report.
    @version 1
    """
    import re

    cite = re.compile(r"([A-Za-z0-9_./-]+\.(?:c|h|cpp|hpp|md|py|yaml|function)):(\d+)")
    rows: list[str] = []
    totals: dict[str, list[int]] = {}
    for path in sorted(history.glob("*.transcript.jsonl")):
        cell = path.name.split(".")[0]
        answer_path = path.parent.parent / f"{cell}.md"
        if not answer_path.exists():
            continue
        seen = " ".join(result for _n, _a, result in calls(path))
        claimed = {
            Path(m.group(1)).name
            for m in cite.finditer(answer_path.read_text(encoding="utf-8", errors="replace"))
        }
        pool = {name for name in claimed if name in seen}
        if not claimed:
            continue
        missing = sorted(claimed - pool)
        arm = "mcp" if "_mcp_" in cell else "src"
        totals.setdefault(arm, [0, 0])
        totals[arm][0] += len(missing)
        totals[arm][1] += len(claimed)
        rows.append(
            f"| {cell} | {len(claimed)} | {len(missing)} | "
            f"{100 * len(missing) / len(claimed):.0f}% | "
            f"{', '.join(missing[:4])}{' …' if len(missing) > 4 else ''} |"
        )
    lines = [
        "## Citations the answer makes that NO tool result contained",
        "",
        "An UPPER BOUND on recall-rather-than-retrieval: a correct citation absent from every tool "
        "result was not read. Inference from an adjacent line inflates it, so read the ARM "
        "DIFFERENCE rather than the absolute rate.",
        "",
        "| cell | cited | unretrieved | rate | examples |",
        "|---|---|---|---|---|",
        *rows,
        "",
    ]
    for arm, (miss, claimed) in sorted(totals.items()):
        lines.append(
            f"**{arm}: {miss} of {claimed} citations unretrieved ({100 * miss / claimed:.0f}%)**"
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
