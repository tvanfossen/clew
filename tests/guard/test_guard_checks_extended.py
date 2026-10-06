"""Tests for extended validation checks (Phase 5).

@brief Tests for unknown tag detection, req cross-validation, file presence, fix hints.
@version 1.0
"""

from __future__ import annotations

from pathlib import Path

from clew.guard.checks import (
    check_file_presence,
    check_presence,
    check_req_exists,
    check_unknown_tags,
)
from clew.guard.config import CONFIG_DEFAULTS, deep_merge
from clew.guard.parser import DoxygenBlock, Function

BASE_CONFIG = CONFIG_DEFAULTS
FIXTURES_DIR = Path(__file__).parent / "fixtures"


## @brief Helper to create a Function with doxygen tags.
#  @version 1.0
def _make_func(name: str, tags: dict | None = None, start_line: int = 0) -> Function:
    doxygen = DoxygenBlock(
        start_line=start_line,
        end_line=start_line + 2,
        tags=tags or {},
    )
    return Function(
        name=name,
        def_line=start_line + 3,
        body_end=start_line + 5,
        doxygen=doxygen,
    )


class TestCheckUnknownTags:
    """Tests for check_unknown_tags with Levenshtein suggestions."""

    def test_known_tag_no_violation(self):
        func = _make_func("f", tags={"brief": ["desc"], "version": ["1.0"]})
        violations = check_unknown_tags(func, "a.c", BASE_CONFIG)
        assert len(violations) == 0

    def test_unknown_tag_produces_violation(self):
        func = _make_func("f", tags={"brief": ["desc"], "sendd": ["EVENT_X"]})
        violations = check_unknown_tags(func, "a.c", BASE_CONFIG)
        assert len(violations) == 1
        assert "sendd" in violations[0].message

    def test_levenshtein_suggestion(self):
        func = _make_func("f", tags={"brief": ["desc"], "verison": ["1.0"]})
        violations = check_unknown_tags(func, "a.c", BASE_CONFIG)
        assert "did you mean @version?" in violations[0].message

    def test_retired_tracer_tags_are_unknown(self):
        """The diagram tags went with the tracer; a tag the tool cannot act on is unknown."""
        func = _make_func("f", tags={"brief": ["desc"], "sends": ["EVENT_X"]})
        violations = check_unknown_tags(func, "a.c", BASE_CONFIG)
        assert len(violations) == 1
        assert "@sends" in violations[0].message

    def test_retired_tags_can_be_readmitted_via_extra_tags(self):
        """Migration path for repos still carrying them."""
        config = deep_merge(BASE_CONFIG, {"validate": {"extra_tags": ["sends", "receives"]}})
        func = _make_func("f", tags={"brief": ["d"], "sends": ["E"], "receives": ["E2"]})
        assert check_unknown_tags(func, "a.c", config) == []

    def test_extra_tags_accepted(self):
        config = deep_merge(BASE_CONFIG, {"validate": {"extra_tags": ["custom"]}})
        func = _make_func("f", tags={"brief": ["desc"], "custom": ["val"]})
        violations = check_unknown_tags(func, "a.c", config)
        assert len(violations) == 0

    def test_disabled_by_config(self):
        config = deep_merge(BASE_CONFIG, {"validate": {"known_tags_warn": False}})
        func = _make_func("f", tags={"brief": ["desc"], "bogus": ["val"]})
        violations = check_unknown_tags(func, "a.c", config)
        assert len(violations) == 0


class TestCheckReqExists:
    """Tests for stale req cross-validation."""

    def test_valid_req_no_violation(self):
        func = _make_func("f", tags={"brief": ["d"], "req": ["REQ-001"]})
        violations = check_req_exists(func, "a.c", BASE_CONFIG, req_ids={"REQ-001"})
        assert len(violations) == 0

    def test_stale_req_violation(self):
        func = _make_func("f", tags={"brief": ["d"], "req": ["REQ-MISSING"]})
        violations = check_req_exists(func, "a.c", BASE_CONFIG, req_ids={"REQ-001"})
        assert len(violations) == 1
        assert "REQ-MISSING" in violations[0].message

    def test_no_req_ids_skips(self):
        func = _make_func("f", tags={"brief": ["d"], "req": ["REQ-001"]})
        violations = check_req_exists(func, "a.c", BASE_CONFIG, req_ids=None)
        assert len(violations) == 0


