# SPDX-License-Identifier: MIT
"""Configuration loading, defaults, and merging for the gate.

The gate's config is the `guard:` section of the repo's `.clew.yaml`, the same file that
carries the index's declarations, so a repo keeps one config file for both.

@brief Load and validate the `guard:` section of `.clew.yaml`.
@version 1.1
"""

from __future__ import annotations

import copy
import difflib
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .errors import ConfigError

if TYPE_CHECKING:
    from .parser import ParseSettings

import yaml

logger = logging.getLogger(__name__)

# The file the gate reads, and the section of it that is the gate's. The rest of the file
# is the index's declaration (clew/declaration.py), which the gate never interprets.
CONFIG_FILE_NAME = ".clew.yaml"
CONFIG_SECTION = "guard"

# doxygen-guard's own config file, which clew does NOT read. Named here only so a repository
# that still carries one can be told why its gate went quiet (group B, 1.1.0 merge review):
# the `@req` gate in particular goes from enforced to absent with no output at all, which is
# the same silent-success failure as a skipped file reporting nothing.
LEGACY_CONFIG_NAME = ".doxygen-guard.yaml"
## A `doxygen-guard` hook id in a pre-commit config (2.0.0, PG4: refused, naming `clew-guard`).
_LEGACY_HOOK_ID = re.compile(r"^\s*-?\s*id:\s*['\"]?doxygen-guard['\"]?\s*$", re.M)

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
            # WIDENED TO MATCH THE INDEX (group A, 1.1.0 merge review). `harvest._CPP_EXTS`
            # has read `.hh`, `.hxx`, `.c++` and `.h++` since C++ support landed, so those
            # files carried symbols, call edges and requirement links while the gate skipped
            # them with a DEBUG line nobody sees. `tests/test_gate_index_extension_parity.py`
            # is what keeps the two tables from drifting again, in either direction.
            # 2.0.0 (C2): and every other C++ suffix doxygen indexes, which the index now parses.
            "extensions": [
                ".cpp",
                ".hpp",
                ".cc",
                ".cxx",
                ".hh",
                ".hxx",
                ".c++",
                ".h++",
                ".ipp",
                ".inl",
                ".ixx",
                ".cppm",
                ".cxxm",
                ".c++m",
                ".ii",
                ".i++",
            ],
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
            # `.pyi` for the reason `harvest._PY_EXTS` gives: a stub carries the signatures
            # and docstrings a consumer reads, so a stub nobody documents is a documented API
            # with an undocumented interface.
            "extensions": [".py", ".pyi"],
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
        # `.mts`/`.cts` are TypeScript's ES-module and CommonJS spellings, read by both
        # `harvest._TS_EXTS` and `synth.SYNTH_EXTS` since JS/TS support landed.
        "extensions": [".ts", ".tsx", ".mts", ".cts"],
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
## ONE DEFAULT PAIR FOR EVERY READER (R5-CFG F8, 2.0.0). The gate defaulted to `Req ID`/`name` and
## the index to `id`/`title`, so an undeclared flat `[{id, ...}]` catalog was keyed by one tool
## and not the other. `id` is the index's id key and `name` the gate's required name field (the
## index reads `name` or `title` either way, so its behaviour does not change).
REQUIREMENTS_ID_COLUMN_DEFAULT = "id"
REQUIREMENTS_NAME_COLUMN_DEFAULT = "name"
REQUIREMENTS_ROOT_KEY = "requirements"
REQUIREMENTS_REQUIRED_FIELDS = (REQUIREMENTS_NAME_COLUMN_DEFAULT,)
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

## ONE PATH FOR THE IMPACT REPORT (R5-CFG F9 / D8, 2.0.0). It was `output_dir` (a generic
## directory that only ever held this report) for the hook, `impact.output.file` for the
## subcommand and `wiki.impact` for the site — three keys that could disagree, and the literal
## `docs/generated/` restated in four places. The hook writes `impact.md` and `impact.json` here,
## `clew guard impact --write` does the same, and the wiki reads `impact.json` from here.
DEFAULT_REPORT_DIR = "docs/generated/impact/"
REPORT_MARKDOWN = "impact.md"
REPORT_JSON = "impact.json"

## The branch the impact report diffs against, when `guard.impact.base` names none (R5-CFG W8, 2.0.0):
## a repository on `master`, `develop` or an `upstream` remote states its own.
DEFAULT_IMPACT_BASE = "origin/main"

