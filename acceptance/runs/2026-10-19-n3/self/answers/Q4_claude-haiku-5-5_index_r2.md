**What's in the answer**

Each row is a causal predecessor, not just a call site. From `callers` (`clew/query/symbols.py:756`), a row carries:

- `edge_class`: `call` for a direct caller, or `key` for a shared-key writer whose stored value `fn` reads. A `key` row does not call `fn` and may run on another thread. Filter on this field before reading the list as callers.
- `confidence`: `exact`, `resolved`, or weaker. A synthetic edge, such as a virtual call continued through an interface method (`_callers_of`, `dispatch_edges.py:194`), inherits the weakest link in its chain, not the strongest.
- `source`: which extraction layer produced the edge (`doxygen_sqlite` or `ast`). Layers are stored separately and the strongest is kept per caller.

The list is distinct callers. Three call sites in one function produce one row, so the row count is not a count of call sites.

**What makes the answer wrong to read as a plain list**

1. **Empty does not mean none.** `callers` on the tool's own `callers` function returned `callers: []` with `callers_unresolved: 16` and a `callers_note` saying the empty list is not a measured negative. Sixteen call sites named something this could be and did not resolve to it. The `callers_unresolved` count and `callers_note` are the fields that distinguish "nothing calls it" from "the index could not tell."
2. **Constructors are often missing.** `_empty_callers_note` (`tools_query.py:632`) documents a real case (gh#4): a class's constructor showed `callers: []` while four brace-initialised construction sites existed, none recorded as a call edge. The `also` field (for example `["variable"]` or a class) is the signal to distrust an empty list.
3. **Same-named functions.** When a name resolves to several functions, the neighbour rows are shared across all of them. You need `candidates` and `qualified` to pick one. `qualified` narrows `call` rows but not `key` rows.
4. **Receiver-dependent calls.** A member call through a pointer or reference resolves only when the declared type pins the class. Otherwise it is unresolved and counted, not listed.
5. **Indirect dispatch is extra work.** Function-pointer dispatch is resolved (`test_callers_includes_fnptr_dispatch`), but only when the layers that produce it ran. Anything outside the indexed file set (Makefiles, CI configs) is invisible.

**How to use it**

Read `edge_class`, `confidence`, and `callers_unresolved` together. If the list is empty and unresolved is non-zero, or `also` names a class, grep the name or read the body at the reported lines before concluding nothing calls it. This answer comes from the dossier output and the source comments it returned; I did not re-check the extraction code itself.