## Short answer

Python reaches the engine through **ctypes**, not a compiled extension. `librentropic.so` is loaded at runtime with `ctypes.CDLL`, and the Python package is a generated ctypes shim over the C ABI in `include/entropic/entropic.h`. The memory rules are documented in that header, but the generated Python binding drops the ownership information, and the Python package does not implement the free side. That leaves at least one confirmed leak path.

I did not build or run anything. The findings below come from reading the source and the index.

## How Python reaches the engine

```
python code
  └─ entropic (__init__.py)          PEP 562 lazy re-export of _bindings
       └─ _bindings.py               GENERATED ctypes shim (do not edit)
            │  _bind(name, restype, *argtypes) pins each signature
            └─ _loader.py → ctypes.CDLL("librentropic.so")
                 └─ C ABI: ENTROPIC_EXPORT functions in src/facade/entropic.cpp
                      └─ C++ engine (exceptions caught here, turned into error codes)
```

- **Library lookup** (`_loader.py`): `$ENTROPIC_LIB`, then `$ENTROPIC_HOME` (nested and flat layouts), then `~/.entropic/...`, then `ctypes.util.find_library`.
- **Generation** (`scripts/gen_bindings.py`): parses `entropic.h` and `types/*.h` by hand, with no pycparser, and emits `_bindings.py` and `_bindings_manifest.py`. Pre-commit runs `gen-bindings --check` and fails on drift.
- **Facade**: `__init__.py` only re-exports the raw functions. `hooks.py`, `streams.py` and `mcp.py` add callback wrappers. There is no `EntropicEngine` class.
- **Errors**: C++ exceptions do not cross the boundary. For example, `entropic_run` catches them and returns `ENTROPIC_ERROR_GENERATE_FAILED`, with the message stored per handle.

## Memory rules

The header (`entropic.h:30-38`, and `entropic_alloc`/`entropic_free` at 239-249) defines three categories:

| Category | Rule | How the Python binding handles it |
|---|---|---|
| **Owned `char*` returns** (e.g. `entropic_list_mcp_servers`) | Caller must free with `entropic_free()` | **Broken** (see below) |
| **Owned `char**` out-params** (e.g. `entropic_run`) | Caller must free `*result_json` with `entropic_free()` | Same problem: the raw pointer is lost unless read first |
| **Borrowed `const char*`** (e.g. `entropic_version`) | Static, or valid until the next call on that handle | Fine: `c_char_p` copies immediately |
| **Callback-scoped structs and args** (e.g. `EntDelegationResult`, token pointers) | Engine-owned, valid only during the callback | Copied with `string_at` during the call (`helpers.py:30`, `streams.py:71`), which is correct |
| **Buffers Python gives to C** (hook `modified_json`) | Must come from `entropic_alloc()` so the engine's `free()` matches | Correct: `hooks.py:159` allocates with `entropic_alloc`, and `hook_registry.cpp` calls `free()` |

Input strings: the binding passes `bytes` (`c_char_p`), so the buffer is only valid for the call. The header does not say whether the engine retains input pointers, so treat them as call-scoped.

`entropic_alloc` is `malloc` and `entropic_free` is `free` (`src/facade/entropic.cpp:1944-1956`). That pairing is what makes the hook handoff correct today.

## Confirmed problems

1. **Owned strings lose their pointer in the binding.** The generator's `CTYPE_MAP` maps every `char*` to `c_char_p`, whether owned or borrowed. A ctypes `c_char_p` restype converts the return value to `bytes` and discards the pointer, so the caller cannot call `entropic_free` on it. Sixteen owned-return functions are affected, including `entropic_list_mcp_servers`, `entropic_adapter_info`, `entropic_grammar_get`, `entropic_grammar_validate`, `entropic_profile_get`, `entropic_list_mcp_keys`, `entropic_get_identity_config` and `entropic_validation_last_result` (`_bindings.py:294-344`). Each call leaks.
2. **`char**` out-params leak the same way.** `entropic_run` and similar functions use `POINTER(c_char_p)`. Reading `out.value` copies the string and drops the original pointer. A caller must capture `ctypes.cast(out, c_void_p).value` before reading if they want to free it. Nothing in the package does this, and `entropic_free` is bound (`_bindings.py:262`) but never called from Python.
3. **Stale doc reference.** The header says `entropic_free_string` at lines 701 and 812, but no such symbol exists in the index. The function is `entropic_free`.

## Likely problems (not verified at runtime)

- **Hook registry keyed by raw handle address.** `hooks.py:84` stores `_bound` by handle address and never clears it on destroy. If a handle is destroyed and a new one gets the same address, `register_hooks` sees the old entries and skips registration, so the new handle silently has no hooks. `streams.py:44` has the same keying, but there it is only a keepalive and the overwrite is harmless.
- **Token callback truncation.** `TOKEN_CB` declares the token as `c_char_p`, and `streams.py` then reads `length` bytes from that value. If ctypes converts the argument to `bytes` by stopping at the first NUL, tokens with embedded NULs would be truncated. I think this is how ctypes behaves, but I did not test it.
- **Hook trampoline returns 1 even if `entropic_alloc` fails.** At `hooks.py:159-165`, `rc = 1` is set whether or not allocation succeeded, so the engine can treat the hook as having transformed the input when nothing was written.

## Suggested fixes

- In the generator, map owned `char*` returns to `c_void_p` and wrap them in a Python helper that copies the string and calls `entropic_free`. Keep `c_char_p` only for borrowed `const char*`. Add a test that checks each owned-return symbol is freed.
- Clear or key `_bound` and `_observers` by a unique handle token, not the raw address, and remove entries in a destroy hook.