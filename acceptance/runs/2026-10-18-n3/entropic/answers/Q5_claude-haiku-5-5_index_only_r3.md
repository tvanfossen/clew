The index answers this well for the C side and the free/alloc rules. It is thinner on the Python-side lifetime rule, which I could only partly recover.

**How Python reaches the engine**

There is no pybind11 or C++ extension in the Python package. It is a pure-Python `ctypes` shim:

- `python/src/entropic/_bindings.py` is auto-generated from the C header by `scripts/gen_bindings.py` (run via `tasks.py`). It exposes the C ABI as ctypes function objects, `IntEnum`s that mirror C enums, `ctypes.Structure` types, and `CFUNCTYPE` callback typedefs.
- It loads `librentropic.so` at runtime. `entropic/__init__.py` imports `_bindings_manifest.py` eagerly, so the names are available without loading the library.
- The README describes it as "a thin ctypes binding over the C ABI, no OOP wrapper." `hooks.py` is the one hand-written Pythonic layer on top, and it wraps the raw hook ABI.
- The C side is the facade `src/facade/entropic.cpp`. Its entry points are `entropic_create` (allocates the engine handle with `new`), `entropic_destroy` (`delete`s it, NULL-safe), and `entropic_register_hook`, all `ENTROPIC_EXPORT`.

**Memory rules across the boundary**

1. **Handles are opaque.** Python gets a `void*`-style `entropic_handle_t` and never sees the struct. Create and destroy are paired, and destroy must not race other calls on the same handle (`@threadsafety` on `entropic_destroy`).
2. **Engine-owned strings are freed with `entropic_free`.** Its doc says all `char*` returns that transfer ownership must be freed with it. It is `free(ptr)`, NULL is a no-op, and it is documented thread-safe. Use it, not Python's or the caller's `free`.
3. **Consumer-allocated buffers the engine will free must come from `entropic_alloc`.** The header says this explicitly for hook `modified_json`. `entropic_alloc` is `malloc`. This matters because the engine calls `free()` on it, so the allocators have to match.
4. **Python-side hook returns are copied into engine memory.** `_alloc_c_string` and the hook trampoline in `hooks.py` call `entropic_alloc`, `memmove` the UTF-8 bytes plus a NUL, and hand the pointer over. The Python bytes object never escapes. The `_build_trampoline` docstring says the engine frees that pointer after consuming it, and that Python must make sure no Python reference outlives that free.
5. **Exceptions never cross.** The trampoline catches every Python exception, prints the traceback, and returns 0 (pass-through). This follows design rule 6 (exceptions don't cross `.so` boundaries; error codes and callbacks do).
6. **Plugin ownership differs by side.** For MCP server plugins, `i_mcp_server.h` says strings returned by the server must be freed with `entropic_free`, while names returned by `name` are server-owned and valid for the handle's lifetime. Input strings are not retained. The inference backend has its own `entropic_inference_free`, which is `std::free`. Each `.so` frees with its own allocator's counterpart.

**What I could not confirm**

The `hooks.py` file header warns about a "Lifetime" foot-gun, but the index truncates it before the rule itself. The likely subject is that the `CFUNCTYPE` trampoline must be kept referenced on the Python side, or the C engine holds a dangling function pointer. I did not verify this, and I could not read the file. Check the top of `python/src/entropic/hooks.py` directly to confirm.