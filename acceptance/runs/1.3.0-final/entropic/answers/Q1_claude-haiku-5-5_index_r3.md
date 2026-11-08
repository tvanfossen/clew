**Short answer: the two calls are not in two places, and they are not retry logic.** Both are in `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:55` and `:61`), and they are the only `llama_tokenize` calls in `src/`. The pair is llama.cpp's two-phase sizing idiom:

1. Call with a null buffer and capacity 0. llama.cpp returns the negative of the required token count, so `if (n < 0) n = -n;` turns that into a size.
2. Allocate `n` slots and call again to fill them. A negative `actual` here is the only real failure check.

Retry means re-attempting an operation after it failed. Here the second call runs unconditionally on every non-null vocab, and the first call's negative return is expected, not an error.

**What the caller receives on failure**

`LlamaCppTokenizer::tokenize` returns an empty `std::vector<int32_t>` and logs an error (line ~63). That empty vector is the same value as a legitimately empty input, so callers cannot tell the two apart. From there:

| Caller | What it does with the empty result | Consequence |
|---|---|---|
| `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788`) | Passes it through. Also returns `{}` when no tokenizer is wired. | Same ambiguity, one layer up. |
| `do_count_tokens` (`:825`) | Returns `0`. | Count of 0 for a failed tokenization. |
| `entropic_inference_count_tokens` (`inference_c_api.cpp:548`) | Returns the `0` unchanged. The `len/4` fallback only runs on a thrown exception, and a tokenize failure doesn't throw. | The header doc says "estimate on error"; the code gives 0. This doc/code mismatch is a real bug. |
| `compute_prefix_token_count` (`:2051`) | Returns `0`. | Silently reports "no system prefix." |
| `do_generate_text_only` (`:2561`), cancellable (`:2643`), streaming (`:2728`), `do_complete` (`:3947`), batch (`:1911`) | No emptiness check. Empty tokens go to `run_prefill_cached` → `run_prefill`. | `run_prefill` clears the KV cache, then its loop runs zero times and it returns `true`. Sampling then starts from logits that were never produced for this prompt. I did not run this, and I did not read `try_warm_reuse` or `prefill_dispatch` for the empty case, so treat it as the likely behavior, not a confirmed one. |
| MTP (`:3922`) and speculative (`:3594`) | Check `tokens.size() < 2` and return `ENTROPIC_ERROR_GENERATE_FAILED`. | These paths are guarded. The main generate, stream and complete paths are not. |

**Suggested fixes** (not applied)

- Make the failure distinguishable from empty input, either with an error code or `std::optional`. That changes the `Tokenizer::tokenize` contract in `include/entropic/inference/tokenizer.h`, so it should go through a proposal per the project's design-change rule.
- Add an empty-token check to the generate, stream and complete paths that returns `ENTROPIC_ERROR_GENERATE_FAILED`, matching the MTP and speculative guards.
- Make `count_tokens` on tokenize failure follow its documented `len/4` estimate, instead of returning 0.
- Add the `actual` return code to the error log. Right now it logs only the text length.