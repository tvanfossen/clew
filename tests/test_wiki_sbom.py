# SPDX-License-Identifier: MIT
"""The SBOM page: the repository's own SBOM rendered, beside its files' licences (#70, P5.8).

Issue #70: render each repo's SBOM — SPDX 2.3 JSON primary (ISO/IEC 5962:2021), CycloneDX JSON
optional (ECMA-424) — as a first-class page: a component table (name, version, licence, kind,
source, digest), the package licence and the accepted-licence list, with NOASSERTION and
not-accepted components flagged. READ-ONLY: the wiki never generates or edits an SBOM. Owner Q/A
2026-11-20 added beside it the index's own per-file SPDX licence layer (S5).

@brief Tests the SBOM page.
@version 1
"""

from __future__ import annotations

import json

from clew.wiki.sbom import Component, read_sbom, sbom_html

_SPDX = {
    "spdxVersion": "SPDX-2.3",
    "name": "demo",
    "documentDescribes": ["SPDXRef-demo"],
    "packages": [
        {
            "SPDXID": "SPDXRef-demo",
            "name": "demo",
            "versionInfo": "1.2.0",
            "licenseDeclared": "MIT",
            "downloadLocation": "NOASSERTION",
        },
        {
            "SPDXID": "SPDXRef-zlib",
            "name": "zlib",
            "versionInfo": "1.3.1",
            "licenseConcluded": "Zlib",
            "primaryPackagePurpose": "LIBRARY",
            "downloadLocation": "https://example.invalid/zlib.tar.gz",
            "checksums": [{"algorithm": "SHA256", "checksumValue": "ab12"}],
        },
        {
            "SPDXID": "SPDXRef-blob",
            "name": "weights",
            "versionInfo": "r7",
            "licenseConcluded": "NOASSERTION",
            "primaryPackagePurpose": "FILE",
            "downloadLocation": "NOASSERTION",
        },
    ],
}

_CDX = {
    "bomFormat": "CycloneDX",
    "specVersion": "1.5",
    "metadata": {"component": {"name": "demo", "licenses": [{"license": {"id": "MIT"}}]}},
    "components": [
        {
            "type": "library",
            "name": "left-pad",
            "version": "1.3.0",
            "licenses": [{"expression": "WTFPL"}],
            "purl": "pkg:npm/left-pad@1.3.0",
            "hashes": [{"alg": "SHA-256", "content": "cd34"}],
        }
    ],
}


def _write(tmp_path, name: str, doc: dict):
    """@brief Write an SBOM file. @return Path."""
    path = tmp_path / name
    path.write_text(json.dumps(doc))
    return path


def test_an_spdx_sbom_reads_its_package_and_components(tmp_path) -> None:
    """@brief SPDX 2.3: the described package's licence, and every other package a component."""
    package, components = read_sbom(_write(tmp_path, "sbom.spdx.json", _SPDX))
    assert package == ("demo", "MIT")
    assert components[0] == Component(
        "zlib", "1.3.1", "Zlib", "library", "https://example.invalid/zlib.tar.gz", "SHA256:ab12"
    )
    assert components[1].licence == "NOASSERTION" and components[1].kind == "file"


def test_a_cyclonedx_sbom_reads_the_same_shape(tmp_path) -> None:
    """@brief CycloneDX JSON: metadata's component, components with expression licences and purls."""
    package, components = read_sbom(_write(tmp_path, "bom.cdx.json", _CDX))
    assert package == ("demo", "MIT")
    assert components == [
        Component("left-pad", "1.3.0", "WTFPL", "library", "pkg:npm/left-pad@1.3.0", "SHA-256:cd34")
    ]


def test_noassertion_and_unaccepted_licences_are_flagged(tmp_path) -> None:
    """@brief Against the accepted list: Zlib passes, NOASSERTION and WTFPL are flagged."""
    spdx = read_sbom(_write(tmp_path, "sbom.spdx.json", _SPDX))
    cdx = read_sbom(_write(tmp_path, "bom.cdx.json", _CDX))
    html = sbom_html([("sbom.spdx.json", *spdx), ("bom.cdx.json", *cdx)], ("MIT", "Zlib"), {}, 0)
    rows = {
        name: html.split(f"<code>{name}</code>", 1)[1].split("</tr>", 1)[0]
        for name in ("zlib", "weights", "left-pad")
    }
    assert 'class="flag' not in rows["zlib"]
    assert 'class="flag noassertion"' in rows["weights"]
    assert 'class="flag unaccepted"' in rows["left-pad"]


def test_without_an_accepted_list_nothing_is_called_unaccepted() -> None:
    """@brief No policy declared: NOASSERTION still flagged, "not accepted" never claimed, and said."""
    comps = [Component("left-pad", "1.3.0", "WTFPL", "library", "", "")]
    html = sbom_html([("bom.cdx.json", ("demo", "MIT"), comps)], (), {}, 0)
    assert 'class="flag unaccepted"' not in html and "No accepted-licence list" in html


def test_the_repositorys_files_licences_are_summarised() -> None:
    """@brief S5: counts by licence, and how many indexed files carry no identifier."""
    html = sbom_html([], (), {"MIT": 40, "Apache-2.0": 2}, 7)
    files = html.split('<section class="file-licences">', 1)[1]
    assert (
        "MIT" in files and ">40<" in files and "7 indexed files carry no SPDX identifier" in files
    )
    assert "No SBOM" in html


def test_a_malformed_sbom_section_is_refused_by_name(tmp_path) -> None:
    """@brief `files: sbom.json` (a string, not a list) is a problem naming the key."""
    from clew.wiki.config import load_wiki_config

    (tmp_path / ".clew.yaml").write_text("wiki:\n  sbom: {files: sbom.json}\n")
    config, problems = load_wiki_config(tmp_path, None)
    assert any("wiki.sbom.files" in p for p in problems) and config.sbom_files == (
        "sbom.spdx.json",
        "bom.cdx.json",
    )
