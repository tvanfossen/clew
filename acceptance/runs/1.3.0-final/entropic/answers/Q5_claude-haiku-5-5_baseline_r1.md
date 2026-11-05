**How Python reaches the engine:** plain ctypes, no C++ extension and no pybind. The wheel is pure Python and loads `librentropic.so` at runtime.

```
Python code
  └─ entropic/__init__.py      PEP 562 lazy exports (manifest-driven)
      └─ entropic/_bindings.py  auto-generated ctypes shim
          └─ _loader.load()     ctypes.CDLL(librentropic.so)
              └─ include/entropic/entropic.h   extern "C" ENTROPIC_EXPORT ABI
                  └─ C++ engine internals
```

- **Library discovery** (`python/src/entropic/_loader.py`): checks `$ENTROPIC_LIB`, then `$ENTROPIC_HOME` in nested and flat layouts, then `~/.entropic/...`, then `ctypes.util.find_library`. The `.so` is fetched by `entropic install-engine`.
- **Bindings are generated.** `scripts/gen_bindings.py` parses `include/entropic/entropic.h` and `types/*.h` and emits `_bindings.py` and `_bindings_manifest.py`. The pre-commit `--check` fails on drift. The generator maps `char*` and `const char*` to `c_char_p`, `char**` to `POINTER(c_char_p)`, and function-pointer params to `CFUNCTYPE` typedefs. Enums become `IntEnum`s and structs become `ctypes.Structure`s.
- **Handles** are `c_void_p`. Out-params use `byref`.
- **Python-side ergonomics** are in `hooks.py` (decorator registry plus dict↔JSON marshalling), `streams.py` (token observer), and `mcp.py` and `helpers.py`.

**Memory rules that cross the boundary.** The header states them in its "Memory ownership" block (`entropic.h` around lines 32–36):

| Direction | Rule | Who frees |
|---|---|---|
| Engine returns `char*` (e.g. `entropic_run` result, `entropic_list_*`, `entropic_metrics_json`) | Ownership transfers to the caller | Caller, with `entropic_free()` |
| Engine returns `const char*` (e.g. `entropic_last_error`, `entropic_version`) | Owned by the engine or handle, valid until the next call | Nobody. Do not free |
| Caller gives the engine a buffer the engine will free (hook `*modified_json`) | Must be allocated with `entropic_alloc()` | Engine, with `entropic_free()` |
| Callback args (hook `context_json`, `TOKEN_CB` token, delegation request/result) | Engine-owned, valid only for the callback | Engine. Copy if you keep it |
| Handle | Created by `entropic_create`, destroyed by `entropic_destroy` | Caller |

The allocator must match. Use `entropic_alloc`/`entropic_free`, not Python or libc allocators, for anything that crosses in either direction.

**How Python honors these rules:**
- **Engine-owned callback data** is copied immediately with `ctypes.string_at(ptr, len)` in `streams.py` and `hooks.py`.
- **Hook return values**: `hooks.py` `_build_trampoline` JSON-encodes the result, copies it into `entropic_alloc` memory, and writes it to `*modified_json`. The engine frees it.
- **Exceptions never cross into C.** Trampolines catch everything, print a traceback, and return 0 (pass-through).
- **CFUNCTYPE lifetime**: wrappers are held in module-level dicts keyed by handle (`hooks._bound`, `streams._observers`). Otherwise the GC reaps them and the engine calls freed memory.

**The gap I found:** the Python layer does not free engine-allocated strings.
- No Python code in `python/`, `tests/` or `scripts/` calls `entropic_free`. The only `entropic_alloc` use is the hook trampoline.
- Functions whose restype is `c_char_p` (e.g. `entropic_list_mcp_servers`, `entropic_adapter_list`, `entropic_grammar_list`) return a Python `bytes` copy. ctypes discards the original pointer, so it can never be passed to `entropic_free`. Every call leaks.
- `char**` out-params (`entropic_run`, `entropic_context_get`, `entropic_metrics_json`, etc.) are `POINTER(c_char_p)`. Reading `.value` copies and drops the pointer. Unless the caller keeps the raw pointer and calls `entropic_free` on it, the result leaks.
- `_alloc_c_string` in `hooks.py` is dead code. The trampoline inlines the same logic.

This is from reading the code and ctypes semantics. I did not run a leak check. To confirm, run `entropic_run` in a loop under a leak tracker, or add a test that asserts every `char*`-returning binding has a wrapper that frees. The fix is to stop using `c_char_p` restype for owned strings (use `c_void_p`, copy with `string_at`, then `entropic_free`) and have the generator emit that. The generator is also where the ownership convention should be encoded, since the header already documents it per function.