**Short answer:** the two calls are a size-query, not retry logic. The failure path has no retry, and it turns into an empty result that callers can't tell apart from a real empty result.

## Why it calls twice

Both pairs are in `src/inference/llama_cpp_tokenizer.cpp`, the thin adapter over llama.cpp.

**Tokenize (lines 55 and 61).** llama.cpp's `llama_tokenize` takes a caller-supplied output buffer. When the buffer is too small it returns the negative of the required count, so the code does:

1. Call with a null buffer and size 0 to learn the token count (`n`, negated if negative).
2. Allocate a `std::vector` of that size and call again to fill it.
3. If the second call returns negative, log `"Tokenization failed for text of length N"` and return `{}`.

**Detokenize (lines 93 and 99).** The same pattern with `llama_token_to_piece`. It tries a 256-byte stack buffer first. If that returns negative, it allocates the exact required size and calls again.

Neither is a retry in the sense of re-attempting a failed operation. Nothing loops, nothing backs off, and the first call isn't a failure to be retried. The first call is a query for the buffer size. The header comment says "sized retry", which is the source of the confusion. The same two-call pattern also appears in `tests/model/test_gh87_common_chat_e2e.cpp:51`.

## What the caller receives on failure

Failure is signalled only by an empty vector (or an empty string for detokenize). There is no error code, exception, or status out-parameter.

- `LlamaCppTokenizer::tokenize` returns `{}`.
- `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788`) forwards that. It also returns `{}` when no tokenizer is wired, so the "not wired" and "llama.cpp failed" cases look the same.
- `LlamaCppTokenizer::detokenize` returns `""` on failure. Note that `llama_token_to_piece` returns non-positive for a zero-length piece as well, so "empty" is ambiguous there too.

An empty token vector is also a legitimate result for empty input with `add_special=false`. The caller cannot distinguish the two cases.

## What the callers do with it

I traced the callers through the index and source. Items marked unverified are where I did not read the downstream code.

| Caller (`llama_cpp_backend.cpp`) | With empty result |
|---|---|
| `do_count_tokens` (826) | Returns `0`. A tokenizer failure is reported to the user as a zero-token count. |
| `tokenize_text` (837–839) | Returns an empty ID list. The interface doc says "empty if COLD or error", so both states look identical. |
| `compute_prefix_token_count` (2066) | Returns `0`, meaning "no system prefix". This feeds `prefill_dispatch`, which can silently disable or mis-key the prompt cache. |
| `do_complete` (3947) | Logs "0 input tokens", then calls `decode_loop` with an empty prompt. The code does not check for empty before doing this. |
| `do_generate_text_only` (2561) and the other generate paths (2643, 2728, 3593, 3921) | Pass the empty sequence to `run_prefill_cached` / `run_prefill`. I did not verify how `run_prefill` handles an empty token list. This is the most important unverified point. |
| Batch path (1911) | Stores an empty token sequence for that request. |
| Detokenize callers (1534, 1819) | Append an empty piece. Output text silently loses that token. |

So the failure is not surfaced in the public return values. It turns into a zero count, a missing prefix, an empty prompt, or dropped text. The only trace is one `logger->error` line in `LlamaCppTokenizer::tokenize`, which logs the length and not the text. The unit tests use a mock tokenizer, and the real adapter is excluded from the CPU unit gate by design (`llama_cpp_tokenizer.cpp:6–10`).

## Open item

To confirm the generate-path behaviour, read `run_prefill` / `try_warm_reuse` for an empty `tokens` input. If `run_prefill` does not guard against it, an empty prompt reaches llama_decode. I did not check that, so I can't say what happens there.