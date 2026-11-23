**What the answer contains**

`callers` returns a list of `CallEdge` neighbours, one per caller *identity*, not one per call site. `CallEdge` (`clew/query/models.py:145`) carries:

- `name` and `rowid` of the caller.
- `source`: which extraction layer found it (`call_source`, e.g. AST, AST-member, fnptr, binding). Edges are stored once per layer, and the query collapses them to the strongest evidence (`clew/query/symbols.py:_direct_call_edges`).
- `confidence`: `exact`, `resolved` or `fuzzy`.
- `edge_class`: always `'call'` for this list. Shared-key dataflow edges are a separate class.
- `implementors`: for a virtual endpoint, the overrides doxygen's `reimplements` relation names. This is an annotation, not an extra edge.

`dossier` adds `callers_unresolved`, a count of call sites that named this function but produced no edge (`models.py` around line 1068). `None` means the index predates that count, so it cannot say whether anything was refused.

**What makes it wrong to read as a list of call sites**

1. **Row count is not relationship count.** Each caller appears once per identity, and the same pair can exist in several layers. `UNIQUE(caller, callee, source)` means the raw table is inflated, and the query collapses it. Counting rows, or assuming one entry per invocation, is wrong.

2. **Fuzzy edges are not filtered here.** `_direct_call_edges` deliberately keeps them. The repo's own notes say 21.3% of clew's own call edges and 79.8% of a C++ target's are fuzzy. For `obj.method()` the receiver's type is never checked, so the edge goes to every function with that name. `NameAmbiguity` (`models.py` around line 1442) gives the example that `Get` matches 33 functions and shows 162 callers, of which at most one per site is real. The entry for a function may be a namesake's caller.

3. **Empty `callers` is not "nothing calls this".** A refused site emits no edge, even when the name matches exactly one function, because the receiver may be a class the index never saw. The refusal is recorded only in `callers_unresolved`. So `callers: []` beside `callers_unresolved: 3` means the function has refused callers. `callers: []` beside `0` is a measured negative. `None` means "can't tell". The test file `tests/test_unresolved_inbound.py` specifies these cases.

4. **Calls to things outside the index leave no trace.** A call to `std::to_string` is not counted as unresolved, because there is no indexed callee to understate. The unresolved count covers only calls whose callee exists in the index.

5. **Virtual dispatch.** A caller that invokes a base-class method appears against the base endpoint. The concrete overrides are listed in `implementors`, but the list does not say which one runs.

6. **Duplicate definitions.** A decl/def pair, or same-named functions in different classes, can produce several candidates. The unresolved-count rule credits a refusal to a symbol only when it names one function, which was a fix for a measured over-attribution (87% of functions flagged).

**Bottom line:** the answer is a set of plausible callers at identity granularity, each graded by how it was found. It does not enumerate every call site, and an empty or short list does not prove absence. The `confidence`, `NameAmbiguity` and `callers_unresolved` fields are the parts to read before trusting it.

I worked from the source and the tests in this checkout (`clew/query/models.py`, `clew/query/symbols.py`, `clew/call_edges.py`, `tests/test_unresolved_inbound.py`). I did not run `clew` against an index, so the percentages come from the repo's own comments, not from a fresh measurement.