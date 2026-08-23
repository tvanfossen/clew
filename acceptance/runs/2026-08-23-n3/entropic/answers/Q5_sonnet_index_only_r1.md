This gives a clear, well-evidenced picture. Here's the answer:

## The path from Python to the engine

There is no Cython, no pybind11, no C-extension build step involved. The bridge is:

1. **`src/facade/entropic.cpp` (+ sibling facade files like `entropic_hooks.cpp`, `entropic_identity.cpp`, `entropic_mcp.cpp`) implement a pure-C API** declared in `include/entropic/entropic.h`. Per that header's own doc: "All functions are pure C — no C++ types cross this boundary." This compiles into `librentropic.so`, with every crossing symbol tagged `ENTROPIC_EXPORT` (`__attribute__((visibility("default")))`, from `entropic_export.h`), applied *only* to factory functions, the `entropic.h` C API, and MCP plugin interface functions — everything else in the `.so` stays hidden.

2. **`python/src/entropic/_bindings.py` is auto-generated** by `scripts/gen_bindings.py`, whose `parse_functions()` walks the header for every `ENTROPIC_EXPORT` declaration and emits a matching `ctypes` function object, `IntEnum`, `ctypes.Structure`, or `CFUNCTYPE` typedef — a flat, 1:1 mechanical mirror of the C ABI, symbol names matching exactly. Python literally calls into the `.so` through `ctypes`, nothing else.

3. **A hand-written Pythonic facade sits on top** — `hooks.py`, `streams.py`, `helpers.py` — wrapping the raw `_bindings` calls to hide two documented foot-guns rather than exposing raw ctypes to consumers.

4. **Drift between the two sides is a gate, not a convention**: a pre-commit hook (`inv gen-bindings --check`) re-runs the generator and diffs against the committed `_bindings.py`; a header change without a regenerated wrapper fails the build (`tests/unit/test_gen_bindings.py` self-tests that this actually fires).

## The memory rules crossing the boundary

The index surfaces concrete, enforced rules rather than a general policy:

- **Engine-allocated memory must be freed by the engine, not by Python/libc.** `entropic_alloc` is a thin `malloc` wrapper; `entropic_free` is a thin `free` wrapper — but the contract (per `i_mcp_server.h`'s doc) is: *"Free with `entropic_free()`. Strings returned by name are server-owned (valid for handle lifetime). Input strings … "* — i.e. ownership direction is explicit per-field, and Python must call back into the C ABI's free function rather than assume its own allocator can reclaim it.

- **Struct-vs-contents ownership is split, and the split is real code, not just docs.** `entropic_free_logprob_result` frees only the `logprobs` and `tokens` arrays *inside* the struct and nulls both pointers to prevent double-free — the struct itself is caller-owned and freed separately. Any Python wrapper touching this type has to track that split explicitly.

- **Callback lifetime is the sharpest foot-gun, and it's named as such in the code.** `hooks.py`'s file doc states it directly: registering a callback via the raw `_bindings.HOOK_CB` / `entropic_register_hook` "carries two foot-guns," the first being **Lifetime**: *"a CFUNCTYPE-wrapped Python callable must be referenced [kept alive] for as long as the engine can call it."* `ctypes.CFUNCTYPE` produces a trampoline that C++ gets a raw function pointer into; if the Python-side wrapper object is garbage-collected while the engine still holds that pointer (e.g. after `entropic_register_hook`), the next dispatch calls freed memory — undefined behavior, not a Python exception. `streams.py` echoes the same concern ("wraps it so consumers don't have to manage CFUNCTYPE lifetime themselves"), and `helpers.py` shows the mitigation pattern explicitly in its docstring example: `_CB = DELEGATION_COMPLETE_CB(...)` held in a module-level/long-lived variable specifically to stop Python from collecting the trampoline out from under the engine.

I didn't find a second named foot-gun in what the index returned (the `hooks.py` doc string was truncated at "two foot-guns: 1. Lifetime… 2. …" and the index doesn't hold raw file text beyond what's captured in doc/body fields) — if that second one matters for what you're doing, it's worth opening `python/src/entropic/hooks.py` directly to read the rest of the docstring.
