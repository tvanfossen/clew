## How Python reaches the engine

Python never links against the C++ code. It loads the shared library at runtime with `ctypes`, and every call crosses the C ABI in `include/entropic/entropic.h`.

```
Python app
  │  import entropic
  ▼
entropic/streams.py, hooks.py, helpers.py   ← hand-written facades: lifetime + marshalling
  ▼
entropic/_bindings.py                        ← generated from entropic.h by scripts/gen_bindings.py
  │  restype/argtypes pinned per symbol, CFUNCTYPE typedefs, enums/structs mirrored
  ▼
entropic/_loader.py  ctypes.CDLL(librentropic.so)
  ▼  ── C ABI boundary (pure C, opaque handles, no C++ exceptions) ──
librentropic.so → C++ engine (core/, inference/, mcp/ ...)
```

- **Loading** (`python/src/entropic/_loader.py`): resolves the `.so` from `$ENTROPIC_LIB`, then `$ENTROPIC_HOME` (nested and flat layouts), then `~/.entropic/`, then `ctypes.util.find_library`. It is loaded with `ctypes.CDLL`, which releases the GIL during every foreign call.
- **Bindings** (`_bindings.py`): auto-generated and marked "do not edit". Pre-commit runs `gen-bindings --check`, so the file cannot drift from the header. Each symbol is bound via `_bind(name, restype, *argtypes)`.
- **Facades**: nothing in `python/src` wraps `entropic_run` or similar. Consumers call the raw symbols, or the facades for observers, hooks, and patches. The facades exist to handle lifetime and JSON marshalling.
- The binding layer is `ctypes` only, with no pybind11 or cffi.

## Memory rules at the boundary

The rules are stated in `entropic.h:32-37` and `:241-249`. Python must follow them by hand.

| Direction | Rule | Python obligation |
|---|---|---|
| Engine → caller, `char*` return or out-param | Caller owns it. Free with `entropic_free()`. | Copy the bytes out first (`string_at` / `.value`), then free. Tests use `if (out) entropic_free(out)`. |
| Engine → caller, `const char*` (e.g. handle-owned strings) | Owned by the handle, valid until the next call on that handle. | Copy immediately. Do not free. |
| `entropic_version()` | Static, never free. | None. |
| Buffers the engine will free (hook `modified_json`) | Must come from `entropic_alloc()`, not `malloc` or Python's allocator. | `hooks.py` does this through `entropic_alloc` + `memmove`. |
| Callback-scoped structs (`EntDelegationRequest/Result`, patch text) | Engine-owned, valid only during the callback. | Copy inside the callback (`helpers.py` uses `string_at`). Do not keep the pointer. |
| Opaque `entropic_handle_t` | `void*` owned by the engine. | Do not free. Destroy via `entropic_destroy`, never concurrently with other calls on that handle. |

**Callback lifetime.** A `CFUNCTYPE` wrapper is a live object, and if Python drops it the engine calls freed memory. The facades therefore keep strong references:
- `streams.py:44` holds `_observers`, keyed by handle address, with a `# keepalive` comment.
- `hooks.py` holds `_HookEntry.trampoline` and a per-handle `_bound` list.

Both registries are keyed by handle address and never cleared on `entropic_destroy`. Entries are only replaced when a new registration reuses that key. That is a small retention gap, not a crash, and I did not find code that clears them.

**Exceptions must not cross into C.** Both trampolines catch everything, print a traceback, and return a neutral code (`rc = 0` for hooks).

**Threads.** Per `entropic.h`, observer and delegation callbacks may fire on the engine thread or a child-loop thread. ctypes re-acquires the GIL for them, so Python observers must be thread-safe. Callbacks must not call back into the API on the same handle.

## Caveats

- I did not verify whether the engine copies input `c_char_p` arguments or retains the pointer. The Python side must keep input buffers alive for the duration of each call, but the header does not settle the retention question for every entry point.
- I read the code and headers only and did not build or run anything, so the claims about runtime behaviour are inferred from the source.