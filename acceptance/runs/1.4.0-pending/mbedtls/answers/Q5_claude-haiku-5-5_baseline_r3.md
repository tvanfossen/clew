## Short answer

Constant-time behaviour in mbedtls is achieved by convention and hand-written assembly, not by any compiler pass or static check. The `mbedtls_ct_*` API is a small set of branch-free primitives that the library calls from selected secret-dependent paths. Verification is runtime testing under MemorySanitizer or Valgrind, and those builds disable the assembly, so the code that ships on ARM/x86 is not the code that gets tested. Coverage is partial, and the repo says so itself.

## How it is enforced at the instruction level

- **Opaque masks, not bools.** `mbedtls_ct_condition_t` is an all-ones or all-zeros word. `mbedtls_ct_bool(x)` turns any value into a mask without a branch. `mbedtls_ct_if` selects with `and`/`not`/`and`/`or` (`library/constant_time_impl.h`).
- **Hiding the value from the compiler.** `mbedtls_ct_compiler_opaque()` is an empty `asm volatile` barrier when assembly is available. Otherwise it XORs with a `volatile` global zero, so the optimiser cannot prove the value and fold the code back into a branch.
- **Pinned instruction sequences.** On the assembly paths, the instruction sequence is fixed. For example, `mbedtls_ct_bool` on AArch64 is `neg / orr / asr 63`, and on x86-64 it is `mov / neg / or / sar $63`.
- **Volatile reads.** `mbedtls_ct_memcmp` reads both buffers through `volatile` pointers, so the compiler cannot add an early exit when a difference appears. It accumulates the XOR of all bytes and tests the result once at the end. (The header comment says the time is constant in the data and in whether the buffers match, but not in `n`.)

## What happens on a compiler or target that cannot support it

- Assembly is used only when `MBEDTLS_HAVE_ASM` is set and the compiler is GCC/Clang-style (or ARMCC 6+). It is further restricted to 32-bit and 64-bit ARM, AArch64, x86 and x86-64 (`constant_time_impl.h:40-52`).
- Anywhere else, `MBEDTLS_CT_ASM` is undefined and the C fallback is used. There is no `#error` and no refusal. The header states only that the fallback "has been observed to be constant-time on latest gcc, clang and MSVC as of May 2023". That is an observation, not a guarantee.
- Setting `MBEDTLS_HAVE_ASM` off (which the MemSan CI component does) also drops the assembly on ARM and x86, and `mbedtls_ct_memcmp` falls back to a plain byte loop. The `MBEDTLS_EFFICIENT_UNALIGNED_VOLATILE_ACCESS` fast path exists only for ARM and AArch64.

## How it is tested

- `tests/suites/test_suite_constant_time*.function` run the primitives under `TEST_CF_SECRET`/`TEST_CF_PUBLIC` markers. Under MSan these flag any branch or memory index that depends on a secret. Under Valgrind memcheck, the same markers flag secret-dependent control flow as uninitialised-value use.
- The CI components are `component_test_memsan_constant_flow` and `component_release_test_valgrind_constant_flow` in `tests/scripts/components-sanitizers.sh`. The MSan build unsets `MBEDTLS_HAVE_ASM` and `MBEDTLS_AESNI_C` because "memsan doesn't grok asm". So the instrumented binary is not the asm binary.
- The checks only cover the paths the tests execute, with the inputs they use.
- In this checkout, `framework/` is an empty submodule directory, so `framework/tests/include/test/constant_flow.h` is missing. I did not build or run the tests here.

## How far it reaches

Grep counts of `mbedtls_ct_` references, which show usage and not verified coverage:

| Area | Refs | Use |
|---|---|---|
| `bignum_core.c`, `bignum.c` | 32, 26 | Modular arithmetic on secret values |
| `rsa.c` | 37 | PKCS#1 v1.5 unpadding (`mbedtls_ct_rsaes_pkcs1_v15_unpadding`) |
| `cipher.c` | 30 | CBC padding removal |
| `ssl_msg.c` | 24 | Record MAC via `mbedtls_ct_hmac`, padding check, MAC compare |
| `base64.c` | 21 | Decoding |
| `gcm.c`, `ccm.c`, `chachapoly.c`, `cmac.c` | 1 each | Tag comparison (`cmac.c` also uses a masked conditional) |

The facility does not cover the whole library:

- `library/aes.c` has no `mbedtls_ct_` references. Software AES uses table lookups, which are a known cache-timing exposure. Only the hardware AES paths avoid that.
- `SECURITY.md` says Mbed TLS "provides limited protection against timing attacks", is "moving towards a model of fully timing-invariant code, but has not reached this point yet", and that block ciphers "do not yet achieve full protection".
- `docs/psa-transition.md` notes that the PSA API has no equivalent of `constant_time.h`, so callers are told to keep using `mbedtls_ct_memcmp` for MAC verification.

## Note

A PostToolUse hook returned text suggesting `dossier` and `search` tools that aren't in this session. I ignored it and used only the file-reading tools.