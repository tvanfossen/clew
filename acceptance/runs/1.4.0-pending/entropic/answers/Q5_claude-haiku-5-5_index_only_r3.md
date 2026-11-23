**How Python reaches the engine**

There is no pybind11 or C++ extension. The Python package is a `ctypes` binding over the C ABI in `include/entropic/entropic.h`:

- `python/src/entropic/_loader.py`: `find()` looks for `librentropic.so` through candidate paths, then falls back to `ctypes.util.find_library("rentropic")`. `load()` raises `OSError` if nothing is found, with a hint to run `entropic install-engine` or set `$ENTROPIC_LIB`, then returns a `ctypes.CDLL`.
- `python/src/entropic/_bindings.py` is generated from the C header by `scripts/gen_bindings.py` (run via `inv gen-bindings`; `--check` fails on drift). It maps C types to ctypes, including `CFUNCTYPE` callback types and `Structure` classes.
- `python/src/entropic/__init__.py` exposes the C symbols directly with lazy (PEP 562) imports, so `entropic install-engine` can run before the `.so` exists. There is no `EntropicEngine` class; the docs say the flat binding is intentional.
- Callbacks (hooks, token streams, delegation) are Python functions wrapped in `CFUNCTYPE` trampolines. `helpers.py` keeps the wrapper referenced for the engine's lifetime so Python's GC can't collect it while C still holds the pointer.

**Memory rules across the boundary**

1. **Engine-returned `char*` is caller-owned.** The header says functions returning `char*` transfer ownership, and the caller frees them with `entropic_free()`. That is `free()` in `src/facade/entropic.cpp`, and it is a no-op on NULL.
2. **Strings returned as `const char*` are handle-owned.** They stay valid only until the next call on that handle. Copy them out in Python before making another call.
3. **Buffers the engine will free must come from `entropic_alloc()`.** This applies to things like the hook `modified_json`. `entropic_alloc()` is `malloc()`. `python/src/entropic/hooks.py:_alloc_c_string` allocates with it, memmoves the UTF-8 bytes plus a NUL, and returns the pointer. Python must never hand the engine a ctypes buffer or a Python-owned pointer that it will free.
4. **Backend and MCP results follow the same pattern.** The inference-backend and MCP-server interface headers say strings returned via `result_json` or `execute` are allocated by the callee and freed with the matching free function (`entropic_inference_free` for backends, `entropic_free` for MCP strings).
5. **Exceptions do not cross.** The header says errors are returned as `entropic_error_t`, with details via `entropic_last_error(handle)`. The Python side turns those codes into `EntropicError`.
6. **Threading.** Each function is documented as thread-safe, serialized per handle, or single-threaded for init/destroy. Destroy must not race any other call on the same handle.

**Caveats**

- I answered from the index only: header and interface doc comments, plus the bodies of `entropic_free`, `entropic_alloc`, `_alloc_c_string`, and the loader. I could not open the trampoline builder (`_build_trampoline` in `hooks.py`) or the callback-lifetime code, so the callback-lifetime rule rests on the `helpers.py` comment alone.
- The `_alloc_c_string` docstring says the caller must ensure "no Python reference outlives that free." That is vague. The engine owns the buffer once it is passed over.