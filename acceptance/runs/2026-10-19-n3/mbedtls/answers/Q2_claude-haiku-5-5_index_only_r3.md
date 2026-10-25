**What it does:** `MBEDTLS_PRIVATE(member)` wraps a public struct member name. In `include/mbedtls/private_access.h`, the default expansion is `private_##member` (line 15), so a field like `mbedtls_aes_context::MBEDTLS_PRIVATE(nr)` is actually named `private_nr`. An application that writes `ctx.nr` gets a compile error, and the library's internal layout is not part of the API. Fields can be renamed or reorganized without breaking callers who stayed on the public names. The header's own doc says the structs are publicly visible but their members "should not be accessed by the user."

**Who it's for:** application developers using the public headers. They are the default audience, and the rename is what keeps them out.

**Where the opt-out is turned on:** the gate is `MBEDTLS_ALLOW_PRIVATE_ACCESS`. When it is defined, the macro expands to plain `member` (line 17), so the real field names are visible. Its definitions in this tree are:

- `library/common.h:132`, the library's own shared header. Library sources that include it get real member names, so the rename never applies inside the library. The index does not record a guard around this line, so I can't confirm from the index alone that it is unconditional.
- `programs/ssl/ssl_client2.c:8` and `programs/ssl/ssl_server2.c:8`, the sample/test SSL programs. They opt out at the top of the file, which means they can read and write struct internals directly. The index does not show whether the define comes before the includes; that ordering is what makes the opt-out take effect.

**What this means for the code in those places:** the library and these two programs see the real field names, so they can touch internals the public API hides. Any change to those fields can break them without a compile error at the public boundary. Code outside those files, including anything an external application compiles, sees only the `private_` names.

**Caveat:** this comes from the index only. I did not read the source, so I haven't checked the surrounding `#if` guards or the include order.