**What it does:** Mbed TLS puts struct members in public headers, so any application could write `ssl->conf` or `cipher->iv_size`. `MBEDTLS_PRIVATE(member)` renames each member for outside code. In `include/mbedtls/private_access.h:15`, the default expansion is `private_##member`, so `ssl->MBEDTLS_PRIVATE(conf)` becomes `ssl->private_conf`. An application that touches `ssl->conf` directly therefore fails to compile instead of silently depending on the layout. The library can then rename or reorder fields without breaking callers who were only meant to use the accessors. The accessors are the supported path, for example `mbedtls_ssl_get_hostname()` and `mbedtls_ssl_session_get_id_len()` in `ssl.h`. The 3.0 migration guide describes direct member access as a last resort.

**Who the opt-out is for:** The gate is `#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS` in `private_access.h:14`. Defining that macro before the Mbed TLS headers are included makes `MBEDTLS_PRIVATE(member)` expand to plain `member`, so the code gets raw field access. The definition's doc says it lets the library reach its own structs' private members. In this tree it is defined in three places:

| Location | Who it covers | Effect |
|---|---|---|
| `library/common.h:132` | Library-internal code that includes this header | Raw member access in library sources |
| `programs/ssl/ssl_client2.c:8` | The `ssl_client2` test/sample program | Raw member access in that program |
| `programs/ssl/ssl_server2.c:8` | The `ssl_server2` test/sample program | Raw member access in that program |

In those places, `ssl->MBEDTLS_PRIVATE(conf)` and `ssl->conf` mean the same thing. The code is coupled to the struct layout, so a field rename breaks it at compile time, which is the intent for code shipped in the same tree. Applications outside the tree get the renamed members, and the inline getters in the public headers compile to the same field either way.

**Caveats:**
- I did not read the source around `common.h:132` or the `#define` lines in the two programs. I did not confirm whether the `#define` in each program comes before every mbedtls include, or whether `common.h` is included by every library `.c` file. The index reports the gate definitions, not their guards or include order.
- The index also lists `MBEDTLS_PRIVATE` as a function or variable in `aes.h` and `ctr_drbg.h`. I read those as parser artifacts from the member-name macro, not real symbols, and did not check them further.