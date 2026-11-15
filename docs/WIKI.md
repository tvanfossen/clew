# clew wiki

A static documentation site generated entirely from what the repository already has — nothing is
written by hand for it:

| source | gives the site |
|---|---|
| the clew index | flows (sequence diagrams), implementers, test links, model-entry references |
| `.clew.yaml` `wiki:` | what to include, reports, theme, audiences |
| the requirements catalog | titles, acceptance criteria, declared status and priority, evidence files — found the way the index finds it (`guard:` declaration, else `requirements.yaml`) |
| clew-guard's `impact.json` | the latest change impact (`<guard.output_dir>/impact/impact.json`, or `wiki.impact`) |
| CI reports | test results, coverage, per-test coverage, mutation records |
| prose you select | Markdown, reStructuredText or HTML pages, as written |

The site is self-contained — no CDN, no font service, no runtime fetch.

```bash
pip install 'clew-trace[wiki]'          # Sphinx + MyST, only for `build`
clew wiki check                          # validate the `wiki:` section; no Sphinx import
clew wiki build --out site               # site/html
clew wiki build --out sites --version v1.2.0   # one site per release, plus a burndown
clew wiki diff --out sites v1.1.0 v1.2.0       # what changed between two recorded versions
clew wiki flow ENTRY --svg --animate     # one diagram, standalone
clew wiki trace --config .clew.yaml      # the graded trace as JSON
```

`check` is cheap and belongs in pre-commit or a CI static stage; `build` is a separate stage.
Both take `--refresh` to bring the index current first. The `clew-wiki-check` pre-commit hook runs
`clew wiki check --refresh`:

```yaml
- repo: https://github.com/tvanfossen/clew
  rev: <tag>
  hooks: [{id: clew-wiki-check}]
```
Every key of the section is known by name: a misspelled one is a problem, never ignored.

## The `wiki:` section of `.clew.yaml`

```yaml
wiki:
  title: Demo
  docs: [README.md, "docs/**/*.md"]
  entry_points: 2               # every console script / main / thread entry is a flow (0 = off)
  flows:                        # roots you choose, added to the entry points
    - entry: load               # bare name; `qualified:` or `file:` selects one identity
      depth: 3
      lanes: files              # files | packages | threads
      stop_at: [log]
      animate: true
  tests:
    junit: [build/junit.xml]
    results:                    # each DECLARED: ctest | tap | catch2 | pytest-json | ceedling | unity
      - {format: ctest, path: build/Testing/Test.xml}
    coverage: build/coverage.xml          # Cobertura
    gcov: ["build/**/*.gcov", build/cov.json.gz]   # gcov text, or gcov / gcovr JSON
    mapping: docs/req_tests.yaml          # {REQ: [test]} or a `req,test` CSV
    features: ["tests/features/**/*.feature"]      # Gherkin: @REQ-ID or @req:REQ-ID tags
    layers: {unit: ["tests/unit/*"], bdd: ["tests/features/*"]}
    min_layers: 2               # flag requirements tested in fewer layers
    target_only: ["test_hw_*"]  # skipped on host by design: TARGET, not a gap
    contexts: build/coverage.json         # coverage.py JSON with --cov-context=test
    evidence_fields: [x-evidence, evidence]  # catalog fields naming test files
    infer_depth: 2              # link tests whose calls reach an implementer (0 = off)
    mutations: build/mutations.yaml
  links:
    template: "https://host/repo/blob/{commit}/{file}#L{line}"
  theme:
    name: clew                  # or any installed Sphinx theme
    palette: {acc: "#3D6B2E"}
    css: [docs/wiki.css]
    logo: docs/logo.svg
    fonts: true
  roadmap: ROADMAP.md
  impact: docs/generated/impact/impact.json   # default: from the guard: section
  audiences:
    partner: {exclude_bodies: true, exclude_requirement_text: true}
```

External node sources, pinned sub-catalogs and external rules (`sources`, `catalogs`, `rules`)
are described in `clew/wiki/config.py`'s module documentation.

## What the site holds

The top bar names the sections and holds the search field.

