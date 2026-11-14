**Short answer:** the two calls are a size probe followed by the real call, not retry logic. When tokenization fails, the caller gets an empty vector with no error signal, and nothing upstream checks for it. The generation paths then carry on with zero tokens.

**Why it calls twice**

There are two places with this pattern, and each is a single function that calls llama.cpp twice:

- **`LlamaCppTokenizer::tokenize`** (`src/inference/llama_cpp_tokenizer.cpp:55` and `:61`). llama.cpp's `llama_tokenize` returns a negative number when the output buffer is too small or absent, and that negative number is the required size. The first call passes a null buffer to learn the size, and the second call fills a `std::vector` of that size. The first call always returns negative for non-empty input, so the second call always runs.
- **`LlamaCppTokenizer::detokenize`** (`:93` and `:99`). This one does have a fallback: it tries a 256-byte stack buffer, and if that is too small it resizes to the required size and calls again. This is buffer resizing, not a retry. The second call uses the size llama.cpp just reported and does not re-attempt a failed operation.

Neither path retries a transient failure. Retry logic would mean repeating the same call after an error and possibly backing off. Here the second call is the work itself.

**What the caller receives on failure**

- `tokenize` logs `"Tokenization failed for text of length N"` at ERROR (`:64–67`) and returns `{}`. The message includes only the length, not the text or the vocab state.
- The first call's return is only sign-flipped, not validated. If it somehow returned 0, the code proceeds with an empty vector.
- `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788–800`) passes `{}` through. It also returns `{}` when no tokenizer is wired, so the two cases look identical to callers.
- `detokenize` on a failed second call returns `""`, with no log line.

**What the callers do with it**

I searched `src/` for `tokens.empty()`, `ids.empty()`, or any check on the failure. There is none, so every caller treats the empty result as valid input.

| Caller | What happens on an empty vector |
|---|---|
| `do_count_tokens` (`llama_cpp_backend.cpp:825`) → `InferenceBackend::count_tokens` → `entropic_inference_count_tokens` (C API) | Returns **0**. Callers see a zero-token text with no error. |
| `compute_prefix_token_count` (`:2051`) | Returns **0**, so a system prefix looks like it has no tokens. This value feeds the prompt-cache path at `:2289`. |
| `do_complete` (`:3941`) | Logs "0 input tokens", then `decode_loop` → `run_prefill`. `run_prefill` with `n_tokens = 0` skips the loop and returns **true**, so no error is raised. Sampling then runs on whatever state the context holds. I did not check what the sampler does without a fresh decode. |
| `do_generate_text_only` (`:2555`) | Same as `do_complete`. `run_prefill_cached` is passed empty tokens. I did not trace all of its branches, so I can't say whether the empty input is caught deeper down. |
| `step_token` → `detokenize` (`:1521`) | An empty piece is appended and `on_token` gets an empty `string_view`. Generation continues, and text is silently missing from the output. |

`GenerationResult.error_code` and `finish_reason` are not set on any of these tokenization-failure paths. The only error signal is the single log line.

**Where I stopped**

I did not check whether the engine's compaction budgeting calls the backend's `count_tokens` (the C API path is confirmed, the compaction path is not). I also did not check what `try_warm_reuse` and `prefill_dispatch` do with an empty token list, or what the sampler returns without logits. Those would settle whether the empty-input case produces a clean error or garbage output.

If you want this fixed, the minimal change is a check in `LlamaCppBackend::tokenize` (or at each of the five call sites) that surfaces a tokenization failure as `ENTROPIC_ERROR_GENERATE_FAILED` with a message. `tokenize` returning `{}` on a real failure needs to be distinguishable from empty input. That would mean changing the seam to return a status, which is an interface change under the project's rules, so it would need your sign-off.