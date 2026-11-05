The answer is a name-resolved neighbour list with provenance labels, not a verified list of call sites. Each row says which layer produced it and how sure clew is, and several things can make a bare reading wrong.

I answered from the source, not from a live query; the clew MCP tools aren't loaded in this session.

**What a row contains** (`CallEdge`, `clew/query/models.py:145`)

| Field | Meaning |
|---|---|
| `name`, `rowid` | The neighbour, matched by name at the far end |
| `source` | Which extraction layer found it: `doxygen_sqlite`, `ast`, `ast_member`, `fnptr`, `binding`, `declared_dispatch`, `macro_hop`, … (`clew/vocabulary.py:182+`) |
| `confidence` | `exact`, `resolved`, or `fuzzy` (`clew/vocabulary.py:262`) |
| `edge_class` | `call` (synchronous, same thread) or `key` (shared-key dataflow, no call) |
| `implementors` | Annotation listing known overrides of a virtual endpoint; not an edge |

`dossier` adds the focal function's identity, body excerpt, locks held, thread, requirements, termini, and `external_callees`. The last one is the list of names it calls that the index has no function for, such as `pthread_mutex_lock`. Those are deliberately not edges.

**What makes it wrong as a list of call sites**

1. **Fuzzy edges are included.** `callers`/`callees` do not filter them (`symbols.py:399`). A method call whose receiver can't be typed becomes a name match: a function of that name exists, but the specific one is unconfirmed. The repo notes 21.3% of clew's own edges are fuzzy, and 79.8% on a C++ target. Traversals like `chain_trace` do filter fuzzy edges; the flat list does not.

2. **`callers` mixes in non-calls.** `edge_class='key'` rows are writers of a shared key that the function reads. They don't call it and may run on another thread. A caller list read as "things that call this" is wrong for those rows.

3. **The far endpoint is matched by name.** `dossier` picks the focal function by identity, but the neighbours are not. Same-named file-private helpers in different modules merge into one node, and their edges combine with full confidence (`CPP_INTEGRATION.md`, "Overloads").

4. **Edges are missing, not just uncertain.**
   - JavaScript and TypeScript don't follow imports, and untyped `obj.m()` calls are fuzzy.
   - Rust has no cross-crate edges; every Rust edge comes from tree-sitter alone and method calls are thin.
   - On Python and Rust, a newly added cross-file call doesn't appear until a full rebuild.
   - Calls through function pointers and callbacks come from a separate layer, and an externally registered callback ends at a terminus.

5. **Empty does not mean no callers.** Python `console_scripts` entry points and `__main__` guards are the only reachability seeds for Python. A library called only from outside the repo shows no callers. A Rust empty list is weak evidence for the same reason.

6. **One row per endpoint.** Two layers finding the same edge produce one row, reporting the strongest `source` and `confidence`. The row doesn't say the other layer disagreed.

**Practical reading:** treat `callers` as "name-level candidates, with confidence labels, plus shared-key writers." Filter to `edge_class='call'` and `confidence != 'fuzzy'` for a conservative set. For a real call-site list, `source` the lines the dossier names and confirm them.