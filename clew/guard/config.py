"""Configuration loading, defaults, and merging for doxygen-guard.

@brief Load and validate .doxygen-guard.yaml configuration.
@version 1.0
"""

from __future__ import annotations

import copy
import difflib
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .errors import ConfigError

if TYPE_CHECKING:
    from .parser import ParseSettings

import yaml

logger = logging.getLogger(__name__)

# Consumers of doxygen-guard may declare their own sections in .doxygen-guard.yaml
# using this prefix. The guard validates that they exist but never interprets them.
PASSTHROUGH_PREFIX = "x-"

VALIDATE_DEFAULTS: dict[str, Any] = {
    "languages": {
        "c": {
            "extensions": [".c", ".h"],
            "function_pattern": (
                r"^\s*(?:(?:static|inline|extern|STATIC|INLINE|WEAK)\s+)*"
                r"(?:(?:const|volatile|unsigned|signed|long|short|struct|enum)\s+)*"
                r"(?:[A-Za-z_]\w*)[\s*]+"
                r"(\w+)\s*\("
            ),
            "exclude_names": [
                "if",
                "for",
                "while",
                "switch",
                "return",
                "sizeof",
                "typedef",
                "define",
                "elif",
                "ifdef",
                "ifndef",
                "include",
            ],
        },
        "cpp": {
            "extensions": [".cpp", ".hpp", ".cc", ".cxx"],
            "function_pattern": (
                r"^\s*(?:(?:static|inline|extern(?:\s+\"C\")?|virtual|explicit|constexpr)\s+)*"
                r"(?:template\s*<[^>]*>\s*)?"
                r"(?:(?:const|volatile|unsigned|signed|long|short|struct|enum)\s+)*"
                r"(?:[A-Za-z_]\w*(?:::[A-Za-z_]\w*)*(?:<[^>]*>)?)[\s*&]+"
                r"(?:[A-Za-z_]\w*::)*(\w+)\s*\("
            ),
            "exclude_names": [
                "if",
                "for",
                "while",
                "switch",
                "return",
                "sizeof",
                "typedef",
                "define",
                "elif",
                "ifdef",
                "ifndef",
                "include",
            ],
        },
        "python": {
            "extensions": [".py"],
            "function_pattern": r"^\s*(?:async\s+)?def\s+(\w+)\s*\(",
            "exclude_names": [],
            "comment_style": {
                "start": r"^\s*##(?!#)",
                "end": r"^\s*#",
            },
        },
    },
    "comment_style": {
        "start": r"/\*\*(?!\*)",
        "end": r"\*/",
    },
    "presence": {
        "require_doxygen": True,
        "require_return": True,
    },
    "version": {
        "tag": "@version",
        "require_present": True,
        "require_increment_on_change": True,
    },
    "tags": {},
    "exclude": [],
}

# Languages the gate supports but does not check unless a repo DECLARES them (Rust,
# JavaScript, TypeScript). Declaring `validate.languages.rust: {}` is enough — the declared mapping is merged over these
# defaults. Opt-in rather than default because the published hook now passes `.rs` files,
# and a repo that adopted the gate for its C would otherwise start failing on its Rust
# the first time it bumps `rev:`.
#
# Rust's conventions (see docs/languages/RUST_INTEGRATION.md): the block is the rustdoc
# outer doc comment (`///` or `/** */`), its summary paragraph stands in for @brief, and
# @return is not required (`require_return: false`) because rustdoc has no return tag.
OPT_IN_LANGUAGE_DEFAULTS: dict[str, dict[str, Any]] = {
    "rust": {
        "extensions": [".rs"],
        "function_pattern": (
            r"^\s*(?:pub(?:\([^)]*\))?\s+)?"
            r"(?:(?:const|async|unsafe|extern(?:\s+\"[^\"]*\")?)\s+)*"
            r"fn\s+(\w+)"
        ),
        "exclude_names": [],
        "comment_style": {
            "start": r"^\s*///(?!/)",
            "end": r"^\s*//",
        },
        "require_return": False,
    },
    # JSDoc. JavaScript has no return annotation, so a JS function always counts as void
    # and `require_return: true` only bites in TypeScript, where `: void` / `Promise<void>`
    # / `never` / `undefined` are void and any other annotation is not.
    "javascript": {
        "extensions": [".js", ".mjs", ".cjs", ".jsx"],
        "function_pattern": r"^\s*(?:export\s+)?(?:async\s+)?function\*?\s+(\w+)",
        "exclude_names": [],
        "comment_style": {"start": r"/\*\*(?!\*)", "end": r"\*/"},
        "require_return": False,
    },
    "typescript": {
        "extensions": [".ts", ".tsx"],
        "function_pattern": r"^\s*(?:export\s+)?(?:async\s+)?function\*?\s+(\w+)",
        "exclude_names": [],
        "comment_style": {"start": r"/\*\*(?!\*)", "end": r"\*/"},
        "require_return": False,
    },
}

