**How Python reaches the engine**

There is no pybind or Cython layer. The Python package is a ctypes shim over `librentropic.so`, and it reaches the engine through the public C header `include/entropic/entropic.h`:

```
Python caller
  └─ entropic (__init__.py)        PEP 562 lazy __getattr__; no .so load at import
       └─ _bindings.py             AUTO-GENERATED from entropic.h by scripts/gen_bindings.py
            └─ _loader.py          find() + ctypes.CDLL(librentropic.so)
                 └─ C ABI          entropic_create / entropic_run / ...  (src/facade/entropic.cpp)
```

- `_loader.load()` resolves the library in this order: `$ENTROPIC_LIB`, then `$ENTROPIC_HOME`, then `~/.entropic/...`, then `ctypes.util.find_library`. If nothing resolves, it raises `OSError`.
- `_bindings.py` pins `restype` and `argtypes` on every symbol via `_bind(...)`. The opaque handle is `entropic_handle_t = ctypes.c_void_p`.
- The lazy import is deliberate. `entropic install-engine` has to import the package before the `.so` exists.
- Hooks, token observers and the attempt-boundary callback go the other way. They are `CFUNCTYPE` trampolines (`HOOK_CB`, `TOKEN_CB`, and so on) that the engine calls back into.

**Memory rules that cross the boundary**

1. **Strings the engine returns and the caller owns.** Functions such as `entropic_run` return `char**` out-params. The header says the caller must free them with `entropic_free()`. Python's `_bindings.py` declares these as `POINTER(c_char_p)`, and ctypes copies the bytes out when you read the value. The raw pointer is lost, so the buffer can't be freed through that path. I found no call to `entropic_free` anywhere in `python/src/entropic/`, so a Python caller of these functions leaks the result unless it re-reads the address as `c_void_p` and frees it. This is the most important finding here.

2. **Memory the caller hands to the engine.** The engine frees these with `free()`, so the caller must allocate them with `entropic_alloc()` (a `malloc` wrapper), never Python's allocator. `hooks.py:_build_trampoline` does this for hook `modified_json`, and the header in `types/hooks.h` states the same rule.

3. **`const char*` returns.** These are owned by the handle and valid until the next call on that handle. Don't free them. The `entropic_last_error` case in `types/error.h` is one example.

4. **Callback arguments.** Strings and structs the engine passes into callbacks (`context_json`, the `ent_delegation_*` structs) are engine-owned and valid only for the duration of the call. Python copies them immediately: `hooks.py` uses `ctypes.string_at(...).decode()`. Anything kept must be copied.

5. **Trampoline lifetime.** A CFUNCTYPE object that Python garbage-collects while the engine still holds its pointer becomes a use-after-free. The package keeps references alive in three places:
   - `hooks.py:_bound`, keyed by handle address
   - `streams.py:_observers`, keyed by handle address
   - `helpers.py:_BCB`, a local the helper keeps alive

6. **Exceptions never cross.** `hooks.py:_trampoline` catches everything, prints the traceback, and returns 0 (pass-through). A raised exception would unwind through C frames.

7. **Handles.** `entropic_create` / `entropic_destroy` must be paired. Destroy is NULL-safe, and the handle is invalid after destroy.

8. **Input strings.** A Python `str` or `bytes` passed as `c_char_p` stays valid for the call. If the engine keeps the pointer after the call returns, that is a bug. I did not verify each input path.

**Risk I'd flag**

`destroy` does not clear the Python-side keepalive registries. `_bound` and `_observers` keep entries for dead handles. If a new handle reuses an address, `register_hooks` checks `_bound[addr]` and skips any hook whose function and point already match. The new handle would then silently miss its hooks. This follows from reading the code and I did not reproduce it. A fix would clear the entries in a teardown path, or key the registries on something other than the raw address.

I did not run the test suite or build the library. The findings are from reading the Python sources and the C header, with the index used to confirm the C side's `malloc`/`free`, `entropic_alloc`, and `entropic_run` signatures.