**Short answer:** the two calls are a size probe followed by a fill, not retry logic. When tokenization fails, the error is swallowed as an empty vector, and the callers keep going as if the prompt had zero tokens.

**Why it calls twice.** The two `llama_tokenize` calls are in `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:49-71`), at lines 55 and 61. The first call passes a null buffer with size 0. llama.cpp then returns the negative of the required token count, and the code flips the sign to get `n`. The second call passes a buffer of exactly `n` and gets the real tokens. The second call only runs once, and it runs with the size the first call reported, so nothing is retried. The only other llama.cpp tokenize call in `src/` is `mtmd_tokenize` in `mtmd_prefill` (`llama_cpp_backend.cpp:2407`). That is a different API for multimodal input, and it is not paired with a second call. So the "two places" you saw are most likely the two lines in one function.

**Failure path, outward:**

1. `LlamaCppTokenizer::tokenize` returns `{}` if `vocab_` is null, and also if the second call returns a negative count. On that path it logs at ERROR with the text length only, not the content. It does not return an error code. The second-call failure is close to unreachable with a correctly sized buffer.
2. `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788-800`) returns `{}` when `tokenizer_` is unset, and otherwise passes the vector through.
3. The callers do not check for empty:
   - **`do_count_tokens`** (`:825`) returns 0. `entropic_inference_count_tokens` (`inference_c_api.cpp:548`) passes that 0 straight to the C caller. The `len/4` estimate only runs when an exception is thrown, so a llama.cpp failure reads as a zero-token count.
   - **`do_complete`** (`:3941`) logs "0 input tokens" and calls `decode_loop` with an empty vector.
   - **`do_generate_text_only`** (`:2555`) does the same, then goes into `run_prefill_cached`. Its only error branch is `prefill_error()`.
   - **`compute_prefix_token_count`** (`:2051`) returns 0, so the prompt-cache prefix is computed as zero.
4. The empty vector reaches `run_prefill` (`:1484`). With zero tokens the chunk loop never runs, and the function returns `true`. `decode_loop` (`:1562`) therefore treats an empty prefill as a success and starts sampling. In this path nothing ever sets `error_code` for the tokenization failure.

Result: a tokenization failure is not visible to the caller. It shows up as "0 tokens" in counts, and as generation from no prompt in completion and generation. I read this from the code and did not run it. Two things I did not verify: how `run_prefill_cached` behaves with an empty vector when the prompt cache is enabled, and whether any caller outside `src/inference/` checks the count.

**Is it retry logic?** No. It is a two-step sized read with no retry, no loop, and no backoff. The real problem is the one above: failure is swallowed into an empty result that the rest of the stack cannot tell apart from a legitimately empty prompt.