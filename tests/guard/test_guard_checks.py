"""Tests for clew.guard.checks (absorbed from doxygen-guard)."""

from __future__ import annotations

from clew.guard.checks import (
    EXEMPTION_TAGS,
    check_duplicate_tags,
    check_presence,
    check_req_coverage,
    check_tags,
    check_unknown_tags,
    check_version_staleness,
)
from clew.guard.config import CONFIG_DEFAULTS, deep_merge
from clew.guard.parser import DoxygenBlock, Function


def _make_func(
    name: str = "Func",
    def_line: int = 5,
    body_end: int = 10,
    tags: dict | None = None,
    has_doxygen: bool = True,
) -> Function:
    """Helper to create Function instances for testing."""
    doxygen = None
    if has_doxygen:
        doxygen = DoxygenBlock(
            start_line=def_line - 4,
            end_line=def_line - 1,
            tags={"brief": ["Do something."], "version": ["1.0"]} if tags is None else tags,
            raw="/**\n * @brief Do something.\n * @version 1.0\n */",
        )
    return Function(name=name, def_line=def_line, body_end=body_end, doxygen=doxygen)


class TestCheckPresence:
    """Tests for check_presence."""

    def test_no_violations_when_documented(self):
        funcs = [_make_func()]
        violations = check_presence(funcs, "test.c", CONFIG_DEFAULTS)
        assert violations == []

    def test_missing_doxygen(self):
        funcs = [_make_func(has_doxygen=False)]
        violations = check_presence(funcs, "test.c", CONFIG_DEFAULTS)
        assert len(violations) == 1
        assert violations[0].check == "presence"
        assert "no doxygen comment" in violations[0].message

    def test_missing_brief(self):
        funcs = [_make_func(tags={"version": ["1.0"]})]
        violations = check_presence(funcs, "test.c", CONFIG_DEFAULTS)
        assert len(violations) == 1
        assert "missing @brief" in violations[0].message

    def test_missing_version(self):
        funcs = [_make_func(tags={"brief": ["Something."]})]
        violations = check_presence(funcs, "test.c", CONFIG_DEFAULTS)
        assert len(violations) == 1
        assert "missing @version" in violations[0].message

    def test_missing_both_tags(self):
        funcs = [_make_func(tags={})]
        violations = check_presence(funcs, "test.c", CONFIG_DEFAULTS)
        assert len(violations) == 2

    def test_presence_disabled(self):
        config = {
            "validate": {
                "presence": {"require_doxygen": False},
                "version": {"require_present": True},
            }
        }
        funcs = [_make_func(has_doxygen=False)]
        violations = check_presence(funcs, "test.c", config)
        assert violations == []

    def test_version_not_required(self):
        config = {
            "validate": {
                "presence": {"require_doxygen": True},
                "version": {"require_present": False},
            }
        }
        funcs = [_make_func(tags={"brief": ["Something."]})]
        violations = check_presence(funcs, "test.c", config)
        assert violations == []

    def test_multiple_functions(self):
        funcs = [
            _make_func(name="Good", def_line=5, body_end=10),
            _make_func(name="Bad", def_line=15, body_end=20, has_doxygen=False),
        ]
        violations = check_presence(funcs, "test.c", CONFIG_DEFAULTS)
        assert len(violations) == 1
        assert "Bad" in violations[0].message

    def test_line_numbers_1_indexed(self):
        funcs = [_make_func(def_line=0, has_doxygen=False)]
        violations = check_presence(funcs, "test.c", CONFIG_DEFAULTS)
        assert violations[0].line == 1  # 0-indexed + 1


def _lines_for(func: Function, body_text: str) -> list[str]:
    """Build a source-line list long enough that func.def_line..body_end holds body_text."""
    body_lines = body_text.splitlines()
    assert len(body_lines) == func.body_end - func.def_line + 1
    lines = [""] * func.def_line
    lines.extend(body_lines)
    return lines


