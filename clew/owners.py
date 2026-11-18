# SPDX-License-Identifier: MIT
"""Who owns a file: CODEOWNERS and kernel-style MAINTAINERS, read into one `owners` layer (S2, S3).

2.0.0 (owner 2026-11-17, prior-art adoptions). Two conventions a repository already keeps, read
as they are written rather than restated in `.clew.yaml`:

  * CODEOWNERS (GitHub / GitLab / Bitbucket) — gitignore-style patterns, one per line, each
    followed by owners. THE LAST MATCHING LINE WINS, and all of its owners apply. Looked for at
    `.github/CODEOWNERS`, `CODEOWNERS`, `docs/CODEOWNERS`, `.gitlab/CODEOWNERS` (GitHub's own
    order), unless `owners.codeowners` names the file.
  * MAINTAINERS (Linux, and the QEMU / U-Boot / coreboot family) — stanzas separated by blank
    lines, a title line, then `X:\\tvalue` records: `M:` maintainer, `R:` reviewer, `F:` a file
    pattern (a trailing `/` is the directory and everything below; `*` matches within one
    directory level), `X:` an exclusion, `N:` a regex over the path. EVERY matching stanza
    applies, so a file can have several. Looked for at `MAINTAINERS` unless
    `owners.maintainers` names the file.

OWNER HANDLES ARE PERSONAL DATA. The layer stores what the repository published; the wiki routes
them through audience redaction (`Audience.exclude_owners`) before anything leaves the index.

@brief The owners layer.
@version 1
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from ._common import logger, within_repo

## Where CODEOWNERS is looked for, in GitHub's own order (the first one found is used).
CODEOWNERS_PATHS = (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS", ".gitlab/CODEOWNERS")
## Where MAINTAINERS is looked for.
MAINTAINERS_PATHS = ("MAINTAINERS",)
## The `owners:` section's keys (declaration.SECTION_KEYS pins the same set).
OWNERS_KEYS = frozenset({"codeowners", "maintainers"})
## Roles a row records: CODEOWNERS owners, MAINTAINERS `M:` and `R:`.
ROLE_OWNER, ROLE_MAINTAINER, ROLE_REVIEWER = "owner", "maintainer", "reviewer"
SOURCE_CODEOWNERS, SOURCE_MAINTAINERS = "codeowners", "maintainers"

_DDL = """
CREATE TABLE IF NOT EXISTS owners (
    path_rowid INTEGER NOT NULL,
    owner TEXT NOT NULL,
    role TEXT NOT NULL,
    source TEXT NOT NULL,
    rule_line INTEGER NOT NULL,
    stanza TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS owners_path ON owners(path_rowid);
"""


## @brief One CODEOWNERS rule: a gitignore-style pattern, its owners, and its line.
## @version 1
class _CodeownersRule:
    ## @brief Hold the rule.
    ## @param pattern The pattern as written.
    ## @param owners Its owners.
    ## @param line Its 1-based line.
    ## @version 1
    ## @dg_internal
    def __init__(self, pattern: str, owners: list[str], line: int) -> None:
        """@brief Store. @return None."""
        self.pattern, self.owners, self.line = pattern, owners, line
        self.regex = _codeowners_regex(pattern)


## @brief A CODEOWNERS pattern as a regex over a repo-relative path.
## @param pattern The pattern.
## @return The regex.
## @version 1
## @dg_internal
def _codeowners_regex(pattern: str) -> re.Pattern[str]:
    """GITIGNORE RULES, as CODEOWNERS documents them: a leading `/` anchors at the root; a pattern
    with no other `/` matches at any depth; a trailing `/` (or no glob at all, for a directory)
    matches everything below; `*` stays inside one path segment and `**` crosses them.

    @brief Translate a CODEOWNERS pattern.
    @return Regex.
    """
    anchored = pattern.startswith("/") or "/" in pattern.rstrip("/")
    body = pattern.strip("/")
    out = ""
    i = 0
    while i < len(body):
        if body.startswith("**", i):
            out += ".*"
            i += 2
        elif body[i] == "*":
            out += "[^/]*"
            i += 1
        elif body[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(body[i])
            i += 1
    prefix = "" if anchored else "(?:.*/)?"
    return re.compile(f"^{prefix}{out}(?:/.*)?$")


## @brief The rules of a CODEOWNERS file.
## @param text The file.
## @return Rules, in file order.
## @version 1
## @dg_internal
def parse_codeowners(text: str) -> list[_CodeownersRule]:
    """A line is `pattern owner...`; `#` starts a comment; a line with no owners is a rule that
    UNSETS ownership (GitHub's documented meaning), kept so the last-match rule still sees it.

    @brief Parse CODEOWNERS.
    @return Rules.
    """
    rules = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip() if not raw.lstrip().startswith("\\#") else raw.strip()
        if not line:
            continue
        pattern, *owners = line.split()
        rules.append(_CodeownersRule(pattern, owners, number))
    return rules


## @brief The owners CODEOWNERS gives one path: the LAST matching rule's.
## @param rules The parsed rules.
## @param rel Repo-relative path.
## @return (owners, line), or None when no rule matches.
## @version 1
## @dg_internal
def codeowners_for(rules: list[_CodeownersRule], rel: str) -> tuple[list[str], int] | None:
    """@brief Apply the last-match rule. @return Owners and line, or None."""
    for rule in reversed(rules):
        if rule.regex.match(rel):
            return rule.owners, rule.line
    return None


## @brief One MAINTAINERS stanza.
## @version 1
class _Stanza:
    ## @brief Hold the stanza.
    ## @param title Its title line.
    ## @param line Its first line.
    ## @version 1
    ## @dg_internal
    def __init__(self, title: str, line: int) -> None:
        """@brief Store. @return None."""
        self.title, self.line = title, line
        self.people: list[tuple[str, str]] = []
        self.files: list[re.Pattern[str]] = []
        self.excludes: list[re.Pattern[str]] = []
        self.names: list[re.Pattern[str]] = []

    ## @brief Whether this stanza covers a path.
    ## @param rel Repo-relative path.
    ## @return True when an F: or N: matches and no X: does.
    ## @version 1
    ## @dg_internal
    def covers(self, rel: str) -> bool:
        """@brief Match. @return Covered."""
        hit = any(f.match(rel) for f in self.files) or any(n.search(rel) for n in self.names)
        return hit and not any(x.match(rel) for x in self.excludes)


## @brief A MAINTAINERS `F:` / `X:` pattern as a regex.
## @param pattern The pattern.
## @return The regex.
## @version 1
## @dg_internal
def _maintainers_regex(pattern: str) -> re.Pattern[str]:
    """The kernel's rules (Documentation/process/maintainers.rst): a trailing `/` is the directory
    and everything below; `*` and `?` match within one level; anything else is that file.

    @brief Translate an F:/X: pattern.
    @return Regex.
    """
    body = re.escape(pattern.rstrip("/")).replace(r"\*", "[^/]*").replace(r"\?", "[^/]")
    tail = "(?:/.*)?" if pattern.endswith("/") else ""
    return re.compile(f"^{body}{tail}$")


## @brief The stanzas of a MAINTAINERS file.
## @param text The file.
## @return Stanzas with at least one file record.
## @version 1
## @dg_internal
def parse_maintainers(text: str) -> list[_Stanza]:
    """A stanza is a title line followed by `X:` records, ended by a blank line; the preamble
    before the first record-bearing stanza (the file's own prose) carries no records and drops.

    @brief Parse MAINTAINERS.
    @return Stanzas.
    """
    stanzas: list[_Stanza] = []
    current: _Stanza | None = None
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip()
        match = re.match(r"^([A-Z]):\s*(.*)$", line)
        if not line:
            current = None
        elif match and current is not None:
            _record(current, match.group(1), match.group(2).strip())
        elif not match:
            current = _Stanza(line.strip(), number)
            stanzas.append(current)
    return [s for s in stanzas if s.files or s.names]


## @brief Apply one record to its stanza.
## @param stanza The stanza.
## @param kind The record letter.
## @param value Its value.
## @return None.
## @version 1
## @dg_internal
def _record(stanza: _Stanza, kind: str, value: str) -> None:
    """@brief Record. @return None."""
    if kind in ("M", "R") and value:
        stanza.people.append((value, ROLE_MAINTAINER if kind == "M" else ROLE_REVIEWER))
    elif kind == "F" and value:
        stanza.files.append(_maintainers_regex(value))
    elif kind == "X" and value:
        stanza.excludes.append(_maintainers_regex(value))
    elif kind == "N" and value:
        try:
            stanza.names.append(re.compile(value))
        except re.error:
            logger.warning(
                "owners: MAINTAINERS stanza %r has an invalid N: regex %r", stanza.title, value
            )


## @brief The file one convention reads: declared, else the first conventional location found.
## @param repo_root The repository.
## @param declared The `owners.<key>` value, or None.
## @param candidates Conventional locations.
## @param key The key, for the message.
## @return The file, or None.
## @version 1
## @dg_internal
def _locate(repo_root: Path, declared: Any, candidates: tuple[str, ...], key: str) -> Path | None:
    """A DECLARED path that does not exist is said, not silently replaced by a conventional one.

    @brief Locate an owners file.
    @return Path or None.
    """
    if declared:
        found = within_repo(repo_root / str(declared), repo_root, setting=f"owners.{key}")
        if found is None or not found.is_file():
            logger.warning(
                "owners: owners.%s names %s, which is not a file in the repository", key, declared
            )
            return None
        return found
    return next((repo_root / c for c in candidates if (repo_root / c).is_file()), None)


## @brief The repository's ownership rules, located and parsed once, asked per file.
## @version 1
class OwnerResolver:
    """ONE RESOLVER FOR THE INDEX AND THE GATE (2.0.0). `record_owners` writes the `owners` layer
    with it and `clew guard impact` names reviewers with it, so a dossier and an impact report can
    never name different owners for one file. The gate needs no index to use it.

    @brief CODEOWNERS + MAINTAINERS resolver.
    @version 1
    """

    ## @brief Hold parsed rules.
    ## @param rules CODEOWNERS rules.
    ## @param stanzas MAINTAINERS stanzas.
    ## @param sources The files read, for the log.
    ## @version 1
    ## @dg_internal
    def __init__(self, rules: list, stanzas: list, sources: list[Path]) -> None:
        self.rules = rules
        self.stanzas = stanzas
        self.sources = sources

    ## @brief Locate and parse the repository's owners files.
    ## @param repo_root The repository.
    ## @param section The `owners:` declaration section, or None.
    ## @return The resolver.
    ## @version 1
    ## @req REQ-DDB-INDEX-007
    @classmethod
    def from_repo(cls, repo_root: Path, section: dict | None = None) -> OwnerResolver:
        """@brief Read the owners files. @return Resolver."""
        section = section or {}
        root = Path(repo_root)
        co = _locate(root, section.get("codeowners"), CODEOWNERS_PATHS, "codeowners")
        mt = _locate(root, section.get("maintainers"), MAINTAINERS_PATHS, "maintainers")
        rules = parse_codeowners(co.read_text(encoding="utf-8", errors="replace")) if co else []
        stanzas = parse_maintainers(mt.read_text(encoding="utf-8", errors="replace")) if mt else []
        return cls(rules, stanzas, [p for p in (co, mt) if p])

    ## @brief Whether the repository keeps any owners file.
    ## @return True when one was read.
    ## @version 1
    ## @dg_internal
    def has_sources(self) -> bool:
        """@brief Any owners file. @return True when read."""
        return bool(self.sources)

    ## @brief One file's owners.
    ## @param rel The file, repo-relative.
    ## @return (owner, role, source, rule line, stanza), in rule order.
    ## @version 1
    ## @req REQ-DDB-INDEX-007
    def owners_of(self, rel: str) -> list[tuple[str, str, str, int, str]]:
        """@brief Resolve one path. @return Owner tuples."""
        return [row[1:] for row in _rows_for(0, rel, self.rules, self.stanzas)]


## @brief Read CODEOWNERS and MAINTAINERS and record every indexed file's owners.
## @param conn Open index connection.
## @param repo_root The repository.
## @param section The `owners:` declaration section, or None.
## @return Rows written.
## v2: through `OwnerResolver`, shared with the gate's impact report (2.0.0)
## @version 2
## @req REQ-DDB-INDEX-007
def record_owners(conn: sqlite3.Connection, repo_root: Path, section: dict | None = None) -> int:
    """THE TABLE IS ALWAYS CREATED, empty when the repository keeps neither file: empty means "we
    looked and nobody is named", absent would mean "this layer never ran".

    @brief Build the owners layer.
    @return Row count.
    """
    conn.executescript(_DDL)
    conn.execute("DELETE FROM owners")
    resolver = OwnerResolver.from_repo(repo_root, section)
    rows = []
    for rowid, rel in conn.execute("SELECT rowid, name FROM path WHERE type = 1"):
        rows += _rows_for(int(rowid), str(rel), resolver.rules, resolver.stanzas)
    conn.executemany(
        "INSERT INTO owners(path_rowid, owner, role, source, rule_line, stanza) VALUES (?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    logger.info(
        "owners: %d row(s) from %s",
        len(rows),
        ", ".join(str(p.name) for p in resolver.sources) or "no owners file",
    )
    return len(rows)


## @brief One file's owner rows.
## @param rowid Its path rowid.
## @param rel Its path.
## @param rules CODEOWNERS rules.
## @param stanzas MAINTAINERS stanzas.
## @return Rows.
## @version 1
## @dg_internal
def _rows_for(rowid: int, rel: str, rules: list, stanzas: list) -> list[tuple]:
    """@brief Rows for one path. @return Rows."""
    out = []
    found = codeowners_for(rules, rel) if rules else None
    if found:
        out += [(rowid, o, ROLE_OWNER, SOURCE_CODEOWNERS, found[1], "") for o in found[0]]
    for stanza in stanzas:
        if stanza.covers(rel):
            out += [
                (rowid, who, role, SOURCE_MAINTAINERS, stanza.line, stanza.title)
                for who, role in stanza.people
            ]
    return out
