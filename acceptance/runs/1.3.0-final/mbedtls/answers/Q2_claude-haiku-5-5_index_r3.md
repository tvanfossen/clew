**What it accomplishes.** `MBEDTLS_PRIVATE` is a name-mangling macro, not access control. `include/mbedtls/private_access.h:14-18` expands it two ways:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

Struct members are declared as `MBEDTLS_PRIVATE(state)`, so in a default build the field is really named `private_state`. Plain `ssl->state` then fails to compile, and the layout is unchanged. The intent is to keep the public surface small, so the team can rename or restructure fields in a minor release without breaking callers. The migration guide says this directly (`docs/3.0-migration-guide.md:66-74`): only fields explicitly documented as public are stable, and direct access is a last resort at the user's own risk.

The spelled-out form `x->MBEDTLS_PRIVATE(f)` compiles in both modes, which is why the guide tells users to write it. That is the escape hatch, and `include/mbedtls/ssl.h:5159-5169` labels it deprecated and asks people to raise an issue instead.

**Who it is for.**

| Who | What they get |
|---|---|
| External applications | Plain `->field` is a compile error. They should use the accessors, such as `mbedtls_ssl_is_handshake_over()` at `ssl.h:5146`, or the explicit `MBEDTLS_PRIVATE(...)` spelling at their own risk. |
| The library itself | `library/common.h:132` defines `MBEDTLS_ALLOW_PRIVATE_ACCESS` unconditionally, so every library `.c` that includes `common.h` sees plain field names. Almost all of them do, and the internal headers (`ssl_misc.h`, `pk_internal.h`, `ssl_ciphersuites_internal.h`) include it too. |
| Two sample programs | `programs/ssl/ssl_server2.c:8` and `ssl_client2.c:8` define the macro before any include, so they get plain names. |
| `programs/ssl/ssl_context_info.c` | Does not define the macro. It uses the spelled-out `MBEDTLS_PRIVATE(flags)` form, so it compiles as external code would. |

**What the opt-out means for those places.** Inside the library, `MBEDTLS_PRIVATE` is a no-op and private fields are freely read and written. That is the designed trade-off: the library may touch its own internals, and the restriction only applies to outside code. The mechanism depends on ordering. If a library file included a public header before `common.h`, that header would see the mangled names. The build would fail, so it is loud rather than silent.

Public inline accessors such as `mbedtls_ssl_is_handshake_over()` live in public headers and are expanded in the user's translation unit. They therefore follow the user's mode, and the user never has to define anything to use them.

**Not verified:** I did not confirm how the test-suite `.function` files (`test_suite_x509write`, `test_suite_psa_crypto`) get plain or mangled names, since they are not in the list of places that define the opt-out.