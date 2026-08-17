# Q7 — mcp — sonnet — run 1

## Answer

**Function added:** `library/version.c:40-45`

```c
/**
 * \brief Acceptance-test probe.
 *
 * Used only to exercise the doxyguard-db acceptance benchmark; not part of
 * the public mbedtls API.
 *
 * \return 0 always.
 */
int mbedtls_acceptance_probe(void)
{
    return 0;
}
```

- **Signature:** `int mbedtls_acceptance_probe(void)` — `library/version.c:40`
- **File:** `library/version.c`, gated by `#if defined(MBEDTLS_VERSION_C)` (`library/version.c:10`, closing at `library/version.c:45`)
- **Doxygen brief (per the index):** empty. The dossier tool returned `"brief":"", "provenance":"ast"` — i.e. it picked the function up via the AST/tree-sitter layer, not doxygen's own XML extraction, so the `\brief Acceptance-test probe.` text I wrote is **not** reflected in the index's `brief` field even though it's present verbatim in the source at `library/version.c:34`.
- **Callers:** none. `dossier` returned `"callers":[]` — nothing in the indexed repository calls `mbedtls_acceptance_probe`.

## How I brought the index up to date

1. Edited `library/version.c` to add the function.
2. Called `mcp__doxyguard-db__index` with `action=refresh`, `target=~/ddb-targets/mbedtls`.
3. The refresh reported `ok: true`, `built: true`, `duration_ms: 7539` (**~7.5 seconds**), and post-build status `stale: false`, `build_version: 50 == expected_build_version: 50`, `source_changed_files: 0` — confirming the rebuilt index matches the current source with no outstanding drift.
4. Then queried `dossier(mbedtls_acceptance_probe, target=.../mbedtls)` for the signature/brief/callers above.

## Gaps

- The doxygen `\brief` comment I wrote does not show up in the dossier's `brief` field — the symbol was resolved via `provenance: "ast"` rather than a doxygen-XML pass, so either the refresh didn't re-run `doxygen` itself (only the tree-sitter/AST layer) or doxygen's brief-extraction didn't attach to this new symbol for some other reason. I did not dig further into the pipeline internals (e.g. rerunning doxygen directly) since that would mean bypassing the MCP tool surface, which the task restricts against.
- I did not independently grep the source for callers to cross-check the `callers:[]` result — the dossier result was taken as authoritative per the task's instruction to reach for the index first.
