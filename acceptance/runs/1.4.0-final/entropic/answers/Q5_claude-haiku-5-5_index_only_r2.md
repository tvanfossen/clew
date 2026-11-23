**Short answer:** Python never links against the C++ code or uses a Python-side C++ wrapper. It calls the C ABI in `librentropic.so` directly through `ctypes`. Memory crosses that boundary under the rules in `entropic.h`: whoever allocates frees, `entropic_alloc`/`entropic_free` are the only allocator pair for buffers that cross, and borrowed `const char*` strings die on the next call.

**Call path**

```
Python (entropic package)
  _bindings.py   ctypes shims, one per ENTROPIC_EXPORT symbol
       │  _bind(name, restype, *argtypes) pins restype/argtypes
  _loader.py     finds librentropic.so (env var, ~/.entropic, then ldconfig)
       │  dlopen-style ctypes.CDLL
  hooks.py       Pythonic @hook layer on top of the raw C hook API
       ▼
librentropic.so   pure C API from include/entropic/entropic.h
       ▼
C++ engine (src/facade/entropic.cpp and below)
```

- `_bindings.py` is generated from `entropic.h` by `scripts/gen_bindings.py`, which the index describes as a full C-to-ctypes generator. The module covers about 220 symbols: functions, IntEnums, `ctypes.Structure` types and CFUNCTYPE callback typedefs.
- `__init__.py` has no `EntropicEngine` class. The package is a flat binding, and imports are lazy (PEP 562) so `install-engine` can run before the `.so` exists.
- The header's design rules say all `.so`-boundary functions are pure C with opaque handles. No C++ types or exceptions cross, and errors come back as `entropic_error_t` plus `entropic_last_error(handle)`.

**Memory rules that cross the boundary**

From `entropic.h` (`@par Memory ownership`) and the `i_inference_backend.h` header:

1. **Engine-returned `char*` transfers ownership to the caller.** Free it with `entropic_free()`. `entropic_free` is a plain `free()` on the engine side, and NULL is a no-op.
2. **Buffers the engine will free must come from `entropic_alloc()`.** That is `malloc` on the engine side. Hook `modified_json` is the main case.
3. **`const char*` returns are borrowed.** The handle owns them, and they are valid only until the next call on that handle. Copy them out immediately.
4. **Each handle is serialized.** Calls on one handle run one at a time. Different handles are independent. `entropic_destroy` is single-threaded and must not race other calls on the same handle.

**How the Python side applies those rules**

- `hooks.py::_alloc_c_string` and `_build_trampoline` allocate through `entropic_alloc`, copy UTF-8 bytes, and set `*modified_json`, so the engine's `free()` gets a pointer of the right provenance.
- The hook trampoline never lets a Python exception reach C. It prints the traceback and returns 0 (pass-through).
- **Callback lifetime:** a `CFUNCTYPE` object must stay referenced for as long as C may call it. A bare `entropic_register_hook(h, p, HOOK_CB(f), None, 0)` is a use-after-free risk, because the wrapper is dropped when the call returns. `hooks.py` keeps trampolines in a per-handle list (`_bound`). `helpers.py` documents the same pattern for the delegation and attempt-boundary callbacks, and tells the caller to hold the `CFUNCTYPE` object for the engine's lifetime.

**Gaps I could not settle from the index**

- I did not confirm the `restype` the bindings use for `char*` returns (`c_void_p` or `c_char_p`). That determines whether Python code must call `entropic_free` on them itself. The `_build_trampoline` cast to `c_char_p` suggests the bindings use `c_char_p` for hook-supplied strings only.
- In `hooks.py`, if `entropic_alloc` returns NULL the trampoline still returns 1 (transform), with no `modified_json` set. I have not checked how the engine handles that case.
- `_bound` is keyed by the handle's address, and I did not find a cleanup path for it on `entropic_destroy`. A reused address could match stale entries.