**Why it calls twice:** The two calls are in different methods, and neither is retry logic. Both are llama.cpp's size-probe idioms.

- **`LlamaCppTokenizer::tokenize`** (`src/inference/llama_cpp_tokenizer.cpp:55-63`): the first `llama_tokenize` passes a null buffer with size 0. llama.cpp returns the negated token count it would need. The code allocates that many slots and calls again to fill them. The first call never produces tokens, and the second is required regardless of outcome, so nothing is being retried.
- **`LlamaCppTokenizer::detokenize`** (`llama_cpp_tokenizer.cpp:93-101`): this tries a 256-byte stack buffer first. If llama.cpp reports the piece is larger, it resizes to the exact size and calls again. That is a buffer-size fallback, not a retry of a failed call.

The backend itself (`LlamaCppBackend`) never calls llama.cpp tokenization directly. It forwards through the `Tokenizer` seam (`llama_cpp_backend.cpp:788-800`, `:809-816`).

**What the caller receives on failure:**

- `tokenize` returns an empty vector. That is the only failure signal. It is also the normal return for empty input, so the two cannot be told apart. The error is logged only when the second call fails, and the log includes the text length but not the text.
- `LlamaCppBackend::tokenize` passes the empty vector through. It also returns empty when no tokenizer is wired, so "no tokenizer" and "tokenization failed" look the same too.

**What the callers do with the empty vector:**

| Caller | Behaviour on empty |
|---|---|
| `do_count_tokens` (`:825`) → `count_tokens` → `entropic_inference_count_tokens` | Returns `0`. The C API cannot report an error here. |
| `do_generate_text_only`, the cancellable variant, and the streaming variant (`:2561`, `:2643`, `:2728`) | Log "0 input tokens" and carry on. `run_prefill_cached` is called with an empty vector. On the cold path, `run_prefill` clears the KV cache, decodes nothing, and returns `true` (`:1484-1503`). So generation proceeds with no prompt and no error. I did not trace the warm-reuse path or the decode loop for a zero-token prompt. |
| Speculative and MTP (`:3593`, `:3921`) | Check `tokens.size() < 2` and return `ENTROPIC_ERROR_GENERATE_FAILED`. This is the only place a tokenizer failure becomes a real error. The message blames prompt length, not tokenization. |
| Batch path (`:1911`) and system-prompt token count (`:2066`) | Feed the empty vector into shared-prefix and suffix arithmetic, or return `0`. I did not trace these further. |
| `detokenize` returns `""` on failure (`llama_cpp_tokenizer.cpp:102-104`) | Streaming (`:1534`) and batch decode (`:1819`) append nothing, so the token is silently dropped from output. This path has no log at all. |

**Net effect:** a tokenization failure on the common generation paths does not surface as an error. The model generates from an empty or missing prompt, and the only trace is one error log line. Fixing this would mean returning a status or `std::optional` from the tokenizer seam so that callers can distinguish failure from empty input. That changes the seam interface, so it is your call, not something I should make.