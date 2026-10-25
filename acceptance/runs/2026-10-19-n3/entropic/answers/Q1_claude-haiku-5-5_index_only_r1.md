**Short answer:** the two calls aren't a retry in the usual sense. They're a size-probe-then-fill pattern, and the failure path returns an empty result that no caller can distinguish from a legitimately empty input.

**Caveat:** the index doesn't hold the bodies of `LlamaCppTokenizer::tokenize` or `detokenize`; those live in `src/inference/llama_cpp_tokenizer.cpp`, which the index only knows as a file row. So the two-call mechanics below come from the Doxygen detail text, not the source. Reading that file would confirm it.

**Why it calls twice**

- **Tokenize (`LlamaCppTokenizer::tokenize`, `src/inference/llama_cpp_tokenizer.h:44`):** the Doxygen says the result is empty if `llama_tokenize` "returned a negative actual-count on the sized retry." That is the standard llama.cpp idiom: call with a guessed buffer, and if it returns a negative count, that count is the required size. The second call uses a correctly sized buffer. Failure means the sized call still returns negative.
- **Detokenize (`LlamaCppTokenizer::detokenize`, line 47):** same shape. It returns empty when "the retry decode returned non-positive," so it uses the same probe-then-fill pattern on `llama_token_to_piece`.

**Is it retry logic?** No. It's one resize-and-retry per call, with no backoff, no loop, and no retry on transient failure. The second call exists because the first call's buffer was the wrong size, not because the first call failed.

**What the caller receives on failure**

There is no error channel. `tokenize` returns `std::vector<int32_t>`, and `detokenize` returns `std::string`, so failure is an empty value.

- `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788`) passes the empty vector through. It also returns empty when no tokenizer is wired.
- `LlamaCppBackend::detokenize` (`:809`) passes the empty string through.

**What the callers do with it**

| Caller | Effect of an empty result |
|---|---|
| `do_count_tokens` (`:825`) | Returns `0`, which is also the documented result for empty input. Callers cannot tell failure from an empty string. |
| `compute_prefix_token_count` (`:2051`) | Returns `0`, so the cached system-prefix boundary becomes 0. I haven't traced what the prompt cache does with a 0-length prefix. |
| `do_complete` (`:3941`) | Logs "0 input tokens" and runs `decode_loop` on an empty prompt. |
| `do_generate_text_only` (`:2555`) | Runs `run_prefill_cached` on an empty prompt. `run_prefill` (`:1484`) with zero tokens executes no `llama_decode` and returns `true`. So the `prefill_error()` path is never reached, and generation proceeds with no prompt. |
| `step_token` (`:1521`) | Appends an empty piece on detokenize failure and keeps going. Output tokens are dropped silently. |
| `tokenize_text` (`backend.h:273`) | Documented as empty on error. |

**Main concern:** a tokenize failure during generation shows up as an empty prompt that runs, plus silently dropped output pieces, rather than as a `GENERATE_FAILED` error. The only error-carrying path is `prefill_error()`, and the empty-token case never reaches it. Most of this is traced from the index, and the empty-prompt behaviour in `try_warm_reuse` and `generate_after_prefill` is unverified. If you want the failure to surface, the fix is to make the tokenizer return a status, or to have the callers check for empty tokens before prefill.