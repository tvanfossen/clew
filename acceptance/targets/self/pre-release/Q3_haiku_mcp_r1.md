# Q3 — mcp — haiku — run 1

Based on my investigation of the codebase, here is the complete analysis of the Doxyfile discovery process:

## Question 3: Doxyfile Search and Configuration

The program (doxyguard-db) looks for a **Doxyfile** — the configuration file for the external tool **Doxygen** — using a multi-location search strategy.

### Everywhere It Looks

The search occurs in a strict precedence order, defined in `discover_doxyfile` (`doxyguard_db/doxygen.py:189-234`):

1. **Repository root**: `<repo-root>/Doxyfile`
2. **Conventional docs directory**: `<repo-root>/docs/Doxyfile` (from `_DOXYFILE_DIRS` at `doxyguard_db/doxygen.py:181`)
3. **Alternative docs directory**: `<repo-root>/doc/Doxyfile` (from the same constant)

The function returns the **first** file found in this order, or `None` if none exists (`doxyguard_db/doxygen.py:231-234`).

### What It Does with Files It Finds But Does Not Use

The discovery mechanism intentionally **rejects** any Doxyfiles found outside the trusted locations. These rejected candidates are:

- Any Doxyfiles matching the pattern `*/Doxyfile` in subdirectories that are NOT `docs/` or `doc/`
- Exposed separately via `rejected_doxyfile_candidates()` (`doxyguard_db/doxygen.py:280-297`)

The rationale is explicit in the docstring (`doxyguard_db/doxygen.py:200-212`): the code previously used `sorted(repo.glob("*/Doxyfile"))[0]`, which once selected a test fixture's Doxyfile to index the entire project — "a wrong Doxyfile is worse than none, because none triggers synthesis."

When rejected candidates exist, they are **reported to the user** with their file paths and the reasoning for rejection (`doxyguard_db/doxygen.py:362-374`), allowing the user to explicitly select one via `--doxyfile <path>` if desired.

### Every Distinct Outcome and Build Continuation

The search produces **four distinct outcomes**, classified by `_doxyfile_situation()` (`doxyguard_db/doxygen.py:307-326`) and phrased by `describe_doxyfile_resolution()` (`doxyguard_db/doxygen.py:412-445`). These are mutually exclusive:

| Outcome | Occurs When | Is Fatal? | Can Build Continue? | Details |
|---------|------------|-----------|-------------------|---------|
| `DOXYFILE_EXPLICIT_MISSING` | User passed `--doxyfile <path>` but the path does not exist | YES | **NO** — exits at `doxyguard_db/cli.py:2313` | Message names the path tried; user must use `--repo-root` or correct the path. (`doxyguard_db/doxygen.py:333-341`) |
| `DOXYFILE_NO_TARGET` | Neither `--doxyfile` nor `--repo-root` flag was provided | YES | **NO** — exits at `doxyguard_db/cli.py:2313` | No directory was searched; fatal because there is nothing to index. (`doxyguard_db/doxygen.py:348-355`) |
| `DOXYFILE_ABSENT` | `--repo-root` was provided; discovery found no Doxyfile in any location; no rejected candidates exist | NO | **YES** — synthesis proceeds (`doxyguard_db/cli.py:2273`) | Supported configuration; a minimal Doxyfile is synthesized (`doxyguard_db/doxygen.py:381-389`). (`doxyguard_db/doxygen.py:448-450`) |
| `DOXYFILE_REJECTED` | `--repo-root` was provided; discovery found Doxyfiles in untrusted locations (e.g., `sample/Doxyfile`, `test/Doxyfile`) | NO | **YES** — synthesis proceeds (`doxyguard_db/cli.py:2273`) | Supported configuration; the rejected candidates are reported with reasoning, then synthesis happens. User can force a choice via `--doxyfile <path>`. (`doxyguard_db/doxygen.py:362-374`) |

The fatal situations (`EXPLICIT_MISSING` and `NO_TARGET`) are defined in `_DOXYFILE_FATAL_SITUATIONS` (`doxyguard_db/doxygen.py:402`). The two non-fatal situations (`ABSENT` and `REJECTED`) proceed to synthesize a minimal Doxyfile from the repo's declared scope or the whole repository (`doxyguard_db/doxygen.py:448-500`).

## Gaps

None. The complete flow was answered by:
- `discover_doxyfile` and `_DOXYFILE_DIRS` definitions (search locations)
- `rejected_doxyfile_candidates` implementation (what files are found but not used)
- `_doxyfile_situation`, `describe_doxyfile_resolution`, and the four situation constants (all outcomes)
- `_DOXYFILE_FATAL_SITUATIONS` and caller code paths in `_resolve_doxyfile_and_root` (continuation logic)
