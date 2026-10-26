**How Python reaches the engine**

Python never links against the C++ code. It loads `librentropic.so` at runtime with `ctypes`:

```
Python caller
  └─ entropic/_bindings.py   (ctypes; restype/argtypes pinned per symbol)
       └─ _loader.load()  →  ctypes.CDLL(librentropic.so)   [_loader.py:94]
            └─ src/facade/entropic.cpp  (extern "C", ENTROPIC_EXPORT)
                 └─ C++ engine (exceptions caught here, turned into error codes)
```

- `_bindings.py` is generated from `include/entropic/entropic.h` (its header says so and says not to edit it). `_bind(name, restype, *argtypes)` fetches each symbol and sets `restype` and `argtypes`. Handles are `c_void_p`, and out-parameters are `POINTER(c_char_p)`.
- Callbacks go the other way, as `CFUNCTYPE` trampolines (`HOOK_CB`, `TOKEN_CB`, and so on). `hooks.py` and `streams.py` keep each wrapper alive in a per-handle dict. Without that, the GC can free the trampoline while C still holds its pointer.
- Errors cross as `entropic_error_t` codes. Python-side exceptions are caught inside the trampolines and printed, so they never unwind into C.

**Memory rules at the boundary**

The header states the rules at `include/entropic/entropic.h:32-37`, with the implementations in `src/facade/entropic.cpp`:

1. **Engine-allocated `char*` results are caller-owned.** Free them with `entropic_free()`, which is `free()` underneath (`entropic.cpp:1954`). Examples are `entropic_run` (`result_json`, `entropic.cpp:1974`) and `entropic_list_mcp_servers` (`entropic.h:1281`).
2. **Memory the engine will free must come from `entropic_alloc()`.** That is `malloc` underneath (`entropic.cpp:1944`). Python does this for hook `modified_json` (`hooks.py:130` and `:159`), copying the bytes in with `ctypes.memmove`. Never give the engine a Python buffer, a `malloc` from another allocator, or a `new`.
3. **`const char*` returns belong to the handle.** They stay valid only until the next call on that handle. `entropic_version` is one example.
4. **Callback-borrowed buffers are valid only during the callback.** `streams.py:71` copies the token with `string_at` before returning. Anything kept longer must be copied.
5. **Per-handle thread safety** is documented per function: thread-safe, serialized per handle, or single-threaded init/destroy.

**Problems I found in the current tree**

- **Ownership-transferring strings are bound as `c_char_p`.** `_bindings.py` declares restype `c_char_p` for functions the header says return caller-owned strings, for example `entropic_list_mcp_servers` (`_bindings.py:294`). ctypes copies the bytes to a Python `bytes` and discards the pointer, so the engine's allocation can never be passed to `entropic_free`. Those calls leak, and the same applies to `entropic_adapter_info`/`_list`, `entropic_grammar_get`/`_validate`/`_list`, `entropic_profile_get`/`_list`, and any others with `char*` return types in the header. The fix is to bind these as `POINTER(c_void_p)` or `c_void_p`, copy with `string_at`, and call `entropic_free`. Because the file is generated, the fix belongs in `scripts/gen_bindings.py`.
- **Stale doc references.** `entropic.h:701` and `:812` name `entropic_free_string`, which does not exist. The real function is `entropic_free`. `src/facade/entropic.cpp:4022` and `:4099` repeat the wrong name.
- **Minor:** in `hooks.py`'s trampoline, if `entropic_alloc` returns NULL, the code still returns `rc = 1` with `*modified_json` unset.

**What I did not verify:** I found no Python-level wrapper that calls `entropic_run` and frees its result, so I can't say how the high-level Python API handles `result_json`. The C++ side's `alloc_cstr` path looks correct. I also did not check the `_loader.find()` search order beyond `$ENTROPIC_LIB`.