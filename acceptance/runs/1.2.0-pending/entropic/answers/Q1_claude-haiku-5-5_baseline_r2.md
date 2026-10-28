**Short answer:** the two calls are in one function, not two places, and they are a size-query-then-fill pair, not retry logic.

**Why it calls twice**

Both calls are in `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:55` and `:61`). llama.cpp's `llama_tokenize` needs a buffer big enough for the output and doesn't allocate one. The first call passes a null buffer with capacity 0. It returns the negative of the required token count, which the code flips to a positive `n` (line 58). The code then allocates `n` slots and makes the second call, which does the actual encoding into that buffer (line 61). The second call is the real work, and there is no loop, backoff, or second attempt at the same operation.

I wouldn't call it retry logic. The doc comment at `llama_cpp_tokenizer.cpp:44-45` says "the sized retry," which is misleading. A better description is "size query, then fill."

**What the caller gets on failure**

- If the second call returns a negative value, the tokenizer logs at error level (line 65) and returns `{}`, an empty vector. There is no error code, exception, or status.
- If `vocab_` is null, it returns `{}` with no log at all (line 52).
- `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788`) passes the vector through. If no tokenizer is wired, it also returns `{}` silently (line 795).
- The interface contract (`include/entropic/inference/tokenizer.h:55`) says "empty on failure or empty input." Those two cases look identical to every caller.

**What the callers do with the empty vector**

| Caller | Location | What happens |
|---|---|---|
| `do_count_tokens` | `llama_cpp_backend.cpp:825` | Returns `0` as if it were a real count. |
| `tokenize_text` | `:837` | Returns an empty vector to the public API. |
| `do_generate_text_only`, `do_generate_cancellable`, `do_generate_stream`, `do_complete` | `:2561`, `:2643`, `:2728`, `:3947` | Log "0 input tokens" and continue into `run_prefill_cached` / `decode_loop` with no emptiness check. |
| `do_generate_batch` | `:1911` | Builds empty token lists and computes the shared prefix from them. |
| system-prompt token count | `:2066` | Returns `0`. `prefill_and_cache_prefix` then takes its no-cache fallback (`:2097`), so the cache silently misses. |
| speculative and MTP paths | `:3593`, `:3921` | Check `tokens.size() < 2` and return `GENERATE_FAILED` with "must have at least 2 tokens." This is a misleading error for a tokenization failure. |

For the generation paths, an empty prompt reaches prefill. `run_prefill` (`:1484`) has an empty loop when there are zero tokens, so it succeeds. I did not trace `decode_loop` on an empty prompt, so I can't say what it produces. The likely outcome is sampling from stale or uninitialized logits, but that is unverified.

**Contrast:** the vision path, `mtmd_prefill` (`llama_cpp_backend.cpp:2407`), checks the return code of its own tokenize call and returns an error with a message. The text path has no equivalent error channel.

**Not checked:** whether any test exercises the failure branch of `LlamaCppTokenizer::tokenize`. The tests I found mock the seam, and the file header says this file is intentionally outside the unit-test gate.