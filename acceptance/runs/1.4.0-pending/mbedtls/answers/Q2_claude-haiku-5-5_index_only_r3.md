**What it accomplishes:** `MBEDTLS_PRIVATE(member)` is a macro in `include/mbedtls/private_access.h:15`. By default it expands to `private_##member`, so `ssl->MBEDTLS_PRIVATE(state)` becomes `ssl->private_state`. Application code that writes `ssl->state` no longer compiles, because the real field name is mangled. The point is to stop applications from depending on struct layout, so the library can rename, reorder, or change fields in a minor release without breaking callers. The migration guide says the same: "Attempting to access a private field directly will result in a compilation error" (`docs/3.0-migration-guide.md`, "Most structure fields are now private"). It also describes direct access as a "last resort."

Almost every public accessor in the tree is written this way. Examples: `mbedtls_ssl_is_handshake_over` (`ssl.h:5148`), `mbedtls_ssl_get_hostname` (`ssl.h:4144`), `mbedtls_cipher_get_name` (`cipher.h:769`), and the `psa_get_key_*` / `psa_set_key_*` helpers in `psa/crypto_struct.h`. The accessors live inside the library's own headers and reach into the struct for the caller.

**The opt-out:** `private_access.h:14-18` is a two-branch gate on `MBEDTLS_ALLOW_PRIVATE_ACCESS`.
- If it is **not** defined, `MBEDTLS_PRIVATE(m)` → `private_m` (the default, mangled).
- If it **is** defined, `MBEDTLS_PRIVATE(m)` → `m` (plain access).

The index shows the macro defined in exactly three places:

| Location | Who it is |
|---|---|
| `library/common.h:132` | Internal library header. The library turns the gate on for itself. |
| `programs/ssl/ssl_client2.c:8` | Test/debug client program |
| `programs/ssl/ssl_server2.c:8` | Test/debug server program |

It is not set in any config header, `.clew.yaml`-style file, or Kconfig file that the index can see. The gate is "undeclared" in the index's terms, so it is not a documented public config option.

**What this means for those places:**
- **Library internals** (`library/*.c`, via `common.h`) can read and write fields directly, e.g. `ecdh.c:150` uses `ctx->MBEDTLS_PRIVATE(grp).id`, which becomes `ctx->grp.id`. This is the intended use: the library is the owner of the layout, so it is the one party allowed to depend on it. Any field rename in the library has to be done consistently across these files, because the compiler will catch mismatches only within the library's own build.
- **`ssl_client2.c` and `ssl_server2.c`** can poke at SSL internals for testing and debugging. They are test drivers, not application examples. Application code that copies this pattern is depending on fields that may change without a version bump.
- **Everyone else** (external applications) gets the mangled name and a compile error if they reach into a field.

**Caveats I could not verify from the index:**
- The index does not show the `#define` ordering in `ssl_client2.c` / `ssl_server2.c`. The opt-out only works if line 8 precedes the mbedtls includes, which is the usual pattern but is an inference.
- I could not confirm that every file under `library/` includes `common.h`. If any library file does not, it would see the mangled names and fail to build, so the claim "the library opts out" should be checked by reading the include lines.