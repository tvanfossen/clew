**Short answer:** the double calls are a size-query idiom, not retry logic. When tokenization fails, the caller gets an empty vector, which looks the same as empty input. Most generation paths then continue with zero prompt tokens instead of reporting an error.

## Why it calls twice

The two calls are in `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:55` and `:61`). The pairs are in two functions, not two places:

- **`tokenize`** (`:55`) passes a null buffer and size 0. llama.cpp returns the negated token count it would need. The code reads that count, sizes a `std::vector`, and calls again (`:61`) to fill it.
- **`detokenize`** (`:93`, `:99`) tries a 256-byte stack buffer first. If the return is negative, it retries with the exact size. This is closer to a retry, but it is still driven by buffer size, not by failure.

A retry re-runs an operation that failed in the hope it succeeds. Here the second call is deterministic and depends on the first call's output. Its failure is logged at `:64–67` and returns `{}`. Nothing is re-attempted.

## What the caller receives on failure

| Layer | On failure |
|---|---|
| `LlamaCppTokenizer::tokenize` (`:64–67`) | Logs an error with the text length, returns `{}`. No status is propagated. |
| `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788–800`) | Forwards `{}`. Also returns `{}` when `tokenizer_` is null. |

Then each caller:

| Caller | With the empty vector |
|---|---|
| `do_count_tokens` (`:825`) | Returns `0`. `InferenceBackend::count_tokens` and `entropic_inference_count_tokens` (`inference_c_api.cpp:548`) return `0` with no error signal. The C API comment at `:544` says `text_len/4` is returned "on error", but that fallback only runs on a C++ exception. |
| `tokenize_text` (`:837`) | Returns an empty vector to the public API. |
| `compute_prefix_token_count` (`:2066`) | Returns `0`. The prefill code comment at `:2081` says a 0-token prefix falls back to a plain uncached prefill, so this one degrades acceptably. |
| `do_generate`, cancellable, streaming (`:2561`, `:2643`, `:2728`) | Only logs "0 input tokens". There is no guard. The empty token list goes to `run_prefill_cached`. |
| `do_complete` (`:3947`) | Same: no guard. `decode_loop` → `run_prefill` (`:1484–1503`) returns `true` for zero tokens, so sampling starts from whatever state the context holds. |
| Speculative (`:3594`) and MTP (`:3922`) | Guard with `tokens.size() < 2` and return `ENTROPIC_ERROR_GENERATE_FAILED`. These are the only paths that surface an error. |

So a tokenization failure on the main generate/complete/stream paths most likely yields a silent generation from an empty prompt. I did not trace `generate_after_prefill` to confirm the exact output, so treat that as the expected behavior from the code I read, not a verified result.

## Suggested fix

1. Have the tokenizer return a status alongside the tokens, so "empty prompt" and "tokenization failed" are distinguishable.
2. Add the same guard the speculative and MTP paths already have to the generate, cancellable, streaming, and complete paths.
3. Make the C API `count_tokens` match its doc comment, or fix the doc.

`include/entropic/inference/tokenizer.h` is a seam header, not under `interfaces/`, but changing its signature is still a design change under the project rules. I'd raise it as a proposal before editing it.