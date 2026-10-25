**What it accomplishes:** `MBEDTLS_PRIVATE(member)` wraps a struct field name in the header so that the field is only reachable by its real name when a build opts in. `include/mbedtls/private_access.h` has two branches gated on `MBEDTLS_ALLOW_PRIVATE_ACCESS`:

- **Default (macro not defined), lines 14–16:** `MBEDTLS_PRIVATE(member)` expands to `private_##member`. The field is renamed, so code that writes `ctx->nr` fails to compile. Only accessors and internal code that use the new name can touch it.
- **Opt-in (macro defined), lines 16–18:** `MBEDTLS_PRIVATE(member)` expands to `member`. Field names are unchanged.

So the mechanism is a compile-time guard against direct field access. It is not a runtime or ABI protection. The intent is that consumers go through the public functions, and the library can change internal layouts without breaking callers who stuck to the API.

**Who the opt-out is for:** The index shows `MBEDTLS_ALLOW_PRIVATE_ACCESS` defined in exactly three places:

| Location | What it means |
|---|---|
| `library/common.h:132` | The library's own internal sources get raw field names. This is the main opt-out for the library. |
| `programs/ssl/ssl_client2.c:8` | The sample client can reach struct internals directly. |
| `programs/ssl/ssl_server2.c:8` | The sample server can reach struct internals directly. |

External consumers get the renamed `private_` fields unless they define the macro themselves before including mbedtls headers. Doing so is an explicit choice to depend on internals.

**Caveats from the index:**
- The three definitions show no enclosing `#if` gate, so I read them as unconditional. The index does not record include order, though. If `common.h` is included after a public header in some library file, that file would still see the renamed fields. I could not confirm this from the index alone.
- The index was built with only `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` set, and no config header is recorded. So I cannot say whether the opt-out is on in the repository's default configuration.
- The index shows `mbedtls_cipher_get_iv_size` and `mbedtls_pk_get_type` referencing the macro. These are library accessors that read wrapped fields and are the sanctioned path for outside code.