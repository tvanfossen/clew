**How Python reaches the engine**

The Python package is a `ctypes` wrapper over `librentropic.so`, the shared library built from the C ABI in `include/entropic/entropic.h`. There is no C++ ABI crossing: Python loads the `.so` and calls exported C functions directly. The index describes it as "a thin pure-Python ctypes shim plus a small CLI," with no object-oriented wrapper layer.

The layers, as the index shows them:

| Layer | File | Role |
|---|---|---|
| Loader | `python/src/entropic/_loader.py` | Locates `librentropic.so` in the install tree. |
| Generated bindings | `python/src/entropic/_bindings.py` | ctypes function objects, IntEnums, Structures, and CFUNCTYPE callback typedefs for every `ENTROPIC_EXPORT` symbol. |
| Generator | `scripts/gen_bindings.py`, run via `inv gen-bindings` (`tasks.py:1002`) | Parses `entropic.h` and writes `_bindings.py`. A `--check` mode diffs against the committed file and backs a pre-commit hook. |
| Pythonic facades | `hooks.py`, `streams.py`, `mcp.py`, `helpers.py` | Hand-written wrappers that handle dict/JSON conversion and callback lifetimes. |

The C side is `entropic.h`, implemented in `src/facade/entropic.cpp`. `librentropic.so` is the facade over the engine subsystems. The bindings are kept in sync with the header, and `tests/unit/test_bindings_abi.py` checks that the Python IntEnums match the C enums in both directions.

**Memory rules that cross the boundary**

1. **Engine-allocated strings are caller-owned.** Per the `entropic.h` file docs, any function returning `char*` transfers ownership to the caller, who frees it with `entropic_free()`. `entropic_free` is a plain `free()` wrapper (`src/facade/entropic.cpp:1954`), and passing NULL is a no-op. The index does not show whether the Python wrapper frees these strings itself. I could not confirm that from the index.

2. **Memory the engine will free must come from `entropic_alloc()`.** `entropic_alloc` is a `malloc()` wrapper (`src/facade/entropic.cpp:1944`). The header says all cross-boundary allocations the engine will later free, such as hook `modified_json` output or consumer strings the engine takes ownership of, must use it. Mixing allocators (Python's allocator or a plain `malloc` in the consumer) is therefore unsafe.

3. **Callee-allocated outputs.** The interfaces `i_inference_backend.h`, `i_inference_callbacks.h`, and `i_mcp_server.h` say the same thing: strings returned by `generate`/`complete`, `list_tools`, and `execute` are allocated by the callee and must be freed with the callee's free function. The MCP interface uses `entropic_free`.

4. **Hooks write results through `entropic_alloc`.** In `_build_trampoline` (`python/src/entropic/hooks.py:140`), a dict returned by the Python callback is JSON-encoded, copied into a block from `entropic_alloc`, and stored in `*modified_json`. The engine then frees it. A `None` return maps to pass-through (0), and a non-`None` return maps to a transform or cancel (1).

5. **Callback lifetime (Python-side GC hazard).** The `hooks.py` file doc says a CFUNCTYPE-wrapped Python callable must be kept referenced for as long as the engine can call it, or the C side holds a dangling function pointer. The Pythonic facade handles this. The stream observer in `streams.py` does it explicitly: `register_token_observer` stores the CFUNCTYPE in a module-level `_observers` dict keyed by handle address (`_observers[handle_key] = cb  # keepalive`). Replacing the observer overwrites that entry.

6. **Exceptions never cross into C.** Every trampoline wraps the Python call in `try/except`, logs via `traceback.print_exc()`, and returns a pass-through code. The stream observer does the same. This follows the design rule that exceptions do not cross `.so` boundaries.

7. **Borrowed token buffers are copied.** The stream trampoline calls `ctypes.string_at(token_ptr, length)` and decodes it, so Python gets its own copy and does not hold the engine's pointer. The index does not show the engine's lifetime guarantee for that pointer. My reading is that it is valid only for the duration of the callback.

**Gaps**

- The index does not cover `_loader.py` or `_bindings.py` as symbols, so I took their roles from file-level docs only.
- I did not verify whether `_bindings.py` or `helpers.py` calls `entropic_free` on returned strings. That is the main unverified point for rule 1.