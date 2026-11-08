## How Python reaches the engine

Python never talks to C++ directly. The path is a single shared library reached through `ctypes`:

```
Python code
  └─ entropic (python/src/entropic/*.py)          pure Python, ~50 KB
       └─ _bindings.py   (generated, ctypes)      restype/argtypes pinned per symbol
            └─ ctypes.CDLL(librentropic.so)       loaded by _loader.py
                 └─ src/facade/entropic.cpp       extern "C", ENTROPIC_EXPORT
                      └─ C++ engine internals     exceptions caught here
```

- **Loading.** `_loader.find()` searches `$ENTROPIC_LIB`, then `$ENTROPIC_HOME`, then `~/.entropic/...`, then `ctypes.util.find_library`. `load()` returns a plain `ctypes.CDLL`.
- **Bindings are generated.** `scripts/gen_bindings.py` parses `include/entropic/entropic.h` and `types/*.h` and emits `_bindings.py` and `_bindings_manifest.py`. The pre-commit `gen-bindings --check` fails on drift. Every `ENTROPIC_EXPORT` symbol gets a `_bind(name, restype, *argtypes)` line.
- **Opaque handle.** `entropic_handle_t` is a `c_void_p`. Python passes it through and never dereferences it.
- **Callbacks** are `CFUNCTYPE` typedefs (`HOOK_CB`, `TOKEN_CB`, `DELEGATION_*_CB`, and so on). The Python wrapper keeps the trampoline alive on the engine side and catches exceptions in each trampoline so they never unwind into C.

The C ABI rule is in `docs/architecture-cpp.md` (design rules 1, 5, 6): pure C at every `.so` boundary, and exceptions do not cross it. Error codes are returned, and the detailed message comes from `entropic_last_error(handle)`.

## Memory rules across the boundary

The header states the contract in its "Memory ownership" block (`entropic.h` ~lines 32–37):

1. **`char*` returns transfer ownership.** The caller frees them with `entropic_free()`. Out-params like `char** result_json` (for example `entropic_run`) are owned the same way. The header comments say this on each function.
2. **`const char*` returns are borrowed.** They belong to the handle and are valid until the next call on that handle. `entropic_version()` is static and must not be freed.
3. **Callback payloads are borrowed.** The `ent_delegation_request_t` and `ent_delegation_result_t` pointers, including `patch` and `files_touched`, are valid only for the callback's duration. The consumer must copy anything it keeps. `helpers.py` shows this with `ctypes.string_at(res.patch, res.patch_len)`.
4. **Buffers the engine will free must come from the engine's allocator.** `entropic_alloc()` and `entropic_free()` are `malloc` and `free` (`src/facade/entropic.cpp` ~1944). Hook `modified_json` is one such buffer, and `hooks.py` allocates it with `entropic_alloc` before writing the JSON into it.
5. **Lengths, not NULs, for binary data.** Stream tokens and the patch buffer arrive with an explicit length. Python reads them with `string_at(ptr, length)`.
6. **Python-side lifetime.** Every CFUNCTYPE wrapper must be stored in Python for as long as the engine might call it. `hooks.py` keeps them in `_bound[handle]`, and `streams.py` keeps them in `_observers`. Dropping one causes a use-after-free from C.

## Problem I found: Python does not free engine-owned strings

The generated bindings declare owned-string returns with `restype = ctypes.c_char_p`. ctypes copies the bytes out and discards the pointer, so the caller has no pointer left to pass to `entropic_free`. The out-param forms (`POINTER(c_char_p)`) keep the pointer in the out variable, but the wrapper never frees it.

Examples from `_bindings.py`:
- `entropic_list_mcp_servers`, `entropic_grammar_get`, `entropic_grammar_list`, `entropic_grammar_validate`, `entropic_adapter_info`, `entropic_adapter_list`, `entropic_profile_get`, `entropic_list_identities`, `entropic_serialize_mcp_keys`. The header marks these as caller-owned.
- Out-params such as `entropic_run`, `entropic_run_as`, `entropic_context_get`, `entropic_get_identity`, `entropic_metrics_json`.

Within `python/src`, the only `entropic_free` reference is the generated binding itself, and nothing calls it. Each owned string returned through these paths leaks. Some of the listed functions may return borrowed `const char*` (`entropic_validation_last_result` and `entropic_get_identity_config` look like candidates), so each one needs checking against its header comment before deciding.

I read this from the source and did not run it. A leak check with `valgrind` or a `tracemalloc`-style test on a loop of `entropic_list_mcp_servers` would confirm it.

Possible fixes:
- Declare owned returns as `c_void_p` and wrap them in a helper that copies and then calls `entropic_free`.
- Generate that helper from the header's ownership comments. `gen_bindings.py` already parses them.

## Other notes

- `_alloc_c_string` in `hooks.py` is annotated `-> ctypes.c_void_p` but returns an `int`. It also returns `None` on OOM, and `_trampoline` then reports `rc=1` with no `modified_json`. Both are minor.
- A PostToolUse hook note suggested a `dossier` tool for reading `hooks.py`. That tool isn't available to me, so I ignored it and read the files directly.