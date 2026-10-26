**Short answer:** the two calls are a size probe followed by the real call, not retry logic. On failure, the tokenizer returns an empty vector, and nothing above it gets an error code. Most callers treat that empty vector as a valid zero-token input.

**Why two calls.** The index places both `llama_tokenize` calls in one function, `entropic::LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:49-71`), at lines 55 and 61. They are not in two separate places. The first call passes a null buffer with size 0 to get the required token count. llama.cpp returns that count negated when the buffer is too small. The code then allocates a vector of that size and makes the second call to fill it. The first call never fails in a way the second one repeats, so there is no retry. The same size-then-fill pattern appears in `LlamaCppTokenizer::detokenize` (`llama_token_to_piece`, lines 86-105), which uses a fixed 256-byte buffer and retries once with the exact size.

**What the caller receives on failure.** `LlamaCppTokenizer::tokenize` returns `{}` in three cases: `vocab_` is null, the sized call returns a negative value, or the second call returns a negative value. The only log line is an ERROR with the text length, not the text itself. The `Tokenizer` interface has no error channel, so the failure is just an empty `std::vector<int32_t>`. `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788-800`) also returns `{}` when no tokenizer is wired, and adds no logging.

**What the callers do with the empty vector:**

| Caller | What happens |
|---|---|
| `do_count_tokens` / `count_tokens` | Returns `0`. This is indistinguishable from empty input. |
| `compute_prefix_token_count` | Returns `0`. `prefill_dispatch` then passes a zero-length prefix to `prefill_and_cache_prefix`. I did not verify what that does with zero. |
| `do_complete` | Logs "0 input tokens" and goes on to `decode_loop`. It does not check the size. |
| `do_generate_text_only` | No size check. It proceeds to `run_prefill_cached`, and the outcome depends on `run_prefill`, which I did not read. |
| `generate_speculative_with_draft` | The only caller that checks: if `tokens.size() < 2`, it returns `ENTROPIC_ERROR_GENERATE_FAILED` with "speculative prompt must have at least 2 tokens". That message misattributes a tokenizer failure to a short prompt. |
| `tokenize_text` (public) | Documented as "empty if COLD or error", so the empty vector is the advertised error signal. |

**Bottom line:** a tokenizer failure surfaces as a zero-length prompt. Only the speculative path turns it into an error, and it does so with the wrong message. Everywhere else the failure is either silent or depends on downstream behaviour the index did not show me. I did not read `run_prefill`, `run_prefill_cached`, or `prefill_and_cache_prefix`, so the outcome for an empty prompt there is unverified. A direct read of those three would settle it.