class TestCheckVersionStaleness:
    """Tests for check_version_staleness."""

    def test_no_head_functions_no_violation(self):
        """No HEAD to compare against (e.g. new file) — nothing can be stale."""
        funcs = [_make_func(def_line=5, body_end=6)]
        content = "\n".join(_lines_for(funcs[0], "int a;\nint b;"))
        violations = check_version_staleness(
            funcs, "test.c", CONFIG_DEFAULTS, content, head_functions=None, head_content=None
        )
        assert violations == []

    def test_body_unchanged_no_violation(self):
        func = _make_func(def_line=5, body_end=6)
        content = "\n".join(_lines_for(func, "int a;\nint b;"))
        head_func = _make_func(def_line=5, body_end=6)
        violations = check_version_staleness(
            [func], "test.c", CONFIG_DEFAULTS, content, [head_func], content
        )
        assert violations == []

    def test_body_changed_version_not_updated(self):
        func = _make_func(def_line=5, body_end=6)
        content = "\n".join(_lines_for(func, "int a;\nint b;"))
        head_func = _make_func(def_line=5, body_end=6)
        head_content = "\n".join(_lines_for(head_func, "int a;\nint c;"))
        violations = check_version_staleness(
            [func], "test.c", CONFIG_DEFAULTS, content, [head_func], head_content
        )
        assert len(violations) == 1
        assert violations[0].check == "version"
        assert "not updated" in violations[0].message

    def test_body_changed_version_bumped(self):
        func = _make_func(def_line=5, body_end=6, tags={"brief": ["x"], "version": ["1.1"]})
        content = "\n".join(_lines_for(func, "int a;\nint b;"))
        head_func = _make_func(def_line=5, body_end=6)  # version 1.0
        head_content = "\n".join(_lines_for(head_func, "int a;\nint c;"))
        violations = check_version_staleness(
            [func], "test.c", CONFIG_DEFAULTS, content, [head_func], head_content
        )
        assert violations == []

    def test_new_function_not_in_head_skipped(self):
        """A function absent from HEAD has no prior version to be stale against."""
        func = _make_func(name="BrandNew", def_line=5, body_end=6)
        content = "\n".join(_lines_for(func, "int a;\nint b;"))
        # HEAD has an unrelated function, not this one
        head_func = _make_func(name="Other", def_line=5, body_end=6)
        head_content = "\n".join(_lines_for(head_func, "int x;\nint y;"))
        violations = check_version_staleness(
            [func], "test.c", CONFIG_DEFAULTS, content, [head_func], head_content
        )
        assert violations == []

    def test_no_doxygen_skipped(self):
        func = _make_func(has_doxygen=False, def_line=5, body_end=6)
        content = "\n".join(_lines_for(func, "int a;\nint b;"))
        head_func = _make_func(has_doxygen=False, def_line=5, body_end=6)
        head_content = "\n".join(_lines_for(head_func, "int a;\nint c;"))
        violations = check_version_staleness(
            [func], "test.c", CONFIG_DEFAULTS, content, [head_func], head_content
        )
        assert violations == []

    def test_staleness_disabled(self):
        config = {
            "validate": {
                "version": {"require_increment_on_change": False, "tag": "@version"},
            }
        }
        func = _make_func(def_line=5, body_end=6)
        content = "\n".join(_lines_for(func, "int a;\nint b;"))
        head_func = _make_func(def_line=5, body_end=6)
        head_content = "\n".join(_lines_for(head_func, "int a;\nint c;"))
        violations = check_version_staleness(
            [func], "test.c", config, content, [head_func], head_content
        )
        assert violations == []

    def test_no_version_tag_skipped(self):
        """Functions without @version are skipped (caught by presence check)."""
        func = _make_func(def_line=5, body_end=6, tags={"brief": ["Something."]})
        content = "\n".join(_lines_for(func, "int a;\nint b;"))
        head_func = _make_func(def_line=5, body_end=6, tags={"brief": ["Something."]})
        head_content = "\n".join(_lines_for(head_func, "int a;\nint c;"))
        violations = check_version_staleness(
            [func], "test.c", CONFIG_DEFAULTS, content, [head_func], head_content
        )
        assert violations == []

    def test_reviewed_marker_clears_staleness(self):
        """Adding [reviewed] to @version counts as updating the version."""
        func = _make_func(
            def_line=5,
            body_end=6,
            tags={"brief": ["Something."], "version": ["1.0 [reviewed]"]},
        )
        content = "\n".join(_lines_for(func, "int a;\nint b;"))
        head_func = _make_func(def_line=5, body_end=6)  # version "1.0", no marker
        head_content = "\n".join(_lines_for(head_func, "int a;\nint c;"))
        violations = check_version_staleness(
            [func], "test.c", CONFIG_DEFAULTS, content, [head_func], head_content
        )
        assert violations == []

    def test_unknown_version_marker_rejected(self):
        """Unknown markers like [typo] are rejected."""
        func = _make_func(
            def_line=5,
            body_end=6,
            tags={"brief": ["Something."], "version": ["1.0 [typo]"]},
        )
        content = "\n".join(_lines_for(func, "int a;\nint b;"))
        head_func = _make_func(def_line=5, body_end=6)  # version "1.0", no marker
        head_content = "\n".join(_lines_for(head_func, "int a;\nint c;"))
        violations = check_version_staleness(
            [func], "test.c", CONFIG_DEFAULTS, content, [head_func], head_content
        )
        assert len(violations) == 1
        assert "unrecognized version marker" in violations[0].message

    def test_version_bump_still_works(self):
        """Normal version bump (no marker) still passes."""
        func = _make_func(
            def_line=5,
            body_end=6,
            tags={"brief": ["Something."], "version": ["1.1"]},
        )
        content = "\n".join(_lines_for(func, "int a;\nint b;"))
        head_func = _make_func(def_line=5, body_end=6)  # version "1.0"
        head_content = "\n".join(_lines_for(head_func, "int a;\nint c;"))
        violations = check_version_staleness(
            [func], "test.c", CONFIG_DEFAULTS, content, [head_func], head_content
        )
        assert violations == []

    def test_new_function_same_name_different_body_shape_still_new(self):
        """Regression for issue #10: a new function whose @version line is textually
        identical to HEAD's must not be flagged, even though its enclosing content
        differs in ways that could confuse a positional diff."""
        func = _make_func(name="add_grid_source_params", def_line=5, body_end=6)
        content = "\n".join(_lines_for(func, "int a;\nint b;"))
        violations = check_version_staleness(
            [func], "test.c", CONFIG_DEFAULTS, content, head_functions=[], head_content=""
        )
        assert violations == []