IMPACT_DEFAULTS: dict[str, Any] = {"report_dir": DEFAULT_REPORT_DIR, "base": DEFAULT_IMPACT_BASE}

## `validate.exemption_reason` settings (2.0.0, PG3b). `optional` is the default: a repository
## turns `required` on once its reasons are written (clew has ~1,629 unreasoned exemptions).
EXEMPTION_REASON_SETTINGS: tuple[str, ...] = ("optional", "required")

## No floor unless declared (owner, 2.0.0): no standard sets a requirement ratio, and the measured
## values differ by repository, so a built-in number would be one repository's tuning.
COVERAGE_DEFAULTS: dict[str, Any] = {"min_req_ratio": None}

## `requirements` is the top-level catalog section, carried in the loaded config so every gate
## reader finds it in one place; None means no catalog is declared. It is not a `guard:` key, and
## `config --effective` reports it under `resolved.requirements` rather than echoing it as input.
## `event_tags` (the declaration's event vocabulary, R5-CFG F10) and `wiki_sources` (whether
## `wiki.sources` is declared, R5-CFG F11) are read from the same `.clew.yaml` for the same reason:
## facts the gate must agree with the index and the wiki about, not `guard:` keys. `owners` (the
## top-level `owners:` section, 2.0.0) is how the impact report finds the same owners files the
## index's `owners` layer reads.
CONFIG_DEFAULTS: dict[str, Any] = {
    "validate": VALIDATE_DEFAULTS,
    "impact": IMPACT_DEFAULTS,
    "coverage": COVERAGE_DEFAULTS,
    "requirements": None,
    "event_tags": None,
    "wiki_sources": False,
    "owners": None,
    "test_paths": None,
}

## Keys of the loaded config that are not `guard:` keys (the cross-section facts above).
NON_GUARD_KEYS = ("requirements", "event_tags", "wiki_sources", "owners", "test_paths")

## THE TOP-LEVEL `requirements:` SECTION (R5-CFG F6/F7/F14, 2.0.0): one catalog, read by the index,
## the gate and the wiki. Before, it lived in five places — a top-level path the index alone read,
## `guard.impact.requirements` (gate, wiki, coverage), `wiki.catalogs` and
## `impact.requirements.external` (one concept in two spellings), and `wiki.needs` — and each
## tool read a different one. `version_field` is a catalog field, so it lives here too.
REQUIREMENTS_SCHEMA: dict[str, Any] = {
    "file": str,
    "format": str,
    "id_column": str,
    "name_column": str,
    ## GH #68: catalogues this repository does not own — a path, or {repo, rev, path, name?}
    ## read from a local clone at that revision. A URL is refused by name. Pinned entries are
    ## also the wiki's sub-catalogues (what `wiki.catalogs` declared, in its other spelling).
    "external": list,
    ## round 3, P6c: a requirement whose `status_field` value is in `exempt_status` is not a
    ## coverage gap; `clew guard coverage` lists it as exempt, never silently.
    "status_field": str,
    "exempt_status": list,
    ## The catalog field naming the release a requirement becomes active in (the version gate).
    "version_field": str,
    ## A Sphinx-needs `needs.json` whose needs join the requirement trace.
    "needs": str,
}

## Keys that MOVED in 2.0.0, refused with where they went rather than as unknown: each was
## correct in 1.x, so "unknown key" would send a reader hunting a typo that is not there.
MOVED_KEYS: dict[str, str] = {
    "impact.requirements": "the top-level `requirements:` section of .clew.yaml",
    "validate.version_gate.version_field": "`requirements.version_field` (top level)",
    "validate.version_gate.current_version": "`guard.validate.current_version`",
    "output_dir": "`guard.impact.report_dir` (the directory the impact report is written to)",
    "validate.bus.tags": (
        "the top-level `event_tags:` section — the index's event vocabulary, which the gate reads "
        "as its bus tags (undeclared: the index's built-in vocabulary)"
    ),
    "impact.output": (
        "`guard.impact.report_dir`; `clew guard impact --write` writes impact.md and impact.json "
        "there, and without --write it prints (`--format markdown|json|text`)"
    ),
}


_OPEN_DICT = object()


