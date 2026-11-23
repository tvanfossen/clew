**Short answer:** the two calls are a size probe followed by a fill, not retry logic. Failure produces an empty vector, and no caller treats that as an error.

**Why it calls twice**

`LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:49-71`) calls `llama_tokenize` at line 55 and again at line 61:

1. **Line 55** passes a null buffer and capacity 0. llama.cpp answers with the negated token count it would need, and the code flips the sign to get `n`.
2. **Line 61** allocates `n` slots and fills them. `actual` is the real count, and the vector is resized to it.

The second call runs unconditionally. It does not repeat on failure, so it is not retry. It is the standard two-phase sizing pattern for C APIs that cannot allocate for you.

**Where the retry-like pattern actually is**

`LlamaCppTokenizer::detokenize` (lines 93-104) is closer to retry. It tries `llama_token_to_piece` with a 256-byte stack buffer, and if that returns a negative size it allocates exactly that size and tries again. That is a grow-on-short-buffer fallback. It is still not a retry of a failed operation.

**What the caller receives on failure**

| Layer | On failure returns | Source |
|---|---|---|
| `LlamaCppTokenizer::tokenize` | empty `vector<int32_t>` | `llama_cpp_tokenizer.cpp:64-68`, after one `logger->error` |
| `LlamaCppBackend::tokenize` | empty `vector<llama_token>` | `llama_cpp_backend.cpp:788-800`; also empty when `tokenizer_` is null |
| `do_count_tokens` / `tokenize_text` | `0` / empty | `llama_cpp_backend.cpp:825-841` |
| `InferenceBackend::count_tokens` | `0` | `backend.cpp:496-502` |
| C API `entropic_inference_count_tokens` | `0`, also on null handle, null text, or exception (which returns `text_len/4`) | `inference_c_api.cpp:548-562` |
| `detokenize` | empty string | `llama_cpp_tokenizer.cpp:102-104` |

The empty vector is indistinguishable from a real empty result, so the failure is not visible to the caller except through the one error log.

**What the callers do with it**

- **Generation paths** (`llama_cpp_backend.cpp` around 2561, 2643, 2728, 3921, 3947) log "N input tokens" and pass the empty vector onward. I found no `tokens.empty()` guard before `run_prefill_cached` or `decode_loop`. I did not trace what prefill and decode do with zero tokens, so the downstream behavior is unverified.
- **Speculative (~3593) and MTP paths** do check `tokens.size() < 2` and return `ENTROPIC_ERROR_GENERATE_FAILED` with a message. These are the only guards I found.
- **Batch path** (~1911) feeds empty vectors into shared-prefix arithmetic. I did not verify that path either.
- **Streaming detokenize** (~1534, ~1819) silently emits an empty piece for a failed token.
- **Count and prompt-size callers** get `0` and cannot tell it from a real zero.

**Recommendation**

The seam is the wrong shape for failure. `Tokenizer::tokenize` should return a status, such as `std::optional` or an error code, so generation can fail fast with `ENTROPIC_ERROR_GENERATE_FAILED` instead of decoding zero tokens. `CLAUDE.md` says interface headers are immutable without a new proposal, so this needs your approval before I touch `include/entropic/inference/tokenizer.h`. The sizing pattern itself is fine as written.