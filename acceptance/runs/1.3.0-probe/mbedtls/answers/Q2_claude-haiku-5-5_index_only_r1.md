**What it accomplishes:** `MBEDTLS_PRIVATE(x)` is a macro wrapper on struct member names. By default it expands to `private_x`, so the real field name no longer exists in the header. Code outside the library that writes `ctx.x` gets a compile error. Callers are pushed to the public accessor functions, and the library can rename or restructure internal fields without breaking them. The 3.0 migration guide calls direct field access "a last resort" and says you can reach a field only by writing `bar.MBEDTLS_PRIVATE(foo)`.

**Mechanism** (`include/mbedtls/private_access.h`):
- Line 14–16: `#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS` → `MBEDTLS_PRIVATE(member)` expands to `private_##member`. This is the default, so private fields are renamed.
- Line 16–18: `#ifdef MBEDTLS_ALLOW_PRIVATE_ACCESS` → it expands to `member`, so the real name is kept.

**Who opts out:** The switch is `MBEDTLS_ALLOW_PRIVATE_ACCESS`. In this tree it is defined in three places:
- `library/common.h:132`: the library's own sources define it. Library code therefore sees the real field names, which is how it can reach internal state across its own translation units.
- `programs/ssl/ssl_client2.c:8` and `programs/ssl/ssl_server2.c:8`: the test/sample SSL programs define it at the top of the file. These programs read and set internal TLS fields directly.

Nothing else in the index defines it. The index does not show the context around those lines, so I can't confirm the `library/common.h` define sits outside any conditional or that the programs' define precedes their includes. Those are worth a glance in the source.

**What that means in practice:** Code inside the library and the two SSL test programs can use plain field names. Any other consumer that defines `MBEDTLS_ALLOW_PRIVATE_ACCESS` before including the headers gets the same access, and the protection is only as strong as that define is controlled. It is a compile-time convention, not a security boundary. The protection is against accidental coupling by application code, not against a deliberate opt-out.