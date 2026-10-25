## Why it calls llama.cpp twice

The two calls are in `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:55` and `:61`). The first call passes a null buffer and size 0, so llama.cpp returns the negative of the token count it would need. Line 58 flips the sign, the code allocates that many slots, and the second call fills them. This is a size-probe followed by the real call, the standard llama.cpp C-API pattern.

The file also has a second probe-then-fill in `detokenize` (`:93` and `:99`), which uses the same pattern for `llama_token_to_piece`.

I would not call either of these retry logic. A retry re-attempts an operation that failed, hoping for a different result. Here the first call's negative return is the library's normal way of reporting required size, not an error. The second call is the actual operation. The only real failure path is the `actual < 0` check at line 64, and with identical inputs and a correctly sized buffer it should not fire in practice.

## What the caller receives on failure

`LlamaCppTokenizer::tokenize` returns an empty vector and logs at ERROR with only the text length (`:64-67`). `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788-800`) passes the empty vector through silently. The backend itself adds no log, so the only trace is the tokenizer's ERROR line. An empty vector is also what it returns when no tokenizer is wired, so the two cases look the same to callers.

What each caller does with the empty result:

| Caller | On empty tokens | Guarded? |
|---|---|---|
| `do_generate_text_only` (`:2555`) and `do_generate_streaming_text_only` (`:2720`) | Logs "0 input tokens", then calls `run_prefill_cached` with no check | **No** |
| `do_complete` (`:3941`) | Logs "0 input tokens", then calls `decode_loop` | **No** |
| `generate_mtp` (`:3906`) and `generate_speculative_with_draft` (`:3571`) | Returns `GENERATE_FAILED` when fewer than 2 tokens | Yes |
| `do_count_tokens` (`:825`) | Returns 0 | Returns a value that looks valid |
| `compute_prefix_token_count` (`:2051`) | Returns 0, so `prefill_dispatch` gets a zero-length prefix | Not checked |

The two text-generation paths are the most concerning. `run_prefill` with zero tokens loops zero times and returns true (`llama_cpp_backend.cpp:1484-1503`). Generation then proceeds on a context where no prompt was decoded. I did not trace what the sampler reads from the logits in that state, so I can't say what the output looks like. I would expect garbage or an error, but this needs a test to confirm.

Token counting returns 0 on failure. `InferenceBackend::count_tokens` (`src/inference/backend.cpp:496`) only uses the len/4 estimate when the model is not loaded. The C API `entropic_inference_count_tokens` (`inference_c_api.cpp:548`) says it returns a len/4 estimate on error, but that fallback only runs on a thrown exception, not on a tokenizer failure. So a failed count returns 0, which contradicts the header's description.

## Summary

- The double call is a size-probe, not retry.
- Tokenization failure becomes an empty vector with one ERROR log in the tokenizer, and nothing else signals it.
- Only the speculative and MTP paths check for it. The plain generate, streaming and complete paths proceed with zero prompt tokens, and token counting reports 0.

The natural fix is to make `tokenize` return an error (or `std::optional`) and have each caller check it. That changes the `Tokenizer` seam, which is a design change under the project's rules, so I'd want your call before touching it.