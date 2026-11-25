---
name: clew-wiki
description: Use when building, checking or configuring a repository's clew wiki (`clew wiki build`, `clew wiki check`, the `wiki:` section of `.clew.yaml`), or when a `clew wiki check` pre-commit hook reports a problem. Covers what each page is drawn from, the keys that change it, and what the check refuses.
---

# clew wiki

A static site drawn from a repository's clew index: requirements, flows, tests, the map,
architecture, the SBOM and the repository's own docs. Every page is derived from the index and the
files the repository declares. Nothing on it is written by hand.

## Build and check

```bash
clew wiki build --refresh --out build/wiki   # the site is build/wiki/html; --refresh brings the index current first
clew wiki check                              # the wiki: section against the index; no Sphinx run
```

`check` prints one problem per line on stdout and exits 1 when there is any, which is the shape a
pre-commit hook wants. EARS notes, when `check: {ears: true}` is set, go to stderr and never change
the exit code.

## What each tab is drawn from

| tab | source |
|---|---|
| Requirements | the catalogue (top-level `requirements:`), `@req` tags, and test evidence (JUnit, coverage contexts, LCOV); group pages, traceability checklist, evidence diagrams |
| Flows | entry points (console scripts, mains, declared `entry_patterns`) and declared `wiki.flows`; block lanes by default, with an actor lane |
| Tests | every test the index recognises; `wiki.test_pages` (`linked` / `all` / `none`) picks which get a page |
| Map | every function, with blocks from `wiki.components`, else inferred |
| Architecture | C4 levels from entry points, blocks and vendor areas; data stores and deployment are named as missing, never drawn |
| SBOM | the repository's own SPDX 2.3 / CycloneDX file, rendered as is (`wiki.sbom`); the wiki never writes one |

## The keys people trip on

- **Old keys are refused by name.** The test-evidence keys are the top-level `tests:` section
  (`junit`, `contexts`, `lcov`, `layers`, `traces`). A `wiki.tests` is refused with a pointer.
- **A string where a list belongs is refused.** For example `docs: README.md` must be
  `docs: [README.md]`.
- **`0` and `[]` are values**, not "unset".
- **Declared flows keep their lanes.** A flow with `lanes: packages` stays on package lanes; only
  flows that name no strategy get block lanes.

Full reference: `docs/WIKI.md`.

## Failure modes and the test flowchart

A requirement declares the ways it can fail in the catalogue (`failure_modes: {FM-ID: meaning}`).
A test page draws "How it can fail" when the test names a mode: each assertion is a diamond whose
failure ends at the mode its inline marker names (`# fails_when: FM-ID`, `// fails_when:` in C and
C++), else the test's only `@fails_when` mode, else "unassigned".

To fill in markers, draft them for a person to review. clew makes no model call; you propose and
they decide:

1. `clew wiki propose-modes [--files tests/test_x.py]` prints YAML: per test, its candidate modes
   with meanings, and each unmarked assertion with `proposed: null`, `status: unreviewed`.
2. For each assertion, read it and the meanings and set `proposed` to the ONE mode whose meaning
   names what that assertion would catch failing. Leave it `null` when none fits; do not stretch a
   meaning to fit. Do not change `status`.
3. Show the person the draft: each assertion, your proposal and a one-line reason. They set
   `status: accepted` or `rejected` per entry.
4. `clew wiki propose-modes --apply reviewed.yaml` writes only the accepted entries as markers. A
   line that no longer reads as its assertion is refused and named, and the run exits 2.

The gate refuses a marker or `@fails_when` id the catalogue does not declare.

## Audiences

`wiki.audiences` builds the same site with things withheld: `exclude_bodies` (source, activity
diagrams, recorded values), `exclude_requirement_text`, `exclude_owners`. Build one with
`clew wiki build --audience NAME`.
