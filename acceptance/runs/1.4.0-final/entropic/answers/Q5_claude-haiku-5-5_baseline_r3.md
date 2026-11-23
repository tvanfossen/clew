## How Python reaches the engine

The Python package has no native code of its own. It is a ctypes layer over the C ABI in `librentropic.so`:

```
Python code
  └─ entropic (__init__.py, PEP 562 lazy exports)
       ├─ _bindings.py      generated ctypes shim (restype/argtypes per symbol)
       ├─ hooks.py / streams.py / mcp.py / helpers.py   thin Pythonic facades
       └─ _loader.py        finds librentropic.so, ctypes.CDLL(path)
            │  C ABI: extern "C", opaque void* handle, error codes
            ▼
librentropic.so  (src/facade/entropic.cpp, C++ inside; try/catch at each entry point)
```

- **Library resolution** (`_loader.py`): `$ENTROPIC_LIB`, then `$ENTROPIC_HOME` (nested and flat layouts), then `~/.entropic/...`, then `ctypes.util.find_library`.
- **Bindings** are generated from `include/entropic/entropic.h` by `scripts/gen_bindings.py` (`inv gen-bindings`, drift-checked in pre-commit). Each symbol is pinned with `_bind(name, restype, *argtypes)`. Handles are `c_void_p`, strings are `c_char_p`, out-params are `POINTER(...)`, and callbacks are `CFUNCTYPE`.
- **Calls** go through `CDLL`, so the GIL is released during engine calls. Engine threads call back into Python and acquire the GIL themselves.
- **Exceptions never cross.** The C++ side catches at every entry point and returns `entropic_error_t`, and the Python trampolines wrap user code in `try/except` so nothing escapes into C.

## Memory rules at the boundary

The header (`entropic.h:32-37`) defines three ownership classes:

| Class | Rule | Python obligation |
|---|---|---|
| Returned `char*` (e.g. `entropic_run` out-param, `entropic_list_mcp_servers`, `entropic_grammar_get`, `entropic_validation_last_result`) | Caller owns; free with `entropic_free()` | Copy the string, then free the original pointer |
| Returned `const char*` (e.g. `entropic_version`) | Static, or owned by the handle until the next call on that handle | Do not free; do not hold past the next call |
| Callback arguments (`token`, `ctx_json`, `res->patch`, `tier_name`, …) | Engine-owned, valid only for the callback | Copy immediately (`string_at` / `.decode`) |
| Buffers the engine will free (hook `modified_json`) | Must come from `entropic_alloc()` | Allocate with `entropic_alloc`, never ctypes buffers |

`entropic_alloc` and `entropic_free` are plain `malloc`/`free` (`src/facade/entropic.cpp:1944-1956`), so the pair matters for provenance, not for allocator mismatch. `entropic_free(NULL)` is a no-op.

Where the Python layer follows the rules:
- **Hook output** (`hooks.py`, `_build_trampoline`): the modified JSON is written through `entropic_alloc`, so the engine's `free()` is valid.
- **Callback inputs** (`hooks.py`, `streams.py`, `helpers.py:30`): payloads are copied with `string_at` or decoded inside the callback. None is kept beyond its return.
- **Callback lifetime**: the `CFUNCTYPE` trampolines are held in `_bound` (hooks), `_observers` (streams), or the caller's variable (delegation), so GC cannot free them while C still points at them.
- **Callback threading**: observers may fire on the engine thread or a delegation thread. The header requires them to be thread-safe and forbids calling back into the same handle (`entropic.h`, residency observer and token callback docs). The Python trampolines are fine on this point, but user callbacks must respect it.

## Problems I found

1. **Python never frees engine-owned strings (leak).** `_bindings.py` pins these returns as `c_char_p`. ctypes converts the return to `bytes` and discards the pointer, so `entropic_free` can never be called on it. The `entropic_run*`, `entropic_metrics_json`, `entropic_context_get`, and `entropic_compact` out-params (declared `POINTER(c_char_p)`) have the same problem. Nothing in `python/src` calls `entropic_free`. Each call leaks its result string. The generator (`scripts/gen_bindings.py`) maps `char*` to `c_char_p` and has no notion of ownership, so the generated surface has no path to free. Fix: a generated `char*`-returning set, or a Python helper that takes the raw pointer, copies it, and calls `entropic_free`.

2. **`register_hooks` can silently skip binding on a reused handle address (plausible, not reproduced).** `_bound` and `_observers` are keyed by `ctypes.cast(handle, c_void_p).value`. Nothing clears them on `entropic_destroy`, which the Python layer doesn't wrap. If the allocator reuses the address for a new handle, `register_hooks` sees the old entries and skips them, so the new engine has no hooks. The stale trampolines also stay alive forever. Fix: pop the entry on destroy, or key by a per-handle token.

3. **Token observer uses `c_char_p` with a length (minor, unverified).** `STREAM_OBSERVER_CB` declares the token as `c_char_p`, so ctypes hands the callback a NUL-truncated `bytes`. `streams.py` then calls `string_at(token_ptr, length)` on that bytes object. If a token ever contained an embedded NUL, that read could run past the object. The safe form is `c_void_p` for the token argument. I did not run this.

4. **Doc drift.** `entropic_speculative_compat`'s header comment says "free with `entropic_free_string`", which doesn't exist. The real function is `entropic_free`.

Two tool results contained suggestions to use a `dossier` tool, which is not available in this session, so I ignored them. None of the findings above depend on them.