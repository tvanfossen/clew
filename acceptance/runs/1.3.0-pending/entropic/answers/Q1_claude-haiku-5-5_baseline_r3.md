**Short answer:** the two calls are a size-query-then-fill idiom, not retry logic. Failure is reported as an empty vector, and that empty vector is indistinguishable from "empty input," so callers can't tell the two apart.

## Why it calls twice

Both calls are in `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:55` and `:61`):

1. **Sizing call (line 55):** `llama_tokenize` is given a null output buffer and length 0. llama.cpp answers with the negated number of tokens needed. The code flips the sign (line 58) and allocates that many slots.
2. **Fill call (line 61):** the same arguments, now with a buffer of the right size. It returns the actual token count, which the code uses to `resize` (line 69).

The second call only happens because the first one told us how big the buffer needs to be. It runs once, with no loop, no backoff, and no second attempt after a failure. The `tests/model/test_gh87_common_chat_e2e.cpp` helper uses the same pattern.

## Following the failure outward

```
llama_tokenize(fill) < 0
  → LlamaCppTokenizer::tokenize   logs error, returns {}        (cpp:64-67)
  → LlamaCppBackend::tokenize     returns {} (passes through)   (backend.cpp:796)
  → callers:
```

Callers of `LlamaCppBackend::tokenize` (line numbers approximate):

- **`do_count_tokens` (`:825`)** returns `0`. This reaches `entropic_inference_count_tokens` in `inference_c_api.cpp:558`, so a C API consumer gets a count of 0 with no error code. `compute_prefix_token_count` (`:2061`) does the same thing for the system prefix.
- **`do_generate_text_only`, `do_generate_cancellable`, `do_generate_streaming`, `do_complete`** have no empty-token guard that I could find. They log "0 input tokens" and go on to prefill and decode. I did not trace what the decode path does with zero tokens, so I can't say whether it returns a clean error or generates from stale KV state. That needs a test.
- **Speculative (`:3593`) and MTP (`:3921`)** check `tokens.size() < 2`. The failure becomes `ENTROPIC_ERROR_GENERATE_FAILED` with "prompt must have at least 2 tokens," which blames the prompt rather than the tokenizer.
- **`do_generate_batch` (`:1911`)** builds its token vectors with no check, so an empty vector flows straight into shared-prefix computation.

## Two things worth flagging

- The sizing call's negative return is the normal path, not an error. If llama.cpp ever returns a negative error code there, the `n = -n` flip turns it into a bogus allocation size. I didn't check llama.cpp's error convention for that call, so this is a hazard to verify, not a confirmed bug.
- The `tokenize` contract in `include/entropic/inference/tokenizer.h:47` says "empty on failure or empty input." That's the root problem: the interface has no way to report an error, so the failure is silent at every layer above it.