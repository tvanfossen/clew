**Short answer:** the two `llama_tokenize` calls are a size-query pattern, not retry logic. Nothing that fails is retried.

## Why it calls twice

`LlamaCppTokenizer::tokenize()` (`src/inference/llama_cpp_tokenizer.cpp:49-71`) needs to know how many tokens the text produces before it can allocate the output vector:

1. The first call passes `nullptr` and capacity `0`. llama.cpp reports the required count as a negative number (`include/llama.h`, `llama_tokenize`).
2. The code negates that value, allocates a vector of that size, and calls again to fill it.

The second call is deterministic given the first, so there is nothing to retry. The code comments say "retry" in a few places, which is misleading. `detokenize()` (lines 92-104) has the same shape with `llama_token_to_piece`: a 256-byte stack buffer, and an exact-size second call if the first is too small.

Two problems in the first call:

- Its return value is never checked for failure. A negative value is always treated as a size.
- llama.h also says `INT32_MIN` means overflow. Negating that overflows, and the resulting negative count goes into `std::vector` construction. This needs an input over 2³¹ tokens, so it is unlikely in practice, but the code doesn't guard it.

## What the caller receives on failure

On failure, `LlamaCppTokenizer::tokenize()` returns an empty vector. Failures covered:

- `vocab_` is null: returns `{}` silently, with no log.
- The second call returns negative (practically unreachable, since the buffer is sized from the first call): logs an error and returns `{}`.
- `LlamaCppBackend::tokenize()` returns `{}` when `tokenizer_` is unset.

Empty is also a valid result for empty text with `add_special=false`, so callers cannot tell success from failure. The seam header (`include/entropic/inference/tokenizer.h`) documents this as "empty on failure or empty input."

## What the callers do with the empty vector

| Caller | Behavior on empty tokens |
|---|---|
| `do_count_tokens` → `count_tokens` (`llama_cpp_backend.cpp:825`) | Returns `0`. The C API comment (`inference_c_api.cpp:544-546`) promises a `text_len/4` estimate on error, but the `catch(...)` only fires on exceptions, so a tokenizer failure returns `0`. |
| `do_generate_text_only`, streaming variant (lines 2561, 2643, 2728) | Logs "0 input tokens" and continues into `run_prefill_cached` with an empty sequence. `run_prefill` (line 1484) clears the KV cache, runs a no-op loop, and returns `true`, so no decode happens. I did not trace the warm-keep branch or `generate_after_prefill`, so I can't confirm what the sampler reads next. It is probably sampling from logits that were never produced for this request. |
| `do_generate_batch` (line 1911) | `batch_shared_prefix_len` returns 0 when any sequence is empty, so the batch is not viable and the code falls back to serial `do_generate`. Each request then tokenizes again and fails again. This is the only repetition in the path, and it repeats the same deterministic failure. |
| Speculative (line 3593) and MTP (line 3921) | Checks `tokens.size() < 2` and returns `ENTROPIC_ERROR_GENERATE_FAILED` with "must have at least 2 tokens." This is the only place the failure surfaces as an error code, and the message is wrong. |
| `do_complete` (line 3947) | No check. Calls `decode_loop` with empty tokens. |
| System-prefix count (line 2066) | Returns `0`, which disables the prefix cache and falls back to a full prefill. Silent. |

## Recommendations

- Split the failure from the empty result. Return `std::optional` or an error code from the tokenizer seam, and check the first call's result before using its size.
- Reject empty prompts at the generate entry points and return a real error code, instead of decoding nothing.
- Either make `count_tokens` return the estimate on failure, as its C API comment says, or correct the comment.

This is a static read only. I did not build or run the tests, and I did not trace the warm-keep branch of `run_prefill_cached`, so the stale-logits consequence is a likely outcome, not a confirmed one.