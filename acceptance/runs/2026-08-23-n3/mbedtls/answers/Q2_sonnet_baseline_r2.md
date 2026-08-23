Enough evidence. Here's the answer:

**What `MBEDTLS_PRIVATE` accomplishes**

`include/mbedtls/private_access.h` defines it as a tiny compile-time switch:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

Public struct definitions (e.g. `mbedtls_ssl_context` in `include/mbedtls/ssl.h`, dozens of other structs across the public headers — 49 uses of the macro in `ssl.h` alone) declare their fields as `MBEDTLS_PRIVATE(member)` instead of `member`. By default that macro expands the field name to `private_foo`, not `foo`. So any application code that does `ssl.state` or `ctx.endpoint` simply fails to compile — the struct is still laid out and visible in the header (mbedTLS needs that for callers to allocate it on the stack/embed it), but the *field names* the API promises don't exist unless the caller opts in. It's a compiler-enforced way of saying "this struct is public for allocation purposes only; its members are implementation detail, use the accessor functions." This is what backs mbedTLS's stated ABI/API stability policy — struct layout can still change between minor versions because no supported caller is touching fields directly, only accessor functions like `mbedtls_ssl_get_...`.

**Who is allowed to opt out, and where it's actually turned on in this tree**

The opt-out is `#define MBEDTLS_ALLOW_PRIVATE_ACCESS` before including the headers, which flips the macro back to identity (`member`). Grepping the tree, it's defined in exactly four places:

- `library/common.h:132` — every file in `library/` includes this, so **the library's own implementation code** gets direct field access everywhere. That's the intended audience: mbedTLS's own internals are exempt because they *are* the code that's allowed to depend on the current layout.
- `programs/ssl/ssl_client2.c:8` and `programs/ssl/ssl_server2.c:8` — two of the sample/test programs shipped in `programs/ssl/`, which historically reach into `ssl_context` fields for test instrumentation (e.g. inspecting negotiated parameters) rather than going through the public accessor API.

So concretely: for ordinary application code linking against mbedTLS, the field names are inaccessible by design — you must use the accessor functions. For code inside this repository's own `library/` tree, and for these two particular sample programs, the macro is defined ahead of time so the private-name mangling never applies and the raw field names work as if the guard weren't there at all. It's an internal escape hatch, not a general-purpose one — a comment above the `common.h` definition (line 127-131) says as much: "Although structs defined in header files are publicly available, their members are private and should not be accessed by the user" — "the user" being anyone outside `library/` and those two sanctioned test programs.