class TestCheckTags:
    """Tests for check_tags."""

    def test_no_tag_rules(self):
        funcs = [_make_func()]
        violations = check_tags(funcs, "test.c", CONFIG_DEFAULTS)
        assert violations == []

    def test_valid_pattern(self):
        config = {
            "validate": {
                "tags": {
                    "req": {"pattern": r"^REQ-\w+$"},
                },
            }
        }
        funcs = [
            _make_func(tags={"brief": ["Something."], "version": ["1.0"], "req": ["REQ-0001"]})
        ]
        violations = check_tags(funcs, "test.c", config)
        assert violations == []

    def test_invalid_pattern(self):
        config = {
            "validate": {
                "tags": {
                    "req": {"pattern": r"^REQ-\w+$"},
                },
            }
        }
        funcs = [_make_func(tags={"brief": ["Something."], "version": ["1.0"], "req": ["INVALID"]})]
        violations = check_tags(funcs, "test.c", config)
        assert len(violations) == 1
        assert "does not match pattern" in violations[0].message

    def test_require_prefix(self):
        config = {
            "validate": {
                "tags": {
                    "sends": {"require_prefix": ["EVENT:", "FSM:"]},
                },
            }
        }
        # Valid prefix
        funcs = [_make_func(tags={"brief": ["X."], "version": ["1.0"], "sends": ["EVENT:READY"]})]
        assert check_tags(funcs, "test.c", config) == []

        # Invalid prefix
        funcs = [_make_func(tags={"brief": ["X."], "version": ["1.0"], "sends": ["BADPREFIX"]})]
        violations = check_tags(funcs, "test.c", config)
        assert len(violations) == 1
        assert "does not start with" in violations[0].message

    def test_require_contains(self):
        config = {
            "validate": {
                "tags": {
                    "calls": {"require_contains": "::"},
                },
            }
        }
        # Valid
        funcs = [_make_func(tags={"brief": ["X."], "version": ["1.0"], "calls": ["mod::func"]})]
        assert check_tags(funcs, "test.c", config) == []

        # Invalid
        funcs = [_make_func(tags={"brief": ["X."], "version": ["1.0"], "calls": ["modfunc"]})]
        violations = check_tags(funcs, "test.c", config)
        assert len(violations) == 1
        assert "does not contain" in violations[0].message

    def test_no_doxygen_skipped(self):
        config = {
            "validate": {
                "tags": {
                    "req": {"pattern": r"^REQ-\w+$"},
                },
            }
        }
        funcs = [_make_func(has_doxygen=False)]
        violations = check_tags(funcs, "test.c", config)
        assert violations == []

    def test_tag_not_present_no_violation(self):
        """Tags that aren't present in the doxygen block don't trigger violations."""
        config = {
            "validate": {
                "tags": {
                    "req": {"pattern": r"^REQ-\w+$"},
                },
            }
        }
        funcs = [_make_func(tags={"brief": ["X."], "version": ["1.0"]})]
        violations = check_tags(funcs, "test.c", config)
        assert violations == []

    def test_violation_str(self):
        from clew.guard.checks import Violation

        v = Violation(file="test.c", line=10, check="presence", message="missing doxygen")
        assert str(v) == "test.c:10: [presence] missing doxygen"


