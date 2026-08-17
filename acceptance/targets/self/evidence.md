<!-- SPDX-License-Identifier: MIT -->
# evidence.md — `self`, pinned at `cd8d6e2`

Source facts behind every mark in `questions.md`. The judge never reads this file; it
exists so a mark can be checked rather than trusted.

## Provenance

`HEAD` was `cd8d6e2` with the working tree far ahead of it (~2,870 changed paths, of
which 17 under `clew/`). **Nothing here is derived from the working tree.** The
pinned package was extracted with `git archive cd8d6e2 clew` and every
behavioural claim was measured against that extraction; every textual claim cites a line
number in `git show cd8d6e2:<path>`. Line numbers below are pinned-tree line numbers.

Two kinds of fact appear. **Read** facts are lines of source. **Measured** facts were
produced by running the pinned package — the transcript of each measurement is quoted
inline, and a probe run against the working tree instead of the pin is refused unless
explicitly overridden, so an accidental worktree measurement cannot be mistaken for a
pinned one.

### The target tree must be materialized AT `cd8d6e2`

Q1 and Q2 are **pin-sensitive, and their truth INVERTS in the current working tree.**
Measured, both trees, same probe:

| | `cd8d6e2` | working tree |
|---|---|---|
| `derive_scope`, no declaration | `source=doxyfile`, no roots | `source=whole-repo`, root = repo |
| nested clone excluded | yes, at WARNING | no |
| nested submodule excluded | no | no |

The working tree has replaced the three-tier rule with two tiers and replaced exclusion
of nested trees with indexing-and-tagging. So a sweep whose `--target` points at the
dirty working directory would mark correct answers wrong on 20 of 70 marks. Materialize
the target as a **clean clone checked out at `cd8d6e2`**, not a `git worktree`: a
worktree shares the object database, and the `src` arm has `Bash`, so a rubric committed
later would be reachable through `git show`.

The other five questions were measured against both trees and are **invariant**.
`indexcache.py`, `treescan.py`, `tiers.py` and `dispatch.py` are byte-identical to the
pin; `doxygen.py` and `vocabulary.py` differ textually but produce identical probe
output.

### The answer key inside the target tree

`acceptance/targets/self/questions.md` exists at `cd8d6e2` — an older, unrun rubric that
names the tool, its tables and its tool calls directly. A target materialized at the pin
therefore contains **that** file, not this one. Its questions do not overlap these
(it asks about a Doxyfile-less repo, an empty dataflow layer, a query's payload path,
self-enforcement of the gate, rebuild triggers, and one requirement id). Bounded
contaminant, recorded rather than hidden.

This rubric can stay out of the answerer's reach: `run_matrix --questions` is a required
path with no default and is never added to `--add-dir`, and `--out` is likewise required,
so both belong outside the materialized target. Put `--out` outside this repository too —
the cell's working directory is `<out>/wd`, and a working directory nested inside the
live repo puts this file within reach of a `Read`.

---

# Q1 — What decides which files a build reads?

All in `clew/scope.py`.

- **Module and function.** Module docstring L2-19; `derive_scope` L139-157.
- **Three ordered tiers.** L2: *"a declaration, else the Doxyfile, else the whole repo"*;
  L4-8 names all three. Provenance constants L43-51: `SOURCE_DOXYFILE`,
  `SOURCE_WHOLE_REPO`, `SOURCE_DECLARED`. `derive_scope` L156 is the first two
  (`_declared_index_scope(...) or _doxyfile_fallback(...)`); `whole_repo_scope` L165 is
  the third.
- **Both declaration locations.** `_declaration_advice` L127-130 emits both spellings from
  imported constants: `x-<tool>: index_scope:` in the guard config, or `index_scope:` in
  the dedicated dotfile. `_declared_index_scope` L377 reads them through
  `load_declaration_located`. `declaration.DECLARATION_NAME = ".clew.yaml"`
  (`declaration.py` L65).
