## Why it calls llama.cpp twice

The two `llama_tokenize` calls are in one function, `entropic::LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:49-71`), at lines 55 and 61. There is no second site in a different function.

- **Call 1 (line 55)** passes a null buffer and size 0. llama.cpp answers with a negative number whose magnitude is the required token count. The code negates it to get `n`.
- **Call 2 (line 61)** allocates `n` slots and fills them. It then shrinks the vector to `actual` tokens.

This is a size probe, not retry logic. Nothing loops, and nothing re-runs after a failure. The first call only measures, and the second call is the real work.

## Failure path

**Tokenizer level.** If `vocab_` is null, it returns an empty vector. If the second call returns a negative `actual`, it logs `"Tokenization failed for text of length N"` (the length only, not the text) and returns an empty vector. No status or error code is raised.

**Backend level.** `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788`) returns `{}` when no tokenizer is wired and otherwise forwards the result. The `Tokenizer::tokenize` doc says "empty on failure or empty input", so an empty vector cannot be told apart from an empty prompt.

**What callers do with the empty vector:**

| Caller | Result on failure |
|---|---|
| `do_count_tokens` (`llama_cpp_backend.cpp:825`) | Returns `0`. The C entry point `entropic_inference_count_tokens` passes that `0` straight through; its `len/4` estimate only applies when an exception is thrown, which a tokenization failure does not cause. |
| `tokenize_text` (`:837`) | Returns an empty vector. Its public doc says "empty if COLD or error". |
| `do_complete` (`:3941`) | Logs "0 input tokens", then calls `decode_loop` with the empty vector. |
| `do_generate_text_only` (`:2555`) and `do_generate_streaming_text_only` (`:2720`) | Log "0 input tokens", then call `run_prefill_cached`. If that returns false, the caller gets `prefill_error()`. |
| `compute_prefix_token_count` (`:2051`) | Returns `0`, so prefix-cache sizing is silently wrong. |
| `generate_mtp` (`:3906`) | The only caller that checks. `tokens.size() < 2` returns `ENTROPIC_ERROR_GENERATE_FAILED` with "MTP prompt must have at least 2 tokens". That is a clean error, but the message blames prompt length rather than tokenization. |

So a tokenization failure is silent everywhere except for the one log line in the tokenizer, and the MTP path. Most generation paths never see an error code.

## Gaps in what the index shows

- I did not confirm how `run_prefill`, `try_warm_reuse`, or `prefill_dispatch` handle an empty token vector. If they accept it, `do_complete` and the text-only paths could generate from zero context with no error.
- The index flags unresolved call sites for `do_count_tokens` and `do_complete`, so some callers may be missing from the caller lists above.