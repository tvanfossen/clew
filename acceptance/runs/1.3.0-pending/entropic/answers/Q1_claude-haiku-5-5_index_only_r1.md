**Short answer:** neither double call is retry logic. Both are a size-probe-then-fill pattern. On failure, tokenization returns an empty result without retrying, and the empty result is not distinguishable from a legitimate empty input. The callers I could trace then carry on with it silently.

**The two calls**

1. **`LlamaCppTokenizer::tokenize`** (`src/inference/llama_cpp_tokenizer.cpp:49-71`) calls `llama_tokenize` twice in a row with the same input. The first call passes a null buffer and size 0 to learn how many tokens are needed. llama.cpp answers with a negative number, which the code negates. The code then allocates that many slots and makes the second call to fill them. If the second call returns negative, it logs an error and returns `{}`.

2. **`LlamaCppTokenizer::detokenize`** (`src/inference/llama_cpp_tokenizer.cpp:86-105`) calls `llama_token_to_piece` with a 256-byte stack buffer. If the piece doesn't fit (negative return), it allocates the exact required size and calls again. This is a resize-on-short-buffer, closer to a retry, but it is still one deterministic pass. It is not triggered by a failure, and it does not repeat the same call hoping for a different result.

Neither path loops, backs off, or re-attempts after an error. Calling this retry logic would be wrong.

**What the caller receives on failure**

- `LlamaCppTokenizer::tokenize` returns an empty `std::vector<int32_t>` after logging `"Tokenization failed for text of length N"`. It also returns empty when `vocab_` is null.
- `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788-800`) forwards that empty vector. It also returns empty when `tokenizer_` is null.
- `LlamaCppBackend::do_count_tokens` returns `tokens.size()`, so a failed tokenization becomes a count of **0**.
- `InferenceBackend::count_tokens` returns `do_count_tokens` when loaded. The `len/4` estimate only applies when the model is not loaded, not when tokenization fails.
- `entropic_inference_count_tokens` (`inference_c_api.cpp:548-562`) returns that 0 to C callers. Its `catch(...)` → `len/4` fallback never fires for this case, because the failure is a return value, not an exception. C consumers get a silent 0.

**What the callers do with the empty vector**

- **`do_complete`** (`llama_cpp_backend.cpp:3941-3955`) logs "0 input tokens", then passes the empty list to `decode_loop`. I found no emptiness guard in its body.
- **`do_generate_text_only`** (`llama_cpp_backend.cpp:2555-2598`) also has no emptiness check. It calls `run_prefill_cached` with the empty list. `run_prefill` (`llama_cpp_backend.cpp:1484-1503`) clears the KV memory, has a zero-iteration loop, and returns `true`. So the failure is not caught by `prefill_error()`. Sampling then starts from an empty context. This is the most serious finding. The failure is silent, and it surfaces only as incoherent output or an odd `finish_reason`. I did not verify `decode_loop` or the sampler behavior with no prompt.
- **`compute_prefix_token_count`** (`llama_cpp_backend.cpp:2051-2068`) returns 0 when tokenization fails. `prefill_dispatch` passes that 0 into `prefill_and_cache_prefix`, which I did not read. A prefix of 0 could mean a cache entry with no prefix state, but that is unverified.
- **`TokenCounter`** (`include/entropic/core/compaction.h`) is a `len/4`-style estimator. It does not call the tokenizer, so tokenization failures do not reach it directly.

**Caveats**

- This is from the index alone. Bodies are verbatim, but the callers lists are incomplete. Several `callers_unresolved` flags were set, so there may be other call sites I could not see.
- I did not trace `decode_loop`, `prefill_and_cache_prefix`, or the sampler, so the empty-prompt behavior above is inferred from the bodies of `do_complete`, `do_generate_text_only` and `run_prefill`.

**Suggested fix:** make failure distinguishable. Options are an error code or `std::optional`/`expected` return from the `Tokenizer` seam, or at minimum a guard in `do_complete` and `do_generate_text_only` that returns an error result when `tokens.empty()` and the prompt was not empty. Whether to change the seam signature is an interface decision, and `i_*.h` headers are immutable per the project rules, so it needs your approval.