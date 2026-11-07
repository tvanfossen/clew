## Short answer

Constant-time behaviour is enforced by convention and hand-written assembly, not by any check on the generated code. The default build uses assembly on four ISA families. Everywhere else, and on any compiler that is not GNU-compatible, it falls back to plain C with no error or warning. The C fallback is only "observed" to be constant-time. Testing is dynamic (Valgrind or MemorySanitizer), and it is off by default.

## How it is enforced at the instruction level

The facility is `library/constant_time_internal.h` (declarations) and `library/constant_time_impl.h` (static inline bodies), plus `library/constant_time.c` for the non-inline functions.

- **Opacity.** `mbedtls_ct_compiler_opaque()` (`constant_time_impl.h:85-93`) stops the optimiser from knowing a value. With assembly it is `asm volatile("" : "+r"(x))`, an empty barrier. Without assembly it is `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` zero (`constant_time.c:23-30`).
- **Condition masks.** Booleans are all-ones or all-zeros words, built by arithmetic with no branch. `mbedtls_ct_bool` is `neg/orr/asr` in assembly (`constant_time_impl.h:130-141`) or `-(y)` arithmetic in C.
- **Selection.** `mbedtls_ct_if` is a mask-and-or, e.g. `(cond & a) | (~cond & b)`.
- **Comparison.** `mbedtls_ct_uint_lt` uses subtraction and sign-bit extraction, not `<`.
- **Memory.** `mbedtls_ct_memcmp` (`constant_time.c:67-116`) reads both buffers through `volatile` pointers, XORs and ORs the differences, and always reads all `n` bytes. It is not constant-time in `n`, as its header says.

The mechanism is therefore "the code avoids branches on secrets, and the optimiser is blocked from re-introducing them". Nothing inspects the emitted instructions in a default build.

## What happens on a compiler that cannot support it

The asm guard is at `constant_time_impl.h:40-41`:

- `MBEDTLS_HAVE_ASM` must be defined (it is on by default, `mbedtls_config.h:52`).
- The compiler must define `__GNUC__`. Clang counts; MSVC does not.
- armcc5 is excluded.

If any of these fails, `MBEDTLS_CT_ASM` stays undefined and the C path is used. Assembly is also per (architecture, width) pair, not per architecture. For example, the ARM Thumb assembly only exists for `MBEDTLS_CT_SIZE_32` (`constant_time_impl.h:142`), so 32-bit ARM with a 64-bit `mbedtls_ct_uint_t` silently uses C for those functions.

Three things about the fallback matter:

1. **It is silent.** There is no `#error` or warning when assembly is absent.
2. **Its guarantee is empirical.** The header says the C fallback "has been observed to be constant-time on latest gcc, clang and MSVC as of May 2023" (`constant_time_internal.h:55-59`). That is a dated observation about specific compilers, not a property the code guarantees.
3. **MemorySanitizer forces it.** `check_config.h:250-251` rejects `MBEDTLS_HAS_MEMSAN` combined with `MBEDTLS_HAVE_ASM`, so the MSan test build runs the C path.

## How far the facility reaches

I counted calls matching `mbedtls_ct_\w+\(` in `library/`: 286 occurrences across 29 files.

| Area | Uses of the facility |
|---|---|
| RSA PKCS#1 v1.5 sign/verify, OAEP decrypt (`rsa.c`) | 29 |
| Bignum core and bignum (`bignum_core.c`, `bignum.c`) | 22 + 21 |
| Cipher tag check (`cipher.c`) | 25 |
| TLS record and HMAC/padding (`ssl_msg.c`) | 22 |
| Base64 (`base64.c`) | 21 |
| TLS 1.2/1.3 server parsing (PMS, PSK binder, Finished, cookie) | a handful per file |
| GCM, CCM, ChaCha20-Poly1305, NIST KW, PSA MAC/hash verify | 1–4 each |

Several pieces of the library have zero uses. A grep over `ecp*.c`, `aes.c`, `aesce.c`, `aesni.c`, `dhm.c`, `ecdsa.c` and `ecdh.c` returns nothing. So this facility does not cover AES table lookups, the generic ECC code, or DHM. I did not audit whether those have other protections.

Uses of the facility do not prove the surrounding code is clean. I did not audit callers for secret-dependent branches outside these functions.

## Testing, and what I could not confirm

- The Valgrind and MemorySanitizer modes are controlled by `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND` and `MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN` (`mbedtls_config.h:2109-2142`). They are commented out by default, and `tests/scripts/components-*.sh` enables them in specific components.
- The `test_suite_constant_time.function` file has no poison calls that I could find. I could not locate the code that marks secret inputs as undefined for the Valgrind run. Without it, I cannot say what the Valgrind component actually checks. Settling this needs a look at how the Valgrind build wires the poisoning in.