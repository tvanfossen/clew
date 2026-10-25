The dossier answer for a function is a list of **caller functions**, not call sites. I ran it on two functions to see what comes back.

**What the answer contains**

For `_build_function_indexes` (`clew/call_edges.py:277`), the reply had:

- **Callers:** 10 entries, each with a name, `source`, `confidence` and `edge_class`. Examples: `_prune`, `extract_locks`, `import_ast_call_edges`, and a test function.
- **Provenance per edge:** `source` was `ast` (recovered by the parser) for most rows and `doxygen_sqlite` for `import_ast_call_edges`. `confidence` was `resolved` or `exact`.
- **Counters:** `callers_unresolved: 0`, `context_undecidable: 0`, `gates_unplaceable: 0`. These are the honest "I could not place this" counts, and they are the first thing to check when a list looks short.
- **Callees, separately:** `callees` was empty, with one `external_callees` entry (`_FuncRanges`, line 308) that did not resolve to an indexed function.
- **Body and requirements:** the verbatim body, the requirements the symbol satisfies, and its covering tests. `_definition_preferring_name_index` showed `REQ-DDB-QUERY-003` and one covering test.

**What makes it wrong to read it as a list of call sites**

1. **No line numbers on the caller side.** Each caller is a function. A caller that invokes the target three times appears once, and the reply does not say which line calls it. Only `external_callees` carries `call_lines`. To see the actual call sites you must open the caller's body.

2. **Mixed provenance.** `ast` edges are parser recoveries, and `doxygen_sqlite` edges are documented by Doxygen. An empty brief on an `ast` row means "not parsed", not "undocumented". Treat the two sources as different levels of evidence.

3. **Callers are not only direct calls.** The index also stores callback-registration edges (`import_callback_registration_edges`), shared-key edges and dominated edges. `edge_class` is the field that distinguishes them, and in these two replies every row said `call`. A function passed as a pointer and registered elsewhere shows up in the same list as a direct caller.

4. **Name-keyed resolution.** The name→rowids index is keyed on the bare name. Same-named functions in different files can collide, so a caller can be attributed to the wrong target. The code handles declaration/definition duplicates by preferring definitions, but it does not disambiguate by namespace or class. The reply has an `ambiguous` block and a `qualified` parameter for this, and you should use them when the name is common.

5. **Tests are mixed in.** The `_build_function_indexes` caller list includes a test function. Production and test callers are not separated.

6. **The list is capped, but not strictly as far as I saw.** I passed `max_neighbors=8` and got 10 callers back. Do not assume that a list shorter than the true caller count means there are no more callers; check the reply for truncation.

7. **Anchor mismatch.** Both replies carried `anchor_mismatch: true`, and the body's first line began mid-signature. The index reported `stale: false` at the same time, so the stored line numbers and the current source disagree. Verify line references in the source before relying on them.

**Bottom line:** the answer is a graded set of "functions the index believes call or reference this one, by which edge kind, with what provenance, and what it could not place". It tells you where to look. It does not give you the call sites, and it does not guarantee completeness.