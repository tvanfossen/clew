**How Python reaches the engine**

It is a flat `ctypes` binding over a C ABI. There is no C++ crossing and no pybind11.

1. `_loader.py` finds `librentropic.so` (via `$ENTROPIC_LIB`, `$ENTROPIC_HOME`, `~/.entropic/...`, then ldconfig) and opens it with `ctypes.CDLL`.
2. `_bindings.py` is generated. Each `ENTROPIC_EXPORT` in `include/entropic/entropic.h` becomes a `_bind(name, restype, *argtypes)` call that pins `restype` and `argtypes` on the symbol. Handles are `ctypes.c_void_p`. Structs such as `EntDelegationResult` are `ctypes.Structure`s, and callbacks are `CFUNCTYPE`s such as `HOOK_CB` and `TOKEN_CB`.
3. `__init__.py` exposes these lazily (PEP 562) from `_bindings_manifest.py`. There is no `EntropicEngine` class. The only wrappers are thin facades: `hooks.py` (`@hook`, `register_hooks`), `streams.py` (`register_token_observer`), `mcp.py`, and `helpers.py`.

**Memory rules at the boundary**

These come from the header's "Memory ownership" block (`entropic.h` ~L32–37) and the `alloc`/`free` implementations.

| Direction | Rule | Mechanism |
|---|---|---|
| Engine → caller, `char*` out-param | Caller owns it and must free it with `entropic_free()` | `entropic_run(h, p, byref(out))` then `entropic_free(out)` |
| Engine → caller, `const char*` return | Owned by the handle, valid only until the next call on that handle | Copy it immediately (`.value` or `string_at`) |
| Caller → engine, buffer the engine will free | Must be allocated with `entropic_alloc()`, never with Python's allocator | `hooks.py` `modified_json` path |
| Engine → Python callback args (`token_ptr`, `context_json`, `res.patch`) | Engine-owned and valid only for the callback's duration | Copy with `ctypes.string_at(...)` before returning (`streams.py`, `hooks.py`, `helpers.py`) |
| Static strings (`entropic_version`) | Never freed | Do not call `entropic_free` on them |

Under the hood, `entropic_alloc` and `entropic_free` are plain `malloc` and `free` (`src/facade/entropic.cpp` ~L1944–1956). The separate function exists so the contract holds if the allocator changes, not because the allocators differ today.

**Other rules**

- **Ctypes callbacks must be kept alive.** A `CFUNCTYPE` wrapper that Python garbage-collects leaves C calling freed memory. `streams.py` stores the wrapper in `_observers[handle]`, and `hooks.py` keeps trampolines in `_bound[handle]`.
- **Exceptions never cross.** Python callbacks catch everything and print a traceback. Failures are reported as `entropic_error_t` codes, and the engine's error text is read via `entropic_last_error(handle)`.
- **The Python package does not free out-params for you.** Its bindings are raw, so any Python code that takes a `char*` out-param must call `entropic_free` itself. I found no such call in `python/src/entropic` outside the tests. The C tests do this consistently (`tests/unit/api/facade_integration_test.cpp`).

**Problems I found while reading**

1. **`hooks.py` trampoline returns 1 even when allocation fails.** If `entropic_alloc` returns NULL, `mod_out_ptr` is left unset but `rc` is still 1. The engine then reads "transform" with no payload. Only `rc = 1` should be set on success.
2. **Handle-keyed Python state is never cleared on destroy.** `entropic_destroy` does not touch `_bound`, `_observers`, or the hook registry. Two effects:
   - Memory grows for each destroyed handle.
   - Plausible but unverified: if the allocator reuses a destroyed handle's address, `register_hooks` sees the stale entries in `_bound[addr]` and skips binding the new handle's hooks. I did not run this to confirm.
3. **`hooks._alloc_c_string` is dead code.** The trampoline repeats its logic inline. Per the repo's DRY rule, the trampoline should call the helper.

I did not build or run any tests. The findings above come from reading the code.

*Note: a PostToolUse hook attached to one of my shell reads suggested using `dossier` for the `entropic.cpp` lookup. I ignored it, since the findings above come from reading the code directly.*