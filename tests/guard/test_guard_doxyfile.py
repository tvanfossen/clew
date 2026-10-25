"""Tests for Doxyfile fragment generation.

The fragment exists because doxygen-guard invents tags doxygen does not define, so a
project running both tools got unknown-command warnings on files written to satisfy the
gate. Declaring them as ALIASES is doxygen's supported extension mechanism.
"""

from __future__ import annotations

from clew.guard.checks import EXEMPTION_TAGS, TOOL_OWNED_TAGS
from clew.guard.config import CONFIG_DEFAULTS, deep_merge
from clew.guard.doxyfile import build_fragment, tool_tags_for


class TestToolTagsFor:
    def test_every_tool_owned_tag_is_included(self):
        tags = set(tool_tags_for(CONFIG_DEFAULTS))
        assert tags >= TOOL_OWNED_TAGS

    def test_real_doxygen_commands_are_never_aliased(self):
        """Aliasing a standard command would override doxygen's own definition."""
        tags = set(tool_tags_for(CONFIG_DEFAULTS))
        assert tags.isdisjoint({"brief", "version", "return", "returns", "file", "param"})

    def test_custom_configured_tags_are_included(self):
        config = deep_merge(CONFIG_DEFAULTS, {"validate": {"tags": {"mytag": {"pattern": ".*"}}}})
        assert "mytag" in tool_tags_for(config)

    def test_extra_tags_are_included(self):
        config = deep_merge(CONFIG_DEFAULTS, {"validate": {"extra_tags": ["sends", "@receives"]}})
        tags = tool_tags_for(config)
        assert "sends" in tags
        assert "receives" in tags, "the leading at-sign should be stripped"

    def test_non_default_version_tag_is_included(self):
        """Pointing the revision counter at a custom tag means doxygen needs that too."""
        config = deep_merge(CONFIG_DEFAULTS, {"validate": {"version": {"tag": "@revision"}}})
        assert "revision" in tool_tags_for(config)

    def test_default_version_tag_is_not_aliased(self):
        assert "version" not in tool_tags_for(CONFIG_DEFAULTS)


class TestBuildFragment:
    def test_declares_an_alias_for_every_tool_tag(self):
        fragment = build_fragment(CONFIG_DEFAULTS)
        for tag in tool_tags_for(CONFIG_DEFAULTS):
            assert f'ALIASES += "{tag}' in fragment, tag

    def test_exemption_markers_map_to_nothing(self):
        """Markers carry no payload, so they should render as empty rather than a section."""
        fragment = build_fragment(CONFIG_DEFAULTS)
        for tag in sorted(EXEMPTION_TAGS):
            assert f'ALIASES += "{tag}="' in fragment, tag

    def test_req_becomes_a_cross_referenced_section(self):
        fragment = build_fragment(CONFIG_DEFAULTS)
        assert "xrefitem req" in fragment
        assert "Requirement" in fragment

    def test_enables_validity_checking(self):
        assert "WARN_IF_DOC_ERROR = YES" in build_fragment(CONFIG_DEFAULTS)

    def test_policy_warnings_are_opt_in_not_default(self):
        """Measured: enabling these produces 399 warnings against this repo, none of
        which are defects by doxygen-guard's standard — 309 are WARN_NO_PARAMDOC
        demanding @param for every parameter. Turning them on by default would impose
        doxygen's policy on adopters, inverting the division of authority.
        """
        fragment = build_fragment(CONFIG_DEFAULTS)
        for key in ("WARN_IF_UNDOCUMENTED", "WARN_NO_PARAMDOC"):
            assert f"# {key} = YES" in fragment, f"{key} should be a commented opt-in"
            assert f"\n{key} = YES" not in fragment, f"{key} must not be active"

    def test_internal_docs_enabled_so_markers_hide_nothing(self):
        """\\internal-style suppression is exactly the bug the exemption rename avoided."""
        assert "INTERNAL_DOCS = YES" in build_fragment(CONFIG_DEFAULTS)

    def test_is_include_ready(self):
        fragment = build_fragment(CONFIG_DEFAULTS)
        assert fragment.endswith("\n")
        assert "@INCLUDE" in fragment, "should document how to include it"

    def test_needs_no_doxygen_installed(self):
        """Pure text generation — doxygen is never a runtime dependency of the gate."""
        assert isinstance(build_fragment(CONFIG_DEFAULTS), str)
