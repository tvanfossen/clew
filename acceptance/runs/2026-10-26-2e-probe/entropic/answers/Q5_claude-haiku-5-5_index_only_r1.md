**How Python reaches the engine:** through `ctypes` over the C ABI. There is no C++ binding and no OOP wrapper.

```
Python (entropic package)
  _bindings.py   ctypes shim, auto-generated from entropic.h by scripts/gen_bindings.py
  _bind(name, restype, *argtypes)  pins restype/argtypes on each symbol of the loaded .so
  hooks.py       Pythonic facade; builds HOOK_CB CFUNCTYPE trampolines
        │  ctypes calls, opaque handles, pure C types
        ▼
librentropic.so   include/entropic/entropic.h  (pure C, ENTROPIC_EXPORT)
  src/facade/entropic.cpp, entropic_hooks.cpp   → C++ engine internals
```

The header states that no C++ types cross this boundary. Callers get an opaque `entropic_handle_t` from `entropic_create`, and `entropic_destroy` tears it down. Per the project design rules, exceptions never cross the `.so` boundary; errors come back as `entropic_error_t` codes.

**Memory rules across the boundary**

| Direction | Rule | Source |
|---|---|---|
| Engine → caller (`char*` return) | Ownership transfers to the caller. Free with `entropic_free()`, which calls `free()`. NULL is a no-op. | `entropic.h` file doc; `entropic_free` in `src/facade/entropic.cpp` |
| Caller → engine (string the engine will free) | Allocate with `entropic_alloc()` (wraps `malloc`). Use this for hook `modified_json` and any string the engine takes ownership of. | `entropic_alloc` doc; `_alloc_c_string` and `_build_trampoline` in `hooks.py` |
| Inference backend → engine | Strings from `generate`/`complete` are freed with `entropic_inference_free()` (wraps `std::free`). | `src/inference/inference_c_api.cpp`; `i_inference_backend.h` |
| Token callbacks | The `token` pointer in `entropic_run_streaming`'s `on_token` is valid only for the callback. Copy it if you keep it. `on_token` must not call back into the entropic API (deadlock risk). | `entropic_run_streaming` doc |
| Python exceptions in hooks | Never escape into C. `_trampoline` catches them, prints a traceback, and returns 0 (pass-through). | `_build_trampoline` in `hooks.py` |
| Hook return values | Return `None` to pass. A non-None return is JSON-encoded into an `entropic_alloc` buffer and written to `*modified_json`, and the return code becomes 1 (cancel or transform). | `_build_trampoline` |
| Handle lifetime | `entropic_destroy` is NULL-safe and invalidates the handle. Init and destroy are single-threaded and must not race other calls on the same handle. It tears down the hook registry, which is owned by value. | `entropic_destroy` in `src/facade/entropic.cpp` |

**Lifetime of Python callables:** `hooks.py` file doc says a `CFUNCTYPE`-wrapped Python callable must be kept referenced for as long as the engine can call it, or it will be garbage-collected under C. The index truncates the second foot-gun it names, so I can't report it.

**Caveats**
- The index holds only the first few hundred characters of the `hooks.py` and `entropic.h` file-level docs. The full ownership section in `entropic.h` isn't visible here, so the table above reflects the per-symbol docs and the snippets I could retrieve. Read `include/entropic/entropic.h` (the "Memory ownership" section) and `python/src/entropic/hooks.py` (the header docstring) to confirm the full rule set.
- `entropic_alloc` and `entropic_free` both use the C library `malloc`/`free`, so mixing them is harmless today. The rule is to pair them anyway, because the convention is the contract.