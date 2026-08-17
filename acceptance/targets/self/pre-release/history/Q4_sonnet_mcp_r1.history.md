# Q4 — mcp — sonnet — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `mcp__doxyguard-db__search`
- **asked:** target, text
### 2. `mcp__doxyguard-db__search`
- **asked:** target, text
- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"precedence declared override default","note":"No matching symbols for 'precedence declared override default'. This is NOT an error and NOT a malformed call, an…

- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"build_argv CLI declaration","note":"No matching symbols for 'build_argv CLI declaration'. This is NOT an error and NOT a malformed call, and it is NOT a defini…

### 3. `mcp__doxyguard-db__dossier`
- **asked:** subject, target
- **got:** {"subject":"build_argv","subject_kind":"function","name":"build_argv","rowid":3349,"signature":" list[str] run_matrix.build_argv(str arm, str model, str prompt, Path target, Path mcp_config)","file":"acceptance/bench/run…

### 4. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"prose matches","count":25,"results":[{"file_path":"doxyguard_db/tiers.py","heading":"doxyguard_db/tiers.py — file-level documentation","snippet":"…is | combines by | |---|---|---|---| | 1 | explicit | a >>CLI<< …

**Reasoning.** Found it — `doxyguard_db/tiers.py`. Let me read that dossier fully.

### 5. `mcp__doxyguard-db__dossier`
- **asked:** kind=file
- **got ⚠ error:** Error executing tool dossier: Subject kind 'file' names no dossier subject: a file has no dossier — its documentation is `search(corpus='prose')`.

### 6. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/tiers.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""Five-tier precedence for every layered build option — ONE combination rule. 3	 4	`resolved = (tier1 or tier2 or tier5) union tier3 union tier4` 5	 6	In one line: **you can correct ou…

### 7. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/tiers.py
- **got:** 150	        """The tier is ALWAYS recorded; the stated layer only when tier 1 won. 151	 152	        Writing `explicit` unconditionally would make the read-back replay a 153	        declaration or the built-in guesses as …

**Reasoning.** I have everything needed for a complete, precise answer.

## Answer

**The rule lives in `doxyguard_db/tiers.py:1-329`**, specifically `resolve_layered()` (`doxyguard_db/tiers.py:300-335`) built on `_stated_layer()` (`doxyguard_db/tiers.py:345-358`).

### The five tiers (`doxyguard_db/tiers.py:8-14`, constants at `doxyguard_db/tiers.py:57-68`)

| tier | name | source | combines by |
|---|---|---|---|
| 1 | `explicit` | a CLI flag | REPLACES |
| 2 | `declared` | the target repo's `.doxyguard-db.yaml` (or `x-doxyguard-db` passthrough) | REPLACES |
| 3 | `target-fact` | facts someone else already

---

## Final answer as submitted

I have everything needed for a complete, precise answer.

## Answer

**The rule lives in `doxyguard_db/tiers.py:1-329`**, specifically `resolve_layered()` (`doxyguard_db/tiers.py:300-335`) built on `_stated_layer()` (`doxyguard_db/tiers.py:345-358`).

### The five tiers (`doxyguard_db/tiers.py:8-14`, constants at `doxyguard_db/tiers.py:57-68`)

| tier | name | source | combines by |
|---|---|---|---|
| 1 | `explicit` | a CLI flag | REPLACES |
| 2 | `declared` | the target repo's `.doxyguard-db.yaml` (or `x-doxyguard-db` passthrough) | REPLACES |
| 3 | `target-fact` | facts someone else already wrote (Doxyfile ALIASES/PREDEFINED, a generator manifest, a language/platform entry point) | ACCUMULATES |
| 4 | `ecosystem` | a known-ecosystem signature (e.g. UDM, ingot) | ACCUMULATES |
| 5 | `heuristic` | built-in name-pattern guesses (the floor) | REPLACES |

### The combination formula (`doxyguard_db/tiers.py:4`)

```
resolved = (tier1 or tier2 or tier5) union tier3 union tier4
```

In prose (`doxyguard_db/tiers.py:6`, `doxyguard_db/tiers.py:314-319`): tiers 1, 2, and 5 (`explicit`, `declared`, `heuristic`) are **mutually exclusive and only one wins** — pick explicit if present, else declared if present, else fall back to heuristics as the floor. Tiers 3 and 4 (`target-fact`, `ecosystem`) **always accumulate on top, regardless of which stated tier won**, and no stated tier can remove them — "you can correct our guesses; you cannot un-discover a fact" (`doxyguard_db/tiers.py:6`). The accumulating layers are placed first in the resolved order (`doxyguard_db/tiers.py:314-316`), so a target that states nothing at all resolves to exactly `(*facts, *ecosystem, *heuristics)` — the built-in default, unchanged.

Tiers 3 and 4 have **identical combination behaviour** by design (`doxyguard_db/tiers.py:24-29`) — the 3-vs-4 label only affects reporting/provenance, never the resolved set. The only load-bearing distinction is 3-or-4 (fact, permanent) versus 5 (guess, discardable).

For predicting an unseen setting: check whether it's a `LayeredResolution` (list-valued, via `resolve_layered`) or a `DocumentResolution` (manifest-valued, via `resolve_document`, `doxyguard_db/tiers.py:258-288`) — both implement the same three-way stated-tier choice (`_stated_layer` / the `if explicit / elif declared / else floor` chain at `doxyguard_db/tiers.py:284-288`), differing only in whether facts/ecosystem accumulate underneath (lists do; a document resolution has no accumulating counterpart since a manifest's effect is computed downstream in loaders, `doxyguard_db/tiers.py:202-207`).

### What an empty value on the command line means

**An empty/falsy CLI value is a withdrawal, not a statement** — it is treated identically to the flag being absent for override purposes, and control falls through to tier 2 (declared), then tier 5 (heuristic floor):

- For list options: `[]` is falsy, so `_stated_layer` falls through past `explicit` (`doxyguard_db/tiers.py:321-324`, `doxyguard_db/tiers.py:354-358`): *"An empty `explicit` IS A WITHDRAWAL, not a statement... which is what lets an operator undo a recorded flag without deleting the database. `None` means the flag was absent."* (Note: `None` = flag never given; `[]`/falsy = flag given but emptied — both fall through, but only `None` is indistinguishable from "never stated"; an emptied value is still recordable as a withdrawal.)
- For manifest/document options: `{}` (falsy) is likewise a withdrawal (`doxyguard_db/tiers.py:267-271`): *"Clearing an option means 'stop overriding', which is the same intent as 'fall back to the target's own declaration'."*

So: passing an empty value on the CLI does **not** clear the setting to nothing — it un-overrides it, deferring to whatever the repo's own `.doxyguard-db.yaml` declares, and if that's also absent, down to the built-in heuristic default.

## Gaps

- I did not trace every one of the ~15+ call sites that invoke `resolve_layered`/`resolve_document` to confirm each concrete CLI option (e.g. `--entry-patterns`, `--shared-key-patterns`) actually routes through this module rather than some bespoke path — the docstring at `doxyguard_db/tiers.py:16-22` states this module was introduced specifically to *unify* previously-inconsistent per-option behavior, implying some call sites may have been migrated after this file's `@version 1`; I did not verify migration completeness across the whole CLI.
- I did not open `doxyguard_db/cli.py`'s `_declared_or_flag` (referenced at `doxyguard_db/tiers.py:264`) to see the CLI-side wiring in full; the tiers.py module was sufficient to answer the rule itself.
