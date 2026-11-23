**Short answer:** the two `llama_tokenize` calls are not retry logic. They are a size query followed by a fill. Both calls are in one function, not two places.

## Why it calls twice

Both calls are in `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:49-71`):

1. **Line 55:** `llama_tokenize(vocab_, ..., nullptr, 0, ...)` passes no output buffer. llama.cpp returns the negated number of tokens it would need. The code flips the sign (`if (n < 0) n = -n;`), allocates a vector of that size, and moves on.
2. **Line 61:** the same call again, this time with the buffer. `actual` is the real token count, and `resize(actual)` trims the vector.

This is the standard two-phase pattern for a C API that has no "allocate for me" mode. The second call is not conditional on the first call succeeding. The first call only sizes the buffer. A failure can only happen at the second call, when `actual < 0`.

The `LlamaCppBackend::tokenize` wrapper (`llama_cpp_backend.cpp:788-800`) does not call llama.cpp at all. It forwards to `tokenizer_->tokenize()`, so it adds no second call.

## Failure: what the caller gets

When `actual < 0`, the function logs an error with the text length only and returns `{}`, an empty vector (`llama_cpp_tokenizer.cpp:64-67`). The same `{}` comes back when `vocab_` is null, and `LlamaCppBackend::tokenize` returns `{}` when no tokenizer is wired. The result is that failure, missing tokenizer, and empty input all look the same to the caller. Only the log line tells them apart, and only for the first failure.

Propagation by caller:

| Caller | What it does with `{}` | Source |
|---|---|---|
| `do_count_tokens` | returns `0`, which `entropic_inference_count_tokens` passes to the C client | `llama_cpp_backend.cpp:825`, `inference_c_api.cpp:558` |
| `tokenize_text` | returns an empty ID vector | `llama_cpp_backend.cpp:837` |
| Prefix token count (system prompt) | returns `0` | `llama_cpp_backend.cpp:2066` |
| `do_generate_batch` | builds batch with a zero-length sequence | `llama_cpp_backend.cpp:1911` |
| Text-only generate and streaming | logs "0 input tokens", then prefill | `llama_cpp_backend.cpp:2561, 2728` |
| `do_complete` | calls `decode_loop` with no tokens | `llama_cpp_backend.cpp:3947` |
| Speculative and MTP paths | **only caller that checks**: `tokens.size() < 2` returns `ENTROPIC_ERROR_GENERATE_FAILED` with "must have at least 2 tokens" | `llama_cpp_backend.cpp:3593, 3921` |

So the main path has no check. `run_prefill` with zero tokens runs a zero-iteration loop and returns `true` (`llama_cpp_backend.cpp:1484-1503`). Generation then proceeds with no prompt. I did not trace `generate_after_prefill` or the batch path on empty input, so what they do there is unverified. What I can say is that no error code reaches the user from the text-only generate path.

The speculative and MTP paths do convert the failure into an error code, but the message is wrong. It reports a short prompt when the real cause was a tokenizer failure.

## Summary

- The double call is llama.cpp's size-then-fill protocol, not retry.
- A tokenizer failure is reported only as an empty vector, which is then reported as `0` by the count API and as "empty prompt" by the generate paths.
- The error log in `LlamaCppTokenizer` is the only place the failure is visible.
- The fix would be to return a status, for example `tl::expected` or an out-parameter error code, so callers can distinguish failure from empty input. That changes the `Tokenizer` interface, so per the project rules it needs a design proposal first.