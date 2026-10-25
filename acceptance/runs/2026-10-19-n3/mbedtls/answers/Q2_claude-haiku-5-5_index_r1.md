**What it does.** `MBEDTLS_PRIVATE(member)` is a preprocessor macro, defined in `include/mbedtls/private_access.h:14-18`:

- By default it expands to `private_##member`. So a struct declared as `int MBEDTLS_PRIVATE(state);` actually has a member named `private_state`. Code that writes `ctx->state` fails to compile.
- If `MBEDTLS_ALLOW_PRIVATE_ACCESS` is defined in that translation unit, it expands to `member`, and the real name is visible.

This is a name-mangling guard, not encapsulation. Layout and ABI are unchanged, because only the identifier differs. Its purpose is to make accidental use of internals a compile error, so users reach for the public accessors instead of depending on fields that can change between releases. The 3.0 migration guide (`docs/3.0-migration-guide.md:74`) describes `bar.MBEDTLS_PRIVATE(foo)` as a last resort, "at your own risk."

**Who it's for.**

1. **Application users (the default).** They get `private_*` names and cannot touch fields directly. Nothing to do.

2. **The library itself.** `library/common.h:127-132` defines `MBEDTLS_ALLOW_PRIVATE_ACCESS` unconditionally. Library sources include `common.h`, so every library translation unit sees real member names. This is the main opt-out, and it is source-level: the library's own code is not mangled. Users who include `common.h` (which is not a public header) get the same effect.

3. **Test and sample programs.** `programs/ssl/ssl_server2.c:8` and `programs/ssl/ssl_client2.c:8` define the macro before any include. Those two programs see all fields by their plain names, for the whole translation unit. This is the only other opt-out in the tree; the `grep` found no build-system definition. `include/mbedtls/ssl.h:5159-5169` marks direct state access as deprecated even under this opt-out.

**Code that spells it out instead.** `programs/ssl/ssl_context_info.c:553-568` and `programs/fuzz/fuzz_dtlsserver.c:138` write `x.MBEDTLS_PRIVATE(field)` without the define. This compiles in both modes, because the struct declaration and the access expand the same way. This is the form the migration guide recommends. The fuzz harness is worth noting because it reaches into `ssl.MBEDTLS_PRIVATE(next_record_offset)` to drive a memory-BIO offset, so it is the sort of code that breaks if the field is renamed.

**Practical consequence.** The same header produces different member names depending on the translation unit. That is safe for ABI, but it means a field name you see in a header may not be the name used by code compiled with the opt-out. Any reader or tool that treats the headers as the spelling of the struct will be wrong for library and program code.