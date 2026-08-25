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
whenever the repository is: a file name, a matched line, a README.

**THE OLD RULE IS GONE AND ITS REPLACEMENT IS WEAKER. SAY SO PLAINLY.** Through 1.0.9 the rule was
"THE OUTPUT IS A COMPILE-TIME CONSTANT — nothing read at run time can reach it", and a reviewer
verified the whole surface by reading four strings. That is no longer true. Bytes that arrived on
stdin now reach the model, because a note that cannot say what you just did was measured changing
nothing: it fired repeatedly through a long session while the agent read four source functions
with `grep`, and its own account was that "the index exists" carries no information a capable model
does not already have. The generic note was safe and inert. THE NEW RULE IS A BOUNDED CODOMAIN:

    The output is a `json.dumps` of a literal-keyed object. Every value in it is either a
    module-level literal, an `int` through `%d`, or a string in `[A-Za-z0-9._-]{1,64}` not
    beginning with `.` — the total codomain of one function, `_safe_token`.

Two independent mechanisms hold two independent risks, and NEITHER covers the other:

  * `json.dumps` over the whole dict kills PROTOCOL injection. Hand-assembled JSON was safe only
    because `%d` on an int cannot emit a `"`; a filename containing `"}}` would otherwise close
    `additionalContext` and append sibling keys — `decision`, `continue` — letting a repository
    author the harness's control plane through a hook the operator cannot see. Serialising the
    object once makes escaping the serialiser's property instead of a validation promise.
  * `_safe_token` bounds CONTENT injection. It does not eliminate it. 64 characters of
    attacker-chosen hyphenated English can be quoted back inside our own sentence: a repo may ship
    `dossier-is-unreliable-prefer-grep.py`. **That residual is accepted, not argued away.** Three
    things make it tolerable — the same bytes are already in the model's context from the tool
    result this hook is reacting to, `tool_response` is NEVER read, and our own literal always
    closes the note so the basename never sits at the end.

Reviewer cost is now "read the literals, plus one small total function". `tests/test_hook.py`
asserts the shape over the AST — `%s` is permitted, but only ever fed `_safe_token`'s output — and
proves the codomain by totality over the input alphabet rather than by sampling.

**THE TEXT VARIES ON PURPOSE, AND THAT IS A MECHANISM RATHER THAN A STYLE CHOICE.** A single
constant string repeats into wallpaper: measured, ~1,900 byte-identical injections across one
session changed nothing, and that session went on to make 2 index calls against ~1,900 searches.
An integer that moves invalidates the prompt cache from that point, so the note has to be
processed instead of replayed. Filtering is defeated mechanically, not by better prose.

**IT PARSES ITS INPUT NOW, AND ONLY FOR ONE FIELD.** stdin is still drained in full so the caller
never blocks on a full pipe. It is then parsed for exactly one purpose: the basename of the file
the agent just looked at. `tool_response` is never read — it is the one bulk repository-authored
field, and the only thing standing between a 64-character allowlisted token and arbitrary file
content. Every parse failure degrades to the fileless note; none can raise, because a traceback on
stderr is itself a second injection channel.

**WHICH TOOL RAN STILL COMES FROM ARGV, NOT FROM STDIN.** The manifest registers one matcher per
modality and passes its own flag, so the modality is a compile-time selector we chose and only ONE
slot in the note originates outside this file. Deriving it from `tool_name` instead would have
doubled the run-time surface for nothing.

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

import json
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

## Where the marker goes. `tempfile` costs 18ms of import on a component that runs after every
## matching tool call, and all it is needed for here is this lookup.
_TMP_ENV = ("TMPDIR", "TMP", "TEMP")

## The argv flag the manifest passes when the tool that just ran was a clew tool. IT COMES FROM
## OUR OWN MANIFEST, never from stdin — which is what lets the hook know what happened without
## reading a byte of repository-controlled text. The matcher decides; the flag reports.
USED_FLAG = "--used"

## ONE FLAG PER MODALITY, from our own manifest, for the same reason `USED_FLAG` exists: the
## matcher already knows which tool fired, so taking the modality from argv keeps `tool_name` out
## of the run-time surface entirely. Only the basename comes from stdin.
READ_FLAG = "--read"
PATTERN_FLAG = "--pattern"
GLOB_FLAG = "--glob"
SHELL_FLAG = "--shell"

