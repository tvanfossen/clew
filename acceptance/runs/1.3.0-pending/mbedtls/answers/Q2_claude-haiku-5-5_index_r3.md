**What it does.** `include/mbedtls/private_access.h` is 20 lines. Unless `MBEDTLS_ALLOW_PRIVATE_ACCESS` is defined, `MBEDTLS_PRIVATE(member)` expands to `private_##member`, so the struct field is renamed. The public header writes `int MBEDTLS_PRIVATE(state);` (`include/mbedtls/ssl.h:1737`), and a caller who writes `ssl->state` gets a compile error. Only the spelling `ssl->MBEDTLS_PRIVATE(state)` (or `private_state`) reaches the field.

This is a speed bump, not a security boundary. Anyone can type the mangled name. Its job is to make "this is not API" visible in code review and grep, and to tell users that direct access is unsupported. The header's own comment at `ssl.h:5159-5169` says direct access to `ssl->state` is deprecated and "could be broken in any future release." Renaming a field does not change the struct layout, so the opt-out is a source-level switch, not an ABI change.

**For whom.** There are three audiences in this tree.

| Who | Setting | Effect |
|---|---|---|
| Application developers (default) | none | Fields are renamed. They must write `MBEDTLS_PRIVATE(x)` to reach a field, and that is documented as deprecated. |
| The library itself | `library/common.h:132` defines it unconditionally | `MBEDTLS_PRIVATE(x)` becomes plain `x` in every library `.c` that includes `common.h`. |
| Test harness programs | `programs/ssl/ssl_server2.c:8`, `ssl_client2.c:8` | Defined as the first line, before `ssl_test_lib.h`, so these programs read internals directly. |

**Where the opt-out is turned on, and what it means there.**

- **Library (`library/common.h:132`).** About 60 library sources include `common.h`, such as `ssl_tls12_server.c:8` and `x509_crt.c:20`. In those files the library reads internals as plain names; for example `ssl_tls12_server.c:4200` uses `switch (ssl->state)`. The library may rename or reshape its own fields without touching library code, but its code is then tied to the internal layout.
- **Test harness programs.** `ssl_server2.c` and `ssl_client2.c` are the only programs that opt out, and they do it on purpose so the test driver can inspect handshake state.
- **Ordering caveat.** The guard in `private_access.h` means the first inclusion decides the macro. The opt-out only works in a translation unit where the define comes before any public header that pulls in `private_access.h`. The two programs do this correctly. I checked `x509_crt.c` and it includes `common.h` first. I did not check every library file.

**The default-access side, which is not opted out.**

- `programs/ssl/ssl_context_info.c:553-568` reads `ciphersuite_info->MBEDTLS_PRIVATE(flags)` and similar fields. It defines no opt-out, so this is the correct external-code pattern: the spelling matches the renamed member.
- `tests/suites` uses the wrapper where it needs fields (one hit each in `test_suite_psa_crypto.function` and `test_suite_x509write.function`). The tests do not opt out.

In short, the wrapper is for external code and for anyone who should see that a field is internal. The opt-out belongs to the library and to its two in-tree test programs, which are built together with the headers and can be updated in lockstep.