Now I have the full picture. Let me answer.

## What `MBEDTLS_PRIVATE` accomplishes

`include/mbedtls/private_access.h`:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

Struct definitions in the public headers write their fields as `MBEDTLS_PRIVATE(state)` etc., which the preprocessor expands to a literal `private_state` token by default. So an **application** including `ssl.h` and writing `ssl->state` gets a compile error — there is no field literally named `state`, only `private_state`. This is a compile-time access-control shim bolted onto plain C structs (which have no real visibility keywords): the struct layout is still fully public in the header (ABI/sizeof needs are satisfied), but the *field names* are deliberately obfuscated so casual/direct member access from outside the library doesn't compile. It forces all access through the accessor functions (`mbedtls_ssl_get_state()`-style getters/setters) that the library provides, which is what lets mbedtls change internal struct layout across releases without an ABI-stability promise to callers who followed the rule — direct member reads/writes are the specific thing declared unstable and off-limits.

## For whom, and where the opt-out is actually flipped

The opt-out is `#define MBEDTLS_ALLOW_PRIVATE_ACCESS` before including the headers, which flips the macro back to `member` (no prefix), i.e. restores direct field access. In this tree it's turned on in exactly three places:

1. **`library/common.h:132`** — every `.c` file inside `library/` includes this, so **the library's own implementation code** gets private access to its own structs. The comment right above it says it plainly: *"structs defined in header files are publicly available, [but] their members are private and should not be accessed by the user"* — the library itself is not "the user"; it's exempted because it has to construct/inspect its own structs directly for performance and implementation reasons the accessor API doesn't need to expose.

2. **`programs/ssl/ssl_client2.c:8`** and **`programs/ssl/ssl_server2.c:8`** — these are the SSL test/demo programs. They opt in because they're written as **whitebox test harnesses** that poke at internal SSL context fields (e.ks., `ssl->state` per the comment at `include/mbedtls/ssl.h:5160-5166`) to test/demonstrate corner cases that the public accessor API doesn't cover.

So the barrier is aimed at ordinary applications linking against mbedtls: an app author who tries `ssl->state` gets a build failure and is pushed toward the stable getter/setter API. The library's own source and its own bundled test/sample programs are the only code in-tree granted the escape hatch, and `ssl.h`'s doc comment explicitly frames using that escape hatch from application code as "deprecated" and something that "could be broken in any future release" — i.e., opting out is tolerated for mbedtls-internal code and explicitly discouraged (unsupported) for everyone else.
