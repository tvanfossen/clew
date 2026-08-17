# Q4 — mcp — sonnet — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `mcp__doxyguard-db__search`
- **asked:** corpus, target
- **got:** {"directories":[{"directory":"library","indexed_files":174,"symbols":4690,"external_files":0,"unresolved_files":0},{"directory":"include","indexed_files":97,"symbols":4057,"external_files":0,"unresolved_files":0},{"direc…

### 2. `mcp__doxyguard-db__index`
- **asked:** action, target
- **got ⚠ error:** Error executing tool index: index(action='status') does not take a target, and '~/ddb-targets/mbedtls' was supplied. Refusing rather than ignoring it, because this action reports on the DERIVED target and on where that d…

### 3. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"indexed files","count":0,"results":[],"subject":"doxygen/*","note":"No indexed file matches 'doxygen/*'. This corpus holds INDEXED SOURCE FILES only, so a build script, a Doxyfile, a data file or anything else t…

### 4. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"indexed files","count":32,"results":[{"path":"3rdparty/Makefile.inc","symbol_count":0},{"path":"3rdparty/everest/Makefile.inc","symbol_count":0},{"path":"3rdparty/everest/README.md","symbol_count":0},{"path":"3r…

### 5. `Bash`
- **asked:** command=grep -n "^INPUT\|^FILE_PATTERNS\|^RECURSIVE" ~/ddb-targets/mbedtls/doxygen/mbedtls.doxyfile
- **got:** 9:INPUT                  = ../include input ../tests/include/alt-dummy 10:FILE_PATTERNS          = *.h 11:RECURSIVE              = YES

### 6. `Bash`
- **asked:** command=find ~/ddb-targets/mbedtls/library -type f | wc -l; find ~/ddb-targets/mbedtls/include -type f | wc -l; find ~/ddb-targets/mbedtls/3rdparty -type f | wc -l; find ~/ddb-targets/mbedtls/tests -type f | wc -l; find ~/ddb-targets/mbedtls/programs -type f | wc -l; cat ~/ddb-targets/mbedtls/3rdparty/README.md 2>/dev/null | head -30
- **got:** 177 99 38 310 123

### 7. `Bash`
- **asked:** command=grep -n -i "3rdparty\|third.party\|vendor" ~/ddb-targets/mbedtls/README.md 2>/dev/null | head -20; echo ---; ls ~/ddb-targets/mbedtls/3rdparty; echo ---; grep -n -i "everest\|p256-m" ~/ddb-targets/mbedtls/3rdparty/Makefile.inc | head -5
- **got:** 319:### Third-party code included in Mbed TLS 321:This project contains code from other projects. This code is located within the `3rdparty/` directory. The original license text is included within project subdirectories…

**Reasoning.** Now I have everything needed.

## Answer

**mbedtls's own implementation + public interface (the "library" proper):**

| Part | Indexed files | Symbols | Role |
|---|---|---|---|
| `include/` | 97 | 4,057 | Public API — headers under `include/mbedtls`, `include/psa`, `include/tls13` |
| `library/` | 174 | 4,690 | Implementation — the `.c` files behind that API |
| **Total** | **271** | **8,747** | mbedtls's own code |

That's the number I'd give someone asking "how big is mbedtls": **271 first-party source files / ~8,700 documented symbols**, split roughly evenly between public interface and i

---

## Final answer as submitted

Now I have everything needed.

## Answer

**mbedtls's own implementation + public interface (the "library" proper):**

| Part | Indexed files | Symbols | Role |
|---|---|---|---|
| `include/` | 97 | 4,057 | Public API — headers under `include/mbedtls`, `include/psa`, `include/tls13` |
| `library/` | 174 | 4,690 | Implementation — the `.c` files behind that API |
| **Total** | **271** | **8,747** | mbedtls's own code |

That's the number I'd give someone asking "how big is mbedtls": **271 first-party source files / ~8,700 documented symbols**, split roughly evenly between public interface and implementation. I'd be explicit that this counts `include/` + `library/` only, and note it's an *index* count (files this repo's grammar can parse), not a raw file census — disk has 99 files under `include/` and 177 under `library/` (grep, disk listing), a handful more than the index resolves.

**Everything else in the repo is not the library:**

- **`3rdparty/`** (32 indexed / 38 on disk, 454 symbols) — explicitly vendored, not mbedtls's own code. The project says so itself: `README.md:319-324` — "Third-party code included in Mbed TLS… located within the `3rdparty/` directory," naming Project Everest (`3rdparty/everest/`) and p256-m (`3rdparty/p256-m/p256-m/`) as imported under their own licenses.
- **`programs/`** (80 indexed, 965 symbols) — example/utility executables built on top of the library, not the library itself.
- **`tests/`** (44 indexed, 859 symbols; 310 files on disk — most are `.data`/`.function` test-generator inputs the index's grammar doesn't parse) — the test suite.
- **`configs/`** (13 files, 143 symbols), **`scripts/`** (9 files, 141 symbols), **`docs/`** (30 files, mostly prose, 12 symbols), **`ChangeLog.d/`** (1 file) — build/config/tooling and narrative docs.
- **`.` (root)** — 47 files indexed, 0 symbols, 41 unresolved — top-level build/meta files (CMakeLists, Makefile, README, etc.), not code.

**What the project's own doc build covers:** `doxygen/mbedtls.doxyfile:9-11`:
```
INPUT          = ../include input ../tests/include/alt-dummy
FILE_PATTERNS  = *.h
RECURSIVE      = YES
```
That's `*.h` only, over three roots: `include/` (the real public API), a local `doxygen/input` directory (doc-only overview pages, not indexed as source — see Gaps), and `tests/include/alt-dummy` (stub headers used to document the pluggable driver/alt-implementation interface for documentation purposes only). **It does not include `library/*.c` at all** — mbedtls's own doc build documents the public interface, not the implementation behind it, and doesn't touch `programs/`, `tests/` (proper), `3rdparty/`, or the rest.

So the honest three-part answer:
1. **The library** (what ships and what you'd call "mbedtls's size"): `include/` + `library/` — 271 indexed files, ~8,700 symbols.
2. **The doc build's scope**: a strict subset of that — just the `*.h` public headers in `include/` (plus a docs-only pages dir and a dummy-header shim for driver docs), never the `.c` implementation.
3. **The rest of the repo** (programs, tests, 3rdparty, configs, scripts, docs, root) is packaging, testing, vendored dependencies, and tooling around the library, not the library.

## Gaps

- `doxygen/input` (the second doc-build root) isn't in the index's source corpus at all — `search(corpus=files, text="doxygen/*")` returned zero rows, because it holds Doxygen overview/mainpage content the pipeline's grammar doesn't ingest as code. I couldn't verify its exact contents from the index; I'm inferring "doc-only pages" from the Doxyfile's `FILE_PATTERNS = *.h` combined with it sitting alongside the doxyfile, not from reading its files directly.
- Disk file counts (`find`) vs. indexed file counts differ (e.g. `library/`: 177 disk vs 174 indexed; `include/`: 99 vs 97) — I didn't chase down which specific files the index excludes; the gap is small and doesn't change the size claim materially.
- I did not attempt to distinguish "public API surface size" (e.g. number of exported functions) from raw symbol counts — `4,057`/`4,690` symbols include macros, structs, and internal-linkage items alongside public functions, so those aren't literally "API surface" counts, just index totals per directory.
