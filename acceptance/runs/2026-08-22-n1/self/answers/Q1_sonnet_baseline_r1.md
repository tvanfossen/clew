## What decides the file set

Three independent decisions compose to produce the final file list, and none of them defaults to "whatever's in the Doxyfile's own INPUT":

**1. Scope — *which directories* are eligible (`clew/scope.py`)**

`derive_scope()` checks exactly one thing: does the repo declare an `index_scope:` section, either in `.clew.yaml` or via the `x-clew` passthrough inside a `.doxygen-guard.yaml`? That section has two keys, `roots:` (required — it *replaces* the scope) and `excludes:` (optional). A declared root that doesn't exist on disk is dropped with a warning rather than silently passed through to doxygen.

If a declaration exists and yields at least one usable root, that becomes `SOURCE_DECLARED` and those roots/excludes are taken **at their word, never walked** for nested repos.

Critically, the target's own `Doxyfile` `INPUT =` line is **not** a tier here at all (removed in gh#333). The code frames this explicitly: a Doxyfile's `INPUT` states a *documentation* target, not a *reasoning* boundary — honoring it used to mean a repo that published a clean API-doc Doxyfile (e.g. `FILE_PATTERNS = *.h`) got a narrower index than a repo that shipped no Doxyfile at all, which is backwards. The Doxyfile is still read for `ALIASES`/`PREDEFINED`/filters, but its `INPUT` is always overridden (`replace_input=True` whenever scope is folded in).

**2. Pattern — *which filenames within those directories count* (`clew/doxygen.py`)**

`FILE_PATTERNS` is now **forced** to doxygen's own stock extension list (the same set `doxygen -g` writes into a fresh Doxyfile — `.c/.cc/.h/.py/.md/...`, ~60 patterns), appended last so it overrides anything the target's Doxyfile declares. This closed gh#340: a target declaring a narrow `FILE_PATTERNS = *.h *.cpp *.md` was silently dropping `.c`/`.cu` files that scope had just admitted (measured losing 2 definitions from entropic's own `main`, plus all of a vendored submodule). `declared_file_patterns()` still reads the target's own declaration, but purely for *reporting* the difference — it's no longer policy.

**3. Content identity, not extension filtering, at hash time (`clew/treescan.py`)**

`enumerate_tree()` walks the resolved INPUT roots recursively, pruning EXCLUDE subtrees during descent (not filtering after), and deliberately does **not** apply an extension filter — everything under INPUT gets hashed. This is the conservative side of "when in doubt, MISS": any change anywhere in the admitted tree invalidates the cache, even to a file doxygen itself wouldn't parse.

## What happens when nothing is declared

No `index_scope:` anywhere → `derive_scope` falls through to `whole_repo_scope()`, the default tier since gh#333, not a last resort:

- The **single INPUT root is the repo root itself** — the whole tree.
- Subtracted: everything `git ls-files --ignored --others --exclude-standard` reports (build output, venvs, caches) **on both sides of every submodule boundary** — a nested repo's own `.gitignore` is invisible to `git` at the parent level, so it's queried separately — plus dot-directories and known cache dirs (`__pycache__`, `node_modules`) that no repo declares as source.
- **Nested git trees (submodules, stray clones) are walked into and indexed, not excluded** (gh#333/gh#335) — they used to be cut out entirely, which meant a `chain_trace` into a submodule boundary just said "left the repo" instead of showing what the call does. They're now tagged `external` post-build (`external.py`) so two codebases in one index stay distinguishable, but their source is in the index.
- `FILE_PATTERNS` is still the forced doxygen-default set regardless of scope tier, so "nothing declared" doesn't narrow extensions either.

This fallback is **logged at WARNING**, not silently applied — `derive_scope_logged` distinguishes a declared scope (logged at INFO with its roots) from the whole-repo default (WARNING, with the reason plus a sentence telling the owner exactly how to declare `index_scope:` to narrow it). If the repo also ships no Doxyfile at all, one is synthesized (`synthesize_doxyfile`) with just `PROJECT_NAME`/`OUTPUT_DIRECTORY`/`STRIP_FROM_PATH` and empty `INPUT` — the scope-derived roots fill `INPUT` in afterward via `replace_input`, so an empty synthesized Doxyfile never produces an empty build (a prior mbedtls regression: clean `rc=0`, 0 functions indexed).

Net effect: a repo that declares nothing about itself gets indexed *in full* (minus what git already says to ignore), rather than getting a narrower index — the tool treats silence as "index everything you can prove is safe to skip," never as "index nothing" or "guess a subset."
