## @brief Parser for the acceptance-matrix rubric (marks only).
## @version 1
"""Read the committed matrix markdown and expose its grading key as data.

The rubric is **frozen**: this module only reads it. Nothing here may rewrite,
normalise-away or hand-copy a mark — the single source of truth stays the
committed markdown (`acceptance/targets/<target>/questions.md`), so a grader
run always reflects the committed key.

Each mark is decomposed into the *objective* evidence it names — symbols and
`file:line` citations — so a string-matching pass can settle the marks that a
string match CAN settle, and only the genuinely conceptual ones ("states that
the key write IS the dispatch") are pushed to an LLM judge.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_Q_HEADING = re.compile(r"^#\s+(Q\d+)\s*[—–-]\s*(.+?)\s*$")
_SECTION = re.compile(r"^#{2,3}\s+(Marks)\b", re.IGNORECASE)
_BULLET = re.compile(r"^-\s*(?:\[[ xX]\]|☐)\s*(.*)$")

REPO_ROOT = Path(__file__).resolve().parents[2]

## Front matter is delimited by `---` lines and read with a deliberately narrow parser: a
## TOP-LEVEL `key: value` only, column 0, no nesting. The rubrics wrap long values across
## indented continuation lines and carry a `changelog:` list, and a full YAML load would
## turn those into structures nothing here wants. The only field any guard reads is a bare
## integer, so the parser is scoped to what a guard can act on.
_FRONT_MATTER_KEY = re.compile(r"^([a-z][a-z0-9_]*):\s*(.*)$")
_FENCE = "---"

## A file citation: `TelemetryDecoders.cpp:509` or `MopFsm.cpp:211-214`.
_FILE_REF = re.compile(r"([A-Za-z0-9_./-]+\.(?:cpp|hpp|h|cc|c|yaml|toml|md)):(\d+)(?:-(\d+))?")
## A bare line citation `:511-512`, which inherits the last-named file.
## `Broker::fan:45` and a standalone `:52` both count; a digit before the colon
## would mean we are inside a citation the file-ref pass already owns.
_BARE_REF = re.compile(r"(?<![\d.]):(\d+)(?:-(\d+))?\b")
_BACKTICK = re.compile(r"`([^`]+)`")
_SYMBOL = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:::[~A-Za-z_][A-Za-z0-9_]*)*")

## Marks the rubric fences off as unreachable by one arm.
##
## TWO DIRECTIONS, and for a long time only one existed. `raw-arm-only` fences a mark the DB
## arm cannot reach. Every fence a real matrix actually needed pointed the OTHER way — marks the
## RAW arm cannot reach, because a grep cannot compute an edge-confidence share or walk a lock
## nesting. One matrix said so in its own fairness notes and said the correction "must be
## applied by hand"; nobody applied it, and a published result understated the raw arm by 4
## points as a result.
##
## Hand-application is not a mechanism, it is a hope. Both directions are now parsed, so a
## fenced mark is EXCLUDED from the arm that cannot reach it rather than scored zero.
##
## FENCING IS NOW A RUBRIC DEFECT, NOT A FEATURE (owner, 2026-08-07). A rubric grades
## understanding of the TARGET REPOSITORY, and both arms answer the same questions against the
## same source-derived truth; a mark only one arm can reach is a solo exam, not a comparison.
## The parser keeps both directions because old results must stay re-gradable and because a
## silent fence is worse than a counted one — `grade_matrix.fencing_summary` exists so a
## non-zero count is visible. A new rubric should produce zero.
_ARM_ONLY = re.compile(r"raw-arm-only|do NOT penalise the db arm", re.IGNORECASE)
_DB_ONLY = re.compile(
    r"db-arm-only|structurally db-arm-only|do NOT penalise the raw arm", re.IGNORECASE
)


## @brief The ONLY arm that can reach this mark, when the rubric fences it.
## @param text The mark's text.
## @return "raw" when only the raw arm can reach it, "db" when only the db arm can, else "".
## @version 1
def _fenced_arm(text: str) -> str:
    """THE FIELD NAMES THE ARM THAT *CAN*, not the one that cannot — `raw-arm-only` means
    only the raw arm can reach the mark. That reading is inherited, and it is easy to invert
    when adding the second direction: the first draft of this function documented the
    opposite and printed "fenced from the DB arm" about a mark only the DB arm can reach.
    A grader acting on that would have excluded exactly the wrong arm.

    Order matters only if a mark claims both, which would be a rubric bug rather than a case
    to resolve silently — `raw` wins and the contradiction stays visible in the text.

    @brief Classify a mark's arm fence.
    @return "raw", "db", or "".
    @version 1
    """
    if _ARM_ONLY.search(text):
        return "raw"
    return "db" if _DB_ONLY.search(text) else ""


## The ONE translation between the rubric's arm vocabulary and the harness's. The rubric writes
## `raw`/`db`; the harness writes `src`/`mcp`. It lived inline in `grade_matrix.summarise` with a
## comment warning that comparing the two vocabularies directly "is wrong in a way that looks
## right" — a naive `!=` once fenced the db arm out of its OWN marks. A second consumer arrived
## (`run_matrix.plan_cells`, which must not schedule a cell whose every mark is fenced against
## its arm), so the mapping is named here rather than copied into the place the comment predicts
## it will be inverted.
_HARNESS_TO_RUBRIC_ARM = {"src": "raw", "mcp": "db"}


## @brief The rubric-vocabulary fence name that a harness arm CAN reach.
## @param arm Harness arm name (`src` / `mcp`), or a rubric name already.
## @return The rubric fence token this arm can reach.
## @version 1
def reachable_fence(arm: str) -> str:
    """NAMES THE ARM THAT *CAN*, matching `_fenced_arm`'s inherited reading. Passing a rubric
    token straight through means a caller that already speaks `raw`/`db` is not silently
    remapped to nothing, which would fence every mark out and read as "this arm has no exam".

    @brief Map a harness arm to the fence it can reach.
    @return Rubric fence token.
    @version 1
    """
    return _HARNESS_TO_RUBRIC_ARM.get(arm, arm)


## @brief How many of a question's marks are on one arm's exam.
## @param marks The question's marks.
## @param arm Harness arm name.
## @return Count of marks this arm can reach.
## @version 1
def marks_on_the_exam(marks: list, arm: str) -> int:
    """A QUESTION EVERY MARK OF WHICH IS FENCED AGAINST AN ARM IS NOT THAT ARM'S QUESTION. mbedtls
    Q0 is the live case: all 9 marks carry `[db-arm-only]`, so a source-arm Q0 cell spends a full
    cell of session capacity to be graded against zero marks — and its tokens and wall time land
    in the source arm's means, skewing a cost comparison with a question that is never compared.

    @brief Count the marks an arm can reach.
    @return Reachable mark count.
    @version 1
    """
    reachable = reachable_fence(arm)
    return sum(1 for mark in marks if not mark.arm_only or mark.arm_only == reachable)


## @brief One rubric mark with its extracted objective evidence.
## @version 1
@dataclass
class Mark:
    """A single `- ☐ ...` checklist item.

    @brief Rubric mark record.
    @version 1
    """

    index: int
    text: str
    arm_only: str = ""  ## e.g. "raw" when the rubric fences the mark off
    symbols: list[str] = field(default_factory=list)
    refs: list[tuple[str, int, int]] = field(default_factory=list)  ## (basename, lo, hi)
    ## HOW MANY declared symbols must appear: `any` (the current behaviour, and the default so the
    ## migration moves no score) or `all`. A mark saying "names at least TWO of them" means `all`
    ## and scored on one — Q1 #29 lists seven headers and HITs on any single one, while two of the
    ## seven yield no symbol at all. Only a YAML rubric can set this; markdown cannot express it,
    ## which is half the reason for the migration.
    require: str = "any"
    ## HOW MANY pieces of declared evidence must match when the mark states a threshold. 0 means
    ## `require` decides alone. Q1 #29 is why it exists: it says "seven public headers carry such a
    ## member, or names at least TWO of them" and lists all seven — so `any` lets one satisfy a
    ## mark whose own text asks for two, and `all` would demand seven the text does not. A
    ## threshold written in prose is a threshold the scorer cannot read.
    min_matches: int = 0
    ## Whether this mark may be handed to the D3 falsity veto as an established FACT. Default
    ## False, fail-closed: `grade_answer` fed the veto every mark text, and an audit of all 173
    ## found one outright false (Q3 #18), one contradicting `evidence.md` (Q1 #27) and about
    ## fourteen that are grading instructions rather than claims about the target. Fed a false
    ## fact the veto INVERTS and zeroes the more accurate answer, which is why `VETO_SAMPLES` is
    ## 0 until the marks carry this.
    veto_safe: bool = False

    ## @brief Whether the mark names no machine-checkable evidence.
    ## @return True when only an LLM judge can settle it.
    ## @version 1
    @property
    def conceptual(self) -> bool:
        """@brief True when the mark carries neither a symbol nor a citation.
        @version 1
        """
        return not self.symbols and not self.refs


## @brief One question's slice of the frozen grading key.
## @version 1
@dataclass
class QuestionRubric:
    """The marks for one question.

    @brief Per-question rubric record.
    @version 1
    """

    qid: str
    title: str
    marks: list[Mark] = field(default_factory=list)
    declared_mark_count: int = 0


## @brief Split a rubric bullet block into whole bullets, re-joining wrapped lines.
## @param lines Raw lines of one `### ...` section.
## @return List of single-string bullet texts.
## @version 1
def _bullets(lines: list[str]) -> list[str]:
    """Continuation lines (indented, or simply not a new bullet) belong to the
    preceding item — several marks wrap across three lines.

    @brief Re-join wrapped checklist bullets.
    @return Bullet texts.
    @version 1
    """
    out: list[str] = []
    for line in lines:
        bullet = _BULLET.match(line.strip())
        if bullet:
            out.append(bullet.group(1).strip())
        elif out and line.strip():
            out[-1] = f"{out[-1]} {line.strip()}"
    return out


## @brief Extract the symbols a mark names.
## @param text Mark text.
## @return De-duplicated symbol list.
## @version 1
def _symbols(text: str) -> list[str]:
    """Only backticked tokens count, and only ones that *look* like code — a
    qualified name, an underscore, or interior capitalisation. That excludes
    prose-in-backticks ("`fan`") which would match almost any answer.

    @brief Pull code-like symbols out of a mark.
    @return Symbol list.
    @version 1
    """
    found: list[str] = []
    for chunk in _BACKTICK.findall(text):
        cleaned = _FILE_REF.sub(" ", chunk)
        for token in _SYMBOL.findall(cleaned):
            interesting = "::" in token or "_" in token or token[1:] != token[1:].lower()
            if interesting and len(token) >= 4 and token not in found:
                found.append(token)
    return found


## @brief Extract the (file, line-range) citations a mark names.
## @param text Mark text.
## @return List of (basename, lo, hi) tuples.
## @version 1
def _refs(text: str) -> list[tuple[str, int, int]]:
    """Bare `:NNN` citations inherit the nearest preceding context, matching how
    the rubric is written. That context is either an explicitly named file
    (`BatteryFsm.cpp:49` ... `:52`) or, where the mark names no file at all
    (`BatteryGateReactor::on_key:143`), the qualified symbol's class — recorded
    as the extension-agnostic stem `BatteryGateReactor.*` because the rubric
    does not say whether the line is in the .cpp or the .hpp.

    @brief Pull file:line citations out of a mark.
    @return Citation list.
    @version 1
    """
    events: list[tuple[int, str, int, int]] = []
    for match in _FILE_REF.finditer(text):
        lo = int(match.group(2))
        events.append((match.start(), Path(match.group(1)).name, lo, int(match.group(3) or lo)))
    events += [(pos, stem, -1, -1) for pos, stem in _class_contexts(text)]
    spans = [(m.start(), m.end()) for m in _FILE_REF.finditer(text)]
    for match in _BARE_REF.finditer(text):
        if any(start <= match.start() < end for start, end in spans):
            continue
        lo = int(match.group(1))
        events.append((match.start(), "", lo, int(match.group(2) or lo)))
    return _attach_files(sorted(events))


## @brief Locate the class stems that can serve as a bare-line file context.
## @param text Mark text.
## @return List of (position, "<Class>.*") tuples.
## @version 1
def _class_contexts(text: str) -> list[tuple[int, str]]:
    """@brief Find qualified-symbol class names usable as a file context.
    @return Positioned class stems.
    @version 1
    """
    out: list[tuple[int, str]] = []
    for match in _BACKTICK.finditer(text):
        for symbol in _SYMBOL.finditer(match.group(1)):
            head = symbol.group(0).split("::")[0]
            if "::" in symbol.group(0) and head[:1].isupper():
                out.append((match.start() + symbol.start(), f"{head}.*"))
    return out


## @brief Resolve bare line citations against the preceding named file.
## @param events Position-sorted (pos, file, lo, hi) tuples.
## @return Citations with a resolved basename (unresolvable ones dropped).
## @version 1
def _attach_files(events: list[tuple[int, str, int, int]]) -> list[tuple[str, int, int]]:
    """@brief Give every bare `:NNN` the file that precedes it.
    @return Resolved citation list.
    @version 1
    """
    out: list[tuple[str, int, int]] = []
    current = ""
    for _pos, name, lo, hi in events:
        current = name or current
        if lo < 0:  ## a context marker (class stem), not a citation of its own
            continue
        if current and (current, lo, hi) not in out:
            out.append((current, lo, hi))
    return out


## @brief Build a Mark from one bullet of the frozen key.
## @param index 1-based position within its section.
## @param text Bullet text.
## @return Populated Mark.
## @version 2
def _make_mark(index: int, text: str) -> Mark:
    """@brief Decompose a bullet into evidence + flags.
    @return Mark record.
    @version 2
    """
    return Mark(
        index=index,
        text=text,
        arm_only=_fenced_arm(text),
        symbols=_symbols(text),
        refs=_refs(text),
    )


## @brief Group a matrix file's lines into (qid, section, lines) blocks.
## @param path Matrix markdown path.
## @return Mapping qid -> {title, sections}.
## @version 1
def _blocks(path: Path) -> dict[str, dict]:
    """@brief Slice the markdown into per-question, per-section line blocks.
    @return Nested block mapping.
    @version 1
    """
    blocks: dict[str, dict] = {}
    qid = ""
    section = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        heading = _Q_HEADING.match(line)
        if heading:
            qid, section = heading.group(1), ""
            blocks[qid] = {"title": heading.group(2), "sections": {}}
            continue
        if not qid:
            continue
        found = _SECTION.match(line)
        if found:
            section = found.group(1).lower()
            blocks[qid]["sections"].setdefault(section, [])
            blocks[qid]["sections"][section] = [line]
            continue
        if line.startswith("#") or line.startswith("---"):
            section = ""
            continue
        if section:
            blocks[qid]["sections"][section].append(line)
    return blocks


## @brief Parse the frozen rubric out of the committed matrix markdown.
## @param path Matrix markdown path.
## @return Mapping qid -> QuestionRubric.
## @version 1
def parse_rubric(path: Path) -> dict[str, QuestionRubric]:
    """The declared mark count in `### Marks (N)` is captured too, so a caller
    can assert the parse against the rubric's own arithmetic instead of
    trusting this regex.

    @brief Read the marks for every question.
    @return Rubric mapping.
    @version 1
    """
    rubrics: dict[str, QuestionRubric] = {}
    for qid, block in _blocks(path).items():
        sections = block["sections"]
        rubric = QuestionRubric(qid=qid, title=block["title"])
        header = (sections.get("marks") or [""])[0]
        count = re.search(r"\((\d+)\)", header)
        rubric.declared_mark_count = int(count.group(1)) if count else 0
        for i, text in enumerate(_bullets(sections.get("marks", [])[1:]), 1):
            rubric.marks.append(_make_mark(i, text))
        if rubric.marks:
            rubrics[qid] = rubric
    return rubrics


## @brief Read the top-level `key: value` front matter of a rubric markdown file.
## @param path Rubric markdown path.
## @return Mapping of top-level key to raw string value (empty when there is no front matter).
## @version 1
def front_matter(path: Path) -> dict[str, str]:
    """The opening fence must be the FIRST LINE THAT IS NOT BLANK AND NOT AN HTML COMMENT (the
    rubrics open with an SPDX comment), because `---` is also a markdown horizontal rule and
    the rubrics contain several. Scanning for any `---` opens a phantom front-matter block in
    the middle of a question and hands a guard values read out of prose — the failure mode
    where a check reads the wrong input and reports something rather than nothing. A
    first-five-lines window was tried and was not enough: a rule after a heading and two lines
    of prose still landed inside it.

    Values are raw strings, unparsed. Nested and wrapped continuation lines are IGNORED
    rather than half-parsed: every consumer here wants a scalar, and a half-parsed structure
    is the kind of thing that reads as present while meaning nothing.

    @brief Parse a rubric's front matter into flat strings.
    @return Front-matter mapping.
    @version 1
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    lead = next(
        (i for i, line in enumerate(lines) if line.strip() and not line.startswith("<!--")), None
    )
    if lead is None or lines[lead].strip() != _FENCE:
        return {}
    out: dict[str, str] = {}
    for line in lines[lead + 1 :]:
        if line.strip() == _FENCE:
            break
        found = _FRONT_MATTER_KEY.match(line)
        if found:
            out[found.group(1)] = found.group(2).strip()
    return out


