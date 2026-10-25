The answer is not a list of call sites. It is a list of causal predecessors, and it can be empty when a caller exists.

**What is in it.** I checked `callers` (`clew/query/symbols.py:756`) and `_empty_callers_note` (`clew/mcp_server/tools_query.py:632`). Each row carries:

- **`edge_class`**: `'call'` for a direct caller, or `'key'` for a shared-key writer whose stored values the function reads. A `'key'` row does not call the function and may run on another thread. The docstring says to check this field on every row.
- **`source`**: `doxygen_sqlite` or `ast`. Doxygen-sourced rows report `confidence: "exact"`, and AST-sourced rows report `"resolved"`.
- **`qualified`**: when a name matches several functions, the answer for one overload is only given if you pass the identity from `candidates`. Without it, the rows are not attributed to one function.

**What would make it wrong to read it as call sites:**

1. **An empty list is not a negative.** `callers` returns `callers: []`, but its `callers_unresolved` is 16 and the note says the emptiness is not a measured negative. Sixteen call sites named something this function could be and did not resolve to it. The docstring for the note says an empty list is "a green light" for changing a shared primitive, so treating it as "nothing calls this" is the dangerous mistake.
2. **Constructor and brace-initialised construction is missing.** The gh#4 comment records a case where `ProgressBar` showed no callers while four construction sites existed. None of them were call edges. The `also` field (for example `["variable"]`) flags a name that is also another kind of symbol.
3. **Member calls through pointers or references resolve only when the receiver's declared type pins the class.** Otherwise the call is missing from the list.
4. **Dataflow rows are not calls.** The `'key'` rows can be mixed into the same list, so counting rows gives the wrong number of callers.
5. **Overloads and same-named functions** are not separated unless you select one by its `qualified` identity.
6. **Shape depends on the build.** The rows are whatever the index recorded. Staleness is flagged on the reply when it applies, and a stale index can miss callers added since the last build.

So the right reading is: rows with `edge_class: 'call'` are resolved direct callers. Everything else needs checking. When `callers_unresolved` is non-zero, or the list is empty for a function that is not free and standalone, read the body or search the name before concluding anything.