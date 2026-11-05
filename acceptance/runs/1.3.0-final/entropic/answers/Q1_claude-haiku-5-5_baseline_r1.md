**Why it calls twice:** It's a size-probe followed by a fill, not a retry. `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:49-71`) first calls `llama_tokenize` with a null buffer and zero length. llama.cpp answers with the negative of the required token count, and the code flips the sign. It then allocates that many slots and calls `llama_tokenize` again to fill them. The second call's return value is the actual count, and it's the only place failure is detected.

It isn't retry logic. Nothing is re-attempted after a failure, no inputs change, there's no backoff, and the first call's result is always used. The comments in the file (the header says "sized retry", and the `@return` line says "on the sized retry") are misleading, and the name should be fixed.

**What the caller receives on failure:** An empty `std::vector<int32_t>`. The seam logs an error with the text length, then returns `{}`. `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788-800`) passes that empty vector straight through. The header contract (`include/entropic/inference/tokenizer.h:45-52`) says "empty on failure or empty input", so the caller can't tell the two apart. The failure is visible only in the log.

**What the callers do with it:**

| Caller | Line | Behaviour on empty tokens |
|---|---|---|
| `do_generate_text_only`, `do_generate_cancellable`, `do_generate_streaming` | 2561, 2643, 2728 | No guard. Logs "0 input tokens" and goes on to `run_prefill_cached`. `run_prefill` (1484) loops zero times and returns true, so the call proceeds to sampling with no prompt decoded. The result is a generation that looks successful. I did not trace `step_token` to see what logits it samples from; that needs a test. |
| `do_complete` | 3947 | No guard. Calls `decode_loop` with an empty prompt, same silent path. |
| `do_generate_batch` | 1911-1922 | Empty sequence gets into the shared-prefix and viability logic (`batch_shared_prefix_len` returns 0 for it). I did not verify what `run_batched_decode` does with an empty sequence. |
| Speculative and MTP paths | 3593, 3921 | Guarded: `tokens.size() < 2` returns a `spec_error`. These are the only callers that handle it. |
| `compute_prefix_token_count` | 2066 | Returns 0, which reads as "no system prefix". This quietly disables the prefix-cache sizing. |
| `do_count_tokens` → `count_tokens` | 825-828, `backend.cpp:496` | Returns 0 when the backend is loaded. Callers get a count of zero with no error. |
| C API `entropic_inference_count_tokens` | `inference_c_api.cpp:548-562` | Returns 0 on a tokenizer failure. Its doc comment says "text_len/4 estimate on error", which the code does not do. The `/4` path only runs when an exception is thrown. |

**Summary:** A tokenizer failure is indistinguishable from empty input. Generation and completion then run with no prompt, and counting reports zero. Only the speculative and MTP paths check for it. Two changes would fix most of this. First, have the seam return an error code or `std::optional`, not an empty vector. Second, have `do_generate_*` and `do_complete` return an error when the token list is empty, as the speculative paths already do. The C API doc should also be corrected to match the code or the other way around. I haven't changed anything, and I haven't run the tests.