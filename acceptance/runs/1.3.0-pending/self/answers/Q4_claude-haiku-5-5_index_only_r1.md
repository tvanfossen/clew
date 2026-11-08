The answer is a list of **edges into the function, not a list of verified call sites**. I checked this against `main` (the query had no `qualified` name, so it resolved to one of several `main` functions). I did not open any source; everything here comes from the index.

**What each entry carries**

- `name`, `file`, and `qualified` (for test methods) identify the caller.
- `source` says which layer found the edge: `doxygen_sqlite` or `ast`.
- `confidence` is `exact` or `resolved`.
- `edge_class` is `call` in every row I saw. The `callers` query in `clew/query/symbols.py` is documented as returning "its callers plus the writers it reads from", so other edge classes can appear. Check `edge_class` before reading a row as a call.

The index also has a count that matters for absence: `callers_unresolved`. It counts call sites that named a function this could be but did not resolve (gh#15). An empty `callers` list therefore means either "nothing calls it" or "callers existed and failed to resolve". `_empty_callers_note` and the test `test_an_empty_callers_list_reports_what_was_refused` exist to keep those apart. For `main` it was 0.

**What makes it wrong to read as a list of call sites**

1. **Name collisions.** `main` resolved to `acceptance/__main__.py`, but the returned candidates list 25 identities and only 8 were shown. The callers included `test_guard_main.TestMain.*`, which exercise `clew/guard/main.py`'s `main`, not the function I queried. The neighbour rows appear to be shared across same-named functions. The reply's `ambiguous` block, which would flag this, was absent. Re-ask with `qualified=` before attributing any row to one function.
2. **Tests are callers.** Most `main` callers are test functions. A caller count is not a count of production call sites.
3. **Dispatch is not a call.** Some rows are function-pointer dispatch edges, and the index has a test for them (`test_callers_includes_fnptr_dispatch`). A caller reached through a function pointer is listed with the same shape as a direct call.
4. **Depth 1 is direct only.** Anything transitive needs `depth` ≥ 2 with `direction='back'`.
5. **Caps.** I passed `max_neighbors=5` and still got 30 callers and 50 callees. Either the cap does not apply to this path or the lists are a union across identities. I did not resolve which, so treat the list as unbounded and verify the count before quoting it.

**Practical reading:** use `callers` to find candidate upstream edges. Check `qualified` and `file` to confirm which function each edge reaches, check `edge_class` to separate calls from dispatch and dataflow, check `callers_unresolved` before reading an empty list as absence, and read the source for anything you will act on.