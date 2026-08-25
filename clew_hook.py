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

The injection surface is `_HEAD`, `_TAIL`, `_NOTE_CAPABILITY` and `_NOTE_OPERATOR` — four
module-level literals, complete sentences and all. THE ONLY RUN-TIME VALUE THAT REACHES THE MODEL
IS ONE INTEGER, our own byte tally, coerced with `int()` and rendered with `%d`. An int through
`%d` emits digits and nothing else, so no repository-controlled byte can become text here. A
reviewer verifies the whole surface by reading four strings, and `tests/test_hook.py` asserts
structurally that the substitution stays an int and that no other interpolation is introduced.

**THE TEXT VARIES ON PURPOSE, AND THAT IS A MECHANISM RATHER THAN A STYLE CHOICE.** A single
constant string repeats into wallpaper: measured, ~1,900 byte-identical injections across one
session changed nothing, and that session went on to make 2 index calls against ~1,900 searches.
An integer that moves invalidates the prompt cache from that point, so the note has to be
processed instead of replayed. Filtering is defeated mechanically, not by better prose.

**IT READS ITS INPUT ONLY TO DISCARD IT.** stdin is drained so the caller never blocks on a full
pipe, and the bytes are dropped without being parsed. Not parsing is deliberate: a JSON parser is
a decision tree over untrusted input, and this needs nothing from it.

**IT NEVER EXITS 2.** For `PostToolUse` that is documented as non-blocking but it surfaces stderr
to the model — a SECOND injection channel, and the one a crash would open by itself. So every
path returns 0, including every failure path.

**IT INFORMS AND NEVER PREVENTS** (owner ruling, 2026-08-23). `PostToolUse` cannot block and this
does not try to: even the loudest tier is a statement of what has happened and what it costs.
`grep` stays correct wherever `grep` is correct.

**THE TALLY DECAYS, AND MUST.** One clew call CLEARS the miss count. The previous policy credited
three and never reset, so a session at 1,339 searches needed ~408 consecutive index calls to get
back under a threshold of 20 — it never would, the loudest tier became permanent, and the note's
own claim that using the tool would stop it was false. A component that lies about its own
behaviour teaches a reader to discount the rest of what it says.

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

## PRESSURE IS SEARCHES SINCE THE INDEX WAS LAST USED. A search adds one; a clew call CLEARS the
## tally outright.
##
## IT USED TO SUBTRACT A CREDIT OF 3 AND NEVER RESET, WHICH MADE THE POLICY UNRECOVERABLE.
## Measured on one real session: 1,339 searches against 38 clew calls is a pressure of 1,225
## against a `_LOUD_AT` of 20, needing ~408 consecutive index calls to earn silence again. A
## second live session sat at 3,747. So the note fired on every single call, which is the
## "warning on the ordinary case" this file's own reasoning says it exists to avoid — and a banner
## on every call is read as boilerplate rather than as instruction.
##
## Reset-on-use also makes the loudest tier's claim TRUE. It previously promised that using the
## tool stops the note while the arithmetic made that unreachable, and a payload that lies about
## its own behaviour teaches a reader to discount everything else it says.
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

## The only characters allowed into the marker's filename. An ALLOWLIST, not a filter of bad
## characters: everything outside this set is dropped, so no separator, dot or control character
## can reach the path whatever the session id contains. Session ids are UUID-shaped, so filtering
## one leaves it intact and unique.
_SAFE = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-")

## The session key, read from the ENVIRONMENT — Claude Code's own, the same trust level as TMPDIR,
## and NOT from stdin, which is where repository-controlled text arrives. Verified present in a
## real hook process before being relied on.
_SESSION_ENV = "CLAUDE_CODE_SESSION_ID"

## THE INJECTION SURFACE, AS THREE LITERAL TEMPLATES. Each is a complete `PostToolUse` reply
## written out rather than built, and the ONLY run-time value that reaches any of them is one
## integer from our own byte tally, substituted with `%d` after an `int()` coercion. An int
## through `%d` cannot emit anything but digits, so no repository-controlled byte can reach the
## model through this channel — which is the security property, stated as what it actually is
## rather than as a blanket ban on substitution.
##
## THE TEXT ESCALATES AND THE COUNT MAKES EVERY INJECTION UNIQUE. One constant string, repeated,
## becomes wallpaper: measured, ~1,900 byte-identical copies changed nothing in a session that
## went on to make 2 index calls against ~1,900 searches. A varying integer breaks the prompt
## cache at that point, so the note has to be processed rather than replayed — a mechanical
## defence against filtering rather than a persuasive one.
##
## THE LOUD TIER STOPS DESCRIBING THE TOOL AND STARTS DESCRIBING THE SESSION. A capability blurb
## is an advertisement and is filed as one. A count of what this agent has done, against a tool
## the operator deliberately installed, is a fact about the reader — and it names the cost, which
## a feature list never does.
##
## IT INFORMS AND NEVER PREVENTS (owner ruling). Even the loudest tier is a statement; nothing
## here blocks, and grep stays the right answer wherever grep is the right answer.
_HEAD = '{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "'
_TAIL = '"}}'