- **Only the declared tier overrides.** `DerivedScope.is_derived` L87-89:
  `self.source == SOURCE_DECLARED and bool(self.roots)`. Docstring L69-72 states the
  other two carry no overriding roots.
- **The middle tier names no roots.** `_doxyfile_fallback` L557-574 constructs
  `DerivedScope(source=SOURCE_DOXYFILE, reason=...)` with `roots` defaulted to `()`
  (L80). Docstring L558-560: *"Names NO roots, which is what makes it a fallback rather
  than a decision"*, and this module never reads the external `INPUT`.
- **Last tier subtracts.** `whole_repo_scope` L184-185:
  `excludes = [*_gitignored_paths(root), *_pruned_dirs(root, ...)]`. `_gitignored_paths`
  L221-231 runs `git ls-files --others --ignored --exclude-standard --directory`;
  `_pruned_dirs` L254-274 with `_skip_dir` L97-99 (dot-directories and `_SKIP_DIR_NAMES`
  = `__pycache__`, `node_modules`, L35).
- **The gate pattern is not a tier.** Module docstring L10-14: *"The doxygen-guard hook's
  `files:` pattern is deliberately NOT one of them… it answers what must be DOCUMENTED,
  not what should be REASONABLE-ABOUT"*, and records that standing in for the index
  decision *"also shadowed the fallback that would have worked"*. Repeated at L176-177.
  **Measured** — a repo carrying only a guard config with a `files:` pattern:

      source     = doxyfile
      roots      = []
      is_derived = False

- **A declared root is never walked.** `_declared_index_scope` docstring L361-366: *"A
  declared root is TAKEN AT ITS WORD AND NEVER WALKED, which is the whole point"*.
  `_existing_paths` L507-518 checks only `path.exists()`.
- **Fallback logs at WARNING with a reason.** `derive_scope_logged` L583-603: `INFO` when
  `is_derived()`, `logger.warning("scope: falling back…")` otherwise (L602).
  `_guard_config_note` L527-548 distinguishes *"no config was found (searched …)"* from
  *"a config WAS found at X (via Y), but it carries no index_scope"*. **Measured** reason
  string, guard config present:

      no index_scope is declared for this repo — a doxygen-guard config WAS found at
      <root>/.doxygen-guard.yaml (via repo root), but it carries no index_scope. The
      indexed tree is the Doxyfile's own INPUT, or the whole repository when the repo
      ships no Doxyfile. Declare `x-clew: index_scope:` in .doxygen-guard.yaml,
      or an `index_scope:` in .clew.yaml, to let the two differ.

- **Precedence not backwards.** The `or` at L156 puts the declaration ahead of the
  fallback; there is no code path in which the guard pattern supplies roots.

---

# Q2 — What keeps a foreign codebase out, and what gets through anyway?

All in `clew/scope.py`.

- **The containment step.** `_with_nested_repos_contained` L315-330 →
  `_nested_repo_excludes` L403-433 → `_nested_repos_under` L441-473. L459:
  `if ".git" in dirnames and here != input_root:` appends the directory.
- **Warned, not silent.** `_nested_repo_excludes` L424-431 logs at WARNING with the
  remedy. Docstring L406-408: *"REPORTED at WARNING: removing part of what a repo's own
  declaration or gate covers is not something to do quietly."* **Measured** warning:

      index_scope: <root>/vendor/nested_clone is a NESTED repository inside INPUT root
      <root> — excluding it. Two codebases in one index cannot be told apart in a search
      result; declare it under index_scope.excludes to silence this, or move it out of
      the root.

- **Single shared exit.** Called at L157 (`derive_scope`) and L186 (`whole_repo_scope`) —
  the only two exits the module has. `derive_scope` docstring L145-149: *"the CHOKE POINT
  every scope this module hands out passes through… Containment is a property of the
  SCOPE, not of the tier that produced it. Applying it inside a tier buckles a safety
  property to a code path."* `_with_nested_repos_contained` docstring L316-317:
  *"Tier-agnostic by construction: it reads only `roots` and `excludes`."*