class TestCheckFilePresence:
    """Tests for file-level doxygen block enforcement."""

    def test_c_file_with_complete_block_passes(self):
        content = (
            "/**\n * @file\n * @brief Sensor driver.\n * @version 1.0\n */\nvoid func(void) {}\n"
        )
        config = deep_merge(BASE_CONFIG, {"validate": {"presence": {"require_file_doxygen": True}}})
        violations = check_file_presence("a.c", content, config)
        assert len(violations) == 0

    def test_c_file_missing_tags_fails(self):
        content = "/** @file sensor_driver.c */\nvoid func(void) {}\n"
        config = deep_merge(BASE_CONFIG, {"validate": {"presence": {"require_file_doxygen": True}}})
        violations = check_file_presence("a.c", content, config)
        assert len(violations) >= 1
        assert any("@brief" in v.message or "@version" in v.message for v in violations)

    def test_c_file_without_file_block_fails(self):
        content = "void func(void) {}\n"
        config = deep_merge(BASE_CONFIG, {"validate": {"presence": {"require_file_doxygen": True}}})
        violations = check_file_presence("a.c", content, config)
        assert len(violations) == 1

    def test_python_file_with_complete_block_passes(self):
        content = "## @file\n## @brief Module.\n## @version 1.0\ndef func(): pass\n"
        config = deep_merge(BASE_CONFIG, {"validate": {"presence": {"require_file_doxygen": True}}})
        violations = check_file_presence("a.py", content, config)
        assert len(violations) == 0

    def test_disabled_by_default(self):
        content = "void func(void) {}\n"
        violations = check_file_presence("a.c", content, BASE_CONFIG)
        assert len(violations) == 0

    def test_include_guards_skipped(self):
        content = (
            "#ifndef FOO_H\n#define FOO_H\n"
            "/**\n * @file\n * @brief Header.\n * @version 1.0\n */\n"
            "void f(void);\n#endif\n"
        )
        config = deep_merge(BASE_CONFIG, {"validate": {"presence": {"require_file_doxygen": True}}})
        violations = check_file_presence("a.h", content, config)
        assert len(violations) == 0


class TestFixHints:
    """Tests for actionable fix hints in violation messages."""

    def test_missing_doxygen_has_fix_hint(self):
        func = Function(name="helper", def_line=5, body_end=7, doxygen=None)
        violations = check_presence([func], "a.c", BASE_CONFIG)
        assert any("@brief" in v.message for v in violations)

    def test_missing_brief_has_fix_hint(self):
        func = _make_func("f", tags={"version": ["1.0"]})
        violations = check_presence([func], "a.c", BASE_CONFIG)
        brief_violations = [v for v in violations if "brief" in v.message.lower()]
        assert len(brief_violations) == 1
        assert "add" in brief_violations[0].message.lower()


class TestCoverageSubcommand:
    """Tests for the coverage analysis module."""

    def test_analyze_coverage_structure(self):
        from clew.guard.coverage import analyze_coverage

        source_dir = str(FIXTURES_DIR / "sources")
        config = deep_merge(
            BASE_CONFIG,
            {
                "impact": {
                    "requirements": {
                        "file": str(FIXTURES_DIR / "sources" / "requirements.csv"),
                        "id_column": "Req ID",
                        "name_column": "Name",
                        "format": "csv",
                    },
                },
            },
        )
        report = analyze_coverage([source_dir], config)
        assert "total_requirements" in report
        assert "covered" in report
        assert "uncovered" in report
        assert "orphan_refs" in report
        assert isinstance(report["covered"], list)

    def test_format_coverage_markdown(self):
        from clew.guard.coverage import format_coverage_markdown

        report = {
            "total_requirements": 5,
            "covered": ["REQ-001", "REQ-002"],
            "uncovered": ["REQ-003"],
            "supports_only": [],
            "orphan_refs": [],
            "unmapped_functions": ["helper"],
        }
        md = format_coverage_markdown(report)
        assert "# Requirements Coverage" in md
        assert "REQ-003" in md
