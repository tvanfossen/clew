"""Tests for clew.guard.parser (absorbed from doxygen-guard)."""

from __future__ import annotations

from clew.guard.parser import parse_doxygen_tags
from guard_helpers import parse_c, parse_cpp


class TestParseTags:
    """Tests for parse_doxygen_tags."""

    def test_single_tag(self):
        block = "/** @brief Initialize the module. */"
        tags = parse_doxygen_tags(block)
        assert "brief" in tags
        assert tags["brief"] == ["Initialize the module."]

    def test_multiple_tags(self):
        block = """\
/**
 * @brief Do something.
 * @version 1.0
 * @req REQ-0001
 */"""
        tags = parse_doxygen_tags(block)
        assert tags["brief"] == ["Do something."]
        assert tags["version"] == ["1.0"]
        assert tags["req"] == ["REQ-0001"]

    def test_duplicate_tags(self):
        block = """\
/**
 * @brief Something.
 * @req REQ-0001
 * @req REQ-0002
 */"""
        tags = parse_doxygen_tags(block)
        assert len(tags["req"]) == 2
        assert "REQ-0001" in tags["req"]
        assert "REQ-0002" in tags["req"]

    def test_empty_block(self):
        block = "/** */"
        tags = parse_doxygen_tags(block)
        assert tags == {}


class TestParseFunctions:
    """Integration tests for parse_functions."""

    def test_simple_c_file(self, fixtures_dir):
        content = (fixtures_dir / "simple.c").read_text()
        functions = parse_c(content)

        assert len(functions) == 3
        assert functions[0].name == "Module_Init"
        assert functions[0].doxygen is not None
        assert "brief" in functions[0].doxygen.tags

        assert functions[1].name == "Module_Process"
        assert functions[1].doxygen is not None
        assert "version" in functions[1].doxygen.tags

        assert functions[2].name == "Undocumented_Function"
        assert functions[2].doxygen is None

    def test_forward_declarations_skipped(self, fixtures_dir):
        content = (fixtures_dir / "forward_decl.c").read_text()
        functions = parse_c(content)

        # Only the definition should be found, not the forward declarations
        assert len(functions) == 1
        assert functions[0].name == "Module_Init"
        assert functions[0].doxygen is not None

    def test_forward_declarations_are_always_skipped(self, fixtures_dir):
        """Bodyless declarations are never reported, and this is not configurable.

        Replaces a test that asserted skip_fwd=False yielded 3 functions. That passed
        only against the regex path, which no shipped language reaches: the production
        AST path skips bodyless functions unconditionally. The knob it exercised
        (presence.skip_forward_declarations) never did anything and has been removed.
        """
        content = (fixtures_dir / "forward_decl.c").read_text()
        functions = parse_c(content, skip_fwd=False)

        assert len(functions) == 1
        assert functions[0].name == "Module_Init"

    def test_exclude_names(self):
        content = """\
/**
 * @brief Real function.
 * @version 1.0
 */
void Real_Func(void) {
    if (x) {
        return;
    }
}
"""
        functions = parse_c(content)
        names = [f.name for f in functions]
        assert "Real_Func" in names
        # 'if' and 'return' should not appear even though they might match the pattern
        assert "if" not in names
        assert "return" not in names

    def test_body_end_tracking(self):
        content = """\
/**
 * @brief Func A.
 * @version 1.0
 */
void Func_A(void) {
    if (x) {
        y();
    }
}

/**
 * @brief Func B.
 * @version 1.0
 */
void Func_B(void) {
    z();
}
"""
        functions = parse_c(content)
        assert len(functions) == 2
        assert functions[0].name == "Func_A"
        assert functions[0].body_end == 8  # closing brace of Func_A
        assert functions[1].name == "Func_B"
        assert functions[1].body_end == 16  # closing brace of Func_B

    def test_tags_parsed_correctly(self, fixtures_dir):
        content = (fixtures_dir / "simple.c").read_text()
        functions = parse_c(content)

        process_func = functions[1]
        assert process_func.name == "Module_Process"
        assert process_func.doxygen is not None
        assert process_func.doxygen.tags["brief"] == ["Process incoming data."]
        assert process_func.doxygen.tags["version"] == ["1.2"]

    def test_arbitrary_tags_are_parsed(self):
        """The parser is vocabulary-agnostic; validation decides what is known.

        Kept separate from the fixture so the fixture can stay free of tags the tool
        does not act on, while still proving custom tags reach Function.doxygen.tags.
        """
        content = """\
/**
 * @brief Do work.
 * @version 1.0
 * @some_custom_tag VALUE_ONE
 * @another_tag second value
 */
void Work(void) { }
"""
        functions = parse_c(content)
        tags = functions[0].doxygen.tags
        assert tags["some_custom_tag"] == ["VALUE_ONE"]
        assert tags["another_tag"] == ["second value"]


