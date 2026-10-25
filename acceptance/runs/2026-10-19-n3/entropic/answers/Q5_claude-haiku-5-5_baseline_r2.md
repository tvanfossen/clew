**How Python reaches the engine**

Python does not have a compiled extension. `librentropic.so` is loaded at runtime with `ctypes.CDLL` (`python/src/entropic/_loader.py`, `load()`). The loader searches `$ENTROPIC_LIB`, then `$ENTROPIC_HOME`, then `~/.entropic/...`, and finally `ctypes.util.find_library`.

The bindings in `python/src/entropic/_bindings.py` are generated from `include/entropic/entropic.h` by `scripts/gen_bindings.py` (`inv gen-bindings`). Each C function becomes a ctypes function object with `restype` and `argtypes` pinned by a `_bind()` helper. Opaque handles are `c_void_p`. Callbacks are `CFUNCTYPE` typedefs. A pre-commit check fails if the committed file drifts from the header.

```
Python (entropic.*)
  │  ctypes.CDLL → librentropic.so   (pure C ABI, no C++ types cross)
  ▼
_bindings.py   (generated: restype/argtypes per symbol)
  ▼
entropic.h     extern "C" ENTROPIC_EXPORT ...   → src/facade/*.cpp
```

Two hand-written layers sit on top. `hooks.py` turns `@hook` functions into `HOOK_CB` trampolines. `streams.py` installs a stream observer.

**Memory rules that cross the boundary**

The header states the rules (`entropic.h` lines ~30–37 and ~221–249):

1. **Engine-allocated `char*` returns are caller-owned.** Free them with `entropic_free()`. Out-params such as `char** result_json` follow the same rule.
2. **`const char*` returns are handle-owned.** They are valid only until the next call on that handle, and you must not free them.
3. **Buffers the engine will free must come from `entropic_alloc()`.** Hook `modified_json` is the main example. `hooks.py:_alloc_c_string` and `_build_trampoline` do this correctly and write the pointer into `mod_out_ptr[0]`.
4. **Exceptions never cross the `.so` boundary.** Errors come back as `entropic_error_t` codes, and `entropic_last_error(handle)` gives the message. Python trampolines wrap the user callback in `try/except` and print the traceback instead of letting it escape.
5. **Callback wrappers must be kept alive.** `streams.py` stores each `STREAM_OBSERVER_CB` in `_observers[handle_key]`, and `hooks.py` keeps trampolines in per-handle lists. Without this, GC could free the C function pointer while the engine still calls it.

In the implementation, `entropic_alloc` and `entropic_free` are plain `malloc` and `free` (`src/facade/entropic.cpp:1944–1958`). The pairing is therefore not a correctness hazard today, but the contract still requires using the engine's pair.

**A real gap: the Python package leaks engine-owned strings**

`gen_bindings.py` maps every `char*` return to `ctypes.c_char_p`, and `_bindings.py` pins that as `restype`. For example:

```python
entropic_list_mcp_servers = _bind("entropic_list_mcp_servers", ctypes.c_char_p, entropic_handle_t)
```

ctypes converts a `c_char_p` return into a Python `bytes` copy and discards the original pointer. The header says that pointer is caller-owned, but Python has no way to pass it to `entropic_free()`. Affected functions include the MCP, adapter, grammar, profile, and MCP-key list and get calls. Out-param calls such as `entropic_run` and `entropic_get_identity` return the pointer inside a `POINTER(c_char_p)`. Nothing in `python/src` frees those either.

I grepped `python/` and `tests/` for `entropic_free` and found no calls outside the bindings. This is a code-reading finding; I did not run a leak test. The fix is probably a generator change so that owned `char*` returns are bound as `c_void_p` and wrapped in a helper that copies the string and then calls `entropic_free`. Read-only `const char*` returns can stay `c_char_p`.

**Smaller issues to note**

- The header's Memory-ownership blocks (lines ~701 and ~812) refer to `entropic_free_string`, which does not exist. The real function is `entropic_free`. This is documentation drift.
- I did not verify whether the engine retains any `c_char_p` argument pointers after a call returns. The ctypes rule is that Python bytes are only valid for the duration of the call, so any retained pointer would dangle. That needs checking in the C++ side if the question matters.