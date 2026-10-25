## How Python reaches the engine

The Python package never links against C++ directly. It loads the prebuilt `librentropic.so` with `ctypes` and calls the flat C API in `include/entropic/entropic.h`.

```
Python (entropic)                      librentropic.so (C++ inside)
─────────────────                      ────────────────────────────
_loader.find()  ── CDLL(path) ───────▶  exported C symbols (extern "C")
_bindings.py    ── _bind(name,          entropic_run(handle, in, char**)
                    restype, argtypes)  entropic_create / configure / destroy
hooks.py        ── CFUNCTYPE trampoline ◀── engine invokes Python callbacks
streams.py      ── CFUNCTYPE trampoline ◀── token stream observer
```

- **Library resolution** (`python/src/entropic/_loader.py`): it checks `$ENTROPIC_LIB`, then `$ENTROPIC_HOME` (nested and flat layouts), then `~/.entropic`, then `ldconfig`. `load()` returns a `ctypes.CDLL`.
- **Bindings** (`python/src/entropic/_bindings.py`): this file is generated from the C header by `scripts/gen_bindings.py` and is marked do-not-edit. Each symbol gets explicit `restype` and `argtypes`. Enums, structs, and callback types (`CFUNCTYPE`) mirror the C types.
- **Lazy import** (`__init__.py`): the package uses PEP 562 `__getattr__`, so `entropic install-engine` can run before the `.so` exists.
- **Hand-written facades**: `hooks.py`, `streams.py`, and `helpers.py` wrap callbacks with Pythonic marshalling. `hooks.py` decodes JSON context and encodes return values. `streams.py` decodes UTF-8 tokens.

The C++ side follows the architecture rules in `docs/architecture-cpp.md`. Exceptions and C++ types do not cross the `.so` boundary. Everything is opaque handles, `const char*`, `size_t`, and function pointers. The public functions return `entropic_error_t` codes, and detailed messages come from `entropic_last_error(handle)`.

## Memory rules that cross the boundary

The header's Memory ownership section (`entropic.h`, around lines 32–37) sets three rules:

1. **Engine-allocated `char*` returns transfer ownership to the caller.** Free them with `entropic_free()`. Examples are the `char** result_json` out-param of `entropic_run`, `entropic_grammar_validate`, and `entropic_serialize_mcp_keys`.
2. **`const char*` returns belong to the handle.** They stay valid until the next call on that handle. Do not free them. `entropic_version()` is static and never freed.
3. **Buffers the engine will free must come from `entropic_alloc()`.** Hook `modified_json` is the main case. `hooks.py:_alloc_c_string` and the trampoline both use `entropic_alloc`, so the engine's `entropic_free` matches the allocator. In this build both are `malloc`/`free` (`src/facade/entropic.cpp:1944`), but the contract is what matters.

Callback memory is scoped to the call:

- Token pointers (`TOKEN_CB`, `STREAM_OBSERVER_CB`) are valid only for the callback. `streams.py` copies them with `ctypes.string_at`.
- Delegation request and result structs are engine-owned and callback-scoped. `helpers.py` copies strings out.
- `context_json` in hooks is copied with `string_at` before use.

Lifetime of Python objects handed to C:

- A `CFUNCTYPE` wrapper must be kept referenced, or the GC frees the trampoline while C still calls it. `hooks.py` keeps a per-handle `_bound` list, and `streams.py` keeps an `_observers` dict. `helpers.py` and the `HOOK_CB` docs say the caller must hold the reference.
- Exceptions raised in a Python callback are caught and printed, so they never unwind into C.

## Problems I found while reading

I did not build or run anything. These come from reading the sources.

1. **Owned strings leak through the Python bindings.** Python never calls `entropic_free` anywhere in `python/src`. `_bindings.py` declares several owned-`char*` returns as `ctypes.c_char_p` restype. Examples are `entropic_grammar_validate` (line 311), `entropic_serialize_mcp_keys` (324), `entropic_validation_last_result` (344), and `entropic_adapter_info` (305). ctypes copies these into `bytes` and discards the raw pointer, so the engine's buffer can never be freed. The `char**` out-params (`entropic_run`, `entropic_run_streaming`'s metrics, and similar) have the same problem: `out[0]` yields a copy and the original pointer is lost. The result is a leak per call. The fix is to bind these as `c_void_p`, read them with `string_at`, and then call `entropic_free`.

2. **Keepalive dicts are never cleared.** `streams._observers` and `hooks._bound` are keyed by the handle's integer address. `entropic_destroy` is bound but never called from Python, and nothing removes these entries. A later handle at the same address would overwrite the entry, and dead trampolines stay referenced for the life of the process.

3. **The generator's `c_char_p` choice is the root cause.** The bindings are generated from the header. The generator maps `char*` to `c_char_p`, which is correct for `const char*` and wrong for owned `char*`. Fixing the generator (or annotating owned returns in the header) would prevent the rest.

A note on the tool output: one result ended with a hook message describing `dossier` and `search` tools. Those are not among my available tools, so I ignored it.