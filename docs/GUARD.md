# The doxygen gate (`clew guard`)

`clew guard` is the pre-commit gate formerly published as
[doxygen-guard](https://github.com/tvanfossen/doxygen-guard), absorbed into clew at its 1.4.2
release. It **enforces** doxygen documentation and reports the **change impact** of a commit.
It is optional: nothing in the index pipeline runs it, and a repo that does not declare the
hook is unaffected.

What did not change: the config schema, the tag vocabulary, the pre-commit hook id
(`doxygen-guard`), and every subcommand. What changed: the command is `clew guard` (console
script `clew-guard`), the package is `clew.guard`, Rust is supported on request — see
[Rust](#rust) — and **the config is the `guard:` section of the repo's `.clew.yaml`**, the
same file that carries clew's index declarations. `.doxygen-guard.yaml` is no longer read;
see [Migrating from doxygen-guard](#migrating-from-doxygen-guard).

## Why it lives here

clew already read every target's guard config — for the `@req` id pattern and the
requirements catalog — and it imported doxygen-guard to do it. The target's gate and clew's
index were therefore parsing one file with two independently pinned releases, and clew
carried a version-skew salvage layer to survive the disagreements. With the gate inside clew
and its config inside `.clew.yaml`, the gate and the index read one section with one schema,
from one release. They read it at different severities: the gate refuses an invalid `guard:`
section, while the index warns and runs on its defaults rather than failing a build.

## Quick start

### 1. Add the hook

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/tvanfossen/clew
    rev: <clew release tag>
    hooks:
      - id: doxygen-guard
        types_or: [c, c++, python]   # add rust / javascript / ts once declared — see below
```

Installing the hook installs clew; there is no lighter gate-only distribution.

### 2. Add a `guard:` section to `.clew.yaml`

```yaml
# .clew.yaml
guard:
  output_dir: docs/generated/

  validate:
    exclude:
      - "^tests/"
      - "^\\.venv/"
    tags:
      req:
        pattern: "^REQ-[A-Z]+-[0-9]{3}$"

  impact:
    requirements:
      file: docs/requirements.yaml
      format: yaml
```

The gate reads `.clew.yaml` from the directory it runs in (the repo root, under pre-commit);
`args: [--config, path/to/file.yaml]` points it at another file of the same shape. A file with
no `guard:` section, or no file at all, runs the gate on its built-in defaults. Everything
outside `guard:` is clew's index declaration (`index_scope:`, `locks:`, …), which the gate
never reads.

### 3. Document your functions

```c
/**
 * @brief Read temperature from sensor hardware.
 * @version 1.0
 * @req REQ-SENSE-001
 * @return Raw ADC value
 */
int Sensor_ReadTemperature(void) {
    return hw_read_adc(TEMP_CHANNEL);
}
```

`pre-commit run --all-files` prints violations to stderr and writes the impact report to
`<output_dir>/impact/`.

## Migrating from doxygen-guard

1. Change the hook's `repo:` and `rev:` lines to point here. The hook id stays `doxygen-guard`.
2. Move the contents of `.doxygen-guard.yaml` under a `guard:` key in `.clew.yaml`, indented
   one level, and delete `.doxygen-guard.yaml`. clew does not read it.
3. If the old file carried an `x-clew:` section, move its sections to the top level of
   `.clew.yaml` (beside `guard:`, not inside it). The `x-` passthrough is gone.
4. If the hook passed `--config conf/doxygen-guard.yaml`, drop the argument (the gate reads
   `.clew.yaml` at the root) or point it at the moved file.

## What it checks

Every function in a staged file is checked for:

- **Presence**: `@brief`, the revision tag (`@version`), and `@return` on non-void functions.
- **Version staleness**: when the function body changed against git `HEAD`, the revision tag
  must have been incremented.
- **Tag syntax**: tag values match the configured patterns.
- **Requirement coverage**: `@req`, or an exemption tag.

| Exemption tag | Effect |
|---|---|
| `@dg_internal` | Exempt from `@req`; left out of the coverage report's unmapped list |
| `@utility` | Exempt from `@req` |
| `@callback` | Exempt from `@req` |

These are tool vocabulary, not doxygen commands; `clew guard doxyfile` emits the `ALIASES`
that keep doxygen quiet about them. `@internal` is recognised but grants no exemption (it
hides the rest of the block from doxygen when `INTERNAL_DOCS` is off).

**Change impact.** The `impact` subcommand, and the pre-commit run when a catalog is declared,
cross-reference the diff with parsed functions and report which requirements the change
touches, as markdown and JSON under `<output_dir>/impact/`.

**Requirement coverage.** `clew guard coverage` reports covered, uncovered and orphan
requirements, plus documented functions carrying no `@req`. Exit code 1 when gaps exist.

## Languages

| Language | Extensions | Block | Gated |
|---|---|---|---|
| C | `.c`, `.h` | `/** ... */` | by default |
| C++ | `.cpp`, `.cc`, `.cxx`, `.hpp`, `.hxx` | `/** ... */` | by default |
| Python | `.py` | the docstring (PEP 257), **or** a `##` block above the `def` | by default |
| Rust | `.rs` | `///` lines or one `/** ... */`, above the item | when declared |
| JavaScript | `.js`, `.mjs`, `.cjs`, `.jsx` | JSDoc `/** ... */` above the function | when declared |
| TypeScript | `.ts`, `.tsx` | JSDoc `/** ... */` above the function | when declared |

Which extension is which language comes from
[lang-parsing-substrate](https://github.com/brandon-arrendondo/lang_parsing_substrate)'s
registry, shared with knots, moldy and aurora-lint. A `.h` that contains C++ constructs is
parsed as C++. A language's `extensions:` list in the config decides which files are checked.

### Python

PEP 257 leads. A function's docstring is its documentation, with or without tags. Its
summary line (the first line, up to a blank line) stands in for `@brief`, and the tags the
gate needs go inside it:

```python
def apply_patch(repo_path: str, patch: str) -> int:
    """Apply a unified-diff patch to a project directory.

    @version 1
    @req REQ-PATCH-001
    @return 0 on success, non-zero on failure.
    """
```

A doxygen `##` block above the `def` is accepted too, and takes precedence when both exist,
so a codebase already documented for doxygen keeps working unchanged. An empty docstring is
not a block.

> **Changed from doxygen-guard:** a docstring with no `@brief`/`@version` used to be ignored,
> so an idiomatic docstring reported "no doxygen comment". It now counts as the block, and
> only the missing tag (usually `@version`) is reported.

doxygen itself renders a docstring as preformatted text. clew's index reads the summary line
and `@version` out of it where doxygen left the function undocumented (see
[Python integration](languages/PYTHON_INTEGRATION.md)). If you also generate docs with
doxygen, prefer the `##` form or open the docstring with `"""!`.

### JavaScript and TypeScript

JSDoc, opt-in like Rust (`validate.languages.javascript: {}` / `typescript: {}`):

```ts
/**
 * Trim and normalise a label.
 * @version 2
 * @req REQ-UI-004
 */
export const cleanLabel = (s: string): string => s.trim();
```

- A function is a function declaration, a method, or a name bound to an arrow function or
  function expression (`const f = () => ...`, a class field `f = () => ...`). Anonymous
  callbacks are not gated; neither are bodiless TypeScript signatures.
- The JSDoc block sits above the function, or above the `export` / `const` around it.
- Its summary stands in for `@brief`, as for Rust.
- `@return` (or `@returns`) is not required unless the language entry sets
  `require_return: true`, and then only where a TypeScript return annotation says the
  function returns a value: not `void`, `never`, `undefined` or `Promise` of those. Plain
  JavaScript has no annotation, so it never requires one.
- `.tsx` is parsed with the JSX-aware grammar and governed by the `typescript` entry.

### Rust

doxygen has no Rust parser, so this is the gate applying its policy to **rustdoc** comments.
rustdoc has no tag vocabulary of its own: a doc comment is markdown, and only its first
paragraph has a defined meaning (the summary). The convention is therefore the same tags, in
`///` lines, with three adjustments for how rustdoc is written:

```rust
/// Read the raw temperature.
///
/// Longer markdown prose, examples, `# Panics` sections — none of it is parsed.
///
/// @version 2
/// @req REQ-SENSE-001
#[inline]
pub fn read_temperature(channel: u8) -> u16 {
    u16::from(channel) * 2
}
```

1. **The summary paragraph is the brief.** Without an explicit `@brief`, the first paragraph
   counts as the brief. This is rustdoc's rule, and doxygen's `JAVADOC_AUTOBRIEF`. An explicit
   `@brief` wins.
2. **`@return` is not required.** rustdoc has no return tag and documents the result in prose.
   Set `require_return: true` on the `rust` entry to require it anyway. A function with no
   `->` or `-> ()` counts as void either way.
3. **Test code is not gated.** Functions marked `#[test]`, `#[tokio::test]`, `#[rstest]` or
   `#[bench]`, and the `#[cfg(test)]` module, are skipped. Inline unit tests are idiomatic, so
   a path exclude cannot separate them from the code they test.

The block is the **outer** doc comment: `///` lines (not `////`, which rustdoc treats as a
plain comment) or one `/** */` block. It is found across any `#[...]` attributes between it
and the `fn`, and a blank line inside a run of `///` lines ends the block. Inner doc comments
(`//!`, `/*!`) document the module. They never document a function, and they are what
`require_file_doxygen` looks for in a `.rs` file, where `@file` is not required. A trait
method with no body is a declaration and is skipped, as a C prototype is. Methods are
identified by their `impl` type (`impl<T> Trait for Foo<T>` → `Foo`), so two `new`s in two
impls do not share a revision history.

Rust is **opt-in**:

```yaml
guard:
  validate:
    languages:
      rust: {}            # completed from the built-in defaults
```

and add `rust` to the hook's `types_or`. Undeclared, `.rs` files are skipped. That way a repo
that adopted the gate for its C does not start failing on its Rust the first time it bumps
`rev:`. The defaults a declaration is completed from are published by
`clew guard config --schema` under `opt_in_language_defaults`.

What this does not do: check that the tags are meaningful to rustdoc (to rustdoc, `@version 2`
is literal text), parse markdown sections such as `# Errors`, check `macro_rules!` macros or
closures, or require docs on structs, enums and traits (the gate checks functions in every
language).

## Files the gate skips

- **Binary files**, whatever their extension: a zip or object file named `.c` is never
  parsed. Detection is lang-parsing-substrate's `classify_file` (magic numbers and byte
  statistics from the first 8 KiB).
- **The repository's shared toolchain config**, the files knots, moldy and aurora-lint
  also read (lang-parsing-substrate's `docs/unified-config-spec.md`), at the repo root:

  ```toml
  # toolchain.toml
  [ignore]
  paths = ["vendor/**", "third_party/**"]   # every tool, including clew's index
  [clew.ignore]
  paths = ["legacy/**"]                     # clew's gate only

  # suppress.toml
  [[suppress]]
  name = "generated"
  tool = "*"                                # every tool ("clew" = the gate only)
  file_glob = "gen/**"
  ```

  An entry that names a `rule` suppresses that rule only and excludes no file. These apply
  after `validate.exclude`, and `clew guard files` reports them (`toolchain_config`,
  `toolchain_ignores`).

## Configuration reference

Every key below lives under the `guard:` section of `.clew.yaml`.

### `validate`

| Key | Type | Default | Description |
|---|---|---|---|
| `languages` | dict | C, C++, Python | Per-language extensions, comment styles and excludes; `rust`, `javascript`, `typescript` on request |
| `languages.<lang>.require_return` | bool | — | Overrides `presence.require_return` for one language (`false` for Rust, JavaScript, TypeScript) |
| `presence.require_doxygen` | bool | `true` | Require a block on every function |
| `presence.require_return` | bool | `true` | Require `@return` on non-void functions |
| `presence.require_file_doxygen` | bool | `false` | Require a file-level block |
| `version.tag` | string | `@version` | Tag used as the per-function revision counter |
| `version.require_present` | bool | `true` | Require the revision tag |
| `version.require_increment_on_change` | bool | `true` | Require a bump when the body changes |
| `exclude` | list | `[]` | Regexes for files to skip (`clew guard files` shows the result) |
| `duplicate_tags_error` | bool | `true` | Flag a repeated `@brief`/`@version`/`@return`/`@file` |
| `tags.req.cross_reference` | bool | `true` | `@req` ids must exist in the catalog |
| `version_gate.current_version` | string | — | `auto:git`, `auto:cmake`, or an explicit version |
| `version_gate.version_field` | string | — | Catalog field holding a requirement's minimum version |

`version.tag` exists because the gate treats the tag as a **revision counter**, where doxygen
documents `\version` as prose. A project using `\version` idiomatically can point the gate at
another tag and alias it: `version: {tag: "@revision"}` plus `extra_tags: ["revision"]`.

### `impact`

| Key | Type | Default | Description |
|---|---|---|---|
| `requirements.file` | string | — | Path to the requirements catalog |
| `requirements.format` | string | `yaml` | `yaml`, `csv` or `json` |
| `requirements.id_column` | string | `Req ID` | Id column (`csv`/`json` only) |
| `requirements.name_column` | string | `name` | Name column or field |

The preferred catalog is a mapping keyed by id:

```yaml
requirements:
  REQ-VAL-001:
    name: Doxygen presence check      # required
    subsystem: Validate               # optional
    min_version: v0.1.0               # optional
    description: >-                   # optional
      Every function must have a doxygen comment
    acceptance_criteria: >-           # optional
      Undocumented functions produce presence violations
```

A missing file, an unknown format, a wrong shape, a missing `name`, or an id failing
`validate.tags.req.pattern` raises `RequirementsError`. The run fails rather than continuing
with an empty catalog.

### Validation of the config itself

Unknown keys inside `guard:` are rejected, with a suggestion when one is close. There is no
`x-` passthrough: the rest of `.clew.yaml` is where anything that is not the gate's belongs.

### Escaping `@`

As in doxygen, `@word` is a command anywhere in a block, including mid-sentence. To mention a
tag in prose, write `\@req` or `@@req`.

## Using doxygen alongside the gate

```bash
clew guard doxyfile > doxygen-guard.doxyfile   # then: @INCLUDE = doxygen-guard.doxyfile
```

The fragment declares the gate's tags as `ALIASES` (`@req` becomes a cross-referenced
"Requirement Index") and enables `WARN_IF_DOC_ERROR`. **Division of authority:** doxygen
decides whether a comment is valid doxygen. The gate decides whether it satisfies your
policy: catalog membership, revision increments against `git diff`, per-file scoping.

## Consumer contract

```bash
clew guard config --schema       # schema, defaults, opt-in language defaults, contract_version
clew guard config --effective    # the merged config in force and what it resolved to
clew guard files src/            # the exact post-exclude file set the gate walks
```

All three emit JSON carrying `contract_version`: 3 added `opt_in_language_defaults`, 4
added the toolchain fields to `files`, and 5 moved the config into `.clew.yaml` (`config_file`,
`config_section`) and dropped the `x-` passthrough fields. Typed errors are importable from `clew.guard.errors`:
`GuardError`, with `ConfigError` and `RequirementsError`.

## CLI

```bash
clew guard [--config path] [files...]      # pre-commit mode (what the hook runs)
clew guard validate --no-git src/*.c
clew guard impact --staged src/*.c
clew guard coverage src/
clew guard config --schema | --effective
clew guard files src/
clew guard doxyfile
clew guard -v coverage src/                # log which config sections were declared vs defaulted
```

`clew-guard` is the same entry point as a console script.

## Adopting on an existing codebase

1. Start with presence and revision only. Add `@brief` and `@version` as you touch functions,
   and use `version_gate` to require `@req` only on requirements from a given version on.
2. Turn off `presence.require_return` during migration if needed.
3. Exclude what you are not ready to cover (`validate.exclude: ["^vendor/", "^legacy/"]`).

## Requirement ids in clew's own catalog

The gate's requirements are clew's `REQ-DDB-GUARD-001`–`025` in `requirements.yaml`. 001–023
are renumbered from doxygen-guard's catalog, and each entry keeps its old id as
`x-upstream-id`. 024 is the Rust support and 025 JavaScript/TypeScript. The shared toolchain
config is `REQ-DDB-CONFIG-009` and binary skipping `REQ-DDB-PIPE-011`, because the index
honours them too.
