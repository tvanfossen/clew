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
import zlib

## Set to anything non-empty to disable the hook entirely. Read for its PRESENCE only; the value
## is never used, so it cannot carry content.
DISABLE_ENV = "CLEW_HOOK_DISABLE"

## Marker filename prefix. The suffix is a HEX DIGEST, so the complete path is this module's own
## literals plus 16 hex characters and nothing else can shape it.
_MARKER_PREFIX = "clew-hook-seen-"

## Temp-directory environment variables, in the order the platform conventions put them, with a
## literal fallback. `tempfile.gettempdir()` would do this better — it PROBES for a writable
## directory — and costs 18ms of import on a component that runs after every matching tool call.
## The worst case here is a marker written somewhere unwritable, which the failure path already
## handles by going silent.
_TMP_ENV = ("TMPDIR", "TMP", "TEMP")

## The session key, read from the ENVIRONMENT — Claude Code's own, the same trust level as TMPDIR,
## and NOT from stdin, which is where repository-controlled text arrives. Verified present in a
## real hook process before being relied on.
_SESSION_ENV = "CLAUDE_CODE_SESSION_ID"

## THE ENTIRE INJECTION SURFACE, AS ONE LITERAL. The complete `PostToolUse` reply, message
## included, written out rather than built. Nothing at run time can alter it, which is the whole
## security argument for this component and is asserted by a structural test.
##
## The wording deliberately ROUTES rather than nags: it names the two calls and what they answer,
## because "consider using the index" costs a turn and teaches nothing. It also says the reminder
## will not repeat, so a reader knows the silence afterwards is by design rather than a failure.
_PAYLOAD = '{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "clew is indexed for this repository and is often one call where a search is several. dossier(subject=NAME) returns a symbol\'s file and line span, both edge directions, the thread it runs on, the locks it takes, the requirements it satisfies and its liveness, in one reply. search(text=..., corpus=...) finds a name when you do not have one, or enumerates a whole layer: threads, locks, files, config, prose. Questions of the form who calls this, where is this defined, what does this touch, and is this used anywhere else are usually answered there in one call rather than several searches plus a file read. This note appears once per session and will not repeat."}}'


##
# @brief The once-per-session marker path for this hook invocation.
# @return Path string under the temp directory, named from literals and a hex digest.
# @version 3
# @dg_internal
def _marker_path() -> str:
    """KEYED ON THE SESSION, DIGESTED, AND BUILT WITHOUT `pathlib` OR `tempfile`.

    `CLAUDE_CODE_SESSION_ID` is the key and was confirmed present in a real hook process before
    being relied on. It comes from the environment — Claude Code's own, the same trust level as
    TMPDIR — and not from stdin, where repository-controlled text arrives. An earlier version
    keyed on `os.getppid()` and fired on EVERY tool call in production, because each invocation
    gets a fresh parent.

    DIGESTED RATHER THAN FILTERED. A session id is an arbitrary string reaching a filesystem path;
    a filter is a blocklist and blocklists are wrong by default. `crc32` is a NAMING device, not a
    security primitive — what it provides is a fixed-length, hex-only output that cannot escape
    the directory whatever it is given. A collision would mean one session silencing another,
    which is a nuisance and not a vulnerability.

    THE IMPORTS ARE THE POINT. Measured, per invocation: `pathlib` +16ms, `tempfile` +18ms,
    `hashlib` +4ms, against a 28ms interpreter floor — on a component that runs after every Bash,
    Grep and Glob. `zlib` is free by comparison and `os.path` needs nothing. The whole module now
    costs about what starting Python costs, which is the floor for a subprocess hook.

    @brief Build the marker path from literals and a hex digest.
    @return The marker path.
    @version 3
    """
    session = os.environ.get(_SESSION_ENV) or str(int(os.getppid()))
    digest = format(zlib.crc32(session.encode("utf-8", "replace")) & 0xFFFFFFFF, "08x")
    tmp = next((os.environ[k] for k in _TMP_ENV if os.environ.get(k)), "/tmp")
    return os.path.join(tmp, _MARKER_PREFIX + digest)


##
# @brief Emit the constant nudge at most once per session; never fail, never block.
# @return Always 0.
# @version 1
# @req REQ-DDB-MCP-003
def main() -> int:
    """EVERY PATH RETURNS 0, including every error path, and that is a security property rather
    than politeness: a non-zero exit on `PostToolUse` surfaces stderr to the model, which is a
    second channel into the context this component exists to protect.

    ORDER MATTERS. The disable check runs before anything else so a disabled hook does no work at
    all; stdin is drained next so the caller cannot block on a full pipe; the marker is claimed
    before the write so a crash mid-write cannot produce a repeating note.

    @brief Run the hook.
    @return 0, always.
    @version 1
    """
    if os.environ.get(DISABLE_ENV):
        return 0

    ## DRAINED, NEVER PARSED. The caller writes the event JSON here and would block on a full
    ## pipe if nobody read it. The bytes are discarded unexamined: this component needs nothing
    ## from them, and a parser over untrusted input is surface it does not have to have.
    try:
        sys.stdin.buffer.read()
    except Exception:
        pass

    try:
        ## ONE GUARD, NOT TWO. An `exists()` fast path stood here as well, and a mutation control
        ## showed it was INERT: removing either left the other, so neither could be tested. The
        ## exclusive create is the real mechanism — it also closes the race an `exists()` check
        ## opens, since two hooks can both see "absent" and both emit.
        with open(_marker_path(), "x", encoding="utf-8") as handle:
            handle.write("1")
    except FileExistsError:
        return 0
    except Exception:
        ## An unwritable temp directory must not make the hook noisy OR loud. Silence is the
        ## correct failure: the note is a convenience, and a hook that complains about its own
        ## bookkeeping is worse than one that says nothing.
        return 0

    try:
        sys.stdout.write(_PAYLOAD)
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
