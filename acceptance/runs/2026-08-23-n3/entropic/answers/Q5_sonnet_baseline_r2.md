## How Python reaches the C++ engine

It's **ctypes**, not cffi/pybind11 — and the wrapper is auto-generated, not hand-written.

- **`python/src/entropic/_loader.py`** locates and `ctypes.CDLL()`-loads `librentropic.so` (search order: `$ENTROPIC_LIB` → `$ENTROPIC_HOME` → `~/.entropic` → `ctypes.util.find_library`).
- **`python/src/entropic/_bindings.py`** is auto-generated from `include/entropic/entropic.h` (plus the `types/{error,enums,hooks}.h` headers) by **`scripts/gen_bindings.py`** — a hand-rolled regex parser, deliberately not pycparser, since the header comment notes it's "uniform C with no macro trickery beyond `ENTROPIC_EXPORT`." Run via `inv gen-bindings` (write) / `inv gen-bindings --check` (CI drift check). It defines `entropic_handle_t = ctypes.c_void_p` (an opaque handle Python never dereferences), IntEnum mirrors of C enums, `ctypes.Structure` mirrors of C structs, `CFUNCTYPE` callback typedefs, and one `_bind()` call per exported C function.
- **`python/src/entropic/__init__.py`** uses PEP 562 lazy `__getattr__` so `import entropic` doesn't force-load the `.so` (needed because `entropic install-engine` runs before the `.so` exists). Note: `python/entropic_native/` is a dead placeholder from an older CMake-driven pipeline — the real wrapper lives in `python/src/entropic/`.
- There is **no OOP `EntropicEngine` class** by design — a flat binding, on the stated principle that the C ABI is the public surface and an OOP layer would just lag behind it.

**Call flow** (e.g. `entropic_run`): Python passes the opaque handle + a `char*` input; ctypes marshals it straight through; C++'s `entropic_run()` (`src/facade/entropic.cpp`) runs inside a `try/catch`, copies its result into a freshly `entropic_alloc`'d buffer, and hands the pointer back via an out-param; ctypes reads it back as `bytes` in Python, which must then call `entropic_free()` on it.

## Memory-crossing rules

Documented centrally at the top of `entropic.h`:

- **Every `char**` out-param is caller-owned** — free it with `entropic_free()`. Repeated at ~40 call sites.
- **`entropic_alloc()`/`entropic_free()`** are the paired allocator/deallocator exposed across the boundary (thin `malloc`/`free` wrappers) — this guarantees the allocator that produced a buffer matches the one required to free it, so Python and C++ never mix allocators.
- **Reverse direction**: if Python hands the engine a buffer it expects the engine to later free (e.g. a hook's `modified_json`), that buffer **must be allocated via `entropic_alloc()`**, not ordinary Python/ctypes memory.
- **`const char*` returns are borrowed, not owned** — valid only until the next call on that handle; never free them, never retain them across calls.
- **Structured results with array fields** get a dedicated destructor (`entropic_free_logprob_result`) rather than field-by-field `entropic_free`.
- **Callback lifetime**: Python must keep the `ctypes.CFUNCTYPE` trampoline object alive for the engine's lifetime, or Python's GC will collect it out from under a live C++ callback pointer. Callback return values must be plain `int`, not `IntEnum`.

## Boundary rules (not just memory)

Per `docs/architecture-cpp.md`: only C types cross a `.so` boundary — no `std::string`/`std::vector`/`std::optional`/C++ vtables. Messages are JSON strings at the boundary. And critically: **exceptions never cross** — `entropic.cpp`'s exception-barrier wraps every entry point in try/catch, maps `std::filesystem::filesystem_error`/`nlohmann::json::exception`/generic `std::exception` to specific `entropic_error_t` codes, logs at error level before swallowing, and (for `entropic_run` specifically) still tries to allocate/return partial context even on failure. GIL/thread-safety is documented per-function (thread-safe / serialized-per-handle / init-destroy-only) rather than via any GIL-specific contract — notably `entropic_run` deliberately avoids holding an internal mutex during a long-running turn so `entropic_interrupt()` from another thread isn't blocked.
