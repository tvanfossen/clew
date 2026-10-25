**Short answer:** the two calls are a size-probe-then-resize, not retry logic. When tokenization fails, the caller gets an empty vector, which nothing downstream checks, so the failure turns into silently wrong output.

**Why it calls twice.** The index shows the tokenizer adapter `entropic::LlamaCppTokenizer` (`src/inference/llama_cpp_tokenizer.h:35`) forwarding to llama.cpp's `llama_tokenize` and `llama_token_to_piece`. Its `tokenize` documents a "sized retry": it calls `llama_tokenize` with a guessed buffer, and if llama.cpp returns a negative count, that count is the required length. It then allocates and calls again. `detokenize` has the same shape, documented as "the retry decode" (`llama_token_to_piece` with `special=false`). Both are standard llama.cpp two-phase C API usage. The second call only happens when the first reports the buffer was too small. The first call is not a failed operation being retried.

**Caveat:** the index does not expose `llama_cpp_tokenizer.cpp`'s body, so I'm working from the header and dossier docs, not the source. The "twice in a row, two places" framing could also mean the `mtmd_tokenize` call in `mtmd_prefill`. That one is a separate path with its own error code, not the tokenizer seam.

**What the caller receives on failure.** This is the part that matters.

| Layer | On tokenization failure |
|---|---|
| `LlamaCppTokenizer::tokenize` | Empty vector (null `vocab_` or negative second count) |
| `LlamaCppTokenizer::detokenize` | Empty string (null `vocab_` or non-positive retry) |
| `LlamaCppBackend::tokenize` | Forwards the empty vector; also empty when `tokenizer_` is unwired |
| `InferenceBackend::tokenize_text` | Documented as "empty if COLD or error" |
| `count_tokens` / `do_count_tokens` | `0` |
| `compute_prefix_token_count` | `0` prefix tokens |

Empty is indistinguishable from a legitimately empty input, and no error is raised.

**What the callers do with it.**
- `do_complete` and `do_generate_text_only` tokenize the prompt and log "N input tokens" with no empty check. They pass the tokens straight into prefill and decode. The only error checks in `do_generate_text_only` are sampler init and prefill, so an empty prompt goes forward. I did not verify what the decode loop does with zero tokens.
- `compute_prefix_token_count` returns 0 when tokenization fails. That feeds `prefill_dispatch`, which decides where the prompt-cache prefix ends. I'm inferring from the bodies that a 0 prefix quietly disables prefix caching for that turn. I have not confirmed it in the index.
- `step_token` calls `detokenize` per generated token and appends the result. A failed detokenize appends an empty piece and generation continues. Its only error return is `llama_decode` failing, so the text comes out silently truncated, and stop-sequence checks run against the gap-riddled text.
- `build_batch_results` concatenates detokenized pieces the same way, so batch output is silently shortened.

**Recommendation.** Have the adapter report failure through an error code or callback, as the architecture doc's rule 6 already requires for crossings like this. Then `do_complete` and `do_generate_text_only` can reject an empty prompt, and `step_token` can fail the turn instead of dropping the piece. I'd also check the `llama_cpp_tokenizer.cpp` body directly, since the index can't show the exact retry conditions.