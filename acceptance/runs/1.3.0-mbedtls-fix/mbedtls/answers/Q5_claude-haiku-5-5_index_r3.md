**Short answer:** Constant time is enforced by convention plus a small amount of inline assembly. Nothing in the build proves it at the instruction level. The check that exists is a Valgrind/MemSan test run on a few suites. On compilers without the assembly path, the build succeeds silently with a C fallback whose constant-time behaviour is only empirically observed. The facility is used in about 25 library files, but several sensitive paths use separate mechanisms.

## How it is enforced at the instruction level

The core is `mbedtls_ct_bool(x)` in `library/constant_time_impl.h:120`, which turns a value into an all-ones or all-zeros mask. The x86-64 version is three instructions with no branch or flag-dependent instruction:

```
mov  x -> s
neg  s            ; s = -x, sets the sign bit iff x != 0
or   s -> x       ; top bit of x set iff x != 0
sar  $63, s      ; s = all ones if x != 0, else all zeros
```

The AArch64, 32-bit Arm and 32-bit x86 variants follow the same pattern (`impl.h:130-182`). Everything else is built from that mask with bitwise select, so `mbedtls_ct_if` and friends never need a conditional.

Two other mechanisms keep the compiler from undoing this:

- **Opaque barrier.** `mbedtls_ct_compiler_opaque` (`impl.h:85`) is `asm volatile("" : "+r"(x))` under assembly. In C it is `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` global set to 0 (`constant_time.c:29`). The compiler cannot prove a value, so it cannot fold a branch on it.
- **Volatile reads in `mbedtls_ct_memcmp`** (`constant_time.c:67`). Both buffers are read through `volatile` pointers so the loop always reads every byte. Its result is `diff` folded to a sign-safe int. It is explicitly *not* constant time with respect to `n`.

## When the compiler cannot support it

The assembly path is selected in `impl.h:40-52`. It needs `MBEDTLS_HAVE_ASM`, which `mbedtls_config.h:52` enables by default, plus GNU-compatible `__GNUC__`. Then it picks by architecture.

| Situation | What `mbedtls_ct_bool` uses | Barrier |
|---|---|---|
| GCC/Clang on AArch64, Arm32, x86, x86-64 with a matching size | Assembly mask | Asm barrier |
| GCC/Clang on another architecture (RISC-V, MIPS, PowerPC…) | C fallback | Asm barrier |
| 32-bit Arm or x86 with `MBEDTLS_HAVE_INT64` (64-bit ct type) | C fallback | Asm barrier |
| MSVC, IAR, armcc5, or `MBEDTLS_HAVE_ASM` unset | C fallback | `volatile` XOR |

The C fallback's comment (`impl.h:127`) says it "does not get optimised into conditional instructions or branches by trunk clang, gcc, or MSVC v19" as of May 2023. That is an observation, not a guarantee. The one hard build error is `check_config.h:250`, which forbids MemorySanitizer with `MBEDTLS_HAVE_ASM`, so MemSan builds must drop the assembly.

On the unsupported side there is no `#error`. A port on an unlisted toolchain gets the C fallback without being told.

## How it is verified

- Test suites are instrumented with `TEST_CF_SECRET` / `TEST_CF_PUBLIC`. Only 8 of 91 suites are annotated: base64, bignum_core, bignum_mod_raw, cipher, constant_time, constant_time_hmac, pkcs1_v15 and psa_crypto_constant_time. Those contain 89 `TEST_CF_SECRET` uses.
- Components in `tests/scripts/components-sanitizers.sh` run MemSan (`:33`, `:53`) and release Valgrind (`:72`, `:105`, `:131`). The Valgrind ones run only the annotated suites (`skip_suites_without_constant_flow`, `:12`).
- The mechanism behind `TEST_CF_*` lives in `framework/tests/include/test/constant_flow.h`. That file is absent from this checkout, so I could not read it and have not verified how it marks secrets.

So the test is a dynamic check on the paths the annotated suites happen to exercise, not a proof for the library.

## How far it reaches

**Used by** (from `mbedtls_ct_\w+(` matches, which include the ct headers' own definitions): `cipher.c` (padding removal, `mbedtls_ct_memcpy_if`), `base64.c`, `rsa.c` (PKCS#1 v1.5 unpadding, OAEP decrypt, signature compare), `bignum.c` and `bignum_core.c` (table lookup for modular exponentiation, conditional assign), `ssl_msg.c` (`mbedtls_ct_hmac` for CBC MAC-then-encrypt, `mbedtls_ct_memcmp` on decrypt), the TLS 1.2/1.3 server (PSK binder and identity checks, Finished), `psa_crypto.c` and `psa_crypto_mac.c` (verify paths), and the GCM, CCM, ChaCha20-Poly1305 and NIST KW tag checks.

**Not using it:**

- `ecp.c` does not call `mbedtls_ct_*`. Its comb-table selection (`ecp.c:2010`) uses `MPI_ECP_COND_ASSIGN`, which wraps `mbedtls_mpi_safe_cond_assign`, a parallel mechanism.
- `aes.c` has no `mbedtls_ct_` calls. Its table lookups are not covered by this facility.
- `3rdparty/p256-m` ships its own constant-time field arithmetic, with its own `MUL64_IS_CONSTANT_TIME` switch.

The facility is a set of primitives used where the library's authors chose to apply them. Coverage is per call site and per module, not a library-wide property.