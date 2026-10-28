**Short answer:** the two calls are a size probe followed by a fill, not retry. Nothing in the tokenizer retries a failure.

**Why it calls twice**

The calls are both in `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:49-71`), not in two places:

1. **Line 55:** `llama_tokenize(vocab, text, nullptr, 0, ...)`. llama.cpp can't return tokens into a buffer it doesn't have, so passing a null buffer and zero length returns the negated token count needed. The code flips the sign and sizes the vector.
2. **Line 61:** the same call with the real buffer. It runs on every invocation, whether or not the first call succeeded, and its result sets the final size.

The only retry-shaped code in this file is `LlamaCppTokenizer::detokenize` (lines 93-103). It calls `llama_token_to_piece` with a 256-byte stack buffer and, if that returns a negative size, reallocates to the exact size and calls again. That is "grow the buffer and retry," still not a retry of a failure. Its second-call result is only checked for `n > 0`, so a failure there silently becomes an empty string.

**Failure path outward**

| Layer | On `llama_tokenize` failure | Effect |
|---|---|---|
| `LlamaCppTokenizer::tokenize` | Logs an error with the text length only, returns `{}` | Also returns `{}` when `vocab_` is null, so "failed" and "empty input" look identical |
| `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788`) | Forwards `{}` | Also `{}` when no tokenizer is wired |
| `do_count_tokens` (`:825`) | Returns `0` | Silent. The C API `entropic_inference_count_tokens` returns `0` with no error channel |
| `tokenize_text` (`:837`) | Returns an empty vector | Caller can't tell failure from no tokens |
| Speculative and MTP paths (`:3594`, `:3922`) | Return `GENERATE_FAILED` with "prompt must have at least 2 tokens" | The real cause (tokenizer failure) is replaced by a misleading message |
| `do_generate_text_only` (`:2561`) and `do_complete` (`:3947`) | No empty check. Logs "0 input tokens" and continues into prefill | I did not trace what prefill does with zero tokens, so the outcome there is unverified. The error would surface later, if at all |
| `compute_prefix_token_count` (`:2066`) | Returns `0` | Downstream effect on prefix caching not traced |

**Two things to fix or check**

- The `LlamaCppTokenizer::tokenize` header comment says "negative actual-count on the sized retry," but there is no retry, only a second call. The comment is inaccurate.
- The failure contract is "empty vector," and every caller receives it as if it were a valid result. A count of `0` or an empty prompt is never reported as an error.

Nothing was modified. The index reported only a test caller for `LlamaCppTokenizer::tokenize` because backend calls go through the virtual `Tokenizer` interface. I traced the backend callers by grep instead.