- **A root is not nested in itself.** L459 `and here != input_root`; docstring L411-413.
- **Already-excluded not re-warned.** L422: `if any(_is_within(nested, ex) for ex in
  excludes + found): continue`, before the log call. Docstring L408-410: *"a warning there
  would train an owner to ignore the one that matters."*
- **Bounded walk, not a recursive glob.** `_nested_repos_under` docstring L442-446: *"A
  BOUNDED walk, not `rglob`. `rglob` would descend into the object stores of the
  repositories it finds and swallow an unreadable directory silently."* Descent stops at a
  hit (L461 `dirnames[:] = []`) and at `_MAX_DEPTH = 16` (L40, checked L463).
- **Unreadable directory warns.** `os.walk(..., onerror=_warn_unwalkable)` L457;
  `_warn_unwalkable` L480-486: *"it was NOT checked for a nested repository"*.
- **A SUBMODULE IS NOT EXCLUDED.** `os.walk` yields `dirnames` — directory names only — so
  a submodule's `.git`, which is a 40-odd-byte file holding `gitdir: …`, never appears in
  it. The same module tests the other way 155 lines earlier: `_descendable` L304 uses
  `(child / ".git").exists()`, true for a file or a directory. Two `.git` tests, one
  module, different answers. **Measured** on a tree holding one nested clone (`.git`
  directory) and one nested submodule (`.git` file):

      whole_repo_scope                      nested_clone excluded = True
                                            nested_submodule excluded = False
      derive_scope (declared roots)         nested_clone excluded = True
                                            nested_submodule excluded = False

  Note `_descendable`'s hit merely prunes the walk (L304-305 `continue`) without appending
  to `found`, so it never supplies an exclusion — which is why the disagreement is not
  masked.
- **The middle tier is unaffected.** `_with_nested_repos_contained` L327-329 returns the
  scope untouched when `_nested_repo_excludes` finds nothing, and a fallback has no roots
  to walk. Docstring L319-321. **Measured**: `derive_scope` with no declaration gives
  `source=doxyfile`, `roots=[]`, neither nested tree excluded.

---

# Q3 — The configuration it wants is missing, or present and not trusted

All in `clew/doxygen.py`.

- **Search order.** `discover_doxyfile` L145-190; `_DOXYFILE_DIRS = ("docs", "doc")`
  L137; the loop L187-189 tries `repo/"Doxyfile"` first, then each directory.
  **Measured**: root present → `Doxyfile`; only `docs/` present → `docs/Doxyfile`; both →
  `Doxyfile`.
- **Refuses to adopt strays.** L190 `return None`. Docstring L156-157: *"REFUSES TO GUESS
  beyond those locations."*
- **The incident.** Docstring L156-163: it used to be
  `sorted(repo.glob("*/Doxyfile"))[0]` — *"any subdirectory, resolved alphabetically"* —
  and *"selected `sample/Doxyfile`, the demobot TEST FIXTURE, to index the whole
  project"*, producing *"a well-formed database describing the wrong code."*
- **Wrong is worse than none.** Docstring L167-168: *"A wrong Doxyfile is worse than none,
  because none triggers synthesis from the declared scope."* `synthesize_doxyfile` L410.
- **Four outcomes.** Constants L201-204: `DOXYFILE_EXPLICIT_MISSING`, `DOXYFILE_NO_TARGET`,
  `DOXYFILE_ABSENT`, `DOXYFILE_REJECTED`. Comment L193-200: *"Two are supported routes
  that proceed via synthesis, two are genuine refusals."*
