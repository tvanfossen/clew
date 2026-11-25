# SPDX-License-Identifier: MIT
"""Validation checks for doxygen comments.

@brief Presence, version staleness, and tag validation checks.
@version 1.0
"""

from __future__ import annotations

import logging
import difflib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .doxygen_commands import DOXYGEN_COMMANDS
from .config import DEFAULT_EVENT_TAG_NAMES, get_requirements, get_validate

if TYPE_CHECKING:
    from collections.abc import Set as AbstractSet

    from .parser import Function

logger = logging.getLogger(__name__)


_JS_SUFFIXES = (".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx")


## @brief Build a language-appropriate doxygen skeleton suggestion.
#  @version 1.2
#  @utility
#  @return Single-line skeleton string in the file's native comment style
def _suggest_skeleton(file_path: str, *, with_return: bool = False) -> str:
    return_tag = " @return <description>" if with_return else ""
    if Path(file_path).suffix.lower() == ".rs":
        return f"'/// <summary sentence>' then '/// @version 1{return_tag}' (above the fn)"
    if Path(file_path).suffix.lower() in _JS_SUFFIXES:
        return f"'/** <summary sentence> @version 1{return_tag} */' (JSDoc, above the function)"
    if Path(file_path).suffix.lower() == ".py":
        return f"'## @brief <description> @version 1.0{return_tag}' (two-hash style, above the def)"
    return f"'/** @brief <description> @version 1.0{return_tag} */' before function"


## @brief Build a language-appropriate file-level doxygen skeleton suggestion.
#  @version 1.2
#  @utility
def _suggest_file_skeleton(file_path: str) -> str:
    if Path(file_path).suffix.lower() in _JS_SUFFIXES:
        return (
            "'/** @fileoverview <desc> @brief <desc> @version 1.0 */' "
            "(JSDoc; @file, @overview and @module are accepted too)"
        )
    if Path(file_path).suffix.lower() == ".rs":
        return "'//! <summary sentence>' / '//! @version 1' (inner doc, before first item)"
    if Path(file_path).suffix.lower() == ".py":
        return (
            "'## @file' / '## @brief <desc>' / '## @version 1.0' "
            "(two-hash style, before first code)"
        )
    return "/** @file @brief <desc> @version 1.0 */ before first code"


## @brief How to supply a missing brief, in the file's own convention.
#  @version 1.1
#  @utility
#  @return The remedy text for a missing-@brief violation
def _brief_hint(file_path: str) -> str:
    if Path(file_path).suffix.lower() in (".rs", ".py", *_JS_SUFFIXES):
        return "start the doc comment with a summary sentence, or add '@brief <description>'"
    return "add '@brief <description>' to the doxygen comment"


## @brief Represents a check failure with location and description.
#  v1.1: `qualified` names the function (class, name, parameters) so a machine format's
#  fingerprint survives a line move (2.0.0, S1). Empty for a file- or catalog-level violation.
#  @version 1.1
#  @utility
@dataclass
class Violation:
    file: str
    line: int  # 1-indexed for display
    check: str  # "presence" | "version" | "tag" | "coverage" | "bus"
    message: str
    qualified: str = ""

    ## @brief Human-readable violation string.
    #  @version 1.0
    #  @utility
    def __str__(self) -> str:
        return f"{self.file}:{self.line}: [{self.check}] {self.message}"


## @brief Verify every function has a doxygen comment with \@brief and the revision tag.
#  v1.6: Violation names the function (qualified) for machine-format fingerprints (2.0.0, S1)
#  @version 1.6
#  @req REQ-DDB-GUARD-001
def check_presence(
    functions: list[Function],
    file_path: str,
    config: dict[str, Any],
    content: str | None = None,
) -> list[Violation]:
    validate = get_validate(config)
    presence_config = validate.get("presence", {})

    if not presence_config.get("require_doxygen", True):
        return []

    version_config = validate.get("version", {})
    require_version = version_config.get("require_present", True)
    version_key = version_config.get("tag", "@version").lstrip("@")

    source_lines = content.splitlines() if content is not None else None
    violations: list[Violation] = []

    for func in functions:
        if func.doxygen is None:
            needs_return = bool(
                source_lines is not None and not _is_void_function(func, source_lines)
            )
            violations.append(
                Violation(
                    file=file_path,
                    line=func.def_line + 1,
                    check="presence",
                    qualified=func.qualified,
                    message=(
                        f"Function '{func.name}' has no doxygen comment"
                        f" — add {_suggest_skeleton(file_path, with_return=needs_return)}"
                    ),
                )
            )
            continue

        if "brief" not in func.doxygen.tags:
            violations.append(
                Violation(
                    file=file_path,
                    line=func.doxygen.start_line + 1,
                    check="presence",
                    qualified=func.qualified,
                    message=(
                        f"Function '{func.name}' doxygen missing @brief tag"
                        f" — {_brief_hint(file_path)}"
                    ),
                )
            )

        # Honour the configured tag. This was hardcoded to "version", so setting
        # validate.version.tag produced a presence violation demanding @version plus an
        # unknown-tag violation for the configured name — the documented escape hatch
        # for projects that use doxygen's \version idiomatically did not work.
        if require_version and version_key not in func.doxygen.tags:
            violations.append(
                Violation(
                    file=file_path,
                    line=func.doxygen.start_line + 1,
                    check="presence",
                    qualified=func.qualified,
                    message=(
                        f"Function '{func.name}' doxygen missing @{version_key} tag"
                        f" — add '@{version_key} 1.0' to the doxygen comment"
                    ),
                )
            )

    return violations


_VOID_PATTERNS = re.compile(r"\bvoid\b")
_PYTHON_NONE_RETURN = re.compile(r"->\s*None\b")