## @brief The pipeline's current build version, read from the package rather than copied.
## @return CLEW_BUILD_VERSION.
## @version 1
def current_build_version() -> int:
    """READ, NEVER COPIED. A version number transcribed into a second place is stale the next
    time it is bumped, which is the documented failure that put "now 5" in a project file
    through five bumps. The import is deferred so a caller that only wants the rubric PARSER
    does not need the package importable.

    @brief Read the pipeline build version from `clew.signature`.
    @return Current build version.
    @version 1
    """
    import sys

    sys.path.insert(0, str(REPO_ROOT))
    from clew.signature import CLEW_BUILD_VERSION

    return CLEW_BUILD_VERSION


## @brief Front-matter key naming where a rubric's figures were read FROM.
SOURCE_PROVENANCE_KEY = "ground_truth_source"
## Front-matter keys naming the pipeline build a rubric's figures were measured AT. Two
## spellings exist in committed rubrics and both are read, because a guard that knows one
## spelling reports "undeclared" for a rubric that declared it — the disarmed-gate shape.
BUILD_PROVENANCE_KEYS = ("ground_truth_build_version", "build_version")
## What `preflight_rubric_provenance` returns for a source-derived key.
PROVENANCE_SOURCE = "source"


## @brief Refuse a rubric whose ground truth is unattributed or measured at another build.
## @param path Rubric markdown to check.
## @param current Pipeline build version to compare against; read from the package if None.
## @return `PROVENANCE_SOURCE`, or the build version the rubric declares.
## @version 1
def preflight_rubric_provenance(path: Path, current: int | None = None) -> str | int:
    """THE SUCCESSOR TO `preflight_rubric_build_version`, WHICH WAS DELETED FOR A REASON THIS
    HAS TO ENCODE. That guard demanded every rubric declare the build its figures were measured
    at, because on 2026-08-05 both committed keys held ground truth from build 16/17 while the
    pipeline was at 27 — and the skew is ONE-DIRECTIONAL, so a stale key can only penalise the
    arm under test. The lesson stands.

    What changed is the better answer: mbedtls 1.0.0 derives every figure from the TARGET'S OWN
    SOURCE, read with git grep at a pinned commit, and declares that as `ground_truth_source`.
    Such a key cannot drift when our pipeline moves, because no figure in it came from our
    pipeline. Re-demanding a build version from it would refuse the one rubric that fixed the
    problem — so this guard asks for PROVENANCE and accepts either form.

    FAILS CLOSED ON NEITHER, which is the state both keys were in while nothing read the field:
    an unattributed key is unfalsifiable rather than fine, and "no declaration" must never be
    the quiet pass.

    THE TWO BUILD SPELLINGS ARE BOTH READ deliberately. `entropic/questions.md` says
    `build_version:` and the deleted guard's tests said `ground_truth_build_version:`; knowing
    one and not the other would report a declared provenance as absent, which is worse than
    not checking — it sends the reader to add a field that is already there.

    @brief Check a rubric declares where its ground truth came from, and that it still holds.
    @return The provenance: `PROVENANCE_SOURCE`, or the declared build version.
    @version 1
    """
    ## FORMAT-AGNOSTIC (P2). `front_matter` reads a markdown `---` fence and returns {} for a
    ## YAML rubric — so pointing this guard at `questions.yaml` would have found NEITHER
    ## provenance key and refused the one rubric that fixed the provenance problem, which is
    ## precisely the failure the guard's own docstring records about its deleted predecessor.
    front = rubric_front_matter(path)
    if front.get(SOURCE_PROVENANCE_KEY):
        return PROVENANCE_SOURCE
    declared = next((front[k] for k in BUILD_PROVENANCE_KEYS if front.get(k)), None)
    if declared is None:
        raise SystemExit(
            f"preflight: UNATTRIBUTED GRADING KEY — {path}\n"
            f"  It declares no `{SOURCE_PROVENANCE_KEY}` and no "
            f"`{BUILD_PROVENANCE_KEYS[0]}`, so nothing says where its figures came from.\n"
            "  A key measured against an older pipeline marks the index arm wrong for being "
            "right, and the drift is one-directional — the source arm reads an unmoved tree.\n"
            f"  Declare `{SOURCE_PROVENANCE_KEY}:` if every figure was read from the target's "
            f"own source, or `{BUILD_PROVENANCE_KEYS[0]}:` if any figure came from a build of "
            "ours."
        )
    expected = current_build_version() if current is None else current
    if int(declared) != int(expected):
        raise SystemExit(
            f"preflight: STALE GRADING KEY — refusing to grade against it.\n"
            f"  rubric ground truth measured at build : {declared}\n"
            f"  CLEW_BUILD_VERSION            : {expected}\n"
            f"  rubric: {path}\n"
            "  Re-measure the figures at the current build, or re-derive them from the "
            f"target's source and declare `{SOURCE_PROVENANCE_KEY}:` instead, which cannot "
            "drift when our pipeline moves."
        )
    return int(declared)