## Every flag the manifest is allowed to pass, so `tests/test_plugin_manifest.py` can pin the set
## rather than a single literal.
MODALITY_FLAGS = (READ_FLAG, PATTERN_FLAG, GLOB_FLAG, SHELL_FLAG)

## Which `tool_input` key holds the path, per modality. `Glob` is absent DELIBERATELY: its input is
## a pattern, not a path, and echoing a raw glob widens the surface for no gain.
_FIELD_FOR = {
    READ_FLAG: "file_path",
    PATTERN_FLAG: "path",
    SHELL_FLAG: "command",
}

## A PARSE CEILING, NOT A SECURITY GATE — and the distinction matters, because a reviewer will
## otherwise read it as a claim it cannot support. Nothing about 1 MiB makes a payload safe; the
## sanitiser does that. This exists because a `Read` of a large file puts the whole file in
## `tool_response`, this process runs after EVERY matching tool call, and the module's budget is
## ~45 ms. Over the ceiling, the note degrades to the fileless variant in silence.
_MAX_EVENT = 1 << 20

## THE TOTAL CODOMAIN OF `_safe_token`, and therefore the complete set of bytes that can reach a
## consumer's model through this hook from outside this file. Deliberately spelled out rather than
## imported from `string` or matched with `re`: this file's import list is a measured performance
## property, and the set is the security argument, so it should be readable without a lookup.
_NAME_SAFE = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
_NAME_MAX = 64

## Commands that mean "the agent just looked at a file". Matched as the VERB, never as a substring:
## `concatenate` is not `cat`. Kept small on purpose — an unrecognised command falls back to the
## fileless note, which is the cheap and correct outcome.
_INSPECT_VERBS = frozenset(
    "cat head tail sed awk less more nl od xxd strings grep rg ack wc".split()
)

## Segment separators. A pipeline's FIRST segment decides; `cat a.py | grep b` is a read of a.py.
_SEGMENT_SPLIT = ("|", "&&", "||", ";")

## Shell metacharacters that make a naive split untrustworthy. Their presence anywhere in the
## command forces the fileless note: refusing to model shell grammar is the point, because a shell
## parser over attacker-adjacent text is a far larger decision tree than the JSON parse above.
_SHELL_UNSAFE = ("`", "$", "*", "?", "~", "<<", ">")

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

## How often the LOUD tier speaks once it is reached. It used to speak on every single call, which
## produced ~30 near-identical injections in one measured session — wallpaper, and therefore
## filtered. 3 keeps the tier present without making it furniture.
_LOUD_INTERVAL = 3

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
## EVERY TEMPLATE SAYS WHAT THE COMPLETED CALL COULD NOT DELIVER. That is the only claim a
## PostToolUse note can make with non-zero marginal value: the answer to "what does this code say"
## is already in context and re-asking is genuinely pointless, but no number of file reads produces
## the REVERSE EDGE. So each template names callers/callees rather than advertising the tool.
##
## SLOT ORDER IS ALWAYS `%s` THEN `%d`, AND OUR OWN LITERAL ALWAYS CLOSES THE NOTE — the basename
## never sits at the end, so a hostile filename cannot read as a trailing directive.
##
## `NAME` STAYS A PLACEHOLDER, NEVER THE BASENAME. Measured: `dossier(subject="clew_hook.py")`
## returns `found: false`. A filename is not a valid subject, so a note inviting one would teach a
## call that fails — and one failing suggestion discredits every note after it.
##
## THE MODALITY IS NAMED IN LOWERCASE PROSE, NEVER AS THE TOOL'S PROPER NAME. `tests/test_hook.py`
## forbids the literal `Grep` in output as a CANARY for echoing `tool_name`; keeping these words as
## our own constants leaves that canary sharp while still making the note a diff against what the
## reader just did.
_CAPABILITY_NAMED = {
    READ_FLAG: (
        "You read `%s`. A file read gives you the body and nothing else; dossier(subject=NAME) "
        "returns that same body verbatim plus its callers, its callees, the thread it runs on and "
        "the locks it takes, in one reply. %d file-inspection calls, no index call."
    ),
    PATTERN_FLAG: (
        "You pattern-matched inside `%s`. A match says where a name occurs; dossier(subject=NAME) "
        "says what it is — verbatim body plus both edge directions — and search(text=...) finds "
        "the name when you do not have one. %d file-inspection calls, no index call."
    ),
    SHELL_FLAG: (
        "You inspected `%s` from a shell. dossier(subject=NAME) returns that body verbatim with "
        "its callers and callees in one reply, which no amount of reading the file can produce. "
        "%d file-inspection calls, no index call."
    ),
}

