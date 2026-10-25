**How Python reaches the engine**

The Python package is a ctypes binding over the C ABI. It has no C++ glue and no pybind11. `python/src/entropic/_bindings.py` loads `librentropic.so` and pins each symbol's `restype` and `argtypes` through a `_bind(name, restype, *argtypes)` helper (`_bindings.py:35`). Every `entropic_*` function in `include/entropic/entropic.h` gets one such line, for example `entropic_free = _bind("entropic_free", None, ctypes.c_void_p)` (`_bindings.py:262`). The docs describe the file as regenerated from `entropic.h` by a CMake-driven script. They also describe it as a "curated" binding for the most-used symbols, so I could not confirm from the index whether every symbol is covered.

```
Python (ctypes)                C ABI (librentropic.so)            C++ engine
───────────────                ───────────────────────            ──────────
entropic_run(h, s, &out) ───▶  entropic.h, extern "C"  ───▶  Engine::run_turn()
                                 opaque handles, error codes
hook callback (CFUNCTYPE) ◀──  function pointer + ctx JSON
```

The C++ side is kept off the boundary by design. `entropic.h` contains only pure C types, the header comment says no C++ types cross it, and exceptions are caught inside the facade. `entropic_run` (`src/facade/entropic.cpp:1974`) catches `std::exception`, stores the message in `last_error`, and returns an error code.

**Memory rules that cross the boundary**

1. **Engine-allocated strings are owned by the caller and freed with `entropic_free`.** Functions returning `char*` through an out-parameter, such as `entropic_run(handle, input, char **result_json)`, transfer ownership. The doc on `entropic_run` says the caller must free `*result_json` with `entropic_free()`. Passing NULL to `entropic_free` is a no-op.

2. **Allocator matching.** `entropic_alloc` is `malloc` and `entropic_free` is `free` (`entropic.cpp:1944` and `:1954`). Memory allocated with `entropic_alloc` is the only memory the engine may free. A consumer-provided buffer that the engine will free must come from `entropic_alloc`. Python's `ctypes` buffers or `bytes` objects must not be handed over, and the engine's pointers must not go to Python's allocator.

3. **Inputs are borrowed, outputs are owned.** `i_inference_backend.h` says strings passed in (`messages_json`, `params_json`, `prompt`) are borrowed for the duration of the call. Strings returned by `generate`/`complete` are allocated by the backend, and the caller frees them through the callee's free function (`entropic_inference_free`). `i_inference_callbacks.h` states the same rule.

4. **Hook callbacks return memory the engine frees.** In `python/src/entropic/hooks.py`, `_build_trampoline` (line 140) decodes `context_json` into a dict on entry, so the engine's buffer is only read. When the hook returns a transform, `_alloc_c_string` (line 123) and the trampoline write the JSON into an `entropic_alloc` block and hand it to the engine, which frees it. The Python side must not free that pointer, and no Python reference may outlive the handover.

5. **No Python exception crosses into C.** The trampoline wraps the user callable in a `try`. On exception it prints a traceback and returns 0, which is pass-through.

**Things I noticed in the index that you should verify**

- In `_build_trampoline` the `rc = 1` line sits outside the `if ptr:` check. If `entropic_alloc` returns NULL, the trampoline still reports "transform/cancel" to the engine without setting `modified_json`. The index body shows this, but I have not confirmed how the engine treats a return of 1 with a NULL output.
- `entropic_free_string` appears in `OLD_NOTES.md` and `docs/architecture-cpp.md` but is not in the index as a symbol (`dossier` returned not found). The current name is `entropic_free`.
- Python-side handling of `result_json` after `entropic_run` (whether the wrapper frees it) is in the Python helpers. I did not read that code, so I cannot say whether the wrapper frees it or leaks it.