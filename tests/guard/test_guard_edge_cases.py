"""Edge case tests covering capability analysis findings."""

from __future__ import annotations

from textwrap import dedent

from clew.guard.checks import check_presence, check_tags, check_version_staleness
from clew.guard.config import CONFIG_DEFAULTS, deep_merge
from clew.guard.main import validate_file
from guard_helpers import FIXTURES_DIR, parse_c, parse_cpp


class TestDecorativeComments:
    """Verify decorative /*** blocks are not mistaken for doxygen."""

    def test_decorative_not_treated_as_doxygen(self):
        content = (FIXTURES_DIR / "mixed_comments.c").read_text()
        functions = parse_c(content)
        names = {f.name: f for f in functions}

        # Decorative block should NOT be associated with the function
        assert names["Documented_After_Decorative"].doxygen is not None
        assert "brief" in names["Documented_After_Decorative"].doxygen.tags

        # Functions after decorative/regular/line comments should have no doxygen
        assert names["After_Regular_Comment"].doxygen is None
        assert names["After_Line_Comment"].doxygen is None
        assert names["After_Second_Decorative"].doxygen is None

    def test_decorative_triggers_presence_violation(self):
        violations = validate_file(
            str(FIXTURES_DIR / "mixed_comments.c"),
            CONFIG_DEFAULTS,
            no_git=True,
        )
        # 3 undocumented functions: After_Regular_Comment, After_Line_Comment,
        # After_Second_Decorative
        undoc_violations = [v for v in violations if "no doxygen comment" in v.message]
        assert len(undoc_violations) == 3

    def test_double_star_still_matches(self):
        """Ensure /** (exactly two stars) is still recognized."""
        lines = [
            "/** @brief Test. @version 1.0 */",
            "void Func(void) {",
        ]
        functions = parse_c("\n".join(lines))
        assert len(functions) == 1
        assert functions[0].doxygen is not None


class TestVersionStaleness:
    """Verify staleness detection against a simulated HEAD revision of the fixture."""

    def test_stale_version_detected(self):
        content = (FIXTURES_DIR / "stale_version.c").read_text()
        functions = parse_c(content)

        # Simulate: Stale_Func body changed since HEAD, @version was not touched.
        # "new_implementation();" (not the "also_" prefixed one) is unique to Stale_Func.
        head_content = content.replace("    new_implementation();", "    old_implementation();")
        head_functions = parse_c(head_content)

        violations = check_version_staleness(
            functions,
            "stale_version.c",
            CONFIG_DEFAULTS,
            content,
            head_functions,
            head_content,
        )
        assert len(violations) == 1
        assert "Stale_Func" in violations[0].message
        assert "not updated" in violations[0].message

    def test_updated_version_no_violation(self):
        content = (FIXTURES_DIR / "stale_version.c").read_text()
        functions = parse_c(content)

        # Simulate: Updated_Func body changed AND @version was bumped since HEAD.
        head_content = content.replace(
            "also_new_implementation();", "also_old_implementation();"
        ).replace("@version 1.1", "@version 1.0")
        head_functions = parse_c(head_content)

        violations = check_version_staleness(
            functions,
            "stale_version.c",
            CONFIG_DEFAULTS,
            content,
            head_functions,
            head_content,
        )
        assert violations == []

    def test_unmodified_overloads_no_violation(self):
        """Regression for #11: same-named overloads (tinyfsm-style react() dispatch)
        must not collide in the HEAD identity lookup on an otherwise unmodified tree."""
        content = dedent("""\
            class RobotMissionFsm {
            public:
                /**
                 * @brief Handle event A.
                 * @version 1.0.0
                 */
                virtual void react(EventA const& e) {
                    handle_a(e);
                }

                /**
                 * @brief Handle event B.
                 * @version 1.0.0
                 */
                virtual void react(EventB const& e) {
                    handle_b(e);
                }

                /**
                 * @brief Handle event C.
                 * @version 1.0.0
                 */
                virtual void react(EventC const& e) {
                    handle_c(e);
                }
            };
        """)
        functions = parse_cpp(content)
        assert len(functions) == 3

        # Unmodified tree: HEAD content is identical to the working tree.
        violations = check_version_staleness(
            functions,
            "robot_mission_fsm.hpp",
            CONFIG_DEFAULTS,
            content,
            functions,
            content,
        )
        assert violations == []

    def test_modified_overload_flags_only_that_overload(self):
        """Changing one overload's body must not falsely flag its siblings."""
        head_content = dedent("""\
            class Fsm {
            public:
                /**
                 * @brief Handle event A.
                 * @version 1.0.0
                 */
                virtual void react(EventA const& e) {
                    old_handle_a(e);
                }

                /**
                 * @brief Handle event B.
                 * @version 1.0.0
                 */
                virtual void react(EventB const& e) {
                    handle_b(e);
                }
            };
        """)
        content = head_content.replace("old_handle_a(e);", "new_handle_a(e);")
        functions = parse_cpp(content)
        head_functions = parse_cpp(head_content)

        violations = check_version_staleness(
            functions,
            "fsm.hpp",
            CONFIG_DEFAULTS,
            content,
            head_functions,
            head_content,
        )
        assert len(violations) == 1
        assert violations[0].line == functions[0].def_line + 1  # the react(EventA) overload


