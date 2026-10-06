"""Tests for the machine-readable consumer contract.

These tests exist so that a consumer pinning doxygen-guard can detect its own drift
from this output. If a field here changes shape, CONTRACT_VERSION must move with it.
"""

from __future__ import annotations

import json
from textwrap import dedent

from clew.guard.config import (
    CONFIG_DEFAULTS,
    CONFIG_SCHEMA,
    REQUIREMENTS_NAME_COLUMN_DEFAULT,
    deep_merge,
    load_config,
    validate_config_schema,
)
from clew.guard.contract import (
    CONTRACT_VERSION,
    build_effective_contract,
    build_files_contract,
    build_schema_contract,
    render,
)


class TestSchemaContract:
    def test_is_json_serializable(self):
        assert json.loads(render(build_schema_contract()))

    def test_carries_contract_version(self):
        assert build_schema_contract()["contract_version"] == CONTRACT_VERSION

    def test_exposes_passthrough_prefix(self):
        assert build_schema_contract()["passthrough_prefix"] == "x-"

    def test_open_nodes_are_marked_not_dropped(self):
        schema = build_schema_contract()["config_schema"]
        assert schema["validate"]["languages"] == "<any>"
        assert schema["validate"]["tags"] == "<any>"

    def test_types_encoded_by_name(self):
        schema = build_schema_contract()["config_schema"]
        assert schema["output_dir"] == "str"
        assert schema["validate"]["presence"]["require_doxygen"] == "bool"

    def test_catalog_constants_match_the_module(self):
        catalog = build_schema_contract()["requirements_catalog"]
        assert catalog["name_column_default"] == REQUIREMENTS_NAME_COLUMN_DEFAULT
        assert catalog["root_key"] == "requirements"
        assert catalog["required_fields"] == ["name"]

    def test_id_column_scoped_to_flat_formats(self):
        """The mapping YAML form keys by ID, so id_column does not apply to it."""
        catalog = build_schema_contract()["requirements_catalog"]
        assert "yaml" not in catalog["formats_using_id_column"]
        assert set(catalog["formats_using_id_column"]) == {"csv", "json"}

    def test_trace_section_absent(self):
        assert "trace" not in build_schema_contract()["config_schema"]


class TestEffectiveContract:
    def test_reports_declared_requirements(self, tmp_path):
        config_file = tmp_path / ".doxygen-guard.yaml"
        config_file.write_text(
            dedent("""\
                impact:
                  requirements:
                    file: docs/requirements.yaml
                    format: yaml
            """)
        )
        resolved = build_effective_contract(load_config(config_file))["resolved"]
        assert resolved["requirements"]["declared"] is True
        assert resolved["requirements"]["file"] == "docs/requirements.yaml"
        assert resolved["requirements"]["format"] == "yaml"

    def test_reports_undeclared_requirements(self):
        resolved = build_effective_contract(CONFIG_DEFAULTS)["resolved"]
        assert resolved["requirements"] == {"declared": False}

    def test_exposes_exclude_patterns(self):
        config = deep_merge(CONFIG_DEFAULTS, {"validate": {"exclude": ["^vendor/"]}})
        assert build_effective_contract(config)["resolved"]["exclude"] == ["^vendor/"]

    def test_exposes_req_pattern(self):
        config = deep_merge(
            CONFIG_DEFAULTS, {"validate": {"tags": {"req": {"pattern": "^R-[0-9]+$"}}}}
        )
        assert build_effective_contract(config)["resolved"]["req_pattern"] == "^R-[0-9]+$"

    def test_lists_passthrough_sections(self, tmp_path):
        config_file = tmp_path / ".doxygen-guard.yaml"
        config_file.write_text("x-doxyguard-db:\n  index_path: .cache\n")
        contract = build_effective_contract(load_config(config_file))
        assert contract["passthrough_sections"] == ["x-doxyguard-db"]

    def test_is_json_serializable(self):
        assert json.loads(render(build_effective_contract(CONFIG_DEFAULTS)))


