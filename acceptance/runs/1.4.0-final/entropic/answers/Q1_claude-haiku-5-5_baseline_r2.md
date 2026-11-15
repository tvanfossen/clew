**Why it calls twice:** The two `llama_tokenize` calls are a size-probe followed by a fill, not a retry. In `src/inference/llama_cpp_tokenizer.cpp`, the first call (line 55) passes a null buffer and zero length. llama.cpp answers with the negated token count it needs. The code allocates that many slots and makes the second call (line 61) to fill them. Both calls are unconditional, and the second one has no retry loop, backoff, or fallback. The header comment's "sized retry" wording (line 45) is misleading. Both calls are in the same function, and `src/` has no other `llama_tokenize` call sites. The backend's `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788`) is a one-line delegation to the seam, so it adds no second call.

**Failure path:** If the second call returns negative, the tokenizer logs one `error` line (`llama_cpp_tokenizer.cpp:65`) and returns an empty `std::vector<int32_t>`. There is no status code, exception, or `optional`. The backend passes that empty vector through unchanged. An empty result is also what valid empty input produces when `add_special=false`, so the two cases can't be told apart by the return value.

**What the callers do with the empty vector:**

| Call site | Behavior on empty |
|---|---|
| `do_generate_text_only`, the cancellable generate path, and the stream path (~2561, 2643, 2728) | Log "0 input tokens" and continue. `run_prefill` with zero tokens clears the KV cache and returns `true`, because its loop never runs. Sampling then starts with no decode behind it. I did not trace what the sampler does in that state, so the outcome is unverified. |
| Speculative (~3593) and MTP (~3921) | Hit the `tokens.size() < 2` guard and return `ENTROPIC_ERROR_GENERATE_FAILED` with "must have at least 2 tokens". The real cause, a tokenizer failure, appears only in the tokenizer's own log. |
| `do_complete` (~3947) | Passes the empty vector to `decode_loop` with no check. Same path as the first row. |
| `do_count_tokens` (~825) | Returns `0`. A caller doing context budgeting would treat that as "fits". |
| Batch path (~1911) | The empty vector goes into `batch_shared_prefix_len`, which returns 0 when any sequence is empty. No error is raised. |
| `detokenize` (`llama_cpp_tokenizer.cpp:86`) | Failure returns `""`, so output tokens are dropped silently. |

So a tokenization failure becomes an empty vector, and most callers either continue into inference or report a misleading "too few tokens" error. Only the speculative and MTP paths produce an error code, and it is the wrong one.

**Possible fix:** Change the seam's `tokenize` to return a status, or an `expected`/`optional`, and map it to an `ENTROPIC_ERROR_*` code at the backend boundary. `include/entropic/inference/tokenizer.h` is an interface header, and CLAUDE.md says those change only through a new proposal with user approval, so this needs your sign-off before I make it.