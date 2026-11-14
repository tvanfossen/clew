**Short answer:** `callers` returns causal neighbours with their evidence grade attached, not a verified list of call sites. Several things in it can make a row or a count misleading. I answered from reading the source (`clew/query/symbols.py`, `clew/query/models.py`, `clew/call_edges.py`, `clew/mcp_server/tools_query.py`). I did not run clew against an index.

**What the answer contains**

`callers(db, fn)` (`symbols.py:756`) returns a list of `CallEdge` rows. Each row has:

- **`edge_class`**: `'call'` for a real direct caller, or `'key'` for a function that writes a shared key which `fn` reads, with no call between them. A `'key'` row is not a caller. It may run asynchronously on another thread.
- **`source`**: which extraction layer found it. Possible values are `doxygen_sqlite`, `ast`, `ast_member`, `macro_hop`, `fnptr`, `declared_dispatch` and `binding`.
- **`confidence`**: `exact` (doxygen's inline xref), `resolved` (unique name match), or `fuzzy` (several candidates share the name).
- **`implementors`**: for a virtual endpoint, the known overrides from doxygen's `reimplements` relation. This is an annotation, not an extra edge.
- **`expansion`**: for `macro_hop` rows, the macro's initializer text, which is the only place the call appears as text.
- **Key-only fields** (`strength`, `key_name`, `dispatch_mode`, `crosses_thread`, `to_thread`), set only on `'key'` rows.

The row is one per endpoint identity, not one per layer (`CallEdge`, `models.py:145`). `source` and `confidence` describe the strongest evidence found for that endpoint.

**What makes it wrong to read as a list of call sites**

1. **It includes dataflow neighbours.** Because `callers` merges `'key'` rows with `'call'` rows, `len(callers)` is not a call count. You have to filter on `edge_class`.

2. **Fuzzy edges are not filtered here.** This surface keeps them on purpose (`_direct_call_edges`, `symbols.py:389`). The code comment measures 21.3% of clew's own call edges as fuzzy, and 79.8% on a large C++ codebase. A fuzzy `ast_member` edge matches an unqualified tail without checking the receiver's type. So every call to `obj.Get()` emits an edge to all 33 functions named `Get`. `NameAmbiguity` (`models.py:1441`) gives a worked example: one function showed 162 callers, and at most one per call site can be real.

3. **Name ambiguity is a separate question.** `name_ambiguity()` (`symbols.py:1959`) returns the number of same-named candidates and how many neighbours arrive through the shared name. It returns `None` when the name is clean. Read it alongside the list. It counts distinct signatures, not memberdef rows, so declarations and definitions don't inflate it.

4. **`qualified` changes which function you are asking about.** Without it, the focal function is chosen by the first row. The gh#26 case from the code comments: `dossier("_classify")` reported callers that belonged to other modules' `_classify`, including a fabricated self-edge. Pass the `qualified` identity from `candidates` when a name is shared.

5. **An empty list is not "no callers".** Construction through braces or a constructor is not a call edge. `_empty_callers_note` (`tools_query.py`, around line 632) flags this when the name also resolves as a class, and when the build recorded refusals against the symbol. An unmeasured count (`None`) is not a zero, and the code says so.

6. **Virtual dispatch is not pulled in.** A base method's caller list does not include callers of its overrides. Those appear only through the `implementors` annotation, and only if doxygen recorded the override.

7. **It is one hop.** `callers` is a flat neighbour list, not transitive. Multi-hop paths go through `chain_trace` or traversal, which filters `fuzzy` edges. So the two can disagree on the same function.

8. **A missing table reads as empty.** If `call_edges` does not exist, `_direct_call_edges` returns `[]` (`symbols.py:423`). That is the same result as "no callers". I did not check whether a higher layer reports the missing table separately.

**How to read it**

Treat the answer as candidate neighbours, each with a grade. Before you act on it:

- Keep only `edge_class == 'call'` rows.
- Check `confidence`, and check `name_ambiguity` when the name is shared.
- Pass `qualified` when the name is shared.
- Treat an empty list as a question, not a clearance. Look at the note and the refusal count.
- Confirm the specific call site with grep before editing.