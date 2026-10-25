## How Python reaches the engine

Python does not have a native extension. It loads the C shared library with `ctypes`:

```
Python code
  └─ entropic/_bindings.py     flat ctypes shims, one per C symbol (auto-generated)
       └─ ctypes.CDLL(librentropic.so)     found by entropic/_loader.py
            └─ src/facade/entropic.cpp     extern "C" entropic_* functions
                 └─ C++ engine (exceptions caught here, turned into error codes)
```

- `_loader.py` resolves the `.so` in order: `$ENTROPIC_LIB`, then `$ENTROPIC_HOME`, then `~/.entropic/...`, then `ctypes.util.find_library`.
- `_bindings.py` is generated from `include/entropic/entropic.h` by `scripts/gen_bindings.py`. Each line pins `restype` and `argtypes`, e.g. `entropic_create = _bind("entropic_create", c_int, POINTER(c_void_p))`. The handle is `c_void_p`, so Python treats it as opaque.
- `__init__.py` exposes these symbols lazily (PEP 562) so `install-engine` can run before the `.so` exists. There is no `EntropicEngine` class.
- The Python-side helpers are thin: `hooks.py` (decorator plus trampoline), `streams.py` (token observer), `mcp.py` (JSON marshalling), and `helpers.py` (`apply_patch`).

## Memory rules at the boundary

The header states these rules at `entropic.h:32-37`, and the implementations confirm them. `entropic_alloc` and `entropic_free` are plain `malloc` and `free` (`src/facade/entropic.cpp:1944-1956`).

| Direction | Rule | Where it applies |
|---|---|---|
| Engine returns `char*` | Caller owns it and must call `entropic_free()` | `entropic_run*`, `entropic_context_get`, `entropic_grammar_get`, `entropic_list_mcp_servers`, `entropic_metrics_json` |
| Engine returns `const char*` | Handle owns it, valid until the next call on that handle. Do not free | `entropic_validation_last_result`, `entropic_version` (static lifetime) |
| Caller passes a buffer the engine will free | Must be allocated with `entropic_alloc()`, not Python's allocator | Hook `modified_json` |
| Callback-scoped pointers | Valid only for the callback. Copy before returning | Token `(ptr, len)`, `ent_delegation_result_t` (`patch`, `files_touched`), residency `tier_name` and `model_path` |
| Python callbacks handed to C | The `CFUNCTYPE` wrapper must be kept referenced for the handle's lifetime, or C calls freed memory | `hooks.py` `_bound` registry, `streams.py` `_observers`, and the `helpers.py` example |
| Exceptions | Never cross the `.so` boundary. Caught in the facade, returned as `entropic_error_t`, detail in `handle->last_error` | Every `entropic_*` function |
| Re-entrancy | Callbacks must not call back into the API on the same handle | Stated for token and residency callbacks |

On the Python side, the existing code follows the rules where it matters. `hooks.py` writes `modified_json` with `entropic_alloc`, so the engine's `free()` is valid. `streams.py` and `helpers.py` copy callback-scoped data with `ctypes.string_at(ptr, len)`. Callback trampolines catch Python exceptions so nothing escapes into C.

## Gaps I found

1. **Returned `char*` strings leak through the Python bindings.** `_bindings.py` declares many functions documented as "caller frees" with `c_char_p` restype, e.g. `entropic_list_mcp_servers` (line 294), `entropic_grammar_get` (310), `entropic_profile_get` (315), `entropic_list_mcp_keys` (322), `entropic_get_identity_config` (332) and `entropic_list_identities` (333). ctypes converts the return to `bytes` and discards the raw pointer, so `entropic_free` can never be called on it. My reading is that the generator maps `char*` to `c_char_p` without ownership information. I did not confirm this in `gen_bindings.py`.
2. **Out-param strings are also never freed in the package.** `entropic_run`, `entropic_context_get` and similar take `POINTER(c_char_p)`. Nothing in `python/src` calls `entropic_free`. A caller must read the raw pointer before `.value` converts it, then free it. The package gives no helper for this.
3. **Doc drift.** `entropic.h` (lines 701 and 812) and `entropic.cpp` (4022, 4099) say to free with `entropic_free_string`, which does not exist. The real function is `entropic_free`.
4. **Dead code.** `hooks.py:_alloc_c_string` has no callers. The trampoline inlines the same logic.
5. **Stale docstring.** The `hooks.py` module docstring uses `entropic.create()`, `entropic.configure()` and `entropic.run()`. None of those are exported; `__getattr__` would raise `AttributeError`. Only the raw `entropic_*` names are exported.

I did not run the Python test suite or check how the existing tests exercise these paths. Item 1 is the most important, because it is a silent leak on every affected call. It is also the first thing to confirm in `scripts/gen_bindings.py`.