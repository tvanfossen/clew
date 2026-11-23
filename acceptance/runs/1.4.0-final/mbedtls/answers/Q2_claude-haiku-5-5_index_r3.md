**What it does.** `MBEDTLS_PRIVATE(member)` is a preprocessor macro defined in `include/mbedtls/private_access.h:14-18`:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

Every struct member in the public headers is written as `MBEDTLS_PRIVATE(foo)`. By default that renames the member to `private_foo`, so `ctx->foo` no longer compiles from application code. It is a soft encapsulation boundary. C has no `private`, so the structs stay visible in the header, but the names change and ordinary access breaks at build time. The `ssl.h` code shows the same thing: `ssl->MBEDTLS_PRIVATE(state)` (`include/mbedtls/ssl.h:5162`) is the sanctioned way to reach a field that is still reachable on purpose.

**Who it is for.** Mostly the application developer. The macro protects the library's internal layout from callers. It lets mbedtls change field names, types and ordering in a minor release without breaking code that reads or writes fields it never promised. The documented consumer of the escape hatch is the user who has no accessor: `docs/3.0-migration-guide.md:74` says to write `bar.MBEDTLS_PRIVATE(foo)` "at your own risk", and warns that such code "is likely to break in a future minor version."

**Who is opted out, and what that means.** The library itself is the one that gets the opt-out. `library/common.h:132` defines `MBEDTLS_ALLOW_PRIVATE_ACCESS` unconditionally, and nearly every library translation unit includes `common.h`, so inside the library `MBEDTLS_PRIVATE(x)` expands to plain `x`. The library can touch its own structs directly. The same macro is also defined in these places:

- `programs/ssl/ssl_server2.c:8` and `programs/ssl/ssl_client2.c:8` define it before any include. These sample/test programs read SSL context internals directly, so they are the "for whom" the question is looking for. They depend on the internal layout, and a layout change can break them.
- Two other places reference the macro (`programs/ssl/ssl_context_info.c` and `programs/fuzz/fuzz_dtlsserver.c` appear in the MBEDTLS_PRIVATE file list). Those files use `MBEDTLS_PRIVATE(...)` rather than the opt-out, so they get the renamed-member form and are not opted out.

**What this means for the code in those places.** In `library/` the struct accesses are plain `ctx->foo`. Renaming a field there is a normal refactor that the compiler checks. In the two SSL demo programs the access is also plain, so they build against the current layout. They would break if the library changed a field name, and they are the only downstream code in this tree that does this. Application code that does not define the macro gets a compile error on any direct field access, which is the intended protection.

**Caveat on the opt-out itself.** `ssl.h:5159-5169` says direct field access, including defining `MBEDTLS_ALLOW_PRIVATE_ACCESS`, is deprecated and "could be broken in any future release." The `ssl_server2.c` and `ssl_client2.c` programs are the existing exceptions to that deprecation, which is worth knowing if you ever change `ssl_context` field names.