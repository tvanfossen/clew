**Short answer:** the two calls are in one function, not two places, and they are a size-probe followed by the real call. That is not retry logic. When tokenization fails, the caller gets an empty vector, which the layers above treat as an ordinary result.

**Why it calls twice**

The only `llama_tokenize` calls in `src/` are in `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:55` and `:61`). llama.cpp's API needs a caller-supplied buffer, so the first call passes `nullptr, 0`. It returns the required size as a negative number. The code negates it (line 58), allocates a vector of that size, and calls again to fill it (line 61). The second call is the one that produces the tokens.

The other `llama_tokenize` hit is `tests/model/test_gh87_common_chat_e2e.cpp:51-56`, which uses the same two-call pattern in a test helper. The vision path calls `mtmd_tokenize` once (`src/inference/llama_cpp_backend.cpp:2407`), which is a different API.

**Is it retry?** No. Nothing is retried on failure. If the second call returns a negative value, the code logs at ERROR (line 65) and returns `{}`. The probe is a protocol requirement, not a second attempt at the same operation.

**What the caller receives on failure**

Failure is reported as an empty `std::vector<int32_t>`. No error code or exception reaches the caller. Empty is also the legitimate result for empty input, so the caller cannot tell the two apart. A null `vocab_` also returns `{}`, but silently, with no log (line 52).

The call chain I traced:

| Caller | What it does with the empty result |
|---|---|
| `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788`) | Passes it through. Returns `{}` if no tokenizer is wired. |
| `do_count_tokens` (`:825`) | Returns 0. |
| `tokenize_text` (`:837`) | Returns the empty vector. Its doc says "empty if COLD or error". |
| `entropic_inference_count_tokens` (`inference_c_api.cpp:548`) | Returns 0 to C callers. Its `len/4` fallback runs only on an exception, not on a failed tokenize, so a tokenize failure gives 0, not the estimate. |
| `do_generate_text_only`, `do_stream`, `do_complete` (`:2561`, `:2643`, `:2728`) | Log "N input tokens" and continue into `run_prefill_cached` / `decode_loop` with no check for empty. |
| Speculative and MTP paths (`:3593`, `:3921`) | Check `tokens.size() < 2` and return `ENTROPIC_ERROR_GENERATE_FAILED`. These are the only generation paths I found that guard against empty input. |

**Unverified:** I did not trace what `run_prefill` and `decode_loop` do with an empty token vector. `run_prefill`'s loop body does nothing when `n_tokens` is 0, so a generation could proceed with no prompt decoded. I would confirm that before relying on it.

**Practical implication:** an encoding failure looks like a zero-token prompt. Token counts silently read as 0, and generation can run on no prompt. The only error log is the one line in `LlamaCppTokenizer::tokenize`. A fix would have `tokenize` report failure distinctly (for example, an error out-parameter or `std::optional`) and have the generation entry points reject it.