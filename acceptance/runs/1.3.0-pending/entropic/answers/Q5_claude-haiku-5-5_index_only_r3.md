## How Python reaches the engine

Python never links against C++. The path is a flat C ABI loaded at runtime:

```
Python caller (entropic.create / run / register_hooks ...)
  │  facades: hooks.py, streams.py, mcp.py (kwargs/dict ↔ JSON, lifetime keepalives)
  ▼
_bindings.py   ctypes prototypes + CFUNCTYPE typedefs (auto-generated from entropic.h, "do not edit")
  ▼  ctypes.CDLL-style load of librentropic.so; _loader.py resolves the path
     ($ENTROPIC_LIB → $ENTROPIC_HOME → ~/.entropic → ldconfig)
librentropic.so  src/facade/entropic.cpp   ← pure-C functions, opaque entropic_handle_t
  ▼
C++ engine (AgentEngine, hook registry, inference backend)
```

- `entropic.h` is the only public surface. It is pure C, and no C++ types cross it.
- The Python package has no `EntropicEngine` class. It exposes the C symbols directly (`entropic_create`, `entropic_run_streaming`, `entropic_destroy`, ...), plus thin "Pythonic" wrappers in `hooks.py`, `streams.py`, and `mcp.py`.
- Imports are lazy (PEP 562), so `entropic install-engine` can run before the `.so` exists.
- Plugin `.so` files (MCP servers, inference backends) cross the same kind of boundary through their own C interfaces (`i_mcp_server.h`, `i_inference_backend.h`).

## Memory rules at the boundary

These are the documented rules from `entropic.h` and the interface headers:

| Direction | Rule | Who frees |
|---|---|---|
| Engine → caller, `char*` out-params (e.g. `entropic_run` `result_json`) | Newly allocated, caller owns | Caller, with `entropic_free()` |
| Caller → engine, buffers the engine will free (e.g. hook `modified_json`) | Must be allocated with `entropic_alloc()`, not `malloc` or Python memory | Engine, with `entropic_free()` |
| Engine → caller, `const char*` (e.g. `entropic_last_error`) | Owned by the handle, do not free, valid until the next call on that handle | Engine |
| Input strings (`input`, `messages_json`, `params_json`, `prompt`) | Borrowed for the duration of the call only | Caller |
| Token pointers in stream callbacks | Valid only inside the callback; copy to keep | Engine |
| Plugin returns (MCP `list_tools`/`execute`, backend `result_json`) | Caller-owned, freed via the plugin's free function (`entropic_free` for MCP, `entropic_inference_free` for backends) | Caller |
| Plugin `name` strings | Owned by the server for the handle's lifetime | Plugin |

`entropic_free` and `entropic_alloc` are simply `free` and `malloc` in `src/facade/entropic.cpp`. The pairing rule therefore matters because it guarantees the engine's free sees a pointer from the same allocator.

Two things are easy to get wrong:

- **Partial results on failure.** When `entropic_run` throws, it still returns `ENTROPIC_ERROR_GENERATE_FAILED` with a serialized partial `result_json`. Callers must free that buffer even on error.
- **Ownership of `entropic_last_error`.** The header says the pointer is handle-owned, so don't free it.

## Lifetime and threading rules

- **Python callbacks must be kept alive.** A `CFUNCTYPE` wrapper that Python drops while C still holds its pointer leads to use-after-free. `hooks.py` keeps a per-handle registry of wrappers. `streams.py` stores its callback in a module-level `_observers` dict keyed by the handle address, which is the keepalive.
- **Exceptions never cross into C.** The stream trampoline catches exceptions and prints them to stderr. The C++ side reports errors through error codes plus callbacks, not C++ exceptions.
- **Handle thread-safety classes** (from `entropic.h`):
  - Thread-safe: callable any time.
  - Serialized per handle: one call at a time per handle; separate handles are independent.
  - Init/destroy: must not race with any other call on the same handle.
- `entropic_destroy` invalidates the handle and is NULL-safe.
- Stream observers can fire from the engine thread and from the external-bridge worker thread, so Python token callbacks must be thread-safe.
- `entropic_set_stream_observer` also fires a synthetic `("", 0)` sentinel at the end of each non-streaming run.

## Discrepancy to check

The `entropic_last_error` doc comment says it returns a *thread-local* cache copy. The body copies into `s_last_error_cache`, which looks like a process-wide static, not a thread-local. The "valid until the next call" guarantee therefore may not hold across threads. I could not verify this beyond the indexed body, so it is worth reading the source directly.