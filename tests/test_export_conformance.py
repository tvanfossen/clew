# SPDX-License-Identifier: MIT
"""Each wiki export conforms to its format (PS4, owner Q/A 2026-11-19).

PS4: the wiki's exports are covered by semver as FORMAT CONFORMANCE ONLY — "a valid <format>
<version>" — while their contents follow the repository. One test per format, so a change that
breaks a format fails here by name:

| export | format | version pinned |
|---|---|---|
| `exports/requirements.reqif` | ReqIF (OMG) | 1.2 schema namespace `ReqIF/20110401` |
| `exports/needs.json` | Sphinx-needs | its `versions` / `current_version` layout |
| `exports/system.dsl` | Structurizr DSL | a `workspace` block |
| `exports/flows/*.mmd` | Mermaid | `sequenceDiagram` |
| `exports/flows/*.puml` | PlantUML | `@startuml` … `@enduml` |
| `exports/flows/*.dot` | Graphviz DOT | a `digraph` |
| `llms.txt` | llms.txt | an H1 title, then Markdown links |

@brief Tests format conformance of every wiki export.
@version 1
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from tests.test_wiki_site import repo, site  # noqa: F401  (module fixtures reused)

_REQIF_NS = "http://www.omg.org/spec/ReqIF/20110401/reqif.xsd"


def _html(site: dict[str, str]) -> Path:  # noqa: F811
    return Path(site["__html__"])


def _balanced(text: str) -> bool:
    """@brief Braces balance and never go negative. @return Flag."""
    depth = 0
    for ch in text:
        depth += {"{": 1, "}": -1}.get(ch, 0)
        if depth < 0:
            return False
    return depth == 0


def test_reqif_is_well_formed_reqif_1_2(site: dict[str, str]) -> None:  # noqa: F811
    """@brief ReqIF: parses as XML, root `REQ-IF` in the ReqIF 1.2 namespace."""
    root = ET.parse(_html(site) / "exports" / "requirements.reqif").getroot()
    assert root.tag == f"{{{_REQIF_NS}}}REQ-IF"


def test_needs_json_has_the_sphinx_needs_layout(site: dict[str, str]) -> None:  # noqa: F811
    """@brief Sphinx-needs: `current_version` names a key of `versions`, which holds `needs`."""
    doc = json.loads((_html(site) / "exports" / "needs.json").read_text())
    assert doc["current_version"] in doc["versions"]
    assert isinstance(doc["versions"][doc["current_version"]]["needs"], dict)


def test_structurizr_dsl_is_one_balanced_workspace(site: dict[str, str]) -> None:  # noqa: F811
    """@brief Structurizr DSL: starts with `workspace`, braces balanced."""
    text = (_html(site) / "exports" / "system.dsl").read_text()
    assert text.lstrip().startswith("workspace") and _balanced(text)


def test_mermaid_flows_are_sequence_diagrams(site: dict[str, str]) -> None:  # noqa: F811
    """@brief Mermaid: every flow export opens with `sequenceDiagram`."""
    files = list((_html(site) / "exports" / "flows").glob("*.mmd"))
    assert files and all(f.read_text().lstrip().startswith("sequenceDiagram") for f in files)


def test_plantuml_flows_are_bracketed(site: dict[str, str]) -> None:  # noqa: F811
    """@brief PlantUML: every flow export is `@startuml` … `@enduml`."""
    files = list((_html(site) / "exports" / "flows").glob("*.puml"))
    for f in files:
        text = f.read_text().strip()
        assert text.startswith("@startuml") and text.endswith("@enduml"), f.name
    assert files


def test_dot_flows_are_balanced_digraphs(site: dict[str, str]) -> None:  # noqa: F811
    """@brief Graphviz DOT: every flow export is a `digraph` with balanced braces."""
    files = list((_html(site) / "exports" / "flows").glob("*.dot"))
    assert files and all(
        f.read_text().startswith("digraph ") and _balanced(f.read_text()) for f in files
    )


def test_llms_txt_opens_with_its_title(site: dict[str, str]) -> None:  # noqa: F811
    """@brief llms.txt: an H1 title first, then Markdown links."""
    text = (_html(site) / "llms.txt").read_text()
    assert text.startswith("# ") and "](" in text
