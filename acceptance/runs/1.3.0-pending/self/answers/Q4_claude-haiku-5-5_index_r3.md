**What the answer contains.** For one function, `dossier` returns a `callers` list. Each row has a name, the file it sits in, a `source` (which extraction layer found it, such as `doxygen_sqlite` or `ast`), a `confidence` (`exact`, `resolved`, or weaker), and an `edge_class` (`call`, plus others). Test callers carry a `qualified` name. Alongside the list come `callers_unresolved`, the callees, the writers and readers, the requirements and covering tests, and the verbatim body.

**Why it isn't a plain list of call sites:**

1. **The name may not identify one function.** `dossier("main")` resolved to `acceptance/__main__.py:main`, but reported 25 candidates and showed only 8. Its `callers` list includes `test_guard_main.py` tests, which call `clew/guard/main.py:main`, not the function the body belongs to. The reply says neighbour rows are shared across all same-named candidates. Re-ask with `qualified=` before attributing a caller to one function.

2. **Confidence varies.** `_callers_of` shows the strongest confidence per (caller, callee) pair across layers, so a row may hide a weaker layer that also found the edge. Synthetic edges are only as strong as their premise: a virtual call's continuation through an interface method inherits the weakest link.

3. **Not all edges are direct calls.** The `callers` list includes function-pointer dispatch (`test_callers_includes_fnptr_dispatch`) and interface continuation. On a variable, the same field is "causal neighbours", meaning writers as well as callers.

4. **An empty list is not "nothing calls this".** The `_empty_callers_note` code (gh#4) exists because brace-initialised construction is not a call edge. `ProgressBar` showed `callers: []` while having one real caller. The note only fires when the name also resolves as a class, or when `callers_unresolved` is non-zero (refused callers, gh#15). A measured zero stays silent, so an empty list in an index that never measured refusals is not evidence of absence.

5. **Scope limits.** Calls from files outside the indexed set (Makefiles, CI configs), and anything the extractors don't model, are invisible. The `target` and `not_searched` fields say what was read.

**How I'd read it:** treat the list as "the edges clew extracted, at these confidences, for this identity", not as an exhaustive enumeration. Check `qualified` for ambiguous names, check `callers_unresolved` and the constructor note before concluding there are no callers, and treat `resolved` or fuzzy-premise edges as leads to verify in source.

I checked this against three functions (`main`, `_empty_callers_note`, `_callers_of`) and the index's own docstrings. I did not independently verify the extractor behaviour beyond what those docstrings and tests state.