# Canonical defaults for the requirements catalog. Consumers that read a catalog
# must import these rather than re-deriving them; duplicating the literals is how
# the gate and its consumers drift apart.
REQUIREMENTS_FORMAT_DEFAULT = "yaml"
REQUIREMENTS_ID_COLUMN_DEFAULT = "Req ID"
REQUIREMENTS_NAME_COLUMN_DEFAULT = "name"
REQUIREMENTS_ROOT_KEY = "requirements"
REQUIREMENTS_REQUIRED_FIELDS = ("name",)
REQUIREMENTS_OPTIONAL_FIELDS = (
    "subsystem",
    "min_version",
    "description",
    "acceptance_criteria",
)

# id_column applies only to the flat row formats (csv, json, and the legacy YAML
# list form). The mapping-keyed YAML catalog carries the ID as the mapping key,
# so no column name is involved.
REQUIREMENTS_FORMATS_USING_ID_COLUMN = ("csv", "json")

IMPACT_DEFAULTS: dict[str, Any] = {
    "requirements": None,
}

CONFIG_DEFAULTS: dict[str, Any] = {
    "output_dir": "docs/generated/",
    "validate": VALIDATE_DEFAULTS,
    "impact": IMPACT_DEFAULTS,
}


_OPEN_DICT = object()

CONFIG_SCHEMA: dict[str, Any] = {
    "output_dir": str,
    "validate": {
        "languages": _OPEN_DICT,
        "comment_style": {"start": str, "end": str},
        "presence": {
            "require_doxygen": bool,
            "require_return": bool,
            "require_file_doxygen": bool,
        },
        "version": {
            "tag": str,
            "require_present": bool,
            "require_increment_on_change": bool,
        },
        "tags": _OPEN_DICT,
        "exclude": list,
        "extra_tags": list,
        "known_tags_warn": bool,
        "duplicate_tags_error": bool,
        "version_gate": {"current_version": str, "version_field": str},
    },
    "impact": {
        "requirements": {
            "file": str,
            "format": str,
            "id_column": str,
            "name_column": str,
        },
        "output": {
            "format": str,
            "file": str,
        },
    },
}


## @brief Build a dotted config path from parent path and key.
#  @version 1.0
#  @dg_internal
def _config_path(parent: str, key: str) -> str:
    return f"{parent}.{key}" if parent else key


## @brief Validate dict keys against schema, recursing into sub-nodes.
#  @version 1.2
#  @req REQ-DDB-GUARD-012
#  @return List of error strings for unknown keys and type mismatches
def _validate_dict_node(user: dict, schema: dict, path: str) -> list[str]:
    errors: list[str] = []
    for key in user:
        child_path = _config_path(path, key)
        if isinstance(key, str) and key.startswith(PASSTHROUGH_PREFIX):
            logger.info("Passthrough config key not interpreted by doxygen-guard: %s", child_path)
        elif key not in schema:
            errors.append(f"Unknown config key: {child_path}{_suggest_key(key, schema)}")
        else:
            errors.extend(_validate_node(user[key], schema[key], child_path))
    return errors


## @brief Suggest the closest known schema key for a misspelled one.
#  @version 1.0
#  @dg_internal
#  @return A " — did you mean 'x'?" fragment, or empty string if nothing is close
def _suggest_key(key: str, schema: dict) -> str:
    matches = difflib.get_close_matches(key, list(schema.keys()), n=1, cutoff=0.6)
    return f" — did you mean '{matches[0]}'?" if matches else ""


## @brief Validate a single config node against its schema spec.
#  @details An explicit null is accepted for any node: it means "section not configured"
#  and is the shape some defaults ship with (impact.requirements). Rejecting it made
#  `config --effective` output invalid as input, so the contract could not round-trip.
#  @version 1.5
#  @req REQ-DDB-GUARD-012
#  @return List of error strings for this node and its children
def _validate_node(user: Any, schema: Any, path: str) -> list[str]:
    unconstrained = schema is _OPEN_DICT or not isinstance(schema, type | dict)
    if unconstrained or user is None:
        return []
    if isinstance(schema, type):
        return (
            []
            if isinstance(user, schema)
            else [f"{path}: expected {schema.__name__}, got {type(user).__name__}"]
        )
    return (
        [f"{path}: expected dict, got {type(user).__name__}"]
        if not isinstance(user, dict)
        else _validate_dict_node(user, schema, path)
    )


## @brief Validate user config keys and types against CONFIG_SCHEMA.
#  @version 1.1
#  @req REQ-DDB-GUARD-012
#  @return List of error strings, empty if config is valid
def validate_config_schema(user_config: dict[str, Any]) -> list[str]:
    return _validate_node(user_config, CONFIG_SCHEMA, "")


