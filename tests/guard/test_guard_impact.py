"""Tests for clew.guard.impact (absorbed from doxygen-guard)."""

from __future__ import annotations

import json
from textwrap import dedent

import pytest

from clew.guard.config import CONFIG_DEFAULTS, deep_merge
from clew.guard.errors import ConfigError, RequirementsError
from clew.guard.impact import (
    ChangedFunction,
    ImpactEntry,
    build_impact_report,
    collect_changed_functions,
    filter_requirements_by_version,
    format_json,
    format_markdown,
    format_text,
    load_requirements,
    load_requirements_full,
    run_impact,
)
from guard_helpers import FIXTURES_DIR


def _make_impact_config(req_file=None):
    """Build a config with impact section for testing."""
    impact: dict = {
        "output": {"format": "markdown", "file": None},
    }
    if req_file:
        impact["requirements"] = {
            "file": str(req_file),
            "id_column": "Req ID",
            "name_column": "Requirement Name",
            "format": "csv",
        }
    return deep_merge(CONFIG_DEFAULTS, {"impact": impact})


class TestCollectChangedFunctions:
    """Tests for collect_changed_functions."""

    def test_finds_changed_function(self, tmp_path):
        c_file = tmp_path / "test.c"
        c_file.write_text(
            dedent("""\
                /**
                 * @brief Do stuff.
                 * @version 1.1
                 * @req REQ-0252
                 */
                void Do_Stuff(void) {
                    new_impl();
                }
            """)
        )

        def mock_runner(cmd):
            return "@@ -6,1 +6,1 @@\n-old\n+new\n"

        result = collect_changed_functions(
            [str(c_file)],
            CONFIG_DEFAULTS,
            staged=True,
            run_command=mock_runner,
        )
        assert len(result) == 1
        assert result[0].name == "Do_Stuff"
        assert "REQ-0252" in result[0].reqs
        assert result[0].new_version == "1.1"

    def test_no_change_no_result(self, tmp_path):
        c_file = tmp_path / "test.c"
        c_file.write_text("void Func(void) { x(); }")

        def mock_runner(cmd):
            return ""

        result = collect_changed_functions(
            [str(c_file)],
            CONFIG_DEFAULTS,
            staged=True,
            run_command=mock_runner,
        )
        assert result == []

    def test_unknown_extension_skipped(self, tmp_path):
        rs_file = tmp_path / "test.rs"
        rs_file.write_text("fn foo() {}")

        def mock_runner(cmd):
            return "@@ -1,1 +1,1 @@\n-old\n+new\n"

        result = collect_changed_functions(
            [str(rs_file)],
            CONFIG_DEFAULTS,
            staged=True,
            run_command=mock_runner,
        )
        assert result == []


