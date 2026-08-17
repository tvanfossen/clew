# SPDX-License-Identifier: MIT
"""A guard config from a DIFFERENT doxygen-guard release still supplies our keys.

gh#32. A target's `.doxygen-guard.yaml` is written against whatever doxygen-guard
release that repo pins; we parse it with whatever release this package pins. Those
are independent decisions by independent repos, so a document we cannot fully parse
is the NORMAL case at scale — and `load_config` is a gate's loader that refuses the
whole document over one unrecognised key.

Observed on a real target: the config was found (gh#16) and then discarded over
`validate.presence.skip_forward_declarations`, valid in the 1.2.9 that target gates
with and absent from the schema we import. Every value we wanted was present and
parseable. Net effect was gh#16's own failure mode restored — the `@req` id pattern,
the catalog mapping and the whole `x-clew` passthrough back on built-in
defaults for a repo that had declared all three.

These tests pin what absence had: the keys we read survive an unknown key elsewhere,
the diagnosis names BOTH versions rather than blaming the author, and the strict
severity is still available for the consumer whose own typo is worth failing over.

@brief Version-skew tolerance of the guard-config read.
@version 1
"""

from __future__ import annotations

import logging
from pathlib import Path

from clew.declaration import load_declaration
from clew.requirements import load_guard_config, resolve_req_id_pattern

## The offending key is VERBATIM from the real target that produced gh#32. It sits
## under a section the schema DOES know (`validate.presence`), so a salvage that
## dropped the parent would silently discard that section's real settings too.
_SKEW_KEY = "skip_forward_declarations"

## The fixture's requirement id is a sanctioned placeholder rather than a freshly
## invented one. A publishability gate used to reject an unlisted id because it cannot
## tell an invented id from another project's; that gate is DELETED and NOTHING now
## checks this file for a foreign requirement id. The convention is kept by hand.
##
## A config declaring, in one document: a key from another release, the `@req` id
## pattern we read, the catalog file we read, and the passthrough that carries this
## tool's entire declaration. All four together, because the defect was that ONE
## unknown key cost all three of the others.
_SKEWED_CONFIG = f"""\
validate:
  presence:
    require_doxygen: true
    {_SKEW_KEY}: true
  tags:
    req:
      pattern: '^REQ-X-[A-Z]+-[0-9]{{3}}$'
impact:
  requirements:
    file: requirements.yaml
x-clew:
  index_scope:
    roots: ['src']
"""

## The rev this fictional target pins. Deliberately NOT the version this package
## imports — the whole point is that the two differ and the report says so.
_PINNED_REV = "v1.2.9"


## @brief Write a skewed guard config and a pre-commit config pinning a rev.
## @param root Repo root to write into.
## @return The written guard-config path.
## @version 1
## @dg_internal
def _write_skewed_repo(root: Path) -> Path:
    """The pre-commit config exists so the skew report can name the target's OWN
    pinned release. Without it the report has only our half of the story, which is
    the half that reads as the author's mistake.

    @brief Write a repo whose guard config is from another doxygen-guard release.
    @return Path to the guard config.
    @version 1
    """
    (root / "src").mkdir(exist_ok=True)
    (root / "requirements.yaml").write_text(
        "requirements:\n  REQ-X-FOO-001:\n    name: A requirement\n", encoding="utf-8"
    )
    (root / ".pre-commit-config.yaml").write_text(
        "repos:\n"
        "  - repo: https://github.com/tvanfossen/doxygen-guard\n"
        f"    rev: {_PINNED_REV}\n"
        "    hooks:\n"
        "      - id: doxygen-guard\n"
        "        files: ^src/.*\\.c$\n",
        encoding="utf-8",
    )
    path = root / ".doxygen-guard.yaml"
    path.write_text(_SKEWED_CONFIG, encoding="utf-8")
    return path


## @brief An unknown key elsewhere must not cost the keys we DO read.
## @version 1
def test_unknown_key_does_not_discard_the_declared_req_pattern(tmp_path: Path) -> None:
    """The `@req` id pattern is the load-bearing one: with it lost, `req_edges` are
    built against the permissive built-in default, so a target's declared id shape
    stops being enforced and nothing says so.

    @brief A skewed config still yields the declared @req pattern.
    @version 1
    """
    config = _write_skewed_repo(tmp_path)

    cfg = load_guard_config(config, tmp_path)

    assert cfg is not None, "a config we can read every wanted key from must not be discarded"
    assert resolve_req_id_pattern(cfg).pattern == "^REQ-X-[A-Z]+-[0-9]{3}$", (
        "the declared @req id pattern was present and parseable — losing it to an "
        "unrelated key is the no-hardcoding mandate's worst case"
    )
    assert cfg["impact"]["requirements"]["file"] == "requirements.yaml", (
        "the catalog declaration was in the same document and must survive with it"
    )
    assert cfg["validate"]["presence"]["require_doxygen"] is True, (
        "the salvage must drop the unknown KEY, not its section's real settings"
    )