## @brief Verify non-void functions have \@return or \@returns tag.
#  v1.4: Violation names the function (qualified) for machine-format fingerprints (2.0.0, S1)
#  @version 1.4
#  @req REQ-DDB-GUARD-005
#  @return List of violations for missing \@return tags
def check_return_presence(
    functions: list[Function],
    file_path: str,
    config: dict[str, Any],
    content: str,
) -> list[Violation]:
    validate = get_validate(config)
    if not _require_return(validate, file_path):
        return []

    lines = content.splitlines()
    violations: list[Violation] = []
    for func in functions:
        if func.doxygen is None:
            continue
        if func.is_constructor() or func.is_destructor():
            continue
        tags = func.doxygen.tags
        if EXEMPTION_TAGS & set(tags.keys()):
            continue
        if tags.get("return") or tags.get("returns"):
            continue
        if _is_void_function(func, lines):
            continue
        violations.append(
            Violation(
                file=file_path,
                line=func.doxygen.start_line + 1,
                check="presence",
                qualified=func.qualified,
                message=(
                    f"Function '{func.name}' doxygen missing @return tag"
                    " — add '@return <description>' to the doxygen comment"
                ),
            )
        )
    return violations


## @brief Whether \@return is required for this file: the language's own setting, else the global one.
#  @details A language entry may carry `require_return`. Rust's defaults set it false:
#  rustdoc has no return tag and documents the result in prose, so demanding one would
#  make every idiomatic Rust block a violation.
#  @version 1.0
#  @req REQ-DDB-GUARD-005
#  @return True when non-void functions in this file must carry \@return
def _require_return(validate: dict[str, Any], file_path: str) -> bool:
    ext = Path(file_path).suffix
    for lang_config in validate.get("languages", {}).values():
        if isinstance(lang_config, dict) and ext in lang_config.get("extensions", []):
            if "require_return" in lang_config:
                return bool(lang_config["require_return"])
            break
    return bool(validate.get("presence", {}).get("require_return", True))


# A Rust signature returns `()` when it has no `->`, or an explicit `-> ()`.
_RUST_FN_RE = re.compile(r"\bfn\s+\w+")
_RUST_UNIT_RETURN = re.compile(r"->\s*\(\s*\)\s*(?:where\b|\{|;|$)")


## @brief Whether a Rust function returns unit, read from its signature text.
#  @version 1.0
#  @req REQ-DDB-GUARD-005
#  @return True when the signature has no `->` or returns `()`
def _is_rust_unit_fn(func: Function, lines: list[str]) -> bool:
    signature: list[str] = []
    for idx in range(func.def_line, min(func.def_line + 12, len(lines))):
        signature.append(lines[idx])
        if "{" in lines[idx] or lines[idx].rstrip().endswith(";"):
            break
    text = " ".join(signature).split("{", 1)[0]
    return "->" not in text or bool(_RUST_UNIT_RETURN.search(text + "{"))


## @brief Check if a function returns void based on its definition lines.
#  @details A parser that knows (JS/TS) sets Function.returns_void, which wins.
#  v1.5 (2.0.0, found by entropic): the C prefix is everything from the function's first line up
#  to its name, so a return type on its own line (`EXPORT void` / `name(...)`, GNU style) is read.
#  A name in column 0 used to be skipped, so that `void` was never seen.
#  @version 1.5
#  @req REQ-DDB-GUARD-005
#  @return True if the function returns void/None
def _is_void_function(func: Function, lines: list[str]) -> bool:
    if func.returns_void is not None:
        return func.returns_void
    if func.def_line < len(lines) and _RUST_FN_RE.search(lines[func.def_line]):
        return _is_rust_unit_fn(func, lines)
    for offset in range(3):
        idx = func.def_line + offset
        if idx >= len(lines):
            break
        line = lines[idx]
        name_pos = line.find(func.name)
        if name_pos < 0 or (name_pos == 0 and offset == 0):
            continue
        prefix = " ".join([*lines[func.def_line : idx], line[:name_pos]])
        is_c_void = bool(_VOID_PATTERNS.search(prefix))
        is_python_none = bool(_PYTHON_NONE_RETURN.search(line))
        is_python_untyped = line.strip().startswith("def ") and "->" not in line
        return is_c_void or is_python_none or is_python_untyped
    return False


# Tags that exempt a function from requiring @req. These are tool vocabulary, not
# doxygen commands.
#
# "internal" was previously in this set, overloading doxygen's \internal — which, with
# INTERNAL_DOCS off, suppresses everything after it in the block. Since this tool kept
# parsing tags after it, a block written to satisfy the gate silently lost its @return
# in generated documentation. Exemption now uses a tool-owned tag that doxygen has no
# meaning for; \internal remains recognised (see _KNOWN_TAGS) so a project using it for
# its real purpose is not flagged, it simply no longer grants an exemption.
#
# 2.0.0 (PG1, OWNER: "a hard cut of doxygen-guard priors — clew only"): the doxygen-guard-era
# `dg_internal` FOLDS INTO `utility`. Never back into `internal`, for the reason above.
EXEMPTION_TAGS: frozenset[str] = frozenset({"utility", "callback"})

# Tags removed in 2.0.0, each refused with its replacement. A REFUSAL, not an unknown-tag
# warning: `known_tags_warn: false` silences those, and a hard cut a key can soften is not one —
# a silenced `@utility` would also stop exempting, failing `@req` coverage with no reason given.
REMOVED_TAGS: dict[str, str] = {"dg_internal": "utility"}

# Tags this tool invents. Doxygen does not define them, so it emits unknown-command
# warnings unless they are declared as ALIASES — which is what `doxygen-guard doxyfile`
# generates. Anything not in here is a real doxygen command and needs no alias.
TOOL_OWNED_TAGS: frozenset[str] = EXEMPTION_TAGS | frozenset({"req"})


## @brief Render the exemption tags for an error message, derived from the set.
#  @version 1.0
#  @utility
#  @return Comma-separated @-prefixed tag names in a stable order
def _exemption_hint() -> str:
    return ", ".join(f"@{t}" for t in sorted(EXEMPTION_TAGS))


## @brief Check if version gate is configured.
#  v1.3: reads the top-level requirements: section (2.0.0, R5-CFG F7)
#  @version 1.3
#  @utility
def _has_version_gate(config: dict[str, Any]) -> bool:
    return bool(
        get_validate(config).get("current_version")
        and get_requirements(config).get("version_field")
    )


## @brief Check if any requirements pass the version gate filter.
#  @version 1.1
#  @utility
def _has_active_requirements(config: dict[str, Any]) -> bool:
    from .impact import filter_requirements_by_version, load_requirements_full

    full = load_requirements_full(config)
    filtered = filter_requirements_by_version(full, config)
    return bool(filtered)