class TestConstructorDestructorSkipping:
    """Constructors and destructors should be exempt from @return and @req checks."""

    def test_constructor_skipped_for_return_check(self):
        from clew.guard.checks import check_return_presence

        ctor = Function(
            name="Foo",
            def_line=5,
            body_end=10,
            doxygen=DoxygenBlock(
                start_line=2, end_line=4, tags={"brief": ["Constructor."], "version": ["1.0"]}
            ),
            enclosing_class="Foo",
        )
        content = "class Foo {\npublic:\nFoo() {}\n};\n"
        violations = check_return_presence([ctor], "test.cpp", CONFIG_DEFAULTS, content)
        assert violations == []

    def test_destructor_skipped_for_return_check(self):
        from clew.guard.checks import check_return_presence

        dtor = Function(
            name="~Foo",
            def_line=5,
            body_end=10,
            doxygen=DoxygenBlock(
                start_line=2, end_line=4, tags={"brief": ["Destructor."], "version": ["1.0"]}
            ),
            enclosing_class="Foo",
        )
        content = "class Foo {\npublic:\n~Foo() {}\n};\n"
        violations = check_return_presence([dtor], "test.cpp", CONFIG_DEFAULTS, content)
        assert violations == []

    def test_constructor_skipped_for_req_check(self):
        from clew.guard.checks import check_req_coverage

        ctor = Function(
            name="Foo",
            def_line=5,
            body_end=10,
            doxygen=DoxygenBlock(
                start_line=2, end_line=4, tags={"brief": ["Constructor."], "version": ["1.0"]}
            ),
            enclosing_class="Foo",
        )
        config = {
            "impact": {"requirements": {"file": "reqs.csv"}},
            "validate": {},
        }
        violations = check_req_coverage([ctor], "test.cpp", config)
        assert violations == []

    def test_regular_function_still_requires_req(self):
        from clew.guard.checks import check_req_coverage

        method = Function(
            name="bar",
            def_line=5,
            body_end=10,
            doxygen=DoxygenBlock(
                start_line=2, end_line=4, tags={"brief": ["Method."], "version": ["1.0"]}
            ),
            enclosing_class="Foo",
        )
        config = {
            "impact": {"requirements": {"file": "reqs.csv"}},
            "validate": {},
        }
        violations = check_req_coverage([method], "test.cpp", config)
        assert len(violations) == 1


