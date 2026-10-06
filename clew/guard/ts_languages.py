"""Tree-sitter grammar loading and language-specific node type maps.

@brief Initialize tree-sitter parsers and provide node type mappings per language.
@version 1.0
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from tree_sitter import Language, Parser

logger = logging.getLogger(__name__)


## @brief Node type mappings and grammar module for a single language.
#  @details `doc_style` selects how the block above a definition is collected: "c" is a
#  single `/** */` comment, "python" is a run of `##` lines (or a docstring), "rust" is a
#  run of `///` lines or one `/** */` block, reached across any `#[...]` attributes.
#  @version 1.2
#  @dg_internal
@dataclass(frozen=True)
class LanguageSpec:
    grammar_module: str
    function_node_types: tuple[str, ...]
    comment_node_types: tuple[str, ...]
    doc_style: str = "c"


LANGUAGE_SPECS: dict[str, LanguageSpec] = {
    "c": LanguageSpec(
        grammar_module="tree_sitter_c",
        function_node_types=("function_definition",),
        comment_node_types=("comment",),
    ),
    "cpp": LanguageSpec(
        grammar_module="tree_sitter_cpp",
        function_node_types=("function_definition",),
        comment_node_types=("comment",),
    ),
    "python": LanguageSpec(
        grammar_module="tree_sitter_python",
        function_node_types=("function_definition",),
        comment_node_types=("comment",),
        doc_style="python",
    ),
    "rust": LanguageSpec(
        grammar_module="tree_sitter_rust",
        # `function_signature_item` (a trait method with no body) is a declaration, the
        # Rust analogue of a C prototype, and is skipped for the same reason.
        function_node_types=("function_item",),
        comment_node_types=("line_comment", "block_comment"),
        doc_style="rust",
    ),
}


## @brief Build the extension -> language table from the parsing substrate's registry.
#  @details The substrate (lang-parsing-substrate) is the one registry of which extension
#  is which language shared with knots, moldy and aurora-lint, so the gate reads it rather
#  than keeping a private copy. Only languages this gate has a LanguageSpec for are kept.
#  `explicit_only` extensions (C's `.h`) are included: the substrate leaves them out of
#  automatic detection because they are ambiguous, and this gate resolves the ambiguity
#  itself (see _looks_like_cpp_header).
#  @version 1.0
#  @req REQ-DDB-GUARD-020
#  @return Mapping of dotted extension to language name
def _substrate_extension_table() -> dict[str, str]:
    import lang_parsing_substrate

    table: dict[str, str] = {}
    for info in lang_parsing_substrate.languages():
        if info.key not in LANGUAGE_SPECS:
            continue
        for ext in (*info.extensions, *info.explicit_only):
            table.setdefault(f".{ext}", info.key)
    return table


EXTENSION_TO_LANGUAGE: dict[str, str] = _substrate_extension_table()


## @brief Load a tree-sitter Language object by importing the grammar module.
#  @version 1.0
#  @dg_internal
@lru_cache(maxsize=8)
def _load_language(grammar_module: str) -> Language:
    import importlib

    mod = importlib.import_module(grammar_module)
    return Language(mod.language())


## @brief Get a tree-sitter Parser for a named language.
#  @version 1.1
#  @req REQ-DDB-GUARD-020
#  @return Configured Parser instance, or None if language is unsupported
def get_parser_for_language(lang_name: str) -> Parser | None:
    spec = LANGUAGE_SPECS.get(lang_name)
    if spec is None:
        logger.warning("No tree-sitter spec for language: %s", lang_name)
        return None
    language = _load_language(spec.grammar_module)
    return Parser(language)


## @brief Get the LanguageSpec for a named language.
#  @version 1.1
#  @req REQ-DDB-GUARD-020
#  @return LanguageSpec for the language, or None if not defined
def get_language_spec(lang_name: str) -> LanguageSpec | None:
    return LANGUAGE_SPECS.get(lang_name)


## @brief Resolve a file extension to a language name.
#  @version 1.1
#  @req REQ-DDB-GUARD-020
#  @return Language name string, or None if the extension is unrecognized
def language_for_extension(ext: str) -> str | None:
    return EXTENSION_TO_LANGUAGE.get(ext)


## @brief Resolve a file path to a language name using config extensions.
#  @version 1.2
#  @req REQ-DDB-GUARD-020
#  @return Language name string, or None if no language matches the file
def language_for_file(file_path: str, config: dict[str, Any]) -> str | None:
    from pathlib import Path

    ext = Path(file_path).suffix
    lang = language_for_extension(ext)
    if lang == "c" and ext == ".h" and _looks_like_cpp_header(file_path):
        lang = "cpp"
    if lang is None:
        lang = _language_from_config(ext, config)
    return lang


## @brief Look up language name from user config extensions.
#  @version 1.0
#  @dg_internal
def _language_from_config(ext: str, config: dict[str, Any]) -> str | None:
    languages = config.get("validate", {}).get("languages", {})
    for lang_name, lang_config in languages.items():
        if ext in lang_config.get("extensions", []) and lang_name in LANGUAGE_SPECS:
            return lang_name
    return None


## @brief Detect C++ constructs in a .h file to route to cpp grammar.
#  @details Looks for namespace, class, template<, or access specifiers at file scope.
#  @version 1.0
#  @dg_internal
#  @return True if the header contains C++ constructs
def _looks_like_cpp_header(file_path: str) -> bool:
    try:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            content = f.read(8192)
    except OSError:
        return False
    import re

    patterns = (
        r"^\s*namespace\s+\w",
        r"^\s*template\s*<",
        r"^\s*class\s+\w",
        r"^\s*(?:public|private|protected)\s*:",
    )
    return any(re.search(p, content, re.MULTILINE) for p in patterns)
