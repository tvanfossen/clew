**Short answer:** The two calls in `LlamaCppTokenizer` are a size-query-then-fill pattern, not retry logic. The second call in `detokenize` is a true retry, but only for buffer sizing. Neither retries on failure. When tokenization fails, the caller gets an empty vector, which is indistinguishable from empty input, and most callers never check for it.

**Why `tokenize` calls llama.cpp twice** (`src/inference/llama_cpp_tokenizer.cpp:49-71`)

1. `llama_tokenize(vocab, text, len, nullptr, 0, ...)` passes no output buffer. llama.cpp answers with the negative of the required token count, and the code flips it to a positive size.
2. It allocates `vector<int32_t>(n)` and calls `llama_tokenize` again with that buffer to fill it.
3. If the second call returns negative, it logs `"Tokenization failed for text of length N"` and returns `{}`. Otherwise it resizes to `actual`.

This is deterministic: one probe, one fill. Nothing is retried after a failure.

**Why `detokenize` calls twice** (`llama_cpp_tokenizer.cpp:86-105`)

It is the one with a genuine retry shape, and it is still only about buffer size. It tries a 256-byte stack buffer with `llama_token_to_piece`. If that returns negative, the negative value is the required size, so it allocates exactly that and calls again. The second result is used if positive, and otherwise the function returns an empty string. Its own doc says so: "Empty when vocab_ is null or the retry decode returned non-positive."

**What the caller receives on failure**

- `LlamaCppTokenizer::tokenize` returns `{}` both when `vocab_` is null and when the fill call fails. The same is true for `detokenize`, which returns `""`.
- `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788`) forwards the empty vector. If no tokenizer is wired it also returns `{}`, so "no tokenizer", "llama.cpp error" and "empty prompt" all look the same.

**What the callers do with the empty vector**

| Caller | Behaviour on empty tokens |
|---|---|
| `do_generate_text_only` (`:2555`) | Logs "0 input tokens" and continues into `run_prefill_cached`. `run_prefill` with zero tokens runs no `llama_decode` and returns `true`, so generation proceeds from an empty context. No error is returned. |
| `do_complete` (`:3941`) | Same pattern. It calls `decode_loop` → `run_prefill`, which succeeds with zero tokens, and then samples. |
| `do_count_tokens` (`:825`) | Returns `0`. A count of zero is returned for a tokenizer failure, with no error signal. |
| `compute_prefix_token_count` (`:2051`) | Returns `0`, which quietly disables the system-prefix cache path. The full prefill still runs. |
| `tokenize_text` (`:837`) | Forwards the empty vector to its callers. |

I did not check whether `run_prefill` should reject zero tokens. Reading its body, the loop is skipped and it returns `true`. So for `do_generate_text_only` and `do_complete`, the most likely failure is generation from an empty context without any error code. The one logged signal is the `logger->error` in `LlamaCppTokenizer::tokenize`, which records only the text length.

**Gaps in the index:** I could not see the C API `entropic_inference_count_tokens` or the Python wrapper, so I cannot say what those surface to users. The batch path (`prefill_shared_and_fanout`) takes its `seq0` tokens from a caller I did not trace.