class TestFilesContract:
    def _tree(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "src" / "a.c").write_text("void A(void) { }")
        (tmp_path / "tests" / "test_a.c").write_text("void T(void) { }")
        return tmp_path

    def test_excluded_paths_are_absent(self, tmp_path, monkeypatch):
        root = self._tree(tmp_path)
        monkeypatch.chdir(root)
        config = deep_merge(CONFIG_DEFAULTS, {"validate": {"exclude": ["tests/"]}})
        contract = build_files_contract(["."], config)
        assert any("a.c" in f for f in contract["files"])
        assert not any("test_a.c" in f for f in contract["files"])

    def test_reports_the_patterns_that_produced_the_set(self, tmp_path, monkeypatch):
        monkeypatch.chdir(self._tree(tmp_path))
        config = deep_merge(CONFIG_DEFAULTS, {"validate": {"exclude": ["tests/"]}})
        assert build_files_contract(["."], config)["exclude"] == ["tests/"]

    def test_count_matches_file_list(self, tmp_path, monkeypatch):
        monkeypatch.chdir(self._tree(tmp_path))
        contract = build_files_contract(["."], CONFIG_DEFAULTS)
        assert contract["count"] == len(contract["files"])

    def test_without_excludes_test_files_are_included(self, tmp_path, monkeypatch):
        """Guards the test above: absence must come from the exclude, not from the walk."""
        monkeypatch.chdir(self._tree(tmp_path))
        contract = build_files_contract(["."], CONFIG_DEFAULTS)
        assert any("test_a.c" in f for f in contract["files"])

    def test_is_json_serializable(self, tmp_path, monkeypatch):
        monkeypatch.chdir(self._tree(tmp_path))
        assert json.loads(render(build_files_contract(["."], CONFIG_DEFAULTS)))


class TestContractRoundTrips:
    """`config --effective` output must be valid input.

    It echoed the merged config verbatim, including runtime-injected private keys, and
    the schema rejected an explicit null section — so a consumer that read the contract
    and fed it back got "Unknown config key" or "expected dict, got NoneType". There was
    no test, which is why it shipped.
    """

    def test_emitted_config_loads(self, tmp_path, monkeypatch):
        import yaml as _yaml

        monkeypatch.chdir(tmp_path)
        emitted = build_effective_contract(load_config(tmp_path / "nonexistent.yaml"))["config"]
        (tmp_path / ".doxygen-guard.yaml").write_text(_yaml.safe_dump(emitted))
        assert load_config(tmp_path / ".doxygen-guard.yaml")

    def test_private_keys_are_stripped(self):
        config = deep_merge(
            CONFIG_DEFAULTS,
            {"validate": {"version_gate": {"current_version": "auto:git", "_resolved": "v1.2.3"}}},
        )
        contract = build_effective_contract(config)
        assert "_resolved" not in contract["config"]["validate"]["version_gate"]
        assert "_resolved" not in contract["resolved"]["version_gate"]

    def test_null_section_is_accepted_by_the_schema(self):
        """impact.requirements ships as None; the schema must permit that shape."""
        assert validate_config_schema({"impact": {"requirements": None}}) == []


class TestResolvedIsGeneratedFromSchema:
    """ROADMAP promises every honoured declaration is observable in output.

    `resolved` was five hand-picked keys, so require_return, version.tag, extra_tags,
    known_tags_warn and duplicate_tags_error were invisible to a consumer reading the
    obvious field. It is now generated from CONFIG_SCHEMA and cannot drift.
    """

    def test_scalar_validate_keys_all_appear(self):
        from clew.guard.config import _OPEN_DICT

        resolved = build_effective_contract(CONFIG_DEFAULTS)["resolved"]
        expected = [
            k
            for k, spec in CONFIG_SCHEMA["validate"].items()
            if spec is not _OPEN_DICT and not isinstance(spec, dict)
        ]
        assert expected, "expected scalar keys under validate.*"
        for key in expected:
            assert key in resolved, key

    def test_adding_a_schema_key_shows_up_without_touching_contract_py(self):
        """The property that makes drift impossible, asserted directly."""
        from clew.guard.config import _OPEN_DICT

        scalars = {
            k
            for k, v in CONFIG_SCHEMA["validate"].items()
            if v is not _OPEN_DICT and not isinstance(v, dict)
        }
        resolved_keys = set(build_effective_contract(CONFIG_DEFAULTS)["resolved"])
        assert scalars <= resolved_keys


