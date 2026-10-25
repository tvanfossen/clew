**How Python reaches the engine**

There is no C++ extension module, no pybind11, and no cffi. Python loads `librentropic.so` with `ctypes.CDLL` and calls its exported C symbols directly.

```
Python caller
  └─ entropic/__init__.py      (PEP 562 lazy re-exports, facade for hooks/streams/mcp)
      └─ entropic/_bindings.py (generated: restype/argtypes per C symbol, IntEnums, Structures, CFUNCTYPEs)
          └─ entropic/_loader.py  find() → ctypes.CDLL(librentropic.so)
              └─ C ABI: include/entropic/entropic.h (ENTROPIC_EXPORT, opaque handle)
                  └─ C++ engine behind the .so
```

- **Library resolution** (`_loader.py`): `$ENTROPIC_LIB`, then `$ENTROPIC_HOME` (nested and flat layouts), then `~/.entropic/...`, then `ctypes.util.find_library`.
- **Binding generation**: `scripts/gen_bindings.py` parses `entropic.h` and `types/*.h` and writes `_bindings.py` and `_bindings_manifest.py`. The `--check` mode runs in pre-commit, so the bindings cannot drift from the header. The `_bind()` helper pins `restype` and `argtypes` on each symbol.
- **Type mapping**: `char*` and `const char*` become `c_char_p`. `char**` out-params become `POINTER(c_char_p)`. Every C enum is an `int` at the boundary, with an `IntEnum` on the Python side. Handles are `c_void_p`.
- **Callbacks**: C function pointers become `CFUNCTYPE` objects (for example `HOOK_CB`, `TOKEN_CB`, `STATE_OBSERVER_CB`).

**Memory rules across the boundary**

The header states the rules. The Python layer partly follows them and partly does not.

1. **Engine-allocated `char*` returns transfer ownership to the caller.** Free them with `entropic_free()`. Many functions document this, including `entropic_list_mcp_servers`, `entropic_adapter_info`, `entropic_grammar_get`, `entropic_grammar_validate`, and `entropic_profile_get`.
2. **`const char*` returns are owned by the handle** and stay valid until the next call on that handle. `entropic_version()` is static and must not be freed.
3. **Memory the engine will free must come from `entropic_alloc()`.** Hook `modified_json` is the example. `hooks.py:_alloc_c_string` and the trampoline in `_build_trampoline` do this correctly: they allocate with `entropic_alloc`, copy the bytes, and let the engine free them.
4. **Engine-owned structs and strings passed to callbacks are valid only for the callback's duration.** Examples are `ent_delegation_request_t`, `ent_delegation_result_t`, and the token pointer in `on_token`. Copy anything you keep. `streams.py` does this with `ctypes.string_at(token_ptr, length)`.
5. **Callbacks must not re-enter the API.** The `on_token` and state-observer docs say this because of deadlock risk.
6. **Callback objects must be kept alive.** Python garbage collection will free a `CFUNCTYPE` object if nothing references it, and the C side would then call freed memory. `streams.py` keeps them in `_observers` keyed by handle, and `hooks.py` keeps them in `_bound`.
7. **Exceptions must not cross into C.** Both trampolines catch everything, print a traceback, and return a pass-through value.
8. **Out-struct rules.** `EntropicLogprobResult` is caller-owned, but its inner arrays must be released with `entropic_free_logprob_result()`.

**Where the Python side breaks rule 1**

The generator maps every `char*` return to `restype = c_char_p`. When ctypes converts a `c_char_p` restype, it copies the bytes into a Python `bytes` object and discards the raw pointer. The caller therefore has no pointer to pass to `entropic_free()`. Nothing in `python/src` calls `entropic_free` except the alloc helpers, so each of these owned returns leaks on every call from Python. The `POINTER(c_char_p)` out-params for `entropic_run`, `entropic_context_get`, and similar functions have the same exposure: the typed binding gives no hint that the pointer must be freed. I confirmed this by reading the generator and the bindings. I did not run a leak check.

Possible fixes, for your decision:
- Give owned-return functions a `c_void_p` restype, then wrap them in a helper that reads the bytes with `string_at`, calls `entropic_free`, and returns `str`.
- Or, if the generator can tell owned from borrowed returns, emit that helper automatically.

**Smaller gap**

`entropic_destroy` is never wrapped in Python, and nothing clears `_observers` or `_bound` on teardown. Those `CFUNCTYPE` objects therefore outlive the engine. This is a small leak, not a crash, and it only matters for long-running processes that create many handles.