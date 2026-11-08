## How Python reaches the engine

Python does not talk to a Python-side engine object. It loads the shared library `librentropic.so` with `ctypes` and calls the C ABI in `include/entropic/entropic.h` directly.

- **Loading:** `python/src/entropic/_loader.py` finds and loads `librentropic.so` (`load()`, `find()`). `python/src/entropic/_bindings.py` is generated from the C header by `scripts/gen_bindings.py`, and it has a `_bind(name, restype, *argtypes)` helper that sets `restype` and `argtypes` on each symbol from the loaded library. The file's banner says "generated, do not edit."
- **Lazy import:** `python/src/entropic/__init__.py` resolves binding names lazily (PEP 562 `__getattr__`), so `entropic install-engine` can run before the `.so` exists on disk.
- **No wrapper class:** the package exposes flat functions such as `entropic_create`, `entropic_configure_dir`, `entropic_run_streaming` and `entropic_destroy`. There is no `EntropicEngine` class; the docstring says the C ABI is the public surface.
- **Enums and structs:** IntEnums and `ctypes.Structure` types are mirrored by hand or generated, and `tests/unit/test_bindings_abi.py` checks them against the C headers so they cannot drift silently.
- **Callbacks:** C function-pointer typedefs are `ctypes.CFUNCTYPE` objects, such as `HOOK_CB`, `TOKEN_CB` and `COMPACTOR_CB`.

The C side is a facade. `include/entropic/entropic.h` says all functions are pure C with no C++ types crossing the boundary. Exceptions do not cross the boundary either: errors come back as `entropic_error_t` codes plus `entropic_last_error(handle)`.

## Memory rules across the boundary

| Direction | Rule | Source |
|---|---|---|
| C → caller, `char*` return | Ownership transfers to the caller. Free with `entropic_free()`. | `entropic.h` "Memory ownership" |
| `const char*` return | Owned by the handle. Valid only until the next call on that handle. | `entropic.h` |
| Caller → engine, buffer the engine will free | Must be allocated with `entropic_alloc()`, which is `malloc`. Example: a hook's `modified_json`. | `entropic.h`, `src/facade/entropic.cpp` |
| `entropic_run` result | `*result_json` is caller-owned and must be freed with `entropic_free()`. On an internal exception the engine still returns partial context in `*result_json` and the caller must free it too. | `entropic_run` doc and body |
| `entropic_free(NULL)` | No-op. | `entropic_free` doc |
| Input strings | Borrowed for the duration of the call only. The engine copies what it keeps. | `i_mcp_server.h`, `i_inference_backend.h` |
| Stream token pointers | Valid only during the callback. Copy them to keep them. | `i_inference_backend.h` |
| Handle lifetime | `entropic_destroy` invalidates the handle. Destroy is single-threaded and must not race other calls on that handle. | `entropic_destroy` doc |

Two rules matter most for Python:

1. **Allocator pairing.** Memory the engine hands out must be freed with `entropic_free`, and memory the engine will free must come from `entropic_alloc`. Mixing these with Python's own allocator is wrong. The index shows `hooks.py` doing this correctly via `_alloc_c_string`, which calls `entropic_alloc`.
2. **Callback lifetime.** `hooks.py` documents the foot-gun directly. A `CFUNCTYPE` wrapper passed inline to `entropic_register_hook` is dropped when the call returns, and later invocations from C then dereference freed memory. The module keeps a per-handle registry that holds the wrappers alive. Any other Python callback registered with the engine needs the same treatment.

## Gaps in what I could verify

- The index shows `entropic_run` and `entropic_free` in the C layer and that `_bindings.py` binds `entropic_free` as a symbol. It does not show a Python call site that frees `result_json` after `entropic_run`. I'm inferring that Python follows the documented contract. Check the high-level Python callers before relying on it.
- `_bindings.py` is generated, so edits belong in `scripts/gen_bindings.py` and not in the output file.