## @brief Verify functions have requirement or exemption tags when requirements are configured.
#  v1.7: reads the top-level requirements: section (2.0.0, R5-CFG F7)
#  v1.8: Violation names the function (qualified) for machine-format fingerprints (2.0.0, S1)
#  v1.9: a declaration's requirement obligation is its definition's (2.0.0, PG2)
#  @version 1.9
#  @req REQ-DDB-GUARD-004
def check_req_coverage(
    functions: list[Function],
    file_path: str,
    config: dict[str, Any],
) -> list[Violation]:
    req_config = get_requirements(config)
    if not req_config or not req_config.get("file"):
        return []

    # If version gate is configured, check if any active requirements exist
    if _has_version_gate(config) and not _has_active_requirements(config):
        return []

    req_file = req_config["file"]
    violations: list[Violation] = []
    for func in functions:
        if func.doxygen is None:
            continue
        ## A DECLARATION'S OBLIGATION IS ITS DEFINITION'S (2.0.0, PG2): one function, so a header
        ## does not need its @req written twice; its block's own tags are still checked.
        if func.is_constructor() or func.is_destructor() or func.is_declaration:
            continue

        tags = func.doxygen.tags
        has_req = bool(tags.get("req"))
        has_exemption = bool(EXEMPTION_TAGS & set(tags.keys()))

        if not has_req and not has_exemption:
            violations.append(
                Violation(
                    file=file_path,
                    line=func.def_line + 1,
                    check="coverage",
                    qualified=func.qualified,
                    message=(
                        f"Function '{func.name}' has no @req tag "
                        f"(see {req_file}) and no exemption "
                        f"({_exemption_hint()})"
                    ),
                )
            )

    return violations


## @brief Build a lookup of HEAD functions keyed by (enclosing_class, name, signature).
#  @details The parameter signature disambiguates overloads and same-named constructors
#  sharing a class — without it, every "react(Event)" overload in a tinyfsm-style
#  dispatch class collided on the same key, so all but the last-parsed overload matched
#  the wrong sibling's HEAD body and was flagged stale on an untouched tree (#11). A
#  function whose signature itself changed finds no match HERE; since 2.0.0 `_pair_by_name`
#  then pairs it by name when it is not overloaded, so a changed parameter list needs a bump.
#  Version 3.1: that comment; the old one said such a function was simply treated as new.
#
#  Version 3.0 (gh#63): a LIST per key, in file order. One file can define the same function
#  twice under exclusive `#ifdef`/`#else` branches; a dict kept only the last copy, so every
#  earlier copy was compared with it — a false "body changed" on a byte-identical file, and a
#  missed unbumped edit when the copies carried different versions.
#  @version 3.1
#  @utility
#  @return Mapping from (enclosing_class, name, signature) to that identity's Functions, in order
def _index_by_identity(
    functions: list[Function],
) -> dict[tuple[str | None, str, str], list[Function]]:
    index: dict[tuple[str | None, str, str], list[Function]] = {}
    for f in functions:
        index.setdefault((f.enclosing_class, f.name, f.signature), []).append(f)
    return index


## @brief Pair a function left unmatched by identity with its HEAD self, by name, if unambiguous.
#  @details A CHANGED SIGNATURE IS A CHANGE (2.0.0, owner Q/A 2026-11-20). Matching by (class,
#  name, signature) alone made a function whose parameters changed look new, so it needed no bump:
#  `def f(x)` → `def f(x, y=0)` with a changed body passed. The fallback pairs it only when exactly
#  ONE copy of (class, name) exists on each side and the HEAD copy is not already paired — an
#  overload set keeps the exact match, so #11 (a sibling paired with the wrong HEAD body) cannot
#  return.
#  @version 1.0
#  @req REQ-DDB-GUARD-002
#  @return Mapping from id(current Function) to its HEAD Function, for the pairs this adds
def _pair_by_name(
    functions: list[Function], head_functions: list[Function], paired: dict[int, Function]
) -> dict[int, Function]:
    taken = {id(h) for h in paired.values()}
    head_by_name: dict[tuple[str | None, str], list[Function]] = {}
    for h in head_functions:
        head_by_name.setdefault((h.enclosing_class, h.name), []).append(h)
    current_by_name: dict[tuple[str | None, str], list[Function]] = {}
    for f in functions:
        current_by_name.setdefault((f.enclosing_class, f.name), []).append(f)
    added: dict[int, Function] = {}
    for key, (func,) in ((k, v) for k, v in current_by_name.items() if len(v) == 1):
        head = head_by_name.get(key, [])
        if id(func) not in paired and len(head) == 1 and id(head[0]) not in taken:
            added[id(func)] = head[0]
    return added


## @brief Pair one identity's current copies with its HEAD copies.
#  @details Copies are paired BY OCCURRENCE when both sides hold the same number — `#ifdef`
#  branches are rarely reordered. When a copy was added or removed, identical bodies pair first,
#  then the remaining copies by body similarity; a current copy left with no HEAD copy is new.
#  @version 1.0
#  @utility
#  @return Mapping from id(current Function) to its HEAD Function, absent when it is new
def _pair_copies(
    current: list[Function], head: list[Function], ctx: VersionCheckContext
) -> dict[int, Function]:
    if len(current) == len(head):
        return {id(c): h for c, h in zip(current, head)}
    pairs: dict[int, Function] = {}
    free = list(head)
    for func in current:
        text = _body_text(func, ctx.lines)
        same = next((h for h in free if _body_text(h, ctx.head_lines) == text), None)
        if same is not None:
            pairs[id(func)] = same
            free.remove(same)
    for func in (c for c in current if id(c) not in pairs):
        if not free:
            break
        best = max(free, key=lambda h, f=func: _similarity(f, h, ctx))
        pairs[id(func)] = best
        free.remove(best)
    return pairs


## @brief Body-text similarity of a current copy to a HEAD copy.
#  @version 1.0
#  @utility
#  @return Ratio in [0, 1]
def _similarity(func: Function, head: Function, ctx: VersionCheckContext) -> float:
    return difflib.SequenceMatcher(
        None, _body_text(func, ctx.lines), _body_text(head, ctx.head_lines)
    ).ratio()