## @brief A mapping whose KEYS are the user's (a tag name, a language name) and whose every VALUE
## follows one schema (R5-CFG F12, 2.0.0). `validate.tags` and `validate.languages` were open
## dicts, so `tags.req.patern` or `languages.c.extentions` passed silently.
## @version 1
class _MapOf:
    ## @brief Hold the schema every entry of the mapping follows.
    #  @version 1.0
    #  @utility
    def __init__(self, schema: dict[str, Any]) -> None:
        self.schema = schema


## 2.1 (#72 item 14): exempt by any catalogue field — `{responsibility: [App, Cloud]}` — so "not ours"
## reads apart from "ours and untested". Any listed field matching exempts. Set here, after `_MapOf`.
REQUIREMENTS_SCHEMA["exempt_when"] = _MapOf(list)


## The keys one `validate.tags.<tag>` entry may carry.
TAG_SCHEMA: dict[str, Any] = {
    "pattern": str,
    "require_prefix": list,
    "require_contains": str,
    ## `req` only: its ids must exist in the catalog.
    "cross_reference": bool,
}

## The keys one `validate.languages.<lang>` entry may carry.
LANGUAGE_SCHEMA: dict[str, Any] = {
    "extensions": list,
    "function_pattern": str,
    "exclude_names": list,
    "comment_style": {"start": str, "end": str},
    "require_return": bool,
}

## The index's built-in event-tag vocabulary (clew/event_edges.py DEFAULT_EVENT_TAGS), restated
## because `clew.guard` imports nothing from the pipeline (a layering decision, recorded in both
## places); a test pins the two copies equal. A repository's declared `event_tags:` replaces it,
## exactly as it does for the index (R5-CFG F10).
DEFAULT_EVENT_TAG_NAMES: tuple[str, ...] = (
    "emits",
    "emit",
    "publishes",
    "publish",
    "produces",
    "sends",
    "raises",
    "fires",
    "posts",
    "handles",
    "handle",
    "subscribes",
    "subscribe",
    "consumes",
    "receives",
    "listens",
    "observes",
)

## The prefix that marks a `validate.exclude` entry as a regex (R5-CFG F18): every other entry is
## a glob, the syntax every other path filter in `.clew.yaml` uses.
EXCLUDE_REGEX_PREFIX = "re:"

CONFIG_SCHEMA: dict[str, Any] = {
    "validate": {
        "languages": _MapOf(LANGUAGE_SCHEMA),
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
        "tags": _MapOf(TAG_SCHEMA),
        "exclude": list,
        "extra_tags": list,
        "known_tags_warn": bool,
        ## 2.0.0 (PG3b): `required` makes every exemption tag carry a one-line reason. `object`
        ## here, like `coverage.min_req_ratio`: `_reason_errors` checks the value.
        "exemption_reason": object,
        "duplicate_tags_error": bool,
        ## The release the version gate compares `requirements.version_field` against: a
        ## literal version, `auto:git` or `auto:cmake` (was `version_gate.current_version`).
        "current_version": str,
        "bus": {"vocabulary": list, "handlers": list, "senders": list},
    },
    "impact": {
        "report_dir": str,
        "base": str,
    },
    ## 2.0.0 (PG3): the requirement ratio floor. `object` here; `_ratio_errors` checks the value,
    ## because the schema's type check would refuse a YAML `1` as "expected float, got int".
    "coverage": {"min_req_ratio": object},
}


## @brief Build a dotted config path from parent path and key.
#  @version 1.0
#  @utility
def _config_path(parent: str, key: str) -> str:
    return f"{parent}.{key}" if parent else key


## @brief Validate dict keys against schema, recursing into sub-nodes.
#  @version 1.3
#  @req REQ-DDB-GUARD-012
#  @return List of error strings for unknown keys and type mismatches
def _validate_dict_node(user: dict, schema: dict, path: str) -> list[str]:
    errors: list[str] = []
    for key in user:
        child_path = _config_path(path, key)
        if key not in schema:
            errors.append(f"Unknown config key: {child_path}{_suggest_key(key, schema)}")
        else:
            errors.extend(_validate_node(user[key], schema[key], child_path))
    return errors


