# SPDX-License-Identifier: MIT
"""One top-level `requirements:` section, read by the index, the gate and the wiki (R5-CFG F6-F8/F14).

FOUND BY THE 2.0.0 CONFIG REVIEW (agent A, vetted, owner-approved). The catalog was stated in five
places and each tool read a different one: top-level `requirements:` (a path, index only),
`guard.impact.requirements` (the gate, the wiki and coverage), `wiki.catalogs` and
`guard.impact.requirements.external` (one concept, `pin`/`catalog` in one and `rev`/`path` in the
other), and `wiki.needs`. A repo writing the documented top-level line got an index with the
catalog, a wiki without it and a gate reporting every `@req` uncheckable. The id/name column
defaults also differed per tool (`Req ID`/`name` in the gate, `id`/`title` in the index), and
`version_field` — a catalog field — sat under a `validate.version_gate` beside `validate.version`.

@brief Tests the one requirements section and the refusal of every old location.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clew.guard.config import ConfigError, get_requirements, load_config
from clew.requirements import load_guard_config, resolve_catalog_columns, resolve_catalog_path


def _repo(tmp_path: Path, text: str) -> Path:
    """@brief A repo with this `.clew.yaml` and a catalog file. @return Root."""
    (tmp_path / ".clew.yaml").write_text(text, encoding="utf-8")
    (tmp_path / "cat.yaml").write_text("- {id: R-1, title: one}\n", encoding="utf-8")
    return tmp_path


_SECTION = (
    "requirements:\n  file: cat.yaml\n  id_column: rid\n  name_column: label\n"
    "  status_field: x-status\n  exempt_status: [planned]\n  version_field: min_version\n"
)


def test_the_gate_and_the_index_read_the_same_top_level_section(tmp_path: Path) -> None:
    """With NO `guard:` section at all: the catalog is the repo's, not the gate's.

    @brief One section, both readers.
    """
    root = _repo(tmp_path, _SECTION)
    gate = get_requirements(load_config(root / ".clew.yaml"))
    assert gate["file"] == "cat.yaml" and gate["id_column"] == "rid"
    index_cfg = load_guard_config(root)
    assert resolve_catalog_path(index_cfg, root) == (root / "cat.yaml").resolve()
    assert resolve_catalog_columns(index_cfg) == ("rid", "label")


def test_a_path_alone_is_the_file(tmp_path: Path) -> None:
    """`requirements: cat.yaml` — the 1.x top-level form — stays the short way to say `file:`.

    @brief String shorthand.
    """
    root = _repo(tmp_path, "requirements: cat.yaml\n")
    assert get_requirements(load_config(root / ".clew.yaml"))["file"] == "cat.yaml"


def test_an_unknown_requirements_key_is_refused(tmp_path: Path) -> None:
    """@brief A misspelled catalog key is refused by name."""
    root = _repo(tmp_path, "requirements:\n  file: cat.yaml\n  id_colum: rid\n")
    with pytest.raises(ConfigError) as exc:
        load_config(root / ".clew.yaml")
    assert "id_colum" in " ".join(exc.value.problems)


@pytest.mark.parametrize(
    ("text", "pointer"),
    [
        ("guard:\n  impact:\n    requirements: {file: cat.yaml}\n", "requirements:"),
        (
            "guard:\n  validate:\n    version_gate: {version_field: v}\n",
            "requirements.version_field",
        ),
        (
            "guard:\n  validate:\n    version_gate: {current_version: '1.0'}\n",
            "validate.current_version",
        ),
    ],
)
def test_an_old_location_is_refused_with_a_pointer(tmp_path: Path, text: str, pointer: str) -> None:
    """Refused by name with where the key went, not as "unknown" — the key was right in 1.x.

    @brief Moved keys point at their new home.
    """
    root = _repo(tmp_path, text)
    with pytest.raises(ConfigError) as exc:
        load_config(root / ".clew.yaml")
    assert pointer in " ".join(exc.value.problems), exc.value.problems


def test_the_current_version_is_read_from_its_new_key(tmp_path: Path) -> None:
    """@brief `validate.current_version` is the release the version gate compares against."""
    root = _repo(tmp_path, "guard:\n  validate:\n    current_version: '2.0.0'\n")
    assert load_config(root / ".clew.yaml")["validate"]["current_version"] == "2.0.0"


@pytest.mark.parametrize(
    ("key", "pointer"), [("catalogs", "requirements.external"), ("needs", "requirements.needs")]
)
def test_the_wiki_catalog_keys_point_at_the_requirements_section(
    tmp_path: Path, key: str, pointer: str
) -> None:
    """@brief `wiki.catalogs` / `wiki.needs` moved to `requirements:`."""
    from clew.wiki.config import load_wiki_config

    root = _repo(tmp_path, f"wiki:\n  {key}: []\n")
    _config, problems = load_wiki_config(root)
    assert any(pointer in p for p in problems), problems


def test_one_default_column_pair_for_every_reader() -> None:
    """F8: an undeclared flat catalog is read with the same id/name keys by gate and index.

    @brief One default pair.
    """
    from clew.guard.config import REQUIREMENTS_ID_COLUMN_DEFAULT, REQUIREMENTS_NAME_COLUMN_DEFAULT

    assert resolve_catalog_columns(None) == (
        REQUIREMENTS_ID_COLUMN_DEFAULT,
        REQUIREMENTS_NAME_COLUMN_DEFAULT,
    )


def test_external_and_needs_reach_the_wiki_from_the_requirements_section(tmp_path: Path) -> None:
    """F6: one pinned-catalog shape, `{repo, rev, path, name}`; the wiki reads it from here.

    @brief The wiki's catalogs come from `requirements.external`.
    """
    from clew.wiki.config import load_wiki_config

    root = _repo(
        tmp_path,
        "requirements:\n  file: cat.yaml\n  needs: docs/needs.json\n"
        "  external:\n    - {repo: ../kv, rev: v1.2.0, path: req.yaml, name: kv}\n",
    )
    config, problems = load_wiki_config(root)
    assert not problems, problems
    assert [(s.name, s.repo, s.pin, s.catalog) for s in config.catalogs] == [
        ("kv", "../kv", "v1.2.0", "req.yaml")
    ]
    assert config.needs == "docs/needs.json"
