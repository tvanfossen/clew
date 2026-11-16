# SPDX-License-Identifier: MIT
"""The 1.4.0 wiki trace extensions, W7–W9 and W11 (#67's fifth consumer).

  * W7 — EXTERNAL NODE SOURCES: a JSON/TOML/YAML file declared with an id and a doc field becomes
    trace targets; a function names one with `@node <source>:<id>`, a node names the requirements
    it serves, and `check` refuses a reference to a node no source declares.
  * W8 — CROSS-REPO TRACE: a sub-catalog in a sibling checkout is read AT ITS PIN; a pin that does
    not resolve, or a catalog that moved since the pin, is a `check` failure. External rules map
    rule → requirement, so the trace reads rule → requirement → function → test.
  * W9 — MUTATION EVIDENCE: a record of (mechanism, test, killed) is the strongest
    requirement → test link; it is reported per requirement, ABSENT when no record was given.
  * W11 — VERSION-KEYED SITES: a versioned build writes `<out>/<key>/` and a snapshot; a diff
    between two keys names node and requirement changes.

@brief Tests for wiki external nodes, pinned catalogs, rules, mutations and versioned sites.
@version 1
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from clew.cli import _build_argparser, _run_pipeline

_PY = '''\
def load():
    """Load the data.

    @req REQ-W-001
    @req REQ-KV-001
    @node keys:net.timeout
    """
    return parse("x")


def parse(raw):
    """Parse the raw text."""
    return raw
'''

_TEST = '''\
from src.data import load


def test_load():
    """Covers the load. @req REQ-W-001"""
    assert load() == "x"
'''

_KEYS = """\
[keys."net.timeout"]
doc = "Network timeout in milliseconds"
reqs = ["REQ-W-001"]

[keys."net.retries"]
doc = "Retry count"
"""

_TOPICS = """\
topics:
  - id: cmd/req
    doc: Command request
"""

_JUNIT = """\
<testsuite><testcase classname="tests.test_data" name="test_load"/></testsuite>
"""

_MUTATIONS = """\
- {mechanism: load, test: test_load, killed: true}
- {mechanism: load, test: test_other, killed: false}
"""


## @brief Run git in a directory, failing loudly.
## @param cwd The directory.
## @param args Git arguments.
## @return stdout, stripped.
## @version 1
def _git(cwd: Path, *args: str) -> str:
    """@brief Run git. @return Output."""
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t"}
    env["GIT_COMMITTER_EMAIL"] = "t@t"
    import os

    out = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, **env},
    )
    return out.stdout.strip()


## @brief A sibling repository holding a pinned requirements catalog.
## @param root Where to create it.
## @return (repo, pinned sha).
## @version 1
def _sub_catalog(root: Path) -> tuple[Path, str]:
    """@brief Create and commit the sub-catalog. @return Repo and pin."""
    kv = root / "kv"
    (kv / "docs").mkdir(parents=True)
    (kv / "docs" / "requirements.yaml").write_text("- {id: REQ-KV-001, title: Store a key}\n")
    _git(kv, "init", "-q")
    _git(kv, "add", ".")
    _git(kv, "commit", "-q", "-m", "catalog")
    return kv, _git(kv, "rev-parse", "HEAD")


## @brief The `wiki:` section for the fixture, pinned at `pin`.
## @param pin The sub-catalog pin.
## @return YAML text.
## @version 1
def _wiki(pin: str) -> str:
    """@brief Section text. @return YAML."""
    return f"""\
wiki:
  title: Trace Demo
  docs: [README.md]
  sources:
    - name: keys
      path: model/keys.toml
      items: keys
      doc: doc
      req: reqs
    - name: topics
      path: model/topics.yaml
      items: topics
      id: id
      doc: doc
  catalogs:
    - name: kv
      repo: ../kv
      pin: "{pin}"
      catalog: docs/requirements.yaml
  rules:
    - id: R1
      title: Timeouts are bounded
      status: adopted
      requirements: [REQ-W-001]
  tests:
    junit: [build/junit.xml]
    mutations: build/mutations.yaml
