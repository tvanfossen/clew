**Short answer:** The double call is a size-probe, not retry logic. The only real failure path does not retry; it logs and returns empty.

## Why it calls twice

The index shows two llama.cpp call pairs. The one you're probably asking about is in `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:49-71`):

1. **Probe:** `llama_tokenize(vocab_, text, ..., nullptr, 0, ...)` with no output buffer. This asks llama.cpp how many tokens the text needs. The code then does `if (n < 0) n = -n;`, which uses the negated return as the size.
2. **Fill:** It allocates `std::vector<int32_t>(n)` and calls `llama_tokenize` again with that buffer. If `actual < 0`, it logs `Tokenization failed for text of length N` and returns `{}`. Otherwise it resizes to `actual` and returns.

The second call is required because llama.cpp's tokenizer will not return the token array until the caller supplies a buffer large enough for it. This is the standard two-pass sizing idiom.

The second pair is in `LlamaCppTokenizer::detokenize` (lines 86-105). It calls `llama_token_to_piece` with a 256-byte stack buffer, and if that returns negative it allocates the exact size and calls again. The source comment literally says "Buffer too small — retry with exact size." That is a resize, not a retry.

**Is it retry?** No. A retry re-attempts an operation that failed in the hope it succeeds. Here the first call's negative return is the protocol's way of reporting size, so it is not a failure. The only failure check is on the second call, and that is not retried. One caveat: the probe treats *any* negative first return as a size, so a genuine error from that call would produce a bogus allocation before the second call catches it. I'm relying on the llama.cpp convention for this, since its source is not indexed.

## What the caller receives on failure

The return is `std::vector<int32_t>{}`. That same value also means "vocab is null" and "empty input." The `Tokenizer::tokenize` contract says "empty on failure or empty input," so the caller can't distinguish them from the return alone.

The chain from there:

| Caller | What happens to the empty result |
|---|---|
| `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788`) | Passes it through. Returns `{}` if no tokenizer is wired. |
| `do_complete` (`:3941`) | No guard. Logs `0 input tokens`, then `decode_loop` → `run_prefill({})`. The loop body never runs, `llama_memory_clear` has already run, and `run_prefill` returns `true`. `generate_after_prefill` then samples from a context that was never prefilled. This is an inference from the bodies; the index does not show what sampling against unprimed logits does. |
| `do_generate_text_only` (`:2555`) | No guard. Empty tokens go into `run_prefill_cached` → `prefill_dispatch` → `run_prefill`, which returns `true`, and generation proceeds the same way. |
| `generate_mtp` (`:3906`) | **Guarded.** `tokens.size() < 2` → `spec_error(GENERATE_FAILED, "MTP prompt must have at least 2 tokens")`. The failure surfaces as an error. |
| `generate_speculative_with_draft` (`:3571`) | **Guarded.** Same check, `"speculative prompt must have at least 2 tokens"`. |
| `compute_prefix_token_count` (`:2051`) | Returns `0` for a failed system-prompt tokenization. `prefill_and_cache_prefix` treats `prefix <= 0` as "no caching" and does a plain prefill, so the cache is silently skipped. |
| `do_count_tokens` (`:825`) → `InferenceBackend::count_tokens` → `entropic_inference_count_tokens` | Returns `0`. The C API has no error channel and only returns `len/4` if an exception is thrown. A consumer sees "zero tokens," indistinguishable from empty text. |

## Takeaways

- The double call is a documented sizing protocol. Renaming it "retry" would be wrong. `detokenize`'s comment uses that word for a resize.
- Failure is signaled only by an empty vector, and that signal is ambiguous with empty input.
- Only the MTP and speculative paths check for it. `do_complete` and `do_generate_text_only` will carry an empty prompt into prefill and generation, and `count_tokens` reports failure as `0`. Those are the places to look if a bad tokenizer state ever shows up as odd output or a zero token count.