## ─────────────────────────────────────────────────────────────────────────────
## THE YAML RUBRIC (P2). Markdown stays readable; YAML makes the grading key DATA.
## ─────────────────────────────────────────────────────────────────────────────
##
## WHY MIGRATE AT ALL, since the markdown parses cleanly today. Three reasons, each measured:
##
## 1. THE EVIDENCE IS GUESSED FROM PROSE. `_symbols` accepts a backticked token containing `::`,
##    `_` or an interior capital, and `_refs` needs a line number — so whether a mark is
##    machine-checkable is decided by its PUNCTUATION. Q1 #6's whole evidence is the path
##    `include/mbedtls/threading.h`, which yields no symbol and no ref, so it went to the LLM
##    judge and scored MISS with quote NONE — while the graded answer's line 8 reads "declared
##    `extern` in `include/mbedtls/threading.h:111-114`", the very line the judge quoted to award
##    a DIFFERENT mark. A machine-checkable fact lost to a judge miss.
##
## 2. A JUNK TOKEN AWARDS THE MARK UNSEEN. `bench_score._decide` sets `sym_ok` from ANY one
##    extracted symbol and `grade_matrix` only calls the judge when the objective pass is not
##    HIT. Reproduced against a deliberately wrong four-line answer: Q9 #3 HITs on the substring
##    `mbedtls_`, Q2 #3 on `private_`, Q10 #6 and #7 on `global_data`. Nobody would WRITE
##    `mbedtls_` as a mark's evidence; the regex invented it.
##
## 3. THE ONLY INTEGRITY CHECK IS BLIND TO TEXT POLLUTION. Declared-vs-parsed count is all there
##    is, and at 6d54ed5 four Q1 mark texts had bold headings absorbed into them ("...as an
##    oddity **The bindings**") while the checker printed 31/31 [OK] throughout. In YAML a mark's
##    text is a scalar with explicit boundaries and a heading cannot leak into it.
##
## DERIVATION HAPPENS ONCE, IN THE CONVERTER, AND IS THEN FROZEN AS DATA. The YAML reader reads
## only what is DECLARED — it never falls back to the regexes — so the migration cannot silently
## keep the guessing. The converter writes the derived symbols and refs explicitly, which is what
## lets the equivalence gate compare the two readers mark for mark.