class TestParseFunctionsCpp:
    """Tests for C++ function pattern matching."""

    def test_cpp_fixture_file(self, fixtures_dir):
        content = (fixtures_dir / "cpp_methods.cpp").read_text()
        functions = parse_cpp(content)
        names = [f.name for f in functions]
        assert "parse_name" in names
        assert "entropic_free" in names
        assert "contains" in names
        assert "getData" in names
        assert "simple_func" in names
        assert "Undocumented_Method" in names

    def test_namespaced_return_type(self, fixtures_dir):
        content = (fixtures_dir / "cpp_methods.cpp").read_text()
        functions = parse_cpp(content)
        by_name = {f.name: f for f in functions}
        assert by_name["parse_name"].doxygen is not None
        assert "brief" in by_name["parse_name"].doxygen.tags

    def test_extern_c_linkage(self, fixtures_dir):
        content = (fixtures_dir / "cpp_methods.cpp").read_text()
        functions = parse_cpp(content)
        by_name = {f.name: f for f in functions}
        assert "entropic_free" in by_name
        assert by_name["entropic_free"].doxygen is not None

    def test_class_qualified_method(self, fixtures_dir):
        content = (fixtures_dir / "cpp_methods.cpp").read_text()
        functions = parse_cpp(content)
        by_name = {f.name: f for f in functions}
        assert "contains" in by_name
        assert "getData" in by_name

    def test_undocumented_detected(self, fixtures_dir):
        content = (fixtures_dir / "cpp_methods.cpp").read_text()
        functions = parse_cpp(content)
        by_name = {f.name: f for f in functions}
        assert by_name["Undocumented_Method"].doxygen is None


class TestCppFirstMemberDoxygen:
    """A C++ class's first member must have its doxygen block found.

    Companion to the Python case: a definition that is the first statement in a
    field_declaration_list has no previous sibling, so the doxygen block above it is
    reachable only through the body node.
    """

    def test_first_member_after_access_specifier(self):
        content = """\
class Widget {
public:
    /**
     * @brief First method after the access specifier.
     * @version 1.0
     * @return one
     */
    int alpha() { return 1; }
};
"""
        by_name = {f.name: f for f in parse_cpp(content)}
        assert by_name["alpha"].doxygen is not None
        assert by_name["alpha"].doxygen.tags["version"] == ["1.0"]

    def test_first_member_with_no_access_specifier(self):
        content = """\
class Bare {
    /**
     * @brief First member, nothing before it in the class body.
     * @version 2.0
     * @return three
     */
    int gamma() { return 3; }
};
"""
        by_name = {f.name: f for f in parse_cpp(content)}
        assert by_name["gamma"].doxygen is not None
        assert by_name["gamma"].doxygen.tags["version"] == ["2.0"]

    def test_class_level_block_does_not_leak_to_first_member(self):
        content = """\
/**
 * @brief Doc for the class itself.
 * @version 9.9
 */
class Leaky {
    int undocumented() { return 0; }
};
"""
        by_name = {f.name: f for f in parse_cpp(content)}
        assert by_name["undocumented"].doxygen is None


class TestEscapedAtSign:
    r"""Doxygen writes a literal @ as \@ or @@; prose must be able to name a tag.

    Without escapes there was no way to mention a tag in documentation text: the
    mention became a real tag. This repo's own gate reported a phantom `@req IDs`
    from the sentence "each with its declared @req IDs".
    """

    def test_backslash_escape_is_not_a_tag(self):
        tags = parse_doxygen_tags(r"@return Each row with its declared \@req IDs")
        assert "req" not in tags
        assert tags["return"] == ["Each row with its declared @req IDs"]

    def test_double_at_escape_is_not_a_tag(self):
        tags = parse_doxygen_tags("@return Each row with its declared @@req IDs")
        assert "req" not in tags
        assert tags["return"] == ["Each row with its declared @req IDs"]

    def test_unescaped_mention_is_still_a_tag(self):
        """Doxygen-correct: an unescaped @word anywhere IS a command."""
        tags = parse_doxygen_tags("@return Each row with its declared @req IDs")
        assert tags["req"] == ["IDs"]

    def test_escape_in_brief_round_trips_single_at(self):
        tags = parse_doxygen_tags(r"@brief Skip functions marked \@internal here")
        assert "internal" not in tags
        assert tags["brief"] == ["Skip functions marked @internal here"]

    def test_genuine_inline_multi_tag_line_still_parses(self):
        tags = parse_doxygen_tags("@brief Do work @version 1.0 @return zero")
        assert tags["brief"] == ["Do work"]
        assert tags["version"] == ["1.0"]
        assert tags["return"] == ["zero"]

    def test_escaped_and_real_tag_on_one_line(self):
        tags = parse_doxygen_tags(r"@brief Mentions \@req only @version 2.0")
        assert tags["brief"] == ["Mentions @req only"]
        assert tags["version"] == ["2.0"]
        assert "req" not in tags

    def test_escape_at_start_of_line_is_not_a_tag(self):
        tags = parse_doxygen_tags("@brief Doc\n\\@version is written like this")
        assert "version" not in tags
        assert tags["brief"] == ["Doc @version is written like this"]

    def test_multiple_escapes_on_one_line(self):
        tags = parse_doxygen_tags(r"@brief Either \@req or \@internal applies")
        assert tags["brief"] == ["Either @req or @internal applies"]

    def test_no_sentinel_leaks_into_output(self):
        tags = parse_doxygen_tags(r"@brief Escaped \@req here")
        assert "\x00" not in tags["brief"][0]
