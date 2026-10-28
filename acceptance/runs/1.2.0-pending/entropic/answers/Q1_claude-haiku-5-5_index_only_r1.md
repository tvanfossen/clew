**Short answer:** the two `llama_tokenize` calls are a size-probe, not retry. They sit in one function, `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:49-71`), at lines 55 and 61, not in two different places.

**Why it calls twice**

The function's own comment says "First call: get required size (negative return = required size)." llama.cpp's `llama_tokenize` doesn't allocate, so the first call passes a null buffer with capacity 0. It returns the token count, negated when the buffer is too small. The code flips the sign, allocates a vector of that size, and calls again to fill it. The second call is unconditional and runs once. There's no loop, no backoff, and no second attempt on the same input, so I wouldn't call it retry logic. It's a two-phase sizing protocol.

**What the caller gets on failure**

Failure is signalled only by an empty vector:

- If `vocab_` is null, it returns `{}` (line 52).
- If the second call returns a negative value, it logs `"Tokenization failed for text of length {}"` at error level (lines 64-68) and returns `{}`. The log includes only the length, not the text.
- `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788-800`) returns `{}` when no tokenizer is wired, and otherwise passes the result through unchanged.

A real failure and legitimately empty input look the same to the caller. The error log is the only signal.

**What the callers do with the empty vector**

| Caller | Empty result becomes |
|---|---|
| `do_count_tokens` (`cpp:825`) | `0` tokens |
| `InferenceBackend::count_tokens` (`backend.cpp:496`) | `0` when loaded; the `len/4` estimate applies only when COLD |
| `entropic_inference_count_tokens` (`inference_c_api.cpp:548`) | `0` to plugin C API callers. The `catch(...)` `len/4` fallback doesn't fire because nothing throws |
| `do_generate_text_only` (`cpp:2555`) / `do_generate_streaming_text_only` (`cpp:2720`) | Logs "0 input tokens", then calls `run_prefill_cached` with an empty sequence |
| `compute_prefix_token_count` (`cpp:2051`) | `0`, passed as the prefix length to `prefill_dispatch` |

The generation paths have no `tokens.empty()` guard. `run_prefill` (`cpp:1484`) loops over `n_tokens`, so with zero tokens it decodes nothing and returns `true`. Generation therefore proceeds with an empty prompt and reports success. I couldn't see from the index what `try_warm_reuse`, `prefill_and_cache_prefix` or `step_token` do with an empty prompt, so I can't say what the model produces in that case.

**Takeaway:** a tokenization failure is not raised or reported as an error. It becomes `0` tokens for counting and an empty-prompt generation for inference. The only trace is one error log line, which doesn't carry the text.