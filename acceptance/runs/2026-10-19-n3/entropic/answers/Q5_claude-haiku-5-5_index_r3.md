Python reaches the engine through ctypes, with no C++ crossing the boundary. The memory rules are simple in the C header, but the Python binding breaks one of them: functions that return `char*` leak their result.

## Call path

```
user code
  └─ entropic/__init__.py      PEP 562 lazy __getattr__ (no .so load at import)
      └─ entropic/_bindings.py  generated from entropic.h by scripts/gen_bindings.py
          └─ _loader.py         dlopen-equivalent: ctypes.CDLL(librentropic.so)
              └─ src/facade/entropic.cpp   extern "C" facade, exceptions caught here
                  └─ C++ engine internals
```

- `_loader.find()` searches `$ENTROPIC_LIB`, then `$ENTROPIC_HOME`, then `~/.entropic/...`, then the ldconfig cache.
- `_bindings.py` is auto-generated and marked "do not edit". Each function is pinned with `_bind(name, restype, *argtypes)`, so `ctypes` knows the signature.
- Callbacks are `CFUNCTYPE` typedefs (`HOOK_CB`, `TOKEN_CB`, `STREAM_OBSERVER_CB`, …).
- There is no OOP wrapper. `docs/getting-started.md` says the Python surface is the C ABI verbatim.
- The `hooks.py` and `streams.py` modules add convenience. They hold the trampolines alive and do the marshalling.

## Memory rules

The rules are stated in `include/entropic/entropic.h` (lines 30–38, 171, 236–250):

| Direction | Rule | What Python does |
|---|---|---|
| Engine returns `char*` | Caller owns it; free with `entropic_free()` | **Does not free.** See below. |
| Engine returns `const char*` | Owned by the handle, valid until the next call on that handle | Not freed by caller. `entropic_version()` is static and must not be freed. |
| Caller passes buffers the engine will free (hook `modified_json`) | Must be allocated with `entropic_alloc()` | `hooks.py` does this correctly. |
| Callbacks receive pointers | Valid only for the callback's duration | Copied out with `ctypes.string_at(...)` before returning. |
| Exceptions | Must never cross the `.so` boundary; use error codes and callbacks | Trampolines catch and log (`hooks.py`, `streams.py`); a hook exception passes through as rc=0. |
| Function pointers | Python must keep the CFUNCTYPE wrapper referenced while C can call it | `hooks.py` keeps a per-handle list; `streams.py` keeps a dict keyed by handle; `helpers.py` docs say to hold the wrapper yourself. |

`entropic_alloc` is `malloc` and `entropic_free` is `free` (`src/facade/entropic.cpp:1944–1956`). The paired-allocator rule matters for portability across CRTs more than for correctness today.

## Defect: `char*` returns leak from Python

`_bindings.py` pins some functions as `ctypes.c_char_p` restype. The header says these return caller-owned `char*`, for example `entropic_list_mcp_servers` (header line 1281), `entropic_adapter_info` (1509), `entropic_grammar_get` (1600), `entropic_profile_get` (1690), `entropic_list_identities` (2043), `entropic_validation_last_result` (2338), and others.

- With `c_char_p` restype, ctypes copies the bytes into a Python `bytes` object and discards the raw pointer.
- The only `entropic_free` binding is never called anywhere under `python/src`. `helpers.py` and `cli.py` never free.
- Result: every such call leaks the engine's heap allocation.
- `entropic_run` and the other out-param functions (`POINTER(c_char_p)`) have the same hazard. The raw pointer is recoverable via `ctypes.cast(out, c_void_p).value` before reading `.value`, but nothing in the wrapper or the getting-started docs does this.

The fix would be to bind caller-owned returns as `c_void_p`, read them with `ctypes.string_at`, and call `entropic_free` on the raw pointer. The generator (`scripts/gen_bindings.py`) maps `char*` to `c_char_p` (lines 132–134), so the fix belongs there, followed by `inv gen-bindings`. I have not run tests or confirmed the leak with a live engine. This finding comes from reading the code.

## Minor notes

- `.claude/CLAUDE.md` says the wrapper lives in `python/entropic_native/`. That directory holds only `py.typed`; the real package is `python/src/entropic/`.
- `_bindings.py` and `_bindings_manifest.py` are generated and checked by pre-commit. Edits belong in `gen_bindings.py`, not the output.