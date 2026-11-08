**Why it calls twice:** The two `llama_tokenize` calls are both inside `LlamaCppTokenizer::tokenize()` (`src/inference/llama_cpp_tokenizer.cpp:55` and `:61`). The first call passes a null buffer and size 0 purely to learn the token count. llama.cpp returns the negative of the required count in that case, so line 58 flips the sign. The second call fills a vector of that size. This is the standard two-phase sized-buffer pattern.

The only other place with a second call is `LlamaCppTokenizer::detokenize()` (lines 93 and 99), which uses a small stack buffer and retries with the exact size when the first call reports it was too small. That one is a genuine resize-and-retry, but it is a different function.

**Is it retry logic?** No. Neither call is retried because of a failure. The first call always runs, and it is a size query rather than an attempt that failed. The second call is not repeated if it fails. The comments at `llama_cpp_tokenizer.cpp:44-45` and `:97` use the word "retry", which is misleading.

**What the caller receives on failure:**

- `LlamaCppTokenizer::tokenize()` logs an error and returns `{}`. The same empty vector is returned when `vocab_` is null.
- `LlamaCppBackend::tokenize()` (`llama_cpp_backend.cpp:788`) passes that through, and also returns `{}` when no tokenizer is wired.
- The interface contract (`include/entropic/inference/tokenizer.h:48`) says empty means "failure or empty input". Callers cannot tell the two apart, and no error code reaches them.

**What the callers do with the empty vector:**

| Caller | Behaviour on empty |
|---|---|
| `do_count_tokens` (`:825`) and the system-token count (`:2066`) | Return 0. Silent. |
| `tokenize_text` (`:837`) | Returns empty. |
| `do_generate_text_only` (`:2561`), the cancellable path (`:2643`), and the stream path (`:2728`) | No check. The empty prompt goes straight to `run_prefill_cached`. |
| `do_complete` (`:3947`) | No check. It goes to `decode_loop`. |
| Batch path (`:1911`) | `batch_shared_prefix_len` returns 0, so the batch fast-path is rejected and it falls back to the serial generate path, which has no check either. |
| Speculative (`:3593`) and MTP (`:3921`) | Check `size() < 2` and return an error, "prompt must have at least 2 tokens". The real cause, a failed tokenization, is lost. |

Only the speculative and MTP paths turn the empty result into an error. The others carry on as if the prompt were empty.

**What I verified and what I did not:** I traced `run_prefill` (`llama_cpp_backend.cpp:1484`). With zero tokens it clears the KV cache, decodes nothing, and returns true. So the generate and complete paths reach sampling with no prompt in the KV cache. I did not trace `try_warm_reuse`, `prefill_dispatch`, or `step_token` for the zero-token case, so I cannot say what text the model produces there. It could be garbage, an immediate stop, or an error from llama.cpp. The code does not guard it either way.

**Suggested fix (not applied, since you asked a question):** Make tokenization failure distinguishable from empty input, either with a status return or an error code. Then check it at the top of each generate, stream, complete, and count entry point and return `ENTROPIC_ERROR_GENERATE_FAILED` with the real message. That would replace the silent 0 and the misleading "at least 2 tokens" message.