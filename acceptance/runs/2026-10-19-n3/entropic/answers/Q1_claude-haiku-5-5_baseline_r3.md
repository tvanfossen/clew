**Why it calls twice:** It's a size probe, not a retry. Both calls are in one function, `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:55` and `:61`). llama.cpp's `llama_tokenize` needs a buffer, and when the buffer is null or too small it returns the negative of the required token count. The first call passes no buffer to learn the size, the code negates it (line 58), allocates, and the second call fills the buffer. The second call runs unconditionally, with no loop, backoff, or condition on the first result. The comment at line 45 and the code comment at line 97 both say "retry", which is a misleading name. "Size probe" describes it better.

The only other `llama_tokenize` double call I found is in `tests/model/test_gh87_common_chat_e2e.cpp:51-56`, which uses the same pattern.

**What the caller gets on failure:** An empty `std::vector<int32_t>`. There's no error code or exception. The failure path logs at error level (`llama_cpp_tokenizer.cpp:65`) and returns `{}`. A null `vocab_` also returns `{}` silently. The header contract (`include/entropic/inference/tokenizer.h:51`) says "empty on failure or empty input", so callers can't tell a failure from a legitimately empty string.

**What the callers do with it:**

| Caller | Behavior on empty result |
|---|---|
| `count_tokens` / `do_count_tokens` (`llama_cpp_backend.cpp:825`), C API `entropic_inference_count_tokens` | Returns 0, which looks like an empty prompt. The cold-model path returns a `len/4` estimate instead, so the two cases differ. |
| `tokenize_text` (`:837`) | Passes the empty vector up. |
| `compute_prefix_token_count` (`:2051`) | Returns 0. That feeds the prefix-cache logic at `:2289`, which I did not trace. |
| `generate` (`:2561`), `generate_cancellable` (`:2643`), `stream` (`:2728`) | No check. Empty tokens go to `run_prefill_cached`. `run_prefill` (`:1484`) clears KV memory, decodes nothing, and returns `true`. I did not trace what the decode loop does next with no prompt logits, so I can't say whether it errors or emits garbage. |
| `complete` (`:3947`) | No check. Same path as generate via `decode_loop`. |
| Speculative (`:3593`) and MTP (`:3921`) | Check `tokens.size() < 2` and return `ENTROPIC_ERROR_GENERATE_FAILED`. These are the only paths that turn a failure into an explicit error, but the message says "prompt must have at least 2 tokens", which misreports a tokenization failure as a short prompt. |
| Batch (`:1911`) | `batch_shared_prefix_len` returns 0 when any sequence is empty, so the batch path proceeds with an empty sequence. I did not trace further. |

**Practical takeaway:** A tokenization failure is invisible to most callers. Only the speculative and MTP paths produce an error, and it's the wrong one. The generate, stream, and complete paths push zero tokens into prefill and succeed silently. Fixing this would mean returning a status alongside the vector, or at least checking `text.empty()` before treating an empty result as a failure. I haven't verified the downstream behavior of the generate path with zero tokens, so that's the first thing to confirm by running it.