## @brief Extract a function's definition-through-body source text.
#  @version 1.0
#  @utility
#  @return Joined source lines from def_line through body_end, or "" if out of range
def _body_text(func: Function, lines: list[str]) -> str:
    return "\n".join(lines[func.def_line : func.body_end + 1])


## @brief Fixed inputs for comparing one file's functions against its HEAD revision.
#  @version 1.0
#  @utility
@dataclass
class VersionCheckContext:
    file_path: str
    tag_key: str
    version_tag: str
    lines: list[str]
    head_lines: list[str]


## @brief Check one function's \@version against its HEAD counterpart.
#  @details Returns None when the function has no version tag, is new (absent from
#  HEAD), its body is unchanged since HEAD, or its version was validly bumped.
#  v1.1: Violation names the function (qualified) for machine-format fingerprints (2.0.0, S1)
#  @version 1.1
#  @utility
#  @return A single Violation, or None if this function is not stale
def _check_one_version(
    func: Function,
    head_func: Function | None,
    ctx: VersionCheckContext,
) -> Violation | None:
    # Written as a single direct condition (not hoisted to a variable) so type checkers
    # can narrow func.doxygen / head_func.doxygen to non-None for the rest of the function.
    if (
        func.doxygen is None
        or ctx.tag_key not in func.doxygen.tags
        or head_func is None
        or head_func.doxygen is None
        or _body_text(func, ctx.lines) == _body_text(head_func, ctx.head_lines)
    ):
        return None

    version_value = func.doxygen.tags.get(ctx.tag_key, [""])[0]
    head_version_value = head_func.doxygen.tags.get(ctx.tag_key, [""])[0]

    if version_value == head_version_value:
        return Violation(
            file=ctx.file_path,
            line=func.def_line + 1,
            check="version",
            qualified=func.qualified,
            message=f"Function '{func.name}' body changed but {ctx.version_tag} was not updated",
        )

    # Version was bumped — validate the optional marker (only [reviewed] is valid).
    marker_match = re.search(r"\[(\w+)\]$", version_value.strip())
    invalid_marker = bool(marker_match) and marker_match.group(1) != "reviewed"
    return (
        Violation(
            file=ctx.file_path,
            line=func.def_line + 1,
            check="version",
            qualified=func.qualified,
            message=(
                f"Function '{func.name}' has unrecognized version marker "
                f"'[{marker_match.group(1)}]' (use [reviewed])"
            ),
        )
        if invalid_marker and marker_match
        else None
    )


## @brief Detect stale \@version tags when function bodies have changed since HEAD.
#  @details Compares each function's def-through-body text against its HEAD counterpart
#  (matched by (enclosing_class, name, signature)) rather than testing whether git's diff
#  happened to pair the \@version line as changed. Positional line matching is unreliable
#  when a version value is textually common (e.g. "1.0") — the differ can pair it as
#  unchanged context even for a brand-new function, producing false positives, and can
#  leave a genuinely changed body's version line out of a hunk, producing false negatives.
#
#  Version 2.2 (gh#63): a same-identity duplicate (`#ifdef`/`#else` copies) is paired with its
#  own HEAD copy via `_pair_copies`, not with whichever copy was parsed last.
#  Version 2.3 (2.0.0, owner 2026-11-20): a function whose SIGNATURE changed is paired by name
#  (`_pair_by_name`) when it is not overloaded, so a changed parameter list needs a bump.
#  @version 2.3
#  @req REQ-DDB-GUARD-002
#  @return Violations for functions whose body changed since HEAD without a version bump
def check_version_staleness(
    functions: list[Function],
    file_path: str,
    config: dict[str, Any],
    content: str,
    head_functions: list[Function] | None,
    head_content: str | None,
) -> list[Violation]:
    validate = get_validate(config)
    version_config = validate.get("version", {})

    if not version_config.get("require_increment_on_change", True):
        return []

    if head_functions is None or head_content is None:
        # No HEAD to compare against (new file, or git unavailable) — nothing is stale.
        return []

    version_tag = version_config.get("tag", "@version")
    ctx = VersionCheckContext(
        file_path=file_path,
        tag_key=version_tag.lstrip("@"),
        version_tag=version_tag,
        lines=content.splitlines(),
        head_lines=head_content.splitlines(),
    )
    head_index = _index_by_identity(head_functions)
    current_index = _index_by_identity(functions)

    paired: dict[int, Function] = {}
    for key, copies in current_index.items():
        paired.update(_pair_copies(copies, head_index.get(key, []), ctx))
    paired.update(_pair_by_name(functions, head_functions, paired))

    violations: list[Violation] = []
    for func in functions:
        violation = _check_one_version(func, paired.get(id(func)), ctx)
        if violation is not None:
            violations.append(violation)

    return violations


## @brief Check that doxygen tags match configured patterns, prefixes, and markers.
#  @version 1.1
#  @req REQ-DDB-GUARD-003
def check_tags(
    functions: list[Function],
    file_path: str,
    config: dict[str, Any],
) -> list[Violation]:
    validate = get_validate(config)
    tag_rules = validate.get("tags", {})

    if not tag_rules:
        return []

    violations: list[Violation] = []

    for func in functions:
        if func.doxygen is None:
            continue

        for tag_name, rules in tag_rules.items():
            tag_values = func.doxygen.tags.get(tag_name, [])

            for value in tag_values:
                violations.extend(_validate_tag_value(file_path, func, tag_name, value, rules))

    return violations


## @brief Check one tag value against pattern, prefix, and contains rules.
#  v1.2: Violation names the function (qualified) for machine-format fingerprints (2.0.0, S1)
#  @version 1.2
#  @utility
def _validate_tag_value(
    file_path: str,
    func: Function,
    tag_name: str,
    value: str,
    rules: dict[str, Any],
) -> list[Violation]:
    violations: list[Violation] = []
    line = func.doxygen.start_line + 1 if func.doxygen else func.def_line + 1

    # Check pattern match
    pattern = rules.get("pattern")
    if pattern and not re.match(pattern, value):
        violations.append(
            Violation(
                file=file_path,
                line=line,
                check="tag",
                qualified=func.qualified,
                message=(
                    f"Function '{func.name}' @{tag_name} value '{value}' "
                    f"does not match pattern '{pattern}'"
                ),
            )
        )

    # Check required prefix
    require_prefix = rules.get("require_prefix")
    if require_prefix and not any(value.startswith(p) for p in require_prefix):
        violations.append(
            Violation(
                file=file_path,
                line=line,
                check="tag",
                qualified=func.qualified,
                message=(
                    f"Function '{func.name}' @{tag_name} value '{value}' "
                    f"does not start with any required prefix: {require_prefix}"
                ),
            )
        )

    # Check required contains
    require_contains = rules.get("require_contains")
    if require_contains and require_contains not in value:
        violations.append(
            Violation(
                file=file_path,
                line=line,
                check="tag",
                qualified=func.qualified,
                message=(
                    f"Function '{func.name}' @{tag_name} value '{value}' "
                    f"does not contain '{require_contains}'"
                ),
            )
        )

    return violations


