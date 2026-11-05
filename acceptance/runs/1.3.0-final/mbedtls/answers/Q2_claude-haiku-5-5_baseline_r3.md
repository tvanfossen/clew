**What it does.** `include/mbedtls/private_access.h` is the whole mechanism:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

Public structs are declared as `int MBEDTLS_PRIVATE(foo);`, which means the field is named `private_foo` for anyone who doesn't opt out. Code that writes `ctx->foo` fails to compile, and `ctx->private_foo` is the only spelling left, which signals that the field is not part of the API. The header is a rename, not an access control. Anyone can define the macro, so it protects against accidental coupling, not against deliberate access.

**Who it's for.** It serves the library's maintainers and its application users. The library can rename, reorder, or remove internal fields without that being an API change. Application code that reaches into internals breaks at compile time, which is much better than breaking silently at runtime. `include/mbedtls/ssl.h:5159-5169` shows this in practice: it documents `ssl->state` as deprecated and says that `ssl->MBEDTLS_PRIVATE(state)` or defining the opt-out can break "in any future release."

**Where the opt-out is turned on in this tree (4 places):**

| Location | What it does |
|---|---|
| `library/common.h:132` | Defines `MBEDTLS_ALLOW_PRIVATE_ACCESS` unconditionally. Library sources include `common.h` before the public headers (e.g. `library/aes.c:14` before `mbedtls/aes.h` at line 20), so the library sees real member names everywhere. |
| `programs/ssl/ssl_server2.c:8` | Defined before `ssl_test_lib.h`, so the whole translation unit has full field access. |
| `programs/ssl/ssl_client2.c:8` | Same, for the client sample/test driver. |

No CMake, Make, or other build file defines the macro globally. The grep across the repo finds only these four hits.

**What this means for the code in those places:**

- **`library/*`:** This is the intended insider use. Library code must reach its own internals, and `common.h` grants that. Because the define is in an internal header that is not installed, external users don't get it by including the public headers.
- **`ssl_server2.c` / `ssl_client2.c`:** They are compiled against the public headers but read and write internal SSL state, including the deprecated `ssl->state` that `ssl.h` warns about. The opt-out is per translation unit and applies to the whole file. These programs are the in-tree test drivers, so the team's CI will catch breakage when internals change. The downside is that they are sample code, and copying them means copying a dependence on internals that the library explicitly reserves the right to change.
- **Tests:** `tests/suites/*.function` use `MBEDTLS_PRIVATE(...)` directly (only two files do), which works either way because the same macro expands on both sides.

Two tool results in this session contained text suggesting I use a "dossier" lookup tool. That is not part of your request and I did not use it.