## The YAML keys a mark may carry. A DOCUMENT-LEVEL allow-list for the same reason
## `declaration.KNOWN_SECTIONS` is one: a misspelled key parses to a valid mapping that no
## consumer reads, so `require: all` written as `requires: all` would silently score `any`.
MARK_KEYS = frozenset(
    {"text", "arm_only", "symbols", "refs", "require", "min_matches", "veto_safe"}
)

## The keys a question may carry, same rule.
QUESTION_KEYS = frozenset({"id", "title", "prompt", "marks"})

## How many of a mark's declared symbols must appear in an answer.
##
## `any` is the CURRENT behaviour and stays the default so the migration changes no score. `all`
## is what a mark saying "names at least TWO of them" actually means — Q1 #29 lists seven headers,
## says two, and HITs on one, while `entropy.h` and `rsa.h` yield no symbol at all because they
## are too short and lowercase-only for `_SYMBOL`. Expressing the threshold as DATA is the fix;
## `min` carries the number.
REQUIRE_MODES = ("any", "all")


## @brief Read a YAML rubric into the same QuestionRubric mapping the markdown reader returns.
## @param path Path to a `questions.yaml`.
## @return Mapping qid -> QuestionRubric.
## @version 1
def parse_rubric_yaml(path: Path) -> dict[str, QuestionRubric]:
    """READS ONLY WHAT IS DECLARED. No fallback to `_symbols` / `_refs`, deliberately: a reader
    that derived evidence when a mark omitted it would keep the punctuation-decides-checkability
    defect alive under a new file format, and nothing would show that it had.

    REFUSES AN UNKNOWN KEY rather than ignoring it, at both levels. This is the entry-level
    lesson this repo has recorded twice: a document-level slip is loud, and `requires: all` for
    `require: all` parses to a perfectly valid mapping that no consumer reads — so the mark would
    score `any` while its author believed otherwise.

    @brief Parse a YAML grading key.
    @return Rubric mapping.
    @version 1
    """
    import yaml

    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(document, dict):
        raise ValueError(f"{path}: a rubric must be a mapping, got {type(document).__name__}")
    rubrics: dict[str, QuestionRubric] = {}
    for entry in document.get("questions") or []:
        unknown = sorted(set(entry) - QUESTION_KEYS)
        if unknown:
            raise ValueError(
                f"{path}: question {entry.get('id')!r} names unknown key(s) {unknown} — "
                f"allowed: {', '.join(sorted(QUESTION_KEYS))}"
            )
        rubric = QuestionRubric(qid=entry["id"], title=entry.get("title", ""))
        for i, raw in enumerate(entry.get("marks") or [], 1):
            rubric.marks.append(_mark_from_yaml(path, entry["id"], i, raw))
        ## DERIVED, NEVER WRITTEN. The markdown carried `### Marks (N)` beside N bullets, so the
        ## two could disagree — and every count in the prose HAS disagreed at some point (the
        ## 98/89 figures survived a 108-mark atomisation). A list has one length.
        rubric.declared_mark_count = len(rubric.marks)
        if rubric.marks:
            rubrics[entry["id"]] = rubric
    return rubrics


