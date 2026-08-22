I've got the whole decision chain from `clew/scope.py`. Here's how it works.

## The decision: two tiers, in order

`derive_scope()` (clew/scope.py:185) tries exactly one thing before falling back: **does the repo declare an `index_scope:` section?** There's no third tier anymore — a repo's `Doxyfile` used to supply the `INPUT` list as a fallback, but that was ripped out in gh#333, and the module docstring explains why in blunt terms: reading a Doxyfile's `INPUT` as a scope boundary inverted the tool. Measured on Mbed-TLS, whose `doxyfile.mbedtls` sets `INPUT = ../include` and `FILE_PATTERNS = *.h`: honoring it indexed 1,571 header declarations and *zero* of the 108 `library/*.c` implementations. A repo that shipped a Doxyfile — i.e., one that documented itself more carefully — got *punished* with a narrower index than a repo that shipped nothing. So a Doxyfile is still read for `ALIASES`/`PREDEFINED`, but its `INPUT` is never trusted as a reasoning boundary again.

**Tier 1 — declared.** `_declared_index_scope()` (line 448) looks for an `index_scope:` block either in the repo's own `.clew.yaml` or in the `x-clew` passthrough section of its `.doxygen-guard.yaml`. The block is strict:
- Only two keys are accepted: `roots` and `excludes`. Any other key (e.g. a typo'd `exclude:` instead of `excludes:`) is rejected outright with a message naming the bad key — this closes a real bug (gh#5) where an unrecognized key silently parsed as valid YAML but was never read, and the build just reported "no index_scope declared" with no way to tell a schema slip from a missing feature.
- `roots` is **required** and **replaces** the scope entirely — `excludes` alone does nothing.
- Each declared root/exclude is resolved relative to repo root and must exist on disk; a stale entry is dropped with a warning, not silently passed to doxygen (which would just emit a confusing "input not found").
- There's also a "tier 1" caller-stated override (`stated` dict, gh#382) — an embedding caller can hand scope directly at call time rather than through a file, built through the identical validation path so it can't diverge in behavior from a written declaration.

**Tier 2 — whole repo.** If nothing usable was declared, `whole_repo_scope()` (line 226) is the default — not a last resort, the docstring is explicit that this has been the default since gh#333. Its root is the entire repository, minus:
- everything `git ls-files --ignored` reports (run per-repo, and *also* per nested git tree, since a submodule's own `.gitignore` is invisible to `git ls-files` in the parent — without that second pass, vendored build output like CMake `FetchContent` deps walks straight back in)
- dot-directories and known cache/vendor dirs (`__pycache__`, `node_modules`) pruned by `_skip_dir`

Nested git trees (submodules, stray developer clones) are **included**, not excluded — that also changed at gh#333. They used to be walked-for and cut out on the theory that two codebases in one index are indistinguishable; the fix instead tags them via `external.py` so they're indexed but distinguishable in a query result, rather than made invisible to `chain_trace`.

## What happens when nothing is declared

That's exactly the state of *this* repo, visible in the `index(action='status')` output I pulled: `"reason":"no index_scope is declared for this repo — a doxygen-guard config WAS found at .doxygen-guard.yaml (via repo root), but it carries no index_scope — so the whole repository is the index scope, INCLUDING any nested git trees, less the paths git ignores and the dot/cache directories."` — with excludes reported as `.github, .claude-plugin`.

Note the log-level asymmetry in `derive_scope_logged()` (line 761): a declared scope logs at **INFO**; falling through to whole-repo logs at **WARNING**, specifically so a boundary nobody chose is never mistaken for one somebody actually set.
