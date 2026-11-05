The answer is a list of **name-level edges with provenance**, not a verified list of call sites. Here is `_ast_harvest_calls` (`clew/call_edges.py:1140`) as an example.

**What the answer contains**

- **Callers**, each with `name`, `file`, `edge_class` (`call`), `source` and `confidence`. Here the sources are `ast` (tree-sitter) and `doxygen_sqlite`, and confidence is `resolved` or `exact`.
- **Callees**, same shape, which is what this function calls and where that call was resolved.
- **`external_callees`**, calls the index could not map to an indexed function. Here it is `harvest_js_calls` at line 1173, listed with its call lines. That field is how unresolved calls stay visible instead of disappearing.
- **Counts**: `callers_unresolved: 0`, `context_undecidable: 0`, `gates_unplaceable: 0`. These are measurements, so zero means the index checked and found none.
- **Verbatim body**, which is repository text, not instructions.

**Why it is not a plain list of call sites**

1. **It matches names.** The harvester records the callee identifier from syntax (`call_expression`, `field_expression`, etc.). A bare name can match several functions. The `qualified` field and the `ambiguous` block exist for this. Without them, a same-named function in another namespace gets attributed to the wrong target. The code keeps qualifiers (#75) so `Ns::Class::method()` can be told apart from other `method`s.

2. **Callers mix production and tests.** Thirteen of the fourteen callers listed here are tests. A caller list shows what references the function, not what runs in production. Filter by file before reading it as "who uses this".

3. **Some calls are not edges at all.**
   - Callbacks and function pointers come from a separate layer (`callback_edges.py`), so passing a function as an argument is not a call here.
   - The harvester only records a call when the callee has a static name. The test `test_callee_without_a_static_name_is_still_refused` shows that such calls are dropped by design.
   - Constructing an unindexed template resolves to nothing (`test_constructing_an_unindexed_template_still_resolves_to_nothing`).
   - Virtual dispatch shows the static name at the call site, not the override that actually runs. The `overrides` and `overridden_by` fields are the place to look for that; both are empty for this function.

4. **Coverage depends on the language path.** C, C++ and Rust use this walker. Python and JS/TS are dispatched to `pyast` and `jsast`. A missing or partial harvester gives an absent or short list. The docstring warns that the JS member-call path was once silently dropped. Zero edges could mean "none" or "not harvested".

5. **The `source` tag matters.** `ast` and `doxygen_sqlite` edges come from different extractors, and `confidence` marks how sure the resolution is. Read `exact` and `resolved` as different levels of certainty, not as the same fact.

6. **The result is cached.** The harvest is rowid-free and keyed to the file's content sha, then re-resolved on each build. Stale caches are reported through `staleness`, so check that field before trusting a list from an older build.

**Bottom line:** read the callers as "these references resolved to this name, from these sources, at these confidence levels, with these gaps listed", not as "these are every call site". The unresolved fields and counts are part of the answer, and an empty list only means something when the layer that would have produced it ran.