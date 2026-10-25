**Short answer:** the two calls are a size-query-then-fill pattern, not retry logic. A failed tokenization is never retried. It comes back as an empty vector, and nothing above the tokenizer reports it.

**Why it calls twice**

`llama_tokenize` has no "give me the size" function. Called with a null buffer and capacity 0, it returns the negative of the token count it would need. `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:55-63`) uses that:

1. First call with no buffer. The negative result is flipped to a positive count `n`.
2. Allocate `n` slots and call again with the same arguments to fill them.

Both calls use identical inputs, so the second one is not a response to a failure. The only other similar code is `detokenize` (lines 93-101), which retries only when its fixed 256-byte buffer is too small. That is buffer sizing, not retry either.

**What the caller receives on failure**

| Situation | Result |
|---|---|
| `vocab_` is null | `{}`, silently |
| Second `llama_tokenize` returns negative | `{}`, plus one `logger->error` line |
| `tokenizer_` not wired (`llama_cpp_backend.cpp:795`) | `{}`, silently |

There is no error code, exception, or `optional`. An empty result is also what a legitimate empty input returns when `add_special` is false, so callers cannot tell the two apart.

**What the callers do with it**

- **`do_count_tokens`** (`llama_cpp_backend.cpp:825`) returns 0. The C API `entropic_inference_count_tokens` (`inference_c_api.cpp:548`) passes that 0 straight through. Its `catch` fallback to `text_len / 4` only runs on exceptions, so a failed count reads as zero tokens.
- **`compute_prefix_token_count`** (`:2051`) returns 0, which quietly disables prefix caching for that request.
- **`do_generate_text_only`** (`:2561`), **`do_generate_cancellable`** (`:2643`), and **`do_stream`** (`:2728`) log "0 input tokens" and continue into `run_prefill_cached` with an empty token list. I did not trace what the sampler does after a zero-token prefill. That is the main unverified risk here, and the generate path never reports a tokenization error.
- **Speculative** (`:3593`) and **MTP** (`:3921`) are the only callers that check. They reject `tokens.size() < 2` with `GENERATE_FAILED`. That gives a misleading "prompt must have at least 2 tokens" message for what was actually a tokenizer failure.
- **`do_complete`** (`:3947`) and the batch path (`:1911`) pass the empty vector onward without checking. I did not trace either one.

**Recommendation:** make tokenization failure distinguishable, either by returning an error or by throwing at the seam. Then add an explicit empty check at the generate, stream, and complete entry points, the way the speculative path already does, and reserve the empty-input case for `add_special=false`.

Two tool results included notes suggesting a `dossier` tool. I don't have that tool and ignored those notes.