## How Python reaches the engine

There is no pybind11 or cffi. The only bridge is `ctypes` calling the C ABI of `librentropic.so`.

```
your Python code
  └─ entropic/__init__.py       PEP 562 lazy exports
       ├─ hooks.py, streams.py  Pythonic wrappers: dict↔JSON, callback keepalive
       └─ _bindings.py          generated ctypes; _bind() pins restype/argtypes
            └─ _loader.py       ctypes.CDLL(librentropic.so)
                 └─ include/entropic/entropic.h  →  src/facade/entropic.cpp
```

- `scripts/gen_bindings.py` parses the public headers with a hand-rolled parser (not pycparser) and emits `_bindings.py` and `_bindings_manifest.py`.
- `_loader.py` finds the library in this order: `$ENTROPIC_LIB`, `$ENTROPIC_HOME`, `~/.entropic`, then `ldconfig`.
- The handle is an opaque `c_void_p`. Structs are `ctypes.Structure`. Enums are `IntEnum`.

## Memory rules across the boundary

The header (`entropic.h`, "Memory ownership") and the hook/stream code set these rules:

1. **Engine-returned `char*` is caller-owned.** Free it with `entropic_free()`. Internally this is `malloc`/`free` in the same `.so`.
2. **Buffers the engine will free must come from `entropic_alloc()`.** Hook `modified_json` is the main case. `hooks.py` does this in its trampoline.
3. **`const char*` returns belong to the handle.** They stay valid until the next call on that handle. `entropic_version()` is static and must not be freed.
4. **Callback arguments are borrowed for the callback only.** The hook `context_json` and the stream token buffer are copied with `ctypes.string_at` before returning.
5. **Exceptions never cross into C.** Trampolines catch and print them. Each returns a status code instead.
6. **Keep CFUNCTYPE objects alive.** `hooks.py` keeps them in per-handle lists. `streams.py` keeps them in `_observers`. A dropped wrapper means C calls freed memory.
7. **Handle lifecycle is single-threaded.** `create`/`destroy` must not race other calls on the same handle. Calls are serialized per handle.

## Problems I found

**1. Owned strings leak in Python.** Six functions return a caller-owned `char*` but are bound with `restype=ctypes.c_char_p`:

- `entropic_adapter_info`
- `entropic_grammar_get`
- `entropic_grammar_validate`
- `entropic_profile_get`
- `entropic_list_mcp_keys`
- `entropic_get_identity_config`

`ctypes` converts a `c_char_p` return into a `bytes` copy and discards the raw pointer. So `entropic_free()` can never be called on it. The generator causes this: `scripts/gen_bindings.py:133` maps every `char*` return to `c_char_p`. The fix is `restype=c_void_p`, copy with `string_at`, then `entropic_free`. Out-params (`char**`, as in `entropic_run`) have the same trap. The raw pointer must be read with `cast(out, c_void_p)` before `.value`. I did not run a leak test. A loop with RSS monitoring would confirm it.

**2. Documentation names a function that does not exist.** `entropic_free_string` appears in `entropic.h:701` and `:812`, and in `entropic.cpp:4022` and `:4099`. The real function is `entropic_free`. A consumer following the docs will get a link error.

**3. Dead helper.** `hooks.py:123` `_alloc_c_string` has no callers. The trampoline at about line 160 repeats its logic inline. This violates the DRY rule in the project standards.

Nothing was built or run. Findings 1 and 2 are from reading the code and headers.