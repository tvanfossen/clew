# SPDX-License-Identifier: MIT
"""REFUSE A COMMIT MESSAGE THAT WOULD PUBLISH A SESSION IDENTIFIER OR AN ASSISTANT TRAILER.

WHY IT EXISTS. 259 commits in this repository's pushed history carry a `Claude-Session:` trailer
holding a `claude.ai/code/session_<id>` URL, and one pull request body carried the same link. The
session id is not a credential, but it is a per-session identifier that ended up in a public
repository and nobody noticed for 259 commits. The owner's instruction is that it must never
appear again, and that the prohibition must be MECHANICAL rather than remembered:

    "Absolutely cannot be a trailer, and must be mechanically prevented."

The co-author trailer goes too, by the same instruction. Both are matched here.

**A RULE THAT DEPENDS ON THE AUTHOR REMEMBERING IT IS THE RULE THAT FAILED.** Tooling can be
configured to add these lines, and a tool's own guidance is not the owner's: the harness
instructing an agent to append a trailer is exactly how the 259 accumulated. So this is a
`commit-msg` hook — the commit is refused at the moment it is written, by the repository, whatever
told the author to add the line.

WHAT IT DOES NOT DO. It does not scan history, because history cannot be rewritten here: the
published acceptance evidence pins commit SHAs, `RESULTS.md` records `clew_commit`, and three
release tags point into it. Rewriting would invalidate the provenance the acceptance work exists
to establish. The 259 stay; the 260th is refused.

Usage (pre-commit wires this for you):
    .venv/bin/python scripts/commit_msg_guard.py .git/COMMIT_EDITMSG
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

## Each entry is (name, pattern, why it is refused). Patterns are case-insensitive and matched
## against the whole message, so a trailer that moves line or gains whitespace is still caught.
##
## MATCHED ON THE LINK ITSELF, NOT ONLY ON THE TRAILER KEY. The leak is the URL, and renaming the
## key to `Session:` or embedding the link in prose would publish exactly the same identifier.
_FORBIDDEN: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "session link",
        re.compile(r"claude\.ai/code/session[_/-]?\S*", re.IGNORECASE),
        "a per-session identifier that must not be published; 259 commits already carry one",
    ),
    (
        "session trailer",
        re.compile(r"^\s*claude[-_]session\s*:", re.IGNORECASE | re.MULTILINE),
        "the trailer that carried the session link",
    ),
    (
        "assistant co-author trailer",
        re.compile(r"^\s*co-authored-by\s*:.*(claude|anthropic)", re.IGNORECASE | re.MULTILINE),
        "the owner's instruction is that the assistant tag is removed going forward",
    ),
    (
        "generated-with footer",
        re.compile(r"generated with \[?claude", re.IGNORECASE),
        "same instruction: no assistant attribution footer",
    ),
)


##
# @brief Every forbidden pattern a message matches.
# @param message The full commit message text.
# @return List of (name, reason, the matched text) for each hit.
# @version 1
def violations(message: str) -> list[tuple[str, str, str]]:
    """RETURNS ALL OF THEM, not the first. A message carrying both a trailer and a prose link
    should be reported once with both, so the author fixes it in one pass instead of discovering
    the second on the next attempt.

    The matched TEXT is returned so the message can quote what it found — a refusal naming only a
    rule leaves the author hunting for the line.

    @brief Forbidden patterns present in a message.
    @param message The commit message.
    @return Triples of name, reason and matched text.
    @version 1
    """
    found: list[tuple[str, str, str]] = []
    for name, pattern, reason in _FORBIDDEN:
        match = pattern.search(message)
        if match:
            found.append((name, reason, match.group(0).strip()))
    return found


##
# @brief Check a commit-message file and refuse it if it carries a forbidden line.
# @param argv Paths to check; pre-commit passes the message file.
# @return 0 when clean, 1 when a forbidden line is present.
# @version 1
def main(argv: list[str] | None = None) -> int:
    """A MISSING FILE IS NOT A PASS. `commit-msg` is always handed a path, so a path that cannot be
    read means the hook was wired wrong — and returning 0 there would make a broken hook
    indistinguishable from a clean message, which is this repository's most-repeated defect shape.

    Single exit point, by the returns-per-function limit this repository enforces.

    @brief Guard one or more commit-message files.
    @param argv The paths.
    @return Process exit code.
    @version 1
    """
    paths = list(sys.argv[1:] if argv is None else argv)
    if not paths:
        print("commit-msg guard: no message file given; the hook is misconfigured", file=sys.stderr)
        return 1

    failed = False
    for name in paths:
        path = Path(name)
        try:
            message = path.read_text("utf-8", errors="replace")
        except OSError as exc:
            print(f"commit-msg guard: cannot read {name}: {exc}", file=sys.stderr)
            failed = True
            continue
        hits = violations(message)
        if not hits:
            continue
        failed = True
        print(f"REFUSED — {name} carries {len(hits)} forbidden line(s):", file=sys.stderr)
        for label, reason, text in hits:
            print(f"  {label}: {text!r}", file=sys.stderr)
            print(f"      {reason}", file=sys.stderr)
        print(
            "\nRemove them and commit again. These are refused by the repository, not by a "
            "style preference — whatever tooling suggested the line, it does not get to add it.",
            file=sys.stderr,
        )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
