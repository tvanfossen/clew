**How Python reaches the engine:** through `ctypes`, with no C++ crossing the boundary.

```
Python code (entropic package)
   │  ctypes.CDLL → librentropic.so
   ▼
_bindings.py  (auto-generated from include/entropic/entropic.h by scripts/gen_bindings.py)
   │  C ABI: entropic_create / entropic_run_streaming / entropic_destroy ...
   ▼
src/facade/entropic.cpp  (extern "C" functions, exceptions caught here)
   │
   ▼
C++ engine internals
```

- The README and `docs/getting-started.md` describe the wrapper as "a thin pure-Python ctypes binding over the C ABI, no OOP wrapper."
- `_bindings.py` is generated, and the `_bind` helper pins `restype`/`argtypes` on each symbol. Enums and structs are mirrored from the headers.
- `_loader.py` finds `librentropic.so`, with a fallback to the system `ldconfig` cache.
- `hooks.py` and `helpers.py` are hand-written conveniences on top of the generated bindings. They are not part of the C ABI.
- The C side enforces the rules in `docs/architecture-cpp.md`: pure C at every `.so` boundary, opaque handles, and exceptions never crossing the boundary. Errors come back as `entropic_error_t` codes, and `entropic_last_error(handle)` gives the message.

**Memory rules that cross the boundary:**

| Direction | Rule | Source |
|---|---|---|
| Engine → caller (`char*` return) | Ownership transfers to the caller. Free with `entropic_free()`. | `entropic.h` file docs |
| Engine → caller, `entropic_last_error` | Owned by the handle, valid until the next API call on that handle. Do not free. | `entropic_last_error` doc |
| Caller → engine (hook `modified_json`, strings the engine will free) | Must be allocated with `entropic_alloc()`, which wraps `malloc`. The engine releases it with `free`. | `entropic_alloc` doc |
| `entropic_free` | Wraps `free()`. NULL is a no-op. | `src/facade/entropic.cpp:1954` |
| Free of logprob results | `entropic_free_logprob_result` frees the arrays and NULLs them. The struct itself stays caller-owned. | `entropic_free_logprob_result` doc |
| Streaming tokens | The token pointer is valid only for the duration of the callback. Copy it if you keep it. The callback must not re-enter the API (deadlock risk). | `entropic_run_streaming` doc |
| Interface headers (`i_*.h`) | Strings returned by inference backends and MCP plugins are allocated by the callee, with a matching free function. | file docs for `i_inference_backend.h` and `i_mcp_server.h` |

**Python-specific application:** `hooks.py::_alloc_c_string` copies a Python `str` into an `entropic_alloc` buffer as NUL-terminated UTF-8, so the engine can `free()` it after consuming. Its docstring warns that the caller must make sure no Python reference outlives that free. The facade's `entropic_register_hook` returns `ENTROPIC_ERROR_INVALID_ARGUMENT` on a NULL callback, and the `hooks.py` docstring flags callback lifetime as a foot-gun, which I could not read in full from the index.

**Gaps:** The index returned only snippets for the Python files and some interface-header memory notes, so I could not read the full `hooks.py` lifetime warning or the complete ownership text in `i_inference_backend.h`. Those would need a source read to confirm. Also, the index does not show whether the Python side keeps `ctypes` callback objects alive. Check that in `hooks.py` before relying on it.