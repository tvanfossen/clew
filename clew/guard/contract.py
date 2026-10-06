"""Machine-readable contract surface for consumers of the gate (formerly doxygen-guard).

@brief Emit the config schema, the effective config, and the resolved file set as JSON.
@version 1.0

Consumers must read their assumptions from here rather than re-deriving them. Every
declaration the gate honours is observable in this output; if a consumer can ignore a
config key with no signal, that is a defect in this module.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .config import (
    _OPEN_DICT,
    CONFIG_DEFAULTS,
    CONFIG_SCHEMA,
    OPT_IN_LANGUAGE_DEFAULTS,
    PASSTHROUGH_PREFIX,
    REQUIREMENTS_FORMAT_DEFAULT,
    REQUIREMENTS_FORMATS_USING_ID_COLUMN,
    REQUIREMENTS_ID_COLUMN_DEFAULT,
    REQUIREMENTS_NAME_COLUMN_DEFAULT,
    REQUIREMENTS_OPTIONAL_FIELDS,
    REQUIREMENTS_REQUIRED_FIELDS,
    REQUIREMENTS_ROOT_KEY,
    get_impact,
    get_validate,
)
from .filters import toolchain_contract
from .tags import find_source_files

logger = logging.getLogger(__name__)

# Bump whenever the emitted shape or the meaning of any field changes. A consumer that
# pins doxygen-guard should compare this against the value it was written for, and
# re-check its assumptions whenever it moves.
#
# 2: `resolved` is generated from CONFIG_SCHEMA instead of a hand-picked list of five
#    keys, so it now carries every scalar validate.* declaration. `version_field` moved
#    under a `version_gate` object. Private underscore-prefixed keys are stripped from
#    `config`, making the emitted config valid as input.
# 3: absorbed into clew (`clew guard`). `opt_in_language_defaults` added: languages the
#    gate supports only when declared (Rust), with the defaults a declaration is completed
#    from. Absent from `config_defaults` because they are not in force until declared.
# 4: `files` carries `toolchain_config` / `toolchain_ignores`, the shared toolchain globs
#    the file set honours beside `exclude`, and the set drops binary files.
CONTRACT_VERSION = 4

_OPEN_NODE = "<any>"


## @brief Render a schema node as JSON-safe data.
#  @version 1.1
#  @req REQ-DDB-GUARD-015
#  @return Type name, "<any>" for open nodes, or a nested dict
def _encode_schema(node: Any) -> Any:
    if node is _OPEN_DICT:
        return _OPEN_NODE
    if isinstance(node, dict):
        return {k: _encode_schema(v) for k, v in node.items()}
    return node.__name__ if isinstance(node, type) else str(node)


## @brief Build the full config contract: schema, defaults, and catalog constants.
#  @version 1.1
#  @req REQ-DDB-GUARD-015
#  @return JSON-serializable contract description
def build_schema_contract() -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "passthrough_prefix": PASSTHROUGH_PREFIX,
        "config_schema": _encode_schema(CONFIG_SCHEMA),
        "config_defaults": CONFIG_DEFAULTS,
        "opt_in_language_defaults": OPT_IN_LANGUAGE_DEFAULTS,
        "requirements_catalog": {
            "root_key": REQUIREMENTS_ROOT_KEY,
            "format_default": REQUIREMENTS_FORMAT_DEFAULT,
            "id_column_default": REQUIREMENTS_ID_COLUMN_DEFAULT,
            "name_column_default": REQUIREMENTS_NAME_COLUMN_DEFAULT,
            "required_fields": list(REQUIREMENTS_REQUIRED_FIELDS),
            "optional_fields": list(REQUIREMENTS_OPTIONAL_FIELDS),
            "formats_using_id_column": list(REQUIREMENTS_FORMATS_USING_ID_COLUMN),
        },
    }


## @brief Describe the requirements catalog as actually resolved from config.
#  @version 1.0
#  @req REQ-DDB-GUARD-015
#  @return Resolved catalog settings, or a declared=False marker
def _effective_requirements(config: dict[str, Any]) -> dict[str, Any]:
    req_config = get_impact(config).get("requirements")
    if not req_config:
        return {"declared": False}
    return {
        "declared": True,
        "file": req_config.get("file"),
        "format": req_config.get("format", REQUIREMENTS_FORMAT_DEFAULT),
        "id_column": req_config.get("id_column", REQUIREMENTS_ID_COLUMN_DEFAULT),
        "name_column": req_config.get("name_column", REQUIREMENTS_NAME_COLUMN_DEFAULT),
    }


## @brief Strip private keys so the emitted config is valid as input.
#  @details Runtime-injected keys such as validate.version_gate._resolved are not in
#  CONFIG_SCHEMA, so echoing them made `config --effective` output that load_config
#  would reject — defeating the point of publishing it.
#  @version 1.1
#  @req REQ-DDB-GUARD-015
#  @return A copy of the mapping with underscore-prefixed keys removed, recursively
def _strip_private(node: Any) -> Any:
    if not isinstance(node, dict):
        return node
    return {k: _strip_private(v) for k, v in node.items() if not str(k).startswith("_")}


## @brief Build the effective-config contract for the config currently in force.
#  @details `resolved` is generated from CONFIG_SCHEMA rather than hand-picked, so it
#  cannot silently omit a declaration the gate honours. A hand-written list of five keys
#  left six honoured keys invisible to a consumer reading the obvious field.
#  @version 2.0
#  @req REQ-DDB-GUARD-015
#  @return JSON-serializable description of the merged config and what it resolved to
def build_effective_contract(config: dict[str, Any]) -> dict[str, Any]:
    validate = get_validate(config)
    resolved: dict[str, Any] = {"output_dir": config.get("output_dir")}
    for key, spec in CONFIG_SCHEMA["validate"].items():
        if spec is _OPEN_DICT or isinstance(spec, dict):
            continue
        resolved[key] = validate.get(key)
    resolved["req_pattern"] = validate.get("tags", {}).get("req", {}).get("pattern")
    resolved["version_gate"] = _strip_private(validate.get("version_gate", {}))
    resolved["requirements"] = _effective_requirements(config)
    return {
        "contract_version": CONTRACT_VERSION,
        "config": _strip_private(config),
        "resolved": resolved,
        "passthrough_sections": sorted(k for k in config if str(k).startswith(PASSTHROUGH_PREFIX)),
    }


## @brief Build the exact post-exclude file set the gate walks for the given roots.
#  @version 1.1
#  @req REQ-DDB-GUARD-015
#  @return JSON-serializable file set with the exclude patterns that produced it
def build_files_contract(source_dirs: list[str], config: dict[str, Any]) -> dict[str, Any]:
    exclude = get_validate(config).get("exclude", [])
    files: list[str] = []
    for source_dir in source_dirs:
        files.extend(str(p) for p in find_source_files(source_dir, config))
    unique = sorted(set(files))
    logger.info("Contract file set: %d file(s) across %d root(s)", len(unique), len(source_dirs))
    return {
        "contract_version": CONTRACT_VERSION,
        "source_dirs": list(source_dirs),
        "exclude": exclude,
        **toolchain_contract(),
        "files": unique,
        "count": len(unique),
    }


## @brief Serialize a contract payload as indented JSON.
#  @version 1.0
#  @utility
#  @return JSON text for the given payload
def render(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, default=str)
