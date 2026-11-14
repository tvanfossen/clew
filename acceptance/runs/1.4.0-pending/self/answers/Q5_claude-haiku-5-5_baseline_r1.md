There are three ways to say so, in descending precedence. When two disagree, the higher one wins for that option, with the exceptions noted below.

**The three routes**

| Route | Where it comes from | Reaches |
|---|---|---|
| **Tier 1: stated for this build** | CLI flags (`--declare FILE`, `--exclude`, `--output`, `--rebuild`, `--verbose`), or the `options` mapping on `build_index()` / MCP `index(action="refresh")` | Any caller, including one with no shell |
| **Tier 2: declared** | `<repo>/.clew.yaml` in the target repo | Both CLI and MCP, since both already know the repo root |
| **Tiers 3–5: defaults** | Facts already in the tree (Doxyfile aliases, manifests), known-ecosystem signatures, and name-pattern heuristics | Built in |

`--declare` and the `options` mapping are the same route. `_apply_declared_document` hands the whole mapping to `apply_options` (`clew/cli.py:586`). The `.clew.yaml` file is the only way to state things in-tree. `--scope` and `--index-cache` are build mechanics, not declarations, so they have no config home.

The `guard:` section of `.clew.yaml` configures the gate, not the index. The index drops it when loading (`clew/declaration.py:304`).

**When they disagree**

The rule is in `clew/tiers.py`: `resolved = (tier1 or tier2 or tier5) ∪ tier3 ∪ tier4`.

- **Same option, tier 1 and tier 2:** the flag or `--declare` replaces the `.clew.yaml` value. The file is the standing statement, and the flag is a deliberate one-off override (`clew/cli.py:1619`). Only the options you name are replaced. Other sections still come from `.clew.yaml`. The code shows this per option, so I inferred the section-level behavior.
- **An empty value:** an empty stated value withdraws to the declaration rather than clearing it. Absent inherits, empty withdraws, and non-empty replaces.
- **Tiers 3 and 4:** these accumulate. Nothing stated can remove a target fact or an ecosystem signature. This is so that passing `--entry-patterns` cannot silently drop `main` and collapse reachability.
- **Tier 5 heuristics:** these are the only defaults a stated value displaces.
- **`--scope` with `index_scope`:** this is a hard error with exit 1, not a silent override. A stated `index_scope` is only read on `--scope from-guard`. Pairing it with any other scope would build a different boundary and report success (`clew/cli.py:783`).
- **A rejected `index_scope`:** the CLI and MCP refuse the build. The internal `derive_scope` falls back to the whole repo with a warning (`clew/scope.py:606`, `:634`).

**Other failure behavior**

- An unknown top-level section in `.clew.yaml` is refused by name. A misspelled key inside an inline `options` value is also refused, so it cannot read as a valid but unused mapping.
- Sections prefixed `x-` are tolerated and ignored with a warning, so experimental keys do not break older clew builds.

**Provenance**

The winning tier is recorded in `build_meta` for each option. Only tier-1 statements are replayed onto later builds, so the index can carry a policy the repo does not declare. Tier 2 is re-read from the file each time.

**Unverified:** I did not confirm whether `--declare` and `.clew.yaml` merge per option or whether `--declare` replaces the file entirely. The per-option semantics in `_apply_declared_document` point to a merge, but I did not trace the full load path.