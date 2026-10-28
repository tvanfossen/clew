Python reaches the engine through `ctypes`, calling the C ABI in `librentropic.so` directly. There is no C++ extension module and no pybind layer. The memory rules are the C API's ownership contract, plus extra rules the Python hook layer has to follow.

**How the call path works**

```
Python (entropic package)
  _bindings.py   ctypes function objects, one per entropic_* symbol
       │  loaded via _loader.py (search order ends in ~/.entropic/lib, then ctypes.util.find_library)
       ▼
librentropic.so   C ABI (entropic.h, pure C, opaque handles)
       │  facade catches C++ exceptions at the edge, returns entropic_error_t
       ▼
C++ engine (AgentEngine, inference, MCP, storage)
```

- `python/src/entropic/_bindings.py` is generated from `entropic.h`. The index says it covers every exported symbol, and that `scripts/gen_bindings.py` produces it. The `python/CMakeLists.txt` header says the bindings are regenerated at release time through `inv gen-bindings` and checked into the wheel. That file is a placeholder, and its comment points to a legacy `.claude/proposals/` path.
- The Python side is a thin wrapper. The README says `entropic install-engine` downloads the matching `librentropic.so` from GitHub Releases.
- Handles are opaque. The lifecycle is `entropic_create` → `entropic_configure` → `entropic_run` → `entropic_destroy`. `entropic_destroy(NULL)` is a no-op, and the handle is invalid after destroy.

**Memory rules across the boundary**

1. **Strings returned as `char*` belong to the caller.** Free them with `entropic_free()`. For example, `entropic_run` returns `result_json` that the caller must free. `entropic_free` is a thin wrapper over `free()` (`src/facade/entropic.cpp:1954`).
2. **Strings returned as `const char*` belong to the handle.** They stay valid until the next call on that handle. Do not free them.
3. **Buffers the engine will free must come from `entropic_alloc()`.** `entropic_alloc` is a wrapper over `malloc()`. The hook `modified_json` is the main case. Memory from a Python allocator or a `ctypes` buffer must never reach the engine's `free()`.
4. **Exceptions never cross the `.so` boundary.** Errors come back as `entropic_error_t` codes, with detail in `entropic_last_error(handle)`. The header and `docs/architecture-cpp.md` both state this. `OLD_NOTES.md` records an older `entropic_configure_dir` exception that escaped the boundary, so the rule has been broken before.
5. **Thread safety is per-function.** Calls are either thread-safe, serialized per handle, or single-threaded for init and destroy. Destroy must not race any other call on the same handle.

**Rules on the Python side (hooks)**

- **Callback lifetime.** A `CFUNCTYPE` wrapper must stay referenced for as long as the engine may call it. If it is dropped, C later calls freed memory. `hooks.py` keeps a per-handle list in `_bound` so trampolines survive as long as the handle does. A bare `entropic_register_hook(handle, point, HOOK_CB(f), None, 0)` is the unsafe pattern the module exists to avoid.
- **Marshalling.** The trampoline decodes `context_json` into a dict. For a non-None return, it encodes JSON and writes it with `entropic_alloc()` into `*modified_json`, so the engine can `free()` it. `_alloc_c_string` in the same module does this.
- **No Python exception escapes into C.** The trampoline catches everything, prints the traceback, and returns pass-through (rc 0). This keeps the engine running, but a buggy hook fails silently from the engine's point of view. A hook that raises behaves as if it returned None.

**Open points**

- I did not read the memory-ownership sections of `i_inference_backend.h` and `i_mcp_server.h`. Both declare their own ownership rules for strings crossing plugin and backend boundaries, and I have not verified them.
- `entropic_run` can return an error code with a non-NULL `result_json` holding partial context. The doc says the caller must still free it. Check for a non-NULL pointer on the error path too, not only on `ENTROPIC_OK`.