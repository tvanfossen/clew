"""Validation checks for doxygen comments.

@brief Presence, version staleness, and tag validation checks.
@version 1.0
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .config import get_impact, get_validate

if TYPE_CHECKING:
    from collections.abc import Set as AbstractSet

    from .parser import Function

logger = logging.getLogger(__name__)


_JS_SUFFIXES = (".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx")


## @brief Build a language-appropriate doxygen skeleton suggestion.
#  @version 1.2
#  @dg_internal
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
#  @version 1.1
#  @dg_internal
def _suggest_file_skeleton(file_path: str) -> str:
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
#  @dg_internal
#  @return The remedy text for a missing-@brief violation
def _brief_hint(file_path: str) -> str:
    if Path(file_path).suffix.lower() in (".rs", ".py", *_JS_SUFFIXES):
        return "start the doc comment with a summary sentence, or add '@brief <description>'"
    return "add '@brief <description>' to the doxygen comment"


## @brief Represents a check failure with location and description.
#  @version 1.0
#  @dg_internal
@dataclass
class Violation:
    file: str
    line: int  # 1-indexed for display
    check: str  # "presence" | "version" | "tag"
    message: str

    ## @brief Human-readable violation string.
    #  @version 1.0
    #  @dg_internal
    def __str__(self) -> str:
        return f"{self.file}:{self.line}: [{self.check}] {self.message}"


## @brief Verify every function has a doxygen comment with \@brief and the revision tag.
#  @version 1.5
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
#  @version 1.3
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
#  @version 1.4
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
        if name_pos <= 0:
            continue
        prefix = line[:name_pos]
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
EXEMPTION_TAGS: frozenset[str] = frozenset({"utility", "dg_internal", "callback"})

# Tags this tool invents. Doxygen does not define them, so it emits unknown-command
# warnings unless they are declared as ALIASES — which is what `doxygen-guard doxyfile`
# generates. Anything not in here is a real doxygen command and needs no alias.
TOOL_OWNED_TAGS: frozenset[str] = EXEMPTION_TAGS | frozenset({"req"})


## @brief Render the exemption tags for an error message, derived from the set.
#  @version 1.0
#  @dg_internal
#  @return Comma-separated @-prefixed tag names in a stable order
def _exemption_hint() -> str:
    return ", ".join(f"@{t}" for t in sorted(EXEMPTION_TAGS))


## @brief Check if version gate is configured.
#  @version 1.2
#  @dg_internal
def _has_version_gate(config: dict[str, Any]) -> bool:
    gate = get_validate(config).get("version_gate", {})
    return bool(gate.get("current_version") and gate.get("version_field"))


## @brief Check if any requirements pass the version gate filter.
#  @version 1.1
#  @dg_internal
def _has_active_requirements(config: dict[str, Any]) -> bool:
    from .impact import filter_requirements_by_version, load_requirements_full

    full = load_requirements_full(config)
    filtered = filter_requirements_by_version(full, config)
    return bool(filtered)


## @brief Verify functions have requirement or exemption tags when requirements are configured.
#  @version 1.6
#  @req REQ-DDB-GUARD-004
def check_req_coverage(
    functions: list[Function],
    file_path: str,
    config: dict[str, Any],
) -> list[Violation]:
    req_config = get_impact(config).get("requirements")
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
        if func.is_constructor() or func.is_destructor():
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
#  function whose signature itself changed since HEAD is treated as new (no match found)
#  rather than matched to a differently-shaped prior version — the same "skip if absent"
#  behaviour as a genuinely new function.
#  @version 2.0
#  @dg_internal
#  @return Mapping from (enclosing_class, name, signature) to the HEAD-side Function
def _index_by_identity(
    functions: list[Function],
) -> dict[tuple[str | None, str, str], Function]:
    return {(f.enclosing_class, f.name, f.signature): f for f in functions}


## @brief Extract a function's definition-through-body source text.
#  @version 1.0
#  @dg_internal
#  @return Joined source lines from def_line through body_end, or "" if out of range
def _body_text(func: Function, lines: list[str]) -> str:
    return "\n".join(lines[func.def_line : func.body_end + 1])


## @brief Fixed inputs for comparing one file's functions against its HEAD revision.
#  @version 1.0
#  @dg_internal
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
#  @version 1.0
#  @dg_internal
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
#  @version 2.1
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

    violations: list[Violation] = []
    for func in functions:
        head_func = head_index.get((func.enclosing_class, func.name, func.signature))
        violation = _check_one_version(func, head_func, ctx)
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
#  @version 1.1
#  @dg_internal
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
#  @version 1.0
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
    known = _KNOWN_TAGS | extra | set(validate_config.get("tags", {}).keys())

    violations: list[Violation] = []
    for tag_name in func.doxygen.tags:
        if tag_name not in known:
            suggestion = _suggest_tag(tag_name, known)
            hint = f" — did you mean @{suggestion}?" if suggestion else ""
            violations.append(
                Violation(
                    file=file_path,
                    line=func.doxygen.start_line + 1,
                    check="tag",
                    message=f"Unknown tag @{tag_name} in {func.name}(){hint}",
                )
            )
    return violations


# Tags that describe the function as a whole. A second occurrence is not additive:
# downstream readers take tags[name][0], so a duplicate is silently ignored and can
# carry a different value than the author intended.
#
# "version" is deliberately absent. Doxygen permits multiple \version entries, which
# accumulate into one paragraph — flagging them rejected legal doxygen. That was a
# regression introduced with this check in 1.3.0.
_SINGLE_VALUED_TAGS: frozenset[str] = frozenset({"brief", "return", "returns", "file"})


## @brief Flag single-valued doxygen tags that appear more than once in one block.
#  @version 1.0
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
                    message=(
                        f"@{tag_name} appears {len(values)} times in {func.name}() — "
                        f"only the first is used; remove the extras"
                    ),
                )
            )
    return violations


## @brief Find the closest known tag name using edit distance.
#  @version 1.1
#  @dg_internal
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
#  @dg_internal
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


## @brief Cross-validate requirement tag references against the requirements file.
#  @version 1.0
#  @req REQ-DDB-GUARD-001
def check_req_exists(
    func: Function,
    file_path: str,
    config: dict[str, Any],
    req_ids: set[str] | None = None,
) -> list[Violation]:
    if func.doxygen is None or req_ids is None:
        return []

    validate_config = get_validate(config)
    tag_config = validate_config.get("tags", {}).get("req", {})
    if not tag_config.get("cross_reference", True):
        return []

    violations: list[Violation] = []
    for req_id in func.doxygen.tags.get("req", []):
        if req_id not in req_ids:
            violations.append(
                Violation(
                    file=file_path,
                    line=func.doxygen.start_line + 1,
                    check="tag",
                    message=(
                        f"@req {req_id} in {func.name}() not found in requirements file"
                        f" — verify the ID or add it to the requirements"
                    ),
                )
            )
    return violations


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
#  @version 1.3
#  @req REQ-DDB-GUARD-006
#  @return List of violations for missing required tags
def _check_file_block_tags(file_path: str, lines: list[str], block_start: int) -> list[Violation]:
    block_text = _extract_file_block_text(lines, block_start)
    from .parser import parse_doxygen_tags

    tags = parse_doxygen_tags(block_text)
    violations: list[Violation] = []
    required = {"file": "@file", "brief": "@brief", "version": "@version"}
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
#  @version 1.1
#  @dg_internal
#  @return The raw text of the doxygen block
def _extract_file_block_text(lines: list[str], start: int) -> str:
    block_lines: list[str] = []
    for i in range(start, min(start + 30, len(lines))):
        block_lines.append(lines[i])
        if "*/" in lines[i] or (i > start and not lines[i].strip().startswith(("*", "#", "//"))):
            break
    return "\n".join(block_lines)


# In Rust only an INNER doc comment documents the file (its module): `///` and `/**` at the
# top of a file document the first item, so reading them as the file block reports an
# item's doc as a file block missing @file.
_RUST_FILE_DOC_STARTS = ("//!", "/*!")


## @brief Find the line index of the file-level doxygen block start.
#  @version 1.4
#  @req REQ-DDB-GUARD-006
#  @return 0-indexed line number, or None if no block found
def _find_file_doxygen_start(
    lines: list[str], doxygen_starts: tuple[str, ...] | None = None
) -> int | None:
    skip_prefixes = ("#include", "#pragma", "#ifndef", "#define")
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
#  @dg_internal
#  @return 1-indexed line number for violation reporting
def _first_code_line(lines: list[str]) -> int:
    for i, line in enumerate(lines):
        if line.strip():
            return i + 1
    return 1
