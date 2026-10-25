**How Python reaches the engine**

The Python package is a thin ctypes shim over `librentropic.so`. It has no C++ glue and no CFFI layer. `python/src/entropic/_bindings.py` is auto-generated from `entropic.h` by `scripts/gen_bindings.py`. Its `_bind(name, restype, *argtypes)` helper does `getattr(_lib, name)` and pins `restype` and `argtypes` on each symbol. The library itself is located by `python/src/entropic/_loader.py`. The engine binary is fetched with `entropic install-engine`.

```
Python (ctypes)                     librentropic.so (pure C ABI)
_bindings.py  --_bind()-->  entropic_create / entropic_* symbols
hooks.py      --CFUNCTYPE-->  engine calls back into Python (HOOK_CB)
```

Hook callbacks run the other way. `hooks.py::_build_trampoline` wraps each `@hook` function in a `HOOK_CB` CFUNCTYPE. `register_hooks(handle)` passes that trampoline to `entropic_register_hook`. The trampoline keeps a reference per handle in `_bound`, so the callback lives as long as the handle does. Each call JSON-decodes `context_json`, calls the user function, and JSON-encodes any non-None return.

**Memory rules that cross the boundary**

1. **Engine → caller strings are caller-owned.** Any `char*` returned by a function that transfers ownership must be released with `entropic_free()`. The header states this in its file doc (`include/entropic/entropic.h`). `entropic_free` is `free()` in `src/facade/entropic.cpp`, and passing NULL is a no-op.

2. **Caller → engine buffers must come from `entropic_alloc()`.** Anything the engine will free itself, such as a hook's `modified_json`, must be allocated with `entropic_alloc()`. That function is `malloc()` in `src/facade/entropic.cpp`. The rule exists so both sides use the same allocator, which matters across `.so` boundaries.

3. **The Python side follows rule 2 for hook output.** `hooks.py::_alloc_c_string` copies a UTF-8 string plus a NUL into `entropic_alloc` memory. The hook trampoline does the same for the JSON payload written to `*modified_json`. Python never hands the engine a pointer into a Python-owned buffer.

4. **Callback input is engine-owned.** `ctx_ptr` is read with `ctypes.string_at` and decoded. The trampoline does not free it. The index does not state how long that pointer stays valid, so treat it as valid only for the duration of the callback.

5. **Exceptions never cross into C.** The trampoline catches `Exception`, prints the traceback, and returns 0 (pass-through). Nothing propagates into the engine.

6. **Other interface contracts follow the same pattern.** The C interface headers under `include/entropic/interfaces/` state the same rules. `i_inference_backend.h` and `i_inference_callbacks.h` say result strings are allocated by the callee and freed with the callee's free function. `i_mcp_server.h` says strings from `list_tools` and `execute` are caller-owned and freed with `entropic_free()`, and that names are server-owned for the handle's lifetime. The doc comment on `entropic_free` in `i_mcp_server.h` also covers this.

**Gaps and cautions**

- I could not confirm the Python-side free of engine-returned `char*`. The index has no `entropic_free_string`, and `OLD_NOTES.md` still mentions it. Treat that name as stale.
- `hooks.py` and `_loader.py` are indexed as files, but dossier by path returned nothing. I used their symbols instead.
- `_alloc_c_string`'s docstring says the caller must ensure "no Python reference outlives that free". The index doesn't explain this further, so I can't tell what it guards against.
- The C++ engine and its interfaces are the live implementation. The Python package is only the wrapper, and the older Python engine has been removed.