# Vocabulary this tool acts on, plus standard doxygen commands. The diagram-generation
# tags (sends, receives, calls, dispatch_key, send_source, receive_source, participant,
# loop, group, after) were removed with the tracer: a tag the tool cannot act on is an
# unknown tag. Repos still carrying them should list them under validate.extra_tags.
_KNOWN_TAGS: frozenset[str] = EXEMPTION_TAGS | frozenset(
    {
        # Enforced by this tool
        "brief",
        "version",
        "req",
        # 2.2: names a declared failure mode (`check_fails_when_exists`)
        "fails_when",
        # Recognised but no longer an exemption — see EXEMPTION_TAGS
        "internal",
        "return",
        "returns",
        "file",
        # Standard doxygen commands, recognized but not enforced
        "note",
        "param",
        "details",
        "see",
        "todo",
        "deprecated",
        "warning",
        "par",
        "throw",
        "throws",
        "exception",
        "pre",
        "post",
        "invariant",
        "since",
        "author",
        "date",
        "copyright",
    }
)


## @brief Check for unknown tags with Levenshtein-based suggestions.
#  @details v1.1: a configured bus tag (`validate.bus.tags`) is a known tag.
#  v1.2 (2.0.0, R5-CFG F10/F11): the declaration's event vocabulary (or the index's built-in one)
#  is known, and `@node` is known when `wiki.sources` is declared.
#  v1.3: Violation names the function (qualified) for machine-format fingerprints (2.0.0, S1)
#  v1.4: a removed tag (REMOVED_TAGS) is left to check_removed_tags (2.0.0, PG1)
#  v1.5: doxygen's built-in commands are known (2.0.0, PG7, a consumer finding)
#  @version 1.5
#  @req REQ-DDB-GUARD-001
def check_unknown_tags(
    func: Function,
    file_path: str,
    config: dict[str, Any],
) -> list[Violation]:
    if func.doxygen is None:
        return []

    validate_config = get_validate(config)
    if not validate_config.get("known_tags_warn", True):
        return []

    extra = set(validate_config.get("extra_tags", []))
    known = (
        _KNOWN_TAGS
        | extra
        | set(validate_config.get("tags", {}).keys())
        | _event_tags(config)
        | ({"node"} if config.get("wiki_sources") else set())
    )

    violations: list[Violation] = []
    for tag_name in func.doxygen.tags:
        ## A removed tag is `check_removed_tags`' to refuse, once, with its replacement. A doxygen
        ## command is known (PG7) but never a SUGGESTION: "did you mean @tparam?" helps nobody.
        if (
            tag_name not in known
            and tag_name not in REMOVED_TAGS
            and tag_name not in DOXYGEN_COMMANDS
        ):
            suggestion = _suggest_tag(tag_name, known)
            hint = f" — did you mean @{suggestion}?" if suggestion else ""
            violations.append(
                Violation(
                    file=file_path,
                    line=func.doxygen.start_line + 1,
                    check="tag",
                    qualified=func.qualified,
                    message=f"Unknown tag @{tag_name} in {func.name}(){hint}",
                )
            )
    return violations


## @brief Refuse a tag removed in 2.0.0, naming its replacement.
#  @details Always on: see REMOVED_TAGS for why no key turns it off.
#  @version 1.0
#  @req REQ-DDB-GUARD-001
#  @return One violation per removed tag in the block
def check_removed_tags(func: Function, file_path: str, config: dict[str, Any]) -> list[Violation]:
    if func.doxygen is None:
        return []
    return [
        Violation(
            file=file_path,
            line=func.doxygen.start_line + 1,
            check="tag",
            qualified=func.qualified,
            message=(
                f"@{tag} in {func.name}() was removed in clew 2.0.0 — use @{REMOVED_TAGS[tag]} "
                "(the doxygen-guard tag is not read)"
            ),
        )
        for tag in func.doxygen.tags
        if tag in REMOVED_TAGS
    ]


## @brief When `validate.exemption_reason` is `required`, refuse an exemption tag with no reason.
#  @details The standards' form (DO-178C, ISO 26262, IEC 62304): code that does not trace to a
#  requirement is acceptable when the exception is justified, so `@utility parses X for Y`, not a
#  bare `@utility`. Off by default; see EXEMPTION_REASON_SETTINGS. 2.0.0, PG3b.
#  @version 1.0
#  @req REQ-DDB-GUARD-001
#  @return One violation per bare exemption tag
def check_exemption_reasons(
    func: Function, file_path: str, config: dict[str, Any]
) -> list[Violation]:
    if func.doxygen is None or get_validate(config).get("exemption_reason") != "required":
        return []
    return [
        Violation(
            file=file_path,
            line=func.doxygen.start_line + 1,
            check="tag",
            qualified=func.qualified,
            message=(
                f"@{tag} in {func.name}() needs a one-line reason "
                f"(validate.exemption_reason is required): `@{tag} <why this has no requirement>`"
            ),
        )
        for tag in sorted(EXEMPTION_TAGS & set(func.doxygen.tags))
        if not any(v.strip() for v in func.doxygen.tags[tag])
    ]


# Tags that describe the function as a whole. A second occurrence is not additive:
# downstream readers take tags[name][0], so a duplicate is silently ignored and can
# carry a different value than the author intended.
#
# "version" is deliberately absent. Doxygen permits multiple \version entries, which
# accumulate into one paragraph — flagging them rejected legal doxygen. That was a
# regression introduced with this check in 1.3.0.
_SINGLE_VALUED_TAGS: frozenset[str] = frozenset({"brief", "return", "returns", "file"})


