Python never touches C++ directly. It loads the engine's C ABI with `ctypes` from a shared library, and every crossing uses C types only. The memory rules are the C header's ownership contract, and Python has to follow them by hand.

## How Python reaches the engine

```
Python code
  │  entropic._bindings  (generated ctypes shims: restype/argtypes pinned per symbol)
  │  entropic._loader    (ctypes.CDLL on librentropic.so)
  ▼
librentropic.so  ── extern "C" entropic_* (include/entropic/entropic.h)
  │                 (C++ engine behind the pure-C facade; no C++ types cross)
  ▼
C++ engine (src/facade/entropic.cpp → core/backends)
```

- **No compiled extension.** There is no pybind11, nanobind, or cffi. `python/CMakeLists.txt` is a placeholder, and the wheel is pure Python.
- **Library lookup** (`python/src/entropic/_loader.py`): `$ENTROPIC_LIB`, then `$ENTROPIC_HOME`, then `~/.entropic/...`, then `ldconfig`.
- **Bindings are generated** from `entropic.h` by `scripts/gen_bindings.py` (`inv gen-bindings`, enforced by a pre-commit `--check`). The output `_bindings.py` is marked do-not-edit. Each `char*` or `const char*` maps to `c_char_p`, `void*` to `c_void_p`, and each callback to a `CFUNCTYPE`.
- **Handles** are `c_void_p`. Out-params use `ctypes.byref` or `POINTER(c_char_p)`.
- **Errors** come back as integer return codes (`EntropicError`), and `entropic_last_error(handle)` gives the message. Exceptions never cross the boundary. The Python trampolines catch exceptions and print them.

## Memory rules at the boundary

These come from the header's "Memory ownership" block and the architecture doc (design rule 2: pure C at `.so` boundaries).

1. **Engine-returned `char*` transfers ownership.** The caller frees it with `entropic_free()`, which is `free()`. `entropic_alloc()` is `malloc()`, so allocators match.
2. **Memory the engine will free must come from `entropic_alloc()`.** `hooks.py` does this in `_alloc_c_string` and the hook trampoline for `modified_json`.
3. **`const char*` returns are owned by the handle** and valid until the next call on that handle. Copy them immediately. The `c_char_p` restype does this.
4. **Callback pointers are borrowed for the call only.** The token and observer trampolines copy with `string_at` before returning. `on_token` must not call back into the API, since that deadlocks.
5. **Python callbacks must be kept alive.** A `CFUNCTYPE` object that gets garbage-collected leaves C holding a dangling function pointer. `hooks.py` (`_bound`), `streams.py` (`_observers`), and the `helpers.py` example each hold a reference per handle.
6. **Interface headers use C types only.** No `std::string`, `std::vector`, or `json` in `interfaces/` or `types/`.

## Gap: owned strings leak in the generated bindings

The bindings do not follow rule 1 for many functions. These C functions return a heap `char*` that the caller must free, but their Python bindings declare `restype = c_char_p`:

- `entropic_list_mcp_servers`, `entropic_list_mcp_keys`, `entropic_serialize_mcp_keys`
- `entropic_grammar_get`, `entropic_grammar_validate`, `entropic_grammar_list`
- `entropic_profile_get`, `entropic_profile_list`
- `entropic_get_identity_config`, `entropic_list_identities`
- `entropic_adapter_info`, `entropic_adapter_list`, `entropic_validation_last_result`

ctypes copies the bytes into a Python object and discards the original pointer, so nothing can call `entropic_free` on it. Each call leaks the string. I confirmed this by reading `_bindings.py` and the header. I did not run it, so the leak is unmeasured.

The generator maps every `char*` to `c_char_p` regardless of ownership. The fix is to bind owning returns as `c_void_p`, then copy with `ctypes.string_at` and call `entropic_free`. This needs a change in `scripts/gen_bindings.py`, not a hand-edit of `_bindings.py`.

The `entropic_run*` out-params have the same ownership rule. The `entropic_run` binding takes `POINTER(c_char_p)`, so a Python caller who reads `.value` must still free the original pointer with `entropic_free`. Nothing in the Python package does that, and the docs example only uses the streaming call.