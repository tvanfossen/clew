# SPDX-License-Identifier: MIT
"""A PostToolUse hook that names the index once per session, and can do nothing else.

**WHAT IT IS FOR.** `grep` has an enormous training prior; an index tool has none. gh#7 measured
the consequence on a real session — the repository indexed, clew documented in the project's own
CLAUDE.md, and across a multi-hour sitting SIX `grep`/`rg` calls, FOUR of them answerable by one
`dossier` call, and ZERO spontaneous index calls. One of those greps produced a wrong conclusion
that a `dossier` reply later corrected. 1.0.3's `alwaysLoad` removed the mechanical penalty (the
tools no longer sit behind a `ToolSearch` round trip); it does nothing about the prior.

**THIS IS A SECURITY-SENSITIVE COMPONENT AND IS WRITTEN AS ONE.** A hook is an invisible
executable that runs on a consumer's machine after their tool calls and injects text into their
model's context. Its stdin carries `tool_input` and `tool_response` — attacker-influenced content
whenever the repository is: a file name, a matched line, a README. So the whole design is one
rule:

    THE OUTPUT IS A COMPILE-TIME CONSTANT. Nothing read at run time can reach it.

`_PAYLOAD` below is a single module-level literal — the complete JSON, message and all. Not a
template, not a format string, not a dict serialized at run time. There is no code path that
concatenates anything into it, because there is no code path that could: the emit is
`sys.stdout.write(_PAYLOAD)`. A reviewer can verify the entire injection surface by reading one
string, and `tests/test_hook.py` asserts structurally that no interpolation is ever introduced.

**IT READS ITS INPUT ONLY TO DISCARD IT.** stdin is drained so the caller never blocks on a full
pipe, and the bytes are dropped without being parsed. Not parsing is deliberate: a JSON parser is
a decision tree over untrusted input, and this needs nothing from it.

**IT NEVER EXITS 2.** For `PostToolUse` that is documented as non-blocking but it surfaces stderr
to the model — a SECOND injection channel, and the one a crash would open by itself. So every
path returns 0, including every failure path.

**ONCE PER SESSION.** No debounce exists in the hook system, so a marker file provides it. A
reminder that fires on every `Grep` is one a reader learns to skip, which is this project's
standing lesson about warnings on the ordinary case. The marker's name is derived from the parent
process id coerced through `int()` — never from a session id, a path, or anything else off stdin,
so no value under a repository's control reaches the filesystem.

**IT LIVES OUTSIDE THE `clew` PACKAGE, AND THAT IS A PERFORMANCE PROPERTY.** This module was
`clew/hook.py`, and a console script pointing into the package imports `clew/__init__.py` — which
eagerly pulls the whole pipeline (`cli`, `doxygen`, `call_edges`, ...). MEASURED: 202 ms per
invocation against 45 ms for the stdlib this file actually uses, on a hook that fires after EVERY
matching tool call. 157 ms of that was the package import, for a component that needs `os`, `sys`,
`tempfile` and `pathlib`.

So it imports nothing from `clew` and must keep importing nothing: the gate asserts it. 25 ms of
the remaining 45 is the interpreter itself, which is the floor for any subprocess hook and the
reason this does as little as it possibly can.

**IT CAN BE TURNED OFF.** `CLEW_HOOK_DISABLE=1` exits immediately. The acceptance harness sets it,
because a standing "prefer the index" nudge would make the one arm that measures UNPROMPTED
reach-for-it unmeasurable — and that arm is worth roughly nine points by this project's own union
analysis. Shipping the mitigation must not destroy the measurement that would justify it.

@brief A constant, once-per-session PostToolUse nudge toward the index.
@version 1
"""

from __future__ import annotations

import os
import sys

## Set to anything non-empty to disable the hook entirely. Read for its PRESENCE only; the value
## is never used, so it cannot carry content.
DISABLE_ENV = "CLEW_HOOK_DISABLE"

## Marker filename prefix. The suffix is a HEX DIGEST, so the complete path is this module's own
## literals plus 16 hex characters and nothing else can shape it.
_MARKER_PREFIX = "clew-hook-seen-"

