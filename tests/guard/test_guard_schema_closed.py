# SPDX-License-Identifier: MIT
"""The gate's own section is closed, globbed and agrees with the index's vocabulary (R5-CFG F10-F13, F18).

FOUND BY THE 2.0.0 CONFIG REVIEW (agent A, vetted, owner-approved):
- F12: `validate.tags` and `validate.languages` were open dicts, so `tags.req.patern` or
  `languages.c.extentions` passed silently, against GUARD.md's "unknown keys are rejected".
- F18: "leave this path out" was a REGEX here (`^tests/`) and a glob everywhere else.
- F10: the index's event-tag vocabulary (`publishes`, `subscribes`, a declared `event_tags:`) was
  unknown to the gate unless restated under `validate.bus.tags`.
- F11: `wiki.sources` makes authors write `@node`, which the gate flagged as unknown.
- F13: keys the gate accepts were missing from GUARD.md's reference.

@brief Tests the closed gate schema and its cross-section vocabulary.
@version 1
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from clew.guard.config import ConfigError, load_config, validate_config_schema

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("config", "named"),
    [
        ({"validate": {"tags": {"req": {"patern": "x"}}}}, "validate.tags.req.patern"),
        (
            {"validate": {"languages": {"c": {"extentions": [".c"]}}}},
            "validate.languages.c.extentions",
        ),
    ],
)
def test_tag_and_language_entries_are_checked(config: dict, named: str) -> None:
    """@brief A misspelled per-tag or per-language key is refused by name."""
    errors = validate_config_schema(config)
    assert any(named in e for e in errors), errors


def test_a_well_formed_tag_and_language_pass() -> None:
    """@brief The documented per-entry keys are accepted, for a new tag and a new language too."""
    assert (
        validate_config_schema(
            {
                "validate": {
                    "tags": {
                        "req": {"pattern": "^R-[0-9]+$", "cross_reference": True},
                        "owner": {
                            "pattern": ".+",
                            "require_prefix": ["@"],
                            "require_contains": "x",
                        },
                    },
                    "languages": {
                        "kotlin": {
                            "extensions": [".kt"],
                            "function_pattern": "fun (\\w+)",
                            "exclude_names": [],
                            "comment_style": {"start": "/\\*\\*", "end": "\\*/"},
                            "require_return": False,
                        }
                    },
                }
            }
        )
        == []
    )


def _excluded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, patterns: list[str]) -> set[str]:
    """@brief Which of a few files the gate skips under these excludes. @return Skipped paths."""
    from clew.guard.main import validate_file

    monkeypatch.chdir(tmp_path)
    paths = ["tests/a.c", "src/tests_util.c", "gen/out.c", "src/ok.c"]
    for rel in paths:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("void f(void) { }\n")
    config = load_config(tmp_path / "missing.yaml")
    config["validate"]["exclude"] = patterns
    return {rel for rel in paths if validate_file(rel, config, no_git=True) == []}


def test_excludes_are_globs_and_a_regex_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F18: `tests/**` is a glob (it does not exclude `src/tests_util.c`); a regex needs `re:`.

    @brief Globs by default, `re:` for a regex.
    """
    skipped = _excluded(tmp_path, monkeypatch, ["tests/**", "re:^gen/"])
    assert {"tests/a.c", "gen/out.c"} <= skipped
    assert "src/tests_util.c" not in skipped and "src/ok.c" not in skipped


def test_a_1x_regex_exclude_is_refused_with_a_pointer(tmp_path: Path) -> None:
    """@brief `^tests/` (the 1.x regex form) is refused naming the glob and `re:` forms."""
    (tmp_path / ".clew.yaml").write_text('guard:\n  validate:\n    exclude: ["^tests/"]\n')
    with pytest.raises(ConfigError) as exc:
        load_config(tmp_path / ".clew.yaml")
    assert "re:" in " ".join(exc.value.problems)


def _unknown_tags(tmp_path: Path, clew_yaml: str, tag: str) -> list[str]:
    """@brief The unknown-tag messages for one tagged function. @return Messages."""
    from clew.guard.checks import check_unknown_tags
    from clew.guard.parser import DoxygenBlock, Function

    (tmp_path / ".clew.yaml").write_text(clew_yaml)
    config = load_config(tmp_path / ".clew.yaml")
    func = Function(
        name="f",
        def_line=3,
        body_end=3,
        doxygen=DoxygenBlock(start_line=0, end_line=2, tags={"brief": ["x"], tag: ["y"]}),
    )
    return [v.message for v in check_unknown_tags(func, "f.c", config)]


def test_the_indexs_event_tags_are_known_to_the_gate(tmp_path: Path) -> None:
    """F10: a declared `event_tags:` word, and the index's built-in vocabulary, are known tags.

    @brief One event vocabulary.
    """
    assert _unknown_tags(tmp_path, "event_tags: {broadcasts: producer}\n", "broadcasts") == []
    assert _unknown_tags(tmp_path, "guard: {}\n", "publishes") == []
    assert _unknown_tags(tmp_path, "guard: {}\n", "broadcasts") != []


def test_bus_tags_moved_to_the_declaration(tmp_path: Path) -> None:
    """@brief `validate.bus.tags` is refused naming the top-level `event_tags:`."""
    (tmp_path / ".clew.yaml").write_text("guard:\n  validate:\n    bus: {tags: [emits]}\n")
    with pytest.raises(ConfigError) as exc:
        load_config(tmp_path / ".clew.yaml")
    assert "event_tags" in " ".join(exc.value.problems)


def test_node_is_known_when_the_wiki_declares_sources(tmp_path: Path) -> None:
    """F11: `wiki.sources` asks authors for `@node`; the gate accepts it there, and only there.

    @brief `@node` follows `wiki.sources`.
    """
    sources = "wiki:\n  sources:\n    - {name: keys, path: keys.toml}\n"
    assert _unknown_tags(tmp_path, sources, "node") == []
    assert _unknown_tags(tmp_path, "guard: {}\n", "node") != []


def test_the_gate_vocabulary_matches_the_index_defaults() -> None:
    """The gate restates the index's default event tags (it imports nothing from the pipeline);
    this pins the two copies together.

    @brief Gate and index defaults agree.
    """
    from clew.event_edges import DEFAULT_EVENT_TAGS
    from clew.guard.config import DEFAULT_EVENT_TAG_NAMES

    assert set(DEFAULT_EVENT_TAG_NAMES) == set(DEFAULT_EVENT_TAGS)


def _leaves(schema: dict, prefix: str = "") -> list[str]:
    """@brief Dotted leaf paths of a schema mapping. @return Paths."""
    out = []
    for key, value in schema.items():
        path = f"{prefix}.{key}" if prefix else key
        out += _leaves(value, path) if isinstance(value, dict) else [path]
    return out


def test_guard_md_documents_every_gate_key() -> None:
    """F13: every key the gate accepts appears in GUARD.md's reference (by its last segment, in a
    table row or a code span), so the reference cannot fall behind the schema again.

    @brief GUARD.md covers the schema.
    """
    from clew.guard.config import CONFIG_SCHEMA, LANGUAGE_SCHEMA, TAG_SCHEMA

    text = (REPO / "docs" / "GUARD.md").read_text(encoding="utf-8")
    keys = (
        _leaves(CONFIG_SCHEMA)
        + _leaves(TAG_SCHEMA, "tags.<tag>")
        + _leaves(LANGUAGE_SCHEMA, "languages.<lang>")
    )
    missing = [
        k for k in keys if not re.search(rf"`[^`]*{re.escape(k.split('.')[-1])}[^`]*`", text)
    ]
    assert missing == [], missing
