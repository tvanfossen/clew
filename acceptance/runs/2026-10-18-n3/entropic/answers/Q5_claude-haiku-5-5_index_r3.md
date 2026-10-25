## How Python reaches the engine

Python never links against the engine. It loads the shared library at runtime with `ctypes`, so there is no compiled extension and no pybind or cffi layer.

```
Python (entropic-engine wheel)
  _loader.py     find librentropic.so, ctypes.CDLL(path)
  _bindings.py   ctypes bindings, generated from entropic.h
  hooks.py / streams.py / helpers.py / mcp.py   thin Python facades
        │  C ABI (pure C, opaque handles, error codes)
        ▼
librentropic.so   src/facade/entropic.cpp → C++ engine behind it
```

- **Library discovery** (`python/src/entropic/_loader.py`): checks `$ENTROPIC_LIB`, then `$ENTROPIC_HOME`, then `~/.entropic`, then `ldconfig`. Both the nested and flat install layouts are searched.
- **Bindings** (`python/src/entropic/_bindings.py`): auto-generated from `include/entropic/entropic.h` by `scripts/gen_bindings.py`. Each function gets explicit `restype` and `argtypes`. The file also holds the enums, the `ctypes.Structure` types and the `CFUNCTYPE` callback typedefs. Pre-commit runs `gen-bindings --check` and fails if the file has drifted from the header.
- **Lazy import** (`_bindings_manifest.py`): the export list is a static set, so `import entropic` works before the `.so` exists. That is what lets `entropic install-engine` run first.
- **Loader type**: `ctypes.CDLL` is used rather than `PyDLL`, so the GIL is released during each engine call. A blocking `entropic_run` does not stall other Python threads, and `entropic_interrupt()` can be called from another thread.
- **No high-level class**: the package exposes flat C-ABI symbols. Only the hooks, streams, helpers and mcp modules add Python-side conveniences.

## Rules for memory crossing the boundary

These come from the header's "Memory ownership" section plus how the Python side follows it.

1. **Engine-allocated strings are caller-owned.** Any `char*` returned or written through a `char**` out-param transfers ownership. The caller must release it with `entropic_free()`. `NULL` is a no-op.
2. **Handle-owned strings are not freed.** A `const char*` return is owned by the handle and is valid only until the next call on that handle. `entropic_version()` is static and must not be freed.
3. **The engine frees what Python gives it only via `entropic_alloc()`.** Hook `modified_json` is the example. `hooks.py` (`_alloc_c_string`, and the trampoline's write to `mod_out_ptr`) allocates through `entropic_alloc` and copies the bytes in with `memmove`. The engine then `free()`s it. Python-owned buffers such as `create_string_buffer` or bytes objects must never be handed over for the engine to free.
4. **Python must keep callback wrappers alive.** A `CFUNCTYPE` object that is garbage-collected leaves the engine holding a dangling function pointer. `streams.py` stores the wrapper in a module-level `_observers` dict keyed by handle address. `hooks.py` keeps a per-handle registry. The `helpers.py` docstring tells consumers to hold the wrapper for the engine's lifetime.
5. **Exceptions never cross into C.** Both the hook trampoline and the stream trampoline catch every exception, print the traceback, and return a pass-through value. This matches design rule 6 in `docs/architecture-cpp.md`.
6. **Errors are return codes, not exceptions.** Each call returns an `entropic_error_t`. Detail comes from the per-handle `last_error`. The Python `EntropicError` IntEnum mirrors the codes.
7. **Thread rules.** Calls are serialized per handle. Callbacks may fire on the engine thread or a delegation thread, so consumer callbacks must be thread-safe. Create and destroy must not race other calls on the same handle.

## A gap I found

The Python package has no wrapper that frees engine-owned strings. The only `entropic_free` in the Python source is the auto-generated binding itself, and nothing in `src/` or `examples/` calls it on a result. Two consequences:

- **Leak on `c_char_p` returns.** `entropic_adapter_info`, `entropic_grammar_get` and `entropic_grammar_validate` are bound with `restype=c_char_p`. ctypes copies the string into a Python `bytes` and drops the raw pointer. The header says the caller must free these, but the caller has no pointer left to free, so each call leaks.
- **Out-param results need manual handling.** `entropic_run` and the others write through `POINTER(c_char_p)`. A caller who reads `.value` gets a copy, and still has to call `entropic_free(out)` on the raw pointer. Nothing in the package enforces that.

The fix is probably to bind those three functions with `c_void_p` restype, copy the value, and call `entropic_free` before returning. Adding a small RAII-style helper for result pointers would also cover the out-param case. I read this from the code and did not run it, so the leak is unconfirmed until a test exercises it.