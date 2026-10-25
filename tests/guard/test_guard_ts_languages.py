"""Tests for clew.guard.ts_languages (absorbed from doxygen-guard)."""

from __future__ import annotations

from clew.guard.ts_languages import (
    LANGUAGE_SPECS,
    get_language_spec,
    get_parser_for_language,
    language_for_extension,
    language_for_file,
)

# Every language parses through lang-parsing-substrate (clew/tsnode.py), as the harvest does.
from clew.tsnode import Parser


class TestGetParserForLanguage:
    """Tests for grammar loading and parser creation."""

    def test_c_parser_produces_tree(self):
        parser = get_parser_for_language("c")
        assert isinstance(parser, Parser)
        tree = parser.parse(b"int main() { return 0; }")
        assert tree.root_node.type == "translation_unit"

    def test_cpp_parser_produces_tree(self):
        parser = get_parser_for_language("cpp")
        assert isinstance(parser, Parser)
        tree = parser.parse(b"void Foo::bar() {}")
        assert tree.root_node.child_count > 0

    def test_python_parser_produces_tree(self):
        parser = get_parser_for_language("python")
        assert isinstance(parser, Parser)
        tree = parser.parse(b"def hello():\n    pass\n")
        assert tree.root_node.type == "module"

    def test_unknown_language_returns_none(self):
        assert get_parser_for_language("zig") is None


class TestLanguageSpec:
    """Tests for LanguageSpec node type mappings."""

    def test_c_spec_has_function_definition(self):
        spec = get_language_spec("c")
        assert spec is not None
        assert "function_definition" in spec.function_node_types

    def test_all_specs_declare_function_and_comment_nodes(self):
        """Replaces two tests that pinned vestigial tracer fields.

        call_node_type, control_flow_types, return_type_field and void_types were
        populated for every language and read by nothing — they fed the deleted
        call-graph engine. These two are what the production path actually consumes.
        """
        for lang_name, spec in LANGUAGE_SPECS.items():
            assert spec.function_node_types, f"{lang_name} declares no function nodes"
            assert spec.comment_node_types, f"{lang_name} declares no comment nodes"


class TestExtensionMapping:
    """Tests for file extension to language resolution."""

    def test_c_extensions(self):
        assert language_for_extension(".c") == "c"
        assert language_for_extension(".h") == "c"

    def test_cpp_extensions(self):
        assert language_for_extension(".cpp") == "cpp"
        assert language_for_extension(".hpp") == "cpp"
        assert language_for_extension(".cc") == "cpp"

    def test_python_extension(self):
        assert language_for_extension(".py") == "python"

    def test_unknown_extension(self):
        assert language_for_extension(".zig") is None

    def test_language_for_file_with_config(self):
        config = {
            "validate": {
                "languages": {
                    "c": {"extensions": [".c", ".h"]},
                },
            },
        }
        assert language_for_file("src/main.c", config) == "c"

    def test_language_for_file_unknown(self):
        assert language_for_file("src/main.zig", {}) is None

    def test_h_file_with_namespace_detected_as_cpp(self, tmp_path):
        """C++ .h file with namespace routes to cpp grammar, not c."""
        f = tmp_path / "header.h"
        f.write_text("namespace foo {\nclass Bar {};\n}\n")
        assert language_for_file(str(f), {}) == "cpp"

    def test_h_file_with_class_detected_as_cpp(self, tmp_path):
        """C++ .h file with class routes to cpp grammar."""
        f = tmp_path / "header.h"
        f.write_text("class Foo {\npublic:\n  void bar();\n};\n")
        assert language_for_file(str(f), {}) == "cpp"

    def test_h_file_with_template_detected_as_cpp(self, tmp_path):
        """C++ .h file with template routes to cpp grammar."""
        f = tmp_path / "header.h"
        f.write_text("template<typename T>\nvoid foo(T x) {}\n")
        assert language_for_file(str(f), {}) == "cpp"

    def test_plain_c_h_file_stays_c(self, tmp_path):
        """Plain C .h file without C++ constructs stays as c."""
        f = tmp_path / "header.h"
        f.write_text("#ifndef FOO_H\n#define FOO_H\nvoid bar(void);\n#endif\n")
        assert language_for_file(str(f), {}) == "c"
