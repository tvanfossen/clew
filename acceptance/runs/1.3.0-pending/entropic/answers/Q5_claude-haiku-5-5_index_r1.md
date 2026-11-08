## How Python reaches the engine

Python never links against C++. It loads the C ABI shared library `librentropic.so` with `ctypes`, and the C header is the only contract.

```
entropic (Python package)
  streams.py / hooks.py / mcp.py / helpers.py   facades: keepalive + marshalling
          │
  _bindings.py          generated from include/entropic/entropic.h
          │             by scripts/gen_bindings.py (pre-commit checks drift)
          │  ctypes.CDLL
          ▼
  _loader.find()        $ENTROPIC_LIB → $ENTROPIC_HOME → ~/.entropic → ldconfig
          │
  librentropic.so       facade/entropic.cpp: extern "C", exceptions caught inside
          │
  C++ engine core
```

- `_loader.py` resolves the library path. `_bindings.py` loads it at import time and pins each symbol's `restype` and `argtypes` through `_bind(...)`.
- The generator maps C types to ctypes: `const char*` and `char*` both become `c_char_p`, `char**` becomes `POINTER(c_char_p)`, and `void*` becomes `c_void_p`.
- `__init__.py` lazily re-exports the raw bindings, so consumers can call the C functions directly.

## Memory rules

The header (`entropic.h:32-37`, `:238-249`) sets these rules:

1. **`char*` returns transfer ownership.** The caller frees them with `entropic_free()`. Out-params such as `char** result_json` follow the same rule.
2. **`const char*` returns belong to the handle** and stay valid until the next call on that handle. `entropic_last_error` and `entropic_version` (static) are examples, and the caller must not free them.
3. **Buffers the engine will free must come from `entropic_alloc()`.** The hook `modified_json` is the main case. The engine calls `free()` on it (`hook_registry.cpp`), and `entropic_alloc` is `malloc` (`entropic.cpp:1944`), so the provenance matches.
4. **Exceptions never cross the boundary.** Errors come back as `entropic_error_t` codes, with the detail available through `entropic_last_error`.
5. **Handle lifetime:** `create` and `destroy` are single-threaded, and `destroy` must not race other calls on the same handle. Per-handle calls are serialized.

The Python facades follow these rules as follows:

- **Callback lifetime.** A `CFUNCTYPE` wrapper is garbage-collected unless Python holds a reference. `streams._observers`, `hooks._bound` and `_HookEntry.trampoline` keep them alive for the handle's life.
- **No exceptions into C.** Trampolines catch everything and call `traceback.print_exc()`.
- **Hook output.** `hooks._build_trampoline` JSON-encodes the returned dict into `entropic_alloc` memory and writes it to `*mod_out`. The engine frees it.

## Gaps I found

1. **The raw bindings leak `char*` returns. This is the main issue.** The generator maps `char*` to `c_char_p`, so ctypes copies the string into a Python `bytes` and discards the pointer. Nothing under `python/src` calls `entropic_free`. Any direct call to `entropic_run`, `entropic_list_mcp_servers`, `entropic_list_identities`, `entropic_validation_last_result`, `entropic_grammar_get` and similar functions leaks the engine's allocation. The C++ caller in `examples/openai-server/src/main.cpp:334-340` frees correctly, so the contract is clear. The header already distinguishes `char*` from `const char*`, so the generator could emit a wrapper (for example, `c_void_p` restype, read with `string_at`, then `entropic_free`) for owned returns and keep `c_char_p` for borrowed ones.

2. **Stream token callback (unverified).** `TOKEN_CB` declares the token as `c_char_p`, so ctypes likely hands the trampoline a NUL-truncated `bytes`. The trampoline then calls `string_at(token_ptr, length)`, which reads `length` bytes from that object. If a token contains an embedded NUL, that read runs past the object. This needs a runtime check before anyone relies on it. Tokens with embedded NULs are probably rare.

3. **Minor, in `hooks.py`.** If `entropic_alloc` returns NULL, the trampoline still returns `rc=1` and never sets `*mod_out`. The per-handle dicts (`_observers`, `_bound`) are also keyed by handle address and never cleared on `entropic_destroy`.

I did not build or run anything; this is from reading the headers, bindings and facades. Gap 1 can be confirmed by reading the generator output, and gap 2 by a small ctypes experiment.