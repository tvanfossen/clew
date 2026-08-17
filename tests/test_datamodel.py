# SPDX-License-Identifier: MIT
"""gh#351: the tier-4 data-model manifest reader.

EVERY MECHANISM HERE HAS A MUTATION CONTROL, because the two that matter most are both
green-for-the-wrong-reason shaped. The selection gate is the sharper one: a test asserting
"the repository's own manifest is admitted" passes with the gate deleted, since without a
gate everything is admitted. So the negative half — the vendored generator's EXAMPLE manifest
must NOT be admitted — is what actually pins it, and it is written here beside the positive
half rather than assumed.

The composition rule has the same shape one level down. `define_name` is verified against a
target's own key list in the field (135 of 135, where the obvious underscore-stripping rule
scored 104), and what a unit test can add is the two characters that discriminate: an
underscore already inside a segment must SURVIVE, and a space must not.

THE SECOND DIALECT ADDS A THIRD SHAPE OF GREEN-FOR-THE-WRONG-REASON, and the fixture is built
against it. Its keys carry defaults this index deliberately does not resolve, so an
implementation that simply marked EVERY UDM key unresolved would satisfy any test written only
against a key that declares one. The fixture therefore carries a key declaring NO default at
all, and that key is what the assertion turns on — the same reason the vendored-example
manifest sits beside the repository's own.

@brief Tests for the data-model manifest reader.
@version 2
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew.datamodel import (
    DIALECT_INGOT,
    DIALECT_UDM,
    define_name,
    discover,
    import_data_model_keys,
    parse_ingot_manifest,
    parse_udm_manifest,
    read_key_list,
)
from tests.gitfixture import repo_with_submodules

## A minimal manifest in the read dialect. Two classes so a class count is not also the
## manifest count, and one key carrying an underscore so the composition rule is exercised by
## the fixture rather than only by its own unit test.
MANIFEST = """
[meta]
id = "widgetbus"
version = "1.0.0"

[[classes]]
id = "telemetry"

    [[classes.keys]]
    id = "SampleRate"
    type = "uint16"
    default = 255
    helpers = true

    [[classes.keys]]
    id = "Is_Charging"
    type = "bool"
    default = false
    helpers = true
    enum = "widget_mode"

[[classes]]
id = "tuning"

    [[classes.keys]]
    id = "Threshold"
    type = "uint8"
    default = 0
    helpers = false
"""

## The three names MANIFEST declares, as the generator would spell them.
DEFINES = (
    "WIDGETBUS_TELEMETRY_SAMPLERATE",
    "WIDGETBUS_TELEMETRY_IS_CHARGING",
    "WIDGETBUS_TUNING_THRESHOLD",
)

## A manifest of the same shape belonging to somebody else — the generator's shipped example.
## Its namespace is what makes its composed names disjoint from any list the repository writes.
EXAMPLE_MANIFEST = """
[meta]
id = "demo"

[[classes]]
id = "sample"

    [[classes.keys]]
    id = "Widget"
    type = "uint8"
    default = 1
"""

## Ordinary project TOML carrying a TOP-LEVEL `classes` list, deliberately. The first version
## of this fixture put `classes` under `[tool.something]`, where `doc.get("classes")` returns
## None — so the document was declined by the `isinstance(..., list)` check and the shape gate
## was never reached. The mutation control caught that: deleting the gate left the test
## passing. A fixture that does not reach the mechanism it names is the exact green-for-the-
## wrong-reason shape the controls exist to find, and it was found here rather than reasoned
## about.
NOT_A_MANIFEST = """
enabled = true
classes = ["a", "b"]

[tool.something]
level = 3
"""

## A manifest in the SECOND dialect. Shares no field name with the first below the top level,
## which is the measured reason one parser does not cover both.
##
## Every discriminating case the real corpus contains is here on purpose, because the three
## key states are what a bare NULL cannot tell apart:
##   - a key with a BASE default AND a per-variant sibling (unresolvable, and the reason the
##     base is not stored);
##   - a key with an `enum_set`, whose value is a variant-to-inlined-member map with no name
##     anywhere in it, so no `enum_name` column can honestly hold anything;
##   - a key declaring NEITHER, which must come back with an EMPTY unresolved-field set.
## The int `id` on the class and on one key is here to be IGNORED: 4 of 233 classes and 14 of
## 1,606 keys in the measured corpus carry one, and the NAME is the identity.
UDM_MANIFEST = """
namespace: widgetbus
classes:
  - name: telemetry
    id: 4
    data:
      - name: Sample of Rate
        id: 11
        generate_helpers: true
        read_only: false
        type:
          mem: uint16
          default_value:
            default: 99
            default_othervariant: 7
      - name: Mode_Select
        generate_helpers: false
        type:
          mem: uint8
          default_value:
            default: 1
        enum_set:
          default:
            MODE_OFF: "0"
            MODE_ON: "1"
      - name: Uptime
        generate_helpers: true
        type:
          mem: uint32
