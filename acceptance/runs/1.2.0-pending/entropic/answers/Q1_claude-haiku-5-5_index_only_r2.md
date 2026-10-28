**Why it calls twice:** The two `llama_tokenize` calls are both in one function, `entropic::LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:49-71`), not in two places. The first call passes a null buffer and size 0 to get the required token count. llama.cpp returns that count negated, and the code flips it back to positive. The second call fills a vector of that size. This is the standard size-query idiom, so the code does not know the token count up front.

**Is it retry logic?** No. The second call is unconditional, there is no loop, and nothing re-issues a call after a failure. It is a two-phase allocate-then-fill. A failure of the second call is logged at error level and returns an empty vector. It is not retried.

**What the caller receives on failure:** An empty `std::vector<int32_t>`. The tokenizer also returns empty when `vocab_` is null. The tokenizer does not return an error code, and the wrapper `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788-800`) passes the empty vector through, or returns empty when no tokenizer is wired.

**What the callers do with it:**

| Caller | Behaviour on empty input |
|---|---|
| `do_complete` | No check. Logs "0 input tokens" and passes the empty vector to `decode_loop`. `decode_loop` only fails if `run_prefill` fails, and I did not read `run_prefill`, so I cannot say whether an empty prompt is caught there. |
| `do_generate_text_only` | No check on the token count. It runs `run_prefill_cached`, and only a `false` return from that becomes an error. |
| `generate_speculative_with_draft` | The only explicit handling. `tokens.size() < 2` returns `ENTROPIC_ERROR_GENERATE_FAILED` with "speculative prompt must have at least 2 tokens". |
| `compute_prefix_token_count` | Empty becomes a prefix length of 0, which the prompt cache treats as no reusable prefix. No error. |
| `do_count_tokens` / `entropic_inference_count_tokens` | Returns 0. The C API documents 0 as the answer for empty text, so a failed tokenization is indistinguishable from empty input. The `len/4` fallback only runs when an exception is thrown, not on tokenize failure. |

Separately, `mtmd_prefill` calls `mtmd_tokenize` once and then `mtmd_helper_eval_chunks`. That is a different llama.cpp call pair in a different function, and it returns a real error code (`ENTROPIC_ERROR_GENERATE_FAILED`) with a message. It is not the text tokenizer path.

**Bottom line:** A text-tokenization failure is silent. It becomes an empty token list, and only the speculative path turns that into an error. Generation paths can run with zero input tokens, and the count API reports 0. The index does not show whether `run_prefill` or `decode_loop` rejects an empty prompt, so that is the one thing to read directly if you need to confirm the generation paths.