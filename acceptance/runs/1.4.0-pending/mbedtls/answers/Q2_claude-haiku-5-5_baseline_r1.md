**Short answer:** `MBEDTLS_PRIVATE` is a compile-time guard for application developers. It doesn't enforce access control. The guard is off inside the library and in a few in-tree programs, and those are the places where the opt-out is turned on.

## What the macro does

`include/mbedtls/private_access.h:14-18`:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

Public headers declare private fields as `MBEDTLS_PRIVATE(foo)`. Without the define, the field is really named `private_foo`, so `ctx->foo` in application code fails to compile. With the define, the field is named `foo`.

This accomplishes three things:

- **Accidental access becomes a compile error.** Application code can't reach internals by mistake and then break on the next minor release.
- **Maintainers can rename or reshape private fields** without it counting as a source-level break.
- **The escape hatch is visible.** `bar.MBEDTLS_PRIVATE(foo)` expands to `bar.private_foo`, so it compiles from outside. `docs/3.0-migration-guide.md:74` calls this "at your own risk," and `include/mbedtls/ssl.h:5159-5169` calls direct access deprecated.

It is not a security boundary. The struct layout, `sizeof`, and field offsets stay public in the header, and anyone can spell the explicit form.

## Who the opt-out is for

The protected party is the external user. The opt-out goes to code that ships in the same tree as the library.

| Location | How it is turned on | What it means |
|---|---|---|
| `library/common.h:132` | Unconditional `#define MBEDTLS_ALLOW_PRIVATE_ACCESS` | Every library `.c` that includes `common.h` (all but `ecp_curves_new.c` and `ssl_debug_helpers_generated.c`) sees the real field names. Library code is never guarded. |
| `programs/ssl/ssl_server2.c:8` | Blanket define before any include | The whole translation unit can touch private fields. `ssl_server2.c:4239` reads `ssl.session->id`, which is `MBEDTLS_PRIVATE(session)` in `ssl.h:1800`, and it only compiles because of this define. |
| `programs/ssl/ssl_client2.c:8` | Same blanket define | `ssl_client2.c:3214` reads `ssl.conf->early_data_enabled`, which is `ssl.h:1668`. Same effect. |

Two more points about these:

- **The `common.h` opt-out depends on include order.** The macro is expanded when the public header is parsed. Each library `.c` that uses it includes `common.h` first (checked in `ecdh.c`, `md.c` and `x509_crt.c`). If a `.c` included a public struct header before `common.h`, its field names would not match and the build would fail. That fails loudly, but it is a rule a new file can break.
- **The `ssl_server2`/`ssl_client2` define hides the accesses from audit.** A `grep MBEDTLS_PRIVATE` finds nothing in those two files, so new private accesses there are invisible. In that file, the rule is "compiles," not "is marked as deliberate."

For contrast, `programs/ssl/ssl_context_info.c:553-568`, `programs/fuzz/fuzz_dtlsserver.c:138`, and the `tests/suites/*.function` files do not define the opt-out. They use the explicit `MBEDTLS_PRIVATE(...)` spelling at each access. That is the form the migration guide describes, and it stays visible in grep. I did not trace whether the generated test `.c` files pull in `common.h`.

## What this means for the code

- **Library `.c` files** can use real field names. The header rename applies to them only through the same macro, so refactors of private fields stay consistent.
- **`ssl_server2.c` and `ssl_client2.c`** are coupled to `mbedtls_ssl_context` internals. Changing those fields breaks these programs at compile time, and they will not be flagged as deliberate in review. If you change `session`, `conf`, or `early_data_enabled`, check these two files.
- **External applications** that copied the `ssl_server2` pattern (define `MBEDTLS_ALLOW_PRIVATE_ACCESS` and read `ssl.session`) get no compatibility promise. The header comment says direct access may break in any future release. In the 3.6 LTS line, the migration guide expects more stability, but not a guarantee.