## Suffixes for the two per-session tallies. SIZE IS THE COUNT: each event appends one byte, so a
## tally needs no parsing, no read-modify-write and no lock. Two concurrent tool calls both append
## and both are counted, where a read-increment-write would lose one.
_MISS_SUFFIX = "-searches"
_USED_SUFFIX = "-clew"

## Where the marker goes. `tempfile` costs 18ms of import on a component that runs after every
## matching tool call, and all it is needed for here is this lookup.
_TMP_ENV = ("TMPDIR", "TMP", "TEMP")

## The argv flag the manifest passes when the tool that just ran was a clew tool. IT COMES FROM
## OUR OWN MANIFEST, never from stdin — which is what lets the hook know what happened without
## reading a byte of repository-controlled text. The matcher decides; the flag reports.
USED_FLAG = "--used"

## PRESSURE, AND IT ESCALATES THE LONGER THE INDEX GOES UNUSED. A search adds one; a clew call
## subtracts `_CLEW_CREDIT`, so using the tool pops the count down faster than searching pushes it
## up and steady use parks it at zero, silently, forever.
##
##   below _QUIET_BELOW   silent — a few searches are ordinary and need no comment
##   up to _LOUD_AT       one note every _INTERVAL searches
##   at _LOUD_AT and up   a note on every search
##
## The escalation is the point. A session that never reaches for the index in spite of it being
## installed and available is the case worth interrupting; a session already using it must hear
## nothing, both to keep this plugin out of the context window and because a model pushed hard
## enough will reach for the index where `grep` is genuinely right — which degrades the agent and
## corrupts any later measurement of whether the index helps.
_QUIET_BELOW = 5
_INTERVAL = 5
_LOUD_AT = 20
_CLEW_CREDIT = 3

## The only characters allowed into the marker's filename. An ALLOWLIST, not a filter of bad
## characters: everything outside this set is dropped, so no separator, dot or control character
## can reach the path whatever the session id contains. Session ids are UUID-shaped, so filtering
## one leaves it intact and unique.
_SAFE = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-")

## The session key, read from the ENVIRONMENT — Claude Code's own, the same trust level as TMPDIR,
## and NOT from stdin, which is where repository-controlled text arrives. Verified present in a
## real hook process before being relied on.
_SESSION_ENV = "CLAUDE_CODE_SESSION_ID"

## THE ENTIRE INJECTION SURFACE, AS ONE LITERAL. The complete `PostToolUse` reply, message
## included, written out rather than built. Nothing at run time can alter it, which is the whole
## security argument for this component and is asserted by a structural test.
##
## The wording deliberately ROUTES rather than nags: it names the two calls and what they answer,
## because "consider using the index" costs a turn and teaches nothing.
##
## AND IT MUST DESCRIBE THE POLICY IT ACTUALLY HAS. It said "appears once per session and will not
## repeat" while the escalation below was being written, which made the constant assert something
## the code no longer did — a payload that lies about its own behaviour is worse than a silent one.
_PAYLOAD = '{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "clew is indexed for this repository and is often one call where a search is several. dossier(subject=NAME) returns a symbol\'s file and line span, both edge directions, the thread it runs on, the locks it takes, the requirements it satisfies and its liveness, in one reply. search(text=..., corpus=...) finds a name when you do not have one, or enumerates a whole layer: threads, locks, files, config, prose. Questions of the form who calls this, where is this defined, what does this touch, and is this used anywhere else are usually answered there in one call rather than several searches plus a file read. This note appears only while the index goes unused, and using it stops the note entirely."}}'