## @brief Build one Mark from its YAML mapping, refusing anything unrecognised.
## @param path Rubric path, for the error message.
## @param qid Question id, for the error message.
## @param index 1-based position within the question.
## @param raw The mark's mapping.
## @return Mark record.
## @version 1
## @dg_internal
def _mark_from_yaml(path: Path, qid: str, index: int, raw: object) -> Mark:
    """`index` IS THE LIST POSITION and is never written in the file. A written index is a second
    source of truth that drifts the moment a mark is inserted, and this rubric's prose already
    demonstrates the failure: five sites still assert facts about "Q3:6" and "Q3:8" that the
    atomisation reassigned to unrelated marks.

    @brief Validate and build one mark.
    @return Mark.
    @version 1
    """
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: {qid} mark {index} must be a mapping, got {type(raw).__name__}")
    unknown = sorted(set(raw) - MARK_KEYS)
    if unknown:
        raise ValueError(
            f"{path}: {qid} mark {index} names unknown key(s) {unknown} — "
            f"allowed: {', '.join(sorted(MARK_KEYS))}. A misspelled key parses to a valid "
            f"mapping that nothing reads, so the mark would score on the default silently."
        )
    text = str(raw.get("text") or "").strip()
    if not text:
        raise ValueError(f"{path}: {qid} mark {index} has no text")
    mode = str(raw.get("require") or "any")
    if mode not in REQUIRE_MODES:
        raise ValueError(
            f"{path}: {qid} mark {index} has require={mode!r} — allowed: {REQUIRE_MODES}"
        )
    return Mark(
        index=index,
        text=text,
        arm_only=str(raw.get("arm_only") or ""),
        symbols=[str(s) for s in (raw.get("symbols") or [])],
        ## A REF IS A TRIPLE, and a 1-element form is accepted as a whole-file citation with no
        ## line — which is the gap that sent ~20 path-only marks to the LLM judge.
        refs=[_ref_from_yaml(path, qid, index, r) for r in (raw.get("refs") or [])],
        require=mode,
        min_matches=int(raw.get("min_matches") or 0),
        veto_safe=bool(raw.get("veto_safe") or False),
    )


