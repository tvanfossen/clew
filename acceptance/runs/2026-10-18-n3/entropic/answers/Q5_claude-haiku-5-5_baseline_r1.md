## How Python reaches the engine

Python does not use a C extension or pybind11. It uses `ctypes` to `dlopen` `librentropic.so` and call the exported C ABI directly.

```
entropic.hooks / streams / helpers   (hand-written, keep callbacks alive, marshal JSON)
        │
_bindings.py                         (generated from include/entropic/entropic.h by scripts/gen_bindings.py)
        │  each symbol: restype + argtypes pinned via _bind()
        │  handle = c_void_p (opaque)
        ▼
librentropic.so  ── extern "C" (entropic.h) ──▶ C++ facade (src/facade/entropic.cpp)
```

- **Loading** (`python/src/entropic/_loader.py`): `ctypes.CDLL` on the first existing path from `$ENTROPIC_LIB`, then `$ENTROPIC_HOME`, then `~/.entropic/...`, then `ctypes.util.find_library("rentropic")`.
- **Bindings** (`_bindings.py`): one `_bind(name, restype, *argtypes)` line per export. It is marked auto-generated, and `inv gen-bindings --check` runs in pre-commit.
- **Hand-written layers**: `hooks.py` (decorator, trampolines, dict↔JSON), `streams.py` (token observer), `helpers.py` (`apply_patch` via `git apply`, since the engine never applies patches itself).

## Memory rules that cross the boundary

These come from the header's "Memory ownership" block and the callback docs:

1. **`char*` returns transfer ownership.** Free them with `entropic_free()`, which is `free()` in the shipped library (`src/facade/entropic.cpp:1954`).
2. **`const char*` returns are not freed.** `entropic_version()` is static. Other `const char*` returns are owned by the handle and valid only until the next call on that handle.
3. **Buffers the engine will free must come from `entropic_alloc()`.** The hook `modified_json` is one example. `hooks.py:_alloc_c_string` and the trampoline both use `entropic_alloc` (`hooks.py:124-160`), so the engine's `free()` gets a matching pointer.
4. **Callback arguments are borrowed for the call only.** Token text, hook `context_json`, and delegation results are valid only during the callback, so copy or decode them before returning. `streams.py` uses `string_at(ptr, length)`, which is safe for embedded NULs.
5. **CFUNCTYPE objects must outlive their registration.** If Python drops the wrapper, C calls freed memory. `hooks.py` keeps trampolines in `_bound` per handle, and `streams.py` keeps observers in `_observers`. A bare `HOOK_CB(f)` passed to `entropic_register_hook` is a use-after-free.
6. **No exceptions cross the `.so` boundary.** The hook trampoline catches everything and returns `rc=0`.
7. **Threading.** Each handle is serialized, `entropic_destroy` must not race other calls on that handle, and state queries are lock-free.

## A gap: the generated bindings leak owned strings

The rule in (1) is not honored on the Python side. `scripts/gen_bindings.py` maps `char*` to `ctypes.c_char_p` with no ownership information (`gen_bindings.py:132-133`). ctypes copies the string to `bytes` and discards the pointer, so the caller can no longer call `entropic_free` on it.

Affected functions (all `char*` returns documented as "caller frees with entropic_free") include `entropic_list_mcp_servers`, `entropic_adapter_info`, `entropic_adapter_list`, `entropic_grammar_get`, `entropic_grammar_validate` (non-NULL error string), `entropic_grammar_list`, `entropic_profile_get`, `entropic_profile_list`, and `entropic_list_identities`. The out-param `entropic_run(..., POINTER(c_char_p))` has the same problem. No file in `python/src/entropic/` calls `entropic_free` on any result, so Python consumers leak each result unless they hold the raw pointer and free it themselves.

I confirmed this by reading the generator, the generated `_bindings.py`, and the header. I did not build the library or run a leak measurement.

Possible fix, in the generator rather than the generated file (per CLAUDE.md, `_bindings.py` is generated and should not be hand-edited): give owned returns a distinct restype, such as `c_void_p`, and have a wrapper copy the bytes and call `entropic_free`. Adding a test that round-trips one of these calls under a leak check would pin the behaviour.