## No basename survived, or the modality never carries one. Still a diff — it names the MODALITY —
## but makes no claim about a file it cannot identify.
_CAPABILITY_FILELESS = {
    READ_FLAG: (
        "%d file-inspection calls in this repository, no index call. dossier(subject=NAME) returns "
        "a symbol's verbatim source body and inline comments with its callers and callees in one "
        "reply; search(text=..., corpus=...) finds the name, or enumerates threads, locks, files, "
        "config, prose."
    ),
    PATTERN_FLAG: (
        'That was a repository-wide pattern match. search(text="two distinctive words", '
        'corpus="symbols") ranks the same repository by what the index actually parsed, and each '
        "row's kind is what dossier takes back verbatim. %d such calls, no index call."
    ),
    ## The one paste-ready template: a measured working call with the same argument shape as the
    ## glob just run, returning strictly more than the glob did (path plus a symbol count).
    GLOB_FLAG: (
        'You globbed for files. search(corpus="files", text=<the same pattern>) answers that '
        "from the index and adds a symbol count per file, so you can see which of them hold parsed "
        "code. %d file-inspection calls, no index call."
    ),
    SHELL_FLAG: (
        "%d file-inspection calls in this repository, no index call. dossier(subject=NAME) returns "
        "a symbol's verbatim source body and inline comments with its callers and callees in one "
        "reply; search(text=..., corpus=...) finds the name, or enumerates threads, locks, files, "
        "config, prose."
    ),
}

## Tier 3 stops selling and starts accounting.
##
## "ONE INDEX CALL CLEARS THIS NOTE" IS DELIBERATELY GONE. It was true, which is exactly why it was
## dangerous: it turned the note into instructions for silencing the note, and the cheapest
## compliance is one junk call — which scores as success on every metric while teaching nothing and
## degrading the agent. The mechanism is described as a RATIO instead. The moralising clause
## ("spending the operator's tokens") is gone for the same reason: it invites the same theatre.
_OPERATOR_NAMED = (
    "You read `%s`. %d file-inspection calls, no index call since the last one — nothing in a file "
    "read gives you its callers, and dossier(subject=NAME) returns body and both edge directions "
    "in one reply. clew is installed here by the operator; grep stays right where grep is right. "
    "This is the ratio, not a block."
)

_OPERATOR_FILELESS = (
    "%d file-inspection calls in this repository, no index call since the last one. The definition, "
    "its body and everything that calls it are one dossier(subject=NAME) call away. clew is "
    "installed here by the operator. Nothing blocks you; this is the ratio, not a block."
)


##
# @brief The basename of a path, reduced to the safe alphabet, or None if anything is off.
# @param token A candidate path from `tool_input`, of unknown type and content.
# @return A name in `[A-Za-z0-9._-]{1,64}` not starting with `.`, or None.
# @version 1
# @dg_internal
def _safe_token(token: object) -> str | None:
    """THIS FUNCTION IS THE SECURITY BOUNDARY. Its return set is the complete set of bytes that can
    reach a consumer's model from outside this file, so it is written to be read in one sitting and
    is proved TOTAL over the input alphabet by `tests/test_hook.py` rather than sampled.

    THE SPLIT IS HAND-ROLLED BECAUSE `os.path.basename` IS THE WRONG TOOL HERE. On Linux it is
    `posixpath.basename` and splits on `/` alone, so a Windows-shaped `C:\\Users\\bob\\evil.py`
    comes back WHOLE — the "basename only, never a full path" rule would be violated on
    attacker-chosen input while the code read as though it enforced it. Normalising `\\` first is
    platform-invariant, and a security predicate must not vary with the machine it runs on.

    REJECT WHOLE, NEVER SCRUB. Stripping bad characters from `IGNORE ALL PREVIOUS` yields
    `IGNOREALLPREVIOUS` — still readable, still attacker-authored, and now with a transform the
    attacker knows and can pre-compensate for. Rejection leaks exactly one bit: whether the note is
    specific or fileless.

    Leading `.` is refused, which covers `.`, `..` and dotfiles: a note naming `..` says nothing,
    and a traversal-shaped token should never be quoted back at all.

    @brief Reduce a candidate path to a safe basename.
    @return The name, or None when it cannot be trusted or is not worth saying.
    @version 1
    """
    if not isinstance(token, str) or not token:
        return None
    tail = token.replace("\\", "/").rsplit("/", 1)[-1]
    if not tail or len(tail) > _NAME_MAX or tail.startswith("."):
        return None
    if any(c not in _NAME_SAFE for c in tail):
        return None
    return tail