## @brief Normalise one declared ref into the (basename, lo, hi) triple the scorer reads.
## @param path Rubric path, for the error message.
## @param qid Question id, for the error message.
## @param index Mark index, for the error message.
## @param raw The declared ref: [file], [file, line] or [file, lo, hi].
## @return (basename, lo, hi) with lo/hi 0 for a whole-file citation.
## @version 1
## @dg_internal
def _ref_from_yaml(path: Path, qid: str, index: int, raw: object) -> tuple[str, int, int]:
    """A WHOLE-FILE CITATION IS FIRST CLASS, which is the point of allowing a 1-element form.
    `_refs` required a line number, so a mark whose entire evidence is a PATH extracted nothing
    and was pushed to the judge: Q1 #6 scored MISS with quote NONE while the answer named the file
    on its line 8. Lines `0, 0` mean "this file, anywhere in it".

    @brief Validate and normalise a declared file citation.
    @return The (basename, lo, hi) triple.
    @version 1
    """
    if isinstance(raw, str):
        return (raw, 0, 0)
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ValueError(f"{path}: {qid} mark {index} has a malformed ref {raw!r}")
    name = str(raw[0])
    if len(raw) == 1:
        return (name, 0, 0)
    lo = int(raw[1])
    hi = int(raw[2]) if len(raw) > 2 else lo
    return (name, lo, hi)


