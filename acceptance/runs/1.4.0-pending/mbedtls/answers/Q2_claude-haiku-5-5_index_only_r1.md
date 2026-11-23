**What it does:** `MBEDTLS_PRIVATE(member)` is a macro wrapper around struct field names in public headers. The header `include/mbedtls/private_access.h` defines it two ways, depending on whether `MBEDTLS_ALLOW_PRIVATE_ACCESS` is defined:

```
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS      (private_access.h:14)
#define MBEDTLS_PRIVATE(member) private_##member   (:15)
#ifdef  MBEDTLS_ALLOW_PRIVATE_ACCESS      (:16)
#define MBEDTLS_PRIVATE(member) member             (:17)
```

- **Default (opt-out not set):** `ctx.MBEDTLS_PRIVATE(nr)` becomes `ctx.private_nr`. The field is renamed in the public header, so user code that touches it fails to compile. The rename is the enforcement, not a comment.
- **With the opt-out:** the same token becomes `ctx.nr`, the real field name. The layout is identical either way; only the spelling changes.

The header's own doc says this is the point: structs are public so users can name them, but their members "are private and should not be accessed by the user." The 3.0 migration guide makes the same point as a compile-time break, and says direct access is a last resort (`bar.MBEDTLS_PRIVATE(foo)`).

**For whom:** the wrapper protects the library's internals from its users. The opt-out exists for the library's own translation units and for in-tree programs that need the fields.

Where the opt-out is turned on in this tree (the index shows the definitions; I did not check include order):

| Location | What it means |
|---|---|
| `library/common.h:132` | Internal header. Any library `.c` that includes it before `private_access.h` gets raw field names. This is the main "for whom": the library itself. |
| `programs/ssl/ssl_client2.c:8` | Test/example client. Defined at the top of the file, so it can read and write SSL context fields directly. |
| `programs/ssl/ssl_server2.c:8` | Same, for the server test program. |

Two caveats I could not settle from the index:

- **Include order matters.** `private_access.h` tests the macro when it is first included. If a library file includes it before `common.h`, the wrapper stays in its private form and that file still fails to compile. I did not check the include order.
- **Coverage of library files.** I did not confirm that every library `.c` includes `common.h`, or whether any library file defines the macro itself.

Consequence for those files: they are the only code that may read or write struct internals such as `mbedtls_aes_context` rounds or the SSL state. Any new code in them can depend on field layout; code outside them cannot. Changing a private field therefore breaks only the library and these two programs, not the public API. Outside callers have to use the public accessor functions.