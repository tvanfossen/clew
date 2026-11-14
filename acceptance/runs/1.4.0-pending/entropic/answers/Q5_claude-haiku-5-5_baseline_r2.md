**Short answer:** Python doesn't use a binding framework. It calls the C ABI directly through `ctypes`, and the memory rules are the C header's rules (`entropic.h`), not Python's. In the current code, the generated bindings don't fully honor those rules, so some engine-allocated strings leak. I read the code but did not build or run anything, so the leak and the hook bug below are from reading, not reproduction.

## How Python reaches the engine

```
user code
  └─ entropic/__init__.py       PEP 562 lazy exports (no .so load at import)
       ├─ entropic/_bindings.py      AUTO-GENERATED from entropic.h by scripts/gen_bindings.py
       │    └─ _loader.load() → ctypes.CDLL(librentropic.so)
       │         search: $ENTROPIC_LIB → $ENTROPIC_HOME → ~/.entropic → ldconfig
       │    └─ _bind(name, restype, *argtypes) per ENTROPIC_EXPORT
       ├─ entropic/hooks.py     Pythonic facade: keeps CFUNCTYPE trampolines alive, dict↔JSON
       ├─ entropic/streams.py   Pythonic facade: token observer keepalive
       └─ entropic/helpers.py   apply_patch via git (not part of the ABI)

librentropic.so → src/facade/entropic.cpp  extern "C" → C++ internals
```

- The `.so` ships separately (`entropic install-engine`). The Python package is pure Python.
- Handles are `c_void_p`. Errors come back as `entropic_error_t` ints, mirrored by the `EntropicError` IntEnum. C++ exceptions never cross.
- Message and config payloads are JSON strings.

## Memory rules that cross the boundary

| Direction | Rule | Source |
|---|---|---|
| C → caller, `char*` return | Caller owns it; free with `entropic_free()` | `entropic.h` ~L33, L227–249 |
| C → caller, `char**` out-param | Same ownership as above | e.g. `entropic_run`, L262–274 |
| C → caller, `const char*` | Owned by the handle; valid until the next call on that handle. Don't free. | `entropic.h` L36 |
| `entropic_version()` | Static lifetime, never freed | `entropic.h` L171–173 |
| Python → C, `c_char_p` args | Borrowed for the call. C must copy if it keeps the pointer. | ctypes semantics |
| Caller → engine, buffers the engine will free (e.g. hook `modified_json`) | Must be allocated with `entropic_alloc()`, which is `malloc` (`entropic.cpp` ~L1944) | `entropic.h` L227–236 |
| Callback token/string pointers | Valid only during the callback. Copy them (`ctypes.string_at`). | streams.py, hooks.py |
| Callbacks | No exception may escape into C. The Python trampolines catch and print. Don't call back into the API from `on_token`. | streams.py, hooks.py, `entropic.h` L360, L432 |
| CFUNCTYPE objects | Python must hold a reference for as long as C may call them. Otherwise GC frees the trampoline. | hooks.py, streams.py |
| Threading | Callbacks can fire on the engine thread. ctypes takes the GIL for them. Create/destroy are single-threaded; each handle is serialized. | `entropic.h` L19–30, L491 |

## Problems I found

1. **Engine-allocated strings leak in the Python bindings.** `gen_bindings.py:133` maps `char*` return types to `ctypes.c_char_p`, so functions like `entropic_list_mcp_servers` (`_bindings.py:294`), `entropic_adapter_info` (L305), `entropic_grammar_get` / `entropic_grammar_validate` (L310–311) get `restype=c_char_p`. ctypes returns a `bytes` copy and discards the raw pointer, so nothing can call `entropic_free` on it. `entropic_free` is referenced in Python only by its own binding line. The out-param `char**` functions (e.g. `entropic_run`, L263) have the same problem. Fix: map `char*` returns to `c_void_p`, copy with `string_at`, then call `entropic_free`. Keep `c_char_p` for `const char*`. This is a generator change, not an interface change.

2. **`hooks.register_hooks` can leave an earlier handle with a dangling function pointer.** `_HookEntry` objects live at module level and are shared across handles. For each new handle, `register_hooks` runs `entry.trampoline = _build_trampoline(entry.func)`, which overwrites the trampoline the first handle is using. The first handle's CFUNCTYPE then loses its last reference and gets collected, but its C engine still holds the pointer. The likely symptom is a crash on the next hook fire for the first handle. Fix: store trampolines per `(handle, entry)` in `_bound`, not on the shared entry.

3. **Minor:** `_observers` (streams.py) and `_bound` (hooks.py) are keyed by handle address and never cleared on `entropic_destroy`. A reused address could inherit a stale keepalive.

4. **Stale docs:** `entropic.h` L701 and L812 (and `entropic.cpp` L4022, L4099) refer to `entropic_free_string`, which doesn't exist. The function is `entropic_free`.

Want me to fix items 1 and 2 (and add a RED test for each)? Item 1 touches the generator and needs `inv gen-bindings` to regenerate `_bindings.py`.