## @brief Parse a version string like "v1.8.2" into a comparable tuple.
#  @version 2.0
#  @req REQ-DDB-GUARD-014
#  @return Tuple of integer components for comparison
def parse_version(version_str: str) -> tuple[int, ...]:
    cleaned = version_str.strip().lstrip("vV")
    # Strip pre-release and build metadata (e.g., -rc1, +build123)
    cleaned = cleaned.split("-")[0].split("+")[0]
    try:
        return tuple(int(p) for p in cleaned.split("."))
    except ValueError as e:
        # Returning (0,) here used to make every requirement sort as "not yet
        # active", which silently disabled the whole @req coverage gate while the
        # run still reported success. A gate that cannot evaluate must not pass.
        logger.error("Could not parse version %r", version_str)
        raise ConfigError(
            f"Could not parse version {version_str!r}. If this came from "
            f"validate.version_gate.current_version, either set a literal version or "
            f"ensure the auto: detector can resolve one."
        ) from e


## @brief Compare two version tuples, padding shorter one with zeros.
#  @version 1.0
#  @dg_internal
def compare_versions(a: tuple[int, ...], b: tuple[int, ...]) -> int:
    max_len = max(len(a), len(b))
    a_padded = a + (0,) * (max_len - len(a))
    b_padded = b + (0,) * (max_len - len(b))
    if a_padded < b_padded:
        return -1
    if a_padded > b_padded:
        return 1
    return 0


## @brief Deep-copy the built-in defaults so callers cannot mutate module state.
#  @details deep_merge is a shallow merge: it only builds a new dict for keys present
#  in both sides, so config["validate"] used to BE the module-level VALIDATE_DEFAULTS
#  when no config file existed. Callers then wrote through that alias (--exclude
#  appending, version-gate resolution) and permanently mutated global state, which
#  leaked across load_config calls in one process and made contract output report
#  defaults a previous call had changed.
#  @version 1.0
#  @req REQ-DDB-GUARD-012
#  @return An independent copy of CONFIG_DEFAULTS
def _fresh_defaults() -> dict[str, Any]:
    return copy.deepcopy(CONFIG_DEFAULTS)


## @brief Recursively merge two dicts; override values win for non-dict leaves.
#  @version 1.0
#  @utility
def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


## @brief Load .doxygen-guard.yaml and merge with built-in defaults.
#  @version 2.2
#  @req REQ-DDB-GUARD-012
#  @return Merged config dict with defaults applied
def load_config(config_path: Path | None = None) -> dict[str, Any]:
    if config_path is None:
        config_path = Path(".doxygen-guard.yaml")

    if not config_path.exists():
        logger.info("No config file found at %s, using defaults", config_path)
        return _fresh_defaults()

    logger.info("Loading config from %s", config_path)
    try:
        with open(config_path) as f:
            user_config = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError) as e:
        logger.error("Could not read config file %s: %s", config_path, e)
        raise ConfigError(f"Could not read config file {config_path}: {e}") from e

    if not isinstance(user_config, dict):
        logger.warning("Config file %s is not a mapping, using defaults", config_path)
        return _fresh_defaults()

    errors = validate_config_schema(user_config)
    if errors:
        for err in errors:
            logger.error("Config error in %s: %s", config_path, err)
        raise ConfigError(f"Invalid config in {config_path}", errors)

    _log_declared_sections(user_config)
    return apply_opt_in_languages(deep_merge(_fresh_defaults(), user_config), user_config)


## @brief Fill a declared opt-in language (e.g. `rust: {}`) from its built-in defaults.
#  @details The user's own keys win; a language the user did not declare is not added.
#  @version 1.0
#  @req REQ-DDB-GUARD-024
#  @return The merged config, with each declared opt-in language completed
def apply_opt_in_languages(merged: dict[str, Any], user_config: dict[str, Any]) -> dict[str, Any]:
    declared = (user_config.get("validate") or {}).get("languages") or {}
    languages = merged.setdefault("validate", {}).setdefault("languages", {})
    for name, defaults in OPT_IN_LANGUAGE_DEFAULTS.items():
        if name in declared:
            languages[name] = deep_merge(copy.deepcopy(defaults), declared[name] or {})
    return merged


## @brief Log which top-level sections the user declared versus which are defaulted.
#  @version 1.0
#  @req REQ-DDB-GUARD-012
def _log_declared_sections(user_config: dict[str, Any]) -> None:
    declared = sorted(k for k in user_config if not str(k).startswith(PASSTHROUGH_PREFIX))
    defaulted = sorted(k for k in CONFIG_SCHEMA if k not in user_config)
    passthrough = sorted(k for k in user_config if str(k).startswith(PASSTHROUGH_PREFIX))
    logger.info("Config sections declared: %s", ", ".join(declared) or "none")
    logger.info("Config sections using defaults: %s", ", ".join(defaulted) or "none")
    if passthrough:
        logger.info("Config passthrough sections (not interpreted): %s", ", ".join(passthrough))