- **The two/two split.** `_DOXYFILE_FATAL_SITUATIONS = frozenset({DOXYFILE_EXPLICIT_MISSING,
  DOXYFILE_NO_TARGET})` L358; classification `_doxyfile_situation` L263-282.
  **Measured**, all four:

      no Doxyfile anywhere                 situation='absent'           is_error=False
      stray Doxyfile in a subdirectory     situation='rejected'         is_error=False
      explicit --doxyfile not on disk      situation='explicit_missing' is_error=True
      neither flag given                   situation='no_target'        is_error=True

- **Severity travels with the message.** `DoxyfileResolution` L209-228, docstring L211-214:
  *"`is_error` is carried alongside the message rather than inferred by the caller from the
  kind… A caller cannot log the reassuring sentence at ERROR."* Set at L401.
- **The explicit-missing action.** `_msg_explicit_missing` L289-298 offers `--repo-root`,
  not `--doxyfile`. `describe_doxyfile_resolution` docstring L380-383: *"the one case the
  old text got actively wrong: it answered 'Pass --doxyfile'."*
- **Strays exposed without adoption.** `rejected_doxyfile_candidates` L236-253, docstring
  L244-246: *"Deliberately NOT a behaviour change. `discover_doxyfile` still returns None
  for every path this lists."* **Measured**: with `sample/Doxyfile` present,
  `discover_doxyfile → None` while `rejected_candidates → ['Doxyfile']`.
- **"Ships none" is supported.** L389-391: *"`absent` … NOT fatal, and this is the bullet
  gh#4 leads with: a SUPPORTED configuration that the tool handles well and used to greet
  with an error."*

---

# Q4 — A declaration and a command-line flag disagree

All in `clew/tiers.py`.

- **One rule, one module.** Docstring L1-2: *"Five-tier precedence for every layered build
  option — ONE combination rule."*
- **Five tiers.** Table L9-15: explicit / declared / target-fact / ecosystem / heuristic.
  Constants L58-70; `TIER_ORDER` L74-77.
- **The rule.** L3: `resolved = (tier1 or tier2 or tier5) union tier3 union tier4`. L5 in
  words: *"you can correct our guesses; you cannot un-discover a fact."* `STATED_TIERS`
  L80 = (explicit, declared, heuristic); `ACCUMULATING_TIERS` L83 = (target-fact,
  ecosystem). Implemented `resolve_layered` L164-199, values assembled L196
  (`(*facts, *ecosystem, *stated)`).
- **Precedence among stated tiers.** `STATED_TIERS` L80 is highest-first; `_stated_layer`
  picks the first non-empty. **Measured**:

      nothing stated                 tier=heuristic  ['main','app_main','*_entry','*_task']
      explicit flag                  tier=explicit   ['main','app_main','only_this']
      declaration                    tier=declared   ['main','app_main','from_decl']
      flag AND declaration           tier=explicit   ['main','app_main','flag']
      ecosystem + explicit flag      tier=explicit   ['main','app_main','udm_entry','only_this']

  `facts` survived in every case; the heuristic guesses survived only when nothing was
  stated.
- **Guesses are the only displaceable layer.** L68-70: tier 5 is *"the floor, and the only
  built-in layer a stated tier is allowed to displace."* L23-25 records the reason.
- **Empty vs absent.** `resolve_layered` docstring L191-194: *"AN EMPTY `explicit` IS A
  WITHDRAWAL, not a statement. `[]` is falsy, so it falls through… `None` means the flag
  was absent."* **Measured**: both `explicit=[]` and `explicit=None` give
  `tier=heuristic` with the full guess set restored.
- **Tier recorded; replay only for tier 1.** `LayeredResolution` L106-131 binds values,
  tier and stated layer; `as_meta` L136-153 writes the tier always and the stated values
  only when `self.tier == TIER_EXPLICIT` (L151). Docstring L143-147 gives the reason —
  replaying a declaration *"would freeze a stale declaration"*. **Measured**:

      explicit  -> {'entry_patterns.tier': 'explicit', 'entry_patterns.explicit': 'f'}
      declared  -> {'entry_patterns.tier': 'declared'}

