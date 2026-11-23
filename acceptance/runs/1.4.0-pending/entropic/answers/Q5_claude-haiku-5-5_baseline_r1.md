## How Python reaches the engine

There is no C++ extension module. The Python package talks to the engine through `ctypes` over the public C API.

```
Python (python/src/entropic/)
  _loader.py        find + ctypes.CDLL(librentropic.so)
  _bindings.py      generated: every C symbol pinned with restype/argtypes
  hooks.py, streams.py, mcp.py, helpers.py   thin Pythonic wrappers
        │  ctypes calls + CFUNCTYPE trampolines
        ▼
librentropic.so  ── extern "C", ENTROPIC_EXPORT ──  include/entropic/entropic.h
        │  (C++ internally; exceptions caught at the .so edge)
        ▼
  engine (C++)
```

- **Library discovery** (`_loader.py`): `$ENTROPIC_LIB`, then `$ENTROPIC_HOME` paths, then `~/.entropic/...`, then `ctypes.util.find_library("rentropic")`.
- **Bindings** (`_bindings.py`): generated from `entropic.h` by `scripts/gen_bindings.py` (`inv gen-bindings`, with `--check` for drift). Each function goes through `_bind(name, restype, *argtypes)`. Exports are listed in `_bindings_manifest.py` and loaded lazily (PEP 562), so `import entropic` works before the `.so` exists.
- **Boundary rule**: C types only (`const char*`, `size_t`, opaque handles, function pointers). No `std::string`, vtables, or third-party headers cross a `.so` boundary. Exceptions are converted to `entropic_error_t` codes and `entropic_last_error(handle)`.
- **Callbacks** go the other way: Python functions become `CFUNCTYPE` trampolines, and the wrappers catch every exception so nothing unwinds into C (`hooks.py` prints the traceback and returns 0).

## Memory rules across the boundary

These are the rules in `entropic.h` (its "Memory ownership" docs) and the architecture doc:

1. **Engine-returned `char*` is caller-owned.** Free it with `entropic_free()`. Passing NULL is a no-op. Internally this is `free()` (`src/facade/entropic.cpp:1954`), and `entropic_alloc()` also uses the same allocator, so the two pair correctly.
2. **`const char*` from a handle** (for example `entropic_last_error`) is owned by the handle and valid only until the next call on that handle. Do not free it.
3. **`entropic_version()`** returns a static string. Do not free it.
4. **Callback-scoped pointers** (`ent_delegation_request_t`, `ent_delegation_result_t`, the token and observer strings) are engine-owned and valid only for the callback. The consumer must copy anything it keeps. The Python code does this with `ctypes.string_at(...)`.
5. **Buffers the engine will free must come from `entropic_alloc()`.** The hook `modified_json` path follows this: `hooks.py` `_alloc_c_string` and the trampoline both allocate with `entropic_alloc`.
6. **Python must keep CFUNCTYPE objects alive** for as long as C may call them. `hooks.py` keeps them in `_HookEntry.trampoline` and `_bound[handle]`. `streams.py` keeps them in `_observers[handle]`, and `register_token_observer` replaces the entry for a handle.
7. **Threading**: each function documents a class. Calls are serialized per handle, and init/destroy must not race other calls on the same handle. Different handles are independent.

## A gap I found

The Python wrapper does not follow rule 1 for the functions it binds as `c_char_p`.

- `_bindings.py` binds `entropic_list_mcp_servers` (line 294), `entropic_adapter_info` (305), `entropic_adapter_list` (306), and similar string-returning functions with `restype = c_char_p`. The header marks these as caller-must-free (`entropic.h` around lines 1273, 1281, 1507). ctypes copies the result into `bytes` and drops the pointer, so `entropic_free` can never be called. Each call leaks the string.
- For out-parameter functions such as `entropic_run`, `entropic_metrics_json`, and `entropic_context_get`, the caller gets a copy through `POINTER(c_char_p)`. The raw pointer is then unrecoverable unless the caller casts it to `c_void_p` and frees it. Nothing in `python/src/entropic/` calls `entropic_free`. A grep for it finds only the binding and the manifest.
- The generator's type map (`scripts/gen_bindings.py`, around lines 118–140) sends `char*` returns to `c_char_p` without special handling. I did not check whether the generator has a separate return-ownership path.

I verified this by reading the code. I did not build the library or run a leak check, so the leak claim is from source inspection. A quick test would confirm it: call `entropic_list_mcp_servers` in a loop under valgrind or ASan and watch the heap grow.

The likely fix is to bind these returns as `c_void_p`, copy the value with `string_at`, and call `entropic_free` in the wrapper. Those functions also need the wrapper to free any out-param pointers. Note that `entropic.h` is an interface contract. The fix belongs in the Python wrapper, so it does not need an interface change.