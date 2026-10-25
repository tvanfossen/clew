**How Python reaches the engine**

The Python package is a thin `ctypes` binding over the C ABI, not a C++ binding and not an OOP wrapper. The README says so directly: "a thin >>ctypes<< binding over the C ABI — no OOP wrapper." The stack is:

```
Python code (entropic package)
   │  ctypes calls
   ▼
python/src/entropic/_bindings.py   auto-generated: ctypes function objects, IntEnums,
   │                               Structures, CFUNCTYPE callback typedefs
   ▼
librentropic.so  ── entropic.h (pure C facade, opaque handles)
   │
   ▼
C++ engine internals (never cross the .so boundary)
```

- `_bindings.py` is generated from `entropic.h` by `scripts/gen_bindings.py`, run through the `gen_bindings` task in `tasks.py`. A test, `tests/unit/test_bindings_abi.py`, checks the hand-curated enums against the C headers so they can't drift.
- `hooks.py`, `streams.py`, and `helpers.py` are pure-Python facades over those bindings. They are not part of the C ABI.
- The native library is fetched on demand via `install-engine`, so the Python package does not bundle it.

**Memory rules across the boundary**

The C header contract says the public API is pure C with opaque handles, and exceptions never cross the boundary (error codes instead, per the architecture rules). The memory rules I could confirm:

1. **Strings returned by the engine are caller-owned.** `entropic.h` says functions returning `char*` transfer ownership to the caller, and they must be released with `entropic_free()`. That function is documented as freeing memory "allocated by the engine or `entropic_alloc()`."
2. **Strings passed into the engine from Python are allocated with `entropic_alloc`.** `_alloc_c_string` in `hooks.py` copies a UTF-8 string into engine-allocated memory, because the engine will `free()` it after consuming it. Python must not allocate that memory with its own allocator.
3. **Backend and plugin strings follow the same pattern.** The inference backend (`i_inference_backend.h`) and MCP plugin (`i_mcp_server.h`) headers each say strings they return are allocated by the callee and freed through a matching free function (`entropic_inference_free`, `entropic_free`). Strings returned by an MCP server's `name` are server-owned and valid for the handle's lifetime. Input strings are owned by the caller.
4. **Callbacks need their Python objects kept alive.** A Python callable wrapped in a `CFUNCTYPE` trampoline must be referenced for as long as the engine can call it, or the garbage collector frees it. `hooks.py` lists this as the first of two foot-guns, and `helpers.py` holds its trampoline in a module-level `_CB` for the engine's lifetime. `_build_trampoline` in `hooks.py` builds the wrapper for each hook.
5. **Handles are opaque.** Engine handles come from `entropic_create` and are released with `entropic_destroy`. Hooks are registered with `entropic_register_hook(handle, point, callback, user_data, priority)`. A NULL handle returns `ENTROPIC_ERROR_INVALID_HANDLE`, and a NULL callback returns `ENTROPIC_ERROR_INVALID_ARGUMENT`.

**Gaps in what I could verify**

The index returns only snippets for the full "Memory ownership" sections and the second hooks foot-gun, so I could not read them in full. The rules above come from those snippets plus the function docs. Read `include/entropic/entropic.h`, `i_inference_backend.h`, and `hooks.py` directly to confirm the exact wording. I also did not find a dedicated `entropic_free_string` symbol, so the matching free function for an engine-returned `char*` is `entropic_free`.