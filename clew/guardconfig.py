# SPDX-License-Identifier: MIT
"""Read a target's `.doxygen-guard.yaml` ACROSS a doxygen-guard version skew.

gh#32. A target's guard config is written against whatever doxygen-guard release
THAT repo pins in its `.pre-commit-config.yaml`. We parse it with whatever release
THIS package pins. Those are independent decisions by independent repos and nothing
forces them to agree, so a config we cannot fully parse is the NORMAL case at scale,
not an authoring error.

`doxygen_guard.config.load_config` is a GATE's loader: one unrecognised key and the
whole document is refused (`ConfigError`). Observed on a real target — a config found
via gh#16 and then discarded over `validate.presence.skip_forward_declarations`, a
flag valid in the 1.2.9 the target gates with and absent from the schema we import.
Net effect was gh#16's own failure mode restored: the `@req` id pattern, the catalog
mapping and the entire `x-clew` passthrough silently back on built-in
defaults, for a repo that had declared all three.

So the INDEX reads permissively. We consume a SMALL, KNOWN set of keys
(`KEYS_WE_READ`); every other key in the document is doxygen-guard's business, and
losing ours over one of theirs is the wrong severity. The strict path remains
available (`strict=True`) and belongs to the GATE, which is where a
silently-ignored typo in your OWN config is worth failing over — the same split
this project already draws between gate scope and index scope.

Permissiveness is SELF-CHECKED rather than trusted: the unknown keys are pruned and
the document is re-validated, so a document that is still invalid for some other
reason is refused exactly as before. The unknown-key error text is upstream's, which
makes parsing it brittle by nature; the re-validation is what turns that brittleness
into a safe refusal instead of a wrong parse.

@brief Version-skew-tolerant loading of a target's doxygen-guard config.
@version 1
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ._common import logger
from .precommit import PRECOMMIT_CONFIG_NAME, pinned_guard_rev

## The keys clew itself reads out of a guard config. Named in the skew report
## so an owner can see that the values we wanted survived — the report exists to say
## "your declaration WAS honoured", which a bare unknown-key error cannot.
KEYS_WE_READ = (
    "validate.tags.req.pattern",
    "impact.requirements.*",
    "validate.exclude",
    "x-clew (this tool's whole declaration passthrough)",
)

## Upstream's own wording for a key its schema does not know. The ONE channel through
## which "unknown key" is distinguishable from "malformed document", because
## `ConfigError.problems` carries formatted strings rather than structured keys.
_UNKNOWN_KEY_PREFIX = "Unknown config key: "

## Upstream appends " — did you mean 'x'?" to a near-miss key. Split on it so the
## suggestion never lands inside the key path we prune.
_SUGGESTION_MARKER = " — did you mean"

## How far above the config file to look for the target's `.pre-commit-config.yaml`
## when the caller did not supply a repo root. A guard config lives at the root or in
## a conventional subdirectory (`conf/`, `.config/`), so two levels is generous.
_REV_SEARCH_DEPTH = 3


## @brief A guard config read across a possible version skew, with what was skipped.
## @version 1
@dataclass(frozen=True)
class GuardConfigRead:
    """The merged config (empty when nothing usable was read), the file it came
    from, the keys the imported doxygen-guard did not recognise, any problem that
    was NOT an unknown key, and the human-readable skew report.

    `skew` is the load-bearing field. Falling back to built-in defaults for a
    declaration that EXISTS is this project's most-repeated defect, and the version
    the target pins versus the version we import is the diagnosis its owner can act
    on — where "unknown config key" alone reads as their mistake.

    @brief Result of a permissive guard-config read.
    @version 1
    """

    config: dict[str, Any]
    path: Path
    unknown_keys: tuple[str, ...] = ()
    rejected: tuple[str, ...] = ()
    skew: str | None = None
    ## Every key we pruned to make the document parse. Kept separate from
    ## `unknown_keys` only in principle — they are equal today — so a future
    ## salvage rule that drops something else cannot report it as unknown.
    pruned_keys: tuple[str, ...] = field(default=())

    ## @brief Whether the read produced a config to declare from.
    ## @return True when at least one key was parsed.
    ## @version 1
    ## @req REQ-DDB-CONFIG-001
    def usable(self) -> bool:
        """@brief Whether any config was recovered from the file."""
        return bool(self.config)


## @brief Import doxygen_guard.config, or None when it is unavailable.
## @param path Config path, named in the warning.
## @return The module, or None.
## @version 2
## @dg_internal
def _import_guard_config(path: Path) -> Any | None:
    """@brief Import the upstream config module, warning rather than raising."""
    try:
        from doxygen_guard import config as dg_config
    except Exception as exc:
        logger.warning("guard config: cannot import doxygen_guard.config (%s) — %s", exc, path)
        return None
    return dg_config


## @brief The doxygen-guard release THIS process imports.
## @return Version string, or "unknown" when the package does not report one.
## @version 2
## @req REQ-DDB-CONFIG-001
def imported_guard_version() -> str:
    """Read from the installed distribution rather than hardcoded, for the same
    reason the passthrough prefix is: a version this file states is a version this
    file will one day be wrong about.

    @brief The doxygen-guard version in this process.
    @return Version string or "unknown".
    @version 2
    """
    try:
        import doxygen_guard
    except Exception:
        return "unknown"
    return str(getattr(doxygen_guard, "__version__", "unknown"))


## @brief Parse a YAML mapping, degrading to {} rather than raising.
## @param path File to read.
## @return The mapping, or {} when unreadable or not a mapping.
## @version 1
## @dg_internal
def _read_raw_mapping(path: Path) -> dict[str, Any]:
    """@brief Read the guard config's raw YAML, tolerating every failure."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("guard config: could not read %s (%s)", path, exc)
        return {}
    return data if isinstance(data, dict) else {}