- **The incident.** Docstring L22-25: *"passing `--entry-patterns` dropped `main`,
  reachability collapsed, and NOTHING reported it."* Corroborated independently in
  `signature.py` L40-41 as a reason an older build must be rebuilt. Tier selection is
  `_stated_layer` L210, called from L195.
- **Keyword-only.** `resolve_layered` L165 `*,`; docstring L180-184: *"five same-typed
  sequence arguments in a row is a transposition waiting to happen and transposing `facts`
  with `heuristics` would invert the whole rule silently."*
- **Not "the command line wins".** L15 shows tier 5 also REPLACES, and tiers 3/4 outlive
  every statement, so the flag governs one layer only.

---

# Q5 — One module owns every enumerated value

`clew/vocabulary.py`, with its test in `tests/test_vocabulary.py`.

- **The module.** Docstring L1-49; `@brief Central registry of the schema's enumerated
  value sets` L47.
- **Generated, and single-source.** `Vocabulary.check` L129-138 builds the clause.
  **Measured**: `grep -rn "CHECK(" clew/` across the whole pinned package matches
  `vocabulary.py` only (lines 30, 31, 126, 138, 937, 955, 966 — all within that file).
  Enforced by `tests/test_vocabulary.py::test_no_raw_check_literal_survives_outside_vocabulary`
  (L95), which walks `PACKAGE.rglob("*.py")` (L92) — chosen over `git ls-files` because the
  git-aware gate cannot see untracked files (L85-91) — plus
  `test_package_sources_were_actually_scanned` (L113) so an empty scan cannot pass
  vacuously, and `test_no_module_redefines_a_valid_constant` (L123).
- **One object does both jobs.** `check` L129 generates the constraint; `validated` L159
  vets a declared token. Docstring L12-14: *"the DDL asks it for a clause… and the
  declared-config loaders ask the SAME object to validate a token."*
- **True leaf.** **Measured**: the only import lines in the file are L51
  `from __future__ import annotations`, L53 `from dataclasses import dataclass, field`,
  L54 `from pathlib import Path`. No intra-package import; no `import logging` either
  (L58-59 records that the logger would come from `logging` directly if one were ever
  needed).
- **The reason.** Docstring L16-20: *"`clew/_common.py` pulls in `rich`, while
  `clew/query/_common.py` is deliberately stdlib-only; importing either here would
  make one of those two layers un-importable without the other's dependencies."*
  `tiers.py` L42-45 takes the same discipline for the same reason.
- **Identical tuples, separate objects.** Docstring L22-28 claims five. **Measured** —
  5 of the 32 exported `Vocabulary` objects have `values == ("low","medium","high")`, and
  `len({id(v) for v in them}) == 5`:

      ACQ_STRENGTH       acq_strength       BOUNDARY_STRENGTH  boundary_strength
      KEY_STRENGTH       key_strength       LOCK_IDENTITY      lock_identity
      THREAD_STRENGTH    thread_strength

  A source grep finds only four (L282, L357, L383, L420) because `BOUNDARY_STRENGTH`
  (L502) spells its last member as the constant `BOUNDARY_STRENGTH_HIGH` (L479).
- **Consequence of merging.** Docstring L24-28: *"Binding one object to all five would mean
  that adding a value for one silently widens the CHECK on the other four, while every
  test that compares the shipped schema to this registry stays green."*
- **Explicit quoting, not a repr.** L137
  `", ".join("'" + v.replace("'", "''") + "'" for v in self.values)`. Docstring L30-35
  names both failures. **Measured**:

      one-value set  -> CHECK(c IN ('only'))        trailing comma present? False
      apostrophe     -> CHECK(c IN ('it''s', 'other'))

  L34-35 records that the old idiom survived only because every set it was applied to
  happened to have two or more values.
