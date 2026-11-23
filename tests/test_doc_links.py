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

@brief Relative documentation links and their anchors resolve.
@version 2
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
## EVERY SHIPPED DOCUMENT (round 3, P6): the root's and docs/'s Markdown, not the two files this
## started with — the docs pass found a README anchor pointing at a renamed heading.
_DOCS = tuple(
    sorted(
        p.relative_to(REPO_ROOT).as_posix()
        for p in (*REPO_ROOT.glob("*.md"), *(REPO_ROOT / "docs").glob("*.md"))
    )
)
## A Markdown heading line.
_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$", re.M)

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
    """ANCHORS TOO (round 3, P6): a link to `FILE.md#heading` or `#heading` must name a heading
    that file has — renaming a heading broke one and nothing noticed.

    Checks two kinds, and the second exists because absolutising the first emptied this
    check. The README's links had to become absolute so PyPI renders them, which left no
    relative link to verify — a gate that passes by having nothing to look at.

    A `.../tree/<ref>/<path>` URL into THIS repository names a path in this tree, so it is
    checkable exactly like a relative one. Links to other hosts are not: verifying them needs
    the network, and a test that needs the network is a test that goes red for someone else's
    outage.

    @brief Unresolvable links in one file, relative or self-referential.
    @return Offending (file, link) pairs.
    @version 3
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
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        linked = path if target.startswith("#") else (path.parent / bare).resolve()
        if not linked.exists():
            dead.append((path.name, target))
        elif "#" in target and linked.suffix == ".md":
            if target.split("#", 1)[1] not in _anchors(linked):
                dead.append((path.name, target))
    return dead


# @brief The anchors GitHub gives a Markdown file's headings.
# @param path The file.
# @return Anchor slugs (a repeated heading gets `-1`, `-2`, … as GitHub numbers them).
# @version 1
def _anchors(path: Path) -> set[str]:
    """GITHUB'S SLUG: lower-cased, punctuation dropped except `-` and `_`, spaces to `-`; inline
    code and links keep their text.

    @brief Heading anchors.
    @return Slugs.
    """
    seen: dict[str, int] = {}
    out = set()
    for heading in _HEADING.findall(path.read_text(encoding="utf-8")):
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading).replace("`", "")
        slug = re.sub(r"[^\w\- ]", "", text.lower()).replace(" ", "-")
        n = seen.get(slug, 0)
        out.add(slug if n == 0 else f"{slug}-{n}")
        seen[slug] = n + 1
    return out


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
    @version 2
    """
    ## Round 3, P6: anchors are checked now — a live one passes, a dead one (here or in another
    ## file) is caught; URLs are still skipped (no network in a test).
    doc = tmp_path / "doc.md"
    (tmp_path / "here.md").write_text("# Top\n\n## A `code` section\n")
    doc.write_text(
        "# Section\n\nsee [live](here.md) and [dead](acceptance/targets/mbedtls/1.0.0/) and "
        "[remote](https://example.invalid/x) and [anchor](#section) and "
        "[there](here.md#a-code-section) and [gone](here.md#nope) and [lost](#missing)\n"
    )
    assert _dead_links(doc) == [
        ("doc.md", "acceptance/targets/mbedtls/1.0.0/"),
        ("doc.md", "here.md#nope"),
        ("doc.md", "#missing"),
    ], "the checker must catch dead paths and anchors, accept live ones, and skip URLs"
