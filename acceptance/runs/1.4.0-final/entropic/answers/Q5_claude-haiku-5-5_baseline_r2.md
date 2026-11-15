## How Python reaches the engine

Python does not embed or re-implement the engine. It loads `librentropic.so` with `ctypes` and calls the C ABI declared in `include/entropic/entropic.h`. No pybind11, cffi, or Python C extension is involved.

```
Python app
  │  import entropic
  ▼
entropic/_bindings.py     auto-generated from entropic.h by scripts/gen_bindings.py
  │  _bind(name, restype, *argtypes) pins each symbol
  ▼
entropic/_loader.py       ctypes.CDLL(librentropic.so), first hit wins:
  │                       $ENTROPIC_LIB → $ENTROPIC_HOME → ~/.entropic → ldconfig
  ▼
librentropic.so           C ABI (ENTROPIC_EXPORT), implemented in src/facade/entropic.cpp
  │                       C++ internals never cross the boundary
  ▼
C++ engine
```

- **Loader** (`_loader.py`): `find()` checks several install layouts, then falls back to `ctypes.util.find_library`. `load()` raises `OSError` with a hint to run `entropic install-engine`.
- **Bindings** (`_bindings.py`): every export gets an explicit `restype` and `argtypes`. The handle is `entropic_handle_t = c_void_p`, and enums and structs are mirrored by hand-generated `IntEnum` and `ctypes.Structure` classes. The file is marked auto-generated and a pre-commit `--check` fails on drift from the header.
- **Lazy import** (`__init__.py`): a PEP 562 `__getattr__` loads `_bindings` only on first use. The export list comes from `_bindings_manifest.py`, which does not load the `.so`.
- **Hand-written layer**: `hooks.py`, `streams.py`, `mcp.py`, and `helpers.py` wrap the callback-heavy parts. `cli.py` shells out to the bundled binary.

The header's C-side rules are: exceptions do not cross `.so` boundaries; errors come back as `entropic_error_t` codes; `ENTROPIC_EXPORT` marks every exported symbol.

## Memory rules across the boundary

**1. Engine-owned `char*` returns are freed with `entropic_free()`.**
- The header says functions returning `char*` transfer ownership to the caller (`entropic.h` ~L33, ~L262, ~L811).
- Native `entropic_alloc` is `malloc` and `entropic_free` is `free` (`src/facade/entropic.cpp` ~L1944–1956).
- Out-param results such as `entropic_run`'s `result_json` must be freed by the caller.
- The generated bindings do not wrap these. A raw call leaves you with a pointer you must free yourself. You need `ctypes.cast(out, c_void_p).value`, then `entropic_free(ptr)`. Nothing in the Python package does this for you.

**2. `const char*` returns are owned by the handle.**
- Examples: `entropic_version` (static, never freed), `entropic_list_mcp_servers`, `entropic_grammar_get`.
- They stay valid only until the next call on that handle.
- The bindings declare these as `c_char_p` restypes, so ctypes copies them into `bytes` immediately. That is safe, and you must not free them.

**3. Memory the engine will free must come from `entropic_alloc`.**
- Example: a hook's `modified_json`.
- `hooks.py` `_trampoline` does this correctly: `entropic_alloc(len)`, then `memmove`.
- Using Python's allocator here would hand the engine a pointer from the wrong heap.

**4. Strings going in must be bytes.**
- `c_char_p` arguments take `bytes`. Encode `str` to UTF-8 at the call site.

**5. Callback wrappers must be kept alive by Python.**
- A `CFUNCTYPE` object that is garbage collected while C still holds its function pointer leads to a crash.
- `hooks.py` stores trampolines in `_HookEntry` and `_bound[handle]`.
- `streams.py` stores the observer in `_observers[handle]`.
- The `helpers.py` docstring tells callers to hold their own references.

**6. Borrowed callback data is valid only during the callback.**
- Examples: the token pointer in `TOKEN_CB`, `EntDelegationRequest`/`Result`, and the residency observer's strings.
- `streams.py` copies with `string_at` before returning, which is correct.
- The header also forbids re-entering the API from some callbacks. For example, on_token and the residency observer must not call back into the same handle.

**7. Exceptions never escape into C.**
- Every trampoline wraps the user function in `try/except`, prints the traceback, and returns a safe code (`hooks.py` returns 0 on error).

**8. Threading.**
- Callbacks may fire on the engine thread or a delegation worker thread (`entropic.h` ~L466, ~L1106).
- Python callbacks must therefore be thread-safe.

## Problems I found while reading

- **Stale doc reference.** `entropic.h` L701 and L812, and `entropic.cpp` ~L4022 and ~L4099, say to free with `entropic_free_string`. That function is not declared or implemented anywhere, so the header contradicts itself. The correct call is `entropic_free()`.
- **Hook registry can skip hooks on a reused handle address.** `register_hooks` keys `_bound` by the handle's address, and nothing clears the entry when the engine is destroyed. If a new handle reuses the address, `if any(b.func is entry.func ...)` treats the hooks as already bound and skips them. The same stale-entry issue applies to `_observers` in `streams.py`. I have not reproduced this; it follows from reading the code.
- **Unverified ctypes behavior.** The trampolines and the `helpers.py` example take `c_char_p` callback arguments and pass them to `string_at` as if they were addresses. I did not check whether ctypes hands these over as `bytes` or as pointers. A quick test under the project venv would settle it.