class TestTagValidation:
    """Verify tag validation with fixture file."""

    def _make_tag_config(self):
        return deep_merge(
            CONFIG_DEFAULTS,
            {
                "validate": {
                    "tags": {
                        "req": {
                            "pattern": r"^REQ-\w+$",
                        },
                        "sends": {"require_prefix": ["EVENT_", "FSM_"]},
                        "calls": {"require_contains": "::"},
                    },
                },
            },
        )

    def test_bad_tags_all_fail(self):
        content = (FIXTURES_DIR / "bad_tags.c").read_text()
        config = self._make_tag_config()
        functions = parse_c(content)

        violations = check_tags(functions, "bad_tags.c", config)
        bad_func_violations = [v for v in violations if "Bad_Tags" in v.message]

        # @req INVALID-FORMAT → pattern fail + missing confidence marker
        # @sends BADPREFIX_EVENT → prefix fail
        # @calls modfunc → contains fail
        assert len(bad_func_violations) >= 3

        messages = " ".join(v.message for v in bad_func_violations)
        assert "does not match pattern" in messages
        assert "does not start with" in messages
        assert "does not contain" in messages

    def test_good_tags_all_pass(self):
        content = (FIXTURES_DIR / "bad_tags.c").read_text()
        config = self._make_tag_config()
        functions = parse_c(content)

        violations = check_tags(functions, "bad_tags.c", config)
        good_func_violations = [v for v in violations if "Good_Tags" in v.message]
        assert good_func_violations == []


class TestBracesInStrings:
    """Document known limitation: brace counting in strings."""

    def test_braces_in_strings_body_end(self):
        """Brace counting does not account for braces inside string literals.

        This documents a known limitation. The parser counts ALL braces,
        including those in strings. For most real code this works because
        string braces are balanced (e.g., printf("{}")).
        """
        content = (FIXTURES_DIR / "braces_in_strings.c").read_text()
        functions = parse_c(content)

        names = [f.name for f in functions]
        assert "Braces_In_String" in names
        assert "After_String_Braces" in names

        # With balanced string braces, body end detection still works
        braces_func = [f for f in functions if f.name == "Braces_In_String"][0]
        after_func = [f for f in functions if f.name == "After_String_Braces"][0]

        # Braces_In_String body should end before After_String_Braces starts
        assert braces_func.body_end < after_func.def_line

    def test_unbalanced_string_brace_is_handled_correctly(self):
        """The AST parser is not confused by an unbalanced brace inside a string.

        This test previously asserted body_end > 6, documenting a "known limitation"
        that only ever existed in the regex path — that path counted every brace in the
        file including those inside string literals. tree-sitter tokenises strings, so
        the limitation does not exist in production. Recorded as a capability, not a
        caveat.
        """
        content = dedent("""\
            /**
             * @brief Problematic function.
             * @version 1.0
             */
            void Unbalanced(void) {
                printf("extra { here");
            }

            /**
             * @brief Should be separate.
             * @version 1.0
             */
            void Next_Func(void) {
                clean();
            }
        """)
        functions = parse_c(content)

        unbal = [f for f in functions if f.name == "Unbalanced"][0]
        next_func = [f for f in functions if f.name == "Next_Func"][0]
        assert unbal.body_end == 6
        assert unbal.body_end < next_func.def_line


class TestForwardDeclarationMix:
    """Verify forward declarations mixed with definitions."""

    def test_only_definitions_checked(self):
        violations = validate_file(
            str(FIXTURES_DIR / "forward_decl.c"),
            CONFIG_DEFAULTS,
            no_git=True,
        )
        # Only the definition (Module_Init with doxygen) should be checked.
        # No violations expected since it has @brief and @version.
        assert violations == []

    def test_undocumented_definition_after_decl(self):
        content = dedent("""\
            void Helper(int x);

            void Helper(int x) {
                do_stuff(x);
            }
        """)
        functions = parse_c(content)
        # Forward declaration skipped, definition found
        assert len(functions) == 1
        assert functions[0].name == "Helper"
        assert functions[0].doxygen is None

        violations = check_presence(functions, "test.c", CONFIG_DEFAULTS)
        assert len(violations) == 1
        assert "no doxygen comment" in violations[0].message


