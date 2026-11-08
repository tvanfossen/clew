**Why it calls twice:** This is a sizing query followed by a fill, not retry logic. In `src/inference/llama_cpp_tokenizer.cpp:55-63`, the first `llama_tokenize` call passes a null buffer with capacity 0. llama.cpp answers with the negated token count it would need, which the code flips to a positive `n`. The second call allocates a vector of that size and fills it. The first call is not a failure; it is how the API asks for the size. The only real failure check is `actual < 0` on the second call, which logs an error and returns `{}`. The other tokenize-in-two-places pattern is the same thing in `compute_prefix_token_count` and in `do_count_tokens`, which just calls `tokenize` again. Nothing re-attempts after a failure.

**What the caller receives on failure:** An empty `std::vector<int32_t>`. The same empty vector comes back when the vocab pointer is null or when no tokenizer is wired (`llama_cpp_backend.cpp:795`). Nothing distinguishes failure from a legitimately empty result, and no error code reaches the caller.

Downstream, the behavior depends on the entry point:

| Caller | What happens with `{}` |
|---|---|
| `do_count_tokens` → `entropic_inference_count_tokens` | Returns **0** to the C API user. The "count" looks like a valid answer. Only the C API's `catch(...)` path uses `len/4` as an estimate. |
| `compute_prefix_token_count` | Returns 0, so the system-prefix cache boundary is 0. I did not trace the effects. |
| `do_generate_text_only`, `do_generate` (cancellable), `do_stream`, `do_complete` (`llama_cpp_backend.cpp:2561, 2643, 2728, 3947`) | **No empty check.** `run_prefill` on zero tokens clears the KV memory, decodes nothing, and returns true. Sampling then starts from whatever logits the context holds. I did not verify what that produces, but it is not an error path. |
| Speculative and MTP (`:3594, 3922`) | Guarded by `tokens.size() < 2`, so they return an error, but the message says "must have at least 2 tokens". The real cause, a tokenization failure, is hidden. |
| Batched generate (`:1911`) | Empty per-request token vectors feed `batch_shared_prefix_len` and `run_batched_decode` unchecked. I did not trace this further. |

**Assessment:** A tokenization failure is converted into a value that looks like success, and most callers keep going. The one log line records only the text length, and the caller never sees an error code. The intent behind the seam, as described in the comments, is that errors are reported through error codes and callbacks, so this is a gap.

**Caveats:**
- I did not open `llama.h` to confirm the negative-return convention. The code's comments and the two-call pattern both assume it.
- The behavior of generation with an empty prompt is inferred from reading the code. I did not run it.
- The tokenizer seam is part of the interface contract. The project rules say changing `include/entropic/...` interface headers needs a new proposal and user approval, so the fix (returning a status from `tokenize` and rejecting empty prompts in the generate paths) should go through that process.