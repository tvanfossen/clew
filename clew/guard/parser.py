"""Doxygen block parsing and the parse entry point.

@brief Parse doxygen tag blocks and dispatch function detection to the AST parser.
@version 2.0

Function detection itself lives in ts_parser.py. This module owns the shared data
models, doxygen tag parsing, and the single parse entry point. The former regex-based
detection path was removed in 1.4.0: it was unreachable for every shipped language,
because parse_source_file_with_content always resolves a language name.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


## @brief Represents a doxygen comment with its location and parsed tags.
#  @version 1.0
#  @dg_internal
@dataclass
class DoxygenBlock:
    start_line: int  # 0-indexed
    end_line: int  # 0-indexed
    tags: dict[str, list[str]] = field(default_factory=dict)
    raw: str = ""


## @brief Represents a function with its location and optional doxygen block.
#  @version 1.3
#  @dg_internal
@dataclass
class Function:
    name: str
    def_line: int  # 0-indexed
    body_end: int  # 0-indexed
    doxygen: DoxygenBlock | None = None
    enclosing_class: str | None = None
    # Whitespace-normalized parameter list text, e.g. "(Event const& e)". Distinguishes
    # overloads sharing a name — see checks._index_by_identity.
    signature: str = ""
    # Whether the function returns no value, when the parser knows (JS/TS, from the
    # annotation). None leaves the decision to checks._is_void_function's text heuristics.
    returns_void: bool | None = None

    ## @brief Check if this function is a constructor of its enclosing class.
    #  @version 1.0
    #  @dg_internal
    #  @return True if name matches enclosing class name
    def is_constructor(self) -> bool:
        return self.enclosing_class is not None and self.name == self.enclosing_class

    ## @brief Check if this function is a destructor of its enclosing class.
    #  @version 1.0
    #  @dg_internal
    #  @return True if name starts with ~ and matches enclosing class
    def is_destructor(self) -> bool:
        return (
            self.enclosing_class is not None
            and self.name.startswith("~")
            and self.name[1:] == self.enclosing_class
        )


## @brief Comment style used to recognise a doxygen block for a language.
#  @version 2.0
#  @req REQ-DDB-GUARD-013
@dataclass
class ParseSettings:
    comment_start: str = r"/\*\*(?!\*)"
    comment_end: str = r"\*/"


# Doxygen writes a literal "@" as "\@" or "@@" (see doxygen manual, Special Commands).
# Without escape support there is no way to mention a tag name in prose: the text is
# parsed as a real tag. Escaped occurrences are masked to a sentinel before tag
# detection and restored to a single "@" in the finalised values.
_ESCAPED_AT_SENTINEL = "\x00"
_ESCAPED_AT_RE = re.compile(r"\\@|@@")


## @brief Mask escaped at-signs so they are not detected as tags.
#  @version 1.0
#  @dg_internal
#  @return The line with every escaped at-sign replaced by a sentinel
def _mask_escaped_at(line: str) -> str:
    return _ESCAPED_AT_RE.sub(_ESCAPED_AT_SENTINEL, line)


## @brief Restore masked at-signs to a single literal at-sign.
#  @version 1.0
#  @dg_internal
#  @return The text with sentinels replaced by "@"
def _unmask_escaped_at(text: str) -> str:
    return text.replace(_ESCAPED_AT_SENTINEL, "@")


## @brief Store the current tag's value and reset state.
#  @version 1.2
#  @dg_internal
def _finalize_tag(
    tags: dict[str, list[str]],
    tag: str | None,
    value: list[str],
) -> None:
    if tag is not None:
        tags.setdefault(tag, []).append(_unmask_escaped_at(" ".join(value).strip()))


_TAG_RE = re.compile(r"@(\w+)(?:\s+(.*))?$")


## @brief Parse all doxygen tag entries from comment text.
#  @version 1.10
#  @req REQ-DDB-GUARD-019
#  @return Dict mapping tag names to lists of their values
def parse_doxygen_tags(block_text: str) -> dict[str, list[str]]:
    tags: dict[str, list[str]] = {}
    current_tag: str | None = None
    current_value: list[str] = []
    # `!?` takes the bang of a Rust inner doc comment (`//!`), so `//! @file` parses.
    prefix_re = re.compile(r"^\s*[/*#]+!?\s?")
    suffix_re = re.compile(r"\s*\*/\s*$")

    for raw_line in block_text.splitlines():
        line = prefix_re.sub("", raw_line)
        line = _mask_escaped_at(suffix_re.sub("", line).strip())
        for segment in _split_inline_tags(line):
            match = _TAG_RE.match(segment)
            if match:
                _finalize_tag(tags, current_tag, current_value)
                current_tag = match.group(1)
                current_value = [match.group(2) or ""]
            elif not segment and current_tag is not None:
                _finalize_tag(tags, current_tag, current_value)
                current_tag = None
                current_value = []
            elif current_tag is not None and segment:
                current_value.append(segment)

    _finalize_tag(tags, current_tag, current_value)
    return tags


# A markdown heading (`# Examples`) or a tag line ends rustdoc's summary paragraph.
_AUTOBRIEF_STOP_RE = re.compile(r"^(?:#|@\w)")


## @brief Supply \@brief from a rustdoc block's summary paragraph when none is written.
#  @details rustdoc's convention is that the first paragraph IS the summary, and doxygen
#  implements the same rule as JAVADOC_AUTOBRIEF. So a Rust item documented idiomatically —
#  `/// Adds one.` then tags — satisfies the \@brief requirement without restating it. An
#  explicit \@brief always wins. Applied to Rust doc comments, JSDoc blocks and Python
#  docstrings (PEP 257's summary line); for C/C++ blocks and Python `##` blocks the gate
#  still requires the tag to be written.
#  @version 1.1
#  @req REQ-DDB-GUARD-024
def apply_autobrief(block_text: str, tags: dict[str, list[str]]) -> None:
    if "brief" in tags:
        return
    prefix_re = re.compile(r"^\s*(?:/\*\*|\*/|[/*]+!?)\s?")
    summary: list[str] = []
    for raw_line in block_text.splitlines():
        line = _mask_escaped_at(prefix_re.sub("", raw_line).removesuffix("*/").strip())
        if not line:
            if summary:
                break
            continue
        if _AUTOBRIEF_STOP_RE.match(line):
            break
        # A one-line block (`/** Adds one. @version 1 */`) ends its summary at the tag.
        segments = _split_inline_tags(line)
        summary.append(segments[0])
        if len(segments) > 1:
            break
    if summary:
        tags["brief"] = [_unmask_escaped_at(" ".join(summary))]


_INLINE_SPLIT_RE = re.compile(r"(?=\s@\w+(?:\s|$))")


## @brief Split a line into segments at inline tag boundaries.
#  @version 1.0
#  @dg_internal
def _split_inline_tags(line: str) -> list[str]:
    parts = _INLINE_SPLIT_RE.split(line)
    return [p.strip() for p in parts if p.strip()] if len(parts) > 1 else [line]


## @brief Parse source code to find functions and their associated doxygen comments.
#  @version 2.0
#  @req REQ-DDB-GUARD-018
#  @return Functions detected in the content, each with any associated doxygen block
def parse_functions(
    content: str,
    exclude_names: list[str],
    settings: ParseSettings | None = None,
    *,
    lang_name: str,
) -> list[Function]:
    from .ts_parser import parse_functions_ts

    s = settings or ParseSettings()
    return parse_functions_ts(
        content,
        lang_name,
        exclude_names=exclude_names,
        comment_start_pattern=s.comment_start,
    )