class TestStandardDoxygenTags:
    """Standard Doxygen tags should be in the known allowlist."""

    def test_par_not_unknown(self):
        from clew.guard.checks import _KNOWN_TAGS

        assert "par" in _KNOWN_TAGS

    def test_throws_not_unknown(self):
        from clew.guard.checks import _KNOWN_TAGS

        assert "throws" in _KNOWN_TAGS
        assert "throw" in _KNOWN_TAGS
        assert "exception" in _KNOWN_TAGS


class TestCheckDuplicateTags:
    """Single-valued tags must not silently duplicate.

    Regression: this repo's own impact.py carried two stacked doxygen blocks above one
    function, giving it two @brief and two @version tags. The gate passed it on every
    commit since the refactor that introduced it. Readers take tags[name][0], so the
    second value is silently discarded and the staleness check can compare against a
    stale orphaned version.
    """

    def test_duplicate_file_tag_flagged(self):
        func = _make_func(tags={"brief": ["Do it."], "version": ["1.0"], "file": ["a", "b"]})
        violations = check_duplicate_tags(func, "test.c", CONFIG_DEFAULTS)
        assert len(violations) == 1
        assert violations[0].check == "tag"
        assert "@file appears 2 times" in violations[0].message

    def test_duplicate_brief_flagged(self):
        func = _make_func(tags={"brief": ["First.", "Second."], "version": ["1.0"]})
        violations = check_duplicate_tags(func, "test.c", CONFIG_DEFAULTS)
        assert len(violations) == 1
        assert "@brief" in violations[0].message

    def test_stacked_blocks_flag_the_single_valued_tags(self):
        """The real shape of the bug: two whole blocks means two of each tag.

        @version is excluded from the set — doxygen permits repeated \\version notes —
        so a stacked block is caught via @brief and @return instead.
        """
        func = _make_func(
            tags={"brief": ["Old.", "New."], "version": ["1.1", "1.0"], "return": ["a", "b"]}
        )
        violations = check_duplicate_tags(func, "test.c", CONFIG_DEFAULTS)
        assert {v.message.split()[0] for v in violations} == {"@brief", "@return"}

    def test_duplicate_return_flagged(self):
        func = _make_func(tags={"brief": ["B."], "version": ["1.0"], "return": ["a", "b"]})
        violations = check_duplicate_tags(func, "test.c", CONFIG_DEFAULTS)
        assert len(violations) == 1
        assert "@return" in violations[0].message

    def test_clean_block_passes(self):
        violations = check_duplicate_tags(_make_func(), "test.c", CONFIG_DEFAULTS)
        assert violations == []

    def test_repeatable_tags_are_not_flagged(self):
        """@req and @param are legitimately repeatable."""
        func = _make_func(
            tags={
                "brief": ["B."],
                "version": ["1.0"],
                "req": ["REQ-VAL-001", "REQ-VAL-002"],
                "param": ["a first", "b second"],
            }
        )
        assert check_duplicate_tags(func, "test.c", CONFIG_DEFAULTS) == []

    def test_undocumented_function_is_not_flagged(self):
        func = _make_func(has_doxygen=False)
        assert check_duplicate_tags(func, "test.c", CONFIG_DEFAULTS) == []

    def test_check_can_be_disabled(self):
        func = _make_func(tags={"brief": ["A.", "B."], "version": ["1.0"]})
        config = deep_merge(CONFIG_DEFAULTS, {"validate": {"duplicate_tags_error": False}})
        assert check_duplicate_tags(func, "test.c", config) == []

    def test_multiple_version_entries_are_legal(self):
        """Doxygen permits repeated \\version notes; flagging them rejected valid doxygen.

        Regression introduced with this check in 1.3.0 and fixed by removing "version"
        from _SINGLE_VALUED_TAGS.
        """
        func = _make_func(tags={"brief": ["B."], "version": ["1.0", "2.0"]})
        assert check_duplicate_tags(func, "test.c", CONFIG_DEFAULTS) == []