## @brief Suggest the closest known schema key for a misspelled one.
#  @version 1.0
#  @utility
#  @return A " — did you mean 'x'?" fragment, or empty string if nothing is close
def _suggest_key(key: str, schema: dict) -> str:
    matches = difflib.get_close_matches(key, list(schema.keys()), n=1, cutoff=0.6)
    return f" — did you mean '{matches[0]}'?" if matches else ""


## @brief Validate a single config node against its schema spec.
#  @details An explicit null is accepted for any node: it means "section not configured"
#  and is the shape some defaults ship with (impact.requirements). Rejecting it made
#  `config --effective` output invalid as input, so the contract could not round-trip.
#  v1.6: a _MapOf node validates every value against one schema (2.0.0, R5-CFG F12)
#  @version 1.6
#  @req REQ-DDB-GUARD-012
#  @return List of error strings for this node and its children
def _validate_node(user: Any, schema: Any, path: str) -> list[str]:
    if isinstance(schema, _MapOf) and user is not None:
        return _validate_map_of(user, schema, path)
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


## @brief Validate a mapping of user-named entries against the schema every entry follows.
#  @version 1.0
#  @utility
#  @return Errors, each naming the entry's dotted path
def _validate_map_of(user: Any, schema: _MapOf, path: str) -> list[str]:
    if not isinstance(user, dict):
        return [f"{path}: expected dict, got {type(user).__name__}"]
    errors: list[str] = []
    for name, entry in user.items():
        errors.extend(_validate_node(entry, schema.schema, _config_path(path, str(name))))
    return errors


## @brief Refuse a 1.x regex-shaped `validate.exclude` entry, naming the two 2.0.0 forms.
#  @version 1.0
#  @utility
#  @return Errors
def _exclude_errors(user_config: dict[str, Any]) -> list[str]:
    validate = user_config.get("validate") if isinstance(user_config, dict) else None
    excludes = validate.get("exclude") if isinstance(validate, dict) else None
    if not isinstance(excludes, list):
        return []  # a wrong type is the schema's to report
    return [
        f"guard.validate.exclude entry {e!r} reads as a regex; since 2.0.0 entries are globs "
        f"(e.g. `tests/**`), and a regex is written with the `{EXCLUDE_REGEX_PREFIX}` prefix "
        f"(e.g. `{EXCLUDE_REGEX_PREFIX}{e}`)"
        for e in excludes
        if isinstance(e, str)
        and not e.startswith(EXCLUDE_REGEX_PREFIX)
        and (e.startswith("^") or e.endswith("$") or "\\" in e)
    ]


## @brief Refuse an `exemption_reason` setting other than `required` or `optional`.
#  @version 1.0
#  @utility
#  @return Errors
def _reason_errors(user_config: dict[str, Any]) -> list[str]:
    validate = user_config.get("validate") if isinstance(user_config, dict) else None
    value = validate.get("exemption_reason") if isinstance(validate, dict) else None
    if value is None or value in EXEMPTION_REASON_SETTINGS:
        return []
    return [
        f"guard.validate.exemption_reason must be one of {', '.join(EXEMPTION_REASON_SETTINGS)}, "
        f"got {value!r}"
    ]


## @brief Refuse a `coverage.min_req_ratio` that is not a number in (0, 1].
#  @version 1.0
#  @utility
#  @return Errors
def _ratio_errors(user_config: dict[str, Any]) -> list[str]:
    coverage = user_config.get("coverage") if isinstance(user_config, dict) else None
    if not isinstance(coverage, dict) or coverage.get("min_req_ratio") is None:
        return []
    value = coverage["min_req_ratio"]
    number = isinstance(value, int | float) and not isinstance(value, bool)
    if number and 0 < value <= 1:
        return []
    return [
        f"guard.coverage.min_req_ratio must be a number in (0, 1], the share of non-test "
        f"functions carrying @req among those carrying @req or an exemption; got {value!r}"
    ]


## @brief Validate user config keys and types against CONFIG_SCHEMA.
#  @details v1.2 (2.0.0): a key in MOVED_KEYS is reported with where it went, and is not also
#  reported as unknown.
#  v1.3: 1.x regex excludes are refused with the glob and re: forms (2.0.0, R5-CFG F18)
#  v1.4: a coverage.min_req_ratio outside (0, 1] is refused (2.0.0, PG3)
#  v1.5: an exemption_reason other than required / optional is refused (2.0.0, PG3b)
#  @version 1.5
#  @req REQ-DDB-GUARD-012
#  @return List of error strings, empty if config is valid
def validate_config_schema(user_config: dict[str, Any]) -> list[str]:
    moved, rest = _moved_keys(user_config)
    return (
        moved
        + _exclude_errors(rest)
        + _ratio_errors(rest)
        + _reason_errors(rest)
        + _validate_node(rest, CONFIG_SCHEMA, "")
    )