## @brief Flag single-valued doxygen tags that appear more than once in one block.
#  v1.1: Violation names the function (qualified) for machine-format fingerprints (2.0.0, S1)
#  @version 1.1
#  @req REQ-DDB-GUARD-007
#  @return Violations for each duplicated single-valued tag
def check_duplicate_tags(
    func: Function,
    file_path: str,
    config: dict[str, Any],
) -> list[Violation]:
    if func.doxygen is None:
        return []
    if not get_validate(config).get("duplicate_tags_error", True):
        return []

    violations: list[Violation] = []
    for tag_name, values in func.doxygen.tags.items():
        if tag_name in _SINGLE_VALUED_TAGS and len(values) > 1:
            logger.warning(
                "Duplicate @%s in %s() at %s:%d — values: %r",
                tag_name,
                func.name,
                file_path,
                func.doxygen.start_line + 1,
                values,
            )
            violations.append(
                Violation(
                    file=file_path,
                    line=func.doxygen.start_line + 1,
                    check="tag",
                    qualified=func.qualified,
                    message=(
                        f"@{tag_name} appears {len(values)} times in {func.name}() — "
                        f"only the first is used; remove the extras"
                    ),
                )
            )
    return violations


## @brief Find the closest known tag name using edit distance.
#  @version 1.1
#  @utility
def _suggest_tag(unknown: str, known: AbstractSet[str]) -> str | None:
    best_tag = None
    best_dist = 3
    for tag in known:
        dist = _edit_distance(unknown, tag)
        if dist < best_dist:
            best_dist = dist
            best_tag = tag
    return best_tag


## @brief Compute Levenshtein edit distance between two strings.
#  @version 1.0
#  @utility
def _edit_distance(a: str, b: str) -> int:
    if len(a) < len(b):
        return _edit_distance(b, a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1] + [0] * len(b)
        for j, cb in enumerate(b):
            cost = 0 if ca == cb else 1
            curr[j + 1] = min(curr[j] + 1, prev[j + 1] + 1, prev[j] + cost)
        prev = curr
    return prev[len(b)]


## @brief A tag that cannot be checked because no catalogue is declared (GH #68).
#  v1.1: Violation names the function (qualified) for machine-format fingerprints (2.0.0, S1)
#  @version 1.1
#  @req REQ-DDB-GUARD-027
#  @return The violation
def _uncheckable(func: Function, file_path: str, req_id: str) -> Violation:
    return Violation(
        file=file_path,
        line=func.doxygen.start_line + 1,
        check="tag",
        qualified=func.qualified,
        message=(
            f"@req {req_id} in {func.name}() cannot be checked: no requirements catalog is "
            "declared; name one under impact.requirements (file or external), or set "
            "validate.tags.req.cross_reference: false"
        ),
    )


## @brief A catalogue entry's `satisfies` ids that no catalogue holds (GH #68).
#  @details v1.1 (2.1, #72 item 13): `serves` is read as the same link (`requirements.link_ids`).
#  v1.2 (2.1, #73 item 3): with a parent catalogue unchecked here, an unresolved link is a warning.
#  @version 1.2
#  @req REQ-DDB-SCHEMA-015
#  @return One violation per unresolvable link, against the catalogue file
def check_satisfies(
    rows: dict[str, dict[str, str]],
    known: set[str],
    catalog_file: str,
    unchecked: list[str] | None = None,
) -> list[Violation]:
    """A link names an id in the local or an external catalogue; `<catalog>:<id>` resolves by
    its id. Anything else is a broken edge in the requirement tree — unless a PARENT catalogue
    could not be read here (`unchecked`), when it may be that parent's: reported unchecked, a
    warning naming the parents, never a violation (#73 item 3)."""
    from ..requirements import link_ids

    out: list[Violation] = []
    for req_id, row in rows.items():
        for target in link_ids(row):
            if target in known or target.split(":", 1)[-1] in known:
                continue
            if unchecked:
                logger.warning(
                    "%s satisfies %s: unchecked — parent catalogue(s) %s not present here",
                    req_id,
                    target,
                    ", ".join(unchecked),
                )
                continue
            out.append(
                Violation(
                    file=catalog_file,
                    line=1,
                    check="tag",
                    message=(
                        f"{req_id} satisfies {target}, which no requirements catalogue holds "
                        "(local or impact.requirements.external)"
                    ),
                )
            )
    return out


## @brief Cross-validate requirement tag references against the requirements file.
#  @details v1.1: an EMPTY id set (looked, no catalogue) reports each tag as uncheckable;
#  None still means no catalogue information was supplied (GH #68).
#  v1.2: Violation names the function (qualified) for machine-format fingerprints (2.0.0, S1)
#  @version 1.2
#  @req REQ-DDB-GUARD-001
def check_req_exists(
    func: Function,
    file_path: str,
    config: dict[str, Any],
    req_ids: set[str] | None = None,
) -> list[Violation]:
    # ABSENCE IS NOT EMPTINESS: None means the caller supplied no catalogue information (skip);
    # an EMPTY set means the catalogues were looked for and none exists (GH #68).
    if func.doxygen is None or req_ids is None:
        return []

    validate_config = get_validate(config)
    tag_config = validate_config.get("tags", {}).get("req", {})
    if not tag_config.get("cross_reference", True):
        return []

    violations: list[Violation] = []
    for req_id in func.doxygen.tags.get("req", []):
        if not req_ids:
            # GH #68: NO CATALOGUE AT ALL used to pass every tag unchecked. A tag that cannot be
            # checked is now said to be one.
            violations.append(_uncheckable(func, file_path, req_id))
        elif req_id not in req_ids:
            violations.append(
                Violation(
                    file=file_path,
                    line=func.doxygen.start_line + 1,
                    check="tag",
                    qualified=func.qualified,
                    message=(
                        f"@req {req_id} in {func.name}() not found in requirements file"
                        f" — verify the ID or add it to the requirements"
                    ),
                )
            )
    return violations