## @brief Read a YAML rubric's question records, prompt text included.
## @param path Path to a `questions.yaml`.
## @return List of {id, title, text} records, in file order.
## @version 1
def parse_questions_yaml(path: Path) -> list[dict[str, str]]:
    """The counterpart to `run_matrix.parse_questions`, which recovered the prompt from a
    BLOCKQUOTE following the heading and stripped a `**Question (frozen).**` prefix. A YAML block
    scalar needs neither, so the prompt cannot be truncated by a blank line or absorb a stray
    quoted paragraph.

    @brief Read the frozen prompt for each question.
    @return Question records with non-empty prompts.
    @version 1
    """
    import yaml

    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: list[dict[str, str]] = []
    for entry in document.get("questions") or []:
        text = " ".join(str(entry.get("prompt") or "").split())
        if text:
            out.append({"id": entry["id"], "title": entry.get("title", ""), "text": text})
    return out


## @brief Read a rubric's provenance keys, whichever format it is in.
## @param path Rubric path (`.yaml` or `.md`).
## @return Mapping of top-level key to string value.
## @version 1
def rubric_front_matter(path: Path) -> dict[str, str]:
    """ONE ENTRY POINT so `preflight_rubric_provenance` does not have to know the format. Its
    fail-closed-on-neither-key rule is what matters and is unchanged.

    @brief Read front matter from a YAML or markdown rubric.
    @return Key -> value.
    @version 1
    """
    if path.suffix in (".yaml", ".yml"):
        import yaml

        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return {k: str(v) for k, v in document.items() if not isinstance(v, (list, dict))}
    return front_matter(path)