## @brief Access the validate section of config.
#  @version 1.0
#  @dg_internal
def get_validate(config: dict[str, Any]) -> dict[str, Any]:
    return config.get("validate", {})


## @brief Access the impact section of config.
#  @version 1.0
#  @dg_internal
def get_impact(config: dict[str, Any]) -> dict[str, Any]:
    return config.get("impact", {})


## @brief Reject output paths containing directory traversal or absolute components.
#  @version 1.4
#  @utility
def validate_output_path(path: str) -> Path:
    p = Path(path)
    if p.is_absolute():
        raise ConfigError(f"Output path '{path}' must be relative")
    if ".." in p.parts:
        raise ConfigError(f"Output path '{path}' contains directory traversal")
    if str(p).startswith("-"):
        # git add would parse a leading dash as an option.
        raise ConfigError(f"Output path '{path}' must not begin with '-'")
    resolve_contained_path(path, setting="output path")
    return p


## @brief Resolve a config-supplied path and require it to stay inside the repo.
#  @details Containment is checked after resolution, so a symlinked component cannot
#  escape. String inspection alone (is_absolute / ".." in parts) does not hold: git
#  tracks symlinks, so a repository can ship one that points outside the worktree.
#  @version 1.0
#  @req REQ-DDB-GUARD-016
#  @return The resolved path
def resolve_contained_path(path: str, *, setting: str) -> Path:
    root = Path.cwd().resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        logger.error("%s resolves outside the repository: %s -> %s", setting, path, target)
        raise ConfigError(
            f"{setting} must stay inside the repository; {path!r} resolves to {target}"
        )
    return target


## @brief Match a file path to its language config by extension.
#  @version 1.2
#  @req REQ-DDB-GUARD-013
#  @return Language config dict, or None if no language matches the file extension
def get_language_config(config: dict[str, Any], file_path: str) -> dict[str, Any] | None:
    ext = Path(file_path).suffix
    languages = get_validate(config).get("languages", {})

    for _lang_name, lang_config in languages.items():
        if ext in lang_config.get("extensions", []):
            return lang_config
    return None


## @brief Parse all functions from a source file using language-aware settings.
#  @version 2.0
#  @req REQ-DDB-GUARD-018
#  @return Detected functions, or None if no language config matches the file
def parse_source_file(
    file_path: str,
    config: dict[str, Any],
) -> list | None:
    result = parse_source_file_with_content(file_path, config)
    if result is None:
        return None
    return result[0]


## @brief Parse functions and return both the function list and file content.
#  @version 2.2
#  @req REQ-DDB-GUARD-018
#  @return Tuple of (functions, content), or None if no language config matches
def parse_source_file_with_content(
    file_path: str,
    config: dict[str, Any],
) -> tuple[list, str] | None:
    content = Path(file_path).read_text(errors="replace")
    functions = parse_content_for_file(file_path, content, config)
    if functions is None:
        return None
    return functions, content


## @brief Parse functions out of arbitrary content using a file path's language config.
#  @details Lets callers parse content that did not come from reading the live file —
#  e.g. a file's contents as of another git revision — through the same language
#  resolution and settings as parse_source_file_with_content.
#  @version 1.0
#  @req REQ-DDB-GUARD-018
#  @return List of functions, or None if no language config or grammar matches
def parse_content_for_file(
    file_path: str,
    content: str,
    config: dict[str, Any],
) -> list | None:
    from .parser import parse_functions
    from .ts_languages import language_for_file

    lang_config = get_language_config(config, file_path)
    if lang_config is None:
        return None

    settings = resolve_parse_settings(config, lang_config)
    lang_name = language_for_file(file_path, config)
    if lang_name is None:
        logger.warning(
            "%s matched language config but no tree-sitter grammar is available; skipping",
            file_path,
        )
        return None

    return parse_functions(
        content=content,
        exclude_names=lang_config.get("exclude_names", []),
        settings=settings,
        lang_name=lang_name,
    )


## @brief Resolve comment style and body style for a given language config.
#  @version 1.4
#  @req REQ-DDB-GUARD-013
#  @return ParseSettings with comment style and body detection mode
def resolve_parse_settings(config: dict[str, Any], lang_config: dict[str, Any]) -> ParseSettings:
    from .parser import ParseSettings

    default_style = VALIDATE_DEFAULTS["comment_style"]
    global_style = get_validate(config).get("comment_style", {})
    lang_style = lang_config.get("comment_style", {})
    return ParseSettings(
        comment_start=lang_style.get("start", global_style.get("start", default_style["start"])),
        comment_end=lang_style.get("end", global_style.get("end", default_style["end"])),
    )