## @brief Each `@fails_when` id must be a failure mode the catalogue declares.
#  @details 2.2 (owner Q/A 2026-11-25): the ids are defined once, in the catalogue's
#  `failure_modes`, so a test naming an id nothing declares is refused like an unknown `@req`.
#  None skips (no catalogue information supplied); an EMPTY set means the catalogue declares no
#  modes, and every reference is then named, never passed.
#  @version 1.0
#  @req REQ-DDB-GUARD-001
#  @return One violation per undeclared id
def check_fails_when_exists(
    func: Function,
    file_path: str,
    config: dict[str, Any],
    mode_ids: set[str] | None = None,
) -> list[Violation]:
    from ..failuremodes import TAG

    if func.doxygen is None or mode_ids is None:
        return []
    return [
        Violation(
            file=file_path,
            line=func.doxygen.start_line + 1,
            check="tag",
            qualified=func.qualified,
            message=(
                f"@{TAG} {mode} in {func.name}() names no failure mode the requirements catalogue "
                "declares — add it under that requirement's `failure_modes`, or correct the id"
            ),
        )
        for mode in func.doxygen.tags.get(TAG, [])
        if mode not in mode_ids
    ]


## @brief Check for file-level doxygen documentation block.
#  @version 1.4
#  @req REQ-DDB-GUARD-006
#  @return List of violations for missing or incomplete file-level doxygen
def check_file_presence(
    file_path: str,
    content: str,
    config: dict[str, Any],
) -> list[Violation]:
    validate = get_validate(config)
    presence_config = validate.get("presence", {})
    if not presence_config.get("require_file_doxygen", False):
        return []

    lines = content.splitlines()
    rust = Path(file_path).suffix == ".rs"
    block_line = _find_file_doxygen_start(lines, _RUST_FILE_DOC_STARTS if rust else None)
    if block_line is None:
        first_code = _first_code_line(lines)
        return [
            Violation(
                file=file_path,
                line=first_code,
                check="presence",
                message=(
                    f"File '{file_path}' has no file-level doxygen block"
                    f" — add {_suggest_file_skeleton(file_path)}"
                ),
            )
        ]

    return _check_file_block_tags(file_path, lines, block_line)


## @brief Check required tags in a file-level doxygen block.
#  @version 1.4
#  @req REQ-DDB-GUARD-006
#  @return List of violations for missing required tags
def _check_file_block_tags(file_path: str, lines: list[str], block_start: int) -> list[Violation]:
    block_text = _extract_file_block_text(lines, block_start)
    from .parser import parse_doxygen_tags

    tags = parse_doxygen_tags(block_text)
    violations: list[Violation] = []
    required = {"file": "@file", "brief": "@brief", "version": "@version"}
    if Path(file_path).suffix.lower() in _JS_SUFFIXES:
        ## ANY OF JSDOC'S FOUR, not the C spelling. `@file` stays in the mapping so a file
        ## naming none of them still reports a missing tag — widening which tags count must
        ## not make the check vacuous.
        if any(tag in tags for tag in _JSDOC_FILE_TAGS):
            del required["file"]
        else:
            required["file"] = "@fileoverview (or @file / @overview / @module)"
    if lines[block_start].strip().startswith(_RUST_FILE_DOC_STARTS):
        # A Rust inner doc comment documents its module by construction, so @file would
        # restate the syntax; and its summary paragraph is the brief, as for items.
        from .parser import apply_autobrief

        apply_autobrief(block_text, tags)
        del required["file"]
    for tag_key, tag_name in required.items():
        if tag_key not in tags:
            violations.append(
                Violation(
                    file=file_path,
                    line=block_start + 1,
                    check="presence",
                    message=f"File-level doxygen missing {tag_name} tag in '{file_path}'",
                )
            )
    return violations


## @brief Extract file-level doxygen block text from lines.
#  @details v1.2 (2.1, found by an adopter, glyph-animator 2026-11-23): a Python MODULE DOCSTRING
#  is read to its closing quotes. It stopped at the first line not starting with `*`, `#` or `//`,
#  so a docstring whose tags follow a blank line read as missing @file/@brief/@version, against
#  GUARD.md's "PEP 257 leads".
#  @version 1.2
#  @utility
#  @return The raw text of the doxygen block
def _extract_file_block_text(lines: list[str], start: int) -> str:
    if lines[start].strip().startswith(_DOCSTRING_QUOTES):
        return _docstring_block(lines, start)
    block_lines: list[str] = []
    for i in range(start, min(start + 30, len(lines))):
        block_lines.append(lines[i])
        if "*/" in lines[i] or (i > start and not lines[i].strip().startswith(("*", "#", "//"))):
            break
    return "\n".join(block_lines)


## The quotes a Python module docstring opens with, and the most lines one is read across.
_DOCSTRING_QUOTES = ('"""', "'''")
_DOCSTRING_MAX_LINES = 400


## @brief A module docstring's text, from its opening quotes to its closing ones.
#  @version 1.0
#  @utility
#  @return The text, quotes removed
def _docstring_block(lines: list[str], start: int) -> str:
    first = lines[start].strip()
    quote = first[:3]
    opened = first[3:]
    if quote in opened:
        return opened.split(quote, 1)[0]
    body = [opened]
    for line in lines[start + 1 : start + _DOCSTRING_MAX_LINES]:
        if quote in line:
            body.append(line.split(quote, 1)[0])
            break
        body.append(line)
    return "\n".join(body)


# In Rust only an INNER doc comment documents the file (its module): `///` and `/**` at the
# top of a file document the first item, so reading them as the file block reports an
# item's doc as a file block missing @file.
_RUST_FILE_DOC_STARTS = ("//!", "/*!")

# WHAT DOCUMENTS A JAVASCRIPT FILE, matching `clew/filedocs.py`'s `_JSDOC_FILE_TAG` tag for
# tag (group A, 1.1.0 merge review). JSDoc's own documentation leads with `@fileoverview`;
# `@file` is its alias, and `@module` documents a file that is a module. Requiring the literal
# `@file` made a correctly documented JS file a file doc to the INDEX and a violation to the
# GATE, with remedy text naming a tag JSDoc does not have.
#
# Duplicated rather than imported, deliberately and for the reason stated throughout
# `clew.guard`: the gate must not import the pipeline. `tests/guard/test_guard_jsdoc_file_level.py`
# parametrises over all four so the two spellings cannot drift.
_JSDOC_FILE_TAGS = ("file", "fileoverview", "overview", "module")

