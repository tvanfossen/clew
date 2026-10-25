**Short answer:** Python never links against C++ types. It `ctypes.CDLL`-loads `librentropic.so` and calls the pure-C functions declared in `include/entropic/entropic.h`. Memory is handled by a few explicit rules: the engine's allocator pair, copy-on-callback for transient pointers, and caller-kept-alive callback objects. The generated bindings have one real bug against those rules, described below.

## How Python reaches the engine

```
Python app
  │  import entropic  (__init__.py, PEP 562 lazy __getattr__)
  ▼
entropic.hooks / streams / mcp / helpers   thin facades, keep CFUNCTYPE alive
  ▼
entropic._bindings  (GENERATED from entropic.h by scripts/gen_bindings.py)
  │  _bind(name, restype, *argtypes) pins every symbol
  ▼
ctypes.CDLL(librentropic.so)   resolved by python/src/entropic/_loader.py
  ▼
src/facade/entropic.cpp        extern "C" facade; exceptions caught here
  ▼
C++ engine (core/, inference/, mcp/)
```

- **Loading** (`_loader.py`): `$ENTROPIC_LIB`, then `$ENTROPIC_HOME` nested and flat layouts, then `~/.entropic/...`, then `ctypes.util.find_library`.
- **Bindings** (`_bindings.py`): generated, with a `--check` gate in pre-commit. `char*` maps to `c_char_p`, `char**` to `POINTER(c_char_p)`, and the opaque handle is `c_void_p`. There is no `EntropicEngine` class; the API is flat.
- **Facades**: `hooks.py`, `streams.py`, and `mcp.py` wrap CFUNCTYPE callbacks and JSON marshalling. `helpers.apply_patch` is pure Python, not part of the ABI.

## Memory rules

| Situation | Rule | Where it is stated |
|---|---|---|
| Engine returns `char*` (e.g. `entropic_run`'s `result_json`, `entropic_context_get`) | Caller owns it; free with `entropic_free()` (`free()` underneath) | `entropic.h:33`, `:241`, `:274` |
| Engine returns `const char*` (`entropic_version`, `entropic_last_error`) | Do not free. Static, or owned by the handle until the next call | `entropic.h:37`, `:173`; `types/error.h:105` |
| Data the engine will free (hook `modified_json`) | Must come from `entropic_alloc()` (also `malloc`), never Python or ctypes buffers | `entropic.h:226`; `hooks.py:159` |
| Callback pointers (tokens, hook `context_json`, delegation `patch`) | Valid only for the callback. Copy before returning | `entropic.h:355`, `:739`; `types/hooks.h:124`; `streams.py:71` and `hooks.py:154` copy with `string_at` |
| Handles | Opaque. Serialized per handle. `entropic_destroy` is NULL-safe and must not race other calls | `entropic.h:157`, `:94` |
| Callback objects | The CFUNCTYPE wrapper must outlive the registration, or the engine calls freed memory | `hooks.py:73`, `streams.py:40` |
| Exceptions | Never cross the `.so` boundary. The facade returns error codes; Python trampolines catch, print, and return 0 | `hooks.py:164`; `streams.py:73` |

## Problems I found

1. **Leak on owned `char*` returns via the raw bindings.** `gen_bindings.py` maps every `char*` return to `restype = c_char_p`. ctypes then copies the string into a Python `bytes` and discards the engine pointer, so it can never be freed. About a dozen functions are affected, including `entropic_get_identity_config`, `entropic_list_mcp_servers`, `entropic_list_identities`, `entropic_validation_last_result`, `entropic_grammar_get`, `entropic_profile_list`, and `entropic_list_mcp_keys`. Each one's header says "caller must free with `entropic_free()`". Use `entropic_run` / `entropic_context_get` with an out-param for owned strings, or fix the generator to map owned returns to `c_void_p` and free after copying. This is a generator bug, not a per-caller one.
2. **Doc drift.** `entropic.h:701`, `:812`, and `src/facade/entropic.cpp:4022` reference `entropic_free_string`, which does not exist. The real function is `entropic_free`.
3. **Keepalive dicts are never released.** `streams._observers` and `hooks._bound` are keyed by handle address and never cleared on `entropic_destroy`. Trampolines accumulate per handle, and a reused address could overwrite a live entry.
4. **Dead helper.** `hooks._alloc_c_string` is never called; the trampoline inlines the same logic. This violates the DRY rule in CLAUDE.md.

I did not build or run anything; these findings come from reading the headers, the generator, and the Python sources, plus index lookups of `entropic_alloc`, `entropic_free`, `entropic_run`, `entropic_context_get`, and `entropic_get_identity`.