## @brief The whole x-clew passthrough must survive a skewed document.
## @version 1
def test_unknown_key_does_not_discard_the_passthrough_declaration(tmp_path: Path) -> None:
    """The passthrough carries this tool's ENTIRE declaration — `index_scope` among
    it — so one unknown key used to decide which files a target gets indexed.

    @brief A skewed config still yields the x-clew declaration.
    @version 1
    """
    _write_skewed_repo(tmp_path)

    declaration = load_declaration(tmp_path)

    assert declaration.get("index_scope") == {"roots": ["src"]}, (
        "the passthrough is the mechanism that exists to carry our declarations; a "
        "key from another release must not silence it"
    )


## @brief The diagnosis must name both versions and the key, not blame the author.
## @version 1
def test_skew_is_reported_with_both_versions_and_the_offending_key(tmp_path: Path, caplog) -> None:
    """ "Unknown config key" alone reads as the target author's mistake. It is not:
    their key is valid for the release their gate runs and unknown to the release
    this index imports, which only a message stating both can convey.

    @brief The skew report names the pinned rev, the imported version and the key.
    @version 1
    """
    ## Read INDEPENDENTLY of the code under test. Asserting
    ## `guardconfig.imported_guard_version() in report` would pass while both were the
    ## string "unknown" — a test green because two wrongs agreed.
    from importlib.metadata import version

    ours = version("doxygen-guard")
    config = _write_skewed_repo(tmp_path)

    with caplog.at_level(logging.WARNING):
        load_guard_config(config, tmp_path)

    reports = [rec.message for rec in caplog.records if "SKEW" in rec.message]
    assert reports, "a version skew reported as a bare unknown-key error is a wrong diagnosis"
    report = reports[0]
    assert _PINNED_REV in report, "the report must name the release the TARGET pins"
    assert ours in report, "the report must name the release WE import"
    assert _SKEW_KEY in report, "the report must name the key that was not recognised"


## The rev of an UNRELATED hook that sits ahead of the guard hook. Distinct from
## `_PINNED_REV` and deliberately alphabetically earlier, so neither "took the first
## entry" nor "took the smallest" can be mistaken for "matched by id".
_DECOY_REV = "v0.0.1"


## @brief A decoy hook ahead of the guard hook must not supply the pinned rev.
## @param tmp_path Per-test temporary directory.
## @return None.
## @version 1
def test_the_pinned_rev_is_matched_BY_ID_not_taken_from_the_first_repo(tmp_path: Path) -> None:
    """MEASURED, and this is the whole reason the test exists (gh#329): stripping the
    `h.get("id") == GUARD_HOOK_ID` comparison out of `pinned_guard_rev`, so it accepts ANY
    hook, left the entire suite green at 867 passed. The same mutation against
    `_find_guard_hook` kills two tests — one rule, two copies, and only one defended.

    THE CAUSE WAS THE FIXTURE, not the assertion. `_write_skewed_repo` writes the guard
    hook as the only hook in the only repo entry, so "matched by id" and "took the first
    one" produce the same answer and no test could tell them apart. A real
    `.pre-commit-config.yaml` has several entries — this repo's own has five ahead of
    nothing, and most targets put `ruff` or `trailing-whitespace` first.

    It also calls `pinned_guard_rev` DIRECTLY. Every existing test reaches it only through
    the skew report's message, so the rev was asserted as a substring of prose; a function
    reached only transitively is defended only as far as its caller happens to look.

    @brief The guard rev is matched by hook id, not by position.
    @version 1
    """
    from clew.precommit import pinned_guard_rev

    (tmp_path / ".pre-commit-config.yaml").write_text(
        "repos:\n"
        "  - repo: https://github.com/astral-sh/ruff-pre-commit\n"
        f"    rev: {_DECOY_REV}\n"
        "    hooks:\n"
        "      - id: ruff\n"
        "      - id: ruff-format\n"
        "  - repo: https://github.com/tvanfossen/doxygen-guard\n"
        f"    rev: {_PINNED_REV}\n"
        "    hooks:\n"
        "      - id: doxygen-guard\n",
        encoding="utf-8",
    )

    assert pinned_guard_rev(tmp_path) == _PINNED_REV, (
        "the rev must come from the repo entry carrying the doxygen-guard hook; taking "
        "the first entry's rev reports a completely unrelated project's release as the "
        "one this target gates with"
    )