##
# @brief The once-per-session marker path for this hook invocation.
# @return Path string under the temp directory.
# @version 4
# @dg_internal
def _marker_path() -> str:
    """The marker gives "once per session" its memory: the hook is a fresh process every time, so
    the fact that it has already spoken has to live somewhere.

    KEYED ON THE SESSION. `CLAUDE_CODE_SESSION_ID` comes from the environment — Claude Code's own,
    the same trust level as TMPDIR — and NOT from stdin, where repository-controlled text arrives.
    It was confirmed present in a real hook process before being relied on. An earlier version
    keyed on `os.getppid()` and fired on EVERY tool call in production, because each invocation
    gets a fresh parent.

    FILTERED THROUGH AN ALLOWLIST. The session id is arbitrary text going into a filename, so
    everything outside `_SAFE` is dropped — no separator, dot or control character can reach the
    path. That is an allowlist rather than a search for bad characters, because a list of bad
    characters is always incomplete.

    @brief Build the marker path from literals and a filtered session key.
    @return The marker path.
    @version 4
    """
    session = os.environ.get(_SESSION_ENV) or str(int(os.getppid()))
    safe = "".join(c for c in session if c in _SAFE)[:64] or "nosession"
    tmp = next((os.environ[k] for k in _TMP_ENV if os.environ.get(k)), "/tmp")
    return os.path.join(tmp, _MARKER_PREFIX + safe)


##
# @brief Count of recorded events of one kind for this session.
# @param suffix Which tally to read.
# @return The count, or 0 when it cannot be read.
# @version 1
# @dg_internal
def _tally(suffix: str) -> int:
    """SIZE IS THE COUNT. Each event appends one byte, so a tally needs no parsing, no
    read-modify-write and no lock — two concurrent tool calls both append and both are counted,
    where a read-increment-write would lose one. It also means nothing from the file is ever
    interpreted: a corrupted or tampered tally can only make the count wrong, never change what
    is emitted, because what is emitted is a constant.

    @brief Read one tally by file size.
    @return The count, or 0.
    @version 1
    """
    try:
        return os.path.getsize(_marker_path() + suffix)
    except Exception:
        return 0


##
# @brief Record one event of a kind for this session.
# @param suffix Which tally to append to.
# @return None.
# @version 1
# @dg_internal
def _record(suffix: str) -> None:
    """@brief Append one byte to a tally, ignoring any failure.
    @return None.
    @version 1
    """
    try:
        with open(_marker_path() + suffix, "ab") as handle:
            handle.write(b".")
    except Exception:
        pass


##
# @brief Whether this search should carry a note, given the session's pressure.
# @param pressure Searches outstanding after crediting clew usage.
# @return True when a note is due.
# @version 1
# @dg_internal
def _is_due(pressure: int) -> bool:
    """@brief Apply the escalation policy to a pressure value.
    @return True when a note is due.
    @version 1
    """
    if pressure < _QUIET_BELOW:
        return False
    if pressure >= _LOUD_AT:
        return True
    return pressure % _INTERVAL == 0


##
# @brief Record the call and emit the constant note when one is due; never fail, never block.
# @return Always 0.
# @version 2
# @req REQ-DDB-MCP-003
def main() -> int:
    """EVERY PATH RETURNS 0, including every error path, and that is a security property rather
    than politeness: a non-zero exit on `PostToolUse` surfaces stderr to the model, which is a
    second channel into the context this component exists to protect.

    WHICH TOOL RAN IS TOLD BY ARGV, NOT BY STDIN. The manifest registers this twice — once for
    the search tools and once for the clew tools with `--used` — so the matcher supplies the fact
    and no repository-controlled byte is ever examined to obtain it.

    @brief Run the hook.
    @return 0, always.
    @version 2
    """
    if os.environ.get(DISABLE_ENV):
        return 0

    ## DRAINED, NEVER PARSED. The caller writes the event JSON here and would block on a full pipe
    ## if nobody read it. The bytes are discarded unexamined: this component needs nothing from
    ## them, and a parser over untrusted input is surface it does not have to have.
    try:
        sys.stdin.buffer.read()
    except Exception:
        pass

    if USED_FLAG in sys.argv[1:]:
        ## The index was used. Record the credit and say nothing — a session already reaching for
        ## the tool is the one that must never hear from this.
        _record(_USED_SUFFIX)
        return 0

    _record(_MISS_SUFFIX)
    pressure = _tally(_MISS_SUFFIX) - _CLEW_CREDIT * _tally(_USED_SUFFIX)
    if not _is_due(pressure):
        return 0

    try:
        sys.stdout.write(_PAYLOAD)
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
