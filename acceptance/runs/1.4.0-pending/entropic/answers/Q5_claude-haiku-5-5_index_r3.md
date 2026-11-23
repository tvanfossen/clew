## How Python reaches the engine

Python talks to the C ABI through `ctypes`. There is no pybind11, cffi, or C extension module.

```
Python code
  └─ entropic/__init__.py   PEP 562 __getattr__ imports _bindings on first use
      └─ _bindings.py       generated; _lib = load() at import, then _bind() per symbol
          └─ _loader.py     finds librentropic.so (ENTROPIC_LIB, ENTROPIC_HOME, ~/.entropic, ldconfig)
              └─ librentropic.so   C ABI (include/entropic/entropic.h), C++ inside
```

- `scripts/gen_bindings.py` parses `include/entropic/entropic.h` and `types/*.h` and emits `_bindings.py` (ctypes function objects with `restype`/`argtypes`, IntEnums, Structures, CFUNCTYPE typedefs) and `_bindings_manifest.py`. `inv gen-bindings --check` runs in pre-commit and fails on drift.
- `entropic_handle_t` is `c_void_p`, an opaque pointer. The C++ engine never crosses the `.so` boundary, per the design rules (pure C at the boundary, error codes instead of exceptions).
- Hand-written modules sit on top: `hooks.py`, `streams.py`, `helpers.py`, `mcp.py`, `cli.py`.

## Memory rules at the boundary

The contract is in the header, `entropic.h:32-37`, and the implementation is trivial: `entropic_alloc` is `malloc` and `entropic_free` is `free` (`src/facade/entropic.cpp:1944-1956`).

| Direction | Rule | Where it applies |
|---|---|---|
| Engine → Python, `const char*` | Owned by the handle, valid until the next call on that handle. Do not free. `entropic_version` is static. | `entropic_version`, and similar |
| Engine → Python, `char*` return or out-param | Caller owns it. Must call `entropic_free()`. | `entropic_run*`, `entropic_list_mcp_servers`, `entropic_grammar_*`, `entropic_profile_*`, and others |
| Python → engine, buffer the engine frees | Must be allocated with `entropic_alloc()`, never with Python's allocator. | Hook `modified_json`, `hooks.py:123` and `:159` |
| Callback arguments (token, context JSON, consumed buffers) | Valid only for the duration of the callback. Copy them if you keep them. | `TOKEN_CB`, `STREAM_OBSERVER_CB`, `HOOK_CB` (`entropic.h:355`, `654`, `739`, `1006`, `1027`) |
| CFUNCTYPE wrappers | Python must hold a reference for as long as C may call them, or C calls freed memory. | `hooks.py:73-76`, `streams.py:40-43` keep per-handle registries |
| Exceptions in callbacks | Must never escape into C. Trampolines catch and print them. | `hooks.py:_trampoline`, `streams.py:_trampoline` |
| Threading | Init and destroy are single-threaded. Other calls are serialized per handle. | `entropic.h:70`, `160` |

Python's own handling follows these rules. Callback data is copied with `ctypes.string_at` (`hooks.py:154`, `streams.py:71`), and the hook payload is written into `entropic_alloc` memory (`hooks.py:159-162`).

## Problems I found

1. **Owned `char*` returns lose their pointer in the raw bindings.** `gen_bindings.py:132-134` maps `char*` to `c_char_p`, and the generator has no notion of ownership. `_bindings.py:294` and the other owned-return bindings therefore give Python a `bytes` copy, and the original pointer is gone, so `entropic_free` can't be called. This leaks. Nothing in `python/src` calls these functions today, so the leak only affects direct users of the raw surface. The fix is to bind owned returns as `c_void_p`, copy the string, then free it, or to annotate ownership in the generator. Not reproduced at runtime.

2. **`_bound` in `hooks.py:84` and `:195` is never cleared.** It is keyed by handle address and no code removes entries on `entropic_destroy`. If a new handle is created at a reused address, `register_hooks` skips every already-recorded `(func, point)` pair and the hooks are silently not registered. `malloc` reuse makes this plausible. I haven't reproduced it.

3. **`hooks.py:_build_trampoline` returns `rc = 1` even when `entropic_alloc` returns NULL.** The `if ptr:` guard prevents the write, but the return still signals "transform" with no payload. I haven't checked how the engine handles a NULL `modified_json` after rc=1.

The Python package has no ABI version check at import time. `entropic_api_version` is bound but never called in `python/src`.