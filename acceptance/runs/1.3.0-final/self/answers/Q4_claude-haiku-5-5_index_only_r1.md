**Short answer:** the caller list is a graph of symbol-level edges, each carrying a confidence and a source. It is not a list of call sites, and an empty or short list does not prove nothing calls the function.

I checked this with two `dossier` calls, on `dossier` and `_budgeted_dossier` in this repo.

**What an entry contains**

Each caller or callee is a symbol, not a line. From the `_budgeted_dossier` reply, an entry carries:
- `name` and `qualified` name
- `file`
- `edge_class`, here `call`
- `confidence`, here `exact`
- `source`, here `doxygen_sqlite`

The same reply also carries the function's other panels: `writes`, `reads`, `overrides`, `overridden_by`, `threads`, `requirements`, `covering_tests`, `liveness` and the verbatim `body`. Those are separate facts about the function, not part of its call list.

**What makes it wrong to read as call sites**

1. **No line numbers.** A caller says "`dossier` calls it", not "line 2140 calls it". Several calls from one function collapse into one edge. The output I received has no per-call line field.
2. **Empty does not mean unused.** `dossier` came back with `callers: []` because its name also resolves to a class, so it is probably a constructor. The reply warns that brace-initialised construction is not modelled as a call edge. The same applies to calls through function pointers. The `dossier` docstring cites `mbedtls_mutex_lock`, which is a function pointer, so `dossier` on it misses its real call paths.
3. **Ambiguous names share neighbours.** When a name matches several signatures, the neighbour lists are shared across all of them. You have to re-ask with `qualified` before attributing a caller to one overload.
4. **Lists are capped and trimmed.** `max_neighbors` limits each list. Oversized replies are trimmed by `_budgeted_dossier`, which says so in a `_limited` block. The `dossier` docstring cites a 125,559-byte reply for a symbol with 331 callers. Check `_limited` and `total_available` before counting.
5. **Unresolved calls are absent from `callees`.** Calls that do not resolve to an indexed function are counted separately (`callers_unresolved`, `external_callees`). They are not listed as callees.
6. **Freshness is per reply.** The `dossier` reply carried `anchor_mismatch: true`, meaning the file changed since the index was built and the body's line range may not be the function's. The edges come from the index, so they can lag the working tree too.
7. **Edge classes differ.** Callers are not only `call` edges. Shared-key dataflow also appears, and `edge_class` tells them apart. Check it before reading a caller as a caller.

**What to take from it:** use the caller list to find who is connected to a function, and read `confidence`, `source` and `edge_class` on each entry. Use an empty list as "no edge was recorded", not "no caller exists". Before concluding there are no users, search the name and check `candidates` and `callers_note`.