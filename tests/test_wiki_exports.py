# SPDX-License-Identifier: MIT
"""The site's exports (round 3, P3b): other tools' formats, generated from the same trace.

Owner 2026-11-15 (interop): ReqIF, Sphinx-needs `needs.json`, Structurizr DSL; and the plan's
Mermaid / PlantUML sequence diagrams (for wikis that render them: ADO, GitHub) and llms.txt /
llms-full.txt (the agent-facing index of the site). Every export ships IN the built site under
`exports/` (llms*.txt at its root, where that convention looks), and every one obeys the build's
audience: no requirement text under `exclude_requirement_text`.

@brief Tests for the exports.
@version 1
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from tests.test_wiki_site import repo, site  # noqa: F401  (module fixtures reused)

_REQIF = "{http://www.omg.org/spec/ReqIF/20110401/reqif.xsd}"


def _html(site: dict[str, str]) -> Path:  # noqa: F811
    return Path(site["__html__"])


def test_flows_export_as_mermaid_and_plantuml(site: dict[str, str]) -> None:  # noqa: F811
    """@brief Mermaid and PlantUML sequence diagrams with the loop frame, linked from the page."""
    html = _html(site)
    mmd = (html / "exports/flows/flow-load.mmd").read_text()
    assert mmd.startswith("sequenceDiagram") and "autonumber" in mmd
    assert "->>" in mmd and ": parse" in mmd and "loop" in mmd and "\n    end" in mmd
    assert mmd.index("loop") < mmd.index(": parse") < mmd.index("end")
    puml = (html / "exports/flows/flow-load.puml").read_text()
    assert puml.startswith("@startuml") and puml.rstrip().endswith("@enduml") and "loop" in puml
    page = site["flow-load.html"]
    assert (
        'href="exports/flows/flow-load.mmd"' in page
        and 'href="exports/flows/flow-load.puml"' in page
    )


def test_llms_txt_indexes_the_site_and_llms_full_carries_it(site: dict[str, str]) -> None:  # noqa: F811
    """@brief llms.txt (an H1, a summary quote, linked sections) and llms-full.txt (dense text)."""
    html = _html(site)
    index = (html / "llms.txt").read_text()
    assert index.startswith("# Site Demo\n") and "\n> " in index
    assert (
        "## Requirements" in index
        and "(requirements.html)" in index
        and "(flow-load.html)" in index
    )
    full = (html / "llms-full.txt").read_text()
    assert "REQ-W-001" in full and "PASS" in full and "load -> parse" in full


def test_requirements_export_as_reqif(site: dict[str, str]) -> None:  # noqa: F811
    """@brief ReqIF 1.2: one SPEC-OBJECT per requirement with its id, title and tier."""
    root = ET.parse(_html(site) / "exports/requirements.reqif").getroot()
    assert root.tag == f"{_REQIF}REQ-IF"
    objects = root.findall(f".//{_REQIF}SPEC-OBJECT")
    values = {
        v.get("THE-VALUE") for o in objects for v in o.findall(f".//{_REQIF}ATTRIBUTE-VALUE-STRING")
    }
    assert len(objects) == 3 and {"REQ-W-001", "Load the data", "PASS"} <= values
    assert root.findall(f".//{_REQIF}SPECIFICATION")


def test_requirements_export_as_sphinx_needs(site: dict[str, str]) -> None:  # noqa: F811
    """@brief needs.json: a version holding one need per requirement, typed `req`."""
    data = json.loads((_html(site) / "exports/needs.json").read_text())
    version = data["versions"][data["current_version"]]
    need = version["needs"]["REQ-W-001"]
    assert need["type"] == "req" and need["title"] == "Load the data"
    assert "Every item is parsed once" in need["content"] and version["needs_amount"] == 3


def test_the_system_exports_as_structurizr(site: dict[str, str]) -> None:  # noqa: F811
    """@brief Structurizr DSL: a software system, a container per component, a relation per link."""
    dsl = (_html(site) / "exports/system.dsl").read_text()
    assert dsl.startswith("workspace") and "softwareSystem" in dsl
    assert 'container "src"' in dsl and "views" in dsl and "autolayout" in dsl


def test_exports_obey_the_audience(repo: tuple[Path, Path], tmp_path: Path) -> None:  # noqa: F811
    """@brief `exclude_requirement_text` keeps titles and criteria out of every export."""
    from clew.wiki.build import build_wiki

    html = build_wiki(repo[0], repo[1], tmp_path / "out", audience="public")
    for rel in ("exports/requirements.reqif", "exports/needs.json", "llms-full.txt"):
        text = (html / rel).read_text()
        assert "Load the data" not in text and "Every item is parsed once" not in text, rel
        assert "REQ-W-001" in text, rel
