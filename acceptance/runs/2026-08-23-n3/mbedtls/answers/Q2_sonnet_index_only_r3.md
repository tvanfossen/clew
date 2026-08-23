I have everything the index can give here.

**Mechanism** (`include/mbedtls/private_access.h`):

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

Every struct field declared in a public header is written as `MBEDTLS_PRIVATE(foo)` instead of `foo`. By default that expands to `private_foo`, so any consumer of the public API who writes `ctx.foo` gets a compile error — the real name simply isn't `foo`. It's a compile-time access control on struct members that C has no native `private` keyword for: the struct layout is still exposed in the header (mbedTLS structs are all public, no opaque pointers), but the *names* are deliberately mangled so casual/direct member access breaks, forcing use of accessor functions instead. This is what lets the project change internal struct layout across versions without it counting as an ABI/API break for well-behaved callers — `mbedtls_aes_context::MBEDTLS_PRIVATE(nr)` etc. show up across `aes.h`, `aria.h`, `asn1.h`, `block_cipher.h`, and more (482 wrapped-member sites total per the index).

**The opt-out, and who flips it:** `MBEDTLS_ALLOW_PRIVATE_ACCESS`, when defined *before* including the header, flips the macro to a no-op (`member` unchanged), restoring direct access to real field names.

The index shows it's turned on in exactly one place in this tree: **`library/common.h`**, which documents itself as existing to "Allow library to access its structs' private members." `library/common.h` is the internal header pulled in by mbedTLS's own `library/*.c` implementation files — so the library's own source code defines the escape hatch for itself and accesses its own struct members directly by their real names (`ctx.nr`, not `ctx.private_nr`).

So concretely, "for whom":
- **External users / anyone consuming the public headers as-is** — no opt-out defined, `MBEDTLS_PRIVATE(member)` → `private_member`, direct field access doesn't compile. They're expected to go through accessor functions (`mbedtls_aes_get_...`, etc.) rather than touch struct internals.
- **mbedTLS's own library implementation (`library/*.c`, via `library/common.h`)** — opts itself back in, so its own code isn't hobbled by the same restriction it imposes on everyone else.

One gap the index can't close: I can't see from the graph alone whether `tests/` or `programs/` also define `MBEDTLS_ALLOW_PRIVATE_ACCESS` independently (the config-symbol search only surfaced `library/common.h` and the guard site itself in `private_access.h`) — if you need certainty there, that's a grep, not an index question.
