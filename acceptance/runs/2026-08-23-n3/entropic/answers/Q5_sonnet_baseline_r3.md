Now I have the full picture, grounded in the actual source.

## How Python reaches the C++ engine

There's no C++ ABI crossing anywhere — that's a hard design rule (`docs/architecture-cpp.md`: "Pure C at all `.so` boundaries"). The path is:

```
Python app code
   │  from entropic import entropic_create, entropic_run, ...
   ▼
entropic/__init__.py      — PEP 562 lazy __getattr__, re-exports names from
                             _bindings_manifest.EXPORTS on first access
   ▼
entropic/_bindings.py     — AUTO-GENERATED (scripts/gen_bindings.py, checked by
                             pre-commit's `inv gen-bindings --check`) flat ctypes.CDLL
                             bindings: one `_bind(name, restype, *argtypes)` line per
                             `ENTROPIC_EXPORT` symbol in include/entropic/entropic.h
   ▼
entropic/_loader.py       — resolves and ctypes.CDLL()-loads librentropic.so
                             (search order: $ENTROPIC_LIB → $ENTROPIC_HOME →
                             ~/.entropic → ldconfig cache)
   ▼
librentropic.so           — the C++ engine, exposed only through a pure-C facade
                             (include/entropic/entropic.h)
```

There is deliberately **no `EntropicEngine` class** — v1.7.x had an OOP wrapper, v2.x dropped it because "the C ABI is the public surface and an OOP layer would just lag behind it" (`__init__.py` docstring). The Python package is ~50 KB: a binding shim plus a CLI (`entropic install-engine`) that downloads the actual native binary — it's never built from source on the Python side.

`hooks.py`, `streams.py`, `mcp.py` are the only places with hand-written Pythonic ergonomics on top (decorator registries, trampoline-lifetime management); everything else is the generated flat binding.

## The memory-crossing rules

The header states one policy at the top of `entropic.h`, and it's unusually strict about direction:

**1. Engine → Python (`char*` return values / out-params): caller frees, no exceptions.**
Every `entropic_run`, `entropic_metrics_json`, `entropic_adapter_info`, `entropic_get_identity_config`, etc. that hands back a heap string transfers ownership to the caller, who **must** call `entropic_free()` on it — never libc `free()`, since the engine may use a different allocator internally. `entropic_free_logprob_result` is the analogous compound-struct case. Ctypes' `_bindings.py` doesn't do this for you automatically — a consumer calling the raw binding is responsible for the `entropic_free` call once done with the `c_char_p`.

**2. `const char*` returns (e.g. `entropic_version()`) are NOT owned.** They're static or handle-owned and valid only until the next call on that handle — never free these, never hold a reference across another call.

**3. Python → Engine (buffers the engine will later free, e.g. hook `modified_json`): must be allocated with `entropic_alloc()`, never a Python-native buffer.** This is the direction most likely to be gotten wrong, and `hooks.py` is the concrete illustration: `_alloc_c_string()` and the hook trampoline both call `entropic_alloc()`, `ctypes.memmove()` the encoded payload in, and only then hand the pointer back to C — because the engine will eventually call its own `free()` on it, and a pointer from Python's allocator (or a ctypes-managed buffer) has the wrong provenance for that free to be valid.

**4. Read-only borrows use `ctypes.string_at()` and copy immediately.** `hooks.py`'s trampoline (`ctx_ptr`) and `streams.py`'s token callback (`token_ptr`, length-bounded) both `string_at()` the C-owned buffer into a Python `bytes`/`str` synchronously inside the callback — they never store the raw pointer, because the engine owns that memory only for the duration of the call.

**5. Callback trampolines have a separate, non-obvious lifetime hazard: CFUNCTYPE objects must be kept alive by Python.** This isn't documented in the C header (it can't be — it's a ctypes/CPython artifact), but `hooks.py` calls it out explicitly: a bare `entropic_register_hook(handle, point, HOOK_CB(my_func), None, 0)` lets Python garbage-collect the trampoline the instant the call returns, and the next time C invokes that function pointer it dereferences freed memory. `hooks.py`'s `_HookEntry.trampoline` field and `helpers.py`'s docstring example ("Hold the CFUNCTYPE wrapper for the engine's lifetime") exist solely to pin these references for as long as the handle can call back into Python.

So the rule set is symmetric and allocator-scoped: **whoever's allocator produced the memory is the only one who may free it**, and the boundary is enforced by which allocation function you called (`entropic_alloc` vs. Python's own), not by which language you're in.
