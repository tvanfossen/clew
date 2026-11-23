# SPDX-License-Identifier: MIT
"""External requirements catalogs for the gate, and the silent no-catalog gap (GH #68, P6b-1).

GH #68: a library whose catalogue is owned by its consumer must still run the gate with
`cross_reference` on — so a repository may name catalogues it does not own under
`impact.requirements.external`: a local path, or `{repo, rev, path}` read with `git show
rev:path` from a local clone or submodule. A bare URL is REFUSED BY NAME (owner 2026-11-16): a
URL would make a pre-commit gate depend on the network. The repository's own `file` becomes
optional.

AND THE GAP #68 EXPOSED: with no catalogue at all and `cross_reference` on, every `@req` passed
UNCHECKED — `req_ids` was None and the check returned nothing. A tag that cannot be checked is
now reported as such; a repository that uses no `@req` tag is unaffected.

@brief Tests for external catalogues and uncheckable requirement tags.
@version 1
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

from clew.guard.main import main
from guard_helpers import guard_yaml

_TAGGED = dedent("""\
    /**
     * @brief Does it.
     * @req {req}
     * @version 1.0
     */
    void f(void) {{}}
""")


def _catalog(path: Path, *ids: str) -> None:
    rows = "".join(f"  {i}:\n    name: {i} name\n" for i in ids)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"requirements:\n{rows}")


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, impact: str, req: str) -> tuple[int, str]:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "f.c").write_text(_TAGGED.format(req=req))
    cfg = tmp_path / "guard.yaml"
    ## FIXTURE CHANGED (2.0.0, R5-CFG F7): the catalog is the top-level `requirements:`.
    cfg.write_text(impact + guard_yaml(""))
    code = main(["--config", str(cfg), "validate", "--no-git", "f.c"])
    return code, ""


def test_an_external_catalogue_satisfies_cross_reference_without_a_local_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """@brief A library checks its tags against its consumer's catalogue; an unknown id is named."""
    _catalog(tmp_path / "product" / "requirements.yaml", "REQ-PRD-001")
    impact = "requirements:\n  external: [product/requirements.yaml]\n"
    code, _ = _run(tmp_path, monkeypatch, impact, "REQ-PRD-001")
    assert code == 0, capsys.readouterr()
    code, _ = _run(tmp_path, monkeypatch, impact, "REQ-PRD-999")
    out = capsys.readouterr()
    assert code == 1 and "REQ-PRD-999" in (out.out + out.err)


def test_a_pinned_external_catalogue_is_read_at_its_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """THE PIN, NOT THE WORKING TREE: an id added to the consumer's catalogue after the pinned
    revision is not satisfied by it.

    @brief `{repo, rev, path}` read with `git show`.
    """
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    _catalog(consumer / "requirements.yaml", "REQ-PRD-001")

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-c", "user.email=t@e", "-c", "user.name=t", *args],
            cwd=consumer,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    git("init", "-q")
    git("add", "-A")
    git("commit", "-q", "-m", "catalogue")
    rev = git("rev-parse", "HEAD")
    _catalog(consumer / "requirements.yaml", "REQ-PRD-001", "REQ-PRD-002")
    impact = (
        "requirements:\n  external:\n"
        f"    - {{repo: consumer, rev: {rev}, path: requirements.yaml}}\n"
    )
    code, _ = _run(tmp_path, monkeypatch, impact, "REQ-PRD-001")
    assert code == 0, capsys.readouterr()
    code, _ = _run(tmp_path, monkeypatch, impact, "REQ-PRD-002")
    assert code == 1


def test_a_url_is_refused_by_name(tmp_path: Path) -> None:
    """@brief A pre-commit gate never reaches the network: a URL source is refused, naming it."""
    from clew.requirements import read_catalog_at

    with pytest.raises(ValueError, match="URL"):
        read_catalog_at(tmp_path, "https://example.invalid/requirements.yaml")
    with pytest.raises(ValueError, match="URL"):
        read_catalog_at(
            tmp_path, {"repo": "git@github.com:o/r.git", "rev": "abc", "path": "r.yaml"}
        )


def test_a_tag_with_no_catalogue_to_check_it_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """THE GAP #68 EXPOSED: `cross_reference` on, no catalogue anywhere, a `@req` tag — reported as
    uncheckable, with how to fix it, never passed silently.

    @brief No catalogue, a tag: a violation.
    """
    code, _ = _run(tmp_path, monkeypatch, "", "REQ-ANY-001")
    out = capsys.readouterr()
    text = out.out + out.err
    assert code == 1 and "REQ-ANY-001" in text and "no requirements catalog" in text


def test_the_wiki_and_the_gate_read_catalogues_through_one_reader(tmp_path: Path) -> None:
    """@brief The shared reader returns every id with its row, in both catalogue shapes."""
    from clew.requirements import read_catalog_at

    _catalog(tmp_path / "keyed.yaml", "REQ-A-001", "REQ-A-002")
    (tmp_path / "flat.yaml").write_text("- {id: REQ-B-001, name: B}\n")
    assert set(read_catalog_at(tmp_path, "keyed.yaml")) == {"REQ-A-001", "REQ-A-002"}
    assert read_catalog_at(tmp_path, "flat.yaml")["REQ-B-001"]["name"] == "B"
