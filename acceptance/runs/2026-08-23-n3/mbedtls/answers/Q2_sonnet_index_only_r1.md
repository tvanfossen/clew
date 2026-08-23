This gives a concrete, complete picture. Here's what the index shows.

**Mechanism** (`include/mbedtls/private_access.h`): `MBEDTLS_PRIVATE(member)` is a macro that struct-field declarations in the public headers are wrapped in — e.g. `int MBEDTLS_PRIVATE(nr);` inside `mbedtls_aes_context`. The macro is gated by an `#ifndef`/`#ifdef` pair on `MBEDTLS_ALLOW_PRIVATE_ACCESS`:

- If `MBEDTLS_ALLOW_PRIVATE_ACCESS` is **not** defined, `MBEDTLS_PRIVATE(member)` expands to `private_##member` — so `nr` becomes the field name `private_nr`. Any external code written against the "obvious" field name (`ctx.nr`) simply fails to compile.
- If it **is** defined, `MBEDTLS_PRIVATE(member)` expands to just `member` — the field keeps its real, natural name and is directly accessible.

So the wrapper doesn't add real C access control (there's no `private:` in C) — it's a compile-time tripwire. `library/common.h:132` documents the intent directly: "Although structs defined in header files are publicly available, their members are private and should not be accessed by the user." Renaming the field is what turns "should not" into "does not compile."

**Who the opt-out is turned on for**, per the macro's own `gated_by`/definition sites recorded in the index:

1. **`library/common.h:132`** — `#define MBEDTLS_ALLOW_PRIVATE_ACCESS`. This header is pulled into the library's own `.c` translation units. So **mbedtls's own library implementation** defines the opt-out for itself, meaning internal code accesses struct fields by their real names (`ctx.nr`, not `ctx.private_nr`).
2. **`programs/ssl/ssl_client2.c:8`** and **`programs/ssl/ssl_server2.c:8`** — the same `#define` appears at the top of these two sample/test programs, before they include any mbedtls headers.

That's the whole set the index finds. The implication: everyone else — a genuine third-party application linking against the public headers without that `#define` — gets the name-mangled `private_*` fields and is expected to go through the public accessor API rather than touch struct internals directly. `ssl_client2.c`/`ssl_server2.c` are two of mbedtls's own bundled example/test programs, so they've deliberately opted back into direct-field access (likely because they're used for interop/fuzz/regression testing and want to poke at internals the public API doesn't expose) — they are not evidence that "normal" applications are meant to do the same. The convention name (`MBEDTLS_ALLOW_PRIVATE_ACCESS`) and the doc comment both frame this as an explicit, deliberate opt-out for code that accepts it's binding itself to internals that can change across versions, not a general permission.

One gap: the index can tell me the opt-out is `#define`d in exactly these three files' first ~10 lines, but it can't read the surrounding comment in `ssl_client2.c`/`ssl_server2.c` explaining *why* those two programs specifically need it — that would take reading the source directly.