- **Docs** — the selected prose.
- **Flows** — a UML sequence diagram for every entry point (console scripts, `main`s outside
  tests, thread entries) and every root declared in `wiki.flows`: lanes, activation bars, numbered calls,
  returns, and loop / opt / alt / try frames around the calls they enclose. Every step is an
  index edge; a call the index did not resolve is not drawn. Click a step for the data it
  carries — the call expression at the call site, the callee's signature and brief, its frames
  and a source link. Play, pause and step through the calls in order.
- **Requirements** — one page: counts and charts, the burndown (versioned builds), per-group
  counts, the change impact, then every requirement with its tier, implementers (linked to
  source), tests and how each was linked, layers, the catalog's declared status and priority,
  model entries and mutation outcomes; acceptance criteria fold out under the id. External rules
  and pinned catalogs follow.
- **Model entries** — entries of the model files declared in `wiki.sources`, with the functions
  that realise each (`@node <source>:<id>`) and the requirements it serves.

## Search

The site's search covers its pages. The authoritative search over the index — every symbol, the
code corpus, ranked — is `clew query search` or the MCP `search` tool; the site does not
re-implement it, so a miss in the site's search never reads as "not in the repository".

## How a test is linked to a requirement

A test needs no tag. Links are made, strongest first, and the page marks every link weaker than a
tag:

| kind | made by |
|---|---|
| tagged | `@req` on the test, a mapping file, or a Gherkin scenario tag |
| measured | per-test coverage ran a line of an implementer |
| catalog | the catalog's evidence field names the test's file (a file-level claim) |
| inferred | the test's calls reach an implementer within `infer_depth` hops |

Reaching code is not verifying it, so the trace counts the requirements linked only by each weaker
kind.

## Test frameworks

| framework | a test is | results |
|---|---|---|
| pytest | a `test*` function or method | JUnit (`--junitxml`), pytest-json-report |
| Catch2 / doctest | `TEST_CASE`, `SCENARIO`, `TEMPLATE_TEST_CASE`, `TEST_CASE_METHOD` — named by its string | Catch2 XML, JUnit reporter |
| GoogleTest | `TEST`, `TEST_F`, `TEST_P`, `TYPED_TEST` — `Suite.Name` | `--gtest_output=xml` (read as JUnit; `notrun` is a skip) |
| Boost.Test | `BOOST_AUTO_TEST_CASE`, `BOOST_FIXTURE_TEST_CASE` | JUnit |
| Unity / Ceedling | a C `test_*` function | Ceedling's XML report, Unity's text output, JUnit |
| CTest, TAP | — | CTest `Test.xml`, TAP |

A framework macro counts as a test only inside test code. Coverage comes from Cobertura (gcovr
`--xml`, coverage.py `xml`), gcov text, or gcov / gcovr JSON.

## Evidence tiers

| tier | meaning |
|---|---|
| PASS | a linked test passed and none failed |
| GAP | a linked test failed or errored |
| TARGET | every linked result is a skip of a target-only test |
| NOT_RUN | tests are linked but skipped, or no report holds their result |
| MISSING | no test is linked |

Unmeasured is never reported as a result: with no coverage report, coverage fields are absent;
with no layers configured, `layers` is absent.

## Burndown

A versioned build records what it traced (`<out>/<key>/site.json`). The burndown plots open
requirements — every tier but PASS and TARGET — at each recorded version. Headings of the roadmap
that name a version (`## v0.8.0 — …`) are milestones; one not yet recorded is drawn ahead, with
an ideal line to zero.

## Theme

The default theme is clew's own, in the sassafras-class look, with Manrope, Newsreader and
JetBrains Mono bundled under the SIL Open Font License (licence texts ship with the fonts).
Palette tokens: `surface paper muted inset ink ink2 faint rule rule2 acc accbg accink root rootbg
err errbg warn warnbg`. Naming another theme leaves that theme's look untouched.

## Audiences

`--audience NAME` applies redaction to the output: `exclude_bodies` removes function bodies and
the call text in flow dialogs; `exclude_requirement_text` removes requirement titles.
