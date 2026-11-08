**Short answer:** a clew caller list is a list of *functions that have a resolved edge into the target name*, each tagged with how it was matched. It is not a list of call sites, and several things can make it misleading.

I answered from the source (`clew/query/models.py`, `clew/query/symbols.py`, `clew/query/dossier.py`, and the tool description templates). I did not run clew against an index.

**What each neighbour row carries** (`CallEdge`)

- `name`, `rowid`: the caller's name and identity. There is no line number or call-site location on the row.
- `source`: which doxygen or AST layer found the edge. Edges are stored once per layer, and the row reports the strongest evidence.
- `confidence`: `exact`, `resolved` or `fuzzy` for call edges.
- `edge_class`: `call` for a direct call, or `key` for a shared-key dataflow edge. A `key` row is not a call at all. It means one function writes a key the other reads, with no call between them, and it may be asynchronous or cross threads.
- `implementors`: for a virtual endpoint, the bodies doxygen says override it. This is an annotation, not a synthetic edge.
- `via_macro` and `via_macro_expansion`: the call is written as a macro, so the body contains no text for that hop.

Around the rows, the reply adds:

- `ambiguous` (`NameAmbiguity`): how many same-named functions the bare name matches, and how many neighbours are shared with them.
- `callers_unresolved`: how many call sites named this function and failed to resolve. `None` means the index predates this measurement, which is not the same as 0.
- `provenance: 'ast'`: the parser recovered the symbol because doxygen never emitted it. An empty brief there means unparsed, not undocumented.
- `anchor_mismatch`: the file changed after the build, so the lines may no longer belong to that function.

**What makes it wrong to read as a list of call sites**

1. **Name-based matching, not receiver-based.** `obj.method()` is matched on the tail name `method`, and the receiver's type is never checked. Every same-named function inherits every such caller. The code's own measurement: `Get` matches 33 functions and shows 162 callers, at most one per call site being real. Check `ambiguous` before attributing any caller to a specific function.
2. **`fuzzy` is a three-value label on a number.** A 2-candidate fuzzy edge and a 33-candidate one get the same label. The candidate count is the part that tells them apart.
3. **Empty is not the same as no callers.** An empty `callers` means "nothing calls this" only when `callers_unresolved` is zero. Calls behind an unsatisfied preprocessor guard, through a function pointer, or in a file the parser could not read can all leave no row.
4. **One row per function, not per site.** Several call sites in one caller collapse into one row, and the row gives no line. You must open the caller to find where it calls.
5. **Surfaces differ.** `dossier` uses direct calls only (`include_dataflow=False`), with dataflow exposed as separate `writes`/`reads`. The standalone `callers` function merges `key` rows into the same list. Whether a list contains dataflow depends on which surface produced it. `qualified` narrows the call half but not the key half, so `key` rows can still come from every same-named function.
6. **Macro hops.** An edge can read `resolved` while the calling text never names the callee; `via_macro` is what shows the path.
7. **Snapshot.** The answer reflects the index at build time, so `anchor_mismatch` and the build's age both matter.

A correct reading is: "these functions have a resolved or fuzzy edge into this name, here is how many same-named functions share that name, and here is how many sites failed to resolve." Treat it as a candidate list to verify in the caller's body, not as a set of confirmed call sites.