**How Python reaches the engine**

There is no pybind11, cffi, or extension module. The Python package is a ctypes shim over the shared library:

```
Python (entropic.*)
  └─ _bindings.py      generated from include/entropic/entropic.h (scripts/gen_bindings.py)
       └─ _loader.py   ctypes.CDLL("librentropic.so")  ← $ENTROPIC_LIB, then ~/.entropic/..., then ldconfig
            └─ src/facade/entropic.cpp   extern "C" entropic_* functions
                 └─ C++ engine internals (never cross the .so boundary)
```

- `_loader.py` finds the library and loads it with `ctypes.CDLL`.
- `_bindings.py` pins `restype` and `argtypes` for every `ENTROPIC_EXPORT` symbol. A pre-commit check (`inv gen-bindings --check`) fails if the file drifts from the header.
- The handle is a `ctypes.c_void_p`. Callbacks are `CFUNCTYPE` objects.
- The package has no `EntropicEngine` class. `__init__.py` says the C ABI is the public surface.

**Memory rules**

The header (`entropic.h`, "Memory ownership") and the architecture doc set these rules:

1. **`char*` returns transfer ownership.** The caller must free them with `entropic_free()`. Internally `entropic_alloc` is `malloc` and `entropic_free` is `free`.
2. **`const char*` returns belong to the handle.** They stay valid until the next call on that handle, so copy them immediately.
3. **Buffers the engine will free must come from `entropic_alloc()`.** Hook `modified_json` is the example. `hooks.py` does this correctly in its trampoline.
4. **Callback arguments are engine-owned and valid only during the callback.** Delegation request and result pointers are one case. `helpers.py` copies them with `string_at` before returning.
5. **Python must keep `CFUNCTYPE` wrappers alive.** `streams._observers` and the hook `_bound` list do this. Dropping the wrapper leaves the engine calling freed memory.
6. **Exceptions must not cross into C.** The Python trampolines catch and print, then return 0.
7. **`entropic_destroy` invalidates the handle.** The header is explicit that it must not race other calls on the same handle.
8. **Cross-`.so` data is C types only.** No `std::string`, vectors, or C++ vtables cross, per the architecture doc's "Pure C at `.so` boundaries" rule.

**Problems I found while checking this**

- **Leaks in the Python bindings.** Many functions the header declares as returning caller-freed `char*` are bound with `restype = ctypes.c_char_p`. Examples are `entropic_list_mcp_servers` (`_bindings.py:294`), `entropic_grammar_get` (:310), `entropic_grammar_validate` (:311), `entropic_adapter_list` (:306), and `entropic_list_mcp_keys` (:322). ctypes copies the string and discards the pointer, so the engine's allocation is never freed. The fix is to bind these as `c_void_p`, read the value, and free it with `entropic_free`.
- **Undocumented out-param ownership.** `entropic_run` and similar functions write a caller-freed string through `POINTER(c_char_p)`. The Python package has no wrapper that frees it, and nothing in `python/src` calls `entropic_free`.
- **Header drift.** `entropic.h` lines 701 and 812 refer to `entropic_free_string`, which does not exist. The real function is `entropic_free`.
- **Dead code.** `hooks._alloc_c_string` is defined but never called. The trampoline inlines the same logic.

I did not run the test suite or a leak check. The leak findings come from reading the bindings against the header and the `strdup`/`malloc` returns in `entropic.cpp`. Confirming them would take a run under valgrind (there's a `tests/valgrind.supp`) or a Python test that calls one of the listed functions in a loop.