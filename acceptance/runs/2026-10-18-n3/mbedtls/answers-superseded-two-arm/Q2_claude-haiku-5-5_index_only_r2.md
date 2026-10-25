**What it does:** `MBEDTLS_PRIVATE(member)` is a macro in `include/mbedtls/private_access.h` that wraps struct member names. By default it expands to `private_##member` (`private_access.h:15`), so a field such as `nr` in `mbedtls_aes_context` (`aes.h:64`) is renamed to `private_nr`. Code outside the library that writes `ctx->nr` then fails to compile. The header's own documentation says the structs are publicly visible, but their members are private and should not be accessed by the user (`library/common.h`, `MBEDTLS_ALLOW_PRIVATE_ACCESS` member docs). The 3.0 migration guide makes the same point: direct access to a private field is a compile error, and the fix is to use the accessor API.

The purpose is to keep the layout and field names of public structs out of the API contract. The library can change internals without breaking applications, and applications cannot silently depend on fields that were never promised.

**Who it is for:** the default is application code, the external user of the library. The wrapper is the enforcement.

**Where the opt-out is turned on.** The switch is `MBEDTLS_ALLOW_PRIVATE_ACCESS`. Its gate in `private_access.h` (lines 14–18) works like this:
- If it is **not** defined, `MBEDTLS_PRIVATE(m)` becomes `private_##m` (renamed, hidden).
- If it **is** defined, `MBEDTLS_PRIVATE(m)` becomes `m` (public name, no rename).

The index shows three places that define it:
1. `library/common.h:132`. This is the library's own shared header. Every library source that includes it gets the public field names, so library code reads and writes struct members directly.
2. `programs/ssl/ssl_client2.c:8`.
3. `programs/ssl/ssl_server2.c:8`.

**What that means for the code in those places:**
- Inside the library, the wrapper is a no-op. The protection applies only to outside users, not to the library's own translation units.
- The two SSL test/demo programs can reach internal SSL state directly. That is a deliberate exception for test and diagnostic tooling, not something an application should copy.
- The macro is not a user-facing Kconfig option. The index records `MBEDTLS_ALLOW_PRIVATE_ACCESS` with origin "undeclared," so it is a plain macro switch in source, not a documented build setting.

**Gaps the index cannot settle:**
- Whether `common.h:132` sits under its own guard, and whether `common.h` is always included before `private_access.h`. If it is not, the opt-out would not reach the wrapper. Verifying this needs the include order and the surrounding lines, which the index does not give me.
- Whether other test or tool sources define the macro. The index reports three definition sites, but unindexed files (Makefiles, CMake, test drivers) are outside its reach.
- The `MBEDTLS_PRIVATE` dossier lists a sample of usages, including `mbedtls_cipher_get_iv_size` and `mbedtls_pk_get_type`. The index holds 482 candidate identities for that name, so it cannot give a complete usage count.