## @brief Run upstream's schema validation, when the imported module offers it.
## @param dg_config The imported doxygen_guard.config module.
## @param raw Raw parsed config mapping.
## @param path Config path, named in the warning when validation itself fails.
## @return Problem strings; () when the validator is unavailable.
## @version 2
## @dg_internal
def _problems(dg_config: Any, raw: dict[str, Any], path: Path) -> tuple[str, ...]:
    """A doxygen-guard old enough not to export `validate_config_schema` reports no
    problems here and is then handled by the strict load, which still raises for a
    bad document. Absence of the validator must not become absence of validation.

    @brief Validate a raw config against upstream's schema.
    @return Tuple of problem strings.
    @version 2
    """
    validator = getattr(dg_config, "validate_config_schema", None)
    if validator is None or not raw:
        return ()
    try:
        return tuple(str(problem) for problem in validator(raw))
    except Exception as exc:
        logger.warning("guard config: schema validation of %s failed (%s)", path, exc)
        return ()


## @brief Split validation problems into unknown-key paths and everything else.
## @param problems Problem strings from upstream's validator.
## @return (unknown key paths, other problems).
## @version 1
## @dg_internal
def _split_problems(problems: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """An unknown key is a SKEW symptom and is salvageable; a type mismatch is a
    statement about a value, which may well be a value we read, so it is not.

    @brief Separate salvageable unknown keys from real problems.
    @return (unknown, other).
    @version 1
    """
    unknown: list[str] = []
    other: list[str] = []
    for problem in problems:
        if problem.startswith(_UNKNOWN_KEY_PREFIX):
            unknown.append(problem[len(_UNKNOWN_KEY_PREFIX) :].split(_SUGGESTION_MARKER)[0].strip())
        else:
            other.append(problem)
    return tuple(unknown), tuple(other)


## @brief Copy a config with the named dotted key paths removed.
## @param raw Raw parsed config mapping.
## @param keys Dotted key paths to drop.
## @return A deep copy without those keys.
## @version 1
## @dg_internal
def _pruned(raw: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    """Drops the key only, never its siblings or its parent: a target that declares
    one flag we do not know inside `validate.presence` keeps the rest of
    `validate.presence`.

    @brief Remove unknown keys from a config copy.
    @return The pruned copy.
    @version 1
    """
    pruned = copy.deepcopy(raw)
    for dotted in keys:
        parts = dotted.split(".")
        node: Any = pruned
        for part in parts[:-1]:
            node = node.get(part) if isinstance(node, dict) else None
        if isinstance(node, dict):
            node.pop(parts[-1], None)
    return pruned


## @brief Merge a pruned config over upstream's built-in defaults.
## @param dg_config The imported doxygen_guard.config module.
## @param pruned The pruned user config.
## @return The merged config, or the pruned config when defaults are unavailable.
## @version 1
## @dg_internal
def _merged(dg_config: Any, pruned: dict[str, Any]) -> dict[str, Any]:
    """Reproduces what `load_config` returns on a clean document — declared values
    over `CONFIG_DEFAULTS` — because a caller reading `impact.requirements` must see
    the same shape whether or not the document happened to be skewed.

    Both pieces are read with `getattr`, so a release that renames either degrades to
    the declared values alone rather than to nothing. That is a narrower loss than
    the whole document, which is the point of this module.

    @brief Apply upstream defaults under a pruned config.
    @return The merged mapping.
    @version 1
    """
    defaults = getattr(dg_config, "CONFIG_DEFAULTS", None)
    merge = getattr(dg_config, "deep_merge", None)
    if not isinstance(defaults, dict) or merge is None:
        logger.info("guard config: upstream defaults unavailable — using declared keys only")
        return pruned
    return dict(merge(copy.deepcopy(defaults), pruned))


## @brief The doxygen-guard `rev:` the target pins, phrased for the skew report.
## @param path The guard config that was read.
## @param repo_root Repo root when the caller knows it, else None.
## @return A clause naming the pinned rev, or saying none could be read.
## @version 1
## @dg_internal
def _pinned_clause(path: Path, repo_root: Path | str | None) -> str:
    """Searches upward from the config when no repo root is supplied, because the
    two loaders that read a guard config do not both know one, and a skew report
    missing the target's own version is half a diagnosis.

    @brief Describe the doxygen-guard version the target gates with.
    @return A human-readable clause.
    @version 1
    """
    candidates = [Path(repo_root)] if repo_root is not None else []
    parent = path.parent
    candidates += [parent, *list(parent.parents)[: _REV_SEARCH_DEPTH - 1]]
    for candidate in candidates:
        rev = pinned_guard_rev(candidate)
        if rev:
            return f"rev: {rev} (in {candidate / PRECOMMIT_CONFIG_NAME})"
    return "no doxygen-guard rev this build could read"


## @brief Compose the version-skew report naming both versions and the keys.
## @param path The guard config that was read.
## @param repo_root Repo root when known, else None.
## @param unknown The key paths the imported doxygen-guard did not recognise.
## @param refused True when strict mode discarded the document.
## @return The report text.
## @version 1
## @req REQ-DDB-CONFIG-001
def skew_report(
    path: Path, repo_root: Path | str | None, unknown: tuple[str, ...], refused: bool = False
) -> str:
    """NAMES BOTH VERSIONS AND THE KEY. "Unknown config key" alone reads as the
    target author's mistake, when in fact their key is valid for the release their
    gate runs and unknown to the release this index imports — a fact about two
    independent pins, which only a message stating both can convey.

    @brief Describe a doxygen-guard version skew and what was done about it.
    @return The report text.
    @version 1
    """
    outcome = (
        "REFUSED in strict mode — nothing was read from the file"
        if refused
        else "Parsed PERMISSIVELY: every key clew reads ("
        + "; ".join(KEYS_WE_READ)
        + ") was taken from the file, and the unrecognised keys were ignored because "
        "they are doxygen-guard's business, not the index's"
    )
    return (
        f"guard config: {path} was written against a DIFFERENT doxygen-guard release — "
        f"this is version SKEW, not an authoring error. The target pins "
        f"{_pinned_clause(path, repo_root)}; this build imports doxygen-guard "
        f"{imported_guard_version()}, whose schema does not know "
        f"{len(unknown)} key(s): {', '.join(unknown)}. {outcome}."
    )


## @brief Load a config through upstream's strict loader, tolerating refusal.
## @param dg_config The imported doxygen_guard.config module.
## @param path Config path to load.
## @return A GuardConfigRead; its config is empty when upstream refused.
## @version 2
## @dg_internal
def _strict_load(dg_config: Any, path: Path) -> GuardConfigRead:
    """`SystemExit` is caught alongside `Exception` deliberately: `load_config` USED
    to `sys.exit(1)` on a bad config, which sailed through a bare `except Exception`
    and killed a completed build at exit 1 with another tool's message. Fixed
    upstream in 1.3.1 (it raises `ConfigError` now) and kept here because the arm
    costs a line and documents a failure that was expensive to find.

    @brief Load a guard config strictly, degrading to {} on refusal.
    @return The read result.
    @version 2
    """
    try:
        loaded = dg_config.load_config(path)
    except (Exception, SystemExit) as exc:
        _warn_unusable(path, exc)
        return GuardConfigRead(config={}, path=path, rejected=(str(exc),))
    return GuardConfigRead(config=loaded if isinstance(loaded, dict) else {}, path=path)


## @brief Warn that a guard config could not be used, distinguishing the cause.
## @param path The config that could not be used.
## @param exc What went wrong.
## @version 1
## @dg_internal
def _warn_unusable(path: Path, exc: BaseException) -> None:
    """The two causes read differently because they ARE different. A `SystemExit`
    means doxygen-guard PARSED the file and REFUSED it, so the owner has a real
    config error and a command that will name it; anything else means we could not
    load the file at all, which is our problem or the filesystem's.

    WARNING in both cases rather than swallowed, because falling back to built-in
    defaults without saying so is exactly the outcome the no-hardcoding mandate
    exists to prevent.

    @brief Warn about an unusable guard config, naming the likely fix.
    @version 1
    """
    if isinstance(exc, SystemExit):
        logger.warning(
            "guard config: %s is INVALID — doxygen-guard rejected it (exit %s). Continuing "
            "with built-in defaults; run 'doxygen-guard validate' against that file to see "
            "which key it refuses.",
            path,
            exc.code,
        )
        return
    logger.warning("guard config: could not load %s (%s) — using built-in defaults", path, exc)


## @brief Read a guard config, tolerating keys from another doxygen-guard release.
## @param path Path to the target's .doxygen-guard.yaml.
## @param repo_root Repo root, used to name the `rev:` the target pins; may be None.
## @param strict Refuse the whole document on any unknown key (the GATE's severity).
## @return A GuardConfigRead; `config` is empty only when nothing could be salvaged.
## @version 1
## @req REQ-DDB-CONFIG-001
def read_guard_config(
    path: Path | str, repo_root: Path | str | None = None, *, strict: bool = False
) -> GuardConfigRead:
    """THE single guard-config load for this package. Both consumers — the `@req` id
    pattern / catalog mapping in `requirements.py` and the `x-clew`
    passthrough in `declaration.py` — go through here, so a skew is diagnosed once
    and cannot be tolerated by one reader and fatal to the other.

    @brief Load a target's guard config across a version skew.
    @return The read result.
    @version 1
    """
    config_path = Path(path)
    dg_config = _import_guard_config(config_path)
    if dg_config is None:
        return GuardConfigRead(config={}, path=config_path)
    raw = _read_raw_mapping(config_path)
    problems = _problems(dg_config, raw, config_path)
    if not problems:
        return _strict_load(dg_config, config_path)
    return _salvage(dg_config, config_path, raw, problems, repo_root, strict=strict)


## @brief Refuse a document, reporting a skew as a skew when that is what it is.
## @param path Config path being read.
## @param repo_root Repo root when known, else None.
## @param unknown Unknown key paths, if any.
## @param other Problems that are not unknown keys.
## @param strict Whether the caller asked for the gate's severity.
## @return A GuardConfigRead with an empty config.
## @version 2
## @dg_internal
def _refuse(
    path: Path,
    repo_root: Path | str | None,
    unknown: tuple[str, ...],
    other: tuple[str, ...],
    *,
    strict: bool,
) -> GuardConfigRead:
    """Two refusals, two verdicts, and THE REASON FOR THIS ONE'S REFUSAL DECIDES
    WHICH. A document refused over unknown keys is a SKEW and says so, because the
    owner's next question is which release differs. A document refused over a type
    mismatch is the author's own config error and must not be dressed up as somebody
    else's version pin — even when it ALSO carries an unrecognised key, which is the
    case that caught this function's first version reporting a strict-mode skew
    refusal for a document nobody had asked to read strictly.

    The unrecognised keys are still named in that case, in lower case and explicitly
    NOT as the reason: `SKEW` in upper case is this module's verdict marker, and a
    consumer grepping for it must not find one where the refusal was a type error.

    @brief Report a refusal at the right severity, naming the real reason.
    @return The empty read result.
    @version 2
    """
    if not other:
        report = skew_report(path, repo_root, unknown, refused=strict)
        logger.warning("%s", report)
        return GuardConfigRead(config={}, path=path, unknown_keys=unknown, skew=report)
    aside = (
        f" It also declares {len(unknown)} key(s) this release does not know "
        f"({', '.join(unknown)}), which is version skew and is NOT why it was refused."
        if unknown
        else ""
    )
    logger.warning(
        "guard config: %s is INVALID for doxygen-guard %s — %s. Continuing with built-in "
        "defaults.%s",
        path,
        imported_guard_version(),
        "; ".join(other),
        aside,
    )
    return GuardConfigRead(config={}, path=path, unknown_keys=unknown, rejected=other)


## @brief Recover the keys we read from a document upstream's schema refuses.
## @param dg_config The imported doxygen_guard.config module.
## @param path Config path being read.
## @param raw Raw parsed config mapping.
## @param problems Problems upstream's validator reported.
## @param repo_root Repo root when known, else None.
## @param strict Refuse rather than salvage.
## @return A GuardConfigRead carrying the skew report either way.
## @version 1
## @dg_internal
def _salvage(
    dg_config: Any,
    path: Path,
    raw: dict[str, Any],
    problems: tuple[str, ...],
    repo_root: Path | str | None,
    *,
    strict: bool,
) -> GuardConfigRead:
    """Salvage is attempted ONLY when every problem is an unknown key, and it is
    SELF-CHECKED: the pruned document is re-validated, so a parse of upstream's
    error text that got a key path wrong ends in the same refusal as before rather
    than in a config missing something we needed. A type mismatch is never salvaged
    — it is a statement about a value, and the value may be one we read.

    @brief Prune unknown keys and re-validate, or refuse.
    @return The read result.
    @version 1
    """
    unknown, other = _split_problems(problems)
    if strict or other or not unknown:
        return _refuse(path, repo_root, unknown, other, strict=strict)
    pruned = _pruned(raw, unknown)
    remaining = _problems(dg_config, pruned, path)
    if remaining:
        logger.warning(
            "guard config: %s still fails validation after dropping %s (%s) — built-in "
            "defaults. This is a salvage failure, not a clean skew.",
            path,
            ", ".join(unknown),
            "; ".join(remaining),
        )
        return GuardConfigRead(config={}, path=path, unknown_keys=unknown, rejected=remaining)
    report = skew_report(path, repo_root, unknown)
    logger.warning("%s", report)
    return GuardConfigRead(
        config=_merged(dg_config, pruned),
        path=path,
        unknown_keys=unknown,
        skew=report,
        pruned_keys=unknown,
    )
