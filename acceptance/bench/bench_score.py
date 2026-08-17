## @brief Objective (string-matching) pass: does an answer cite a mark's symbols and lines?
## @version 1
"""Settle the marks a string match CAN settle, with quoted evidence.

Deliberately conservative, because the LLM judge runs afterwards on everything
this pass does not score a clean HIT: a false MISS here costs one judge call,
whereas a false HIT would silently inflate a score no human ever re-checks.

Two normalisations matter:

- **Paths are compared by basename.** The rubric cites `LinkOwner.cpp:49`
  (an illustrative name); an answer may cite
  `deps/net/link-owner/src/LinkOwner.cpp:49`. Same citation.
- **Line drift is tolerated.** Answers cite ranges (`:49-64`) around the exact
  line the rubric names; a few lines of slack is a correct citation, not a
  lucky one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from bench_rubric import Mark

_FILE_REF = re.compile(
    r"([A-Za-z0-9_./-]+\.(?:cpp|hpp|h|cc|c|yaml|toml|md)):(\d+)(?:\s*[-–]\s*(\d+))?"
)

## A file NAMED without a line, which is what satisfies a whole-file `[path]` ref.
##
## THE EXTENSION SET IS THE SAME as `_FILE_REF`'s plus `.function`, and the pattern deliberately
## requires a path-shaped token rather than any word: mbedtls prose says "the `library/` tree" and
## "a `.c` file" constantly, and a looser match would turn a mark's file citation into another
## auto-HIT — the exact defect this whole sweep exists to remove. A bare `threading.h` with no
## directory still matches, because an answer naming the basename HAS named the file.
_FILE_NAMED = re.compile(r"\b([A-Za-z0-9_./-]+\.(?:cpp|hpp|h|cc|c|yaml|toml|md|function))\b(?!:\d)")
DEFAULT_DRIFT = 4


## @brief One mark's objective verdict plus the evidence behind it.
## @version 1
@dataclass
class ObjectiveResult:
    """@brief Objective-pass verdict record.
    @version 1
    """

    verdict: str = "n/a"  ## HIT | MISS | n/a (nothing checkable) — no partial credit
    symbols_hit: list[str] = field(default_factory=list)
    symbols_weak: list[str] = field(default_factory=list)
    symbols_missed: list[str] = field(default_factory=list)
    refs_hit: list[str] = field(default_factory=list)
    refs_file_only: list[str] = field(default_factory=list)
    refs_missed: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


## @brief Index every `file:line` citation an answer makes.
## @param answer Answer markdown.
## @return Mapping basename -> list of (lo, hi) cited ranges.
## @version 1
def answer_citations(answer: str) -> dict[str, list[tuple[int, int]]]:
    """@brief Collect the answer's own file:line citations by basename.
    @return Citation index.
    @version 1
    """
    index: dict[str, list[tuple[int, int]]] = {}
    for match in _FILE_REF.finditer(answer):
        name = Path(match.group(1)).name
        lo = int(match.group(2))
        index.setdefault(name, []).append((lo, int(match.group(3) or lo)))
    ## A FILE NAMED WITHOUT A LINE IS STILL A CITATION, and until this ran the whole-file `[path]`
    ## ref form was unmatchable: `_FILE_REF` needs `name:line`, so an answer saying "declared in
    ## `include/mbedtls/threading.h`" indexed NOTHING and a mark declaring that file scored MISS.
    ## Accepting the form in the parser and then never matching it here would have moved the defect
    ## rather than fixed it — and invisibly, because a declared ref that can never match reads
    ## exactly like an answer that never cited the file.
    ##
    ## Recorded with an EMPTY line list so the two cases stay distinguishable: a line-bearing ref
    ## still requires overlap, and only a whole-file ref is satisfied by the bare mention.
    for match in _FILE_NAMED.finditer(answer):
        name = Path(match.group(1)).name
        index.setdefault(name, [])
    return index


## @brief Find the answer line that mentions a token, as quotable evidence.
## @param answer Answer markdown.
## @param token Token to locate.
## @return A trimmed line containing the token, or "".
## @version 1
def _quote(answer: str, token: str) -> str:
    """THE EVIDENCE MUST QUOTE THE OCCURRENCE THAT MATCHED. This used to scan for `token in line`
    while the matcher had moved to whole-identifier matching, so the recorded evidence pointed at
    the FIRST substring occurrence — which is frequently a different identifier that merely ends
    in the declared one.

    That is not cosmetic and it is not hypothetical. An independent reviewer audited the committed
    sidecars, read `symbol \\`mutex_\\` — adapter_mutex_ in AdapterManager` on entropic Q1 #7, and
    correctly concluded the mark had been awarded on a different member. Replaying the scorer over
    the same answers showed every one of those four cells DOES name a bare `mutex_` elsewhere in
    the text, so the mark was earned and only the quote was wrong. A misattributing evidence field
    manufactures false findings in exactly the audit it exists to support, and a human overturning
    a grade would have been misled the same way.

    Falls back to a substring line when no whole-identifier line exists, so a WEAK or diagnostic
    quote still says something rather than nothing.

    @brief Quote the answer line where a token appears as itself.
    @return Evidence line.
    @version 2
    """
    lines = answer.splitlines()
    for line in lines:
        if _names_symbol(line, token):
            return line.strip()
    for line in lines:
        if token in line:
            return line.strip()
    return ""


## @brief Find a line where every part of a qualified symbol appears together.
## @param answer Answer markdown.
## @param symbol Qualified symbol, e.g. `VacuumFsm::react`.
## @return The co-locating line, or "" when the parts never share a line.
## @version 1
def _co_located(answer: str, symbol: str) -> str:
    """Requiring one LINE to carry both the class and the member is what stops
    "`VacuumFsm::react`" being credited to an answer that says "VacuumFsm"
    somewhere and, pages later, "LEDs might also *react* to battery state".
    That false positive was real, and it inflated a PARTIAL.

    @brief Test whether a qualified symbol's parts co-occur on one line.
    @return Evidence line or "".
    @version 1
    """
    parts = symbol.split("::")
    for line in answer.splitlines():
        if all(part in line for part in parts):
            return line.strip()
    return ""


## @brief Does the answer name this symbol as a whole identifier?
## @details A bare `symbol in answer` cannot tell a member from its own suffix, and that is not a
##          hypothetical: entropic Q1 #7 requires six classes to declare a member LITERALLY NAMED
##          `mutex_`, and it auto-HIT in 4 of 4 cells on `adapter_mutex_` and `io_mutex_` — two
##          different members. The mark's whole point is the collision, and the matcher awarded it
##          to the non-collision.
##
##          The boundary is a property of C identifiers rather than a word list, so it needs no
##          maintenance and an answering agent cannot phrase around it. A trailing `_` still
##          matches when the next character is punctuation or space, and correctly fails when the
##          PRECEDING character is a word character — which is exactly the distinction the mark
##          asks about. `::` and `.` are not word characters, so qualified and dotted names work
##          unchanged.
## @param answer Answer markdown.
## @param symbol Declared symbol.
## @return True when the symbol appears as a whole identifier.
## @version 1
def _names_symbol(answer: str, symbol: str) -> bool:
    """@brief Whole-identifier symbol match. @return True when named as itself. @version 1"""
    return re.search(rf"(?<![A-Za-z0-9_]){re.escape(symbol)}(?![A-Za-z0-9_])", answer) is not None


## @brief Classify a mark's symbols against the answer text.
## @param mark Rubric mark.
## @param answer Answer markdown.
## @param result Result record to populate.
## @version 2
def _match_symbols(mark: Mark, answer: str, result: ObjectiveResult) -> None:
    """A qualified symbol counts as WEAK when the answer names the member and
    the class separately but never the qualified form — common in prose, and
    real evidence, but not the same as citing the symbol.

    @brief Score a mark's symbols.
    @version 2
    """
    for symbol in mark.symbols:
        if _names_symbol(answer, symbol):
            result.symbols_hit.append(symbol)
            result.evidence.append(f"symbol `{symbol}` — {_quote(answer, symbol)}")
        elif "::" in symbol and _co_located(answer, symbol):
            result.symbols_weak.append(symbol)
            result.evidence.append(
                f"symbol `{symbol}` (unqualified) — {_co_located(answer, symbol)}"
            )
        else:
            result.symbols_missed.append(symbol)


## @brief Resolve a rubric citation target against the answer's citation index.
## @param cites Answer citation index.
## @param name Basename, or an extension-agnostic `<Stem>.*`.
## @return Matching cited ranges (possibly across several extensions).
## @version 1
def _lookup(cites: dict[str, list[tuple[int, int]]], name: str) -> list[tuple[int, int]]:
    """A `<Stem>.*` target comes from a rubric mark that named a class but no
    file, so a citation in either the header or the translation unit counts.

    @brief Look up a citation target, tolerating an unspecified extension.
    @return Cited ranges.
    @version 1
    """
    if not name.endswith(".*"):
        return cites.get(name, [])
    stem = name[:-2]
    return [rng for key, ranges in cites.items() if Path(key).stem == stem for rng in ranges]


## @brief Whether the answer named this file at all, with or without a line.
## @param cites Answer citation index.
## @param name Declared file name, possibly `<Stem>.*`.
## @return True when the answer mentions the file.
## @version 1
## @dg_internal
def _names_file(cites: dict[str, list[tuple[int, int]]], name: str) -> bool:
    """PRESENCE, NOT TRUTHINESS. A file named without a line is recorded with an EMPTY range list,
    so `if cites.get(name)` is False for a file the answer plainly cited — which is what made every
    whole-file ref report as missed until a test caught it.

    @brief Test whether a file appears in the answer's citations.
    @return True when named.
    @version 1
    """
    if not name.endswith(".*"):
        return name in cites
    stem = name[:-2]
    return any(Path(key).stem == stem for key in cites)


## @brief Classify a mark's file:line citations against the answer's citations.
## @param mark Rubric mark.
## @param cites Answer citation index.
## @param drift Permitted line drift.
## @param result Result record to populate.
## @version 1
def _match_refs(
    mark: Mark, cites: dict[str, list[tuple[int, int]]], drift: int, result: ObjectiveResult
) -> None:
    """@brief Score a mark's citations with line-drift tolerance.
    @version 1
    """
    for name, lo, hi in mark.refs:
        label = f"{name}:{lo}" + (f"-{hi}" if hi != lo else "")
        found = _lookup(cites, name)
        ## A WHOLE-FILE CITATION (lines 0,0) MATCHES ON THE FILE BEING NAMED, and this is the half
        ## of gh#431 the parser could not supply alone. `_refs` used to require a line number, so a
        ## mark whose entire evidence is a PATH extracted nothing and went to the LLM judge — Q1 #6
        ## scored MISS with quote NONE while the answer named the file. Accepting the `[path]` form
        ## in the parser and then failing it here would have moved the defect rather than fixed it,
        ## invisibly: a declared ref that can never match reads exactly like an answer that never
        ## cited the file.
        ##
        ## TESTED FOR PRESENCE, NOT TRUTHINESS, and getting that wrong is why this branch sits
        ## ABOVE the missing-file check. `answer_citations` records a named-but-unlined file with an
        ## EMPTY range list, so `if not found` fired first and reported every whole-file ref as
        ## missed — the empty-list-is-falsy trap, caught by the test rather than by reading.
        if lo == 0 and hi == 0:
            if _names_file(cites, name):
                result.refs_hit.append(name)
                result.evidence.append(f"cite {name}: file named (whole-file citation)")
            else:
                result.refs_missed.append(label)
            continue
        if not found:
            result.refs_missed.append(label)
            continue
        overlap = [c for c in found if c[0] - drift <= hi and c[1] + drift >= lo]
        if overlap:
            result.refs_hit.append(label)
            result.evidence.append(f"cite {label} ≈ answer {name}:{overlap[0][0]}-{overlap[0][1]}")
        else:
            result.refs_file_only.append(label)
            result.evidence.append(f"cite {label}: file named, lines {found} do not overlap")


## @brief Decide the objective verdict from the matched evidence.
## @param mark Rubric mark.
## @param result Populated result record.
## @return "HIT", "MISS" or "n/a".
## @version 2
def _decide(mark: Mark, result: ObjectiveResult) -> str:
    """A mark naming nothing checkable returns `n/a` so the caller routes it to
    the judge rather than recording an unearned MISS.

    NO PARTIAL (owner, 2026-08-13: a mark is a mark). This branch used to return PARTIAL
    whenever ANY evidence matched, and both PARTIAL and MISS route to the judge identically —
    `grade_mark` judges anything that is not HIT — so the distinction never changed which
    marks were escalated. It only changed the arithmetic, by 0.5 per mark, on a path no test
    read. Partial evidence is still RECORDED in `symbols_weak` / `refs_file_only` for a human
    overturning a grade; it just no longer earns a fraction of one.

    @brief Reduce matched evidence to a verdict.
    @return Verdict token.
    @version 2
    """
    if mark.conceptual:
        return "n/a"
    ## `require` AND `min_matches` ARE READ HERE, and until they were the whole YAML migration was
    ## cosmetic — a threshold declared and ignored is the accepted-but-unread defect this project
    ## keeps finding one level down (`key_arg_idx` for `key_arg_index` keying a dataflow off
    ## argument 0). Both default to the old any-of behaviour, so nothing moves for a mark that
    ## states no threshold.
    ##
    ## WHY ANY-OF WAS WRONG WHERE A MARK SAYS OTHERWISE, measured against a deliberately wrong
    ## four-line answer: Q1 #29 lists SEVEN headers and says "at least TWO", and HIT on one. Q10 #5
    ## is about two DISTINCT objects sharing a name and HIT on either. An any-of scorer cannot
    ## express either mark, and the mark's own text was the only place the threshold lived.
    threshold = mark.min_matches or (
        len(mark.symbols) + len(mark.refs) if mark.require == "all" else 1
    )
    matched = len(result.symbols_hit) + len(result.refs_hit)
    declared = len(mark.symbols) + len(mark.refs)
    if mark.min_matches or mark.require == "all":
        ## A THRESHOLD IS OVER ALL DECLARED EVIDENCE, symbols and refs together, because a mark
        ## saying "at least two of these seven headers" does not care which KIND of evidence names
        ## them — Q1 #29's seven are refs, and two of the seven yielded no symbol at all under the
        ## old regex, so a symbols-only threshold would have been unsatisfiable by them.
        return "HIT" if matched >= min(threshold, declared) else "MISS"
    sym_ok = bool(result.symbols_hit) or not mark.symbols
    ref_ok = bool(result.refs_hit) or not mark.refs
    return "HIT" if sym_ok and ref_ok else "MISS"


## @brief Score one mark objectively against one answer.
## @param mark Rubric mark.
## @param answer Answer markdown.
## @param cites Pre-computed answer citation index.
## @param drift Permitted line drift.
## @return ObjectiveResult.
## @version 1
def score_mark(
    mark: Mark, answer: str, cites: dict[str, list[tuple[int, int]]], drift: int = DEFAULT_DRIFT
) -> ObjectiveResult:
    """@brief Run the objective pass for a single mark.
    @return Objective result with evidence.
    @version 1
    """
    result = ObjectiveResult()
    _match_symbols(mark, answer, result)
    _match_refs(mark, cites, drift, result)
    result.verdict = _decide(mark, result)
    return result