## @brief Split out the keys that moved in 2.0.0, each with a pointer to its new home.
#  @version 1.0
#  @utility
#  @return (errors naming each moved key, the config without them)
def _moved_keys(user_config: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    rest = copy.deepcopy(user_config) if isinstance(user_config, dict) else user_config
    for dotted, where in MOVED_KEYS.items():
        *parents, leaf = dotted.split(".")
        node = rest
        for part in parents:
            node = node.get(part) if isinstance(node, dict) else None
        if isinstance(node, dict) and leaf in node:
            errors.append(f"guard.{dotted} moved in 2.0.0 to {where}")
            del node[leaf]
    gate = (rest.get("validate") or {}) if isinstance(rest, dict) else {}
    if isinstance(gate, dict) and gate.get("version_gate") == {}:
        del gate["version_gate"]
    return errors, rest


## @brief Read and validate the top-level `requirements:` section of a `.clew.yaml`.
#  @details A bare string is the short form of `{file: <string>}`, which is what the 1.x top-level
#  section was. Unknown keys are refused with a suggestion, like every `guard:` key.
#  @version 1.0
#  @req REQ-DDB-GUARD-012
#  @return The section as a mapping, or None when the file declares none
def read_requirements_section(config_path: Path) -> dict[str, Any] | None:
    try:
        with open(config_path) as f:
            document = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError) as e:
        raise ConfigError(f"Could not read config file {config_path}: {e}") from e
    raw = document.get(REQUIREMENTS_ROOT_KEY) if isinstance(document, dict) else None
    if raw is None:
        return None
    section = {"file": raw} if isinstance(raw, str) else raw
    errors = _validate_node(section, REQUIREMENTS_SCHEMA, REQUIREMENTS_ROOT_KEY)
    if not isinstance(section, dict):
        errors = [f"{REQUIREMENTS_ROOT_KEY}: expected a mapping or one path"]
    if errors:
        for err in errors:
            logger.error("Config error in %s: %s", config_path, err)
        raise ConfigError(f"Invalid config in {config_path}", errors)
    return dict(section)


## @brief Parse a version string like "v1.8.2" into a comparable tuple.
#  v2.1: the message names validate.current_version (2.0.0)
#  @version 2.1
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
            f"validate.current_version, either set a literal version or "
            f"ensure the auto: detector can resolve one."
        ) from e


## @brief Compare two version tuples, padding shorter one with zeros.
#  @version 1.0
#  @utility
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


## @brief Refuse to run while a doxygen-guard leftover is in the repository, naming it.
#  @details 2.0.0 (PG4, owner): "a hard cut of doxygen-guard priors — clew only". A leftover
#  `.doxygen-guard.yaml`, or a `doxygen-guard` hook id in `.pre-commit-config.yaml`, FAILS the gate
#  instead of warning. FAIL CLOSED, as a missing catalog does: a stale config a contributor reads
#  states rules the gate does not enforce (the entropic session's catalog went unnoticed for 15
#  months because every consumer failed open). It replaces a warning that fired only when no
#  `guard:` section existed.
#  @version 1.0
#  @req REQ-DDB-GUARD-012
#  @return None; raises ConfigError naming every leftover
def refuse_doxygen_guard_leftovers(root: Path) -> None:
    problems = []
    if (root / LEGACY_CONFIG_NAME).is_file():
        problems.append(
            f"{root / LEGACY_CONFIG_NAME} is a doxygen-guard config: clew 2.0.0 does not read it. "
            'Move its contents under `guard:` in .clew.yaml (docs/GUARD.md, "Migrating from '
            'doxygen-guard") and delete it.'
        )
    hooks = root / ".pre-commit-config.yaml"
    text = hooks.read_text(encoding="utf-8", errors="replace") if hooks.is_file() else ""
    if _LEGACY_HOOK_ID.search(text):
        problems.append(
            f"{hooks} declares the `doxygen-guard` hook id: since 2.0.0 the hook is `clew-guard`, "
            "from the clew repository."
        )
    if problems:
        raise ConfigError("doxygen-guard leftovers (clew 2.0.0 is clew only)", problems)