class TestGccAttributes:
    """Verify __attribute__ between doxygen and function signature is handled."""

    def test_attribute_visibility_hidden(self):
        content = (FIXTURES_DIR / "attribute.c").read_text()
        functions = parse_c(content)
        names = {f.name: f for f in functions}

        assert "queue_inbound_event" in names
        assert names["queue_inbound_event"].doxygen is not None
        assert "brief" in names["queue_inbound_event"].doxygen.tags

    def test_attribute_unused(self):
        content = (FIXTURES_DIR / "attribute.c").read_text()
        functions = parse_c(content)
        names = {f.name: f for f in functions}

        assert "unused_callback" in names
        assert names["unused_callback"].doxygen is not None
        assert "version" in names["unused_callback"].doxygen.tags

    def test_no_false_positives_with_attributes(self):
        violations = validate_file(
            str(FIXTURES_DIR / "attribute.c"),
            CONFIG_DEFAULTS,
            no_git=True,
        )
        assert violations == []

    def test_attribute_inline(self):
        """__attribute__ on same line as other content still works."""
        content = dedent("""\
            /**
             * @brief Inlined helper.
             * @version 1.0
             */
            __attribute__((always_inline))
            void inline_helper(void) {
                fast_stuff();
            }
        """)
        functions = parse_c(content)
        assert len(functions) == 1
        assert functions[0].doxygen is not None

    def test_multiline_attribute_is_handled_correctly(self):
        """Multi-line __attribute__ breaks doxygen association (known limitation)."""
        content = dedent("""\
            /**
             * @brief Multi-attr function.
             * @version 1.0
             */
            __attribute__((visibility("hidden"),
                           unused))
            void multi_attr(void) {
                work();
            }
        """)
        functions = parse_c(content)
        assert len(functions) == 1
        # The AST path associates the block through the multi-line attribute. The
        # former assertion (doxygen is None) encoded a regex-path limitation: its
        # backward scan stopped on the attribute's second line and never found */.
        # That limitation does not exist in production.
        assert functions[0].doxygen is not None
        assert functions[0].doxygen.tags["brief"] == ["Multi-attr function."]


class TestTypedefReturnsAndMacroQualifiers:
    """Verify function detection with typedef return types and macro qualifiers."""

    def test_lowercase_typedef_return(self):
        content = (FIXTURES_DIR / "typedef_returns.c").read_text()
        functions = parse_c(content)
        names = {f.name: f for f in functions}
        assert "get_status" in names
        assert names["get_status"].doxygen is not None

    def test_typedef_pointer_return(self):
        content = (FIXTURES_DIR / "typedef_returns.c").read_text()
        functions = parse_c(content)
        names = {f.name: f for f in functions}
        assert "find_config" in names
        assert names["find_config"].doxygen is not None

    def test_static_macro_qualifier(self):
        content = (FIXTURES_DIR / "typedef_returns.c").read_text()
        functions = parse_c(content)
        names = {f.name: f for f in functions}
        assert "internal_helper" in names
        assert names["internal_helper"].doxygen is not None

    def test_weak_macro_qualifier(self):
        content = (FIXTURES_DIR / "typedef_returns.c").read_text()
        functions = parse_c(content)
        names = {f.name: f for f in functions}
        assert "default_handler" in names
        assert names["default_handler"].doxygen is not None

    def test_undocumented_typedef_detected(self):
        content = (FIXTURES_DIR / "typedef_returns.c").read_text()
        functions = parse_c(content)
        names = {f.name: f for f in functions}
        assert "undocumented_func" in names
        assert names["undocumented_func"].doxygen is None

    def test_no_false_positives(self):
        violations = validate_file(
            str(FIXTURES_DIR / "typedef_returns.c"),
            CONFIG_DEFAULTS,
            no_git=True,
        )
        # Only undocumented_func should fail
        assert len(violations) == 1
        assert "undocumented_func" in violations[0].message

    def test_inline_typedef_return(self):
        content = dedent("""\
            /**
             * @brief Convert error code.
             * @version 1.0
             */
            err_code_t convert_error(int raw) {
                return (err_code_t)raw;
            }
        """)
        functions = parse_c(content)
        assert len(functions) == 1
        assert functions[0].name == "convert_error"
        assert functions[0].doxygen is not None

    def test_struct_qualified_return(self):
        content = dedent("""\
            /**
             * @brief Create a new node.
             * @version 1.0
             */
            struct node* create_node(int value) {
                return allocate(value);
            }
        """)
        functions = parse_c(content)
        assert len(functions) == 1
        assert functions[0].name == "create_node"