"""


## @brief An indexed repository using every W7–W9 feature, with a pinned sibling catalog.
## @param tmp_path Scratch directory.
## @return (repo, index, sub-catalog repo).
## @version 1
@pytest.fixture()
def trace_repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    """@brief Build the fixture. @return Paths."""
    kv, pin = _sub_catalog(tmp_path)
    repo = tmp_path / "repo"
    for sub in ("src", "tests", "model", "build"):
        (repo / sub).mkdir(parents=True)
    (repo / "src" / "data.py").write_text(_PY)
    (repo / "tests" / "test_data.py").write_text(_TEST)
    (repo / "model" / "keys.toml").write_text(_KEYS)
    (repo / "model" / "topics.yaml").write_text(_TOPICS)
    (repo / "build" / "junit.xml").write_text(_JUNIT)
    (repo / "build" / "mutations.yaml").write_text(_MUTATIONS)
    (repo / "README.md").write_text("# Demo\n")
    (repo / ".clew.yaml").write_text(_wiki(pin))
    db = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(db), "--repo-root", str(repo)]))
    return repo, db, kv


# --- W7: external node sources -------------------------------------------------------------------


def test_sources_load_nodes_from_toml_mappings_and_yaml_lists(trace_repo) -> None:
    """A MAPPING's keys are its ids; a LIST names its id field. Each node keeps its doc and the
    requirements it serves.

    @brief TOML mapping and YAML list sources both load.
    @return None.
    """
    from clew.wiki.config import load_wiki_config
    from clew.wiki.sources import load_nodes

    repo, _db, _kv = trace_repo
    config, problems = load_wiki_config(repo)
    assert problems == []
    nodes, problems = load_nodes(repo, config.sources)
    assert problems == []
    by_ref = {n.ref: n for n in nodes}
    assert set(by_ref) == {"keys:net.timeout", "keys:net.retries", "topics:cmd/req"}
    assert by_ref["keys:net.timeout"].doc == "Network timeout in milliseconds"
    assert by_ref["keys:net.timeout"].requirements == ("REQ-W-001",)
    assert by_ref["topics:cmd/req"].file == "model/topics.yaml"


def test_a_function_names_a_node_with_the_node_tag(trace_repo) -> None:
    """@brief `@node keys:net.timeout` in a doc comment links the function to that node.
    @return None.
    """
    from clew.wiki.sources import node_references

    _repo, db, _kv = trace_repo
    refs = node_references(db)
    assert refs.get("keys:net.timeout") == ("load",)


def test_check_refuses_a_reference_to_an_undeclared_node(trace_repo, tmp_path: Path) -> None:
    """THE TRACE TARGET MUST EXIST: a tag naming a node no source declares is a named problem, as
    is a source file that is missing.

    @brief Unknown node reference and missing source are check problems.
    @return None.
    """
    from clew.wiki.check import check_wiki

    repo, db, _kv = trace_repo
    assert check_wiki(repo, db) == []
    (repo / "src" / "data.py").write_text(_PY.replace("net.timeout", "net.nope"))
    db2 = tmp_path / "again.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(db2), "--repo-root", str(repo)]))
    (repo / "model" / "topics.yaml").unlink()
    problems = "\n".join(check_wiki(repo, db2))
    assert "keys:net.nope" in problems and "load" in problems
    assert "model/topics.yaml" in problems


# --- W8: pinned sub-catalogs and external rules --------------------------------------------------


def test_a_sub_catalog_is_read_at_its_pin(trace_repo) -> None:
    """@brief The pinned catalog's ids are listed with the pin they were read at.
    @return None.
    """
    from clew.wiki.catalogs import catalog_requirements
    from clew.wiki.config import load_wiki_config

    repo, _db, _kv = trace_repo
    config, _ = load_wiki_config(repo)
    (catalog,) = config.catalogs
    rows, problems = catalog_requirements(repo, catalog)
    assert problems == []
    assert [(r.req_id, r.title) for r in rows] == [("REQ-KV-001", "Store a key")]


def test_a_catalog_that_moved_since_its_pin_fails_check(trace_repo) -> None:
    """CATALOG MOVED, PIN DID NOT: the consumer is tracing against requirements its pin no longer
    describes — a `check` failure, named. An unresolvable pin is one too.

    @brief Moved catalog and bad pin are problems, and the site says so.
    @return None.
    """
    from clew.wiki.check import check_wiki

    repo, db, kv = trace_repo
    (kv / "docs" / "requirements.yaml").write_text("- {id: REQ-KV-001, title: Store a key, v: 2}\n")
    _git(kv, "commit", "-qam", "move")
    problems = "\n".join(check_wiki(repo, db))
    assert "kv" in problems and "moved" in problems
    from clew.wiki.build import build_wiki

    page = (build_wiki(repo, db, repo.parent / "site") / "requirements.html").read_text()
    assert "moved since pin" in page, "the site states what check found, not only check"
    text = (repo / ".clew.yaml").read_text()
    pin = text.split("pin: ")[1].split("\n")[0]
    (repo / ".clew.yaml").write_text(text.replace(pin, "0" * 40))
    assert "does not resolve" in "\n".join(check_wiki(repo, db))


def test_a_rule_must_name_known_requirements(trace_repo) -> None:
    """@brief A rule naming a requirement nobody declares or tags is a problem.
    @return None.
    """
    from clew.wiki.check import check_wiki

    repo, db, _kv = trace_repo
    text = (repo / ".clew.yaml").read_text()
    (repo / ".clew.yaml").write_text(text.replace("[REQ-W-001]", "[REQ-W-001, REQ-NOPE-9]"))
    assert "REQ-NOPE-9" in "\n".join(check_wiki(repo, db))


# --- W9: mutation evidence -----------------------------------------------------------------------


def test_mutation_records_attach_to_the_requirement_their_mechanism_implements(trace_repo) -> None:
    """KILLED AND SURVIVED ARE BOTH REPORTED; with no record the field is ABSENT (None), because
    unmeasured is not "no mutant survived".

    @brief Mutation outcomes per requirement; None without a record.
    @return None.
    """
    from clew.wiki.evidence import requirement_evidence

    repo, db, _kv = trace_repo
    rows = requirement_evidence(
        db,
        junit=[repo / "build" / "junit.xml"],
        mutations=repo / "build" / "mutations.yaml",
    )
    req = next(r for r in rows if r.req_id == "REQ-W-001")
    assert req.tier == "PASS"
    assert req.mutations == (("load", "test_load", "killed"), ("load", "test_other", "survived"))
    plain = requirement_evidence(db, junit=[repo / "build" / "junit.xml"])
    assert next(r for r in plain if r.req_id == "REQ-W-001").mutations is None


# --- the site carries all of it ------------------------------------------------------------------


def test_the_site_shows_nodes_rules_catalogs_and_mutations(trace_repo, tmp_path: Path) -> None:
    """@brief Node page, rule chain, pinned catalog and mutation outcomes are rendered.
    @return None.
    """
    from clew.wiki.build import build_wiki

    repo, db, _kv = trace_repo
    site = build_wiki(repo, db, tmp_path / "site")
    pages = {p.name: p.read_text() for p in site.rglob("*.html")}
    assert "Network timeout in milliseconds" in pages["nodes.html"]
    # Round 3, P1g: the page explains itself with a worked example drawn from a REAL entry —
    # model file entry → the function that realises it (`@node`) → the requirement it serves.
    example = pages["nodes.html"].split('<svg class="node-example"', 1)[1].split("</svg>", 1)[0]
    assert "net.timeout" in example and ">load<" in example and "@node keys:net.timeout" in example
    req = pages["requirements.html"]
    assert "R1" in req and "Timeouts are bounded" in req
    assert "REQ-KV-001" in req and "Store a key" in req
    assert "survived" in req and "keys:net.timeout" in req


# --- W11: version-keyed sites and a diff page ----------------------------------------------------


def test_versioned_builds_and_a_diff_between_them(trace_repo, tmp_path: Path) -> None:
    """ONE SITE PER KEY, and the diff names what changed between two keys: nodes added or removed
    (the key space) and requirement tier changes.

    @brief Two versioned builds, then a diff page and payload.
    @return None.
    """
    from clew.wiki.build import build_wiki
    from clew.wiki.versions import diff_versions

    repo, db, _kv = trace_repo
    out = tmp_path / "sites"
    build_wiki(repo, db, out, version="v1")
    (repo / "model" / "keys.toml").write_text(_KEYS.replace("net.retries", "net.backoff"))
    (repo / "build" / "junit.xml").write_text(_JUNIT.replace("/>", "><failure/></testcase>"))
    build_wiki(repo, db, out, version="v2")
    assert (out / "v1" / "html" / "index.html").is_file()
    assert (out / "v2" / "html" / "index.html").is_file()
    assert [v["key"] for v in json.loads((out / "versions.json").read_text())] == ["v1", "v2"]
    assert "v1" in (out / "index.html").read_text()
    diff = diff_versions(out, "v1", "v2")
    assert diff["nodes_added"] == ["keys:net.backoff"]
    assert diff["nodes_removed"] == ["keys:net.retries"]
    assert {"id": "REQ-W-001", "from": "PASS", "to": "GAP"} in diff["requirements_changed"]
    page = (out / "diff-v1-v2.html").read_text()
    assert "keys:net.backoff" in page and "REQ-W-001" in page


def test_the_cli_takes_an_out_of_tree_config(trace_repo, tmp_path: Path, capsys) -> None:
    """A REPOSITORY CAN BE DOCUMENTED WITHOUT WRITING INTO IT: `--config` names the file whose
    `wiki:` section applies.

    @brief `clew wiki check --config FILE` reads that file's section.
    @return None.
    """
    from clew.wiki.command import wiki_main

    repo, db, _kv = trace_repo
    outside = tmp_path / "outside.yaml"
    outside.write_text((repo / ".clew.yaml").read_text() + "  colour: blue\n")
    args = ["check", "--index", str(db), "--repo-root", str(repo)]
    assert wiki_main(args) == 0
    assert wiki_main([*args, "--config", str(outside)]) == 1
    assert "colour" in capsys.readouterr().out


def test_a_list_of_scalars_is_a_list_of_ids(tmp_path: Path) -> None:
    """A KEY MANIFEST IS OFTEN A BARE LIST (`["also", "chain", ...]`): with no `id` field declared,
    each scalar is its own id, with no doc.

    @brief Scalar list items are ids.
    @return None.
    """
    from clew.wiki.config import SourceSpec
    from clew.wiki.sources import load_nodes

    (tmp_path / "keys.json").write_text('{"envelope_keys": ["also", "chain"]}')
    spec = SourceSpec(name="wire", path="keys.json", items="envelope_keys")
    nodes, problems = load_nodes(tmp_path, (spec,))
    assert problems == []
    assert [n.ref for n in nodes] == ["wire:also", "wire:chain"]


def test_a_node_tag_mentioned_in_prose_is_not_a_reference(tmp_path: Path) -> None:
    """A TAG IS A LINE'S FIRST WORD, as doxygen reads a command: a sentence that MENTIONS
    `@node a:b` (found by `clew wiki check` on clew's own tests) references nothing.

    @brief Only a line-leading `@node` is a reference.
    @return None.
    """
    from clew.wiki.sources import node_references

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "m.py").write_text(
        'def tagged():\n    """Do it.\n\n    @node keys:real\n    """\n\n\n'
        'def mentions():\n    """A sentence naming `@node keys:fake` in prose."""\n'
    )
    db = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(db), "--repo-root", str(repo)]))
    assert node_references(db) == {"keys:real": ("tagged",)}
