**Why it calls twice:** `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:49-71`) uses llama.cpp's two-phase sizing protocol. The first `llama_tokenize` call passes a null buffer and zero capacity, so llama.cpp returns the negated token count it would need. The code flips the sign, allocates a vector of that size, and makes the second call to fill it. The first call is a size query, not an attempt that failed.

**Is it retry logic?** No. The second call is unconditional and runs on every input, whether or not the first one "failed." The only error check is on the second call. Nothing re-runs the same operation on failure.

The "two places" are the same pattern in two functions:
- `tokenize` always makes two `llama_tokenize` calls.
- `detokenize` (lines 86-105) makes a second `llama_token_to_piece` call only when the 256-byte stack buffer is too small. That is size-on-demand, and it is still not retry.

**What the caller receives on failure:**

| Layer | Failure result | Notes |
|---|---|---|
| `LlamaCppTokenizer::tokenize` | `{}` | Also `{}` when `vocab_` is null. Logs one error line. |
| `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788`) | `{}` | Also `{}` when `tokenizer_` is unset. |
| `LlamaCppTokenizer::detokenize` | `""` | Logs nothing on the second-call failure path. |

The empty vector is indistinguishable from a legitimate empty result. With `add_special=false` and `""`, `{}` is correct. No error code or flag reaches the caller.

**What the callers do with it:**

- **`do_count_tokens`** (`:825`) returns 0. `count_tokens` and `entropic_inference_count_tokens` (`inference_c_api.cpp:548`) pass 0 through. The C API has no error channel for this, so a caller doing context budgeting sees "0 tokens" and proceeds.
- **`tokenize_text`** (`:837`) returns an empty vector to its caller.
- **Generation entry points** (`do_generate_text_only` `:2561`, the cancellable variant `:2643`, the stream variant `:2728`, `do_complete` `:3947`) log "0 input tokens" and pass the empty vector to `run_prefill_cached`. `run_prefill` (`:1484`) loops over zero chunks and returns `true` (`:1502`). So generation proceeds with no prompt decoded, and no error is returned. I did not trace the cache-HIT path or the decode loop after that, so I can't say exactly what text the model produces. The only signal is the log line.
- **Speculative and MTP paths** (`:3593`, `:3921`) check `tokens.size() < 2` and return `ENTROPIC_ERROR_GENERATE_FAILED`. This is the only place a tokenizer failure surfaces as an error, and the message ("prompt must have at least 2 tokens") misattributes the cause.
- **System-prompt token accounting** (`:2066`) returns 0, which corrupts prefix-count bookkeeping without any error.
- **`detokenize` failure** returns `""`. In generation (`:1534`), the piece is appended as empty, `on_token` fires with an empty `string_view`, and the stop-sequence check runs on unchanged text. Streamed output silently drops a token.

**Bottom line:** the sizing double-call is correct and not retry logic. The failure contract is the problem. Tokenization failure is reported as an empty vector, which the generation paths treat as a valid zero-length prompt, and the only log is one error line in the tokenizer. Most callers do not check for it. If you want this fixed, the smallest change is to return a `Result`-style status from `LlamaCppTokenizer::tokenize` and have the generation entry points reject an empty prompt when the input text was non-empty. That is a design change, so I have not made it.

I did not run any tests or builds. The findings come from reading the code.