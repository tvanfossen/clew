# SPDX-License-Identifier: MIT
"""Auto-detected starter `.clew.yaml` (issue #54) — the proposer's contract.

The feature's failure mode is not a missing proposal, it is a PLAUSIBLE WRONG
one: a pattern that looks right, gets committed into a repo's declaration, and
from then on shapes every answer the graph gives with nothing downstream able to
tell a fabricated edge from a real one. So the tests here are mostly about
refusal — that a candidate reaching the output has been MEASURED, that a refused
one is still reported with its reason, and that the emitted draft parses to
exactly the sections it claims.

Most synthetic repos here are built in tmp_path with invented conventions
(`ACME_SET_*`), never a real repo's names: the module under test reads whatever a
repo declares or exhibits, so baking a real shape in would defeat it. The one
exception is the `repo_root`/`rich_db` pair, where the point IS a real code
generator's accessor convention — `DataModel_Set_<KEY>(v)` beside
`DataModel_SetIntegralTypeByKey(key, v)`, two families that split at DIFFERENT
boundaries and must therefore stay separate.

That convention is now WRITTEN OUT in `tests/data/csample/gen/ingot/`, where it
used to be committed generator output. What the two tests below prove is
unchanged — the detector recovers the family from CALL SITES (not from
`memberdef`, which is structurally blind to a macro-shaped accessor), refuses it
against the evidence floor, and says why. What they no longer evidence is that a
real generator emits that shape; that was never asserted, but it was implied by
the fixture's provenance, and it is worth being explicit that it no longer is.

@brief Tests for clew.propose.
@version 1
"""

from __future__ import annotations

import contextlib
import io
import sqlite3
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from clew import cli as build_cli
from clew.declaration import (
    DECLARATION_NAME,
    SECTION_DATA_MODEL,
    SECTION_DISPATCH,
    SECTION_ENTRY_PATTERNS,
    SECTION_LOCKS,
    SECTION_MQTT,
    SECTION_SHARED_KEY,
    SECTION_THREADS,
    load_declaration,
)
from clew.harvest import try_import_tree_sitter
from clew.propose import (
    YAML_MARKER,
    SectionStatus,
    marked_lines,
    propose,
    propose_main,
    section_names,
    uncomment,
)
from clew.propose import command as propose_command
from clew.propose.astdefs import ForwardCall, FuncDef
from clew.propose.dryrun import index_defect
from clew.propose.sharedkey_detect import Family, Pair
from clew.propose.sharedkey_report import _section_yaml
from clew.propose.threads_detect import resolve_fixpoint
from clew.scope import INDEX_SCOPE_SECTION
from clew.signature import write_build_signature

pytestmark = pytest.mark.skipif(
    try_import_tree_sitter() is None,
    reason="the proposer needs tree_sitter + its C/C++ grammars",
)

_GUARD_CONFIG = """\
    repos:
      - repo: https://example.invalid/doxygen-guard
        rev: v1
        hooks:
          - id: doxygen-guard
            files: ^src/.*\\.(c|h)$
    """

# An invented data-model convention: the key is in the NAME, a setter takes
# exactly one argument and a getter none. Writers and readers sit in DIFFERENT
# functions, which is what makes the pair a causal seam rather than a
# read-modify-write the gate would refuse as self-loops.
_ACME_SOURCE = """\
#define ACME_SET_ALPHA(v) acme_store("alpha", v)
#define ACME_SET_BETA(v)  acme_store("beta", v)
#define ACME_GET_ALPHA()  acme_load("alpha")
#define ACME_GET_BETA()   acme_load("beta")

void producer(void)
{
    ACME_SET_ALPHA(1);
    ACME_SET_BETA(2);
}

void consumer(void)
{
    int a = ACME_GET_ALPHA();
    int b = ACME_GET_BETA();
    (void)a;
    (void)b;
}
"""

# No accessor convention at all: two plain functions, one calling the other.
_PLAIN_SOURCE = """\
void helper(void)
{
    volatile int x = 1;
    (void)x;
}

void main_loop(void)
{
    helper();
}
"""


