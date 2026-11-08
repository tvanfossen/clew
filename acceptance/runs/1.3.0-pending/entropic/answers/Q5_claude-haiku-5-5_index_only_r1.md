**Short answer:** Python never touches C++ objects. It loads `librentropic.so` with `ctypes`, calls flat `extern "C"` functions on opaque handles, and receives callbacks back through `CFUNCTYPE` trampolines. Memory is handled by convention: the engine's `malloc`/`free` pair is the only allocator that crosses the boundary.

## How Python reaches the engine

```
Python (entropic.*)
  │  _loader.find()        picks librentropic.so (ENTROPIC_LIB → ENTROPIC_HOME →
  │                        ~/.entropic → ldconfig)
  ▼
  _bindings.py             generated from include/entropic/entropic.h by
  │                        scripts/gen_bindings.py; each symbol pinned via
  │                        _bind(name, restype, *argtypes)
  ▼
librentropic.so  ──  src/facade/entropic.cpp  (extern "C" facade)
  │                  C++ internals (AgentEngine, orchestrator) stay behind it
  ▼
Engine
```

- **Forward calls:** `entropic_create`, `entropic_configure`, `entropic_run`, and so on are plain C calls through `ctypes`. Handles are opaque.
- **Reverse calls:** hooks and delegation or attempt-boundary callbacks are `CFUNCTYPE` objects handed to `entropic_register_hook`, `entropic_set_delegation_callbacks`, and similar. `hooks.py` converts `context_json` to a dict and back, and keeps a per-handle registry so the trampolines are not garbage-collected.
- **Lazy loading:** `entropic/__init__.py` imports binding symbols lazily (PEP 562), so `entropic install-engine` can run before the `.so` exists.
- **Pure C at the boundary:** no C++ types or exceptions cross it (design rule 1 and 6 in `docs/architecture-cpp.md`).

## Memory rules across the boundary

| Direction | Rule | Source |
|---|---|---|
| Engine returns `char*` | Caller owns it and must free with `entropic_free()`. Example: `entropic_run` writes a `result_json` the caller frees. | `entropic.h` memory-ownership section |
| Engine returns `const char*` (e.g. `entropic_last_error`) | Owned by the handle, valid until the next call on that handle. Do **not** free. | `entropic_last_error` doc |
| Python gives the engine a buffer it will free (hook `modified_json`) | Must be allocated with `entropic_alloc()`, which is `malloc`. `hooks._alloc_c_string` and the trampoline do this. Using a Python or `ctypes` buffer here would be a free of the wrong provenance. | `entropic_alloc` doc, `_build_trampoline` |
| `entropic_free(NULL)` | No-op. `entropic_free_logprob_result` NULLs its pointers after freeing; the struct itself stays caller-owned. | `entropic_free` and `entropic_free_logprob_result` docs |
| Exceptions | Never cross. The hook trampoline catches every `Exception`, prints the traceback, and returns 0 (pass-through). | `_build_trampoline` body |
| Callback lifetime | A `CFUNCTYPE` wrapper must be kept referenced for as long as the engine may call it, or it dereferences freed memory. | `hooks.py` file doc, `helpers.py` example |
| Callback return values | Must be plain ints, not `IntEnum` members. | `helpers.py` example comment |
| Structs and buffers with length | Read with `ctypes.string_at(ptr, len)` using the explicit length (e.g. `patch`/`patch_len`), not NUL termination. | `helpers.py` example |
| Handle-owned state | Sharing a handle is serialized per handle; `entropic_interrupt` is callable from another thread. | `entropic.h` file doc, `entropic_run` doc |

## Caveats

- Everything above comes from the index: doc blocks, the function bodies I read, and file docs. I did not read the Python call sites that pass input strings into `entropic_run`, so I can't confirm how input lifetime is handled on that path.
- The hook trampoline swallowing exceptions means a buggy Python hook fails silently except for the stderr traceback. That's a design choice worth knowing about.
- The Python layer is not a full wrapper: the README and `docs/dist-README.md` describe it as a thin `ctypes` shim with no OOP layer, so the C ABI is the public surface.