"""

## The three names UDM_MANIFEST declares, as the generator would spell them. The first is the
## one that pins the composition rule across dialects: its manifest name carries SPACES, and
## the accessor drops them rather than underscoring them.
UDM_DEFINES = (
    "WIDGETBUS_TELEMETRY_SAMPLEOFRATE",
    "WIDGETBUS_TELEMETRY_MODE_SELECT",
    "WIDGETBUS_TELEMETRY_UPTIME",
)


## @brief Write a repository fixture carrying manifests and an optional key list.
## @param root Directory to build in.
## @param manifests Filename to manifest text.
## @param listed Define names to write into a key list, or None for no list at all.
## @return The repository root.
## @version 1
def _repo(root: Path, manifests: dict[str, str], listed: tuple[str, ...] | None) -> Path:
    """Writes the key list under a name that says NOTHING about its role, because the reader
    recognises a list by shape and must not be able to fall back on a filename.

    @brief Build a data-model repository fixture.
    @return The repository root.
    @version 1
    """
    model = root / "conf" / "datamodel"
    model.mkdir(parents=True, exist_ok=True)
    for name, text in manifests.items():
        (model / name).write_text(text, encoding="utf-8")
    if listed is not None:
        body = "---\n" + "".join(f"- {name}\n" for name in listed)
        (model / "some_list.yaml").write_text(body, encoding="utf-8")
    return root


## @brief An underscore inside a segment SURVIVES composition.
## @return None.
## @version 1
def test_define_name_preserves_an_underscore() -> None:
    """THE MEASURED RULE, and the one an obvious reading gets wrong. Stripping every
    non-alphanumeric character scored 104 of 135 against a real target's own key list; keeping
    underscores scored 135. Both the segment and the separator underscores appear here, so a
    rule that dropped either is caught.

    MUTATION: add `_` to `_DROPPED_FROM_SEGMENT`'s character class in `datamodel.py`. This
    test fails, reporting `ALERTS_GROUP_TELEMETRY_ISCHARGING`.

    @brief Underscores inside a manifest segment survive.
    @version 1
    """
    assert define_name("alerts_group", "telemetry", "Is_Charging") == (
        "ALERTS_GROUP_TELEMETRY_IS_CHARGING"
    )


## @brief A space inside a key name is DROPPED, not turned into an underscore.
## @return None.
## @version 1
def test_define_name_drops_a_space() -> None:
    """The other discriminating character. The unread dialect writes key names with spaces
    ("Sample of Rate"), and a repository's key list spells that key with the spaces GONE
    rather than underscored — so a rule that mapped every separator to `_` would compose a
    name no accessor carries and every key would read as never observed.

    MUTATION: change `_DROPPED_FROM_SEGMENT` to `[^0-9A-Za-z_ ]+`, keeping spaces. This test
    fails with a space in the composed name.

    @brief Spaces are removed rather than underscored.
    @version 1
    """
    assert define_name("widgetbus", "telemetry", "Sample of Rate") == (
        "WIDGETBUS_TELEMETRY_SAMPLEOFRATE"
    )


## @brief The shape gate declines ordinary project TOML.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_ordinary_toml_is_declined(tmp_path: Path) -> None:
    """The SUCCESS half is `test_manifest_is_parsed` below; this is the half that pins the
    gate. `NOT_A_MANIFEST` carries a TOP-LEVEL `classes` list on purpose, so a gate that
    checked only for that key's presence and its type admits it and this test fails. See the
    fixture's own note: the first version nested that key and therefore tested nothing.

    MUTATION: in `parse_ingot_manifest`, drop the `_is_ingot_class_list(classes)` conjunct.
    This test fails — the lint config parses as a manifest declaring nothing.

    @brief Ordinary TOML is not a manifest.
    @version 1
    """
    path = tmp_path / "pyproject.toml"
    path.write_text(NOT_A_MANIFEST, encoding="utf-8")
    assert parse_ingot_manifest(path, tmp_path) is None


## @brief A manifest parses to its declared keys, with metadata and a relative path.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_manifest_is_parsed(tmp_path: Path) -> None:
    """Asserts the per-key metadata as well as the names, because the metadata IS the second
    of the three gains and nothing else in the index carries a key's type or default.

    The path assertion is not cosmetic: anything reachable over MCP is published, and an
    absolute manifest path here would reintroduce the machine-layout disclosure that forced an
    earlier build-version bump.

    MUTATION: in `parse_ingot_manifest`, replace `rel_key(path, repo_root)` with `str(path)`.
    The relative-path assertion fails.

    @brief A manifest's keys and metadata are read.
    @version 1
    """
    path = tmp_path / "widgetbus.toml"
    path.write_text(MANIFEST, encoding="utf-8")
    keys = parse_ingot_manifest(path, tmp_path)
    assert keys is not None
    assert tuple(k.define_name for k in keys) == DEFINES
    charge = next(k for k in keys if k.key_id == "Is_Charging")
    assert (charge.value_type, charge.default_value, charge.enum_name) == (
        "bool",
        "False",
        "widget_mode",
    )
    assert charge.helpers is True
    assert charge.dialect == DIALECT_INGOT
    assert not Path(charge.manifest).is_absolute()
    assert charge.manifest == "widgetbus.toml"


## @brief A boolean default stays a boolean, not a zero.
## @return None.
## @version 1
def test_false_default_is_not_zero(tmp_path: Path) -> None:
    """A boolean default and a numeric zero default are different facts about a key, and
    `str(False)` is not `"0"`. The `Threshold` key's default IS `0`, so the two appear in one
    fixture and a coercion that flattened them together is visible.

    MUTATION: in `_scalar`, return `str(int(value))` for a bool. This test fails.

    @brief False and 0 are distinguishable defaults.
    @version 1
    """
    path = tmp_path / "widgetbus.toml"
    path.write_text(MANIFEST, encoding="utf-8")
    keys = parse_ingot_manifest(path, tmp_path)
    assert keys is not None
    by_id = {k.key_id: k.default_value for k in keys}
    assert by_id["Is_Charging"] == "False"
    assert by_id["Threshold"] == "0"


## @brief A key list is recognised by shape; a path list and a word list are not.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("---\n- WIDGETBUS_TELEMETRY_SAMPLERATE\n- FOO_BAR_BAZ\n", 2),
        ("---\n- models/alpha/alpha_001.yaml\n- models/beta/beta_001.yaml\n", None),
        ("---\n- alpha\n- beta\n", None),
        ("---\nkeys:\n  - FOO_BAR_BAZ\n", None),
        ("--- []\n", None),
    ],
)
def test_key_list_recognition(tmp_path: Path, body: str, expected: int | None) -> None:
    """THE LOOSENING THAT WOULD BE INVISIBLE. A relaxed entry pattern still recognises the
    real key list, so the positive case cannot detect it — what detects it is the manifest-set
    selection file (a sequence of PATHS, which the other generator ships) being mistaken for a
    key list, at which point every shape-matching manifest in the tree is vouched for by names
    that are really file paths.

    MUTATION: relax `_LIST_ENTRY` to `^.+$`. The path-list and word-list cases fail.

    @brief Only a flat sequence of define-name tokens is a key list.
    @version 1
    """
    path = tmp_path / "candidate.yaml"
    path.write_text(body, encoding="utf-8")
    names = read_key_list(path)
    assert (None if names is None else len(names)) == expected


## @brief A repository's own manifest is admitted and the generator's example is not.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_selection_admits_only_what_a_key_list_vouches_for(tmp_path: Path) -> None:
    """BOTH HALVES IN ONE TEST, because separated they mislead. The positive half passes with
    the gate deleted (everything is admitted), and the negative half passes if the parser is
    broken (nothing is admitted). Asserting the SPLIT — one in, one out, and the refusal
    counted — is what cannot be satisfied by either failure.

    MUTATION: in `_select`, drop the `if not any(key.define_name in listed ...)` branch. This
    test fails: the example's key appears and `manifests_unlisted` is 0.

    @brief Selection separates the repository's model from a shipped example.
    @version 1
    """
    root = _repo(
        tmp_path,
        {"widgetbus.toml": MANIFEST, "example.toml": EXAMPLE_MANIFEST},
        DEFINES,
    )
    found = discover(root)
    assert {k.define_name for k in found.keys} == set(DEFINES)
    assert found.manifests == ("conf/datamodel/widgetbus.toml",)
    assert found.manifests_unlisted == 1
    assert found.list_count == 1


## @brief With no key list at all, nothing is selected and the refusal is counted.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_no_key_list_selects_nothing_and_says_so(tmp_path: Path) -> None:
    """FAIL CLOSED, and the COUNT is the whole value. Zero keys on its own is
    indistinguishable from a repository with no data model; zero keys beside
    `manifests_unlisted == 1` says a manifest was found and nothing vouched for it, which an
    operator can act on.

    MUTATION: in `_select`, count the refusal without the `continue` (i.e. admit it anyway).
    This test fails on the key count.

    @brief A manifest with no key list contributes nothing, visibly.
    @version 1
    """
    root = _repo(tmp_path, {"widgetbus.toml": MANIFEST}, None)
    found = discover(root)
    assert found.keys == ()
    assert found.manifests_unlisted == 1
    assert found.list_count == 0
    assert found.as_meta()["manifests_unlisted"] == "1"
    assert found.as_meta()["keys"] == "0"


## @brief A repository with no data model is a correct negative, not an error.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_no_data_model_is_a_correct_negative(tmp_path: Path) -> None:
    """Most repositories have no generated data model, and the two public control targets are
    both in this state. Raising here would turn the stage into a gate on a feature nobody
    asked for — and the recorded zeros are what make the answer a measurement.

    @brief No data model yields an empty set and no exception.
    @version 1
    """
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.c").write_text("int main(void){return 0;}\n", encoding="utf-8")
    found = discover(tmp_path)
    assert found.keys == ()
    assert found.manifests_unlisted == 0
    assert found.as_meta()["dialect"] == ""
    assert found.as_meta()["keys"] == "0"


## @brief A manifest inside a nested dependency tree is excluded by its TREE.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_submodules_manifest_is_excluded(tmp_path: Path) -> None:
    """The generator itself is a dependency, and its examples come with it. Excluding them by
    the TREE that owns them rather than by a directory NAME is the rule this repository already
    holds: `vendor/` and `examples/` are conventions, a git tree is a fact.

    The fixture gives the nested tree its OWN key list naming its own keys, so the selection
    gate alone would admit it. Only the tree exclusion can decline it, which is exactly what
    makes this test pin that mechanism rather than the gate.

    MUTATION: in `_candidates`, drop the `any(path.is_relative_to(tree) ...)` filter. This test
    fails — the dependency's key appears.

    @brief A nested dependency tree's manifests are not the repository's model.
    @version 1
    """
    root = repo_with_submodules(tmp_path, "deps/generator")
    _repo(tmp_path, {"widgetbus.toml": MANIFEST}, DEFINES)
    vendored = tmp_path / "deps" / "generator" / "examples"
    vendored.mkdir(parents=True, exist_ok=True)
    (vendored / "demo.toml").write_text(EXAMPLE_MANIFEST, encoding="utf-8")
    (vendored / "its_list.yaml").write_text("---\n- DEMO_SAMPLE_WIDGET\n", encoding="utf-8")
    found = discover(root)
    assert {k.define_name for k in found.keys} == set(DEFINES)
    assert "DEMO_SAMPLE_WIDGET" not in {k.define_name for k in found.keys}


## @brief The second dialect parses to its declared keys, with its OWN field mapping.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_udm_manifest_is_parsed(tmp_path: Path) -> None:
    """EVERY FIELD NAME HERE DIFFERS FROM THE OTHER DIALECT'S, which is the whole argument for
    a second parser: `namespace` not `meta.id`, `name` not `id`, `data` not `keys`, and the type
    one level down at `type.mem` rather than a flat `type`. A mapping table shared with the
    ingot parser would have to guess which spelling it was looking at.

    MUTATION: in `_udm_keys`, read `type_block.get("type")` instead of `type_block.get("mem")`.
    This test fails — every value_type comes back None.

    @brief A UDM manifest's keys and metadata are read.
    @version 1
    """
    path = tmp_path / "widgetbus_001.yaml"
    path.write_text(UDM_MANIFEST, encoding="utf-8")
    keys = parse_udm_manifest(path, tmp_path)
    assert keys is not None
    assert tuple(k.define_name for k in keys) == UDM_DEFINES
    assert {k.dialect for k in keys} == {DIALECT_UDM}
    assert [k.value_type for k in keys] == ["uint16", "uint8", "uint32"]
    assert [k.helpers for k in keys] == [True, False, True]
    assert {k.namespace for k in keys} == {"widgetbus"}
    assert {k.class_name for k in keys} == {"telemetry"}
    assert keys[0].manifest == "widgetbus_001.yaml"


## @brief The ingot parser DECLINES a UDM manifest, and vice versa.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_neither_parser_reads_the_other_dialect(tmp_path: Path) -> None:
    """THE NEGATIVE HALF, and it is what stops the two parsers becoming one by accident. Each
    positive test above passes with a parser that accepted anything shaped roughly right; only
    a refusal pins that the shape gate discriminates. It also pins the file-extension split not
    being what does the work — the ingot parser is handed the YAML document directly.

    WHAT MUTATION CONTROLS SAID THIS TEST ACTUALLY GUARDS, which is less than it looks: in
    BOTH directions the refusal comes from the document FORMAT, not from either shape gate.
    Deleting the `"namespace" not in doc` conjunct changes nothing here, because
    `yaml.safe_load` of a TOML document yields a string that `isinstance(doc, dict)` already
    refuses; deleting `_is_ingot_class_list` changes nothing either, because `toml.loads` of a
    YAML document raises. So this test pins the CROSS-DIALECT refusal and the two shape gates
    are pinned by the two tests that can see them —
    `test_udm_manifest_without_a_namespace_is_declined` and `test_ordinary_toml_is_declined`,
    both written or re-aimed because a control showed nothing else covered them.

    @brief Each parser refuses the other dialect's document.
    @version 2
    """
    ingot = tmp_path / "widgetbus.toml"
    ingot.write_text(MANIFEST, encoding="utf-8")
    udm = tmp_path / "widgetbus_001.yaml"
    udm.write_text(UDM_MANIFEST, encoding="utf-8")
    assert parse_udm_manifest(ingot, tmp_path) is None
    assert parse_ingot_manifest(udm, tmp_path) is None


## @brief A UDM-shaped document with no namespace is declined.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_udm_manifest_without_a_namespace_is_declined(tmp_path: Path) -> None:
    """WRITTEN BECAUSE A MUTATION CONTROL SAID IT WAS MISSING. Deleting the `namespace`
    conjunct from the UDM shape gate broke no test, so the conjunct was undefended — and it is
    load-bearing: with no namespace every composed name would be `_CLASS_KEY`, a leading
    underscore that matches no generated accessor, so every key in such a document would read
    as declared-and-never-observed rather than as a document that should not have been read.

    MUTATION: in `_udm_document`, drop the `"namespace" not in doc` conjunct. This test fails —
    the document parses and yields a key.

    @brief A namespace-less UDM document is not a manifest.
    @version 1
    """
    path = tmp_path / "nameless.yaml"
    path.write_text(
        "classes:\n  - name: telemetry\n    data:\n      - name: Uptime\n",
        encoding="utf-8",
    )
    assert parse_udm_manifest(path, tmp_path) is None


## @brief A UDM key's identity is its NAME, never the optional int `id`.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_udm_identity_is_the_name_not_the_int_id(tmp_path: Path) -> None:
    """4 of 233 classes and 14 of 1,606 keys in the measured corpus carry an int `id`, so a
    reader keying off it would key off a field the corpus almost entirely omits — and would
    compose an accessor name no generated code carries, making every such key read as never
    observed. The fixture puts an `id` on the class AND on one key so both levels are covered.

    MUTATION: in `_udm_keys`, compose from `entry.get("id", entry.get("name"))`. This test
    fails: the composed name carries the integer.

    @brief The int id is not the key identity.
    @version 1
    """
    path = tmp_path / "widgetbus_001.yaml"
    path.write_text(UDM_MANIFEST, encoding="utf-8")
    keys = parse_udm_manifest(path, tmp_path)
    assert keys is not None
    composed = {k.define_name for k in keys}
    assert composed == set(UDM_DEFINES)
    assert not any("4" in name or "11" in name for name in composed)


## @brief A UDM default is recorded as DECLARED-AND-UNRESOLVED, never as absent.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_udm_default_is_unresolved_not_absent(tmp_path: Path) -> None:
    """THE DISTINCTION THIS COLUMN EXISTS FOR, and all three states are in one assertion
    because separated they mislead. A UDM key's default is a base plus per-variant siblings
    that only a build's variant selection resolves, so no value is stored — but a key that
    declares NO default (280 of 1,606 in the measured corpus) must be distinguishable from one
    that declares several. `Uptime` is the empty case, and it is what makes this test fail
    against an implementation that simply marks every UDM key unresolved.

    `enum_set` rides the same mechanism: its value is a variant-to-inlined-member map with no
    name anywhere inside it, so there is nothing an `enum_name` column could honestly hold.

    MUTATION 1: in `_udm_keys`, set `default_value=_scalar(type_block["default_value"]["default"])`.
    This test fails — the base default is stored and would silently disagree with a variant
    build.
    MUTATION 2: make `_udm_unresolved` return `()` unconditionally. This test fails on the two
    keys that declare defaults, and PASSES on `Uptime` — which is why `Uptime` is in the
    fixture.

    @brief Declared-but-unresolved is distinct from not declared.
    @version 1
    """
    path = tmp_path / "widgetbus_001.yaml"
    path.write_text(UDM_MANIFEST, encoding="utf-8")
    keys = parse_udm_manifest(path, tmp_path)
    assert keys is not None
    by_id = {k.key_id: k for k in keys}
    assert all(k.default_value is None and k.enum_name is None for k in keys)
    assert by_id["Sample of Rate"].unresolved_fields == ("default_value",)
    assert by_id["Mode_Select"].unresolved_fields == ("default_value", "enum_set")
    assert by_id["Uptime"].unresolved_fields == ()


## @brief The selection gate and the composition rule are dialect-blind.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_both_dialects_coexist_under_one_key_list_gate(tmp_path: Path) -> None:
    """ONE REPOSITORY, TWO GENERATORS is a real state — an app pulls one model in while
    migrating off another — so the counts have to stay attributable. `dialect` alone stops
    being informative the moment both appear, which is why `keys_by_dialect` is asserted here
    rather than trusted.

    The key list names keys from BOTH manifests, so a gate that only ever consulted the ingot
    half would admit the UDM manifest anyway; what pins the gate for the new dialect is
    `test_udm_manifest_with_no_key_list_is_declined` below.

    THE NOTE MUST NAME ONLY THE DIALECT THAT LEFT SOMETHING UNRESOLVED. With both present, a
    note built from every dialect would put "ingot" into a sentence about per-variant defaults
    ingot does not have — authoritative-sounding prose that is wrong about half its subject, in
    the one field of this payload a consumer reads as an explanation rather than a count.

    MUTATION 1: in `_parsed_manifests`, drop the `udm_paths` loop. This test fails — `dialect`
    is "ingot" and the UDM keys are gone.
    MUTATION 2: in `_unresolved_note`, build `owners` from `self.dialects()`. This test fails on
    the note, and ONLY here — the single-dialect note test cannot see it.

    @brief Both dialects are selected and separately counted.
    @version 2
    """
    root = _repo(
        tmp_path,
        {"widgetbus.toml": MANIFEST, "widgetbus_001.yaml": UDM_MANIFEST},
        DEFINES + UDM_DEFINES,
    )
    found = discover(root)
    assert found.dialects() == (DIALECT_INGOT, DIALECT_UDM)
    meta = found.as_meta()
    assert meta["dialect"] == "ingot+udm"
    assert meta["keys_by_dialect"] == "ingot=3,udm=3"
    assert meta["keys"] == "6"
    assert meta["keys_with_unresolved_fields"] == "2"
    assert len(found.manifests) == 2
    assert meta["unresolved_note"].startswith("udm declares")
    assert DIALECT_INGOT not in meta["unresolved_note"]


## @brief A UDM manifest no key list vouches for is declined, and counted.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_udm_manifest_with_no_key_list_is_declined(tmp_path: Path) -> None:
    """THE NEGATIVE HALF OF THE GATE FOR THE NEW DIALECT. The positive half passes with the
    gate deleted, since without a gate everything is admitted — so this is the assertion that
    pins it, and it is what stops a vendored generator's example YAML from being read as the
    repository's model.

    MUTATION: in `_select`, drop the `if not any(key.define_name in listed ...)` branch. This
    test fails: the UDM keys appear and `manifests_unlisted` is 0.

    @brief An unvouched-for UDM manifest contributes nothing, visibly.
    @version 1
    """
    root = _repo(tmp_path, {"widgetbus_001.yaml": UDM_MANIFEST}, None)
    found = discover(root)
    assert found.keys == ()
    assert found.manifests_unlisted == 1
    assert found.as_meta()["dialect"] == ""


## @brief The unresolved-fields note is emitted for UDM and withheld for ingot.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_unresolved_note_is_emitted_only_when_it_applies(tmp_path: Path) -> None:
    """THE PAYLOAD HAS TO SAY IT, because a consumer reading a NULL `default_value` will
    otherwise conclude the manifest was silent — and for a UDM row that conclusion is wrong.
    The ingot half is the control: a repository whose every declared default WAS resolved must
    get no note at all, or the note becomes boilerplate that asserts a policy which did not
    apply and stops being read.

    MUTATION: make `_unresolved_note` return its prose unconditionally. The ingot half of this
    test fails.

    @brief The note appears exactly when something was left unresolved.
    @version 1
    """
    udm_root = _repo(tmp_path / "udm", {"widgetbus_001.yaml": UDM_MANIFEST}, UDM_DEFINES)
    note = discover(udm_root).as_meta()["unresolved_note"]
    assert "default_value" in note and "enum_set" in note
    assert "unresolved_fields" in note

    ingot_root = _repo(tmp_path / "ingot", {"widgetbus.toml": MANIFEST}, DEFINES)
    assert discover(ingot_root).as_meta()["unresolved_note"] == ""


## @brief The per-row column stores the names, and NULL when there are none.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_unresolved_fields_column_is_null_when_nothing_is_unresolved(tmp_path: Path) -> None:
    """NULL, NOT AN EMPTY STRING, so that a consumer's test for "unresolved" is the same NULL
    test every other optional column here takes. An empty string would be a value that looks
    declared and is not — the same defect `_scalar` avoids one column over.

    MUTATION: change the insert to `",".join(key.unresolved_fields)` without the `or None`.
    This test fails: the `Uptime` row holds "" instead of NULL.

    @brief The column is NULL exactly when nothing was declared-and-unresolved.
    @version 1
    """
    root = _repo(tmp_path, {"widgetbus_001.yaml": UDM_MANIFEST}, UDM_DEFINES)
    db = tmp_path / "clew.db"
    import_data_model_keys(db, root)
    conn = sqlite3.connect(str(db))
    try:
        rows = dict(conn.execute("SELECT key_id, unresolved_fields FROM data_model_keys"))
        dialects = {r[0] for r in conn.execute("SELECT DISTINCT dialect FROM data_model_keys")}
    finally:
        conn.close()
    assert rows == {
        "Sample of Rate": "default_value",
        "Mode_Select": "default_value,enum_set",
        "Uptime": None,
    }
    assert dialects == {DIALECT_UDM}


## @brief The UDM half is read even with no TOML parser on the interpreter.
## @param tmp_path Pytest temporary directory.
## @param monkeypatch Pytest monkeypatch fixture.
## @return None.
## @version 1
def test_udm_is_read_without_a_toml_parser(tmp_path: Path, monkeypatch) -> None:
    """A MISSING TOML PARSER USED TO STOP THE WHOLE PASS, and once the second dialect became
    readable that was a "could not look" about a half that was perfectly readable. The UDM
    dialect is YAML; only the ingot dialect needs `tomllib` or the `tomli` backport. So
    `toml_unavailable` narrows to what it can honestly claim, and the ingot manifest beside the
    UDM one is what proves the flag still means something.

    MUTATION: restore the early `return ManifestSet(toml_unavailable=True)` in `discover`. This
    test fails — no UDM keys are found.

    @brief No TOML parser blocks only the ingot half.
    @version 1
    """
    root = _repo(
        tmp_path,
        {"widgetbus.toml": MANIFEST, "widgetbus_001.yaml": UDM_MANIFEST},
        DEFINES + UDM_DEFINES,
    )
    monkeypatch.setattr("clew.datamodel.toml_module", lambda: None)
    found = discover(root)
    assert found.toml_unavailable is True
    assert found.as_meta()["toml_unavailable"] == "1"
    assert {k.define_name for k in found.keys} == set(UDM_DEFINES)
    assert found.dialects() == (DIALECT_UDM,)


## @brief Key lists with no selected manifest is a NAMED state, not a silent zero.
## @param tmp_path Pytest temporary directory.
## @param caplog Pytest log capture.
## @return None.
## @version 1
def test_key_lists_with_no_manifest_warns_about_the_tree_boundary(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """MEASURED ON A REAL TARGET, which is why this exists at all. A repository can declare its
    model in a SHARED SUBMODULE and keep the key list that selects from it in the app; nested
    git trees are excluded, so the manifests and the evidence that vouches for them land on
    opposite sides of that boundary. The result is a catalog of zero keys with
    `manifests_unlisted` ALSO zero — byte-identical to a repository with no data model, which
    is the silence this module's every other count exists to break.

    The fixture reproduces exactly that split: the manifest and its own key list are inside the
    nested tree, and the app has a key list of its own naming keys nothing declares.

    MUTATION: drop the `if found.list_count and not found.manifests` branch in `_log`. This
    test fails — the two states become indistinguishable again.

    @brief The lists-without-manifests state is warned about.
    @version 1
    """
    root = repo_with_submodules(tmp_path, "deps/model")
    _repo(tmp_path, {}, DEFINES)
    vendored = tmp_path / "deps" / "model"
    (vendored / "widgetbus.toml").write_text(MANIFEST, encoding="utf-8")

    with caplog.at_level("WARNING"):
        found = import_data_model_keys(tmp_path / "clew.db", root)
    assert found.keys == ()
    assert found.manifests_unlisted == 0, "premise: the manifest is excluded, not declined"
    assert found.list_count == 1
    assert [r for r in caplog.records if "NESTED GIT TREE" in r.getMessage()]


## @brief `observed` joins the shared-key vocabulary the earlier stages wrote.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_observed_flag_joins_the_shared_key_layer(tmp_path: Path) -> None:
    """THE THIRD GAIN, and the reason the stage runs below the shared-key stages rather than
    beside them. Run above and every row reads `observed = 0`, which is a plausible answer —
    a repository touching none of its own data model — rather than an obviously wrong one.

    The fixture writes ONE of the three names into `shared_key_edges`, so a join that ignored
    the vocabulary and flagged everything is caught as surely as one that flagged nothing.

    MUTATION: make `_observed_keys` return `frozenset()`. This test fails: the observed count
    drops to 0.

    @brief The observed flag reflects the shared-key vocabulary.
    @version 1
    """
    root = _repo(tmp_path, {"widgetbus.toml": MANIFEST}, DEFINES)
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE shared_key_edges (key_name TEXT)")
    conn.execute("INSERT INTO shared_key_edges VALUES (?)", (DEFINES[1],))
    conn.commit()
    conn.close()

    import_data_model_keys(db, root)
    conn = sqlite3.connect(str(db))
    try:
        rows = dict(conn.execute("SELECT define_name, observed FROM data_model_keys"))
    finally:
        conn.close()
    assert rows == {DEFINES[0]: 0, DEFINES[1]: 1, DEFINES[2]: 0}


## @brief The stage tolerates a database with no shared-key table at all.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_missing_shared_key_table_is_tolerated(tmp_path: Path) -> None:
    """`shared_key_edges` is created by whichever of its two stages runs first, and a target
    with no accessor convention legitimately has neither. Raising here would turn "this
    repository has no dataflow" into a build failure.

    MUTATION: remove the `except sqlite3.OperationalError` in `_observed_keys`. This test
    fails with an OperationalError.

    @brief No shared-key table is not an error.
    @version 1
    """
    root = _repo(tmp_path, {"widgetbus.toml": MANIFEST}, DEFINES)
    db = tmp_path / "clew.db"
    found = import_data_model_keys(db, root)
    assert len(found.keys) == 3
    conn = sqlite3.connect(str(db))
    try:
        assert (
            conn.execute("SELECT COUNT(*) FROM data_model_keys WHERE observed=1").fetchone()[0] == 0
        )
    finally:
        conn.close()


## @brief An oversized document is refused UNREAD, and the refusal is counted.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_an_oversized_document_is_refused_unread(tmp_path: Path) -> None:
    """MEASURED CAUSE, not a hypothetical. One control target vendors a YAML parser's benchmark
    corpus, including a 10.7 MB deliberately-pathological document, and the first version of
    this stage did not finish walking it in twenty-five minutes at full CPU. Recognising
    documents by SHAPE means parsing documents nobody declared, so the parse needs a bound
    that content cannot defeat.

    The fixture writes an oversized document that WOULD be a valid key list at a legal size, so
    the ceiling is what declines it and not the shape gate — and the real manifest beside it
    still lands, which is what stops the ceiling from being a way to disable the layer.

    MUTATION: raise `_MAX_DOCUMENT_BYTES` to `2 * 1024 * 1024 * 1024`. This test fails on the
    oversized count, and the key list is read.

    @brief A document over the ceiling is counted, not parsed.
    @version 1
    """
    root = _repo(tmp_path, {"widgetbus.toml": MANIFEST}, DEFINES)
    big = root / "conf" / "datamodel" / "huge.yaml"
    filler = "".join(f"- PADDING_KEY_{n}\n" for n in range(200_000))
    big.write_text("---\n" + filler, encoding="utf-8")
    assert big.stat().st_size > 2 * 1024 * 1024
    found = discover(root)
    assert found.oversized == 1
    assert found.as_meta()["documents_oversized"] == "1"
    assert "PADDING_KEY_0" not in found.listed
    assert {k.define_name for k in found.keys} == set(DEFINES)


## @brief A subtree the BUILD excluded is not walked for candidates.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_build_excludes_are_honoured(tmp_path: Path) -> None:
    """A CORRECTNESS REQUIREMENT, not a speed one. A generated data model's OUTPUT lands in a
    build directory, and this layer's whole premise is that it reads the generator's SOURCES —
    an index that is a function of whether somebody ran a build would make two indexes of one
    commit disagree about which keys exist. The build already excludes its own output, so
    honouring that list is what makes the guarantee structural rather than a naming convention.

    The fixture puts a manifest AND a key list naming its keys inside the excluded tree, so the
    selection gate alone would admit it: only the exclusion can decline it.

    MUTATION: in `_candidates`, drop `foreign |= set(excludes)`. This test fails — the generated
    manifest's key appears.

    @brief An excluded subtree contributes no candidates.
    @version 1
    """
    _repo(tmp_path, {"widgetbus.toml": MANIFEST}, DEFINES)
    generated = tmp_path / "build" / "gen"
    generated.mkdir(parents=True)
    (generated / "dm_full.toml").write_text(EXAMPLE_MANIFEST, encoding="utf-8")
    (generated / "gen_list.yaml").write_text("---\n- DEMO_SAMPLE_WIDGET\n", encoding="utf-8")

    unbounded = discover(tmp_path)
    assert "DEMO_SAMPLE_WIDGET" in {k.define_name for k in unbounded.keys}

    bounded = discover(tmp_path, (tmp_path / "build",))
    assert {k.define_name for k in bounded.keys} == set(DEFINES)
    assert "DEMO_SAMPLE_WIDGET" not in bounded.listed


## @brief The table exists even when the repository declares no keys.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_table_is_created_with_no_rows(tmp_path: Path) -> None:
    """An empty answer from a real table is a measurement; a missing table is not — it cannot
    be told apart from an index built before this layer existed, which is the ambiguity every
    structured zero in this pipeline exists to remove.

    MUTATION: move `_ensure_table(conn)` inside a `if found.keys:` guard. This test fails with
    `no such table`.

    @brief A target with no data model still gets the table.
    @version 1
    """
    db = tmp_path / "clew.db"
    import_data_model_keys(db, tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        assert conn.execute("SELECT COUNT(*) FROM data_model_keys").fetchone()[0] == 0
    finally:
        conn.close()
