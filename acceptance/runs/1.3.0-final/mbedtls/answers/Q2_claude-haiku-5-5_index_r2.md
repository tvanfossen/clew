**What it accomplishes.** `include/mbedtls/private_access.h` is the whole mechanism. Without `MBEDTLS_ALLOW_PRIVATE_ACCESS`, `MBEDTLS_PRIVATE(member)` expands to `private_##member`, so `ctx->MBEDTLS_PRIVATE(state)` becomes `ctx->private_state`. Ordinary code that writes `ctx->state` no longer compiles. The 3.0 migration guide (`docs/3.0-migration-guide.md:68-74`) describes this as the intent: direct access to undocumented fields gives a compile error, and callers should use the accessors (`mbedtls_<MODULE>_{get,set}_<FIELD>`). It is a source-level compatibility boundary, not a security one. The struct layout is unchanged, and `ctx->private_state` still compiles for anyone who types it. The benefit is that the team can reshape internals in a minor release without breaking callers who stayed on the public surface.

**Who it is for.** Three groups, by where the opt-out is switched on:

| Where | Opt-out | Effect on that code |
|---|---|---|
| Application code (default) | none | Field access is a compile error. It must use an accessor, or the last-resort `MBEDTLS_PRIVATE(foo)` form, which the guide says is at the caller's own risk. |
| Library sources | `library/common.h:132` defines `MBEDTLS_ALLOW_PRIVATE_ACCESS` | Every library `.c` includes `common.h`, and `ssl_misc.h` includes it before `mbedtls/ssl.h` (`library/ssl_misc.h:14`). Internal code uses real field names. |
| Two sample programs | `programs/ssl/ssl_server2.c:8` and `ssl_client2.c:8` define it before any include | They use the real names, as in-tree test harnesses. |

The opt-out is the one place the library's "private" fields become "internal." A project that defines the macro itself gets the same access, and `ssl.h:5159-5169` labels that path deprecated and unsupported for future releases.

**Code that uses the escape hatch without opting out.** These compile against the renamed `private_*` names, so they are the places a future rename would break:
- `programs/ssl/ssl_context_info.c:553-568` reads `ciphersuite_info->MBEDTLS_PRIVATE(flags|cipher|mac)`.
- `programs/fuzz/fuzz_dtlsserver.c:138` reads `ssl.MBEDTLS_PRIVATE(next_record_offset)`.

**Header inlines.** The accessors in public headers, such as `ssl.h:2824` and `psa/crypto_struct.h:416`, use `MBEDTLS_PRIVATE` internally. Those work in both modes because the struct definition and the accessor expand the same way.

**Caveat.** I did not build the test suites. That tests get the opt-out is inferred from the include chain: `test_suite_ssl.function` includes `ssl_misc.h`, which pulls in `common.h`.