class TestLoadRequirements:
    """Tests for load_requirements."""

    def test_load_csv(self):
        config = _make_impact_config(req_file=FIXTURES_DIR / "impact" / "req.csv")
        reqs = load_requirements(config)
        assert reqs["REQ-0252"] == "BLE-First Pairing"
        assert reqs["REQ-0555"] == "OTA Download"

    def test_load_json(self, tmp_path, monkeypatch):
        req_file = tmp_path / "req.json"
        monkeypatch.chdir(tmp_path)
        req_file.write_text(
            json.dumps(
                [
                    {"Req ID": "REQ-0001", "Requirement Name": "Test Req"},
                ]
            )
        )
        config = deep_merge(
            CONFIG_DEFAULTS,
            {
                "impact": {
                    "requirements": {
                        "file": req_file.name,
                        "id_column": "Req ID",
                        "name_column": "Requirement Name",
                        "format": "json",
                    },
                },
            },
        )
        reqs = load_requirements(config)
        assert reqs["REQ-0001"] == "Test Req"

    def test_load_yaml(self, tmp_path, monkeypatch):
        req_file = tmp_path / "req.yaml"
        monkeypatch.chdir(tmp_path)
        req_file.write_text(
            dedent("""\
                - Req ID: REQ-0001
                  Requirement Name: YAML Req
            """)
        )
        config = deep_merge(
            CONFIG_DEFAULTS,
            {
                "impact": {
                    "requirements": {
                        "file": req_file.name,
                        "id_column": "Req ID",
                        "name_column": "Requirement Name",
                        "format": "yaml",
                    },
                },
            },
        )
        reqs = load_requirements(config)
        assert reqs["REQ-0001"] == "YAML Req"

    def test_no_requirements_config(self):
        reqs = load_requirements(CONFIG_DEFAULTS)
        assert reqs == {}

    def test_missing_file_raises(self):
        """A declared-but-absent catalog must fail loudly, not degrade to an empty dict."""
        config = deep_merge(
            CONFIG_DEFAULTS,
            {"impact": {"requirements": {"file": "nonexistent-req.csv", "format": "csv"}}},
        )
        with pytest.raises(RequirementsError, match="not found"):
            load_requirements(config)

    def test_out_of_tree_catalog_rejected(self, tmp_path):
        """A catalog outside the repo is refused before it is ever opened.

        Its rows are echoed back in validation errors, so an unconstrained path made
        the error channel a file-disclosure primitive.
        """
        outside = tmp_path / "secret.csv"
        outside.write_text("Req ID,name\nREQ-X,y\n")
        config = deep_merge(
            CONFIG_DEFAULTS,
            {"impact": {"requirements": {"file": str(outside), "format": "csv"}}},
        )
        with pytest.raises(ConfigError, match="must stay inside the repository"):
            load_requirements(config)

    def test_traversal_catalog_rejected(self):
        config = deep_merge(
            CONFIG_DEFAULTS,
            {"impact": {"requirements": {"file": "../../etc/passwd", "format": "csv"}}},
        )
        with pytest.raises(ConfigError, match="must stay inside the repository"):
            load_requirements(config)

    def test_declared_without_file_raises(self):
        config = deep_merge(CONFIG_DEFAULTS, {"impact": {"requirements": {"format": "csv"}}})
        with pytest.raises(RequirementsError, match="impact.requirements.file"):
            load_requirements(config)

    def test_unknown_format_raises(self, tmp_path, monkeypatch):
        catalog = tmp_path / "reqs.toml"
        monkeypatch.chdir(tmp_path)
        catalog.write_text("nope\n")
        config = deep_merge(
            CONFIG_DEFAULTS,
            {"impact": {"requirements": {"file": catalog.name, "format": "toml"}}},
        )
        with pytest.raises(RequirementsError, match="Unknown requirements format"):
            load_requirements(config)

    def test_wrong_yaml_shape_raises(self, tmp_path, monkeypatch):
        catalog = tmp_path / "reqs.yaml"
        monkeypatch.chdir(tmp_path)
        catalog.write_text("just-a-string\n")
        config = deep_merge(
            CONFIG_DEFAULTS,
            {"impact": {"requirements": {"file": catalog.name, "format": "yaml"}}},
        )
        with pytest.raises(RequirementsError, match="must be a mapping"):
            load_requirements(config)

    def test_mapping_form_loads(self, tmp_path, monkeypatch):
        catalog = tmp_path / "reqs.yaml"
        monkeypatch.chdir(tmp_path)
        catalog.write_text(
            dedent("""\
                requirements:
                  REQ-VAL-001:
                    name: Presence check
                    subsystem: Validate
            """)
        )
        config = deep_merge(
            CONFIG_DEFAULTS,
            {"impact": {"requirements": {"file": catalog.name, "format": "yaml"}}},
        )
        assert load_requirements(config)["REQ-VAL-001"] == "Presence check"

    def test_missing_name_field_raises(self, tmp_path, monkeypatch):
        catalog = tmp_path / "reqs.yaml"
        monkeypatch.chdir(tmp_path)
        catalog.write_text("requirements:\n  REQ-VAL-001:\n    subsystem: Validate\n")
        config = deep_merge(
            CONFIG_DEFAULTS,
            {"impact": {"requirements": {"file": catalog.name, "format": "yaml"}}},
        )
        with pytest.raises(RequirementsError, match="missing required field"):
            load_requirements(config)

    def test_id_failing_configured_pattern_raises(self, tmp_path, monkeypatch):
        catalog = tmp_path / "reqs.yaml"
        monkeypatch.chdir(tmp_path)
        catalog.write_text("requirements:\n  REQ-0001:\n    name: Legacy\n")
        config = deep_merge(
            CONFIG_DEFAULTS,
            {
                "validate": {"tags": {"req": {"pattern": r"^REQ-[A-Z]+-[0-9]{3}$"}}},
                "impact": {"requirements": {"file": catalog.name, "format": "yaml"}},
            },
        )
        with pytest.raises(RequirementsError, match="does not match"):
            load_requirements(config)


class TestBuildImpactReport:
    """Tests for build_impact_report."""

    def test_groups_by_requirement(self):
        config = _make_impact_config(req_file=FIXTURES_DIR / "impact" / "req.csv")
        changed = [
            ChangedFunction(name="FuncA", file_path="a.c", reqs=["REQ-0252"]),
            ChangedFunction(name="FuncB", file_path="b.c", reqs=["REQ-0252"]),
            ChangedFunction(name="FuncC", file_path="c.c", reqs=["REQ-0555"]),
        ]
        entries = build_impact_report(changed, config)
        assert len(entries) == 2

        req252 = next(e for e in entries if e.req_id == "REQ-0252")
        assert len(req252.functions) == 2
        assert req252.req_name == "BLE-First Pairing"

    def test_no_changes(self):
        entries = build_impact_report([], CONFIG_DEFAULTS)
        assert entries == []


