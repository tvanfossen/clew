# SPDX-License-Identifier: MIT
"""A session identifier reached 259 pushed commits and nobody noticed.

Every one of those commits carries a `Claude-Session:` trailer holding a
`claude.ai/code/session_<id>` URL, and one pull-request body carried the same link. Not a
credential — a per-session identifier, published, 259 times.

**THE PROHIBITION HAD TO BECOME MECHANICAL, because the version that depended on remembering is
the version that failed.** Tooling can be configured to append such a trailer, and a tool's own
guidance is not the repository owner's. The owner's instruction was explicit: *"Absolutely cannot
be a trailer, and must be mechanically prevented."* The assistant co-author tag goes with it.

So the guard runs at `commit-msg`: the commit is refused as it is written, by the repository,
whatever told the author to add the line.

**HISTORY IS NOT REWRITTEN AND THAT IS DELIBERATE.** The published acceptance evidence pins
commit SHAs, `RESULTS.md` records `clew_commit`, and three release tags point into that history.
Rewriting it would invalidate the provenance the acceptance work exists to establish. The 259
stay; the 260th is refused.

@brief A commit message must not publish a session id or an assistant trailer.
@version 1
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


##
# @brief Load the guard script without making `scripts/` a package.
# @return The loaded module.
# @version 1
# @dg_internal
def _load() -> ModuleType:
    """@brief Load `scripts/commit_msg_guard.py`.
    @return The module.
    @version 1
    """
    path = REPO_ROOT / "scripts" / "commit_msg_guard.py"
    spec = importlib.util.spec_from_file_location("commit_msg_guard", path)
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load()


##
# @brief Every shape the leak actually took, and the ones it could take next, must be refused.
# @param message The offending commit message.
# @return None.
# @version 1
@pytest.mark.parametrize(
    "message",
    [
        pytest.param(
            "fix: a thing\n\nClaude-Session: https://claude.ai/code/session_01ABC\n",
            id="the-exact-trailer-that-shipped-259-times",
        ),
        pytest.param(
            "fix: a thing\n\nCo-Authored-By: Claude Opus 5 <noreply@anthropic.com>\n",
            id="assistant-co-author",
        ),
        pytest.param(
            "fix: a thing\n\nsee https://claude.ai/code/session_01ABC for context\n",
            id="link-in-prose-not-a-trailer",
        ),
        pytest.param(
            "fix: a thing\n\nSession: https://claude.ai/code/session_01ABC\n",
            id="renamed-trailer-key",
        ),
        pytest.param(
            "fix: a thing\n\n  claude-session:  https://claude.ai/code/session_01ABC\n",
            id="indented-and-lowercased",
        ),
        pytest.param(
            "fix: a thing\n\n\U0001f916 Generated with [Claude Code](https://claude.com/claude-code)\n",
            id="generated-with-footer",
        ),
    ],
)
def test_a_forbidden_message_is_refused(message: str, tmp_path: Path) -> None:
    """**MATCHED ON THE LINK, NOT ONLY ON THE TRAILER KEY.** Renaming the key to `Session:` or
    dropping the URL into prose publishes exactly the same identifier, so a guard that only knew
    one trailer name would be trivially defeated by the next tool that formats it differently.

    The indented and lowercased case is here because a trailer's whitespace and case are not under
    this repository's control.

    @brief Forbidden messages are refused.
    @param message The message.
    @return None.
    @version 1
    """
    path = tmp_path / "COMMIT_EDITMSG"
    path.write_text(message, encoding="utf-8")

    assert guard.main([str(path)]) == 1, f"this message was allowed through: {message!r}"


##
# @brief An ordinary message must pass, including one that merely mentions the assistant.
# @param message A legitimate commit message.
# @return None.
# @version 1
@pytest.mark.parametrize(
    "message",
    [
        pytest.param("fix: a thing\n\nA plain body.\n", id="plain"),
        pytest.param(
            "fix: the grader\n\nThe judge model is claude-sonnet-4-5-20250929, pinned.\n",
            id="names-a-model-id",
        ),
        pytest.param(
            "docs: note that an agent reads SKILLS.md\n\nAnthropic's CLI is the transport.\n",
            id="mentions-the-vendor-in-prose",
        ),
        pytest.param(
            "feat: a thing\n\nCo-Authored-By: A Human <human@example.com>\n",
            id="human-co-author-is-fine",
        ),
    ],
)
def test_an_ordinary_message_passes(message: str, tmp_path: Path) -> None:
    """**THE PERMISSIVE LEG IS WHAT KEEPS THE GUARD ALIVE.** A rule that refused any mention of
    the vendor would block commit messages about the judge model, about the CLI the harness shells
    out to, and about SKILLS.md — all of which this repository writes constantly. It would be
    switched off within a day and the real leak would come back behind it.

    A HUMAN co-author must still be allowed: the trailer itself is not the problem.

    @brief Legitimate messages pass.
    @param message The message.
    @return None.
    @version 1
    """
    path = tmp_path / "COMMIT_EDITMSG"
    path.write_text(message, encoding="utf-8")

    assert guard.main([str(path)]) == 0, f"a legitimate message was refused: {message!r}"


##
# @brief Every violation in one message must be reported together.
# @return None.
# @version 1
def test_all_violations_are_reported_at_once() -> None:
    """A message carrying both a trailer and a prose link should be fixed in ONE pass, not have
    the second discovered on the next attempt.

    @brief Violations are reported together.
    @return None.
    @version 1
    """
    message = (
        "fix: a thing\n\nsee https://claude.ai/code/session_01ABC\n"
        "Claude-Session: https://claude.ai/code/session_01ABC\n"
        "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>\n"
    )

    found = {name for name, _reason, _text in guard.violations(message)}

    assert {"session link", "session trailer", "assistant co-author trailer"} <= found, found


##
# @brief A missing or unreadable message file must fail, not pass.
# @param tmp_path Per-test temporary directory.
# @return None.
# @version 1
def test_a_misconfigured_hook_fails_rather_than_passing(tmp_path: Path) -> None:
    """**A BROKEN HOOK MUST NOT LOOK LIKE A CLEAN MESSAGE.** `commit-msg` is always handed a path,
    so no path — or an unreadable one — means the hook is wired wrong. Returning 0 there would
    make a guard that never runs indistinguishable from one that found nothing, which is the
    failure shape this repository returns to most often.

    @brief Misconfiguration fails closed.
    @return None.
    @version 1
    """
    assert guard.main([]) == 1, "a hook invoked with no message file reported success"
    assert guard.main([str(tmp_path / "does-not-exist")]) == 1, "an unreadable file passed"
