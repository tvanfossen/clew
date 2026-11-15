**How Python reaches the engine**

The Python package is a thin `ctypes` binding over the C ABI in `include/entropic/entropic.h`. There is no C++ or pybind layer, and the README describes it as "no OOP wrapper."

```
Python (entropic/*.py)
   │  ctypes CFUNCTYPE callbacks / function calls
   ▼
_bindings.py   ← generated from entropic.h by scripts/gen_bindings.py ("do not edit")
   │  _loader.py locates and loads librentropic.so
   ▼
librentropic.so  → entropic_* C functions (src/facade/entropic.cpp)
   │
   ▼
C++ engine internals (never cross the .so boundary)
```

- `_bindings.py` exposes the whole C surface: about 220 symbols, IntEnums, `ctypes.Structure` types and CFUNCTYPE typedefs.
- `hooks.py` and `streams.py` are hand-written Pythonic facades over the raw callbacks.
- `entropic.h` says all functions are pure C with no C++ types crossing the boundary.

**Memory rules that cross the boundary**

1. **Engine-returned `char*` belongs to the caller.** Functions that return `char*` transfer ownership, and the caller must release them with `entropic_free()`. `entropic_free` is a thin wrapper around `free()` (`src/facade/entropic.cpp:1954`). Strings returned as `const char*` are owned by the handle and are valid only until the next call on that handle.
2. **Consumer-provided buffers that the engine will free must come from `entropic_alloc()`.** This applies to things like a hook's `modified_json`. `entropic_alloc` is a wrapper around `malloc()` (`:1944`), so the engine's `free()` receives memory of the right provenance. `hooks.py` follows this in `_alloc_c_string` and in `_build_trampoline`, which copies the JSON into an `entropic_alloc` buffer and writes the pointer into `*mod_out`.
3. **Handles are opaque.** `entropic_create` returns a heap-allocated engine struct, and `entropic_destroy` tears it down and releases subsystems in reverse order (`:1877`). The handle is invalid after destroy, and `destroy` must not race other calls on the same handle.
4. **Python callables must outlive the C engine's use of them.** A `CFUNCTYPE` wrapper that is garbage-collected while C still holds its pointer leads to a use-after-free. The `hooks.py` docstring names this as the main foot-gun. `register_token_observer` in `streams.py` avoids it by keeping the wrapper in a module-level `_observers` dict keyed by handle address (`:50-82`).
5. **No exceptions cross the boundary.** Python callbacks catch all exceptions, print a traceback, and return a neutral value. In the hook trampoline, a raised exception becomes "pass through" (`rc = 0`). The C ABI reports errors through error codes and `entropic_last_error(handle)`.
6. **Bytes are copied, not borrowed.** The stream observer uses `ctypes.string_at(token_ptr, length)`, which copies the token before decoding it. Hook context arrives as JSON and is decoded into a dict.

**Things to watch**

- The stream observer can fire from the engine thread and from the external-bridge worker thread, so Python token callbacks must be thread-safe (`entropic_set_stream_observer` docs).
- I did not verify whether `entropic_destroy` or re-registration releases the Python-side `_observers` entry. The observer is replaced on re-register, but I did not confirm cleanup on destroy.
- The index does not cover `_loader.py`'s full search order. I saw only the last step (`ctypes.util.find_library`).