# A shebang (`#!/usr/bin/env node`) and a `'use strict'` / `"use strict"` prologue legally
# precede the file's doc block, and `_find_file_doxygen_start` stops at the first line that is
# not a doc comment — so a Node executable could not carry a file block at all.
_JS_PROLOGUE_PREFIXES = ("#!", "'use strict'", '"use strict"')


## @brief Find the line index of the file-level doxygen block start.
#  @version 1.5
#  @req REQ-DDB-GUARD-006
#  @return 0-indexed line number, or None if no block found
def _find_file_doxygen_start(
    lines: list[str], doxygen_starts: tuple[str, ...] | None = None
) -> int | None:
    ## `#!` and the `use strict` directives join the C preprocessor lines: all of them
    ## legally sit ABOVE a file's doc block, and stopping at one reports a documented file as
    ## undocumented (group A, 1.1.0 merge review).
    skip_prefixes = ("#include", "#pragma", "#ifndef", "#define") + _JS_PROLOGUE_PREFIXES
    doxygen_starts = doxygen_starts or ("/**", "///", "## @", '"""')
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or any(stripped.startswith(p) for p in skip_prefixes):
            continue
        if any(stripped.startswith(s) for s in doxygen_starts):
            return i
        return None
    return None


## @brief Find the first non-blank, non-preprocessor line number.
#  @version 1.1
#  @utility
#  @return 1-indexed line number for violation reporting
def _first_code_line(lines: list[str]) -> int:
    for i, line in enumerate(lines):
        if line.strip():
            return i + 1
    return 1


## @brief The event vocabulary: the declaration's `event_tags:`, else the index's built-in one.
#  @details ONE VOCABULARY (R5-CFG F10, 2.0.0): the gate used its own `validate.bus.tags`, so a word
#  the index read as an event (`publishes`, or a declared `broadcasts`) was an unknown tag here.
#  @version 1.0
#  @utility
#  @return Tag names
def _event_tags(config: dict[str, Any]) -> set[str]:
    declared = config.get("event_tags")
    return {str(t).lower() for t in declared} if declared else set(DEFAULT_EVENT_TAG_NAMES)


## @brief The bus tags a configuration enforces; empty when no `validate.bus` section exists.
#  @details v1.1 (2.0.0): the tags are the event vocabulary (`_event_tags`); `validate.bus` only
#  switches the rule on and scopes it.
#  @version 1.1
#  @utility
#  @return Tag names
def _bus_tags(config: dict[str, Any]) -> set[str]:
    if not get_validate(config).get("bus"):
        return set()
    return _event_tags(config)


## @brief Verify that functions crossing a bus carry a bus tag naming a known bus.
#  @details 1.4.0 W10 (#67's fifth consumer). SCOPED, NEVER BLANKET: a function is in scope
#  when its name matches a `validate.bus.handlers` glob or its body calls a
#  `validate.bus.senders` name — the caller that chooses the topic is the crossing, not only a
#  named handler. A sender itself is the transport and is out of scope. The existing exemptions
#  (@callback, @utility, @utility) are honoured: a blanket rule pushes repositories to add
#  exemptions, which hides the very gap the rule exists to expose. Every bus tag's first word
#  must be in `validate.bus.vocabulary` when one is given. With no `validate.bus` section the
#  rule checks nothing.
#  v1.1: Violation names the function (qualified) for machine-format fingerprints (2.0.0, S1)
#  @version 1.1
#  @req REQ-DDB-GUARD-026
#  @return Violations
def check_bus_tags(
    functions: list[Function],
    file_path: str,
    config: dict[str, Any],
    lines: list[str],
) -> list[Violation]:
    bus = get_validate(config).get("bus")
    if not bus:
        return []
    tags = _bus_tags(config)
    vocabulary = set(bus.get("vocabulary") or ())
    handlers = tuple(bus.get("handlers") or ())
    senders = tuple(bus.get("senders") or ())
    call = re.compile(r"\b(?:%s)\s*\(" % "|".join(map(re.escape, senders))) if senders else None
    violations: list[Violation] = []
    for func in functions:
        if func.doxygen is None or func.name in senders:
            continue
        present = {t: v for t, v in func.doxygen.tags.items() if t in tags}
        violations.extend(_bus_vocabulary(func, file_path, present, vocabulary))
        if present or EXEMPTION_TAGS & set(func.doxygen.tags):
            continue
        if _crosses_bus(func, lines, handlers, call):
            violations.append(
                Violation(
                    file=file_path,
                    line=func.def_line + 1,
                    check="bus",
                    qualified=func.qualified,
                    message=(
                        f"Function '{func.name}' crosses a bus but carries no bus tag "
                        f"({', '.join(f'@{t}' for t in sorted(tags))}) and no exemption "
                        f"({_exemption_hint()})"
                    ),
                )
            )
    return violations


## @brief Whether a function is in the bus rule's scope.
#  @version 1.0
#  @utility
#  @return True for a handler-glob name or a body calling a sender
def _crosses_bus(
    func: Function, lines: list[str], handlers: tuple[str, ...], call: re.Pattern[str] | None
) -> bool:
    from fnmatch import fnmatchcase

    if any(fnmatchcase(func.name, g) for g in handlers):
        return True
    if call is None:
        return False
    body = "\n".join(lines[func.def_line + 1 : func.body_end + 1])
    return call.search(body) is not None


## @brief Violations for bus tags naming a bus outside the vocabulary.
#  v1.1: Violation names the function (qualified) for machine-format fingerprints (2.0.0, S1)
#  @version 1.1
#  @utility
#  @return Violations
def _bus_vocabulary(
    func: Function, file_path: str, present: dict[str, list[str]], vocabulary: set[str]
) -> list[Violation]:
    if not vocabulary:
        return []
    line = func.doxygen.start_line + 1 if func.doxygen else func.def_line + 1
    return [
        Violation(
            file=file_path,
            line=line,
            check="bus",
            qualified=func.qualified,
            message=(
                f"@{tag} {value!r} in {func.name}() names bus {value.split()[0] if value.split() else ''!r}, "
                f"not in validate.bus.vocabulary ({', '.join(sorted(vocabulary))})"
            ),
        )
        for tag, values in present.items()
        for value in values
        if not value.split() or value.split()[0] not in vocabulary
    ]
