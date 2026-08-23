Now I have the full picture. Let's lay it out.

## What `MBEDTLS_PRIVATE` does

`include/mbedtls/private_access.h` is a two-line switch:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

Struct fields in the public headers are declared as `int MBEDTLS_PRIVATE(state);`, which the preprocessor expands to `int private_state;` by default. So the field's *actual, linkable name* becomes `private_state` — an application source file that writes `ssl->state` gets a flat compile error (no such member), while `ssl->MBEDTLS_PRIVATE(state)` still resolves because the macro re-derives `private_state` at the call site.

This isn't access control in the security sense — there's no runtime enforcement and nothing hidden from the ABI. It's a **compile-time deterrent against relying on struct layout**. The header comment in `common.h:127-131` states the intent plainly: "structs defined in header files are publicly available, their members are private and should not be accessed by the user." mbedtls's structs are public (sizeof/layout visible for stack allocation), but the fields inside them are implementation detail that the maintainers want the freedom to rename, reorder, or move behind accessor functions across releases without it counting as an API break for external callers.

## Who gets the opt-out, and where it's actually flipped

`MBEDTLS_ALLOW_PRIVATE_ACCESS` un-mangles the names back to their real ones for whoever defines it before including the headers. Grepping the tree, it's turned on in exactly three places:

1. **`library/common.h:132`** — unconditionally `#define`s it. Every `.c` file in `library/` includes `common.h`, so **the library's own implementation always sees unmangled member names.** This makes sense: the library is the one place that's allowed to know its own layout — everywhere else, `MBEDTLS_PRIVATE` isn't there to stop the library from touching its own data, it's there to stop everyone downstream from doing so.
2. **`programs/ssl/ssl_client2.c:8`** and **`programs/ssl/ssl_server2.c:8`** — each defines it before any mbedtls include. These are the in-tree example/test SSL client and server programs, which historically poke at handshake internals (e.g. `ssl->state`) for test instrumentation and debug output that the public API doesn't expose. Rather than adding accessor functions for every internal field these test programs happen to want, they just opt out of the mangling for themselves.

`include/mbedtls/ssl.h:5163` documents this explicitly as an escape hatch of last resort: you *can* define `MBEDTLS_ALLOW_PRIVATE_ACCESS` and reach into `ssl->state` directly, but doing so is called out as deprecated, unsupported and "could be broken in any future release" — and the maintainers ask you to file an issue instead so they can add a real API rather than have you rely on layout.

So the "for whom": the mangling exists for **third-party application code** — anyone linking against mbedtls from outside the tree — to keep them off the struct internals and preserve the maintainers' freedom to change field layout without a major-version bump. The opt-out is granted, by design, only to **mbedtls itself** (`library/`, unconditionally) and to its **own bundled test/example SSL programs** (`ssl_client2`/`ssl_server2`, which need internal handshake state for test purposes) — not to any downstream consumer, even though nothing stops a user from writing the same `#define` before their own includes. The doc comment turns that theoretical availability into an explicit "don't, and tell us why if you must."