## Tier 2 — first contact. ROUTES rather than nags, and leads with the fact that misroutes agents
## most often: dossier returns the SOURCE, not a summary of it. A session was measured asserting
## the opposite and answering from grep for twenty turns on the strength of that belief.
_NOTE_CAPABILITY = (
    "clew is indexed for this repository and %d file-inspection calls have gone by without an "
    "index call. dossier(subject=NAME) returns the symbol's VERBATIM SOURCE BODY and inline "
    "comments, plus its file and line span, both edge directions, the thread it runs on, the "
    "locks it takes and its liveness — in one reply. Raise max_body_lines when a body comes back "
    "truncated. search(text=..., corpus=...) finds a name when you do not have one, or enumerates "
    "a whole layer: threads, locks, files, config, prose. One index call clears this note."
)

## Tier 3 — the operator-intent tier. It stops selling and starts accounting.
_NOTE_OPERATOR = (
    "%d file-inspection calls in this repository, still zero index calls since the last one. The "
    "operator installed and enabled clew here, so using it is the configured expectation and not "
    "a suggestion. dossier returns verbatim source body and inline comments, which means these "
    "calls are re-deriving what one call already holds — spending the operator's tokens to "
    "rediscover indexed facts. Nothing here blocks you and grep is still right where grep is "
    "right; this is the cost of not checking. One index call clears it."
)


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
# @brief Clear a tally, so pressure can fall as well as rise.
# @param suffix Which tally to clear.
# @return None.
# @version 1
# @dg_internal
def _clear(suffix: str) -> None:
    """THE DECAY THE POLICY WAS MISSING. Without it the tally is monotonic and the loudest tier is
    a one-way door: a session measured at 1,339 searches needed ~408 consecutive index calls to
    get back under a threshold of 20, so it never did, and the escalation designed to be rare
    became the constant case.

    Truncation, not deletion — the path is already ours and re-creating it invites a race with a
    concurrent append. Every failure is swallowed for the same reason every other path here
    swallows: this component must never be the thing that breaks a tool call.

    @brief Reset one tally to zero.
    @return None.
    @version 1
    """
    try:
        with open(_marker_path() + suffix, "wb"):
            pass
    except Exception:
        pass


##
# @brief The complete reply for this pressure, tier chosen by count.
# @param pressure Searches since the index was last used.
# @return The JSON reply to write on stdout.
# @version 1
# @dg_internal
def _payload_for(pressure: int) -> str:
    """THE ONE RUN-TIME VALUE THAT REACHES THE MODEL IS AN INT THROUGH `%d`. `int()` first, so
    even a corrupted tally can only widen a number — no repository byte can become text here, and
    that is the security property this file is built around, stated as what it is rather than as
    a blanket ban on substitution.

    THE COUNT IS ALSO THE MECHANISM. A constant string repeats into wallpaper: ~1,900 identical
    copies were measured changing nothing. A number that moves invalidates the prompt cache at
    that point, so the note is processed rather than replayed.

    @brief Choose and render the tier.
    @return Complete JSON reply.
    @version 1
    """
    count = int(pressure)
    note = _NOTE_OPERATOR if count >= _LOUD_AT else _NOTE_CAPABILITY
    return _HEAD + (note % count) + _TAIL


##
# @brief Whether this search should carry a note, given the session's pressure.
# @param pressure Searches since the index was last used.
# @return True when a note is due.
# @version 2
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
        ## The index was used. CLEAR the miss tally and say nothing — a session already reaching
        ## for the tool must never hear from this, and one call is what earns the silence. The
        ## old credit-of-3 never reset, so a session that had drifted could not get back under
        ## the threshold and the loudest tier became permanent.
        _clear(_MISS_SUFFIX)
        return 0

    _record(_MISS_SUFFIX)
    pressure = _tally(_MISS_SUFFIX)
    if not _is_due(pressure):
        return 0

    try:
        sys.stdout.write(_payload_for(pressure))
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
