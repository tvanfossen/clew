## @brief Apply the audited corrections to a YAML rubric, each with a precondition.
## @version 2
"""Correct the grading key, one declared edit at a time, refusing on any surprise.

WHY A SCRIPT AND NOT SIXTY HAND EDITS. Every correction here carries the text it EXPECTS to
find, so a mark that has moved, been reworded or already been fixed fails loudly instead of
being silently overwritten — which is the same free correctness check `Edit`'s `old_string`
gives, applied to sixty of them at once. It is also re-runnable and reviewable: the list below
IS the changelog, and a reader can see what each correction asserts about the target.

WHAT MAKES A CORRECTION LEGITIMATE. Only three things: the mark is FALSE against the target's
source, it CONTRADICTS the committed `evidence.md`, or it cannot be SCORED as written (a
prohibition satisfiable by silence, a grading instruction masquerading as a fact, junk evidence
that awards it unseen). Rewording a mark because it reads awkwardly is not a correction and is
not done here — the questions are the specification.

EVERY FACTUAL CLAIM BELOW WAS RE-VERIFIED AGAINST THE TARGET, not taken from the audit that
found it. Two examples that mattered: `MBEDTLS_HAVE_TIME` is active at `mbedtls_config.h:131`
and `MBEDTLS_TIMING_ALT` is commented out at `:353`, which is what makes Q3 #18 false; and
`git grep -nE 'static +mbedtls_threading_mutex_t'` returns NOTHING, which is what makes
`debug_mutex` a true sixth global and Q1 #27's unqualified "FIVE" wrong.

Run:
    .venv/bin/python acceptance/bench/rubric_fix.py acceptance/targets/mbedtls/questions.yaml
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


## @brief One declared correction to one mark.
## @version 1
@dataclass(frozen=True)
class Fix:
    """`expect` is the precondition and it is a SUBSTRING, not the whole text: a mark's full
    prose is long and quoting it here would make this file a second copy of the rubric that
    drifts. A distinctive fragment is enough to prove the right mark was found and short enough
    to read.

    @brief A precondition-guarded mark edit.
    @version 1
    """

    qid: str
    index: int
    why: str
    expect: str
    ## The replacement text. None leaves the text alone (used when only evidence changes).
    text: str | None = None
    ## Declared evidence to set. None leaves it alone; [] clears it deliberately.
    symbols: list[str] | None = None
    refs: list[list] | None = None
    require: str | None = None
    ## How many declared evidence items must match, when the mark states a threshold in prose that
    ## `any`/`all` cannot express. Q1 #29's "at least TWO of them" over seven listed headers.
    min_matches: int | None = None
    veto_safe: bool | None = None
    ## Set when the mark is to be DELETED rather than edited.
    delete: bool = False


## Grader-only routing tokens that must NOT sit inside a mark's graded text.
##
## `[db-arm-only]` is a FENCE, and `arm_only` is the field that carries it. The markdown had no
## field, so a section-level "Every mark below is [db-arm-only]" was invisible to `_bullets` and
## the token got spliced into all nine Q0 marks — MID-SENTENCE, splitting noun phrases: mark 3
## read "behind conditional [db-arm-only] compilation". `grade_prompts.mark_prompt` renders the
## mark verbatim as a CHECKLIST ITEM, so a grader-only token was inside the text the judge reads
## and the answer is scored against. Now that the fence is a field, the token is redundant.
STRIP_TOKENS = ("[db-arm-only] ", " [db-arm-only]", "[db-arm-only]")


## ─────────────────────────────────────────────────────────────────────────────
## BATCH 2 — marks that CANNOT BE SCORED as written. A prohibition is satisfiable by SILENCE, so
## an answer that never raises the topic earns it and one that engages honestly can lose it; a
## grading rule written as a checklist item instructs a judge that has no source access and
## therefore defaults to HIT. Rule 8 forbids the first class outright. Where the substance is
## already covered by a sibling mark the entry is DELETED rather than reworded, because two marks
## grading one behaviour means one failure costs two points.
##
## THIS IS NOT STYLE EDITING. Every entry here is unscoreable or double-counted, not merely
## awkward — the questions are the specification and prose is left alone.
## ─────────────────────────────────────────────────────────────────────────────
## ─────────────────────────────────────────────────────────────────────────────
## BATCH 4 — ENUMERATE WHAT WOULD SATISFY AN OPEN MARK. A mark reading "names a concrete file" or
## "names at least one generated file and its generator" states a REQUIREMENT and no ANSWER KEY, and
## the judge has no source access: a plausible fabrication (`library/x509_verify.c`,
## `scripts/gen_tables.py`) reads exactly like the truth and defaults to HIT. Batch 2 removed the
## grading instructions a blind judge auto-passes; this batch closes the same hole one step over,
## where the mark is a legitimate open-ended requirement whose ACCEPTABLE SET was never written down.
##
## SO THESE ENTRIES DO CHANGE TEXT, unlike batch 3 — the acceptable set has to be inside the text the
## judge reads, not only in declared evidence, because a symbol list settles a HIT and can never
## settle a MISS on a name that is not in it.
##
## EVERY SET WAS ENUMERATED FROM THE TARGET AT THIS COMMIT, and two of them are wider than the
## obvious answer in ways that would have made a stricter mark punish a correct answer:
##
##   * Q8 #5 — the generator NAMED IN THE BANNER IS OFTEN NOT IN THIS CHECKOUT.
##     `library/ssl_debug_helpers_generated.c` credits `generate_ssl_debug_helpers.py` and
##     `tests/src/psa_test_wrappers.c` credits `generate_psa_wrappers.py`; NEITHER is tracked
##     (`git ls-files` returns nothing) because both live in the unpopulated `framework/` submodule
##     — the same submodule Q8's first four marks are about. And
##     `programs/psa/psa_constant_names_generated.c`'s banner says `generate_psa_constant.py` while
##     the tracked script is `scripts/generate_psa_constants.py`, PLURAL. So the mark accepts the
##     banner's spelling: quoting the file's own attribution is the correct method even when the
##     script it names cannot be opened here, and demanding a tracked path would fail a right answer.
##   * Q6 #2 — FOUR public entry points, not the two the prose implies:
##     `mbedtls_x509_crt_verify` (`include/mbedtls/x509_crt.h:3159`),
##     `_verify_with_profile` (`:3176`), `_verify_restartable` (`:3210`) and
##     `mbedtls_x509_crt_verify_with_ca_cb` (`library/x509_crt.c`, AST-recovered).
##
## Q7 #1 IS A DIFFERENT SHAPE and gets a method rather than a set: "the function is actually added"
## is a claim about the FILESYSTEM, which neither the judge nor the objective pass can inspect. The
## mark now grades the QUOTED definition, which is the most a transcript can carry — and says so,
## rather than leaving a judge to assume an unverifiable assertion.
##
## FOUR OF THESE ENTRIES DELIBERATELY DECLARE NO EVIDENCE, and the first draft of this batch got it
## wrong in exactly the way batch 3 existed to fix — caught by re-reading batch 3's own rule against
## it, and by confirming `_match_symbols` compares with `symbol in answer`, a SUBSTRING:
##
##   * A CONJUNCTION OF ALTERNATIVES IS NOT DECLARABLE. Q8 #5 wants a generated file AND its
##     generator, over six acceptable PAIRS; Q11 #5 wants the header AND the compile-time
##     consequence; Q7 #1 wants the name AND the quoted definition. `require: all` demands every
##     declared item (wrong — one pair suffices) and `require: any` settles a HIT on HALF the
##     requirement, which is the auto-HIT defect with a longer symbol list. So these three keep
##     empty evidence and are judge-settled, with the enumeration in the TEXT where the judge reads
##     it. The objective pass cannot express "one of these pairs, both halves", so it must not
##     pretend to.
##   * `heap` IS A JUNK TOKEN. Q10 #2's first draft declared it, and it matches "heap allocation",
##     "the heap", "heaps" — any answer discussing memory at all. It is dropped from the symbol list
##     and left to the text; the other three carriers (`mbedtls_calloc_func`, `mbedtls_free_func`,
##     `global_data`) are distinctive enough to declare.
## ─────────────────────────────────────────────────────────────────────────────
## ─────────────────────────────────────────────────────────────────────────────
## BATCH 5 — A MARK THAT GRADES ARRANGEMENT CANNOT BE SCORED, and as of the judge fix it is also
## a live contradiction: the judge is now instructed that "format and placement are not graded",
## so a mark asking it to grade placement asks for the one thing it is told to refuse.
##
## This is the third legitimate correction class — "cannot be SCORED as written" — not a rewording
## for taste. Q3 #8 asked for the library/samples distinction "as the substance of the answer, not
## as a caveat appended to it". The substance half is a real fact about mbedtls and stays; the
## arrangement half is not a fact about anything and goes.
##
## MEASURED, which is what makes it a defect rather than a preference: the graded answer's FIRST
## SENTENCE was "Yes — but only in the example programs, not in the core mbedtls library itself
## (crypto/x509/TLS code)" — the distinction, leading — and the judge conceded that and failed it
## on rhetorical arrangement anyway.
##
## Q0 #1 SURVIVES DELIBERATELY. It also grades order ("the coverage check comes FIRST"), and there
## the order IS the fact: Q0 asks whether the answer established its basis before making claims, so
## sequence is the subject of the question rather than the presentation of an answer to it. The two
## look alike and are not the same, which is exactly why this is a per-mark correction and not a
## sweep for a phrase.
## ─────────────────────────────────────────────────────────────────────────────
## ─────────────────────────────────────────────────────────────────────────────
## BATCH 6 — A COUNT CANNOT BE SETTLED BY A SYMBOL, and declaring one hands the mark away.
##
## Q2 #18 asks for a FIGURE ("about 884 lines in 71 files, or 879 in 70") and declared
## `symbols: ['MBEDTLS_PRIVATE']` — a token every answer to this question contains. `_decide`
## scores an objective HIT on it and `grade_matrix` then SKIPS THE JUDGE, so the mark is awarded
## without anything ever reading whether a number was stated.
##
## MEASURED on p5-both: both arms scored HIT and NEITHER ANSWER CONTAINS ANY COUNT. The recorded
## evidence for the src arm is `symbol MBEDTLS_PRIVATE — "**The macro:** MBEDTLS_PRIVATE, defined
## in include/mbedtls/private_access.h:15"` — a definition line, credited as a census.
##
## THIS IS THE AUTO-HIT CLASS AGAIN, one batch after batch 3 removed six of them and batch 4
## reintroduced and then removed a seventh. The shape is stable enough to state as a rule:
## DECLARED EVIDENCE MUST BE ABLE TO DISCRIMINATE. A symbol that appears in every plausible answer
## discriminates nothing, and a mark whose substance is a NUMBER cannot be settled by a NAME at
## all — no symbol or ref can, so the evidence is cleared and the judge settles it.
##
## It matters more than one mark: #18 is the mark the whole usage-census gap (#437) turns on, so a
## free HIT here hides the one place the index arm is known to be incapable.
## ─────────────────────────────────────────────────────────────────────────────
FIXES: list[Fix] = [
    Fix(
        qid="Q2",
        index=18,
        why=(
            "AUTO-HIT on `MBEDTLS_PRIVATE`, a token every answer to this question contains. The "
            "mark's substance is a COUNT, which no symbol can settle, and the objective HIT skips "
            "the judge entirely. Measured on p5-both: both arms HIT and neither answer states any "
            "number. Evidence cleared so the judge reads for the figure."
        ),
        expect="reports hundreds of uses — not tens, not thousands",
        symbols=[],
    ),
]

## ─────────────────────────────────────────────────────────────────────────────
## BATCH 5 (APPLIED at ba86185) — a mark that grades ARRANGEMENT cannot be scored, and as of the
## judge fix it is also a live contradiction: the judge is instructed that "format and placement are
## not graded". Q3 #8's substance half was kept and its layout half deleted. Q0 #1 also grades order
## and SURVIVED, because there the order IS the fact. Kept for the `why` field.
## ─────────────────────────────────────────────────────────────────────────────
APPLIED_BATCH_5: list[Fix] = [
    Fix(
        qid="Q3",
        index=8,
        why=(
            "GRADES ARRANGEMENT, which no judge can settle and which the fixed judge is now told "
            "to ignore outright. The library-vs-samples distinction is a real fact about mbedtls "
            "and is kept; 'as the substance, not as a caveat' is a claim about layout and is "
            "deleted. Measured: the answer led with the distinction in sentence one and the judge "
            "failed it on framing."
        ),
        expect="as the substance of the answer, not as a caveat appended to it",
        text=(
            "distinguishes LIBRARY code from sample programs and tests — the spawn sites are in "
            "`programs/`, and the crypto/X.509/TLS library code itself creates no threads"
        ),
    ),
]

## ─────────────────────────────────────────────────────────────────────────────
## BATCH 4 (APPLIED at abfbaa0) — ENUMERATE WHAT WOULD SATISFY AN OPEN MARK. Kept for the `why`
## field, which is the only written record of the reasoning; re-running would fail every
## precondition. A mark reading "names a concrete file" states a REQUIREMENT and no ANSWER KEY, and
## a codebase-blind judge cannot tell a plausible fabrication from the truth.
## ─────────────────────────────────────────────────────────────────────────────
APPLIED_BATCH_4: list[Fix] = [
    Fix(
        qid="Q6",
        index=1,
        why=(
            "OPEN MARK, no acceptable set. 'names a concrete file' invites a plausible invention "
            "(`library/x509_verify.c` does not exist) that a blind judge cannot distinguish from "
            "`library/x509_crt.c`. The two real files are enumerated and declared as refs."
        ),
        expect="locates certificate verification in the x509 layer and names a concrete file",
        text=(
            "locates certificate verification in the x509 layer and names a concrete file — "
            "`library/x509_crt.c` or `include/mbedtls/x509_crt.h`. A file that does not exist in "
            "this tree does not earn the mark however plausible its name"
        ),
        refs=[["x509_crt.c"], ["x509_crt.h"]],
        veto_safe=True,
    ),
    Fix(
        qid="Q6",
        index=2,
        why=(
            "OPEN MARK. Four entry points exist and the mark named none, so any `mbedtls_x509_*` "
            "invention passed. Enumerated from the index: three declared in the public header, one "
            "AST-recovered from library/x509_crt.c."
        ),
        expect="names a public entry point, or the profile-taking form the simple one delegates to",
        text=(
            "names a public entry point, or the profile-taking form the simple one delegates to — "
            "any of `mbedtls_x509_crt_verify` (`include/mbedtls/x509_crt.h:3159`), "
            "`mbedtls_x509_crt_verify_with_profile` (`:3176`), "
            "`mbedtls_x509_crt_verify_restartable` (`:3210`) or "
            "`mbedtls_x509_crt_verify_with_ca_cb` (`library/x509_crt.c`). Any ONE earns the mark; a "
            "name outside this set does not"
        ),
        symbols=[
            "mbedtls_x509_crt_verify",
            "mbedtls_x509_crt_verify_with_profile",
            "mbedtls_x509_crt_verify_restartable",
            "mbedtls_x509_crt_verify_with_ca_cb",
        ],
        require="any",
        veto_safe=True,
    ),
    Fix(
        qid="Q7",
        index=1,
        why=(
            "UNVERIFIABLE AS WRITTEN. 'the function is actually added and is valid C' is a claim "
            "about the filesystem; the judge reads a transcript and the objective pass reads an "
            "answer. Neither can open library/version.c. So the mark grades what a transcript CAN "
            "carry — the quoted definition — and says so, instead of leaving a blind judge to take "
            "an assertion on trust. NO EVIDENCE IS DECLARED: `mbedtls_acceptance_probe` as a symbol "
            "would settle a HIT on an answer that merely NAMES the function, which is the half of "
            "the requirement the mark no longer accepts."
        ),
        expect="**the function is actually added** and is valid C",
        text=(
            "**the answer REPRODUCES the definition it added**, and what it shows is valid C: a "
            "`mbedtls_acceptance_probe` taking no arguments and returning `int`. Graded on the "
            "QUOTED code, because that is what a transcript can evidence — an answer that asserts "
            "it made the edit without showing what it wrote does not earn the mark"
        ),
        symbols=[],
    ),
    Fix(
        qid="Q8",
        index=5,
        why=(
            "OPEN MARK, and the naive fix would have been WRONG. Enumerating from the target: the "
            "generator a banner credits is frequently NOT in this checkout — "
            "generate_ssl_debug_helpers.py and generate_psa_wrappers.py are both untracked, living "
            "in the unpopulated framework/ submodule — and psa_constant_names_generated.c's banner "
            "spells its script singular where the tracked file is plural. So the mark accepts the "
            "banner's own attribution, which is the correct method here. NO EVIDENCE IS DECLARED: the "
            "mark wants a PAIR out of six, and neither `any` (settles on the file alone) nor `all` "
            "(demands every pair) can express that."
        ),
        expect="names at least one tracked C or header file that is machine-generated, and its generator",
        text=(
            "names at least one tracked C or header file that is machine-generated, and its "
            "generator. Verified pairs at this commit: `library/ssl_debug_helpers_generated.c` ← "
            "`generate_ssl_debug_helpers.py`, `programs/psa/psa_constant_names_generated.c` ← "
            "`generate_psa_constant.py` (the banner's spelling; the tracked script is "
            "`scripts/generate_psa_constants.py`, PLURAL), `tests/src/psa_test_wrappers.c` ← "
            "`generate_psa_wrappers.py`, `library/psa_crypto_driver_wrappers_no_static.h` ← "
            "`scripts/generate_driver_wrappers.py`, and `library/error.c` / "
            "`library/version_features.c` ← `scripts/generate_errors.pl` / "
            "`scripts/generate_features.pl`. THE GENERATOR NEED NOT BE IN THE CHECKOUT: the first "
            "and third live in the unpopulated `framework/` submodule, so quoting the file's own "
            "banner is a correct answer and citing an untracked script path is not an error. A pair "
            "outside this set does not earn the mark"
        ),
        symbols=[],
    ),
    Fix(
        qid="Q9",
        index=4,
        why=(
            "OPEN MARK: 'cites the repository's own prose' with no statement of WHICH prose, so any "
            "invented doc path passed. Enumerated by prose search over the index plus git ls-files."
        ),
        expect="**cites the repository's own prose for that**",
        text=(
            "**cites the repository's own prose for that**, rather than general knowledge of the "
            "project — `docs/psa-transition.md`, any file under "
            "`docs/architecture/psa-migration/` (`strategy.md`, `psa-legacy-bridges.md`, "
            "`psa-limitations.md`, `transition-guards.md`), or `README.md`'s PSA section. A quoted "
            "document that is not in this tree does not earn the mark"
        ),
        refs=[["psa-transition.md"], ["strategy.md"], ["README.md"]],
        require="any",
    ),
    Fix(
        qid="Q9",
        index=6,
        why=(
            "OPEN MARK. 'at least one concrete implementation file for the newer interface' with no "
            "set: `library/psa.c` would pass and does not exist. Enumerated from the tree."
        ),
        expect="names at least one concrete implementation file for the newer interface",
        text=(
            "names at least one concrete implementation file for the newer interface — "
            "`library/psa_crypto.c`, `library/psa_crypto_slot_management.c`, "
            "`library/psa_crypto_client.c`, `library/psa_crypto_storage.c` or another "
            "`library/psa_*.c`. A file not in this tree does not earn the mark"
        ),
        refs=[["psa_crypto.c"], ["psa_crypto_slot_management.c"], ["psa_crypto_client.c"]],
        require="any",
    ),
    Fix(
        qid="Q10",
        index=2,
        why=(
            "OPEN MARK: 'names the shared object' with no set, and this question's whole difficulty "
            "is that the objects are file-static and easy to invent. The four real carriers are "
            "already enumerated in sibling mark #3 — stating them here makes THIS mark checkable "
            "instead of relying on a judge to remember a later checklist item."
        ),
        expect="**names the shared object that carries it**, not only the two functions",
        text=(
            "**names the shared object that carries it**, not only the two functions — the "
            "buffer allocator's file-static `heap` (`library/memory_buffer_alloc.c:68`), the "
            "allocator pointers `mbedtls_calloc_func` / `mbedtls_free_func` "
            "(`library/platform.c:44-45`), or either file-static `global_data` "
            "(`library/psa_crypto.c:124`, `library/psa_crypto_slot_management.c:193`). An object "
            "not in this set does not earn the mark"
        ),
        symbols=["mbedtls_calloc_func", "mbedtls_free_func", "global_data"],
        require="any",
        veto_safe=True,
    ),
    Fix(
        qid="Q11",
        index=3,
        why=(
            "OPEN MARK. 'names the supported programmatic route' — there is exactly one supported "
            "script and it is tracked, so the set is small and the mark should say it. "
            "`scripts/config.pl` also ships and is the legacy form."
        ),
        expect="names the supported programmatic route as well as editing by hand",
        text=(
            "names the supported programmatic route as well as editing by hand — `scripts/config.py` "
            "(`set` / `unset` / `full`), or the legacy `scripts/config.pl` that ships beside it. "
            "Naming some other tool does not earn the mark"
        ),
        refs=[["config.py"], ["config.pl"]],
        require="any",
        veto_safe=True,
    ),
    Fix(
        qid="Q11",
        index=5,
        why=(
            "OPEN MARK, and the COMPILE half is the substance. Two headers do this and both are "
            "tracked; enumerating them also states the mechanism (`#error`) so the mark cannot be "
            "earned by a vague 'the build checks it'. NO EVIDENCE IS DECLARED: the mark itself says "
            "both halves are required, and a whole-file ref would settle a HIT on the header alone."
        ),
        expect="names what catches a contradictory configuration, and says it fails the COMPILE",
        text=(
            "**names what catches a contradictory configuration, and says it fails the COMPILE** "
            "rather than being detected at run time — `include/mbedtls/check_config.h` (202 `#error` "
            "directives) or `library/check_crypto_config.h` (17), which raise a PREPROCESSOR error "
            "so the translation unit does not compile. Both halves are required: naming the header "
            "without the compile-time consequence, or asserting a compile failure without naming "
            "what raises it, does not earn the mark"
        ),
        refs=[],
        veto_safe=True,
    ),
]

## ─────────────────────────────────────────────────────────────────────────────
## BATCH 3 (APPLIED at 9f8a7ef) — EVIDENCE TYPING. These marks were true and scoreable; what was
## wrong is what the SCORER was given to settle them with, invented by a regex rather than declared
## by an author. Kept for the `why` field, the only written record of the reasoning; re-running it
## would fail every precondition, which is the guard working.
##
## TWO FAILURE DIRECTIONS, both measured against a deliberately wrong four-line answer:
##   AUTO-HIT   `bench_score._decide` set `sym_ok` from ANY one extracted symbol and
##              `grade_matrix` skips the judge on an objective HIT. So `mbedtls_`, `private_`,
##              `psa_crypto` and `mbedtls_config` awarded their marks UNSEEN — nobody would write
##              a bare vendor prefix as a mark's evidence; `_SYMBOL` produced it from prose.
##   AUTO-MISS  `_refs` required a line number, so a mark whose whole evidence is a PATH extracted
##              nothing and went to the LLM judge. Q1 #6 scored MISS with quote NONE while the
##              graded answer's line 8 read "declared `extern` in
##              `include/mbedtls/threading.h:111-114`" — the very line the judge quoted to award a
##              DIFFERENT mark. A machine-checkable fact lost to a judge miss.
##
## THE TEXTS WERE NOT TOUCHED. Every entry here changed only declared evidence, which is the whole
## point of the migration: the mark said what it always said, and the scorer now knows what would
## satisfy it. A whole-file ref is `[path]`. Batch 4 above is the one batch that DOES change text,
## and the reason is stated there.
## ─────────────────────────────────────────────────────────────────────────────
APPLIED_BATCH_3: list[Fix] = [
    Fix(
        qid="Q0",
        index=3,
        why=(
            "AUTO-HIT on `mbedtls_config`, which matches any answer that mentions the config header "
            "at all — and this mark is about noticing that function bodies are GUARDED, not about "
            "naming a file. The junk symbol goes; the two paths the text already cites become refs."
        ),
        expect="guards nearly every function body behind conditional compilation",
        symbols=[],
        refs=[["mbedtls_config.h"]],
    ),
    Fix(
        qid="Q1",
        index=6,
        why=(
            "THE EXEMPLAR OF THE AUTO-MISS CLASS. Its entire evidence is a path, `_refs` needed a "
            "line number, so it extracted nothing, went to the judge and scored MISS with quote NONE "
            "— while the graded answer named the file on its line 8 and the judge quoted that line "
            "to award mark #9. Declaring the whole-file ref makes it settleable by the objective "
            "pass, which also REDUCES judge load, and session capacity is the binding constraint."
        ),
        expect="locates the pointer declarations in `include/mbedtls/threading.h`",
        refs=[["threading.h", 111, 114]],
        veto_safe=True,
    ),
    Fix(
        qid="Q1",
        index=9,
        why="Path-only, same class as #6. The bindings are at library/threading.c:101-104.",
        expect="locates the bindings in `library/threading.c`",
        refs=[["threading.c", 101, 104]],
        veto_safe=True,
    ),
    Fix(
        qid="Q1",
        index=19,
        why=(
            "AUTO-HIT on `psa_crypto`, which also matches `psa_crypto_slot_management` and "
            "`psa_crypto_random` — so it cannot discriminate the HEAVIEST user from any other psa "
            "file. Re-verified: `library/psa_crypto.c` holds 19 of the 46 acquisitions, more than "
            "twice the next file."
        ),
        expect="identifies `library/psa_crypto.c` as the heaviest user",
        symbols=[],
        refs=[["psa_crypto.c"]],
        veto_safe=True,
    ),
    Fix(
        qid="Q1",
        index=20,
        why=(
            "Path-only for both sites it names. `ssl_pthread_server` is a real discriminator and "
            "stays; the refs make the claim machine-settleable."
        ),
        expect="notes that call sites exist OUTSIDE `library/`",
        symbols=["ssl_pthread_server"],
        refs=[["ssl_pthread_server.c"], ["test_suite_psa_crypto.function"]],
        veto_safe=True,
    ),
    Fix(
        qid="Q1",
        index=29,
        why=(
            "ITS OWN THRESHOLD WAS UNREADABLE TO THE SCORER. The text says 'seven public headers "
            "carry such a member, or names at least TWO of them' and lists all seven — and the "
            "objective pass HIT on ONE, because `sym_ok` is any-of. Worse, `entropy.h` and `rsa.h` "
            "yield NO symbol at all (too short, lowercase-only), so two of the seven acceptable "
            "answers were silently unscoreable. All seven are now whole-file refs with "
            "`min_matches: 2`, which is exactly what the mark asks for."
        ),
        expect="states that seven public headers carry such a member",
        symbols=[],
        refs=[
            ["ctr_drbg.h"],
            ["entropy.h"],
            ["hmac_drbg.h"],
            ["rsa.h"],
            ["ssl_cache.h"],
            ["ssl_cookie.h"],
            ["ssl_ticket.h"],
        ],
        min_matches=2,
        veto_safe=True,
    ),
    Fix(
        qid="Q2",
        index=2,
        why="Path-only. The definition is at include/mbedtls/private_access.h:15-17.",
        expect="locates its definition in `include/mbedtls/private_access.h`",
        symbols=["MBEDTLS_PRIVATE"],
        refs=[["private_access.h", 15, 17]],
        veto_safe=True,
    ),
    Fix(
        qid="Q2",
        index=3,
        why=(
            "AUTO-HIT on `private_`, a bare prefix that matches `private_access.h`, "
            "`MBEDTLS_ALLOW_PRIVATE_ACCESS` and the word 'private' in any prose. The mark is about "
            "the DEFAULT expansion being the prefixed form, which lives in the `ifndef` branch at "
            "private_access.h:15."
        ),
        expect="states the DEFAULT expansion is a prefixed name",
        symbols=[],
        refs=[["private_access.h", 15]],
        veto_safe=True,
    ),
    Fix(
        qid="Q2",
        index=14,
        why="Path-only. The library's own opt-in is at library/common.h:132.",
        expect="names `library/common.h` as where the library does it",
        symbols=["MBEDTLS_ALLOW_PRIVATE_ACCESS"],
        refs=[["common.h", 132]],
        veto_safe=True,
    ),
    Fix(
        qid="Q2",
        index=17,
        why=(
            "Path-only for both acceptable answers, and this is a mark the INDEX beats grep on: "
            "`dossier('MBEDTLS_ALLOW_PRIVATE_ACCESS')` lists all three definition sites including "
            "these two in `programs/`, which the graded agent's `--include`-filtered grep missed "
            "entirely. Either site satisfies it, so `require` stays `any`."
        ),
        expect="names at least one other opt-in site",
        symbols=["ssl_client2", "ssl_server2"],
        refs=[["ssl_client2.c", 8], ["ssl_server2.c", 8]],
        veto_safe=True,
    ),
    Fix(
        qid="Q5",
        index=7,
        why=(
            "AUTO-HIT on `psa_crypto`. The mark's substance is the FLATNESS of `library/` and its "
            "filename-prefix grouping, none of which a single symbol can settle — so the junk "
            "symbol is removed rather than replaced, leaving the mark honestly judge-settled "
            "instead of falsely auto-passed."
        ),
        expect="**reports that `library/` is FLAT**",
        symbols=[],
    ),
    Fix(
        qid="Q7",
        index=3,
        why="Path-only. The file the edit targets is library/version.c.",
        expect="names the file `library/version.c`",
        refs=[["version.c"]],
    ),
    Fix(
        qid="Q9",
        index=3,
        why=(
            "AUTO-HIT on `mbedtls_`, which every answer about this library contains. The mark is "
            "about the DIRECTION of travel and no single symbol settles it, so the junk evidence is "
            "removed and the mark is honestly judged rather than falsely passed."
        ),
        expect="names the direction of travel",
        symbols=[],
    ),
    Fix(
        qid="Q11",
        index=1,
        why=(
            "AUTO-HIT on `mbedtls_config`, which matches the header's own name — so the mark scored "
            "on any answer that mentioned the file it is asking about. The path becomes a ref, "
            "which is a real check, and the junk symbol goes."
        ),
        expect="as where the decision is recorded",
        symbols=[],
        refs=[["mbedtls_config.h"]],
        veto_safe=True,
    ),
]

## ─────────────────────────────────────────────────────────────────────────────
## BATCH 1 (APPLIED at 0ba220f) — kept here as the record of what was corrected and why. Re-running
## it would fail every precondition, which is the guard working: these marks no longer read as they
## did. The entries stay because `why` is the only place the reasoning is written down.
## ─────────────────────────────────────────────────────────────────────────────
## ─────────────────────────────────────────────────────────────────────────────
## BATCH 2 (APPLIED at b160889) — the unscoreable marks: prohibitions satisfiable by silence,
## grading rules a codebase-blind judge defaults to HIT on, and duplicates that made one failure
## cost three points. Kept for the `why` field, which is the only written record of the reasoning.
## ─────────────────────────────────────────────────────────────────────────────
APPLIED_BATCH_2: list[Fix] = [
    Fix(
        qid="Q0",
        index=8,
        why=(
            "LEADS WITH A PROHIBITION whose positive half is already in the same sentence. Silence "
            "about the change satisfies the negative reading, so re-leading with what the answer "
            "must SAY costs nothing and makes the mark falsifiable."
        ),
        expect="does not present a widened view as if it had been the default",
        text=(
            "**says what it changed** — so a reader can tell which of its answers rest on the "
            "default coverage and which on the widened one, rather than presenting a widened view "
            "as if it had been the default"
        ),
    ),
    Fix(
        qid="Q4",
        index=3,
        why=(
            "A PROHIBITION INSIDE THE SUPPOSEDLY-CLEANED Q1-Q4. Satisfiable by silence and "
            "unfalsifiable by an answer that never raises the topic. The Q4 preamble claimed the "
            "last negative mark had been converted and task #411 recorded it as complete; this one "
            "survived both."
        ),
        expect="does not treat those two as interchangeable",
        text=(
            "states what each of `library/` and `include/` holds that the other does not — the "
            "implementations against the declared contract"
        ),
        refs=[["library"], ["include"]],
    ),
    Fix(
        qid="Q5",
        index=2,
        why=(
            "LEADS WITH A PROHIBITION and then supplies its own positive form. Re-verified: 62 "
            "files match `^int main` and 61 of them are under `programs/`, so exactly one is not."
        ),
        expect="does not nominate a single `main` as the entry point",
        text=(
            "**states that no single `main` is canonical** — about 60 files define one, 61 of the "
            "62 under `programs/`, so nominating one as THE entry point is wrong. The exact count "
            "is not required and neither is the `programs/` claim being exact"
        ),
    ),
    Fix(
        qid="Q5",
        index=8,
        why=(
            "UNSCOREABLE BY THIS JUDGE. `mark_prompt` states 'You have NO access to the codebase', "
            "so it cannot tell an invented claim from a verified one and defaults to HIT for any "
            "answer that sounds careful. Fabrication control belongs to the falsity veto, which "
            "has a truth list, not to a per-mark checklist item that cannot be settled."
        ),
        expect="does not invent architecture it did not verify",
        delete=True,
    ),
    Fix(
        qid="Q7",
        index=5,
        why=(
            "COMPOUND: a positive fact fused with a prohibition. Under one-mark-one-fact the second "
            "clause cannot fail independently, and the judge cannot verify the absence of callers "
            "without the repo. The positive half is kept and is the whole mark."
        ),
        expect="**states that NOTHING calls it**, and invents no caller",
        text="**states that NOTHING calls it** — the function it just added has no callers",
    ),
    Fix(
        qid="Q7",
        index=8,
        why=(
            "THREE MARKS GRADE ONE BEHAVIOUR. #6 already grades the positive form ('describes how "
            "it made sure its answer reflects the edit') and #1 covers the same ground, so one "
            "failure costs three points. It is also a prohibition with an auto-fail clause."
        ),
        expect="does not answer from a view taken before the edit",
        delete=True,
    ),
    Fix(
        qid="Q8",
        index=8,
        why=(
            "REDUNDANT WITH #1, which grades identifying `framework/` as an unpopulated submodule. "
            "An answer earning #1 cannot fail this, so it is a free point rather than a "
            "discriminator — and it is phrased as a prohibition."
        ),
        expect="does not report the checkout as complete",
        delete=True,
    ),
    Fix(
        qid="Q9",
        index=2,
        why=(
            "POSITIVE STATEMENT CARRYING A PROHIBITION CLAUSE. The trailing 'claiming a parallel "
            "one for them is a MISS' instructs the judge to fail an answer for something it says, "
            "which is a scoring rule embedded in a checklist item. Trimmed to the fact."
        ),
        expect="claiming a parallel one for them is a MISS",
        text=(
            "**states that the two-interface split covers CRYPTOGRAPHY only** — X.509 and TLS have "
            "a single public interface"
        ),
    ),
    Fix(
        qid="Q10",
        index=1,
        why=(
            "A PROHIBITION, AN AUTO-FAIL CLAUSE, AND UNDECIDABLE. `questions-TEMPLATE.md` forbids "
            "auto-fail clauses outright; 'outweighs whatever else the answer gets right' is one. "
            "And a judge with no source access cannot tell a fabricated coupling from a real one, "
            "so it defaults to HIT. Fabrication is the falsity veto's job."
        ),
        expect="fabricates no couplings",
        delete=True,
    ),
    Fix(
        qid="Q10",
        index=6,
        why=(
            "AUTO-HIT ON A JUNK TOKEN, and a prohibition with an auto-fail clause. Its only "
            "extracted symbol was `global_data`, so the objective pass HIT on any answer "
            "containing that string and the judge was never called. Re-verified in the target: two "
            "`static psa_global_data_t global_data` at library/psa_crypto.c:124 and "
            "library/psa_crypto_slot_management.c:193. Naming both citations makes it a real "
            "discriminator, and `require: all` stops one of the two satisfying it."
        ),
        expect="avoids conflating same-named file-statics",
        text=(
            "**states that `library/psa_crypto.c` and `library/psa_crypto_slot_management.c` each "
            "declare a SEPARATE file-static `psa_global_data_t global_data`** — two distinct "
            "objects that share a name"
        ),
        symbols=["psa_global_data_t"],
        refs=[["psa_crypto.c", 124], ["psa_crypto_slot_management.c", 193]],
        require="all",
        veto_safe=True,
    ),
    Fix(
        qid="Q10",
        index=8,
        why=(
            "A GRADING RULE, NOT A FACT about mbedtls or a demonstrable property of an answer — and "
            "a duplicate of #1, now deleted. A codebase-blind judge cannot distinguish the two "
            "cases it describes, so it defaults to HIT. The honesty/fabrication trade belongs in "
            "the veto and the scoring policy, where it can be enforced."
        ),
        expect='an honest "I could not establish more than the couplings I named" scores FULL credit',
        delete=True,
    ),
]

APPLIED_BATCH_1: list[Fix] = [
    Fix(
        qid="Q3",
        index=18,
        why=(
            "FALSE. A default build DOES create a thread on Windows: benchmark.c:430's "
            "`_beginthread(TimerProc, ...)` is gated on `#if defined(_WIN32) && !defined(EFIX64) "
            "&& !defined(EFI32)` — a PLATFORM condition, not a config option — inside "
            "`#if !defined(MBEDTLS_TIMING_ALT)`. Re-verified in the target: MBEDTLS_HAVE_TIME is "
            "ACTIVE at mbedtls_config.h:131 and MBEDTLS_TIMING_ALT is commented out at :353. "
            "The mark also contradicts Q3 #5 and #6, which credit that very spawn. It came from "
            "the pre-atomisation compound mark 6, where it was one of three alternative ways to "
            "earn ONE mark; atomisation promoted it to a mandatory mark of its own."
        ),
        expect="concludes that a DEFAULT build of this repository creates no threads at all",
        text=(
            "concludes that a default POSIX build of this repository creates no threads — the "
            "pthread spawn's own guard (`MBEDTLS_THREADING_C` / `MBEDTLS_THREADING_PTHREAD`) is "
            "off in the shipped configuration. An answer that adds that a default WINDOWS build "
            "does spawn one is MORE correct, not less, and must not be marked down for it"
        ),
        refs=[["mbedtls_config.h", 3787], ["mbedtls_config.h", 2196]],
        veto_safe=True,
    ),
    Fix(
        qid="Q3",
        index=15,
        why=(
            "AMBIGUOUS, and measurably earnable by naming the WRONG guard: the spot check awarded "
            "it on the quote `#if defined(_WIN32) && !defined(EFIX64) && !defined(EFI32)`, which "
            "is benchmark.c:405 — the Windows site — for a mark about the POSIX one. Naming the "
            "file makes it settleable."
        ),
        expect="reports that the POSIX spawn site is itself conditionally compiled",
        text=(
            "reports that the POSIX spawn site in `programs/ssl/ssl_pthread_server.c` is itself "
            "conditionally compiled, behind `MBEDTLS_THREADING_C` / `MBEDTLS_THREADING_PTHREAD`"
        ),
        refs=[["ssl_pthread_server.c", 24, 30]],
        veto_safe=True,
    ),
    Fix(
        qid="Q3",
        index=9,
        why=(
            "RESURRECTED BY THE ATOMISATION. This is verbatim the epistemic-habit mark the "
            "rubric's own re-aim table records as REPLACED: questions.md:240 lists it in the "
            "'graded a habit' column and :144 asserts that Q3 carries no contaminated mark at "
            "all. Its substance is already covered by #7 (exactly TWO spawn sites in this "
            "checkout) and #8. It also grades the PROMPT's own instruction to say how confident "
            "you are, which is a habit and not a fact about mbedtls."
        ),
        expect="scopes the completeness claim to the tree in front of it",
        delete=True,
    ),
    Fix(
        qid="Q1",
        index=27,
        why=(
            "CONTRADICTS THE COMMITTED EVIDENCE. `evidence.md`'s census reads '6 GLOBALS — 5 "
            "named ... 1 debug_mutex, programs/ssl/ssl_pthread_server.c:65 — a global OUTSIDE "
            "library/'. Re-verified: five definitions at library/threading.c:182,185,188,189,190 "
            "plus `mbedtls_threading_mutex_t debug_mutex;` at ssl_pthread_server.c:65, and "
            "`git grep -nE 'static +mbedtls_threading_mutex_t'` returns NOTHING, so debug_mutex "
            "is a true non-static global. An answer reporting SIX is more complete and graded "
            "MISS."
        ),
        expect="states that there are FIVE named global mutexes",
        text=(
            "states that FIVE named global mutexes live in the LIBRARY (`library/threading.c`), "
            "and does not present that as the repository's total — a sixth named global, "
            "`debug_mutex`, sits in `programs/`"
        ),
        symbols=["mbedtls_threading_readdir_mutex", "mbedtls_threading_gmtime_mutex"],
        refs=[["threading.c", 182, 190]],
        veto_safe=True,
    ),
    Fix(
        qid="Q1",
        index=17,
        why=(
            "WRONG ABOUT ITS OWN ARITHMETIC'S TERMS. Two of the three `library/threading.c` lines "
            "are pointer DEFINITIONS in mutually exclusive branches (:103 under "
            "MBEDTLS_THREADING_PTHREAD, :127 under MBEDTLS_THREADING_ALT) and :140 is an "
            "ASSIGNMENT inside `mbedtls_threading_set_alt`. `evidence.md` says "
            "'definitions/assignment'; the mark, which is what the judge reads, calls all three "
            "definitions. An answer distinguishing them is more accurate than the key."
        ),
        expect="the same 48 plus the `threading.h` declaration and three pointer definitions",
        text=(
            "reports tens of call sites, not one and not hundreds. BOTH figures are creditable "
            "and neither may be marked down: 48 call sites in 16 files, or the 52 lines in 18 "
            "files that `git grep -n mbedtls_mutex_lock` prints (the same 48 plus the "
            "`threading.h` declaration, two pointer definitions in mutually exclusive branches of "
            "`library/threading.c`, and one assignment inside `mbedtls_threading_set_alt`)"
        ),
        symbols=["mbedtls_mutex_lock"],
        refs=[["threading.c", 101, 104], ["threading.h", 111, 114]],
    ),
    Fix(
        qid="Q1",
        index=12,
        why=(
            "UNQUALIFIED AND THEREFORE FALSE OF THE COMMON BUILD. The stand-ins "
            "(`threading_mutex_dummy` / `threading_mutex_fail`, threading.c:120-128) exist ONLY "
            "under MBEDTLS_THREADING_ALT; a pthread build has real pthread bindings and no "
            "stand-ins, and `threading_mutex_fail` REFUSES rather than standing in. An answer "
            "correctly saying a pthread build has no placeholders graded MISS."
        ),
        expect="mentions the stand-in implementations used until a caller supplies its own",
        text=(
            "names the `MBEDTLS_THREADING_ALT` stand-ins — `threading_mutex_dummy` and "
            "`threading_mutex_fail` — which REFUSE until a caller calls "
            "`mbedtls_threading_set_alt`, and are not present in a pthread build at all"
        ),
        symbols=["threading_mutex_dummy", "threading_mutex_fail", "mbedtls_threading_set_alt"],
        refs=[["threading.c", 120, 128]],
    ),
    Fix(
        qid="Q1",
        index=30,
        why=(
            "NAMES AN OBJECT THAT DOES NOT EXIST. There is no file-static mutex in that file — "
            "`git grep -nE 'static +mbedtls_threading_mutex_t'` returns nothing tree-wide. What "
            "exists is a `mutex` MEMBER (memory_buffer_alloc.c:63, itself behind "
            "`#if defined(MBEDTLS_THREADING_C)`) of the file-static struct `heap` (:68). "
            "`evidence.md` files it under STRUCT MEMBERS, not globals — and the index reports it "
            "correctly as `heap.mutex`, so here the tool is more precise than the key."
        ),
        expect="names the file-static heap mutex in `library/memory_buffer_alloc.c`",
        text=(
            "names `heap.mutex` — a mutex MEMBER of the file-static `buffer_alloc_ctx heap` in "
            "`library/memory_buffer_alloc.c`, not a mutex global of its own"
        ),
        symbols=["heap.mutex", "buffer_alloc_ctx"],
        refs=[["memory_buffer_alloc.c", 63], ["memory_buffer_alloc.c", 68]],
    ),
]


## @brief Locate a mark's entry span in the YAML text.
## @param lines The rubric's lines.
## @param qid Question id.
## @param index 1-based mark position.
## @return (start, end) line indices of the mark entry.
## @version 1
def mark_span(lines: list[str], qid: str, index: int) -> tuple[int, int]:
    """@brief Find one mark's line span.
    @return (start, end).
    @version 1
    """
    q_start = next(i for i, ln in enumerate(lines) if ln.strip() == f"- id: {qid}")
    q_end = next(
        (i for i in range(q_start + 1, len(lines)) if lines[i].startswith("  - id: ")),
        len(lines),
    )
    starts = [i for i in range(q_start, q_end) if lines[i].startswith("    - text:")]
    if index > len(starts):
        raise SystemExit(f"{qid} has {len(starts)} marks; asked for #{index}")
    start = starts[index - 1]
    end = starts[index] if index < len(starts) else q_end
    return start, end


## @brief Render a corrected mark entry.
## @param fix The correction.
## @param old The mark's existing lines.
## @return Replacement lines.
## @version 1
def render(fix: Fix, old: list[str]) -> list[str]:
    """PRESERVES WHAT THE FIX DOES NOT NAME. A correction that only changes evidence must not
    silently drop `arm_only`, and one that only changes text must not drop declared refs — so
    unnamed fields are carried across from the old entry rather than defaulted.

    @brief Rebuild one mark entry with the correction applied.
    @return Replacement lines.
    @version 1
    """
    import yaml

    ## Parse the ONE entry rather than regexing it: the text is a block scalar carrying colons,
    ## quotes and dashes, and a line-oriented edit of that is how prose gets corrupted.
    entry = yaml.safe_load("".join(ln[4:] for ln in old))[0]
    if fix.text is not None:
        entry["text"] = fix.text
    for name, value in (
        ("symbols", fix.symbols),
        ("refs", fix.refs),
        ("require", fix.require),
        ("min_matches", fix.min_matches),
        ("veto_safe", fix.veto_safe),
    ):
        if value is not None:
            entry[name] = value
    body = yaml.safe_dump(
        [entry], sort_keys=False, allow_unicode=True, width=100, default_flow_style=False
    )
    return [f"    {ln}\n" for ln in body.splitlines()]


## @brief Apply every correction, refusing on a failed precondition.
## @param path The YAML rubric.
## @return Number of corrections applied.
## @version 1
def apply_all(path: Path) -> int:
    """REVERSED ORDER, so an earlier edit cannot shift a later mark's span. Deletions make the
    ordering load-bearing rather than merely tidy.

    @brief Apply the declared corrections.
    @return Count applied.
    @version 1
    """
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    ## THE TOKEN STRIP RUNS FIRST and is line-oriented on purpose: it removes a fixed substring
    ## from mark text without reshaping any entry, so it cannot disturb the spans the fixes below
    ## locate. Doing it as nine `Fix` entries would mean nine near-identical preconditions and one
    ## place for a transcription slip.
    stripped = 0
    for i, line in enumerate(lines):
        if not any(token in line for token in STRIP_TOKENS):
            continue
        new = line
        for token in STRIP_TOKENS:
            new = new.replace(token, "")
        ## Only touch the mark BODY, never a key line — `arm_only: db` must survive.
        if new != line and not line.lstrip().startswith(
            ("arm_only:", "- id:", "refs:", "symbols:")
        ):
            lines[i] = new
            stripped += 1
    if stripped:
        print(f"  stripped {stripped} grader-only fence token(s) from mark text")

    ordered = sorted(FIXES, key=lambda f: (f.qid, f.index), reverse=True)
    for fix in ordered:
        start, end = mark_span(lines, fix.qid, fix.index)
        old = lines[start:end]
        if fix.expect not in "".join(old):
            raise SystemExit(
                f"PRECONDITION FAILED for {fix.qid} #{fix.index}: expected to find\n"
                f"  {fix.expect!r}\nin\n  {''.join(old)[:400]!r}\n"
                f"The mark has moved or already changed — refusing to overwrite it."
            )
        replacement = [] if fix.delete else render(fix, old)
        lines[start:end] = replacement
        print(f"  {'DELETED' if fix.delete else 'fixed  '} {fix.qid} #{fix.index}")
    path.write_text("".join(lines), encoding="utf-8")
    return len(ordered)


## @brief CLI entry point.
## @return Process exit code.
## @version 1
def main() -> int:
    """@brief Apply the corrections and report the new mark counts.
    @return 0 on success.
    @version 1
    """
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("rubric", type=Path)
    args = ap.parse_args()

    import bench_rubric

    before = bench_rubric.parse_rubric_yaml(args.rubric)
    print(f"before: {sum(len(r.marks) for r in before.values())} marks")
    count = apply_all(args.rubric)
    after = bench_rubric.parse_rubric_yaml(args.rubric)
    print(f"applied {count} correction(s)")
    print(f"after : {sum(len(r.marks) for r in after.values())} marks")
    for qid in sorted(after, key=lambda q: int(q[1:])):
        if len(after[qid].marks) != len(before[qid].marks):
            print(f"  {qid}: {len(before[qid].marks)} -> {len(after[qid].marks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