## @brief Materialise a synthetic scope-declaring repo with one C source file.
## @param root Repo root to create.
## @param source C source text for `src/app.c`.
## @return The repo root.
## @version 2
def _repo(root: Path, source: str) -> Path:
    """The `index_scope:` is what the proposer's first-party gate reads. The gate hook
    is written too, so the fixture is a repo that declares BOTH boundaries — which is
    what a real adopting repo looks like and what keeps the two distinguishable.

    @brief Build a synthetic repo that declares an index scope.
    @return The repo root.
    @version 2
    """
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / ".pre-commit-config.yaml").write_text(textwrap.dedent(_GUARD_CONFIG), encoding="utf-8")
    (root / ".clew.yaml").write_text("index_scope:\n  roots: [src]\n", encoding="utf-8")
    (root / "src" / "app.c").write_text(source, encoding="utf-8")
    return root


## @brief Build a doxygen-shaped index over one synthetic file.
## @param db_path Where to write the database.
## @param rel_path Repo-relative path of the indexed source file.
## @param functions (rowid, name, bodystart, bodyend) for each indexed function.
## @return The database path.
## @version 1
def _index(db_path: Path, rel_path: str, functions: list[tuple[int, str, int, int]]) -> Path:
    """Only `path` + `memberdef` are needed: the dry run re-runs the real
    importer, which walks the `path` table and attributes each call site to the
    memberdef whose body range encloses it.

    @brief Seed a minimal doxygen-shaped index for a dry run.
    @version 1
    """
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE path (name TEXT);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY,
            kind TEXT, name TEXT, file_id INTEGER, bodyfile_id INTEGER,
            bodystart INTEGER, bodyend INTEGER
        );
        """,
    )
    conn.execute("INSERT INTO path (rowid, name) VALUES (1, ?)", (rel_path,))
    conn.executemany(
        "INSERT INTO memberdef (rowid, kind, name, file_id, bodyfile_id, bodystart, bodyend) "
        "VALUES (?, 'function', ?, 1, 1, ?, ?)",
        functions,
    )
    conn.commit()
    conn.close()
    write_build_signature(db_path)
    return db_path


## @brief A synthetic repo exhibiting the ACME convention, plus its index.
## @param tmp_path Per-test temporary directory.
## @return (repo root, index path).
## @version 1
def _acme(tmp_path: Path) -> tuple[Path, Path]:
    """@brief Build the ACME writer/reader fixture and an index over it."""
    root = _repo(tmp_path / "acme", _ACME_SOURCE)
    db = _index(
        tmp_path / "acme.db", "src/app.c", [(1, "producer", 6, 10), (2, "consumer", 12, 18)]
    )
    return root, db


## @brief The section result for one section name.
## @param proposal The proposal to read.
## @param name Section name.
## @return That section's SectionProposal.
## @version 1
def _section(proposal, name: str):
    """@brief Look one section up by name."""
    return next(s for s in proposal.sections if s.name == name)


# ─── the registry cannot silently omit a section ─────────────────────────────


## @brief Every declaration section is reported on, not just the detected ones.
## @version 2
def test_every_declaration_section_is_reported_on() -> None:
    """A draft that simply omits `locks:` leaves an owner unable to tell "we
    looked and found nothing" from "we never looked" — opposite actions. So the
    registry must cover the declaration module's whole surface, and this test is
    what makes a newly-added section impossible to leave out silently.

    IT DID NOT DO THAT. The assertion was a hand-written literal set, so it moved
    only when someone edited it — and `preprocessor` (gh#17) and `kconfig` (gh#18)
    were both added to `KNOWN_SECTIONS` and never to the registry, staying missing
    from every rendered draft while this test passed and its own docstring claimed
    the omission was impossible. A guard that fires on some of the real cases is
    worse than none: it converts "unchecked" into "checked and fine".

    So it now compares against `KNOWN_SECTIONS` itself, which is the set the
    loader ACCEPTS. That cannot be satisfied by editing one list, and a section
    reachable in a repo's YAML but absent from the proposer is the definition of
    the gap this test names.

    @brief The registry enumerates every `.clew.yaml` section.
    @version 2
    """
    from clew.declaration import KNOWN_SECTIONS

    assert set(section_names()) == set(KNOWN_SECTIONS)
    # The literals stay named, so a RENAME still has to touch this file rather than
    # silently satisfying the set comparison on both sides.
    assert {
        SECTION_SHARED_KEY,
        SECTION_THREADS,
        SECTION_MQTT,
        SECTION_DATA_MODEL,
        SECTION_LOCKS,
        SECTION_ENTRY_PATTERNS,
        SECTION_DISPATCH,
        INDEX_SCOPE_SECTION,
    } <= set(section_names())


## @brief The CLI's dispatch word and the command module's agree.
## @version 1
def test_cli_subcommand_word_matches_the_command_module() -> None:
    """`cli.PROPOSE_COMMAND` is spelled separately so a build invocation never
    imports the proposer. Two spellings of one token drift; this pins them."""
    assert build_cli.PROPOSE_COMMAND == propose_command.COMMAND


# ─── demobot: the generated accessor convention is recovered from call sites ──


## @brief demobot's generated accessor family is recovered and correctly refused.
## @version 2
def test_demobot_recovers_the_ingot_convention_from_call_sites(
    repo_root: Path, rich_db: Path
) -> None:
    """The fixture's data model is `DataModel_Set_<KEY>` / `Get_<KEY>`, and the
    detector must recover that family FROM CALL SITES — the whole reason it does
    not reuse the build-time diagnostic, which reads `memberdef` and is
    structurally blind to a macro-shaped accessor.

    It must ALSO refuse it, and say why. The fixture deliberately has exactly ONE
    key that is both written and read (its punchline is the missing path between a
    writer and a reader of `DEMOBOT_UX_SOUND_EVENT`), so the pair sits below the
    shared-key evidence floor. One coincidence is not a data model. The name-keyed
    family and the argument-keyed `...ByKey` dispatchers must stay SEPARATE
    families — merging them at the common `DataModel_Set` would take the arity gate
    down with both.

    Measured identical on the retired `sample/` build and on `csample`: the same 1
    shared key over the same 3 attributed call sites, the same two rejections.

    @brief The generated family is recovered, refused, and the refusal explained.
    @version 2
    """
    section = _section(propose(repo_root, rich_db), SECTION_SHARED_KEY)
    assert section.status is SectionStatus.NO_CANDIDATES
    by_name = {r.name: r for r in section.rejections}

    name_keyed = next((r for name, r in by_name.items() if "DataModel_Set_*" in name), None)
    assert name_keyed is not None, f"the generated family was dropped in silence: {list(by_name)}"
    assert "DataModel_Get_*" in name_keyed.name
    assert "below the floor" in name_keyed.reason
    assert "1 key(s) are both written and read" in name_keyed.reason

    # The ByKey dispatchers are a DIFFERENT family, refused for a different
    # reason: their key is an argument, not part of the name.
    by_key = next((r for name, r in by_name.items() if name == "DataModel_Set*"), None)
    assert by_key is not None, list(by_name)
    assert "arity varies" in by_key.reason
    assert "VARIABLE" in by_key.reason


## @brief Rejections reach the rendered draft with their reasons.
## @version 2
def test_rejections_appear_in_the_rendered_draft_with_reasons(
    repo_root: Path, rich_db: Path
) -> None:
    """A refused candidate is part of the deliverable. The candidate an owner
    EXPECTED is exactly the one they go looking for, and without the reason the
    only available conclusion is that clew missed it."""
    proposal = propose(repo_root, rich_db)
    text = proposal.yaml_text
    assert "REJECTED" in text
    assert "DataModel_Set_" in text
    assert "floor" in text
    section = _section(proposal, SECTION_SHARED_KEY)
    assert section.rejections
    for rejection in section.rejections:
        assert rejection.reason, f"{rejection.name} was refused with no reason"
        assert rejection.name in text, f"{rejection.name} never reached the draft"


# ─── a repo with no convention says so, and invents nothing ─────────────────


## @brief A repo with no detectable convention yields an empty but valid draft.
## @version 1
def test_no_convention_yields_an_empty_but_valid_draft_that_says_so(tmp_path: Path) -> None:
    """The failure to avoid is a draft that fills the silence with something
    plausible. With a real index to measure against and nothing to find, every
    section must report a MEASURED absence — `no_candidates`, with the counts that
    make it legible — and the document must contain no activatable YAML at all.

    @brief Nothing detectable produces a measured empty draft, not an invention.
    @version 1
    """
    root = _repo(tmp_path / "plain", _PLAIN_SOURCE)
    db = _index(tmp_path / "plain.db", "src/app.c", [(1, "helper", 1, 5), (2, "main_loop", 7, 10)])

    proposal = propose(root, db)

    shared = _section(proposal, SECTION_SHARED_KEY)
    assert shared.status is SectionStatus.NO_CANDIDATES, shared.reason
    assert shared.checked["families"] == 0
    assert _section(proposal, SECTION_THREADS).status is SectionStatus.NO_CANDIDATES
    assert not any(s.entries for s in proposal.sections)
    assert marked_lines(proposal.yaml_text) == [], "an empty draft must carry no YAML"
    assert uncomment(proposal.yaml_text).strip() == ""
    # ... and it has to SAY so, per section, rather than omitting them.
    assert proposal.yaml_text.count("STATUS:") == len(section_names())


## @brief Without a usable index the gated section refuses instead of guessing.
## @version 1
def test_without_an_index_the_shared_key_section_refuses_to_propose(tmp_path: Path) -> None:
    """An unmeasured shared-key declaration can mint a bipartite blob of
    fabricated causal edges, so the structural filters passing is NOT enough.
    With no index the section must report `not_analysed` — never a guess derived
    from the (perfectly real) call-site evidence it did collect."""
    root, _db = _acme(tmp_path)

    section = _section(propose(root, None), SECTION_SHARED_KEY)

    assert section.status is SectionStatus.NOT_ANALYSED
    assert section.entries == ()
    assert section.checked["arity_consistent_pairs"] >= 1, (
        "the structural filters must still have FOUND the pair — the refusal is "
        "the measurement gate, not a detection failure"
    )


## @brief `--no-dry-run` is fail-closed, not "trust the structure".
## @version 1
def test_no_dry_run_is_fail_closed(tmp_path: Path) -> None:
    """Disabling measurement must remove the proposal, not the gate."""
    root, db = _acme(tmp_path)
    assert _section(propose(root, db), SECTION_SHARED_KEY).status is SectionStatus.PROPOSED
    section = _section(propose(root, db, dry_run=False), SECTION_SHARED_KEY)
    assert section.status is SectionStatus.NOT_ANALYSED
    assert section.entries == ()


# ─── a late-resolving `#if` arm must revise the answer, not be discarded ────


## @brief Build a FuncDef with hand-written forwarding evidence.
## @param name Definition name.
## @param params Parameter identifiers, in declaration order.
## @param forwards Its parameter-forwarding calls.
## @return The FuncDef.
## @version 1
def _fdef(name: str, params: tuple[str, ...], forwards: tuple[ForwardCall, ...]) -> FuncDef:
    """Hand-built rather than parsed: the behaviour under test is the FIXPOINT,
    and feeding it source would make the test depend on the AST layer too.

    @brief An in-scope definition with the given forwarding calls.
    @return The FuncDef.
    @version 1
    """
    return FuncDef(
        name=name,
        rel_path="src/app.c",
        line=1,
        params=params,
        is_macro=False,
        in_scope=True,
        forwards=forwards,
    )


## @brief Build one parameter-forwarding call record.
## @param callee Callee name.
## @param arg_params (argument position, enclosing parameter position) pairs.
## @return The ForwardCall.
## @version 1
def _call(callee: str, arg_params: tuple[tuple[int, int], ...]) -> ForwardCall:
    """@brief A call passing the enclosing definition's parameters through.

    @return The ForwardCall.
    @version 1
    """
    return ForwardCall(callee=callee, line=1, arg_params=arg_params)


## @brief A wrapper's two `#if` arms are folded even when one resolves later.
## @version 1
def test_a_late_resolving_second_arm_revises_the_kind_instead_of_being_dropped() -> None:
    """Measured on a C/POSIX library: `SYSTEM_TASKCREATE` has an ESP-IDF arm
    reaching `xTaskCreate` in ONE hop and a POSIX arm reaching `pthread_create` in
    THREE. The fast arm resolved in round 1; by round 3 the fixpoint could see
    both and would have folded them to `kind: "unknown"` — but the round-1 answer
    was frozen, so the draft proposed `kind: "task"` on a repo that only ever
    compiles the POSIX arm. That is this feature's headline failure: a plausible,
    committed, wrong declaration asserting the wrong OS.

    The disagreement is a property of the DEFINITIONS, not of the order they
    happen to resolve in, so a later round must be allowed to revise an earlier
    answer.

    @brief A slower `#if` arm still reaches the fold.
    @version 1
    """
    known, _refused = resolve_fixpoint(
        {
            # The two macro arms. Arm A is one hop from a seed, arm B is three.
            "ACME_SPAWN": [
                _fdef(
                    "ACME_SPAWN",
                    ("fn", "name", "handle"),
                    (_call("xTaskCreate", ((0, 0), (1, 1))),),
                ),
                _fdef(
                    "ACME_SPAWN",
                    ("fn", "name", "handle"),
                    (_call("acme_posix_spawn", ((0, 0), (1, 1), (2, 2))),),
                ),
            ],
            "acme_posix_spawn": [
                _fdef(
                    "acme_posix_spawn",
                    ("fn", "name", "handle"),
                    (_call("acme_thread_create", ((0, 2), (1, 0), (2, 1))),),
                )
            ],
            "acme_thread_create": [
                _fdef(
                    "acme_thread_create",
                    ("handle", "fn", "name"),
                    (_call("pthread_create", ((0, 0), (2, 1))),),
                )
            ],
            # One hop further out: it must inherit the WITHHELD kind, not the
            # stale one, or the revision stops at the wrapper it was found on.
            "acme_start_worker": [
                _fdef(
                    "acme_start_worker",
                    ("entry", "label"),
                    (_call("ACME_SPAWN", ((0, 0), (1, 1))),),
                )
            ],
        }
    )

    spawn = known["ACME_SPAWN"]
    assert spawn.entry_arg_index == 0, "the arms agree on the entry argument"
    assert spawn.kind == "unknown", f"the arms disagree on kind; got {spawn.kind!r}"
    assert "kind" in spawn.conflicts
    assert "name_arg_index" in spawn.conflicts, "only the RTOS arm names its task"

    downstream = known["acme_start_worker"]
    assert downstream.kind == "unknown", (
        f"the withheld kind must propagate; got {downstream.kind!r}"
    )
    assert "kind" in downstream.conflicts, (
        "a kind withheld upstream must still be EXPLAINED downstream — an "
        'unexplained kind: "unknown" is exactly as unauditable as a wrong one'
    )


# ─── the load-bearing test: the draft parses back to what it claims ─────────


## @brief The rendered draft round-trips through the real declaration loader.
## @version 1
def test_rendered_draft_round_trips_through_load_declaration(tmp_path: Path) -> None:
    """A draft that does not parse is useless, and every emitted line is a
    comment — so the only way to prove the proposal is real is to perform the
    activation an owner would perform and load the result through the SAME code
    path a build uses.

    @brief Activating the draft yields the declaration it claims to propose.
    @version 1
    """
    root, db = _acme(tmp_path)
    proposal = propose(root, db)
    shared = _section(proposal, SECTION_SHARED_KEY)
    assert shared.status is SectionStatus.PROPOSED, shared.reason

    # As written, the draft is inert: the loader sees no sections at all.
    target = tmp_path / "inert"
    target.mkdir()
    (target / DECLARATION_NAME).write_text(proposal.yaml_text, encoding="utf-8")
    assert load_declaration(target) == {}

    # Activated, it parses to exactly the proposed section.
    active = tmp_path / "active"
    active.mkdir()
    (active / DECLARATION_NAME).write_text(uncomment(proposal.yaml_text), encoding="utf-8")
    declared = load_declaration(active)
    assert set(declared) == {SECTION_SHARED_KEY}
    assert declared[SECTION_SHARED_KEY]["writers"] == [{"name_prefix": "ACME_SET_"}]
    assert declared[SECTION_SHARED_KEY]["readers"] == [{"name_prefix": "ACME_GET_"}]


## @brief The same draft round-trips into a build OPTION, not only into a file.
## @version 1
def test_draft_becomes_a_statable_option_without_a_file(tmp_path: Path) -> None:
    """gh#360. The test above proves the draft parses when an owner ACTIVATES IT IN A FILE;
    this proves the other route exists at all. An agent has nowhere to write that file — a
    third-party repo must stay byte-identical, and anywhere else is untracked or `git
    clean`ed — so before this, `propose_declaration` returned prose and `options` took a
    structure, with no path between them.

    ASSERTED AGAINST THE DECLARATION LOADER'S OWN RESULT, so the two vocabularies are pinned
    to each other rather than each to its own idea of the shape. Then driven through the real
    `apply_options`, which is the only check that the proposal survives validation as strict
    as a parsed file's — a statement the validator would refuse is not a route.

    @brief A draft's statement is exactly what a build option accepts.
    @version 1
    """
    from clew.buildoptions import apply_options
    from clew.propose import statement_from_draft

    root, db = _acme(tmp_path)
    proposal = propose(root, db)
    assert _section(proposal, SECTION_SHARED_KEY).status is SectionStatus.PROPOSED

    active = tmp_path / "activated"
    active.mkdir()
    (active / DECLARATION_NAME).write_text(uncomment(proposal.yaml_text), encoding="utf-8")
    statement = statement_from_draft(proposal.yaml_text)

    assert statement == load_declaration(active), "one proposal, two spellings of it"

    args = SimpleNamespace(**dict.fromkeys(statement))
    assert apply_options(args, statement, root) == sorted(statement)
    assert getattr(args, SECTION_SHARED_KEY)["writers"] == [{"name_prefix": "ACME_SET_"}]


## @brief A draft that proposes nothing yields an empty statement, not an error.
## @version 1
def test_a_draft_with_no_candidates_states_nothing(tmp_path: Path) -> None:
    """`{}` is a RESULT — no candidate survived the dry run — and it must not read as a
    failure, because a repository that needs no declaration is the correct negative this
    whole feature has to preserve. An exception here would make "nothing to declare"
    indistinguishable from "the proposer broke".

    @brief An empty draft yields an empty statement.
    @version 1
    """
    from clew.propose import statement_from_draft

    root = tmp_path / "bare"
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")

    proposal = propose(root, None)

    assert marked_lines(proposal.yaml_text) == []
    assert statement_from_draft(proposal.yaml_text) == {}


## @brief Two accepted pairs merge into one writers/readers list, not duplicate keys.
## @version 1
def test_two_accepted_pairs_do_not_collide_into_duplicate_yaml_keys() -> None:
    """`writers:`/`readers:` are two sibling LISTS. Emitting one block per
    accepted pair produced DUPLICATE mapping keys under a single
    `shared_key_patterns:`, and YAML resolves those to the LAST one silently — so
    a second accepted pair would have DELETED the first with no error. Same
    fabrication class as a wrong pattern, arriving through the renderer.

    @brief The section merges its pairs into one writers/readers list.
    @version 1
    """
    pairs = [_pair("A_SET_", "A_GET_"), _pair("B_SET_", "B_GET_")]
    parsed = yaml.safe_load("\n".join(_section_yaml(pairs)))
    assert parsed[SECTION_SHARED_KEY]["writers"] == [
        {"name_prefix": "A_SET_"},
        {"name_prefix": "B_SET_"},
    ]
    assert parsed[SECTION_SHARED_KEY]["readers"] == [
        {"name_prefix": "A_GET_"},
        {"name_prefix": "B_GET_"},
    ]


## @brief A minimal Pair for YAML-shaping tests.
## @param writer Writer family prefix.
## @param reader Reader family prefix.
## @return The Pair.
## @version 1
def _pair(writer: str, reader: str) -> Pair:
    """@brief Build a Pair with empty call-site evidence."""
    keys = frozenset({"X", "Y"})
    return Pair(
        writer=Family(writer, "set", writer, keys, (), ()),
        reader=Family(reader, "get", reader, keys, (), ()),
        shared_keys=keys,
    )


## @brief `uncomment` recovers only the marked lines.
## @version 1
def test_uncomment_recovers_only_the_marked_lines() -> None:
    """The marker exists so prose ABOUT a proposal can never be mistaken for the
    proposal. Anything else in the file is dropped."""
    text = "\n".join(
        [
            "# prose that mentions shared_key_patterns: and must not be parsed",
            YAML_MARKER + "shared_key_patterns:",
            YAML_MARKER + "  writers:",
            YAML_MARKER + '    - name_prefix: "Z_SET_"',
            "#  ── NOTES ──",
        ]
    )
    assert yaml.safe_load(uncomment(text)) == {
        SECTION_SHARED_KEY: {"writers": [{"name_prefix": "Z_SET_"}]}
    }


# ─── the CLI must not clobber a repo's own declaration ─────────────────────


## @brief An existing `.clew.yaml` is never overwritten without --force.
## @version 1
def test_existing_declaration_is_not_overwritten_without_force(tmp_path: Path) -> None:
    """The one file this command is about is the one file it must not clobber:
    replacing a hand-tuned declaration with an all-comments draft DISABLES every
    convention it declared while the build keeps succeeding — a silently different
    answer, which is worse than a crash.

    @brief The output path is refused when it exists, unless --force.
    @version 1
    """
    root, db = _acme(tmp_path)
    declaration = root / DECLARATION_NAME
    original = "shared_key_patterns:\n  writers:\n    - name_prefix: 'HAND_SET_'\n"
    declaration.write_text(original, encoding="utf-8")
    argv = ["--repo-root", str(root), "--db", str(db), "-o", str(declaration)]

    assert propose_main(argv) == 2
    assert declaration.read_text(encoding="utf-8") == original, "the declaration was clobbered"

    assert propose_main([*argv, "--force"]) == 0
    assert declaration.read_text(encoding="utf-8") != original
    assert load_declaration(root) == {}, "the written draft must be inert"


## @brief The draft goes to stdout when no output path is given.
## @version 1
def test_stdout_is_the_default_destination(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """A command that writes into the tree by default turns "show me what you
    would suggest" into an edit."""
    root, db = _acme(tmp_path)
    before = (root / DECLARATION_NAME).read_text(encoding="utf-8")
    assert propose_main(["--repo-root", str(root), "--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert out.lstrip().startswith("#")
    assert (root / DECLARATION_NAME).read_text(encoding="utf-8") == before, (
        "the declaration the repo already carries must come back byte-identical"
    )


## @brief `--ignore-declaration` re-proposes what the repo already declares.
## @version 1
def test_ignore_declaration_re_proposes_a_declared_convention(tmp_path: Path) -> None:
    """An owner auditing a hand-written declaration needs to see whether the
    evidence supports it. With the declaration read, its own entry is (correctly)
    refused as already covered; ignoring it turns the same entry back into a
    measured proposal — which is the audit."""
    root, db = _acme(tmp_path)
    (root / DECLARATION_NAME).write_text(
        "index_scope:\n  roots: [src]\n"
        "shared_key_patterns:\n"
        "  writers:\n    - name_prefix: 'ACME_SET_'\n"
        "  readers:\n    - name_prefix: 'ACME_GET_'\n",
        encoding="utf-8",
    )
    assert _section(propose(root, db), SECTION_SHARED_KEY).status is SectionStatus.NO_CANDIDATES
    audited = _section(propose(root, db, use_declaration=False), SECTION_SHARED_KEY)
    assert audited.status is SectionStatus.PROPOSED
    assert audited.entries[0].measured["new_edges"] > 0


# ─── refusing a database that is not one ────────────────────────────────────


## @brief A file that is not a clew index is rejected, not crashed on.
## @version 1
def test_a_zero_byte_docs_db_is_rejected_rather_than_crashed_on(tmp_path: Path) -> None:
    """`<repo>/clew.db` is part of the discovery order, and a zero-byte leftover
    of that name really does sit in this repo's own sample tree. The dry run calls
    pipeline importers that select straight from `memberdef`, so an index that is
    not one used to reach an `OperationalError` mid-analysis.

    @brief An unusable index degrades to "no index", with the defect named.
    @version 1
    """
    root = _repo(tmp_path / "bogus", _ACME_SOURCE)
    empty = root / "clew.db"
    empty.write_bytes(b"")
    assert index_defect(empty)

    proposal = propose(root, empty)

    assert proposal.db_status["exists"] is True
    assert proposal.db_status["usable"] is False
    assert _section(proposal, SECTION_SHARED_KEY).status is SectionStatus.NOT_ANALYSED
    assert "REJECTED" in proposal.yaml_text
    assert "memberdef" in proposal.yaml_text


## @brief A hand-declared section reports as declared, not as undetected.
## @version 1
def test_a_declared_hand_section_is_reported_as_already_declared(tmp_path: Path) -> None:
    """`locks:` has no detector by design. When the repo declares one anyway, the
    draft must confirm clew SEES it — otherwise the same "not analysed" text
    appears whether or not the owner has already done the work."""
    root = _repo(tmp_path / "declared", _PLAIN_SOURCE)
    (root / DECLARATION_NAME).write_text(
        "locks:\n  - name: AcmeGuard\n    form: raii\n", encoding="utf-8"
    )
    proposal = propose(root, None)
    assert _section(proposal, SECTION_LOCKS).status is SectionStatus.ALREADY_DECLARED
    assert _section(proposal, SECTION_MQTT).status is SectionStatus.NOT_ANALYSED


## @brief A non-C/C++ indexed scope reports NOT_APPLICABLE, not a measured absence.
## @version 1
def test_a_non_c_indexed_scope_is_not_applicable_not_no_candidates(tmp_path: Path) -> None:
    """The parser router covers Python as well as C/C++, so a Python file PARSES —
    and then contributes nothing, because a Python `function_definition` has no
    `declarator` chain and its calls are `call`, not `call_expression`. Counting
    parses would report a Python codebase as a MEASURED empty C repo: a claim about
    the repo, where the truth is a claim about the detector. clew's own indexed
    scope is exactly this case, so it is not hypothetical.

    @brief The blocking check is language-aware, not parse-count-aware.
    @version 1
    """
    root = tmp_path / "pyrepo"
    (root / "src").mkdir(parents=True)
    (root / ".clew.yaml").write_text("index_scope:\n  roots: [src]\n", encoding="utf-8")
    (root / "src" / "app.py").write_text("def main():\n    return 0\n", encoding="utf-8")

    proposal = propose(root, None)

    assert proposal.scope["files_in_scope"] >= 1, "the Python file must be IN scope"
    assert proposal.scope["ast_readable_in_scope"] == 0
    for name in (SECTION_SHARED_KEY, SECTION_THREADS):
        section = _section(proposal, name)
        assert section.status is SectionStatus.NOT_APPLICABLE, f"{name}: {section.reason}"
        assert "not a measurement of the repo" in section.reason


## @brief An undeclared index scope blocks detection instead of proposing vendor code.
## @version 1
def test_an_undeclared_scope_blocks_detection_rather_than_guessing(tmp_path: Path) -> None:
    """Without a derived scope clew has no notion of first-party, and the first
    thing a detector proposes is a vendored library's own helper. The gate must
    report that as un-analysed rather than as an empty measurement."""
    root = tmp_path / "unscoped"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.c").write_text(_ACME_SOURCE, encoding="utf-8")
    proposal = propose(root, None)
    section = _section(proposal, SECTION_SHARED_KEY)
    assert section.status is SectionStatus.NOT_ANALYSED
    assert "NOT DERIVED" in proposal.yaml_text
    assert "first-party" in section.reason.lower() or "FIRST-PARTY" in section.reason


# ─── the MCP surface ────────────────────────────────────────────────────────


## @brief The MCP tool returns a draft without ever writing to stdout.
## @version 2
def test_mcp_propose_returns_a_draft_and_keeps_stdout_clean(tmp_path: Path) -> None:
    """On the MCP server `sys.stdout` IS the protocol transport, and every dry run
    re-runs a pipeline importer that renders a rich progress bar. Spliced into the
    JSON-RPC stream those bars corrupt the framing, so the proposer runs with its
    output bound to a buffer instead.

    Written against the OUTCOME rather than the mechanism: the draft comes back, and
    nothing reached this process's stdout. That holds however the silencing is done,
    which is what makes it a regression guard rather than a restatement.

    @brief The tier-0 propose tool is transport-safe.
    @version 2
    """
    pytest.importorskip("mcp", reason="the MCP surface needs the optional mcp extra")
    from clew.mcp_server.server import DocsDbServer
    from clew.mcp_server.state import Target

    root, db = _acme(tmp_path)
    target = Target(repo_path=str(root), slug="acme-test", db_path=str(db))

    with _captured_stdout() as leaked:
        result = DocsDbServer.__new__(DocsDbServer)._run_propose(target, False)

    assert result["ok"] is True, result
    assert result["measured_against"] == str(db)
    assert result["draft"].lstrip().startswith("#")
    assert SECTION_SHARED_KEY in result["draft"]
    assert leaked.getvalue() == "", "the proposer must never write to this stdout"


## @brief Capture anything written to the real stdout for the duration of a block.
## @return Context manager yielding the capture buffer.
## @version 1
@contextlib.contextmanager
def _captured_stdout():
    """@brief Trap writes to sys.stdout so a leak is observable."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        yield buffer


## @brief index_scope is report-only and never emits YAML.
## @version 2
def test_index_scope_is_report_only(tmp_path: Path) -> None:
    """`index_scope.roots` REPLACES the scope rather than extending it, so an owner
    who activates a proposed root narrows the index to exactly that root and DELETES
    everything the other tiers covered — and the build logs that as a success. There
    is no safe emission.

    @brief The index_scope section reports and never emits YAML.
    @version 2
    """
    root, db = _acme(tmp_path)
    section = _section(propose(root, db), INDEX_SCOPE_SECTION)
    assert section.status is SectionStatus.REPORT_ONLY
    assert section.yaml_header == ()
    assert section.entries == ()
    assert any("REPLACES the scope" in note for note in section.notes)