## @brief A guard hook with no rev pins nothing, and says so as None.
## @param tmp_path Per-test temporary directory.
## @return None.
## @version 1
def test_a_local_guard_hook_pins_nothing_and_that_is_an_answer(tmp_path: Path) -> None:
    """`repo: local` carries no `rev:`, which is the documented None case — and the decoy
    is what makes this test worth writing rather than trivial. With an unrelated pinned
    hook present, a position-based read returns the DECOY's rev here, confidently naming a
    version this target does not gate with at all. So the two tests fail on the same defect
    from opposite directions: one by returning the wrong string, one by returning a string
    where None is correct.

    @brief A local guard hook yields None even when another hook is pinned.
    @version 1
    """
    from clew.precommit import pinned_guard_rev

    (tmp_path / ".pre-commit-config.yaml").write_text(
        "repos:\n"
        "  - repo: https://github.com/astral-sh/ruff-pre-commit\n"
        f"    rev: {_DECOY_REV}\n"
        "    hooks:\n"
        "      - id: ruff\n"
        "  - repo: local\n"
        "    hooks:\n"
        "      - id: doxygen-guard\n"
        "        entry: .venv/bin/doxygen-guard\n"
        "        language: system\n",
        encoding="utf-8",
    )

    assert pinned_guard_rev(tmp_path) is None, (
        "a local hook pins nothing; reporting a neighbour's rev would attribute a version "
        "to a target that deliberately states none"
    )


## @brief A clean config still loads through upstream's own loader, unchanged.
## @version 1
def test_a_clean_config_is_untouched_by_the_permissive_path(tmp_path: Path, caplog) -> None:
    """The permissive read must be invisible on the common path: no skew reported,
    upstream's defaults merged exactly as before. A tolerance that changes the clean
    case is a behaviour change wearing a bug fix's clothes.

    @brief A config with no unknown keys reports no skew.
    @version 1
    """
    config = tmp_path / ".doxygen-guard.yaml"
    config.write_text("validate:\n  tags:\n    req:\n      pattern: '^REQ-[0-9]+$'\n", "utf-8")

    with caplog.at_level(logging.WARNING):
        cfg = load_guard_config(config, tmp_path)

    assert cfg is not None and resolve_req_id_pattern(cfg).pattern == "^REQ-[0-9]+$"
    assert not [rec for rec in caplog.records if "SKEW" in rec.message], (
        "nothing was skewed, so nothing may be reported as skewed"
    )


## @brief The strict severity is still available, and still reports the skew.
## @version 1
def test_strict_mode_still_refuses_and_still_names_the_skew(tmp_path: Path, caplog) -> None:
    """Strict belongs to the GATE and permissive to the INDEX — the same split this
    project draws between gate scope and index scope. A silently-ignored typo in
    one's OWN config is the failure strictness prevents, so the severity stays
    reachable; what changes is that even a refusal names both releases, because
    "unknown config key" was never the right diagnosis for a skew.

    @brief strict=True refuses the document but reports it as a skew.
    @version 1
    """
    from clew.guardconfig import read_guard_config

    config = _write_skewed_repo(tmp_path)

    with caplog.at_level(logging.WARNING):
        read = read_guard_config(config, tmp_path, strict=True)

    assert not read.usable(), "strict mode must refuse the document, as the gate does"
    assert read.skew and _PINNED_REV in read.skew and _SKEW_KEY in read.skew, (
        "a refusal still has to say WHICH releases disagree and over what"
    )
    assert read.unknown_keys == (f"validate.presence.{_SKEW_KEY}",), (
        "the unrecognised key is reported to the caller, not only logged"
    )


## @brief A malformed value is NOT salvaged — it may be a value we read.
## @version 1
def test_a_type_error_is_still_refused(tmp_path: Path, caplog) -> None:
    """Permissiveness is scoped to unknown KEYS. A type mismatch is a statement
    about a VALUE, and the value may be one we read, so it is refused exactly as
    before — and reported as a config error rather than dressed up as somebody
    else's version pin.

    @brief A schema type violation still degrades to built-in defaults.
    @version 1
    """
    config = tmp_path / ".doxygen-guard.yaml"
    ## An unknown key AND a type error in one document. The unknown key alone would
    ## refuse trivially (there is nothing to salvage past the type error), so the
    ## interesting case is the one where salvage LOOKS available and must not be taken.
    config.write_text(
        f"validate:\n  exclude: 'not-a-list'\n  presence:\n    {_SKEW_KEY}: true\n",
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING):
        cfg = load_guard_config(config, tmp_path)

    assert cfg is None, "a genuinely invalid document must not be half-read"
    assert any("INVALID" in rec.message for rec in caplog.records), (
        "a real config error must read as a config error, not as a version skew"
    )
    assert not any("SKEW" in rec.message for rec in caplog.records), (
        "calling an author's type error a version skew sends them to the wrong place"
    )
