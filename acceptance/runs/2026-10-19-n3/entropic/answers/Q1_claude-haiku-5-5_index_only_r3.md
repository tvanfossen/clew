## Why it calls llama.cpp twice

The two calls are a buffer-size negotiation, not retry logic. The index's doc comments say `LlamaCppTokenizer` forwards to `llama_tokenize` (in `tokenize`) and `llama_token_to_piece` (in `detokenize`). The `tokenize` doc says it returns empty when "`llama_tokenize` returned a negative actual-count on the sized retry". The `detokenize` doc says the same about "the retry decode returned non-positive". So the pattern is: call once with a guessed buffer, and if llama.cpp reports that the buffer is too small, call again with the size it asked for.

Retry implies re-attempting something that may have failed for a transient reason. This is deterministic and happens at most once. There is no backoff and no attempt limit. If the second call also fails, the result is just empty.

Caveat: I could not read the bodies of `LlamaCppTokenizer::tokenize` or `detokenize`. The qualified lookups returned no dossier, so this rests on the doc comments.

## What the caller receives on failure

`LlamaCppTokenizer::tokenize` returns an empty `std::vector<int32_t>`. There is no error code, exception, or status. `LlamaCppBackend::tokenize` (`src/inference/llama_cpp_backend.cpp:788`) also returns `{}` when no tokenizer is wired.

An empty result is also the correct answer for an empty prompt, so the caller cannot tell "failed" from "nothing to encode".

## What the callers do with it

| Caller | What happens on empty |
|---|---|
| `do_count_tokens` → `count_tokens` → `entropic_inference_count_tokens` | Returns `0`. The C API cannot distinguish failure from zero tokens. |
| `compute_prefix_token_count` | Returns `0`. `prefill_dispatch` then treats the system prefix as empty, silently. |
| `do_generate_text_only`, `do_generate_streaming_text_only`, `do_complete` | No empty check. They log "0 input tokens" and pass the empty vector to prefill. |
| `generate_speculative_with_draft`, `generate_mtp` | Guarded by `tokens.size() < 2`. Returns `GENERATE_FAILED` with "prompt must have at least 2 tokens". The message is misleading, since the real cause is the tokenizer failure. |
| `tokenize_text` (public) | Returns empty, documented as "empty if COLD or error". Same ambiguity. |

On the plain generate paths, `run_prefill` clears the KV cache (`llama_memory_clear`, line 1485) before checking the token count. An empty vector therefore wipes the resident KV and decodes nothing, and the function still returns `true`. I did not inspect `generate_after_prefill`, so what sampling does with no prompt is unverified. It is probably an error or junk output, not a clean failure.

## Recommendation

The seam collapses "tokenizer failed" into "empty". To fix it, return a status or `std::optional` from the tokenizer seam. Then add the same empty-prompt guard to the plain generate and complete paths that the speculative and MTP paths already have. Your call on whether to do that.