class TestExemptionTagsAreToolOwned:
    """@req exemption no longer overloads doxygen's \\internal.

    Doxygen's \\internal suppresses everything after it in the block when INTERNAL_DOCS
    is off, while this tool kept reading tags past it — so a block written to satisfy
    the gate silently lost its @return in generated documentation. Exemption now uses
    @dg_internal, which doxygen has no meaning for.
    """

    def test_dg_internal_exempts(self):
        assert "dg_internal" in EXEMPTION_TAGS

    def test_internal_no_longer_exempts(self):
        assert "internal" not in EXEMPTION_TAGS

    def test_internal_is_still_a_recognised_tag(self):
        """A project using \\internal for its real purpose must not be flagged."""
        func = _make_func(tags={"brief": ["B."], "version": ["1.0"], "internal": [""]})
        assert check_unknown_tags(func, "a.c", CONFIG_DEFAULTS) == []

    def test_dg_internal_is_a_recognised_tag(self):
        func = _make_func(tags={"brief": ["B."], "version": ["1.0"], "dg_internal": [""]})
        assert check_unknown_tags(func, "a.c", CONFIG_DEFAULTS) == []

    def test_coverage_message_lists_the_real_exemption_tags(self, tmp_path):
        """The hint is derived from EXEMPTION_TAGS, so it cannot drift out of date."""
        catalog = tmp_path / "reqs.yaml"
        catalog.write_text("requirements:\n  REQ-VAL-001:\n    name: A req\n")
        config = deep_merge(
            CONFIG_DEFAULTS,
            {"impact": {"requirements": {"file": str(catalog), "format": "yaml"}}},
        )
        func = _make_func(tags={"brief": ["B."], "version": ["1.0"]})
        violations = check_req_coverage([func], "a.c", config)
        assert violations
        message = violations[0].message
        assert "@dg_internal" in message
        assert "@internal," not in message


class TestConfiguredVersionTag:
    """validate.version.tag was honoured by staleness only, not by presence.

    Setting it produced a presence violation demanding @version AND an unknown-tag
    violation for the configured name, so the documented escape hatch for projects
    using doxygen's \\version idiomatically did not work.
    """

    def _config(self, tag: str):
        return deep_merge(
            CONFIG_DEFAULTS,
            {"validate": {"version": {"tag": tag}, "extra_tags": [tag.lstrip("@")]}},
        )

    def test_configured_tag_satisfies_presence(self):
        func = _make_func(tags={"brief": ["B."], "revision": ["1.0"]})
        assert check_presence([func], "a.c", self._config("@revision")) == []

    def test_missing_configured_tag_is_reported_by_that_name(self):
        func = _make_func(tags={"brief": ["B."]})
        violations = check_presence([func], "a.c", self._config("@revision"))
        assert len(violations) == 1
        assert "@revision" in violations[0].message
        assert "@version" not in violations[0].message

    def test_default_remains_version(self):
        func = _make_func(tags={"brief": ["B."], "version": ["1.0"]})
        assert check_presence([func], "a.c", CONFIG_DEFAULTS) == []