class TestFormatMarkdown:
    """Tests for format_markdown."""

    def test_renders_table(self):
        entries = [
            ImpactEntry(
                req_id="REQ-0252",
                req_name="Pairing",
                functions=[ChangedFunction(name="Func", file_path="a.c", reqs=["REQ-0252"])],
            ),
        ]
        result = format_markdown(entries)
        assert "## Change Impact Report" in result
        assert "REQ-0252" in result
        assert "Func" in result
        assert "1 requirement(s)" in result

    def test_empty_report(self):
        result = format_markdown([])
        assert "No requirements affected" in result


class TestFormatJson:
    """Tests for format_json."""

    def test_valid_json(self):
        entries = [
            ImpactEntry(
                req_id="REQ-0001",
                functions=[ChangedFunction(name="F", file_path="a.c", new_version="1.0")],
            ),
        ]
        result = format_json(entries)
        data = json.loads(result)
        assert len(data) == 1
        assert data[0]["req_id"] == "REQ-0001"


class TestFormatText:
    """Tests for format_text."""

    def test_lists_reqs(self):
        entries = [
            ImpactEntry(req_id="REQ-0252"),
            ImpactEntry(req_id="REQ-0555"),
        ]
        result = format_text(entries)
        assert "REQ-0252" in result
        assert "REQ-0555" in result

    def test_empty_report(self):
        result = format_text([])
        assert "No requirements affected" in result


class TestRunImpact:
    """Integration tests for run_impact."""

    def test_full_pipeline(self, tmp_path):
        c_file = tmp_path / "test.c"
        c_file.write_text(
            dedent("""\
                /**
                 * @brief Func.
                 * @version 1.0
                 * @req REQ-0252
                 */
                void Func(void) {
                    impl();
                }
            """)
        )

        def mock_runner(cmd):
            return "@@ -6,1 +6,1 @@\n-old\n+new\n"

        config = _make_impact_config(req_file=FIXTURES_DIR / "impact" / "req.csv")
        result = run_impact(
            [str(c_file)],
            config,
            staged=True,
            run_command=mock_runner,
        )
        assert "REQ-0252" in result
        assert "Func" in result


class TestFilterRequirementsByVersion:
    """Tests for filter_requirements_by_version."""

    def test_no_version_gate_returns_all(self):
        reqs = {"REQ-001": {"Min Version": "v0.1.0"}, "REQ-002": {"Min Version": "v2.0.0"}}
        result = filter_requirements_by_version(reqs, CONFIG_DEFAULTS)
        assert result == reqs

    def test_future_reqs_filtered(self):
        reqs = {"REQ-001": {"Min Version": "v0.1.0"}, "REQ-002": {"Min Version": "v2.0.0"}}
        config = deep_merge(
            CONFIG_DEFAULTS,
            {
                "validate": {
                    "version_gate": {"current_version": "v1.0.0", "version_field": "Min Version"},
                },
            },
        )
        result = filter_requirements_by_version(reqs, config)
        assert "REQ-001" in result
        assert "REQ-002" not in result

    def test_current_reqs_kept(self):
        reqs = {"REQ-001": {"Min Version": "v0.5.0"}}
        config = deep_merge(
            CONFIG_DEFAULTS,
            {
                "validate": {
                    "version_gate": {"current_version": "v1.0.0", "version_field": "Min Version"},
                },
            },
        )
        result = filter_requirements_by_version(reqs, config)
        assert "REQ-001" in result

    def test_equal_version_kept(self):
        reqs = {"REQ-001": {"Min Version": "v1.0.0"}}
        config = deep_merge(
            CONFIG_DEFAULTS,
            {
                "validate": {
                    "version_gate": {"current_version": "v1.0.0", "version_field": "Min Version"},
                },
            },
        )
        result = filter_requirements_by_version(reqs, config)
        assert "REQ-001" in result


