# Q10 — mcp — haiku — run 1

## ANSWER

I found multiple clear instances of **shared-state coupling** in mbedtls where one function writes to a data structure that another function reads, with **no direct call** between them:

### 1. **CTR_DRBG Context Configuration**

**Write Function:** `mbedtls_ctr_drbg_set_entropy_len` (library/ctr_drbg.c:124)
```c
ctx->entropy_len = len;
```

**Read Function:** `mbedtls_ctr_drbg_seed` (library/ctr_drbg.c:555-557)
```c
if (ctx->entropy_len == 0) {
    ctx->entropy_len = MBEDTLS_CTR_DRBG_ENTROPY_LEN;
}
```

**Evidence of No Call:** 
- `mbedtls_ctr_drbg_set_entropy_len` callers: only `mbedtls_ctr_drbg_self_test`
- `mbedtls_ctr_drbg_seed` does not call `mbedtls_ctr_drbg_set_entropy_len`
- `mbedtls_ctr_drbg_set_entropy_len` does not call `mbedtls_ctr_drbg_seed`

---

### 2. **CTR_DRBG Nonce Length Configuration**

**Write Function:** `mbedtls_ctr_drbg_set_nonce_len` (library/ctr_drbg.c:148)
```c
ctx->reseed_counter = (int) len;
```

**Read Function:** `mbedtls_ctr_drbg_seed` (library/ctr_drbg.c:562-564)
```c
nonce_len = (ctx->reseed_counter >= 0 ?
             (size_t) ctx->reseed_counter :
             good_nonce_len(ctx->entropy_len));
```

**Evidence of No Call:**
- `mbedtls_ctr_drbg_set_nonce_len` callers: only `mbedtls_ctr_drbg_self_test`
- No call path between them

---

### 3. **CTR_DRBG Prediction Resistance Flag**

**Write Function:** `mbedtls_ctr_drbg_set_prediction_resistance` (library/ctr_drbg.c:118)
```c
ctx->prediction_resistance = resistance;
```

**Read Function:** `mbedtls_ctr_drbg_random_with_add` (library/ctr_drbg.c:633)
```c
if (ctx->reseed_counter >= ctx->reseed_interval ||
    ctx->prediction_resistance) {
```

**Evidence of No Call:**
- `mbedtls_ctr_drbg_set_prediction_resistance` callers: `main`, `mbedtls_ctr_drbg_self_test`
- `mbedtls_ctr_drbg_random_with_add` does not call `mbedtls_ctr_drbg_set_prediction_resistance`

---

### 4. **HMAC_DRBG Entropy Length Configuration**

**Write Function:** `mbedtls_hmac_drbg_set_entropy_len` (library/hmac_drbg.c:291)
```c
ctx->entropy_len = len;
```

**Read Function:** `mbedtls_hmac_drbg_seed` (library/hmac_drbg.c:253)
```c
if (ctx->entropy_len == 0) {
    ctx->entropy_len = md_size <= 20 ? 16 : ...
}
```

**Evidence of No Call:**
- `mbedtls_hmac_drbg_set_entropy_len` has no callers in the index
- `mbedtls_hmac_drbg_seed` callers: `main`, `mbedtls_hmac_drbg_self_test`, `rng_seed`, `mbedtls_psa_drbg_seed`
- No call relationship between them

---

## Gaps

All identified couplings follow the **setter/reader pattern** on context structures (CTR_DRBG and HMAC_DRBG initialization parameters). The index confirmed these are shared-key dataflow edges: one function initializes or configures a shared context, and separate callers may invoke the configuration function and then separately invoke functions that read those configured values.

I did not find examples of more complex **global variable** couplings or **inter-module state sharing** patterns—though the index reported 99 shared-key inferred edges total, suggesting such patterns likely exist elsewhere in the codebase. These setters/readers are the most obvious documented examples.