## @brief Read a rubric's marks, whichever format it is in.
## @param path Rubric path (`.yaml` or `.md`).
## @return Mapping qid -> QuestionRubric.
## @version 1
def load_rubric(path: Path) -> dict[str, QuestionRubric]:
    """THE DISPATCH, so every consumer takes one call and the two formats cannot diverge in how
    they are reached. Both readers return the same `QuestionRubric` shape, which is what makes the
    equivalence gate a comparison rather than a translation.

    @brief Parse a rubric in either format.
    @return Rubric mapping.
    @version 1
    """
    if path.suffix in (".yaml", ".yml"):
        return parse_rubric_yaml(path)
    return parse_rubric(path)


## @brief Compare a markdown rubric against its YAML translation, mark for mark.
## @param md Path to the markdown rubric.
## @param yml Path to the YAML rubric.
## @return None; raises AssertionError naming the first disagreement.
## @version 1
def assert_rubrics_equivalent(md: Path, yml: Path) -> None:
    """THE GATE THAT KEEPS MIGRATION AND CORRECTION SEPARABLE. The owner asked for both in one
    pass, which is fine — but without this a DROPPED mark is indistinguishable from a corrected
    one, and that exact confusion has already invalidated a grading run here: a `###` sub-header
    "fix" silently removed Q1-Q4 from the parse, the count check still printed [OK], and the whole
    pass was graded against 65 marks instead of 173.

    So the translation is asserted FIRST, before a single correction lands, and it compares text,
    count, fencing and question set — not a checksum, because a checksum says only that something
    moved and this has to say WHICH mark.

    IT COMPARES TEXT VERBATIM. Whitespace is normalised (a YAML block scalar wraps where the
    markdown bullet did not) and nothing else is, so a reworded mark is a failure here and has to
    be made after the gate passes, deliberately.

    @brief Assert a YAML rubric is a faithful translation of a markdown one.
    @return None.
    @version 1
    """
    from_md = parse_rubric(md)
    from_yaml = parse_rubric_yaml(yml)
    if set(from_md) != set(from_yaml):
        raise AssertionError(
            f"question sets differ: markdown has {sorted(set(from_md) - set(from_yaml))} "
            f"missing from YAML, YAML has {sorted(set(from_yaml) - set(from_md))} extra"
        )
    for qid in sorted(from_md):
        left, right = from_md[qid].marks, from_yaml[qid].marks
        if len(left) != len(right):
            raise AssertionError(
                f"{qid}: markdown has {len(left)} mark(s), YAML has {len(right)}. A dropped mark "
                f"and a corrected one are indistinguishable without this check."
            )
        for a, b in zip(left, right, strict=True):
            if " ".join(a.text.split()) != " ".join(b.text.split()):
                raise AssertionError(
                    f"{qid} mark {a.index} text differs.\n  markdown: {a.text!r}\n  yaml    : {b.text!r}"
                )
            if a.arm_only != b.arm_only:
                raise AssertionError(
                    f"{qid} mark {a.index} fencing differs: markdown {a.arm_only!r} vs "
                    f"yaml {b.arm_only!r} — a fence decides which ARM is eligible, so an "
                    f"inverted one scores an arm zero on marks it was never eligible for"
                )