## @brief Load the `guard:` section of `.clew.yaml` and merge with built-in defaults.
#  @details A missing file, or a file with no `guard:` section, runs on the defaults. A
#  doxygen-guard leftover beside it is refused first (2.0.0, PG4: refuse_doxygen_guard_leftovers).
#  v3.2 (2.0.0): the top-level `requirements:` section rides along as `config["requirements"]`,
#  read with or without a `guard:` section, so the gate and the index read one catalog.
#  v3.3: reads the event vocabulary and wiki.sources from the same file (2.0.0, R5-CFG F10/F11)
#  v3.4: refuses a doxygen-guard leftover before any default applies (2.0.0, PG4)
#  @version 3.4
#  @req REQ-DDB-GUARD-012
#  @return Merged config dict with defaults applied
def load_config(config_path: Path | None = None) -> dict[str, Any]:
    if config_path is None:
        config_path = Path(CONFIG_FILE_NAME)
    ## THE HARD CUT, on every path (2.0.0, PG4): before any default is applied.
    refuse_doxygen_guard_leftovers(config_path.parent)

    if not config_path.exists():
        logger.info("No config file found at %s, using defaults", config_path)
        return _fresh_defaults()

    logger.info("Loading config from %s", config_path)
    shared = {
        REQUIREMENTS_ROOT_KEY: read_requirements_section(config_path),
        **_shared_facts(config_path),
    }
    user_config = read_guard_section(config_path)
    if user_config is None:
        logger.info("No %r section in %s, using defaults", CONFIG_SECTION, config_path)
        return {**_fresh_defaults(), **shared}

    errors = validate_config_schema(user_config)
    if errors:
        for err in errors:
            logger.error("Config error in %s: %s", config_path, err)
        raise ConfigError(f"Invalid config in {config_path}", errors)

    _log_declared_sections(user_config)
    merged = apply_opt_in_languages(deep_merge(_fresh_defaults(), user_config), user_config)
    merged.update(shared)
    return merged


## @brief The facts the gate reads from the rest of `.clew.yaml`: the event vocabulary and sources.
#  v1.1: the owners: section (2.0.0)
#  v1.2: the declared test paths (2.0.0, PG3)
#  @version 1.2
#  @utility
#  @return {"event_tags": declared mapping or None, "wiki_sources": bool, "owners": mapping or None}
def _shared_facts(config_path: Path) -> dict[str, Any]:
    try:
        with open(config_path) as f:
            document = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return {}
    if not isinstance(document, dict):
        return {}
    tags = document.get("event_tags")
    wiki = document.get("wiki") if isinstance(document.get("wiki"), dict) else {}
    owners = document.get("owners")
    tests = document.get("tests") if isinstance(document.get("tests"), dict) else {}
    return {
        ## 2.0.0 (PG3): the declared test paths, so the ratio floor leaves out the code the index
        ## calls test code; None means the index's built-in guesses apply.
        "test_paths": list(tests["paths"]) if isinstance(tests.get("paths"), list) else None,
        "event_tags": dict(tags) if isinstance(tags, dict) else None,
        "wiki_sources": bool(wiki.get("sources")),
        ## 2.0.0: the impact report's reviewers read the same `owners:` section the index does.
        "owners": dict(owners) if isinstance(owners, dict) else None,
    }


## @brief Read the raw `guard:` mapping out of a `.clew.yaml`.
#  @details Raises rather than defaulting on an unreadable file or a `guard:` that is not a
#  mapping: the author plainly meant to configure the gate, and running on the defaults
#  while they believe otherwise is the failure this loader exists to prevent. A document
#  that is not a mapping at all holds no `guard:` section, and is warned about.
#  @version 1.0
#  @req REQ-DDB-GUARD-012
#  @return The section, or None when the file declares no `guard:` section
def read_guard_section(config_path: Path) -> dict[str, Any] | None:
    try:
        with open(config_path) as f:
            document = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError) as e:
        logger.error("Could not read config file %s: %s", config_path, e)
        raise ConfigError(f"Could not read config file {config_path}: {e}") from e
    if not isinstance(document, dict):
        logger.warning("Config file %s is not a mapping, using defaults", config_path)
        return None
    section = document.get(CONFIG_SECTION)
    if section is None:
        return None
    if not isinstance(section, dict):
        raise ConfigError(f"{config_path}: `{CONFIG_SECTION}:` must be a mapping")
    return section


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
#  @version 1.1
#  @req REQ-DDB-GUARD-012
def _log_declared_sections(user_config: dict[str, Any]) -> None:
    declared = sorted(str(k) for k in user_config)
    defaulted = sorted(k for k in CONFIG_SCHEMA if k not in user_config)
    logger.info("Config sections declared: %s", ", ".join(declared) or "none")
    logger.info("Config sections using defaults: %s", ", ".join(defaulted) or "none")


