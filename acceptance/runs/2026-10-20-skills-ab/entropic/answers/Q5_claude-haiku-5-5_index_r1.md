## How Python reaches the engine

Python does not link against the engine or go through a compiled extension. It loads the shared library at runtime with `ctypes` and calls the C ABI directly.

```
Python code
  └─ entropic._bindings        (auto-generated ctypes shims, _bindings.py)
       └─ entropic._loader.load()  → ctypes.CDLL("librentropic.so")   (_loader.py:94)
            └─ C ABI in include/entropic/entropic.h  (ENTROPIC_EXPORT symbols)
                 └─ src/facade/entropic.cpp  (C++ engine behind the flat C API)
```

- **Library lookup** (`_loader.py:35-71`): `$ENTROPIC_LIB`, then `$ENTROPIC_HOME` (nested, then flat layout), then `~/.entropic/...`, then `ctypes.util.find_library("rentropic")`. `_bindings.py:24` calls `load()` at import time, so importing the module fails if the .so is missing.
- **Signatures**: `_bindings.py` pins `restype` and `argtypes` on each symbol through `_bind()` (lines 35-43). `entropic_handle_t` is a `c_void_p`, so the engine's `struct entropic_engine*` is opaque on the Python side.
- **Callbacks**: C-to-Python callbacks are `CFUNCTYPE` objects (`_bindings.py:231-245`). Python-side helpers `hooks.py` and `streams.py` wrap them in trampolines that catch every exception and print it, so nothing unwinds into C.
- **Public surface**: `entropic/__init__.py` lazily re-exports `_bindings` names (PEP 562). Application code calls the raw `entropic_run`, `entropic_create` and so on.

**Discrepancy:** `.claude/CLAUDE.md` says the auto-generated wrapper lives in `python/entropic_native/`. In this checkout that directory holds only `py.typed`. The generated code is `python/src/entropic/_bindings.py`, whose header says it is produced by `scripts/gen_bindings.py`.

## Memory rules across the boundary

The contract is documented in `entropic.h` and implemented in `entropic.cpp`.

1. **Engine-allocated outputs are caller-owned.** Any `char**` out-parameter that transfers ownership (e.g. `entropic_run`'s `result_json`, `entropic.h:262-274`) must be released with `entropic_free()`. Many other functions carry the same "Caller must free with entropic_free()" note.
2. **One allocator pair.** `entropic_alloc` is `malloc` and `entropic_free` is `free` (`entropic.cpp:1944-1956`). Memory that the engine will free must come from `entropic_alloc`, and memory the caller frees with `entropic_free` must come from the engine. Mixing in a Python-side buffer (`ctypes.create_string_buffer`) or a Python-allocated pointer is invalid.
3. **Engine-owned strings are borrowed.** `const char*` returns are owned by the handle and valid only until the next call on that handle (`entropic.h:34-37`). Version strings are static and must not be freed (`entropic.h:171-173`). Callback arguments such as delegation request/result descriptors are "engine-owned, callback-scoped" (`entropic.h:1027`, `1053`, `1075`), so Python must copy them before returning.
4. **Python must copy borrowed data immediately.** The wrappers do this with `ctypes.string_at(ptr, len)` (`streams.py:71`, `helpers.py:30`), which copies bytes out before the pointer can be invalidated.
5. **Lifetime of the callback objects.** A `CFUNCTYPE` wrapper must be kept referenced for as long as C may call it. `hooks.py:1-20` keeps a per-handle registry for this, and `streams.py:79-80` stores the observer in `_observers[handle_key]`. Dropping the reference is a use-after-free.
6. **Hook output goes through `entropic_alloc`.** `hooks.py:124-135` and `hooks.py:159-162` copy the modified JSON into engine-allocated memory, which the engine later frees. Python must not free it.
7. **Handle lifecycle.** `entropic_destroy` (`entropic.cpp:1877-1905`) deletes the handle and makes it invalid. Nothing in the Python files I read calls it automatically, so the caller has to destroy the handle.

## Sharp edges

- **No Python helper frees `result_json`.** I found no `entropic_free` call in the Python package, so raw `entropic_run` callers must free the `c_char_p` buffer themselves or they leak it. Whether `entropic_free(out)` accepts a `c_char_p` argument through the `c_void_p` argtype is something I did not test.
- **Doc inconsistency.** Some header comments (`entropic.h:701`, `812`) say `entropic_free_string`, which is not the exported name. The real function is `entropic_free`.

I did not run the code, so the ctypes behaviour above is from reading the source.