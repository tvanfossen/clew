# SPDX-License-Identifier: MIT
"""A flow states its intent, its scenario and a worked example, declared (W-1, W-5, 2.0.0).

OWNER REVIEW 2026-11-22: "the flows could be better named, plain description, Gherkin/BDD is great
for this, as it abstracts to a more human notion - always visible below the abstract layer", and
"some major flows could use a high level intent context, like show me the dossier content for a
given tool call (using an internal example …) so I can better understand how it pieces things
together". Owner Q/A the same day: DECLARED ONLY — "abstract prose is hard to derive from derived".

@brief Tests flow intent, scenario and example.
@version 1
"""

from __future__ import annotations

from pathlib import Path


def _load(tmp_path: Path, flow: str):
    from clew.wiki.config import load_wiki_config

    (tmp_path / ".clew.yaml").write_text("wiki:\n  flows:\n" + flow, encoding="utf-8")
    return load_wiki_config(tmp_path, None)


def test_a_flow_declares_intent_scenario_and_example(tmp_path: Path) -> None:
    """@brief The three keys are read as written; a scenario may be a block or a list."""
    config, problems = _load(
        tmp_path,
        "    - entry: dossier\n"
        "      intent: Everything the index knows about one name.\n"
        "      scenario: |\n"
        "        Given an index of this repository\n"
        "        When an agent asks dossier about derive_flow\n"
        "        Then the reply carries its body, callers and callees\n"
        "      example:\n"
        '        input: dossier(subject="derive_flow")\n'
        '        output: "file: clew/wiki/flow.py"\n',
    )
    assert problems == [], problems
    (spec,) = config.flows
    assert spec.intent == "Everything the index knows about one name."
    assert spec.scenario[0] == "Given an index of this repository" and len(spec.scenario) == 3
    assert spec.example == ('dossier(subject="derive_flow")', "file: clew/wiki/flow.py")


def test_a_scenario_line_without_a_gherkin_keyword_is_refused_by_name(tmp_path: Path) -> None:
    """@brief Each line starts Given / When / Then / And / But; otherwise a named problem."""
    _config, problems = _load(
        tmp_path, '    - entry: dossier\n      scenario: ["Given x", "Returns a reply"]\n'
    )
    assert any("wiki.flows[0].scenario" in p and "Returns a reply" in p for p in problems), problems


def test_the_preface_shows_intent_then_scenario_then_example() -> None:
    """@brief Rendered in reading order, keywords marked, text escaped."""
    from clew.wiki.config import FlowSpec
    from clew.wiki.flowpage import _preface

    spec = FlowSpec(
        entry="dossier",
        intent="One name, <all> layers.",
        scenario=("Given an index", "When dossier runs", "Then a reply"),
        example=("dossier(subject='x')", "file: a.py"),
    )
    html = _preface(spec)
    assert (
        html.index('class="intent"') < html.index('class="gherkin"') < html.index('class="example"')
    )
    assert '<b class="kw">Given</b> an index' in html and "&lt;all&gt;" in html
    assert _preface(FlowSpec(entry="x")) == ""


def test_the_flows_page_says_what_each_flow_is_for() -> None:
    """@brief A flow's declared intent sits under its title in the Flows table."""
    from clew.wiki.flowpage import FlowPage, _role_block

    page = FlowPage(
        "flow-d", "Look up one name", frozenset(), role="product", intent="Everything about it."
    )
    html = _role_block("product", [page])
    assert "Look up one name" in html and '<span class="intent">Everything about it.</span>' in html


def test_a_scenario_line_may_name_the_call_it_starts_at(tmp_path: Path) -> None:
    """X-1 (owner review 2, 2026-11-22): "show WHAT is being built up by the sequence diagram … blocks
    of it can be aligned to gherkin syntax". A scenario line is text, or `{step, at}` naming the call
    where its part of the diagram begins.

    @brief Anchored scenario lines.
    """
    config, problems = _load(
        tmp_path,
        "    - entry: dossier\n"
        "      scenario:\n"
        "        - Given an index\n"
        "        - {step: When names are asked about, at: _accepted_batch}\n"
        "        - {step: Then one reply answers them, at: _batched_dossiers}\n",
    )
    assert problems == [], problems
    (spec,) = config.flows
    assert spec.scenario[1] == "When names are asked about"
    assert spec.scenario_at == ("", "_accepted_batch", "_batched_dossiers")


def test_the_story_groups_steps_under_the_scenario_in_plain_words() -> None:
    """X-1: a story view lists each step as its callee's brief, grouped under the scenario line whose
    anchor begins it; steps before the first anchor join the first anchored line. Each step carries
    `data-step`, so play lights it.

    @brief Story view.
    """
    from types import SimpleNamespace

    from clew.wiki.config import FlowSpec
    from clew.wiki.flowpage import _story

    spec = FlowSpec(
        entry="dossier",
        scenario=("Given an index", "When names are asked about", "Then one reply answers them"),
        scenario_at=("", "_accepted_batch", "_batched_dossiers"),
    )
    steps = [
        SimpleNamespace(callee=c, not_run=0)
        for c in ("_accepted_batch", "_batched_dossiers", "batch_payload")
    ]
    data = [
        {"brief": "Normalise the request."},
        {"brief": "Several subjects in ONE reply."},
        {"brief": ""},
    ]
    html = _story(spec, SimpleNamespace(steps=steps), data)
    first, second = html.split("one reply answers them")
    assert 'data-step="0"' in first and "Normalise the request." in first
    assert 'data-step="1"' in second and 'data-step="2"' in second and "batch_payload" in second
