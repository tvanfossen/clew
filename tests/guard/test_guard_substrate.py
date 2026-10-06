"""The gate's extension -> language table comes from lang-parsing-substrate.

The substrate is the shared registry knots, moldy and aurora-lint read; the gate keeps no
private copy, so these tests pin the derivation rather than a literal table.
"""

from __future__ import annotations

import lang_parsing_substrate

from clew.guard.ts_languages import EXTENSION_TO_LANGUAGE, LANGUAGE_SPECS, language_for_file


def test_every_substrate_extension_for_a_gated_language_is_mapped():
    expected = {
        f".{ext}": info.key
        for info in lang_parsing_substrate.languages()
        if info.key in LANGUAGE_SPECS
        for ext in (*info.extensions, *info.explicit_only)
    }
    assert EXTENSION_TO_LANGUAGE == expected


def test_languages_without_a_spec_are_not_mapped():
    """Go is in the substrate but the gate has no LanguageSpec for it."""
    assert ".go" not in EXTENSION_TO_LANGUAGE
    assert language_for_file("main.go", {}) is None


def test_tsx_is_routed_to_the_jsx_aware_grammar():
    """The substrate files `.tsx` under typescript; the gate parses it with the tsx grammar."""
    assert EXTENSION_TO_LANGUAGE[".tsx"] == "typescript"
    assert language_for_file("App.tsx", {}) == "tsx"
    assert language_for_file("app.ts", {}) == "typescript"


def test_c_header_is_mapped_although_the_substrate_marks_it_explicit_only():
    """`.h` is ambiguous, so the substrate keeps it out of automatic detection; the gate
    maps it to C and then sniffs for C++ itself."""
    assert EXTENSION_TO_LANGUAGE[".h"] == "c"


def test_every_language_spec_is_reachable_by_some_extension():
    """Every spec but `tsx` comes from the registry; `tsx` is reached by language_for_file."""
    assert set(LANGUAGE_SPECS) - {"tsx"} == set(EXTENSION_TO_LANGUAGE.values())