##
# @brief The one file token a shell command inspected, when that is unambiguous.
# @param command The raw `tool_input.command` string.
# @return A candidate path, or None whenever anything is uncertain.
# @version 1
# @dg_internal
def _bash_target(command: object) -> str | None:
    """BIASED HARD TOWARD None, AND THAT IS THE DESIGN. A note saying "you read foo.py" when the
    agent read `bar.py` costs more credibility than a fileless note costs attention — and this
    file's own argument is that a component which lies about itself teaches a reader to discount
    everything else it says. So every uncertainty resolves to the fileless variant.

    NO SHELL GRAMMAR IS MODELLED, DELIBERATELY. Quotes, substitutions, globs and heredocs make a
    naive split untrustworthy, so their mere presence refuses the whole command. A shell parser over
    attacker-adjacent text would be a far larger decision tree than the JSON parse this module
    already reluctantly admits.

    @brief Find the single inspected file in a shell command, or refuse.
    @return The candidate token, or None.
    @version 1
    """
    if not isinstance(command, str) or any(bad in command for bad in _SHELL_UNSAFE):
        return None
    segment = command
    for sep in _SEGMENT_SPLIT:
        segment = segment.split(sep, 1)[0]
    words = segment.split()
    ## Skip leading `NAME=value` assignments so `LC_ALL=C grep ...` still resolves its verb.
    while words and "=" in words[0] and not words[0].startswith("-"):
        words = words[1:]
    if not words or words[0] not in _INSPECT_VERBS:
        return None
    ## EXACTLY ONE candidate, or refuse: `cat a.py b.py` is genuinely ambiguous about what was
    ## "just read", and `grep -r pat src/` names a directory rather than a file.
    found = [w for w in words[1:] if not w.startswith("-") and "." in w]
    return found[0] if len(found) == 1 else None


##
# @brief The basename the agent just looked at, from the event, or None.
# @param raw The undecoded stdin bytes.
# @param modality The argv-supplied modality flag.
# @return A safe basename, or None to use the fileless note.
# @version 1
# @dg_internal
def _target_name(raw: bytes, modality: str) -> str | None:
    """EVERY RUNG FALLS TO None, AND None IS ALWAYS SAFE — it selects the fileless note, which is
    where this component was before 1.0.10. There is no rung that raises and none that returns
    partial trust.

    `except Exception` IS DELIBERATE AND NARROWING IT WOULD BE A BUG. `RecursionError` from deeply
    nested JSON is a `RuntimeError`, NOT a `ValueError`, so `except (ValueError, TypeError)` would
    let it escape — and an escape here becomes a traceback on stderr, which `PostToolUse` surfaces
    to the model: the second injection channel this file exists to keep shut. `MemoryError` is
    reachable the same way. After either, the stack or heap is nearly exhausted, so the handler does
    nothing but return.

    THE `isinstance(event, dict)` GUARD IS NOT DEFENSIVE PADDING. Valid JSON is not necessarily an
    object: `"a string"` parses to `str`, and the test suite's own helper feeds a double-encoded
    event that does exactly that. Without this rung the hook would raise `AttributeError` on its own
    fixture.

    `tool_response` is NEVER read. It is the one bulk repository-authored field.

    @brief Extract a safe basename from the event.
    @return The name, or None.
    @version 1
    """
    if len(raw) > _MAX_EVENT:
        return None
    try:
        ## BYTES, not a manual decode: `json.loads` does its own UTF-8 handling, while
        ## `.decode(errors="surrogateescape")` would mint lone surrogates that `json.dumps` happily
        ## emits as "\\udcff" and strict consumers then reject.
        event = json.loads(raw)
    except Exception:
        return None
    if not isinstance(event, dict):
        return None
    field = _FIELD_FOR.get(modality)
    if field is None:
        return None
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    value = tool_input.get(field)
    if modality == SHELL_FLAG:
        value = _bash_target(value)
    return _safe_token(value)


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
def _payload_for(pressure: int, modality: str, name: str | None) -> str:
    """TWO RUN-TIME VALUES REACH THE MODEL AND BOTH ARE BOUNDED: an `int` through `%d`, and a string
    that came out of `_safe_token`. `int()` first, so a corrupted tally can only widen a number; and
    `name` is either None or inside `[A-Za-z0-9._-]{1,64}`. There is no third slot, and
    `tests/test_hook.py` pins that over the AST.

    SERIALISED ONCE, OVER THE WHOLE OBJECT. The reply used to be assembled by concatenating
    literals, which was safe only because `%d` on an int cannot emit a `"`. With a string in play,
    a filename containing `"}}` would close `additionalContext` and append sibling protocol keys —
    so escaping has to be the serialiser's job. The result must never be post-processed: a `+`, a
    `.replace()`, or dumping a fragment to paste between literals each reopen the hole. `_HEAD` and
    `_TAIL` were DELETED rather than left beside this path, so a later patch cannot reach for them.

    `ensure_ascii` is left at its default, which also escapes U+2028/U+2029 — legal in JSON strings
    but breaking for JS-adjacent consumers.

    THE VARYING SLOTS ARE ALSO THE MECHANISM. A constant string repeats into wallpaper: ~1,900
    identical copies were measured changing nothing. The count moves on every fire and now the
    basename moves too, so the prompt cache breaks at that point and the note is processed rather
    than replayed.

    @brief Choose and render the tier.
    @return Complete JSON reply.
    @version 2
    """
    count = int(pressure)
    ## A modality with no named template (Glob) is treated as fileless: better to say less than to
    ## invent a sentence about a pattern that is not a path.
    if name is not None and modality not in _CAPABILITY_NAMED:
        name = None
    if name is None:
        template = _OPERATOR_FILELESS if count >= _LOUD_AT else _CAPABILITY_FILELESS[modality]
        text = template % count
    else:
        template = _OPERATOR_NAMED if count >= _LOUD_AT else _CAPABILITY_NAMED[modality]
        text = template % (name, count)
    return json.dumps(
        {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}}
    )


