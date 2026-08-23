## How Python reaches the engine

There's no C++ crossing the process boundary at all — the chain is:

**`librentropic.so` (C++ engine) → pure C ABI in `include/entropic/entropic.h` → `ctypes` bindings in `python/src/entropic/_bindings.py` → thin Python facades**

- `entropic.h`'s file doc states the rule directly: *"This is the unified facade. Most consumers link against librentropic and include only this header. All functions are pure C — no C++ types cross this boundary."* This is a repo-wide convention, not just this header — `docs/architecture-cpp.md` calls it "The Rule": *"uses C types only. No `std::string`, `std::vector`, `std::optional`, or C++ vtables cross a shared library boundary."*
- `python/src/entropic/_bindings.py` is a flat `ctypes` shim: each C function is bound once at module load with explicit `restype`/`argtypes`, e.g.
  - `entropic_create = _bind("entropic_create", ctypes.c_int, ctypes.POINTER(entropic_handle_t))`
  - `entropic_run = _bind("entropic_run", ctypes.c_int, entropic_handle_t, ctypes.c_char_p, ctypes.POINTER(ctypes.c_char_p))`
  - callback-taking functions (`entropic_run_streaming`, `entropic_set_stream_observer`) bind against `ctypes` function-pointer types (`TOKEN_CB`, `STREAM_OBSERVER_CB`).
- The package's own file doc (`python/src/entropic/__init__.py`) confirms this is deliberately minimal: *"The package itself is ~50 KB of pure Python: a ctypes binding shim and a small CLI. The native engine binary is fetched on demand via `pip install entropic-engine` / `entropic install-engine`"* — i.e. the `.so` is not vendored into the wheel, it's downloaded separately and `dlopen`'d/`ctypes.CDLL`'d at runtime.
- `docs/dist-README.md` is explicit that this isn't a hidden abstraction: *"There is no `EntropicEngine` class — bindings mirror the C ABI verbatim."* Anything nicer (`hooks.py`, `mcp.py`, `streams.py`) is a hand-written convenience wrapper sitting on top of the raw `_bindings` calls, not a different transport.

So the handle itself (`entropic_handle_t`) is opaque on both sides — Python holds a `ctypes` pointer, C++ holds `struct entropic_engine*` (defined privately in `src/facade/engine_handle.h`, per its file brief, "private to the facade" — Python never sees the struct layout, only the pointer value).

## The memory-crossing rules

Two allocators, two directions, one governing rule: **whoever allocates across the boundary must be the one whose `free` is called** — never `free()`/`malloc()` mixed across the C/C++ or C/Python allocator boundary.

**1. Engine → Python (strings/results): callee allocates, caller frees with `entropic_free`.**
- `entropic_run`'s doxygen is explicit: `result_json` is *"a newly allocated JSON result string (**caller owns, free with `entropic_free`**)"*. The body calls `alloc_cstr(...)` internally to produce it.
- `entropic_free` is trivial and symmetric on purpose: `void entropic_free(void* ptr) { free(ptr); }` — it's a thin wrapper around libc `free`, exported specifically so a caller in a different runtime (Python's ctypes, or any other language) never calls its own allocator's `free` on memory the engine's C runtime allocated. `entropic_alloc` (`malloc(size)`) is the mirror-image entry point when a caller needs to hand *the engine* a buffer it will own.
- The i_inference_backend.h interface doc generalizes this per-interface: *"Strings returned by generate/complete (via result_json) are allocated by..."* (the engine side) — same pattern at every `.so` boundary, not just the top-level facade.
- Every `entropic_run*` variant (`entropic_run`, `entropic_run_as`, `entropic_run_batch`, `entropic_run_messages`, …) follows this out-parameter-plus-`entropic_free` shape, per the bindings list in `_bindings.py`.

**2. Python → Engine (callbacks/user_data): lifetime is the caller's problem, and it's a documented foot-gun.**
- `hooks.py`'s file doc calls this out directly: using the raw ABI (`_bindings.HOOK_CB`, `_bindings.entropic_register_hook`) *"carries two foot-guns: 1. Lifetime: a [callback held only by the ctypes trampoline / GC'd Python object]..."* — i.e. `ctypes.CFUNCTYPE` callback objects must be kept alive on the Python side for as long as the C engine might invoke them, or the underlying trampoline is freed while C still holds a raw function pointer to it. The Pythonic facades (`hooks.py`, `streams.py`, `mcp.py`) exist specifically to hide this: they keep a reference to the ctypes callback object alive for the handle's lifetime so the caller doesn't have to reason about it manually.
- `entropic_destroy`'s body shows the C++ side has its own analogous ordering constraint: *"Stop external bridge FIRST — it holds a raw pointer to handle"* and releases `inference_iface_ctx` "before the orchestrator unloads, since the context holds a raw orchestrator pointer" — raw-pointer-holding subsystems are torn down in a specific reverse order precisely because nothing here is reference-counted across the boundary; ownership is a documented protocol, not enforced by the type system.

**3. Handles themselves are opaque and non-reentrant-unsafe in one place worth flagging:** `entropic_run`'s comment notes the API mutex is deliberately *not* held for the duration of a run ("a long turn must not block `entropic_interrupt()` called from another thread") — so from Python, a handle can be destroyed or reused concurrently with an in-flight call if the caller doesn't serialize that itself; the index shows no lock enforcing it at the `entropic_run`/`entropic_destroy` pair.

**Gap I can't close from the index:** the exact `ctypes.CDLL`/`dlopen` call site and the `_bind()` helper's error handling aren't resolvable by name search (`_bind` matches 61 token hits with no distinguishing second term, and `CDLL` isn't indexed as a symbol token at all — it's likely inside `_bind`'s body or a loader function whose name I haven't guessed). If you need the exact library-load mechanics (search path, versioning, failure mode on ABI mismatch), that's a "read `python/src/entropic/_bindings.py` directly" question rather than one the index settles.
