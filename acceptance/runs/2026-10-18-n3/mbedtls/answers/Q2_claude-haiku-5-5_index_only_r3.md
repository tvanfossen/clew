**What it does.** `MBEDTLS_PRIVATE(member)` is a preprocessor macro (`include/mbedtls/private_access.h:15`) that wraps struct member names in public headers. By default it expands to `private_##member`, so `ctx.MBEDTLS_PRIVATE(iv_size)` becomes `ctx.private_iv_size`. The member is renamed, not hidden by C access rules, so user code that reaches for it fails to compile. The layout doesn't change, so ABI is unaffected. The intent is to stop applications from depending on internals that Mbed TLS can change between releases. The 3.0 migration guide describes it as a last resort for code that must reach a field (`docs/3.0-migration-guide.md`, "Most structure fields are now private"). The wrapped members are in headers such as `ssl.h`, `bignum.h`, `ctr_drbg.h`, `rsa.h`, `gcm.h`, `ccm.h`, `aes.h` and the PSA headers.

**The opt-out.** The header's own guard decides which expansion you get (`private_access.h:14-18`):

- If `MBEDTLS_ALLOW_PRIVATE_ACCESS` is **not** defined, `MBEDTLS_PRIVATE(member)` → `private_##member`. The field is hidden.
- If it **is** defined, `MBEDTLS_PRIVATE(member)` → `member`. The field is plain and accessible.

The macro is defined in three places in this tree:

| Location | Who it covers |
|---|---|
| `library/common.h:132` | Mbed TLS's own library sources |
| `programs/ssl/ssl_client2.c:8` | The `ssl_client2` sample/test program |
| `programs/ssl/ssl_server2.c:8` | The `ssl_server2` sample/test program |

**What that means for those places.**

- **Library sources:** the library code reads and writes internal fields directly. The `library/common.h` definition is what lets every library `.c` file do that without the private-name indirection. Only the library itself is affected here; external consumers that include the public headers are not.
- **The two SSL programs:** they set the opt-out at the top of the file, before their includes, so they can inspect and manipulate SSL internals (handshake state and similar) for testing and diagnostics. This is the only way the tree's own programs get past the wrapper.
- **Everyone else** (applications linking the library) gets `private_*` names and a compile error on direct field access. Defining the macro in your own code would work but is unsupported. The public API is the supported route.

**Caveats from the index.**

- The index doesn't show the conditional context around `library/common.h:132`. The index records the definition but not whether it's unconditional, so I can't confirm from here whether the library always opts out or only in some builds. Check the lines around it.
- The index reports `MBEDTLS_ALLOW_PRIVATE_ACCESS` as `origin: undeclared`, and the index was built with only the threading macros set, so it doesn't show the repository's own default configuration.