class TestContractEnvelopeShape:
    """CONTRACT_VERSION is a promise about shape; nothing asserted the shape.

    The previous tests checked individual fields, so a dropped field would not fail —
    which is the one thing a version-pinned consumer depends on.
    """

    SCHEMA_KEYS = {
        "contract_version",
        "passthrough_prefix",
        "config_schema",
        "config_defaults",
        "opt_in_language_defaults",
        "requirements_catalog",
    }
    EFFECTIVE_KEYS = {"contract_version", "config", "resolved", "passthrough_sections"}
    FILES_KEYS = {
        "contract_version",
        "source_dirs",
        "exclude",
        "toolchain_config",
        "toolchain_ignores",
        "files",
        "count",
    }
    CATALOG_KEYS = {
        "root_key",
        "format_default",
        "id_column_default",
        "name_column_default",
        "required_fields",
        "optional_fields",
        "formats_using_id_column",
    }

    def test_schema_envelope(self):
        assert set(build_schema_contract()) == self.SCHEMA_KEYS

    def test_opt_in_languages_are_published_but_not_in_force(self):
        contract = build_schema_contract()
        assert "rust" in contract["opt_in_language_defaults"]
        assert "rust" not in contract["config_defaults"]["validate"]["languages"]

    def test_catalog_block_envelope(self):
        assert set(build_schema_contract()["requirements_catalog"]) == self.CATALOG_KEYS

    def test_effective_envelope(self):
        assert set(build_effective_contract(CONFIG_DEFAULTS)) == self.EFFECTIVE_KEYS

    def test_files_envelope(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert set(build_files_contract(["."], CONFIG_DEFAULTS)) == self.FILES_KEYS

    def test_contract_version_is_an_int(self):
        assert isinstance(CONTRACT_VERSION, int)


class TestFilesAgreesWithTheGate:
    """`files` is documented as authoritative, so its predicate must match the gate's.

    The exclude patterns are applied by two separate call sites — main.validate_file and
    tags.find_source_files — and both must reach the same verdict for the same path.
    """

    def test_excluded_path_is_absent_and_gate_skips_it(self, tmp_path, monkeypatch):
        from clew.guard.main import validate_file

        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "src" / "a.c").write_text("void A(void) { }")
        (tmp_path / "tests" / "t.c").write_text("void T(void) { }")
        monkeypatch.chdir(tmp_path)
        config = deep_merge(CONFIG_DEFAULTS, {"validate": {"exclude": ["^tests/"]}})

        listed = build_files_contract(["."], config)["files"]
        assert not any("tests/t.c" in f for f in listed)
        assert validate_file("tests/t.c", config, no_git=True) == []

        assert any("src/a.c" in f for f in listed)
        assert validate_file("src/a.c", config, no_git=True) != []

    def test_nested_lookalike_path_agrees(self, tmp_path, monkeypatch):
        """^tests/ must not match src/tests/, in either the listing or the gate."""
        from clew.guard.main import validate_file

        (tmp_path / "src" / "tests").mkdir(parents=True)
        (tmp_path / "src" / "tests" / "n.c").write_text("void N(void) { }")
        monkeypatch.chdir(tmp_path)
        config = deep_merge(CONFIG_DEFAULTS, {"validate": {"exclude": ["^tests/"]}})

        listed = build_files_contract(["."], config)["files"]
        assert any("src/tests/n.c" in f for f in listed)
        assert validate_file("src/tests/n.c", config, no_git=True) != []
