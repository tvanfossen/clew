**Short answer:** neither double call is retry logic. Both are the llama.cpp two-phase sizing idiom: call once with no buffer to learn the required size, then call again with a buffer of that size. Failure is not retried, and a failed tokenization returns an empty result that the callers mostly don't check.

## The two double calls

| Site | First call | Second call | Runs when |
|---|---|---|---|
| `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:55`, `:61`) | `llama_tokenize(..., nullptr, 0, ...)` to get the count | `llama_tokenize(..., tokens.data(), n, ...)` to fill | Always, on every call |
| `LlamaCppTokenizer::detokenize` (`:93`, `:99`) | `llama_token_to_piece` into a 256-byte stack buffer | Re-call with `-n` bytes | Only when the 256-byte buffer was too small |

The tokenize path is the probe. The detokenize path is a fallback that runs only when the first buffer is too small. In both, the second call is the real work. Neither is retried after a failure, and neither loops.

The tokenize code also has a small flaw. It negates a negative first return without checking whether it means "needed size" or a real error. A real error therefore still allocates a vector of that size, and only the second call reports the failure. The result is still empty, so the outcome is correct, but it is an unneeded allocation.

## What the caller receives on failure

- `LlamaCppTokenizer::tokenize` logs at error level and returns `{}`. Failure and empty input look the same to callers.
- `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788`) forwards that empty vector. It returns `{}` when no tokenizer is wired too.
- `detokenize` returns `""` on failure.

No exception or error code leaves the tokenizer.

## What the callers do with the empty result

| Caller | What it does with empty tokens |
|---|---|
| `do_generate_text_only`, `do_generate_streaming_text_only`, cancellable generate (`:2561`, `:2643`, `:2728`) | Logs the count, then calls `run_prefill_cached` with the empty vector. Nothing checks for empty, so the failure is handled only by whatever prefill does with zero tokens. I did not read `try_warm_reuse` or `prefill_dispatch`, so I can't say what that yields. |
| `do_generate_batch` (`:1911`) | Empty sequences feed the shared-prefix and viability checks. Not checked for empty. |
| `do_complete` (`:3947`) | Passes the empty vector to `decode_loop` → `run_prefill`. Error only if prefill itself fails. |
| Speculative (`:3593`) and MTP (`:3921`) | The only callers that check: `tokens.size() < 2` returns `ENTROPIC_ERROR_GENERATE_FAILED` with "must have at least 2 tokens". This surfaces the failure, but the message is misleading, since the real cause was tokenization. |
| `compute_prefix_token_count` (`:2066`) | Returns 0, so the prefix cache length becomes 0. |
| `do_count_tokens` → `count_tokens` (`backend.cpp:496`) | Returns 0. |
| `entropic_inference_count_tokens` (`inference_c_api.cpp:548`) | Returns 0 to the plugin caller. Its `len/4` fallback runs only on a C++ exception, and a tokenizer failure is not an exception. |
| `tokenize_text` (`:837`) | Returns empty to the public API. |
| Decode loop detokenize (`:1534`, `:1819`) | Appends `""`, so the token is silently dropped from the output. |

## Assessment

- Tokenization failure is silent throughout. The tokenizer logs once, and every caller turns the empty result into 0 tokens, an empty string, or a downstream error that does not name tokenization.
- The one caller that reports an error (speculative/MTP) misattributes it.
- The highest-impact gap is `entropic_inference_count_tokens`. A plugin caller gets 0 with no error signal, which can cause silent budget miscalculation.
- A fix would make `LlamaCppTokenizer::tokenize` report failure distinctly from empty input. That needs a change to the `Tokenizer` interface, so it is an interface change. Per the repo's CLAUDE.md, that requires explicit user approval. I have not made any change.

I did not run the code or check the pinned llama.cpp source for `llama_tokenize`'s exact return convention. The analysis is from reading the entropic source and its callers.