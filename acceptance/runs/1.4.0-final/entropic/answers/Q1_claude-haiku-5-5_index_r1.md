**Short answer:** Neither double call is retry logic. Both are the standard size-probe-then-fill idiom for llama.cpp's C API. The one real failure path returns an empty vector, and nothing above the tokenizer distinguishes that from an empty prompt.

## Why it calls twice

There are two sites, both in `LlamaCppTokenizer` (`src/inference/llama_cpp_tokenizer.cpp`):

1. **`tokenize`, lines 55 and 61.** The first `llama_tokenize(..., nullptr, 0, ...)` passes no buffer. llama.cpp answers with a negative count, which is the required size. The code negates it, allocates that many `int32_t`, and calls `llama_tokenize` again to fill the buffer. The second call is not a retry of anything that failed. It is the fill step, and it reuses the size the first call reported.
2. **`detokenize`, lines 93 and 99.** This one uses a 256-byte stack buffer. Only if `llama_token_to_piece` returns negative (the piece is larger than 256 bytes) does it allocate the exact size and call again. That is a resize, not a retry.

Calling it "retry" would be wrong for two reasons. The second call never repeats a failed input; it uses different arguments derived from the first call's answer. And if the second call fails, the code does not try again. In `tokenize` it logs and returns empty. In `detokenize` it returns an empty string.

## What the caller receives on failure

Only `tokenize` has a real failure path. If the second `llama_tokenize` returns negative, the code logs `Tokenization failed for text of length N` and returns `{}`. The log records only the length, not the text. `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788`) forwards that empty vector, and it also returns `{}` when no tokenizer is wired. Each caller then handles the empty vector as follows:

| Caller | What it does with empty tokens | Result |
|---|---|---|
| `do_count_tokens` (`llama_cpp_backend.h:825`) | Returns `size()` = 0 | C API `entropic_inference_count_tokens` returns 0. Indistinguishable from an empty string, and a budget check would treat it as "fits". |
| `tokenize_text` (`llama_cpp_backend.h:837`) | Returns the empty vector | Header documents "empty if … error". |
| `compute_prefix_token_count` (`:2051`) | Returns 0 | Feeds `prefill_dispatch` as the prefix length. I did not trace the downstream effect on the prompt cache. |
| `generate_mtp` (`cpp:3906`) and `generate_speculative_with_draft` (`cpp:3571`) | Check `tokens.size() < 2` | Return `GENERATE_FAILED` with "prompt must have at least 2 tokens". The real cause is only in the log. |
| `do_complete` (`cpp:3941`) | No check. Logs "0 input tokens" | Passes empty tokens to `decode_loop`. `run_prefill` with zero tokens clears memory and returns true, so sampling starts with nothing decoded. I did not verify what `generate_after_prefill` does in that state. |
| `do_generate_text_only` / `do_generate_streaming_text_only` (`cpp:2555`, `:2720`) | No check | Same unverified path through `run_prefill_cached`. |
| `build_batch_results` (`cpp:1819`) | `detokenize` returns empty string on failure | Output text silently loses those pieces. |

## Summary

- The double call is size-probe plus fill, in `tokenize` and `detokenize`. Not retry.
- On tokenize failure, the empty vector travels up with no error code. Only the speculative and MTP paths check for it, and they report it as a misleading "too short" error.
- The non-speculative generation paths do not check, and the count path reports 0. Both fail silently.

I did not run the code. The findings come from reading the bodies returned by the index. The unverified points are the zero-token behaviour in `generate_after_prefill` and the prompt-cache effect of a zero prefix count.