The answer is a causal-neighbour list, not a list of call sites. Several things in it change what a row means.

**What a row contains.** Each entry carries a `name`, a `source` (`doxygen_sqlite` or `ast`), a `confidence` (for example `exact` or `resolved`), and an `edge_class`. The `edge_class` matters most:

- `call` means the neighbour calls the function.
- `key` means a shared-key writer whose values the function reads. It does not call the function and may run on another thread. `callers` mixes both, so filter on `edge_class` before treating a row as a caller.

**Why a row is not a call site.**

- **One row per caller function, not per site.** `_callers_of` selects `DISTINCT callee, caller, confidence` and keeps one entry per (callee, caller) pair. A function that calls `fn` five times appears once. Stored edges are per extraction layer, and the strongest confidence is kept.
- **Tests are callers.** The `_empty_callers_note` callers include `test_*` functions. A count of callers includes test code.
- **Dispatch is a synthetic edge.** A virtual call lands on the interface method, and `_callers_of` carries the premise's confidence forward. Function-pointer dispatch appears as a resolved edge (`test_callers_includes_fnptr_dispatch`).
- **Constructors are not calls.** Brace-initialised construction produces no call edge, so `callers: []` on a class constructor can be wrong. This was the gh#4 case, where a class was reported as having two callers when it had one. The `also` field flags this.

**Why an empty list is not a negative.** The live example is `callers`, which returned `callers: []` with `callers_unresolved: 16`. The index recorded 16 call sites that named a function it could not pin to a specific one. The reply says so in `callers_note`. The index also says a member call through a pointer or reference resolves only when the receiver's declared type pins the class. Empty means "not recorded," which is not the same as "nothing calls this."

**Same-named functions.** When a name matches several functions, the neighbour rows are shared across the candidates. Use `candidates` and `qualified` to pick one before attributing rows to it.

**Practical rule.** Treat the list as "what the index can establish causally precedes this function." Check `edge_class`, `confidence`, `callers_unresolved`, and `callers_note` before concluding anything. For a shared primitive or a change-impact question, read the body at the reported lines or `search` the name as well.

I did not check the boundary cases the MCP instructions mention, such as files outside the indexed set (Makefiles, CI configs). Those would also be invisible to this list.