## @brief Access the validate section of config.
#  @version 1.0
#  @utility
def get_validate(config: dict[str, Any]) -> dict[str, Any]:
    return config.get("validate", {})


## @brief Access the impact section of config.
#  @version 1.0
#  @utility
def get_impact(config: dict[str, Any]) -> dict[str, Any]:
    return config.get("impact", {})


## @brief The directory the impact report is written to and read from.
#  @version 1.0
#  @utility
def report_dir(config: dict[str, Any] | None) -> str:
    return str(((config or {}).get("impact") or {}).get("report_dir") or DEFAULT_REPORT_DIR)


## @brief The ref the impact report diffs against (`guard.impact.base`).
#  @version 1.0
#  @utility
def impact_base(config: dict[str, Any] | None) -> str:
    return str(((config or {}).get("impact") or {}).get("base") or DEFAULT_IMPACT_BASE)


## @brief Access the requirements catalog section (the top-level `requirements:`).
#  @version 1.0
#  @utility
def get_requirements(config: dict[str, Any] | None) -> dict[str, Any]:
    return (config or {}).get(REQUIREMENTS_ROOT_KEY) or {}


## @brief Why a catalogue row is exempt from coverage, or None: its status, or a named field.
#  @details 2.1 (#72 item 14): ONE PREDICATE for the gate's coverage and the wiki's evidence, so the
#  two never disagree about what is exempt. `exempt_status` matches `status_field`; each
#  `exempt_when` field matches its own listed values.
#  @version 1.0
#  @req REQ-DDB-GUARD-022
#  @return `"<field>: <value>"`, or None
def exemption(row: dict[str, Any], requirements: dict[str, Any]) -> str | None:
    field = requirements.get("status_field", "status")
    rules = [(field, requirements.get("exempt_status") or [])]
    rules += list((requirements.get("exempt_when") or {}).items())
    for name, values in rules:
        value = row.get(name)
        if value is not None and str(value) in {str(v) for v in values}:
            return f"{name}: {value}"
    return None


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


## @brief Name a language the gate ships but this config did not enable, for one file.
#  @param config The resolved gate config.
#  @param file_path The file that matched no active language.
#  @return The shipped language's name, or None when nothing the gate ships claims it.
#  @version 1
#  @req REQ-DDB-GUARD-013
def unconfigured_language(config: dict[str, Any], file_path: str) -> str | None:
    """WHY A SKIP IS SOMETIMES WORTH REPORTING AND USUALLY IS NOT (group A, 1.1.0 merge
    review). `rust`, `javascript` and `typescript` are opt-in: the published hook passes `.rs`
    files, and a repo that adopted the gate for its C must not start failing on its Rust the
    first time it bumps `rev:`. That decision is right and it was paid for in silence —
    `validate_file` logged "no matching language config" at DEBUG and returned clean, so a
    repository whose every `.rs` file was undocumented got `rc=0` and no output.

    A README or a lock file must stay silent, or the report is noise an owner scrolls past.
    The question that separates the two is not "is this source" — it is whether THE GATE SHIPS
    A LANGUAGE for this extension that this configuration did not enable. Nothing else can be
    something the gate failed to check.

    @brief The shipped-but-unconfigured language for a file, if any.
    @return The language name, or None.
    """
    ext = Path(file_path).suffix.lower()
    shipped = dict(VALIDATE_DEFAULTS["languages"])
    shipped.update(OPT_IN_LANGUAGE_DEFAULTS)
    for name, lang_config in shipped.items():
        if ext in {e.lower() for e in lang_config.get("extensions", [])}:
            return name
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
