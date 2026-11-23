# SPDX-License-Identifier: MIT
"""The impact report says who reviews each affected requirement (2.0.0, S2/S3 served).

The report named the requirements a change touches and the functions that changed, and stopped
there; the question a reviewer-assigning author asks next ("who has to look at this") was in the
repository's CODEOWNERS or MAINTAINERS file, and the gate never read it. It now does, through the
same `owners.OwnerResolver` the index's `owners` layer uses, so the gate and a dossier cannot
name different owners for one file. The gate needs no index for this.

ABSENT WHEN THERE IS NO OWNERS FILE: `reviewers` is left out of the JSON and the markdown has no
Reviewers column, because "nobody" and "this repository names no owners" are different answers.

@brief Tests reviewers in the impact report.
@version 1
"""

from __future__ import annotations

import json
from pathlib import Path

from clew.guard.impact import ChangedFunction, build_impact_report, format_json, format_markdown
from clew.owners import OwnerResolver

_CONFIG: dict = {}


def _changed() -> list[ChangedFunction]:
    """@brief Two functions under one requirement, in two owned areas. @return Changes."""
    return [
        ChangedFunction(name="sock_open", file_path="src/net/socket.c", reqs=["REQ-NET-001"]),
        ChangedFunction(name="util_helper", file_path="src/util.c", reqs=["REQ-NET-001"]),
    ]


def test_each_requirement_names_the_owners_of_the_changed_files(tmp_path: Path) -> None:
    """@brief The union of both files' owners, in first-seen order."""
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github/CODEOWNERS").write_text("* @core\n/src/net/ @net-team\n")
    resolver = OwnerResolver.from_repo(tmp_path)
    (entry,) = build_impact_report(_changed(), _CONFIG, owners=resolver)
    assert entry.reviewers == ["@net-team", "@core"]
    ## SPEC CHANGED (2.0.0, PS3): entries live under `entries` beside `schema_version`.
    assert json.loads(format_json([entry]))["entries"][0]["reviewers"] == ["@net-team", "@core"]
    assert "| Reviewers |" in format_markdown([entry])


def test_no_owners_file_leaves_reviewers_out_rather_than_empty(tmp_path: Path) -> None:
    """@brief No CODEOWNERS or MAINTAINERS: no key, no column."""
    resolver = OwnerResolver.from_repo(tmp_path)
    (entry,) = build_impact_report(_changed(), _CONFIG, owners=resolver)
    assert entry.reviewers is None
    assert "reviewers" not in json.loads(format_json([entry]))["entries"][0]
    assert "Reviewers" not in format_markdown([entry])


def test_impact_json_names_its_schema_version() -> None:
    """PS3: the report is an object carrying `schema_version`, its entries under `entries`.

    @brief impact.json is versioned.
    """
    import json

    from clew.guard.impact import IMPACT_SCHEMA_VERSION, format_json

    doc = json.loads(format_json([]))
    assert doc == {"schema_version": IMPACT_SCHEMA_VERSION, "entries": []}