class TestCatalogFailuresAreUniform:
    """A malformed catalog must fail the same way regardless of format.

    Only the YAML loader wrapped its failures, so a malformed CSV or JSON catalog
    raised raw json.JSONDecodeError / OSError / AttributeError past the GuardError
    boundary as a traceback — same user error, two qualities of failure.
    """

    def _config(self, catalog, fmt, **extra):
        reqs = {"file": catalog.name, "format": fmt}
        reqs.update(extra)
        return deep_merge(CONFIG_DEFAULTS, {"impact": {"requirements": reqs}})

    def test_malformed_json_raises_requirements_error(self, tmp_path, monkeypatch):
        catalog = tmp_path / "reqs.json"
        catalog.write_text("{not valid json")
        monkeypatch.chdir(tmp_path)
        with pytest.raises(RequirementsError, match="Could not parse"):
            load_requirements(self._config(catalog, "json"))

    def test_json_object_instead_of_list_raises(self, tmp_path, monkeypatch):
        catalog = tmp_path / "reqs.json"
        catalog.write_text('{"REQ-VAL-001": {"name": "x"}}')
        monkeypatch.chdir(tmp_path)
        with pytest.raises(RequirementsError, match="list of rows"):
            load_requirements(self._config(catalog, "json"))

    def test_json_list_with_non_dict_element_does_not_crash(self, tmp_path, monkeypatch):
        """The JSON path lacked the isinstance guard its YAML twin had."""
        catalog = tmp_path / "reqs.json"
        catalog.write_text('["bare string", {"Req ID": "REQ-VAL-001", "name": "ok"}]')
        monkeypatch.chdir(tmp_path)
        reqs = load_requirements(self._config(catalog, "json", id_column="Req ID"))
        assert reqs == {"REQ-VAL-001": "ok"}

    def test_csv_missing_id_column_names_the_problem(self, tmp_path, monkeypatch):
        catalog = tmp_path / "reqs.csv"
        catalog.write_text("Wrong Header,name\nREQ-VAL-001,ok\n")
        monkeypatch.chdir(tmp_path)
        with pytest.raises(RequirementsError, match="is not in the header"):
            load_requirements(self._config(catalog, "csv", id_column="Req ID"))

    def test_csv_short_row_does_not_crash(self, tmp_path, monkeypatch):
        """A row shorter than the header yields None values via csv restval."""
        catalog = tmp_path / "reqs.csv"
        catalog.write_text("Req ID,name,extra\nREQ-VAL-001,ok\n")
        monkeypatch.chdir(tmp_path)
        reqs = load_requirements(self._config(catalog, "csv", id_column="Req ID"))
        assert reqs == {"REQ-VAL-001": "ok"}


class TestVersionFieldMustExist:
    """A missing version_field used to default to v0.0.0, activating every requirement.

    So a typo'd version_field — or rows omitting it — silently made the gate enforce
    nothing while appearing to work.
    """

    def _config(self, catalog, field_name):
        return deep_merge(
            CONFIG_DEFAULTS,
            {
                "validate": {
                    "version_gate": {"current_version": "v1.0.0", "version_field": field_name}
                },
                "impact": {"requirements": {"file": catalog.name, "format": "yaml"}},
            },
        )

    def _catalog(self, tmp_path, body):
        catalog = tmp_path / "reqs.yaml"
        catalog.write_text(dedent(body))
        return catalog

    def test_typoed_version_field_raises(self, tmp_path, monkeypatch):
        catalog = self._catalog(
            tmp_path,
            """\
                requirements:
                  REQ-VAL-001:
                    name: A req
                    min_version: v0.1.0
            """,
        )
        monkeypatch.chdir(tmp_path)
        config = self._config(catalog, "min_verison")  # typo
        with pytest.raises(RequirementsError, match="do not declare it"):
            filter_requirements_by_version(load_requirements_full(config), config)

    def test_row_missing_the_field_raises(self, tmp_path, monkeypatch):
        catalog = self._catalog(
            tmp_path,
            """\
                requirements:
                  REQ-VAL-001:
                    name: Has it
                    min_version: v0.1.0
                  REQ-VAL-002:
                    name: Missing it
            """,
        )
        monkeypatch.chdir(tmp_path)
        config = self._config(catalog, "min_version")
        with pytest.raises(RequirementsError) as exc:
            filter_requirements_by_version(load_requirements_full(config), config)
        assert any("REQ-VAL-002" in p for p in exc.value.problems)

    def test_all_rows_declaring_the_field_filters_normally(self, tmp_path, monkeypatch):
        catalog = self._catalog(
            tmp_path,
            """\
                requirements:
                  REQ-VAL-001:
                    name: Active
                    min_version: v0.1.0
                  REQ-VAL-002:
                    name: Future
                    min_version: v9.0.0
            """,
        )
        monkeypatch.chdir(tmp_path)
        config = self._config(catalog, "min_version")
        active = filter_requirements_by_version(load_requirements_full(config), config)
        assert set(active) == {"REQ-VAL-001"}
