# SPDX-License-Identifier: MIT
"""THREE AXES OF STALENESS, INTERPRETED — the tool describing its own currency.

`db_status` already measured freshness and already published the diagnosis for
two of these axes as raw fields that nothing read out loud. This module turns
those fields into a sentence naming the ACTION that clears them, because the
three axes are cleared by three DIFFERENT actions and a bare `stale: true` does
not say which.

  * `data`   — the database is older than the source. Cleared by a rebuild.
                `db_status` reports it correctly today as `source_changed_files`.
  * `code`   — the running server process imported its modules at launch, so a
                committed fix is not in its answers. Cleared ONLY by restarting
                the client. `status` reported `stale: false` here — truthfully,
                about the `data` axis — while serving old logic, which is why this
                is the actively misleading one (gh#29).
  * `schema` — `build_version` versus `expected_build_version`. When the index is
                NEWER than the server, `stale: true` is UNRESOLVABLE by any action
                the consumer can take: rebuilding re-stamps the same newer version
                and the flag stays up. Observed live at 23 versus 17. The two
                integers were already in the payload; nothing interpreted them.

PRECISION ABOUT THE `code` AXIS MATTERS AS MUCH AS RAISING IT. Query tools open
the database per call, so DATA is read live and IS current — a session confirmed
newly-added symbols appearing immediately while the version skew showed. What is
stale is the process's LOGIC and its module-level constants. Saying "the server is
stale" without that qualification trades one wrong conclusion for another, and the
messages below are worded to keep the distinction.

AND THAT PRECISION WAS HALF WRONG, WHICH IS WORSE THAN VAGUE (gh#348). "The DATA is
not affected" is TRUE FOR READS and FALSE FOR WRITES: a stale process reads live data
and writes dead logic. Measured by calling the tool — a build-30 process rebuilt a
build-32 index AT 30, the `external` stage vanished from the stage list,
`external_files`/`unresolved_files` left `coverage`, and `status` afterwards reported
`stale: false, build_version: 30`, i.e. perfectly healthy, having just destroyed a
layer. The notice that should have stopped that told the reader not to worry.

So the read exemption and the write refusal now travel together in one sentence, and
`stale_code_refusal` is what a write path calls BEFORE touching an index. Refusing is
cheap: one client reconnect restored the dropped layer.

THE AXIS NAMES ARE NOT IN `vocabulary.py`, deliberately. That module is the single
source for the SCHEMA's enumerated columns and the DDL CHECK clauses generated from
them; these three tokens never reach a table. Putting them there would imply a
column somewhere holds them, and would put a payload-shape decision behind the
schema's change control.

@brief Interpret the data / code / schema staleness axes into actionable messages.
@version 2
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path

from ..signature import CLEW_BUILD_VERSION

## The three axes, as tokens a consumer can branch on. A message is prose and may be
## reworded; the axis is the stable field.
AXIS_DATA = "data"
AXIS_CODE = "code"
AXIS_SCHEMA = "schema"

## THE TWO HALVES OF THE `code` AXIS, WRITTEN ONCE. They are constants rather than inline
## prose because the notice and the write refusal must not be able to drift apart: the
## whole defect was a message that stated one half and was pinned by a test for that half.
_READ_EXEMPTION = (
    "READS are not affected — query tools open the database per call and read it live, so "
    "the data in this reply is current."
)
_WRITE_HAZARD = (
    "WRITES ARE AFFECTED and a build through this process is refused: it would run old "
    "pipeline logic and re-stamp the index with it, which can silently DROP WHOLE LAYERS "
    "and then report the result as healthy."
)

## Only `.py` is fingerprinted. A `.pyc` is regenerated as a side effect of importing
## the very code we are trying to identify, so hashing bytecode would make the
## fingerprint change because it was read — and the house test procedure purges
## `__pycache__` between control runs, which would move it again for no source change.
_SOURCE_GLOB = "*.py"

## Length of the published fingerprint. It exists to be COMPARED, never inverted, so
## twelve hex characters is ample and keeps the block small against the response budget.
_FINGERPRINT_CHARS = 12


## @brief The installed package's source directory.
## @return Path to the `clew` package root.
## @version 1
## @dg_internal
def package_source_root() -> Path:
    """The directory the RUNNING process imported from, whatever install shape put it
    there. Under `pipx install --editable` that is the working tree, which is the whole
    reason the `code` axis can drift at all; under a snapshot install it is a
    site-packages copy that never changes, and the axis then correctly stays silent.

    @brief Locate the imported package's source directory.
    @return The package root.
    @version 1
    """
    return Path(__file__).resolve().parent.parent


## @brief Fingerprint the package source's identity on disk.
## @param root Package root to fingerprint (defaults to the imported one).
## @return Short hex digest, or "" when the tree cannot be read or holds no source.
## @version 3
## @req REQ-DDB-MCP-004
def source_fingerprint(root: Path | None = None) -> str:
    """Hashes RELATIVE path and file CONTENT for every `.py` under the package — never
    mtime, and never an absolute path.

    IT HASHED MTIME UNTIL A LIVE MEASUREMENT KILLED THAT. The reasoning was that "has the
    tree moved since this process started" is answered by a stat, and reading every byte
    would cost real time on a surface called once per reply. The cost claim was wrong by
    measurement — 90 files and 2.6 MB hash in 4.0 ms against 2.2 ms for stat-only, so
    content costs 1.8 ms — and the correctness cost was much larger than 1.8 ms.

    THE CODE AXIS IS A HARD REFUSAL: `matches_source` false blocks the automatic
    query-time refresh AND refuses an explicit build, and no rebuild clears it — only
    restarting the client does. An mtime key trips on `git checkout`, a branch switch,
    `git stash pop`, rsync and plain `touch`, every one of which leaves byte-identical
    content. Observed here: reverting ONE file with `git checkout` moved the fingerprint,
    the axis fired on the next two query replies, and that is what stopped the
    query-time auto-refresh from ever engaging in this repository. A safety gate that
    fires on ordinary git operations disables the feature it guards.

    The sibling `IndexCache` already states this codebase's rule — mtime+size is a
    PREFILTER and the sha256 of the bytes is the AUTHORITY, so a touch with no edit and a
    checkout that restores identical content both stay HITS. This now follows it. No
    prefilter here, because there is nothing to compare a prefilter against: the result is
    a single digest over the whole tree, not a per-file cache lookup.

    Not absolute paths because anything reachable over MCP is published, and stamping a
    machine's directory layout into a payload is the disclosure that forced the
    build-version-9 bump. A digest over relative paths compares exactly as well and
    discloses nothing.

    Returns "" — meaning "cannot tell", never "unchanged" — when the tree is unreadable,
    and `notices` treats an empty fingerprint on either side as no evidence rather than
    as agreement. A missing measurement must not read as a clean bill of health.

    THE EMPTY-TREE CASE IS CHECKED SEPARATELY AND A CONTROL CAUGHT IT. `Path.rglob`
    SWALLOWS a missing or unreadable directory and yields nothing rather than raising, so
    the `except OSError` alone let a tree that could not be read hash to the digest of
    ZERO FILES — a perfectly stable, entirely fabricated fingerprint. Worse than useless:
    two unreadable trees produce the SAME digest, so `matches_source` would compare equal
    and report the process as healthy on no evidence at all. That is this repo's standing
    lesson exactly — "no rows" is a claim about the detector — reached by a detector that
    could not look. A package with zero `.py` files is not a package.

    @brief Digest the package source tree's CONTENT identity.
    @return Short hex digest, or "" when unreadable or empty.
    @version 3
    """
    base = root if root is not None else package_source_root()
    digest = hashlib.sha256()
    seen = 0
    try:
        for path in sorted(base.rglob(_SOURCE_GLOB)):
            rel = path.relative_to(base).as_posix()
            digest.update(f"{rel}\0".encode())
            digest.update(hashlib.sha256(path.read_bytes()).digest())
            seen += 1
    except OSError:
        return ""
    return digest.hexdigest()[:_FINGERPRINT_CHARS] if seen else ""


## The fingerprint AS THIS PROCESS STARTED. Computed at import, which for the server is
## launch — the same moment the modules whose logic we are describing were bound. A
## LATER-imported submodule (the pipeline imports several lazily) may therefore be newer
## than this fingerprint claims, so the message below says the loaded modules MAY predate
## the tree rather than asserting which ones do.
PROCESS_SOURCE_FINGERPRINT = source_fingerprint()


## The DISTRIBUTION name, which is not the import name: the package imports as `clew` and
## ships as `clew-trace`. Deriving it instead — `packages_distributions()["clew"]` — resolves
## to None under an editable install, so the derivation fails in exactly the environment every
## developer runs. A literal bound by a test is the version that works in both.
_DISTRIBUTION = "clew-trace"


## @brief The package version this process is running.
## @return Version string, or "unknown" when the metadata cannot be read.
## @version 3
## @dg_internal
def package_version() -> str:
    """Read from installed metadata, so the version cannot drift from `pyproject.toml`.
    "unknown" rather than a raise: this is called on the way out of replies that already
    succeeded.

    THE DISTRIBUTION NAME IS THE PART THAT DRIFTED. This asked for `version("clew")` — the
    import name — and every `index(action='status')` reply since the rename reported
    `package_version: "unknown"`, which is the first field a consumer pastes into a bug
    report. Nothing caught it because the fallback is silent by design: the failure of a
    version lookup renders as a plausible-looking value, not as an error.

    @brief Read the installed package version.
    @return Version string or "unknown".
    @version 3
    """
    try:
        from importlib.metadata import (
            version,
        )

        return version(_DISTRIBUTION)
    except Exception:
        return "unknown"


## @brief The code identity the process is actually running.
## @return {package_version, process_fingerprint, source_fingerprint, matches_source}.
## @version 1
## @req REQ-DDB-MCP-004
def code_identity() -> dict[str, object]:
    """The `code` axis as data, so a consumer can see the comparison and not only the
    verdict — gh#29's point was that a payload should say what produced it.

    `matches_source` is False ONLY on positive evidence of disagreement: two non-empty
    fingerprints that differ. An unreadable tree leaves it True, because "cannot tell"
    must not manufacture a warning that sends someone restarting a client for no reason.
    The asymmetry is deliberate and is the opposite of the one `source_fingerprint`
    makes, for the same reason: absent evidence is not evidence.

    @brief Report the running code's identity against the source tree.
    @return Code identity mapping.
    @version 1
    """
    current = source_fingerprint()
    both_known = bool(current) and bool(PROCESS_SOURCE_FINGERPRINT)
    return {
        "package_version": package_version(),
        "process_fingerprint": PROCESS_SOURCE_FINGERPRINT,
        "source_fingerprint": current,
        "matches_source": (not both_known) or current == PROCESS_SOURCE_FINGERPRINT,
    }


## @brief Spell a millisecond count the way a reader would say it.
## @param raw The stored `duration_ms` value, as the string it is persisted as.
## @return A phrase like "8 min 27 s", or the raw milliseconds when it is not a number.
## @version 1
## @dg_internal
def _humanise_ms(raw: str) -> str:
    """KEEPS MILLISECONDS BELOW TEN SECONDS, because at that scale they are the informative
    unit and rounding a 2.7 s refresh to "3 s" throws away the thing that makes it obviously
    cheap. Above it, minutes are what a reader compares against their own patience.

    FALLS BACK TO THE RAW STRING rather than raising or guessing. `duration_ms` is persisted as
    text and an index written by a future version could hold something else; a notice that
    printed a traceback, or invented a number, would be worse than one that quotes what it
    found.

    @brief Render a stored duration in readable units.
    @return The spelled duration.
    @version 1
    """
    try:
        ms = int(float(raw))
    except (TypeError, ValueError, OverflowError):
        ## `OverflowError` IS NOT THEORETICAL and is not a subclass of the other two: `float`
        ## accepts "1e9999" happily and returns `inf`, which `int()` then refuses. Caught by the
        ## test that feeds this function junk — without it a staleness notice raises and takes
        ## down a query that was otherwise answerable, which is the opposite of what a notice is
        ## for.
        return f"{raw} ms"
    if ms < 10_000:
        return f"{ms} ms"
    seconds = round(ms / 1000)
    if seconds < 60:
        return f"{seconds} s"
    minutes, rest = divmod(seconds, 60)
    ## Both parts, always, above a minute: "8 min" alone loses the half-minute that decides
    ## whether a refresh fits inside somebody's threshold.
    return f"{minutes} min {rest} s"


## @brief Human phrasing for what a refresh of this target last cost.
## @param refresh The persisted `refresh.*` section, or None.
## @return A clause naming the measured cost, or one saying it has not been measured.
## @version 3
## @dg_internal
def _cost_clause(refresh: Mapping[str, str] | None) -> str:
    """GROUNDED IN THIS TARGET'S OWN HISTORY, not a constant (gh#9). An agent that
    cannot measure the correction must estimate it, and it estimates badly — that is
    the whole of Q8, the worst result in the acceptance matrix.

    Says so plainly when there is no history, rather than falling back to a
    representative number. A fabricated estimate presented as a measurement is the
    failure this repo has recorded most often.

    IN UNITS A READER ACTS ON. This said "506974 ms", which is eight and a half minutes and
    does not scan like it — the tool recommended a refresh and then priced it in a unit that
    reads as small. That exact number sat in a real target's metadata while the operator's
    stated bar was ten minutes, and nobody noticed the two were in tension.

    @brief Phrase the measured cost-to-refresh.
    @return Cost clause.
    @version 3
    """
    duration = (refresh or {}).get("duration_ms")
    if not duration:
        return "no refresh of this target has been timed yet, so the cost is unmeasured"
    spelled = _humanise_ms(duration)
    ## NOT "file(s)" (#470). This number counts (file, stage) PAYLOADS recomputed, and there are
    ## ~10 stages, so it is normally several times the changed-file count. Printed as files it
    ## landed in the same notice as "18 source file(s) have changed" and read as a broken counter
    ## — or worse, as the refresh doing four times the necessary work. `files_reprocessed` is
    ## still read so an index built before the rename keeps reporting its cost.
    payloads = (refresh or {}).get("payloads_recomputed") or (refresh or {}).get(
        "files_reprocessed"
    )
    work = f" recomputing {payloads} cached stage payload(s)" if payloads else ""
    return f"the last refresh of this target measured {spelled}{work}"


## @brief The data-axis notice, when the sources have drifted.
## @param status A `db_status` payload.
## @return One notice, or None when the database describes the current sources.
## @version 2
## @dg_internal
def _data_notice(status: Mapping[str, object]) -> dict[str, str] | None:
    """Fires on `source_changed_files`, which `db_status` has measured correctly all
    along — this only says what to DO about it, with the cost attached so the decision
    is informed rather than guessed.

    @brief Build the data-axis notice.
    @return The notice, or None.
    @version 2
    """
    changed = status.get("source_changed_files") or 0
    if not isinstance(changed, int) or changed <= 0:
        return None
    newest = status.get("newest_changed_source")
    where = f" (most recently {newest})" if newest else ""
    refresh = status.get("refresh")
    cost = _cost_clause(refresh if isinstance(refresh, Mapping) else None)
    return {
        "axis": AXIS_DATA,
        "message": (
            f"{changed} indexed source file(s) have changed since this index was built"
            f"{where}, so an answer may describe code that no longer exists. Call "
            f"index(action='refresh') to correct it — {cost}."
        ),
    }


## @brief The schema-axis notice, when the stamped and expected versions disagree.
## @param status A `db_status` payload.
## @return One notice, or None when the versions agree.
## @version 2
## @dg_internal
def _schema_notice(status: Mapping[str, object]) -> dict[str, str] | None:
    """THE DIRECTION DECIDES THE ADVICE, and getting it backwards is worse than
    silence. `expected < actual` means the SERVER predates the INDEX: rebuilding
    re-stamps the same newer version, so `stale: true` cannot be cleared by any action
    the consumer takes, and telling them to rebuild sends them round a loop that cannot
    terminate. Observed live at 23 versus 17.

    The opposite direction is the ordinary one and a rebuild really does fix it.

    @brief Build the schema-axis notice.
    @return The notice, or None.
    @version 2
    """
    stamped = status.get("build_version")
    if not isinstance(stamped, int) or stamped == CLEW_BUILD_VERSION:
        return None
    if stamped > CLEW_BUILD_VERSION:
        message = (
            f"This index was built by pipeline version {stamped} and this server process "
            f"expects {CLEW_BUILD_VERSION}, so THE SERVER PREDATES THE INDEX. "
            "REBUILDING CANNOT CLEAR the `stale` flag — a rebuild re-stamps the same "
            "newer version. Restart the MCP client so it loads the current code."
        )
    else:
        message = (
            f"This index was built by pipeline version {stamped} and this server expects "
            f"{CLEW_BUILD_VERSION}, so the index predates the server and may be "
            "missing whole layers rather than merely being out of date. Call "
            "index(action='refresh', force=True) to rebuild it."
        )
    return {"axis": AXIS_SCHEMA, "message": message}


## @brief The code-axis notice, when the source moved under a running process.
## @param code A `code_identity` payload.
## @return One notice, or None when the process matches the source tree.
## @version 2
## @dg_internal
def _code_notice(code: Mapping[str, object]) -> dict[str, str] | None:
    """THE AXIS THAT HAD NO SIGNAL AT ALL, and whose available signal pointed the other
    way (gh#29). It has now cost this loop three separate debugging sessions: a fix
    lands, `status` reports `stale: false`, and the query returns the pre-fix payload
    byte-for-byte, so an agent cannot distinguish "my fix did not work" from "the server
    has not loaded my fix".

    The message is careful in THREE directions now. It must not let anyone conclude their
    fix failed; it must not let anyone conclude the DATA is stale, because the query tools
    open the database per call and are current, which was measured; and — gh#348 — it must
    not let anyone conclude a REBUILD is safe, because it is not. The first two were here
    already. The third is the one whose absence cost a layer: the message said the data was
    unaffected, full stop, and was read as reassurance by someone about to write.

    Only logic and module-level constants are old, and only a client restart replaces them
    — this deliberately does not hot-reload modules, which is a bad idea and was not asked
    for.

    @brief Build the code-axis notice.
    @return The notice, or None.
    @version 2
    """
    if code.get("matches_source"):
        return None
    return {
        "axis": AXIS_CODE,
        "message": (
            f"This server process loaded clew {code.get('package_version')} at "
            f"launch and the package source has changed since "
            f"(fingerprint {code.get('process_fingerprint')} on disk now "
            f"{code.get('source_fingerprint')}), so its LOGIC and module-level constants "
            f"may predate the working tree. {_READ_EXEMPTION} {_WRITE_HAZARD} A rebuild "
            "cannot fix this: restart the MCP client to load the current code."
        ),
    }


## @brief Tag a deliberate refusal so a truncating client still shows the distinction.
## @param exc The exception a tool method raised on purpose.
## @return The exception's message, prefixed once with "REFUSED:".
## @version 2
## @req REQ-DDB-MCP-004
def refused(exc: Exception) -> str:
    """FIELD-REPORTED: a caller's client showed only the tool name for both an EXPECTED
    refusal (a mistyped action, an ambiguous target) and an actual crash. THE FIRST
    HYPOTHESIS — a client rendering or truncating aggressively — was wrong, and only a
    real second environment proved it: CI (mcp==2.1.1) reproduced the bare "Error
    executing tool X" this function exists to prevent, on the very tests written to
    guard it, while a developer venv (mcp==2.0.0) had the fix working the whole time.
    `Tool.run()`, since 2.1, preserves an exception's text ONLY when it is already the
    SDK's own `ToolError`/`ResourceError`/`MCPError` — anything else is an unexpected
    CRASH by definition, and its text is discarded before a client ever sees it. So the
    caller has to raise the RESULT of this function as `_sdk.ToolError`, not as
    `type(exc)`; tagging a `RuntimeError`'s message and re-raising the same type was a
    fix that only worked on the OLDER SDK behaviour. `stale_code_refusal` below already
    spoke the REFUSED: convention for one case; this generalises the marker for every
    deliberate refusal this server raises, and lives beside it for that reason — one
    module owns the wording, even though a different module now owns getting it there.

    SCOPED TO `RuntimeError`/`ValueError`, which is what every deliberate refusal on the
    MCP surface already raises — not a bespoke exception hierarchy, which would mean
    touching every one of its ~30 call sites and risking a missed one. The trade a
    type-based tag accepts: a stdlib call that happened to raise one of those two for a
    genuine bug would be mislabelled REFUSED. None currently does, on those call sites.

    IDEMPOTENT, because a refusal built from another refusal's text (a caught-and-rewrapped
    RuntimeError) must not read "REFUSED: REFUSED: ...".

    @brief Prefix a deliberate refusal's message with "REFUSED:", once.
    @return The tagged message text.
    @version 2
    """
    text = str(exc)
    return text if text.startswith("REFUSED:") else f"REFUSED: {text}"


## @brief The refusal a write path owes its caller when this process predates its source.
## @param code A `code_identity` payload; measured when omitted.
## @return The refusal message, or None when a write is safe.
## @version 2
## @req REQ-DDB-MCP-004
def stale_code_refusal(code: Mapping[str, object] | None = None) -> str | None:
    """THE GUARD A WRITE PATH CALLS BEFORE TOUCHING AN INDEX. Returns None — meaning
    "go ahead" — on the ordinary case, so the caller is one `if` and the prose lives here
    with the rest of the code-axis wording rather than being paraphrased at each call site.

    IT DOES NOT ACCEPT AN OVERRIDE, and `force` deliberately does not bypass it. `force`
    exists to skip the FRESHNESS check; the incident that motivated this used it, so a
    refusal it could argue past would have prevented nothing.

    REJECTED — reload the pipeline modules and proceed: `PROCESS_SOURCE_FINGERPRINT` is
    taken at import and module-level constants captured by OTHER modules do not refresh
    with a reload, so a partially-reloaded pipeline would build with a MIXTURE of old and
    new logic and report success. That is a harder bug than the one being fixed.

    REJECTED — warn loudly and proceed: the notice above ALREADY warned on every call. It
    was read, and the downgrade happened anyway, because the warning said the data was
    unaffected. A louder version of a message that is already present and already wrong is
    not a fix.

    @brief Refuse a write when the running code predates the source tree.
    @return Refusal message, or None when the process matches its source.
    @version 2
    """
    identity = code if code is not None else code_identity()
    if identity.get("matches_source"):
        return None
    return (
        f"REFUSED: this server process loaded clew "
        f"{identity.get('package_version')} at launch and the package source has changed "
        f"since (fingerprint {identity.get('process_fingerprint')} on disk now "
        f"{identity.get('source_fingerprint')}). {_WRITE_HAZARD} Nothing was written. "
        "Restart the MCP client so it loads the current code, then call "
        f"index(action='refresh', force=True) — one reconnect is the whole cost. {_READ_EXEMPTION}"
    )


## @brief Every staleness axis currently in play, with the action that clears it.
## @param status A `db_status` payload.
## @param code A `code_identity` payload; measured when omitted.
## @return Notices in data → schema → code order; EMPTY when the tool is current.
## @version 1
## @req REQ-DDB-MCP-004
def notices(
    status: Mapping[str, object], code: Mapping[str, object] | None = None
) -> list[dict[str, str]]:
    """EMPTY ON A CURRENT TOOL, which is the load-bearing half. A warning that is always
    present is a warning nobody reads, and this annotation rides on every query reply —
    so the control on the whole change is that a genuinely current index is annotated
    with nothing at all.

    Ordered by how likely the reader is to act on it: `data` is the common case and the
    cheapest fix, `schema` is rarer and changes which fix applies, `code` is last because
    it is the one that says no rebuild will help.

    @brief List the active staleness axes with their remedies.
    @return List of {axis, message}, empty when current.
    @version 1
    """
    identity = code if code is not None else code_identity()
    found = (_data_notice(status), _schema_notice(status), _code_notice(identity))
    return [notice for notice in found if notice is not None]
