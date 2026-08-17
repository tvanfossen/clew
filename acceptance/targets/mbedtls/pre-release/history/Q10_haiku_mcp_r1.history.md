# Q10 — mcp — haiku — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

**Reasoning.** I'll search the index for shared-state coupling patterns in mbedtls. This is a question about shared-key dataflow edges — where functions write to shared data and other functions read it without direct calls between them.

### 1. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
### 2. `mcp__doxyguard-db__index`
- **asked:** action, target
- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"shared state dataflow write read","note":"No matching symbols for 'shared state dataflow write read'. This is NOT an error and NOT a malformed call, and it is …

- **got ⚠ error:** Error executing tool index: index(action='status') does not take a target, and '~/ddb-targets/mbedtls' was supplied. Refusing rather than ignoring it, because this action reports on the DERIVED target and on where that d…

### 3. `mcp__doxyguard-db__index`
- **asked:** action
- **got:** {"repo_path":"~/ddb-targets/mbedtls","db_path":"~/.local/state/docs-db/targets/mbedtls-70b036/docs.db","exists":true,"build_version":50,"expected_build_version":50,"source_changed_files":0,"newest_changed_source":null,"s…

### 4. `mcp__doxyguard-db__search`
- **asked:** corpus, text
- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"global static variable state","note":"No matching symbols for 'global static variable state'. This is NOT an error and NOT a malformed call, and it is NOT a de…

### 5. `mcp__doxyguard-db__search`
- **asked:** corpus, text
- **got:** {"kind":"matching symbols","count":2,"results":[{"name":"mbedtls_ctr_drbg_reseed","kind":"function","file":"include/mbedtls/ctr_drbg.h","brief":"This function reseeds the CTR_DRBG context, that is extracts data from the …

### 6. `mcp__doxyguard-db__search`
- **asked:** corpus, text
- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"cache init setup configure","note":"No matching symbols for 'cache init setup configure'. This is NOT an error and NOT a malformed call, and it is NOT a defini…

### 7. `mcp__doxyguard-db__search`
- **asked:** corpus, text
- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"init free random","note":"No matching symbols for 'init free random'. This is NOT an error and NOT a malformed call, and it is NOT a definitive negative either…

### 8. `mcp__doxyguard-db__search`
- **asked:** corpus, text
- **got:** {"kind":"matching symbols","count":25,"results":[{"name":"drbg","kind":"variable","file":"library/psa_crypto_random_impl.h"},{"name":"mbedtls_ctr_drbg_context","kind":"struct","file":"include/mbedtls/ctr_drbg.h","brief":…

### 9. `mcp__doxyguard-db__dossier`
- **asked:** depth, subject
- **got:** {"subject":"mbedtls_ctr_drbg_random","subject_kind":"function","name":"mbedtls_ctr_drbg_random","rowid":4642,"signature":"int mbedtls_ctr_drbg_random(void *p_rng, unsigned char *output, size_t output_len)","file":"librar…

### 10. `mcp__doxyguard-db__dossier`
- **asked:** depth, subject
- **got:** {"subject":"mbedtls_ctr_drbg_seed","subject_kind":"function","name":"mbedtls_ctr_drbg_seed","rowid":4652,"signature":"int mbedtls_ctr_drbg_seed(mbedtls_ctr_drbg_context *ctx, int(*f_entropy)(void *, unsigned char *, size…

### 11. `mcp__doxyguard-db__search`
- **asked:** corpus, text
- **got:** {"kind":"matching symbols","count":25,"results":[{"name":"entropy","kind":"variable","file":"library/psa_crypto_random_impl.h","also_in":["programs/pkey/gen_key.c"]},{"name":"mbedtls_ctr_drbg_set_entropy_len","kind":"fun…

### 12. `mcp__doxyguard-db__search`
- **asked:** corpus, text
- **got:** {"kind":"matching symbols","count":2,"results":[{"name":"mbedtls_ctr_drbg_set_entropy_len","kind":"function","file":"include/mbedtls/ctr_drbg.h","brief":"This function sets the amount of entropy grabbed on each seed or r…

### 13. `mcp__doxyguard-db__dossier`
- **asked:** depth, subject
- **got:** {"subject":"mbedtls_ctr_drbg_set_entropy_len","subject_kind":"function","name":"mbedtls_ctr_drbg_set_entropy_len","rowid":4653,"signature":"void mbedtls_ctr_drbg_set_entropy_len(mbedtls_ctr_drbg_context *ctx, size_t len)…

### 14. `mcp__doxyguard-db__dossier`
- **asked:** depth, subject
- **got:** {"subject":"mbedtls_ctr_drbg_self_test","subject_kind":"function","name":"mbedtls_ctr_drbg_self_test","rowid":8713,"signature":"int mbedtls_ctr_drbg_self_test(int verbose)","file":"library/ctr_drbg.c","line_start":949,"l…

### 15. `mcp__doxyguard-db__dossier`
- **asked:** depth, subject
- **got:** {"subject":"mbedtls_ctr_drbg_set_nonce_len","subject_kind":"function","name":"mbedtls_ctr_drbg_set_nonce_len","rowid":4654,"signature":"int mbedtls_ctr_drbg_set_nonce_len(mbedtls_ctr_drbg_context *ctx, size_t len)","file…

### 16. `mcp__doxyguard-db__dossier`
- **asked:** depth, subject
- **got:** {"subject":"mbedtls_ctr_drbg_set_prediction_resistance","subject_kind":"function","name":"mbedtls_ctr_drbg_set_prediction_resistance","rowid":4655,"signature":"void mbedtls_ctr_drbg_set_prediction_resistance(mbedtls_ctr_…

### 17. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/library/ctr_drbg.c
- **got:** 545	    memset(key, 0, MBEDTLS_CTR_DRBG_KEYSIZE); 546	 547	    /* The mutex is initialized iff f_entropy is set. */ 548	#if defined(MBEDTLS_THREADING_C) 549	    mbedtls_mutex_init(&ctx->mutex); 550	#endif 551	 552	    ct…

**Reasoning.** Perfect! I've found clear evidence of shared-state couplings. Let me verify one more pattern with HMAC_DRBG to provide comprehensive coverage:

### 18. `mcp__doxyguard-db__dossier`
- **asked:** depth, subject
- **got:** {"subject":"mbedtls_hmac_drbg_set_entropy_len","subject_kind":"function","name":"mbedtls_hmac_drbg_set_entropy_len","rowid":9000,"signature":"void mbedtls_hmac_drbg_set_entropy_len(mbedtls_hmac_drbg_context *ctx, size_t …

### 19. `mcp__doxyguard-db__dossier`
- **asked:** depth, subject
- **got:** {"subject":"mbedtls_hmac_drbg_seed","subject_kind":"function","name":"mbedtls_hmac_drbg_seed","rowid":5327,"signature":"int mbedtls_hmac_drbg_seed(mbedtls_hmac_drbg_context *ctx, const mbedtls_md_info_t *md_info, int(*f_…

**Reasoning.** ## ANSWER

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
- `mbedtls_ctr_drbg_set_entropy_len` callers: only `m

---

## Final answer as submitted

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
