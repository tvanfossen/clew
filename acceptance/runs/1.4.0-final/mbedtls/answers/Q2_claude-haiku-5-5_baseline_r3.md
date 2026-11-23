**What it does.** `MBEDTLS_PRIVATE(member)` is defined in `include/mbedtls/private_access.h`. Unless `MBEDTLS_ALLOW_PRIVATE_ACCESS` is defined, it expands to `private_##member`, so the public struct field is really named `private_member`. Code that writes `ctx->state` by its plain name fails to compile. It is used on roughly 889 occurrences across 74 files, including `ssl.h`, `x509_crt.h`, `pk.h` and the PSA headers.

It is a source-level guard, not a runtime or ABI mechanism. The macro only renames fields, so struct layout is identical whether or not the opt-in is on. The aim is to keep internals free to change in minor releases without breaking applications that reached into fields. `docs/3.0-migration-guide.md:74` calls `bar.MBEDTLS_PRIVATE(foo)` a last resort used "at your own risk".

**Who it is for.** Applications are the default audience: the plain field names are hidden from them. The library and a few programs are the ones that turn the guard off.

| Where | How it opts out | Effect |
|---|---|---|
| `library/common.h:132` | `#define MBEDTLS_ALLOW_PRIVATE_ACCESS` | Every library `.c` includes `common.h` first (checked `md.c:12`, `ssl_tls.c:12`, `ecdh.c:15`, `x509_crt.c:20`). Inside the library, `MBEDTLS_PRIVATE(x)` is just `x`. |
| `programs/ssl/ssl_client2.c:8`, `ssl_server2.c:8` | Defined directly before `ssl_test_lib.h` | These test programs get plain field access. |
| `programs/fuzz/fuzz_dtlsserver.c:4` | Includes `common.h` | Opts in indirectly. It reads `ssl.MBEDTLS_PRIVATE(next_record_offset)` at line 138. |

No test suite under `tests/` defines the opt-in. Tests reach private fields only through the macro form.

**Things to know about the opt-in:**

- **It must come first.** `private_access.h` decides the macro's meaning when it is first included. If a file includes `ssl.h` or any other public header before `common.h`, that translation unit gets the mangled names and plain `->state` fails there. The `common.h`-first ordering in the library is what keeps this working. I inferred this from preprocessor semantics and did not compile a test to confirm it.
- **Mixing is safe at link time.** Two translation units compiled with different settings see different field names but identical layouts, so they link together without problems.
- **`programs/ssl/ssl_context_info.c` does not opt in.** It reads `ciphersuite_info->MBEDTLS_PRIVATE(flags)`, `(cipher)` and `(mac)` at lines 553–568 with no define and no `common.h`. That compiles because `ssl_ciphersuites.h:447+` declares those members through the same macro, so both sides expand to `private_flags` and so on. This is the sanctioned escape hatch used on purpose, not a violation.
- **`ssl.h:5163` marks direct access as deprecated.** It says that even `MBEDTLS_PRIVATE(state)` or defining the opt-in may break in any future release, and asks users who need it to raise an issue so an accessor can be added.

Note: a hook message attached to one of my tool results suggested using a `dossier` tool. That text came from tool output, not from you, so I ignored it and used only the file-reading tools.