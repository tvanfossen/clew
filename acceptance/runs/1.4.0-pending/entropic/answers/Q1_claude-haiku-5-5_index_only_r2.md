**Short answer:** the two `llama_tokenize` calls are not in two different places. Both are in `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:49-71`, calls at lines 55 and 61). It is a size-probe, not retry logic.

**Why it calls twice**

1. The first call passes a null buffer and size 0. llama.cpp answers with a negative number whose magnitude is the required token count. The code negates it to get `n`.
2. It allocates `n` slots and calls again to fill them. `actual` is the real count, and the vector is resized to it.

The second call runs unconditionally after a successful probe. Nothing re-attempts a failed operation, so this is two-phase sizing, not retry.

**The other layers:** `LlamaCppBackend::tokenize` (`src/inference/llama_cpp_backend.cpp:788-800`) does no llama.cpp calls. It forwards to the `Tokenizer` seam and returns `{}` if no tokenizer is wired. `LlamaCppBackend::tokenize_text` (line 837) adds BOS by calling `tokenize(text, true)`.

**What the caller gets on failure**

`LlamaCppTokenizer::tokenize` returns an empty `std::vector<int32_t>`. It also returns empty when `vocab_` is null. The only signal is one `logger->error` line that records the text length, not the text. No error code or status travels up.

An empty vector also means "legitimately empty input", so the seam contract (`include/entropic/inference/tokenizer.h`) reads "empty on failure or empty input". Callers cannot tell the two apart.

**What callers do with the empty vector**

| Caller | Behaviour on empty tokens |
|---|---|
| `do_count_tokens` (`:825`) | Returns `0`. `entropic_inference_count_tokens` (`src/inference/inference_c_api.cpp:548`) passes that `0` straight to C callers. |
| `compute_prefix_token_count` (`:2051`) | Returns `0`, so the system-prefix size is silently zero. |
| `do_complete` (`:3941`) | Logs "0 input tokens" and calls `decode_loop` with an empty vector. |
| `do_generate_text_only` (`:2555`) | Logs "0 input tokens", then `run_prefill_cached` runs on an empty vector. Its failure path is `prefill_error()`. |
| `do_generate_batch` (`:1903`) | Empty token lists go into the batch-prefix logic. |

Two things to flag:

- **Count is silently wrong.** The C API's `catch` branch falls back to `len/4`, but a tokenizer failure does not throw. It returns `0`, so a failed count is reported as zero tokens. That breaks the documented "exact or estimate" contract.
- **Generation proceeds on empty input.** `do_complete` and `do_generate_text_only` do not check for empty tokens before prefill. Whether `decode_loop` or `run_prefill` then returns a clean error or produces garbage is something I could not establish from the index. The bodies of `run_prefill` and `run_prefill_cached` were not in the results I read.

The sizing pattern itself is fine. The gap is that a failure becomes an empty vector and is then treated as valid input by every caller above it.