**How Python reaches the engine**

The Python package does not embed or compile the engine. It is a pure-Python `ctypes` shim over the shared library `librentropic.so`, with no pybind or cffi. The docs describe it as "a thin ctypes binding over the C ABI, no OOP wrapper" (README.md, Python Wrapper section). The package is about 50 KB, plus a CLI.

```
Python (entropic package)                 native (librentropic.so)
─────────────────────────                 ─────────────────────────
_loader.py    find + dlopen the .so  ───▶ C ABI: include/entropic/entropic.h
_bindings.py  ctypes fns, enums,         (pure C, opaque handles,
              structs, CFUNCTYPE         ENTROPIC_EXPORT symbols)
              (generated from the header
               by scripts/gen_bindings.py)
hooks.py      Python callables wrapped ◀── engine calls back via HOOK_CB
              as CFUNCTYPE trampolines
```

- `_loader.py` resolves the library. Its docs list several lookup paths, ending with `ctypes.util.find_library("rentropic")`.
- `_bindings.py` is auto-generated from the C header. Each symbol is bound through `_bind()`, which pins `restype` and `argtypes` on the loaded `.so` function.
- `hooks.py` builds `CFUNCTYPE` trampolines so Python hook callables can be invoked from the C engine.
- The C side (`src/facade/entropic.cpp`) implements the facade. `entropic_create` allocates an engine handle with `new` and returns it as an opaque pointer.

**Memory rules that cross the boundary**

1. **Strings returned by the engine are caller-owned.** Per the `entropic.h` file docs, functions returning `char*` transfer ownership to the caller, who frees them with `entropic_free()`. `entropic_free` is a thin wrapper over `free()` and is a no-op on NULL. The same rule appears in `i_mcp_server.h`: strings from `list_tools` and `execute` are caller-owned.

2. **Memory the engine will free must come from `entropic_alloc()`.** The header says consumer-provided buffers that the engine frees must be allocated with `entropic_alloc()`, which wraps `malloc()`. Internally, `alloc_cstr` uses it so that the result can be released with `entropic_free`.

3. **Python follows rule 2 for hook output.** `_build_trampoline` JSON-encodes the hook's return value, copies it into an `entropic_alloc` buffer, and writes the pointer to `*modified_json`. The engine then frees it. `_alloc_c_string` follows the same pattern, and its docstring warns that no Python reference may outlive that free.

4. **Callee-allocated results.** `i_inference_callbacks.h` and `i_inference_backend.h` say the backend allocates `result_json`, and the caller frees it with the callee's free function (for example `entropic_inference_free`).

5. **Python callbacks must be kept alive.** `hooks.py` states that a `CFUNCTYPE`-wrapped callable must be referenced from Python for as long as the engine might invoke it. If it is garbage-collected while registered, the C side holds a dangling function pointer.

6. **C++ exceptions never cross the `.so` boundary.** The design rule, repeated across `architecture-cpp.md`, `error.h`, and the prompt files, is that errors cross as `entropic_error_t` return codes plus callbacks. The trampoline enforces this on the Python side: it catches every exception, prints the traceback, and returns 0 (pass-through), so nothing unwinds into C.

**Caveats**

- These rules are conventions documented in headers. The index shows no type-level enforcement. The Python code's compliance at every call site is not verified here.
- The trampoline's blanket `except Exception` with `traceback.print_exc()` conflicts with the repo's logging standard, which asks for full-context logging. Its own comment says "Future: pluggable logger." The fix is worth tracking.
- `OLD_NOTES.md` records an exception escaping `entropic_configure_dir`, which violated the no-exceptions rule. It was fixed in v2.3.13.
- I did not read `_loader.py` or the full `entropic.h` header. The above is from indexed docs and symbol bodies, not the complete source.