**Short answer:** the two llama.cpp calls are a size probe, not retry logic, and when tokenization fails the error is swallowed as an empty value. Only the speculative and MTP paths check for it.

**Why it calls twice**

Both calls are in `LlamaCppTokenizer` (`src/inference/llama_cpp_tokenizer.h` and `.cpp`), which wraps llama.cpp's vocab API:

1. **`tokenize()` → `llama_tokenize`.** The header doc describes a "sized retry." llama.cpp returns a negative count when the buffer is too small, which reports the required size. The tokenizer then calls again with a buffer of that size.
2. **`detokenize()` → `llama_token_to_piece`.** Same shape. The doc says it retries when the first call returns non-positive, meaning the buffer was too small.

I wouldn't call this retry logic. The first call is a probe, not a failed attempt. Nothing is retried on a transient cause, there is no backoff, and it runs at most once. If the second call fails, that's a real failure. The word "retry" in the source is misleading.

Caveat: the `.cpp` bodies aren't indexed (the file row only says it forwards to those functions). This account comes from the header doc comments and llama.cpp's negative-return convention, not from reading the code.

**What the caller gets on failure**

There is no error channel. Failure arrives as an empty value:

| Entry point | On failure | What happens next (from the bodies) |
|---|---|---|
| `LlamaCppTokenizer::tokenize` | empty vector | Passed up through `LlamaCppBackend::tokenize` |
| `LlamaCppTokenizer::detokenize` | `""` | `step_token` appends nothing and keeps generating. `build_batch_results` silently drops the token. |
| `do_count_tokens` | `0` | Returned through `count_tokens` |
| `entropic_inference_count_tokens` (C API) | `0` | C callers get `0` with no error code. Only a thrown exception yields the `len/4` estimate. |
| `tokenize_text` | empty vector | No callers inside the indexed repo |

The prompt paths matter more than the counters:

- **`do_generate_text_only`, `do_generate_streaming_text_only`, `do_complete`** take the token vector without a size check. Empty tokens go into `run_prefill`. With zero tokens it clears KV memory, the loop doesn't run, and it returns `true`. Generation then samples with no prompt decoded. I read this from the bodies; I did not run it.
- **`generate_speculative_with_draft` and `generate_mtp`** check `tokens.size() < 2` and return `ENTROPIC_ERROR_GENERATE_FAILED`. These are the only guarded paths.
- **`compute_prefix_token_count`** returns `0` on failure. `prefill_and_cache_prefix` then skips the prefix cache and does a plain full prefill, so the failure degrades silently.

**Takeaway:** tokenization failure is invisible to the caller everywhere except the two speculative/MTP guards. The text-only and completion paths can generate from no prompt, and the C count API reports a failure as a count of 0. Adding an explicit error path at the `LlamaCppTokenizer` boundary would fix both, but that is a design change to discuss before implementing.