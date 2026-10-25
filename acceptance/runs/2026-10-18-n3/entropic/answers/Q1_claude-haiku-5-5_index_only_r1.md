**Short answer:** the double call is a size probe, not retry logic. The second call is deterministic and only happens because the first call reported that its buffer was too small. Tokenization failure isn't retried. It comes back as an empty result, and callers can't distinguish that from a genuinely empty input.

**Why it calls twice**

I couldn't read the body of `LlamaCppTokenizer::tokenize` directly; the index didn't resolve that qualified name. The doxygen for it says the method returns empty "if `llama_tokenize` returned a negative actual-count on the sized retry." The file doc says the adapter "forwards to `llama_tokenize` / `llama_token_to_piece`." Together with llama.cpp's convention (a negative return means "buffer too small, here's the required size"), the pattern is:

1. Call `llama_tokenize` with a buffer to learn the token count.
2. If the count is negative, allocate that size and call again.

I believe `detokenize` has the same shape with `llama_token_to_piece` (its doc mentions a "retry decode"). That's the likely "two different places," but I haven't confirmed it from the body.

Would I call it retry? No. Nothing transient is being retried, and the second call's result isn't a fallback for a failed first attempt. It's a two-phase sizing protocol.

**What the failure produces**

| Layer | On failure, returns | Source |
|---|---|---|
| `LlamaCppTokenizer::tokenize` | empty `vector` (null vocab, or bad sized retry) | doxygen |
| `LlamaCppBackend::tokenize` | empty if `tokenizer_` is null, otherwise passes through | `llama_cpp_backend.cpp:788` |
| `do_count_tokens` | `0` (size of the empty vector) | `llama_cpp_backend.cpp:825` |
| `compute_prefix_token_count` | `0` | `llama_cpp_backend.cpp:2051` |
| `Tokenizer::count_tokens` default | `0` | `tokenizer.h:74` |
| `InferenceBackend::tokenize_text` base | `{}` | `backend.h:273` |

**What the callers do with it**

- **`do_complete`** (`llama_cpp_backend.cpp:3941`): calls `tokenize(prompt, false)`, logs "0 input tokens", then goes straight into `decode_loop`. It never checks for empty.
- **`decode_loop`** calls `run_prefill`. `run_prefill` with zero tokens doesn't enter its loop, so it returns `true`. The empty prompt is accepted as success and generation proceeds. Its error path (`ENTROPIC_ERROR_GENERATE_FAILED`, "Prefill decode failed") is never reached for this case. I haven't read `generate_after_prefill` and can't confirm what it does with an empty KV state, but nothing in the index shows an error there.
- **`prefill_dispatch`**: a `0` from `compute_prefix_token_count` means the prefix boundary is zero, so the prompt cache stores a zero-length prefix.
- **Token-count consumers** (`do_count_tokens`, `count_tokens`): they report 0 tokens for a prompt that failed to tokenize, and the caller can't tell it apart from a real empty string.

So the failure is silent. The only thing that signals it is a log line (if any), and the empty prompt continues through the generation path as though it were valid. The one error code that exists on this path is set only when prefill itself fails, not when tokenization fails.

**Caveats**

- The tokenizer-body and `generate_after_prefill` claims rest on doxygen and the callee graph, not the source. Reading `llama_cpp_tokenizer.cpp` would confirm the double call and whether the failure path logs anything.
- I didn't check whether `LlamaCppBackend::tokenize_text` (the override at `llama_cpp_backend.h:837`) handles empty results differently from the base.