- **Ordered tuple, not a set.** L36-38: *"`values` is also a TUPLE, never a set: set
  iteration order is not part of any contract, and a set here would make the shipped
  schema text vary between builds."* `Vocabulary.values: tuple[str, ...]` L119; L105.
- **Fails closed.** `validated` L167-171 raises `DeclarationError` (L65). Docstring L40-43:
  *"`acq_form`/`acq_role`/`acq_mode` have no 'unknown' member at all."* **Measured**:

      DeclarationError: probe.yaml: invalid kind 'not_a_lock_kind' — allowed: mutex,
      recursive_mutex, shared_mutex, semaphore, spinlock, unknown

- **Explicit rank.** `Vocabulary.rank` L121; docstring L106-109 gives the reason.
  **Measured**: `CALL_MATCH.values = ('exact','resolved','fuzzy')` with
  `rank = {'exact': 2, 'resolved': 1, 'fuzzy': 0}` — strongest first — against
  `ACQ_STRENGTH` weakest first, so a positional ordinal would invert one of them.

---

# Q6 — A mis-spelled key in a manifest

`clew/dispatch.py`, plus `clew/declaration.py` for the last mark.

- **The rejection helper.** `_reject_unknown` L109-121: collects
  `[k for k in mapping if k not in allowed]` and raises when non-empty.
- **Both levels — four call sites.** Document level L429
  (`_reject_unknown(doc, _DOCUMENT_KEYS, origin)`); entry level L327 (interfaces), L354
  (dispatch tables), L375 (shared-key wrappers). Key sets L96-99: `_DOCUMENT_KEYS`,
  `_INTERFACE_KEYS = {"interface", "binds", "methods", "boundary"}`, `_TABLE_KEYS`,
  `_WRAPPER_KEYS`.
- **Message names offender and allowed set.** L119-120 formats both. Docstring L110-112:
  *"Names the offending keys AND the allowed set, so the fix is mechanical."*
- **The singular slip is REJECTED.** **Measured**, a manifest whose top-level key is
  `interface:` instead of `interfaces:`:

      DeclarationError: <path>/bad.yaml: unknown key(s) 'interface' — allowed:
      dispatch_tables, interfaces, key_alias_prefixes, shared_key_wrappers

  This contradicts the repository's own `CLAUDE.md`, which still describes the hole as
  open (*"every singular/plural slip … parsed to an empty manifest and built GREEN"*).
  At `cd8d6e2` it is closed. The mark follows the measurement, not the prose.
- **Entry level matters as much.** `_WRAPPER_KEYS` L99 contains `key_arg_index`; a
  mistyped `key_arg_idx` would, absent this check, leave the wrapper keying off argument
  0. The same shape applies to `_TABLE_KEYS`' `handler_arg_index` (L98).
- **Success path.** **Measured**, a well-formed manifest —
  `interfaces: [{interface: Sensor, methods: [read], binds: [TempSensor]}]` — loads to a
  `DispatchManifest` carrying one `InterfaceBinding`. (An earlier probe using invented
  entry keys `base`/`method`/`implementors` was itself rejected at the entry level, which
  is how the real `_INTERFACE_KEYS` spelling was established.)
- **One error type.** `DeclarationError` is defined in `vocabulary.py` L65 and raised by
  `dispatch._reject_unknown` L118, so the manifest loader and the enumerated-value
  registry fail with the same type.
- **Unparseable file is different.** `declaration.py` L178-181 and L265 return an empty
  mapping *"when unreadable, malformed, or not a mapping"*, warning rather than raising
  (L213). **Measured**, a truncated flow sequence in the declaration:

      <root>/.clew.yaml is unreadable (while parsing a flow sequence …) —
      ignoring it, using defaults
      sections found = []

  So a mistyped KEY aborts and an unparseable FILE degrades to defaults — opposite
  handling, deliberately.
- **Not permissive.** Every one of the four call sites raises rather than filtering.

