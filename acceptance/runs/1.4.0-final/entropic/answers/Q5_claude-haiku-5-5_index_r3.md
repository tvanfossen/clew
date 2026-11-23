**Short answer:** Python never links the C++ code. It loads `librentropic.so` with `ctypes` and calls the pure-C ABI in `entropic.h`. The memory rules are the C header's: who frees what, and what must be allocated by the engine's allocator. The Python side follows most of them, but the ownership rule for returned `char*` strings is not followed in the bindings.

```
Python code
  │
  ├─ entropic/_loader.py   ctypes.CDLL(librentropic.so)
  ├─ entropic/_bindings.py  _bind(): fn.restype / fn.argtypes pinned per symbol
  │                         CFUNCTYPE typedefs (HOOK_CB, TOKEN_CB, ...)
  ├─ facades: hooks.py, streams.py, mcp.py, helpers.py
  │
  ▼  C ABI (entropic.h, pure C, opaque handles, error codes)
src/facade/entropic.cpp  ── entropic_alloc = malloc, entropic_free = free
  │
  ▼  C++ engine (exceptions never cross the .so boundary)
```

**The C header's memory rules** (`include/entropic/entropic.h:32-37`, `entropic_free` and `entropic_alloc` docs):

1. A `char*` return transfers ownership to the caller. Free it with `entropic_free()`.
2. A `const char*` return is owned by the handle and valid until the next call on that handle. `entropic_version()` is static and must not be freed.
3. Any buffer the engine will free must come from `entropic_alloc()`. The hook `modified_json` is the example (`include/entropic/types/hooks.h:119`).
4. Thread safety is per function: thread-safe, serialized per handle, or single-threaded init/destroy.

**How the Python side honours them:**

- **Inbound buffers (rule 3):** `hooks._alloc_c_string` and `_build_trampoline` allocate with `entropic_alloc`, copy the UTF-8 bytes plus NUL, and let the engine free them. Using `entropic_alloc` rather than Python's allocator matters because the engine's `free` is the C library `free`, and the allocator must match.
- **Callback lifetime:** a `CFUNCTYPE` object is garbage-collected if nothing holds it, and C would then call freed memory. `hooks.py` keeps every trampoline on a per-handle list in `_bound`. `streams.py` keeps the observer in `_observers`. Both key by the handle's address.
- **Length-delimited data:** streamed tokens are read with `ctypes.string_at(ptr, length)`, not as NUL-terminated strings, because the engine passes a length.
- **No exceptions into C:** every trampoline wraps the user callable in `try/except`, prints the traceback, and returns a pass-through code.

**A gap I found:** the `char*`-returning functions are bound with `restype = c_char_p`, for example `entropic_list_mcp_servers` (`_bindings.py:294`), `entropic_adapter_info` and `entropic_adapter_list` (305-306), `entropic_grammar_get`, `entropic_grammar_validate`, `entropic_grammar_list` (310-312), `entropic_profile_get` (315), `entropic_list_mcp_keys` (322), and `entropic_get_identity_config` / `entropic_list_identities` (332-333). With `c_char_p` restype, ctypes copies the result into a Python `bytes` object and discards the original pointer. Nothing in the Python package calls `entropic_free` on these returns (grep confirms the only `entropic_free` reference outside the generated file is the export list). Each call should leak one allocation. I confirmed this by reading the bindings and grepping; I did not run a leak check. The fix is to bind these as `POINTER(c_void_p)` or a small `c_void_p` wrapper, copy the string, then call `entropic_free`. The out-parameter functions (`entropic_run`, `entropic_compact`, `entropic_get_identity`, and so on) take `POINTER(c_char_p)` and have the same problem, unless the caller frees them by hand.