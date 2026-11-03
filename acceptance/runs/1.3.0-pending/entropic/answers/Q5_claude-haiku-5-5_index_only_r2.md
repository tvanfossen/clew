## How Python reaches the engine

It is a plain `ctypes` binding over the C ABI. There is no C++ extension module and no `EntropicEngine` class; the v1.7 Python engine is gone.

```
Python (entropic package)
  _loader.load()  ->  ctypes.CDLL("librentropic.so")
  _bindings.py    ->  ctypes function objects, IntEnums, CFUNCTYPE typedefs
        |  C ABI, entropic.h (pure C, opaque handles)
        v
librentropic.so  ->  src/facade/entropic.cpp, entropic_hooks.cpp, ...
```

- **Library location:** `_loader.find()` resolves `librentropic.so`. `load()` raises `OSError` and tells the user to run `entropic install-engine` or set `$ENTROPIC_LIB`.
- **Bindings:** `python/src/entropic/_bindings.py` is generated from `entropic.h` by `scripts/gen_bindings.py` (`tasks.py gen_bindings`) and is marked "do not edit". Each symbol gets its `restype`/`argtypes` pinned by `_bind`.
- **Lazy import:** `entropic/__init__.py` uses PEP 562 `__getattr__`, so `entropic install-engine` can run before the `.so` exists.
- **Handles:** Python holds an opaque `entropic_handle_t` from `entropic_create`. Calls are `entropic_configure` (JSON string), `entropic_run*`, and `entropic_destroy`.
- **Hooks:** `hooks.py` adds a Pythonic facade over `entropic_register_hook`. It JSON-marshals the context and wraps each callable in a `HOOK_CB` CFUNCTYPE trampoline.

## Memory and error rules at the boundary

These come from the `entropic.h` header comments and the functions' dossiers.

1. **Pure C only.** No C++ types or exceptions cross the `.so` boundary. Failures come back as `entropic_error_t` codes. The detail is read with `entropic_last_error(handle)`.
2. **Exceptions stop at the boundary.** The hook trampoline wraps the user callable in `try/except Exception`, prints the traceback, and returns "pass through". Python exceptions never reach C.
3. **Ownership of returned `char*`.** The caller owns the string and must free it with `entropic_free()`. This applies to `result_json` from `entropic_run` and the other `*_json`-style returns.
4. **`const char*` returns are not owned by the caller.** `entropic_last_error` is an example. The string is owned by the handle, valid until the next call on that handle, and must not be freed.
5. **Buffers the engine will free come from the engine's allocator.** Any buffer the engine later frees must come from `entropic_alloc()`. The trampoline does this for `modified_json`: it JSON-encodes the return value into an `entropic_alloc` buffer, then writes the pointer into `*mod_out`. `entropic_alloc` and `entropic_free` are `malloc` and `free` today, but the rule is about pairing, so a Python-side or other-CRT buffer must never be handed to `entropic_free`, and engine memory must never be freed with a foreign `free`.
6. **Callback lifetime is the caller's problem, and it is the main hazard.** A `CFUNCTYPE` object must stay referenced for as long as C may call it. If it is dropped, C calls freed memory. `hooks.py` handles this with a module-level `_pending` list and a per-handle `_bound` list that keeps trampolines alive until the handle is gone. Raw `entropic_register_hook(handle, pt, HOOK_CB(f), None, 0)` without a kept reference is the documented foot-gun.
7. **Threading.** Each function documents its thread-safety class. Calls are serialized per handle, and different handles are independent. `entropic_interrupt` can be called from another thread during a run. `init` and `destroy` must not race other calls on the same handle.

## Caveats

- I answered only from dossiers. I did not read the Python `entropic_run*` wrappers, so I cannot confirm that every Python call site frees `result_json` with `entropic_free`.
- The `entropic_last_error` doc says the cache is thread-local, but the body I saw uses `s_last_error_cache`. I could not confirm from the index whether that variable is `thread_local`. Check it if you rely on the "valid until next call" contract across threads.