---

# Q7 — How does it avoid redoing work, and what makes it decide it must?

`clew/indexcache.py` and `clew/treescan.py` (both byte-identical to the
pin in the working tree), plus `clew/cli.py`.

- **Two modules, split by responsibility.** `treescan.py` L2-6: *"this module answers
  'what files does this build read, and what is each one's identity?' — the filesystem
  side — while `indexcache` owns the sidecar SQLite store."* Mirrored in `indexcache.py`
  L4-5.
- **Sidecar, and why.** `indexcache.py` L7-10: *"clew.db is rebuilt from scratch on every
  run (doxygen → copy → augment → `os.replace`), so the incrementality state cannot live
  inside it. It lives in a sidecar SQLite file (`<output>.idxcache` by default)."* Default
  computed in `cli.py` L1365 (`output.with_name(output.name + ".idxcache")`), described to
  the operator at `cli.py` L450.
- **Atomic swap.** `cli.py` L1378: *"Build into a sibling temp DB, then os.replace() it
  onto --output"*; executed L1431 with the comment *"atomic swap onto the live path"*.
- **Prefilter vs authority.** `indexcache.py` L12-14: *"mtime+size is only a PREFILTER
  (skip re-hashing when both match); the sha256 of the file's bytes is the AUTHORITY."*
  Same claim, independently, `treescan.py` L8-9.
- **Consequences.** `indexcache.py` L14-15 and `treescan.py` L10-12: *"a `touch` with no
  edit and a branch checkout that restores identical content both stay cache HITS, which
  mtime alone cannot do."*
- **Trigger-happy, with the asymmetry.** `indexcache.py` L23-25: *"Invalidation is
  deliberately trigger-happy — **when in doubt, MISS**. A false miss costs time; a false
  hit ships a wrong database."*
- **Three invalidation axes.** `indexcache.py` L25-28: the build-version constant *"wipes
  the whole cache"*; *"each stage carries its own `STAGE_VERSION`"*; manifest inputs *"fold
  their content hashes into the affected stage's `extra_key`"*. In code: the wipe is
  `_invalidate_on_build_version` L104-128, called from the constructor L95, comparing
  against `CLEW_BUILD_VERSION` (L114, imported L43); stage version and extra key
  are part of the cache primary key L63 and of every lookup/store (L231-232, L249-254).
  `STAGE_VERSION` appears in this module alone across the pinned package.
- **Payloads carry no row identifiers.** L15-19: *"Payloads are rowid-FREE (they record
  source LINES + identifier text); rowid resolution happens on every build against the
  freshly generated memberdef table, because doxygen rowids are not stable across runs."*
- **What is not incremental.** L20-22: the third store maps `tree_sha` to the external
  tool's output *"so an unchanged tree skips the (non-incrementable) doxygen run
  entirely"* — skipped wholesale, never partially.
- **Per-file identity recorded.** L11-12: `size`, `mtime_ns`, `content_sha`. Schema
  `source_files` L51-56 (`path` primary key, `size_bytes`, `mtime_ns`, `content_sha`);
  `treescan.FileIdentity` L31-32.

---

## Unestablished, and therefore not graded

- **The gate's own coverage of this repository.** `.doxygen-guard.yaml` at the pin was
  read but its interaction with the pinned `requirements.yaml` was not re-measured, so no
  mark claims a documented-coverage figure.
- **Counts of anything.** No mark states a file, symbol, function or line count. Those
  move between the pin and any materialization detail, and the template forbids
  instrument-derived figures; the one place a count appears (five identical value sets) is
  measured from the pinned module and phrased to accept an approximate answer.
- **`Q2`'s submodule finding as a *defect report*.** Whether the disagreement between the
  two `.git` tests is a bug or an accepted bound is not established at the pin — no test,
  issue or comment in the pinned tree addresses it. The mark asks only that the answerer
  find that a submodule is not excluded, which is measured.
