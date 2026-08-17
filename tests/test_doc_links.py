# SPDX-License-Identifier: MIT
"""Every relative link in the shipped documentation must resolve on disk.

THIS SHIPPED. The README carried two links to `acceptance/targets/mbedtls/1.0.0/` for weeks
after `2a141fe` deleted that directory, and the served MCP instructions cited the same dead
path as the provenance for its headline numbers. Nothing noticed, because a broken relative
link fails only when a human clicks it, and the humans who would click it are the outside
consumers this project does not have yet.

The rule is narrow on purpose. Only MARKDOWN LINK SYNTAX pointing at a RELATIVE PATH is
checked: prose that mentions a filename is not a promise that the file exists, while
`[text](path)` is. Anchors, URLs and `mailto:` are skipped — a link checker that needs the
network is a flaky test, and this project would rather have a gate that always runs.

@brief Relative documentation links resolve.
@version 1
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

## Markdown inline links. The path group deliberately excludes whitespace and `)` so a link
## with a title (`[a](b "t")`) yields just the path.
_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)")

## Documentation a reader is invited to follow. There is one file, and that is the point: the
## README is the only prose this repository asks a stranger to read and act on. Measured results
## live in `acceptance/` beside the transcripts that produced them, and the working-instructions
## file is untracked, because how someone instructs their own agent is theirs to maintain.
_DOCS = ("README.md",)

## A GitHub blob/tree URL pointing back into this repository, whose `<path>` must therefore
## exist in this tree. Any ref is accepted: pinning `main` here would fail every link on a
## branch, which is a gate firing on the ordinary case.
_SELF_TREE = re.compile(r"https://github\.com/tvanfossen/clew/(?:tree|blob)/[^/]+/(?P<path>.+?)/?$")


##
# @brief Collect unresolvable relative links from one markdown file.
# @param path markdown file
# @return list of (file, link) pairs that do not exist on disk
# @version 1
def _dead_links(path: Path) -> list[tuple[str, str]]:
    """Checks two kinds, and the second exists because absolutising the first emptied this
    check. The README's links had to become absolute so PyPI renders them, which left no
    relative link to verify — a gate that passes by having nothing to look at.

    A `.../tree/<ref>/<path>` URL into THIS repository names a path in this tree, so it is
    checkable exactly like a relative one. Links to other hosts are not: verifying them needs
    the network, and a test that needs the network is a test that goes red for someone else's
    outage.

    @brief Unresolvable links in one file, relative or self-referential.
    @return Offending (file, link) pairs.
    @version 2
    """
    if not path.is_file():
        return []
    dead = []
    for target in _LINK.findall(path.read_text(encoding="utf-8")):
        bare = target.split("#", 1)[0]
        own = _SELF_TREE.match(bare)
        if own:
            if not (REPO_ROOT / own["path"]).exists():
                dead.append((path.name, target))
            continue
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        if not (path.parent / bare).resolve().exists():
            dead.append((path.name, target))
    return dead


## @brief Every relative link in the shipped docs resolves.
## @return None.
## @version 1
def test_shipped_documentation_has_no_dead_relative_links() -> None:
    """@brief Shipped docs contain no dead relative links. @return None. @version 1"""
    offenders = [pair for name in _DOCS for pair in _dead_links(REPO_ROOT / name)]
    assert not offenders, (
        f"documentation links a reader is invited to follow, pointing at paths that do not "
        f"exist: {offenders}"
    )


## @brief The checker itself must be able to fail.
## @param tmp_path Pytest temp dir.
## @return None.
## @version 1
def test_the_link_checker_detects_a_dead_link(tmp_path: Path) -> None:
    """THE CONTROL, because a link checker that silently matches nothing passes every repository
    including a broken one. This project has shipped a vacuous gate before — a pathspec whose `**`
    did not recurse passed on 62% of the package unread.

    Asserts both halves: a real path is accepted and a missing one is caught.

    @brief The link checker fails on a dead link and passes a live one.
    @return None.
    @version 1
    """
    doc = tmp_path / "doc.md"
    (tmp_path / "here.md").write_text("x")
    doc.write_text(
        "see [live](here.md) and [dead](acceptance/targets/mbedtls/1.0.0/) and "
        "[remote](https://example.invalid/x) and [anchor](#section)\n"
    )
    assert _dead_links(doc) == [("doc.md", "acceptance/targets/mbedtls/1.0.0/")], (
        "the checker must catch the dead path, accept the live one, and skip URLs and anchors"
    )
