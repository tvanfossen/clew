<!-- SPDX-License-Identifier: MIT -->
# Rust

| | |
|---|---|
| front end | **rustdoc JSON** — `cargo +nightly rustdoc -- -Z unstable-options --output-format json` |
| requires | `cargo` **and a nightly toolchain**. `rustup toolchain install nightly` |
| doxygen | **not used, not required.** `clew init` reports `doxygen  not required` for a cargo repo |

Doxygen has no Rust parser — a `.rs` file fed to it produces zero rows, silently. So
`clew/rustdoc.py` synthesizes the same `path`/`refid`/`memberdef`/`compounddef`/`member`/
`reimplements` tables from rustdoc's JSON, and every downstream harvester runs unmodified.

Routing is automatic: a repo with a `Cargo.toml` and no discoverable Doxyfile builds through
rustdoc. A repo that ships its own Doxyfile keeps doxygen — an owner who configured one wins over
Cargo.toml's mere presence.

## Measured

[brandon-arrendondo/knots](https://github.com/brandon-arrendondo/knots) @ `9be25b3`, whole-repo
scope, no declaration:

| | |
|---|---|
| `memberdef` / functions | 351 / 342 |
| `compounddef` | 38 |
| `call_edges` | 233 — `ast` 216, `ast_member` 17 |
| `xrefs` / `threads` | 0 / 0 |
| barren files · undocumented | 0 · 0 |

## You do not need doc comments

Private, entirely undocumented functions come back from `dossier` with full signature, body,
callers, callees and liveness. `///` fills in `brief` and `detail` and nothing else. The
translation is mechanical and does not depend on prose being present, so **do not invest in doc
comments before indexing** — the requirement is zero.

## `//!` module docs do something `///` does not

File-level docs feed `search`'s conceptual path — `search("deadlock")` finding a module about
lock nesting even though nothing is named that. That is a different mechanism from the per-symbol
`brief`/`detail` that `///` produces. A `//!` at the top of a file whose value is conceptual (a
metrics module, a dispatch or threading module) is worth more than `///` on each of its functions,
for the same reason a C file benefits from a leading `/*! ... */`.

## Limitations, and they are structural

**`xrefs` is empty by construction.** rustdoc's JSON is a documentation index — items,
signatures, docs — not a call graph. Where a C/C++ target gets an edge layer from doxygen, Rust
gets none, so **every Rust call edge comes from tree-sitter alone.**

**Method-receiver resolution is the weak layer.** Resolving `self.foo()` or `x.bar()` needs the
receiver's type, which tree-sitter does not have. The `ast` vs `ast_member` split above is the
tell: a codebase that mostly calls free functions indexes densely, and a method-heavy one thins
out sharply. Measured on a method-heavy multi-crate codebase, edge density was roughly an order of
magnitude below the 0.68 edges/function above, and **no edge crossed a crate boundary** although
both crates were indexed and one called into the other throughout.

So a workspace's crates are each indexed but not joined to each other. Treat the Rust call graph
as good within a crate and absent between them.

**Not modelled:** generic impls' type parameters; trait default method bodies inherited rather
than overridden; `compoundref`, because Rust has no class inheritance — empty by construction, not
by gap.

**Incremental refresh cannot see a newly-added cross-file call, for the same reason `xrefs` is
empty.** A refresh re-runs the changed files plus a closure of their neighbours, and one closure
pass walks doxygen's `includes` table — populated from `#include` directives, which Rust does not
have. So that pass contributes nothing here and `use` / module paths are not followed in its place.

The changed file itself is always re-indexed, so a call you *write* is picked up; what is missed is
a third, unedited file whose resolution changed as a consequence. Given that the Rust graph is
already absent across crate boundaries, this narrows the gap to within-crate cases. A full build
(`index(action='refresh', force=True)`) closes it; fixing it properly needs a tree-sitter module
graph.

## Cross-compilation

A crate that sets `[build] target` in `.cargo/config.toml` — which is every embedded Rust project
— makes cargo write to `<target-dir>/<triple>/doc/` rather than `<target-dir>/doc/`. That is
handled. What is **not** handled for you: `cargo +nightly` switches toolchain, and a target
installed for stable is not installed for nightly. If the build fails with
``can't find crate for `core` ``, run:

```
rustup target add <triple> --toolchain nightly
```

## Workspaces

Every package's lib **and** every bin target are documented. A `main.rs` is not reliably a thin
wrapper around a sibling lib of the same name, and documenting the lib instead silently dropped
every module reachable only from the bin — with no error, because `cargo metadata` succeeds
either way.

Known rough edge: a crate documented as both lib and bin can return the same shared symbol twice
from `search`.
