**What it accomplishes:** `MBEDTLS_PRIVATE(member)` is a rename, not an access check. In `include/mbedtls/private_access.h`, when `MBEDTLS_ALLOW_PRIVATE_ACCESS` is not defined, the macro expands to `private_##member` (line 15). So a struct field written as `ssl->MBEDTLS_PRIVATE(state)` is actually named `private_state`. Code outside the library that writes `ssl->state` no longer compiles. The header's own docs say the same: the structs are public, but "their members are private and should not be accessed by the user" (`library/common.h`, the `MBEDTLS_ALLOW_PRIVATE_ACCESS` doc block). The intent is to stop callers from depending on layout, so the library can change fields without breaking an ABI or API.

The public inline accessors in the headers are written against the macro, so they compile in both modes. Examples from the index: `mbedtls_ssl_conf_max_tls_version` writes `conf->MBEDTLS_PRIVATE(max_tls_version)` (`include/mbedtls/ssl.h:4463`), `mbedtls_cipher_info_get_name` reads `info->MBEDTLS_PRIVATE(name)` (`include/mbedtls/cipher.h:511`), and the `psa_*_key_*` attribute helpers in `include/psa/crypto_struct.h` go through it too. Users get the stable accessor functions, and the field names stay hidden.

**Who the opt-out is for:** The gate is `MBEDTLS_ALLOW_PRIVATE_ACCESS`. The index finds it defined in three places, and nowhere else:

| Location | Line | Who it is |
|---|---|---|
| `library/common.h` | 132 | The library's own internal sources |
| `programs/ssl/ssl_client2.c` | 8 | Bundled sample/test client |
| `programs/ssl/ssl_server2.c` | 8 | Bundled sample/test server |

Defining it before the headers are included makes `MBEDTLS_PRIVATE(x)` expand to the real name `x`, so those translation units read and write fields directly. The two `programs/ssl` files are the only code outside the library that gets this access.

**What that means for those files:**
- The library internals are the intended exception. They are built against the same struct layout, so they must see real names.
- The two sample programs are the notable case. They are not library code, but they reach into `ssl` and `conf` internals. A field rename or layout change in `ssl.h` can break those programs even though a normal application would be protected. Treat them as a coupling point, not as an example of supported API usage.
- Any new file that defines the gate gets the full struct internals, and no compiler error will tell you it did.

**Limits of what I could confirm from the index:**
- The gate is `origin: undeclared`. It is not a Kconfig symbol and it is not in any config header the index knows about, so it is a per-translation-unit switch set in source, not a build option.
- The index does not show whether `library/common.h:132` sits under an `#if`. If it is unconditional, every library source that includes `common.h` gets direct access. I could not check that from the index alone.
- `ssl_client2.c` and `ssl_server2.c` define the gate at line 8. I did not verify whether they include the library headers before or after that line, which determines whether the define takes effect. Their line numbers suggest it is placed before the includes.