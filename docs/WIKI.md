# clew wiki

A static documentation site generated from a repository's clew index: the repository's own
prose, sequence diagrams derived from the call graph, and the requirement trace joined to what
CI measured. The site is self-contained — no CDN, no font service, no runtime fetch.

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
Every key of the section is known by name: a misspelled one is a problem, never ignored.

## The `wiki:` section of `.clew.yaml`

```yaml
wiki:
  title: Demo
  docs: [README.md, "docs/**/*.md"]
  flows:
    - entry: load               # bare name; `qualified:` selects one identity
      depth: 3
      lanes: files              # files | packages | threads
      stop_at: [log]
      animate: true
  tests:
    junit: [build/junit.xml]
    results:                    # other formats, each DECLARED: ctest | tap | catch2 | pytest-json
      - {format: ctest, path: build/Testing/Test.xml}
    coverage: build/coverage.xml          # Cobertura
    gcov: ["build/**/*.gcov", build/cov.json.gz]   # gcov text, or gcov / gcovr JSON
    mapping: docs/req_tests.yaml          # {REQ: [test]} or a `req,test` CSV
    features: ["tests/features/**/*.feature"]      # Gherkin: @REQ-ID or @req:REQ-ID tags
    layers: {unit: ["tests/unit/*"], bdd: ["tests/features/*"]}
    min_layers: 2               # flag requirements tested in fewer layers
    target_only: ["test_hw_*"]  # skipped on host by design: TARGET, not a gap
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
  audiences:
    partner: {exclude_bodies: true, exclude_requirement_text: true}
```

External node sources, pinned sub-catalogs and external rules (`sources`, `catalogs`, `rules`)
are described in `clew/wiki/config.py`'s module documentation.

## What the site holds

- **Summary** — requirements by tier and tests by status as charts, and per requirement group:
  how many are implemented, tested, in each tier, and below the layer minimum. A versioned build
  adds the burndown.
- **Flows** — a UML sequence diagram per declared entry: lanes, activation bars, numbered calls,
  returns, and loop / opt / alt / try frames around the calls they enclose. Every step is an
  index edge; a call the index did not resolve is not drawn. Click a step for the data it
  carries — the call expression at the call site, the callee's signature and brief, its frames
  and a source link. Play, pause and step through the calls in order.
- **Requirements** — each requirement's tier, linked tests with their status, test layers,
  model nodes and mutation outcomes, plus external rules and pinned catalogs.

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
