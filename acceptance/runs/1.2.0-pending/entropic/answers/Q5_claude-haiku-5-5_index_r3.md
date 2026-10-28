**How Python reaches the engine**

There is no Python engine class. The Python package is a ctypes shim over the C ABI:

```
Python caller
  └─ entropic (__init__.py)        PEP 562 lazy exports, no logic
       └─ entropic._bindings       generated from include/entropic/entropic.h
            │                      by scripts/gen_bindings.py (pre-commit checks drift)
            └─ _loader.load()      finds librentropic.so, returns ctypes.CDLL
                 search order: $ENTROPIC_LIB, $ENTROPIC_HOME/{entropic/,}lib,
                 ~/.entropic/{entropic/,}lib, then ldconfig
                  └─ librentropic.so   extern "C" entropic_* (ENTROPIC_EXPORT)
```

- Each symbol is bound once with `_bind(name, restype, *argtypes)`. The handle is `entropic_handle_t = c_void_p`.
- Hand-written facades sit on top: `hooks.py`, `streams.py`, `mcp.py`, `helpers.py`.
- Errors come back as `entropic_error_t` return codes, not exceptions. Exceptions never cross the `.so` boundary, and the Python trampolines catch and print them.

**Memory rules that cross the boundary**

1. **Engine-allocated `char*` out-params** (e.g. `entropic_run(h, input, char** result_json)`) are owned by the caller and must be released with `entropic_free()`. Both `entropic_alloc` and `entropic_free` are `malloc`/`free` inside the same library, so the pairing is consistent (`src/facade/entropic.cpp:1944`, `:1954`).
2. **Consumer-allocated buffers the engine frees** (hook `modified_json`) must come from `entropic_alloc()`. `hooks.py:123` (`_alloc_c_string`) and `hooks.py:159-162` follow this rule.
3. **`const char*` returns** (e.g. `entropic_version`, `entropic_last_error`) are static or handle-owned. They are valid until the next call on that handle and must not be freed.
4. **Callback arguments are borrowed.** Token, state, residency, and delegation pointers are valid only for the callback's duration. Python must copy them (`string_at`, `decode`) before returning.
5. **Python must keep CFUNCTYPE trampolines alive** for as long as C can call them. `hooks._bound` and `streams._observers` hold references per handle. A bare `HOOK_CB(f)` that is dropped becomes a use-after-free.
6. **Callbacks must not re-enter the same handle.** The header says so for token callbacks and residency observers, and warns of a deadlock risk.

**Problems I found while checking the rules**

- **Leaks in the generated bindings.** Twelve functions return caller-owned `char*` per the header: `entropic_list_mcp_servers`, `entropic_adapter_info`, `entropic_adapter_list`, `entropic_grammar_get`, `entropic_grammar_list`, `entropic_grammar_validate`, `entropic_profile_get`, `entropic_profile_list`, `entropic_list_mcp_keys`, `entropic_serialize_mcp_keys`, `entropic_get_identity_config`, `entropic_list_identities`, and `entropic_validation_last_result`. `_bindings.py` binds them with `restype = c_char_p`. ctypes copies the string to `bytes` and discards the pointer, so the buffer can never reach `entropic_free`. Every direct ctypes call leaks. The fix belongs in the generator: map these to `c_void_p`, then copy and free.
- **`entropic_run` and friends have no wrapper.** The out-param is typed `POINTER(c_char_p)`. A Python caller has to read the result and then free the raw address via `ctypes.cast(p, c_void_p)`. Nothing under `python/src/` calls `entropic_free`, so the package offers no safe path for this.
- **Token observer may mis-read tokens with embedded NUL (unverified).** `TOKEN_CB` and `STREAM_OBSERVER_CB` declare the first argument as `c_char_p`, so ctypes hands `streams.py:71` a NUL-truncated `bytes`. Then `string_at(token_ptr, length)` reads `length` bytes from that object. A token containing NUL is truncated, and if `length` exceeds the copy, the read runs past the object. The fix is to declare the argument `c_void_p` and read `length` bytes. I did not run this.
- **Stale doc references.** `entropic.h` at lines 701 and 813 says to free with `entropic_free_string`. That symbol does not exist; the function is `entropic_free`.

I did not run any Python or tests for this. The findings come from reading the header, the generated bindings, and the facades.