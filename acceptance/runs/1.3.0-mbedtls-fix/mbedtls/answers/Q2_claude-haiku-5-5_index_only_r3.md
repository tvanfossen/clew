**What it does.** `MBEDTLS_PRIVATE(member)` is a macro that renames a struct member so ordinary code can't reach it by name. From `include/mbedtls/private_access.h`:

```c
#define MBEDTLS_PRIVATE(member)  private_##member   /* default: member is renamed */
#define MBEDTLS_PRIVATE(member)  member             /* when MBEDTLS_ALLOW_PRIVATE_ACCESS is defined */
```

Every struct member in the public headers is written as `MBEDTLS_PRIVATE(foo)`, so a user who writes `ctx->foo` gets a compile error. The header's own description is "Macro wrapper for struct's members." The effect is that the library can change a struct's layout, rename or remove fields, and add fields in a patch release without that being a source or binary break for applications. The migration guide (`docs/3.0-migration-guide.md`, "Most structure fields are now private") gives the same reason and says direct access is a last resort: `bar.MBEDTLS_PRIVATE(foo)`.

**Who it's for.** Two audiences:
- **Applications** get the protection. They use the accessor functions (e.g. `mbedtls_ssl_get_version_number`, `mbedtls_ssl_session_get_id_len`) instead of fields.
- **The library itself** needs direct field access. The opt-out is the switch for that.

**Where the opt-out is turned on in this tree.** `MBEDTLS_ALLOW_PRIVATE_ACCESS` is defined at:
- `library/common.h:132`. This is the library's own build-wide opt-out, so library `.c` files see the real member names.
- `programs/ssl/ssl_client2.c:8` and `programs/ssl/ssl_server2.c:8`. These sample/test programs opt out too.

**What that means for the code in those places.**
- Inside the library (`library/*.c`), code such as `library/ecdh.c:150` (`ctx->MBEDTLS_PRIVATE(grp).id`) and `library/x509_crt.c:3306` reads fields directly. Those accesses only compile because the opt-out is on there. If `common.h` were not included first, they would fail.
- The two SSL programs reach into library internals directly. They are coupled to the struct layout of the version they are built against, so they must be rebuilt with the library. That is acceptable for in-tree tools, but it is the reason they should not be copied as examples for application code.
- Any new application code that defines `MBEDTLS_ALLOW_PRIVATE_ACCESS` before including mbedtls headers takes on that layout coupling and can break on upgrades.

**Caveats from the index.**
- I did not confirm from the index that `library/common.h:132` is unconditional, or that every library `.c` includes `common.h` before the public headers. Those are the conditions that make the opt-out work across the library.
- `search` returned 50 hits for `MBEDTLS_PRIVATE`, which is a capped list. The `ecdh.c` and `x509_crt.c` lines above are examples from that list, not a complete census of library call sites.
- The `callers` data for the macro is ambiguous: it matches 336 signatures, so I cannot attribute specific callers to specific functions from the index alone.