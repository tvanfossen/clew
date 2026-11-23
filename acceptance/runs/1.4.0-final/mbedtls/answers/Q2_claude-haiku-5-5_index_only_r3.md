**What it does.** `MBEDTLS_PRIVATE(member)` is a macro in `include/mbedtls/private_access.h`. Its body depends on whether `MBEDTLS_ALLOW_PRIVATE_ACCESS` is defined:

- **Not defined (the default for users):** `MBEDTLS_PRIVATE(member)` expands to `private_##member`. So `ssl->MBEDTLS_PRIVATE(state)` becomes `ssl->private_state`, and user code that writes `ssl->state` fails to compile. The 3.0 migration guide says the same: "Attempting to access a private field directly will result in a compilation error."
- **Defined:** it expands to plain `member`, and the field is accessible by its real name.

The point is to keep struct layout and field names out of the public contract. The structs are still declared in public headers, so the layout is visible, but the names are mangled and users are steered to the accessor functions. That lets the library change internal fields without breaking callers who were reaching into them. It is a source-level convention, not a security boundary: anyone who defines the gate macro gets access.

**Who it is for.** The default is for application code. The opt-out is for the library itself and for a few bundled programs.

Where the opt-out is turned on, per the index:

| Location | What it does |
|---|---|
| `library/common.h:132` | `#define MBEDTLS_ALLOW_PRIVATE_ACCESS`. The index shows no enclosing conditional, so every library translation unit that includes `common.h` gets direct field access. |
| `programs/ssl/ssl_client2.c:8` | Defined before the includes, so this sample/test client can reach internal SSL fields. |
| `programs/ssl/ssl_server2.c:8` | Same, for the server. |

For those translation units, `MBEDTLS_PRIVATE(x)` is just `x`, so the code reads and writes fields directly. The library's own `.c` files use the macro this way. Its inline accessors in public headers (for example `mbedtls_ssl_conf_get_endpoint` at `ssl.h:2126`) also use it, but those are compiled into user code too, so they resolve to `private_*` names there. That works only if the struct declarations use the same macro, so the two sides always agree.

**What this means in practice.** Inside the library and in those two programs, a field change is a plain edit with no accessor needed. In user code, the only supported route is the public accessors and setters. Defining `MBEDTLS_ALLOW_PRIVATE_ACCESS` in an application is possible but unsupported: the field names and layout are not covered by the API stability promise.

**Caveats.** The index's `referenced_by` list for `MBEDTLS_PRIVATE` shows only two callers, so it is not a complete census of uses. I did not read the `library/common.h` line itself, so I cannot confirm whether it is inside an `#if`. The index reports no gate on it, which is why I say "unconditional" above.