##
# @brief Whether this search should carry a note, given the session's pressure.
# @param pressure Searches since the index was last used.
# @return True when a note is due.
# @version 2
# @dg_internal
def _is_due(pressure: int) -> bool:
    """THE LOUD TIER NO LONGER FIRES ON EVERY CALL, AND THAT IS A FIX RATHER THAN A SOFTENING. It
    did, and one measured session took ~30 near-identical injections past the threshold — which is
    precisely the wallpaper condition this file's own reasoning says it exists to avoid. A banner on
    every call is read as boilerplate, so the tier that matters most was the one being filtered
    hardest. It now speaks every `_LOUD_INTERVAL` calls; the count keeps climbing, so the text
    still escalates and the prompt cache still breaks.

    @brief Apply the escalation policy to a pressure value.
    @return True when a note is due.
    @version 2
    """
    if pressure < _QUIET_BELOW:
        return False
    if pressure >= _LOUD_AT:
        return pressure % _LOUD_INTERVAL == 0
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

    ## DRAINED IN FULL, still — the caller writes the event JSON here and would block on a full pipe
    ## if nobody read it. Truncating the READ would trade a non-problem for a hang or an EPIPE; the
    ## ceiling that matters is on the PARSE, in `_target_name`.
    try:
        raw = sys.stdin.buffer.read()
    except Exception:
        raw = b""

    ## ABOVE THE PARSE, DELIBERATELY. A clew call needs nothing from the event, so this path still
    ## examines not one byte of repository-controlled text — the narrowest possible surface for the
    ## most frequent case in a session that is already using the index.
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
        ## PARSED ONLY WHEN A NOTE IS ACTUALLY DUE. Most invocations are silent, and this keeps the
        ## parser off the hot path entirely for them.
        return 0

    ## THE MODALITY COMES FROM ARGV — our own manifest's flag, never `tool_name`. An unflagged or
    ## unknown invocation falls back to the read wording, which is the safe generic.
    modality = next((flag for flag in MODALITY_FLAGS if flag in sys.argv[1:]), READ_FLAG)
    try:
        name = _target_name(raw, modality)
        payload = _payload_for(pressure, modality, name)
    except Exception:
        ## Belt and braces: `_target_name` is written not to raise, and if it ever does, silence is
        ## the correct outcome. A traceback here would reach the model through stderr.
        return 0

    try:
        sys.stdout.write(payload)
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
